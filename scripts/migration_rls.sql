-- ============================================================
-- Hemaya Policy AI — RLS Security Migration
-- Generated: 2026-05-10
--
-- WHAT THIS FIXES:
--
--   GAP 1 — Missing operations on tables already covered by RLS:
--     The original rls_migration.sql left several DML operations
--     without policies, allowing any non-postgres role to bypass
--     scoping on those operations.
--
--       compliance_results  → missing UPDATE, DELETE
--       mapping_reviews     → missing DELETE
--       remediation_drafts  → missing DELETE
--       policy_versions     → missing UPDATE (intentionally denied),
--                             DELETE (intentionally denied — append-only)
--       ai_insights         → missing UPDATE, DELETE
--       reports             → missing UPDATE
--
--   GAP 2 — Tables with no RLS at all:
--       policy_ecc_assessments  → user assessment data, fully exposed
--       policy_chunks           → user policy embeddings, fully exposed
--       verification_cache      → backend-only, should block direct access
--       ecc2_verification_cache → backend-only, should block direct access
--       framework_load_log      → admin-only audit trail
--       system_settings         → public read, admin write
--       ecc_framework           → public read-only reference data
--       ecc_compliance_metadata → public read-only reference data
--       ecc_ai_checkpoints      → public read-only reference data
--       sacs002_metadata        → public read-only reference data
--
-- POLICY PATTERNS USED:
--   "own via policy"   → scope via JOIN to policies.owner_id
--                        (same pattern as existing rls_migration.sql)
--   "public read"      → USING (true) — framework reference tables
--   "backend-only"     → no SELECT/INSERT/UPDATE/DELETE policy created;
--                        only postgres superuser (which bypasses RLS)
--                        can access the table
--   "admin-only"       → app-layer check via require_admin(); DB policy
--                        blocks direct non-postgres access entirely
--   "deny"             → explicit USING (false) for operations that must
--                        never be allowed directly (e.g. policy_versions
--                        UPDATE/DELETE — immutable audit trail)
--
-- HOW TO RUN:
--   psql $DATABASE_URL -f migration_rls.sql
--
-- IDEMPOTENT: all policies use DROP IF EXISTS before CREATE.
-- ============================================================


-- ============================================================
-- PART 1: Fill missing operations on already-covered tables
-- ============================================================


-- ── 1a. compliance_results ───────────────────────────────────
-- UPDATE: allow owner to update their own results
-- DELETE: allow owner to delete (e.g. re-analysis wipe)

DROP POLICY IF EXISTS "compliance_results_update_own" ON compliance_results;
DROP POLICY IF EXISTS "compliance_results_delete_own" ON compliance_results;

CREATE POLICY "compliance_results_update_own" ON compliance_results
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = compliance_results.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "compliance_results_delete_own" ON compliance_results
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = compliance_results.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ── 1b. mapping_reviews ──────────────────────────────────────
-- DELETE was missing (SELECT, INSERT, UPDATE already existed)

DROP POLICY IF EXISTS "mapping_reviews_delete_own" ON mapping_reviews;

CREATE POLICY "mapping_reviews_delete_own" ON mapping_reviews
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = mapping_reviews.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ── 1c. remediation_drafts ───────────────────────────────────
-- DELETE was missing (SELECT, INSERT, UPDATE already existed)

DROP POLICY IF EXISTS "remediation_drafts_delete_own" ON remediation_drafts;

CREATE POLICY "remediation_drafts_delete_own" ON remediation_drafts
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = remediation_drafts.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ── 1d. policy_versions ──────────────────────────────────────
-- policy_versions is an IMMUTABLE append-only audit trail.
-- UPDATE and DELETE are architecturally forbidden for users.
-- USING (false) creates an explicit deny that documents intent.

DROP POLICY IF EXISTS "policy_versions_update_deny" ON policy_versions;
DROP POLICY IF EXISTS "policy_versions_delete_deny" ON policy_versions;

CREATE POLICY "policy_versions_update_deny" ON policy_versions
  FOR UPDATE
  USING (false);

CREATE POLICY "policy_versions_delete_deny" ON policy_versions
  FOR DELETE
  USING (false);


-- ── 1e. ai_insights ──────────────────────────────────────────
-- UPDATE: owner can update insight status (e.g. mark as Reviewed)
-- DELETE: owner can dismiss/remove insights for their policy

DROP POLICY IF EXISTS "ai_insights_update_own" ON ai_insights;
DROP POLICY IF EXISTS "ai_insights_delete_own" ON ai_insights;

CREATE POLICY "ai_insights_update_own" ON ai_insights
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = ai_insights.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "ai_insights_delete_own" ON ai_insights
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = ai_insights.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ── 1f. reports ──────────────────────────────────────────────
-- UPDATE was missing (SELECT, INSERT, DELETE already existed)
-- Needed for status updates (e.g. Generating → Completed)

DROP POLICY IF EXISTS "reports_update_own" ON reports;

CREATE POLICY "reports_update_own" ON reports
  FOR UPDATE
  USING (
    -- Reports with NULL policy_id (policy deleted) are backend-managed only
    policy_id IS NOT NULL
    AND EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = reports.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ============================================================
-- PART 2: Enable RLS + create policies for uncovered tables
-- ============================================================


-- ── 2a. policy_ecc_assessments ───────────────────────────────
-- Per-policy ECC assessment results. Scoped via policies.owner_id.
-- policy_id is now VARCHAR (after migration_integrity.sql Part C).

ALTER TABLE policy_ecc_assessments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "pea_select_own"  ON policy_ecc_assessments;
DROP POLICY IF EXISTS "pea_insert_own"  ON policy_ecc_assessments;
DROP POLICY IF EXISTS "pea_update_own"  ON policy_ecc_assessments;
DROP POLICY IF EXISTS "pea_delete_own"  ON policy_ecc_assessments;

CREATE POLICY "pea_select_own" ON policy_ecc_assessments
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = policy_ecc_assessments.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "pea_insert_own" ON policy_ecc_assessments
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = policy_ecc_assessments.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "pea_update_own" ON policy_ecc_assessments
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = policy_ecc_assessments.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "pea_delete_own" ON policy_ecc_assessments
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = policy_ecc_assessments.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ── 2b. policy_chunks ────────────────────────────────────────
-- pgvector embeddings for uploaded policy documents.
-- Scoped via policies.owner_id. No direct user mutation
-- (the backend manages chunks through the analysis pipeline).

ALTER TABLE policy_chunks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "policy_chunks_select_own" ON policy_chunks;
DROP POLICY IF EXISTS "policy_chunks_insert_own" ON policy_chunks;
DROP POLICY IF EXISTS "policy_chunks_delete_own" ON policy_chunks;

CREATE POLICY "policy_chunks_select_own" ON policy_chunks
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = policy_chunks.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

-- INSERT/DELETE via backend (postgres bypasses RLS).
-- Policies below block direct non-postgres inserts/deletes only.
CREATE POLICY "policy_chunks_insert_own" ON policy_chunks
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = policy_chunks.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "policy_chunks_delete_own" ON policy_chunks
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id    = policy_chunks.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ── 2c. verification_cache ───────────────────────────────────
-- Backend-only table: stores per-policy checkpoint analysis results.
-- Enable RLS with no user policies → only postgres (superuser) can
-- read or write. Direct access by any other role is blocked.

ALTER TABLE verification_cache ENABLE ROW LEVEL SECURITY;
-- No policies created intentionally — backend-only via postgres superuser.


-- ── 2d. ecc2_verification_cache ──────────────────────────────
-- Backend-only table: stores per-policy ECC-2 analysis cache.
-- Same treatment as verification_cache above.

ALTER TABLE ecc2_verification_cache ENABLE ROW LEVEL SECURITY;
-- No policies created intentionally — backend-only via postgres superuser.


-- ── 2e. framework_load_log ───────────────────────────────────
-- Admin-only audit trail for framework import operations.
-- Enable RLS with no user policies → blocked for non-postgres roles.
-- Admin reads are done via the postgres superuser (bypasses RLS).

ALTER TABLE framework_load_log ENABLE ROW LEVEL SECURITY;
-- No policies created intentionally — admin/backend via postgres superuser.


-- ── 2f. system_settings ──────────────────────────────────────
-- Platform configuration (lockout thresholds, feature flags).
-- Public read: clients need to read settings (e.g. lockout config).
-- Write is admin-only via postgres (bypasses RLS).

ALTER TABLE system_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "system_settings_public_read" ON system_settings;

CREATE POLICY "system_settings_public_read" ON system_settings
  FOR SELECT
  USING (true);


-- ── 2g. ecc_framework ────────────────────────────────────────
-- Layer 1 official ECC regulatory text. Immutable reference data.
-- Public read for all authenticated and unauthenticated roles.
-- Write is import-only via postgres superuser.

ALTER TABLE ecc_framework ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ecc_framework_public_read" ON ecc_framework;

CREATE POLICY "ecc_framework_public_read" ON ecc_framework
  FOR SELECT
  USING (true);


-- ── 2h. ecc_compliance_metadata ──────────────────────────────
-- Layer 2 human-validated compliance metadata. Public read.

ALTER TABLE ecc_compliance_metadata ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ecc_compliance_metadata_public_read" ON ecc_compliance_metadata;

CREATE POLICY "ecc_compliance_metadata_public_read" ON ecc_compliance_metadata
  FOR SELECT
  USING (true);


-- ── 2i. ecc_ai_checkpoints ───────────────────────────────────
-- Layer 3 AI-generated audit aids. Public read.
-- ai_generated CHECK constraint (= TRUE) already prevents
-- misuse; RLS adds the access control layer.

ALTER TABLE ecc_ai_checkpoints ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "ecc_ai_checkpoints_public_read" ON ecc_ai_checkpoints;

CREATE POLICY "ecc_ai_checkpoints_public_read" ON ecc_ai_checkpoints
  FOR SELECT
  USING (true);


-- ── 2j. sacs002_metadata ─────────────────────────────────────
-- SACS-002 framework operational metadata. Public read.

ALTER TABLE sacs002_metadata ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "sacs002_metadata_public_read" ON sacs002_metadata;

CREATE POLICY "sacs002_metadata_public_read" ON sacs002_metadata
  FOR SELECT
  USING (true);


-- ============================================================
-- VERIFICATION
-- ============================================================

/*
-- All tables should show rowsecurity = true:
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'policy_ecc_assessments', 'policy_chunks',
    'verification_cache', 'ecc2_verification_cache',
    'framework_load_log', 'system_settings',
    'ecc_framework', 'ecc_compliance_metadata',
    'ecc_ai_checkpoints', 'sacs002_metadata'
  )
ORDER BY tablename;

-- Full policy list — cross-reference against expected coverage:
SELECT tablename, policyname, cmd, qual
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, cmd, policyname;
*/
