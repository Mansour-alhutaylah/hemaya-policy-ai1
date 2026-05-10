-- ============================================================
-- Hemaya Policy AI — SACS-002 Cache + Status Constraint Fix
--
-- WHAT THIS FIXES:
--
--   PART A — sacs002_verification_cache missing table:
--     The SACS-002 analyzer (Phase G.2) reads and writes a
--     verification cache that was only created by the startup
--     migration in main.py (gated on RUN_STARTUP_MIGRATIONS).
--     When that env-var is not set, every cache lookup throws
--     psycopg2.errors.UndefinedTable, which poisons the active
--     PostgreSQL transaction so every subsequent DB call in the
--     same session fails with "current transaction is aborted".
--     That forces all 92 controls to non_compliant regardless of
--     their actual evidence and corrupts the final score.
--
--   PART B — compliance_results.status CHECK constraint mismatch:
--     migration_integrity.sql added:
--       CHECK (status IN ('Compliant', 'Partial', 'Non-Compliant'))
--     Both ecc2_analyzer.py and sacs002_analyzer.py write:
--       status = 'completed'
--     This violates the constraint and leaves compliance_results
--     empty, so the UI cannot display the analysis results.
--
-- HOW TO RUN:
--   psql $DATABASE_URL -f scripts/migration_sacs002_cache.sql
--
-- SAFE TO RE-RUN: all DDL is guarded with IF NOT EXISTS / IF EXISTS.
-- ============================================================


-- ============================================================
-- PART A: sacs002_verification_cache
--
-- Schema mirrors ecc2_verification_cache (the reference impl for
-- ECC-2:2024) with two additions:
--   updated_at      — set by ON CONFLICT DO UPDATE; lets the UI
--                     surface "last used" age for cache entries.
--   ttl_expiration  — optional wall-clock expiry; the cache reader
--                     in sacs002_cache.py skips stale rows even if
--                     their cache key matches, preventing analysis
--                     results from being served from entries older
--                     than CACHE_TTL_DAYS (default 30).
--
-- Cache key invariants (all must change to invalidate):
--   control_code | policy_hash | prompt_version | model |
--   retrieval_floor | grounding_version | grounding_sim
-- The key is the SHA-256 of those values concatenated.
-- Bumping SACS002_PROMPT_VERSION in sacs002_analyzer.py produces
-- new keys for every entry, so old rows become unreachable without
-- any DELETE required.
-- ============================================================

CREATE TABLE IF NOT EXISTS sacs002_verification_cache (
    -- SHA-256 of all cache-key invariants (64 hex chars)
    cache_key       TEXT        PRIMARY KEY,

    -- Stored so ops can inspect what's in the cache without
    -- re-hashing. Not used in lookup logic.
    control_code    TEXT        NOT NULL,
    policy_hash     TEXT        NOT NULL,   -- first 16 hex chars of SHA-256(policy_text)
    prompt_version  TEXT        NOT NULL,   -- e.g. "v1"; bump to global-invalidate
    model           TEXT        NOT NULL,   -- e.g. "gpt-4o-mini"

    -- Full post-grounding control assessment dict (the return value of
    -- _assess_control). Stored as JSONB so PostgreSQL can index into it
    -- and ops can query individual fields without parsing in Python.
    result          JSONB       NOT NULL,

    -- Lifecycle timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Optional expiry. NULL = never expires. Set to
    -- NOW() + INTERVAL '30 days' by sacs002_cache.py on write.
    -- The cache reader filters with: ttl_expiration IS NULL OR ttl_expiration > NOW()
    ttl_expiration  TIMESTAMPTZ
);

COMMENT ON TABLE sacs002_verification_cache IS
    'Phase G.2 per-control post-grounding GPT result cache for SACS-002. '
    'Mirrors ecc2_verification_cache. Cache key = SHA-256 of '
    '(SACS002|control_code|policy_hash|prompt_version|model|'
    'floor=retrieval_floor|grounding=grounding_version|gsim=grounding_sim). '
    'Bump SACS002_PROMPT_VERSION in sacs002_analyzer.py to invalidate all entries.';

COMMENT ON COLUMN sacs002_verification_cache.cache_key IS
    'SHA-256 hex digest of all cache invariants. Primary lookup key.';
COMMENT ON COLUMN sacs002_verification_cache.result IS
    'Complete post-grounding _assess_control() return dict. '
    'Includes compliance_status, evidence_text, score, sub_results, etc.';
COMMENT ON COLUMN sacs002_verification_cache.ttl_expiration IS
    'Wall-clock expiry. NULL = immortal entry. '
    'sacs002_cache.py sets NOW() + 30 days on every write.';


-- ── Indexes ──────────────────────────────────────────────────────────────────

-- Primary lookup: exact cache_key match (covered by PK index).

-- Invalidation by policy: when a policy is re-uploaded or modified,
-- sacs002_cache.invalidate_policy(db, policy_hash) runs a DELETE
-- WHERE policy_hash = :ph — this index makes that O(log n).
CREATE INDEX IF NOT EXISTS idx_sacs002_cache_policy_hash
    ON sacs002_verification_cache (policy_hash);

-- Invalidation by control: useful for prompt-level invalidation
-- targeting a specific control family.
CREATE INDEX IF NOT EXISTS idx_sacs002_cache_control_code
    ON sacs002_verification_cache (control_code);

-- Composite: (control_code, policy_hash) supports the most common
-- cache-management query: "show all entries for this policy + control".
CREATE INDEX IF NOT EXISTS idx_sacs002_cache_control_policy
    ON sacs002_verification_cache (control_code, policy_hash);

-- Stale-entry scan: purge_expired() deletes rows WHERE
-- ttl_expiration IS NOT NULL AND ttl_expiration < NOW().
-- Partial index only covers rows that have an expiry set.
CREATE INDEX IF NOT EXISTS idx_sacs002_cache_ttl
    ON sacs002_verification_cache (ttl_expiration)
    WHERE ttl_expiration IS NOT NULL;

-- Age-of-cache visibility: ops can ORDER BY created_at DESC to find
-- the most recently populated entries.
CREATE INDEX IF NOT EXISTS idx_sacs002_cache_created_at
    ON sacs002_verification_cache (created_at DESC);


-- ── Row-Level Security ───────────────────────────────────────────────────────
-- Backend-only table: the anon / authenticated roles used by Supabase / PostgREST
-- must not be able to read or write cache entries directly.
-- No GRANT or SELECT policy is created — the backend connects as the
-- postgres superuser or a service role that bypasses RLS.

ALTER TABLE sacs002_verification_cache ENABLE ROW LEVEL SECURITY;
-- No policies → no direct access from the PostgREST / Supabase anon key.


-- ============================================================
-- PART B: Fix compliance_results.status CHECK constraint
--
-- The old constraint restricted status to compliance-level values
-- ('Compliant', 'Partial', 'Non-Compliant') but both analyzers
-- write a processing status ('completed'). This caused the final
-- summary-row INSERT to fail with a constraint violation, leaving
-- compliance_results empty and breaking the UI score display.
--
-- The fix drops the old constraint and replaces it with one that
-- covers both the processing statuses the backend actually writes
-- and the compliance-level values that older rows may contain.
-- Existing data is not affected (no UPDATE / DELETE required).
-- ============================================================

ALTER TABLE compliance_results
    DROP CONSTRAINT IF EXISTS chk_compliance_results_status;

ALTER TABLE compliance_results
    ADD CONSTRAINT chk_compliance_results_status
        CHECK (status IN (
            'completed',        -- set by analyzers after a successful run
            'failed',           -- set when analysis exits with an unrecoverable error
            'pending',          -- reserved for queued / async runs
            'Compliant',        -- legacy compliance-level values (kept for backward compat)
            'Partial',
            'Non-Compliant'
        ));


-- ============================================================
-- VERIFICATION QUERIES (run manually to confirm migration)
-- ============================================================

/*
-- A: Confirm table and columns exist:
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name   = 'sacs002_verification_cache'
ORDER BY ordinal_position;
-- Expected 8 rows: cache_key, control_code, policy_hash, prompt_version,
--                  model, result, created_at, updated_at, ttl_expiration

-- A: Confirm all indexes exist:
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'sacs002_verification_cache'
ORDER BY indexname;
-- Expected: 6 indexes (PK + 5 named indexes)

-- A: Confirm RLS is enabled:
SELECT relname, relrowsecurity
FROM pg_class
WHERE relname = 'sacs002_verification_cache';
-- Expected: relrowsecurity = true

-- B: Confirm new constraint allows 'completed':
SELECT conname, pg_get_constraintdef(oid) AS definition
FROM pg_constraint
WHERE conrelid = 'compliance_results'::regclass
  AND conname  = 'chk_compliance_results_status';
-- Expected: IN list includes 'completed', 'failed', 'pending'

-- B: Confirm no existing compliance_results rows violate the new constraint:
SELECT DISTINCT status FROM compliance_results ORDER BY status;
*/
