-- ============================================================
-- Hemaya – Row Level Security Migration
-- Run this in: Supabase Dashboard → SQL Editor
-- ============================================================
-- Architecture note:
--   The FastAPI backend connects as the postgres superuser,
--   which bypasses RLS by default. This migration:
--   1. Enables RLS on every table (Phase 1 – safe, no code changes)
--   2. Adds user-scoped policies using app.current_user_id
--      which the backend will SET at the start of each request
--      (Phase 2 – requires the database.py change in this PR)
-- ============================================================


-- ============================================================
-- PHASE 1 – Enable RLS on all tables
-- This alone does NOT break the backend (postgres bypasses RLS)
-- but protects against Supabase Dashboard / REST API direct access
-- ============================================================

ALTER TABLE users                  ENABLE ROW LEVEL SECURITY;
ALTER TABLE policies               ENABLE ROW LEVEL SECURITY;
ALTER TABLE otp_tokens             ENABLE ROW LEVEL SECURITY;
ALTER TABLE password_reset_tokens  ENABLE ROW LEVEL SECURITY;
ALTER TABLE compliance_results     ENABLE ROW LEVEL SECURITY;
ALTER TABLE gaps                   ENABLE ROW LEVEL SECURITY;
ALTER TABLE mapping_reviews        ENABLE ROW LEVEL SECURITY;
ALTER TABLE control_library        ENABLE ROW LEVEL SECURITY;
ALTER TABLE frameworks             ENABLE ROW LEVEL SECURITY;
ALTER TABLE remediation_drafts     ENABLE ROW LEVEL SECURITY;
ALTER TABLE policy_versions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs             ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports                ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_insights            ENABLE ROW LEVEL SECURITY;


-- ============================================================
-- PHASE 2 – Per-user RLS Policies
--
-- These use current_setting('app.current_user_id', true)
-- which the backend sets at the start of every authenticated
-- request via: SET LOCAL app.current_user_id = '<uuid>'
--
-- The second argument (true) makes it return NULL instead of
-- raising an error when the variable is not set.
-- ============================================================


-- ────────────────────────────────────────────────────────────
-- Helper: reusable expression
-- current_user_id() → the UUID set by the backend per request
-- ────────────────────────────────────────────────────────────
-- We use inline current_setting() calls since Postgres does not
-- support CREATE FUNCTION inside RLS policies directly.


-- ────────────────────────────────────────────────────────────
-- TABLE: users
-- ────────────────────────────────────────────────────────────
-- Users can only read their own row.
-- Admin reads all (enforced in app layer; DB allows SELECT for own row).
-- Backend (postgres) bypasses automatically.

DROP POLICY IF EXISTS "users_select_own"  ON users;
DROP POLICY IF EXISTS "users_update_own"  ON users;

CREATE POLICY "users_select_own" ON users
  FOR SELECT
  USING (
    id = current_setting('app.current_user_id', true)::uuid
  );

CREATE POLICY "users_update_own" ON users
  FOR UPDATE
  USING (
    id = current_setting('app.current_user_id', true)::uuid
  )
  WITH CHECK (
    id = current_setting('app.current_user_id', true)::uuid
  );

-- INSERT / DELETE are backend-only operations; no policy needed
-- (postgres superuser handles them, bypassing RLS)


-- ────────────────────────────────────────────────────────────
-- TABLE: policies
-- ────────────────────────────────────────────────────────────
-- Users see and modify only their own policies.

DROP POLICY IF EXISTS "policies_select_own"  ON policies;
DROP POLICY IF EXISTS "policies_insert_own"  ON policies;
DROP POLICY IF EXISTS "policies_update_own"  ON policies;
DROP POLICY IF EXISTS "policies_delete_own"  ON policies;

CREATE POLICY "policies_select_own" ON policies
  FOR SELECT
  USING (
    owner_id = current_setting('app.current_user_id', true)::uuid
  );

CREATE POLICY "policies_insert_own" ON policies
  FOR INSERT
  WITH CHECK (
    owner_id = current_setting('app.current_user_id', true)::uuid
  );

CREATE POLICY "policies_update_own" ON policies
  FOR UPDATE
  USING (
    owner_id = current_setting('app.current_user_id', true)::uuid
  );

CREATE POLICY "policies_delete_own" ON policies
  FOR DELETE
  USING (
    owner_id = current_setting('app.current_user_id', true)::uuid
  );


-- ────────────────────────────────────────────────────────────
-- TABLE: otp_tokens
-- ────────────────────────────────────────────────────────────
-- Backend-only table (no direct user access via API).
-- Policies block all direct access from non-backend roles.

DROP POLICY IF EXISTS "otp_tokens_own" ON otp_tokens;

CREATE POLICY "otp_tokens_own" ON otp_tokens
  FOR ALL
  USING (
    user_id = current_setting('app.current_user_id', true)::uuid
  )
  WITH CHECK (
    user_id = current_setting('app.current_user_id', true)::uuid
  );


-- ────────────────────────────────────────────────────────────
-- TABLE: password_reset_tokens
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "password_reset_tokens_own" ON password_reset_tokens;

CREATE POLICY "password_reset_tokens_own" ON password_reset_tokens
  FOR ALL
  USING (
    user_id = current_setting('app.current_user_id', true)::uuid
  )
  WITH CHECK (
    user_id = current_setting('app.current_user_id', true)::uuid
  );


-- ────────────────────────────────────────────────────────────
-- TABLE: compliance_results
-- Scoped via the parent policy's owner_id (JOIN needed)
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "compliance_results_select_own" ON compliance_results;

CREATE POLICY "compliance_results_select_own" ON compliance_results
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = compliance_results.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "compliance_results_insert_own" ON compliance_results
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = compliance_results.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ────────────────────────────────────────────────────────────
-- TABLE: gaps
-- Scoped via parent policy's owner_id
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "gaps_select_own"  ON gaps;
DROP POLICY IF EXISTS "gaps_insert_own"  ON gaps;
DROP POLICY IF EXISTS "gaps_update_own"  ON gaps;
DROP POLICY IF EXISTS "gaps_delete_own"  ON gaps;

CREATE POLICY "gaps_select_own" ON gaps
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = gaps.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "gaps_insert_own" ON gaps
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = gaps.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "gaps_update_own" ON gaps
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = gaps.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "gaps_delete_own" ON gaps
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = gaps.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ────────────────────────────────────────────────────────────
-- TABLE: mapping_reviews
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "mapping_reviews_select_own"  ON mapping_reviews;
DROP POLICY IF EXISTS "mapping_reviews_insert_own"  ON mapping_reviews;
DROP POLICY IF EXISTS "mapping_reviews_update_own"  ON mapping_reviews;

CREATE POLICY "mapping_reviews_select_own" ON mapping_reviews
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = mapping_reviews.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "mapping_reviews_insert_own" ON mapping_reviews
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = mapping_reviews.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "mapping_reviews_update_own" ON mapping_reviews
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = mapping_reviews.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ────────────────────────────────────────────────────────────
-- TABLE: control_library
-- Public read (framework controls are shared across all users)
-- Write is backend-only (admin uploads frameworks)
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "control_library_public_read" ON control_library;

CREATE POLICY "control_library_public_read" ON control_library
  FOR SELECT
  USING (true);

-- INSERT/UPDATE/DELETE: handled by postgres (admin operations only)


-- ────────────────────────────────────────────────────────────
-- TABLE: frameworks
-- Public read; write is admin-only (backend handles this)
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "frameworks_public_read" ON frameworks;

CREATE POLICY "frameworks_public_read" ON frameworks
  FOR SELECT
  USING (true);


-- ────────────────────────────────────────────────────────────
-- TABLE: remediation_drafts
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "remediation_drafts_select_own"  ON remediation_drafts;
DROP POLICY IF EXISTS "remediation_drafts_insert_own"  ON remediation_drafts;
DROP POLICY IF EXISTS "remediation_drafts_update_own"  ON remediation_drafts;

CREATE POLICY "remediation_drafts_select_own" ON remediation_drafts
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = remediation_drafts.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "remediation_drafts_insert_own" ON remediation_drafts
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = remediation_drafts.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "remediation_drafts_update_own" ON remediation_drafts
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = remediation_drafts.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ────────────────────────────────────────────────────────────
-- TABLE: policy_versions
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "policy_versions_select_own"  ON policy_versions;
DROP POLICY IF EXISTS "policy_versions_insert_own"  ON policy_versions;

CREATE POLICY "policy_versions_select_own" ON policy_versions
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = policy_versions.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "policy_versions_insert_own" ON policy_versions
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = policy_versions.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ────────────────────────────────────────────────────────────
-- TABLE: audit_logs
-- Users see only logs where they are the actor.
-- Admin sees all (handled in app layer; DB allows actor's own logs).
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "audit_logs_select_own"  ON audit_logs;
DROP POLICY IF EXISTS "audit_logs_insert_own"  ON audit_logs;

CREATE POLICY "audit_logs_select_own" ON audit_logs
  FOR SELECT
  USING (
    actor_id = current_setting('app.current_user_id', true)::uuid
  );

CREATE POLICY "audit_logs_insert_own" ON audit_logs
  FOR INSERT
  WITH CHECK (
    actor_id = current_setting('app.current_user_id', true)::uuid
  );


-- ────────────────────────────────────────────────────────────
-- TABLE: reports
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "reports_select_own"  ON reports;
DROP POLICY IF EXISTS "reports_insert_own"  ON reports;
DROP POLICY IF EXISTS "reports_delete_own"  ON reports;

CREATE POLICY "reports_select_own" ON reports
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = reports.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "reports_insert_own" ON reports
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = reports.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "reports_delete_own" ON reports
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = reports.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ────────────────────────────────────────────────────────────
-- TABLE: ai_insights
-- ────────────────────────────────────────────────────────────

DROP POLICY IF EXISTS "ai_insights_select_own"  ON ai_insights;
DROP POLICY IF EXISTS "ai_insights_insert_own"  ON ai_insights;

CREATE POLICY "ai_insights_select_own" ON ai_insights
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = ai_insights.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );

CREATE POLICY "ai_insights_insert_own" ON ai_insights
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM policies
      WHERE policies.id = ai_insights.policy_id
        AND policies.owner_id = current_setting('app.current_user_id', true)::uuid
    )
  );


-- ============================================================
-- VERIFICATION QUERIES
-- Run these after applying to confirm RLS is active
-- ============================================================

-- Should return 't' (true) for every table listed:
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'users', 'policies', 'otp_tokens', 'password_reset_tokens',
    'compliance_results', 'gaps', 'mapping_reviews', 'control_library',
    'frameworks', 'remediation_drafts', 'policy_versions',
    'audit_logs', 'reports', 'ai_insights'
  )
ORDER BY tablename;

-- Should list all policies created above:
SELECT tablename, policyname, cmd, qual
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, policyname;
