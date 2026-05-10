-- ============================================================
-- Hemaya Policy AI — DB-1 Supplement: additional indexes
-- ============================================================
--
-- WHAT THIS ADDS
--   Indexes that the existing migration_indexes.sql does NOT cover,
--   surfaced by the schema audit (Phase D-* roadmap, section §4.1).
--
--   1. Partial index for the "open severity distribution" donut on the
--      Dashboard, which filters gaps WHERE status = 'Open'.
--   2. Two indexes on policy_ecc_assessments — heavily read by the
--      explainability router and the Mapping Review page.
--   3. A composite index on compliance_results that mirrors the
--      DISTINCT ON ordering used by /api/dashboard/stats.
--   4. A composite index on audit_logs covering the user activity
--      feed (actor_id + timestamp DESC).
--
-- WHAT THIS DOES NOT TOUCH
--   migration_indexes.sql is unchanged. This script is purely
--   additive. Every CREATE INDEX uses IF NOT EXISTS so it's safe
--   to re-run.
--
-- HOW TO RUN (Supabase)
--   The Supabase SQL Editor wraps statements in a transaction by
--   default, but CREATE INDEX CONCURRENTLY cannot run inside a
--   transaction. Two options:
--
--   Option A — psql (cleanest):
--       psql "$DATABASE_URL" -f scripts/db1_supplement_indexes.sql
--
--   Option B — Supabase SQL Editor, run each statement one at a
--   time. Keep an eye on the "ran outside a transaction" notice.
--
-- ROLLBACK
--   DROP INDEX IF EXISTS <name>;
--   Each index is independent.
-- ============================================================


-- ── 1. gaps: severity rollup on Open status only ─────────────
-- Powers the Dashboard severity donut, which filters status='Open'.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gaps_open_severity
    ON gaps (severity)
    WHERE status = 'Open';


-- ── 2. policy_ecc_assessments: explainability + mapping joins ──
-- Read on every Mapping Review page render, scoped by policy.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pea_policy_framework
    ON policy_ecc_assessments (policy_id, framework_id);

-- Partial index: rows the explainability page actually highlights
-- (everything that isn't 'compliant'). Smaller index, faster scan.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_pea_open_status
    ON policy_ecc_assessments (compliance_status)
    WHERE compliance_status IN ('partial', 'non_compliant');


-- ── 3. compliance_results: latest-per-framework lookup ────────
-- /api/dashboard/stats does:
--   SELECT DISTINCT ON (f.name) ... ORDER BY f.name, cr.analyzed_at DESC, cr.id DESC
-- A composite (policy_id, framework_id, analyzed_at DESC) helps the
-- WHERE filter AND the DISTINCT ON ordering in one index seek.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_compliance_results_pf_analyzed
    ON compliance_results (policy_id, framework_id, analyzed_at DESC);


-- ── 4. audit_logs: user activity feed ────────────────────────
-- Existing script has separate (actor_id) and (timestamp DESC).
-- Compound covers "show this user's recent N events" in one seek.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_actor_timestamp
    ON audit_logs (actor_id, timestamp DESC);


-- ============================================================
-- VERIFICATION
-- ============================================================
/*
SELECT schemaname, tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
      'idx_gaps_open_severity',
      'idx_pea_policy_framework',
      'idx_pea_open_status',
      'idx_compliance_results_pf_analyzed',
      'idx_audit_logs_actor_timestamp'
  )
ORDER BY tablename, indexname;
*/
