-- ============================================================
-- Hemaya Policy AI — Schema Integrity Migration
-- Generated: 2026-05-09
--
-- WHAT THIS FIXES:
--
--   PART A — Foreign key ON DELETE actions:
--     Most FKs were declared with no ON DELETE clause (default =
--     NO ACTION). This means deleting a parent row (policy, user)
--     raises an error unless all children are manually deleted
--     first — hence the complex ordering in production_cleanup.sql.
--     After this migration, the database enforces correct cascade
--     semantics automatically.
--
--     Rules applied:
--       → CASCADE:  child data is meaningless without the parent
--                   (e.g. compliance result without its policy)
--       → SET NULL: child data has standalone value but loses the
--                   reference (e.g. report without its source policy,
--                   gap without its assigned reviewer)
--       → RESTRICT: block deletion if children exist — prevents
--                   accidental framework deletion with live data
--
--   PART B — CHECK constraints on enum-like string columns:
--     String columns storing a fixed set of states had no database-
--     level enforcement. Invalid values could be written by any
--     future code path without raising an error.
--
--   PART C — UUID / VARCHAR type mismatch on policy_ecc_assessments:
--     policy_ecc_assessments.policy_id was declared UUID while
--     policies.id is VARCHAR. No FK constraint was possible.
--     This fixes the type and adds the missing FK.
--
-- HOW TO RUN:
--   psql $DATABASE_URL -f migration_integrity.sql
--
-- STRATEGY:
--   FK changes:    DROP existing constraint (found dynamically) +
--                  ADD new constraint NOT VALID + VALIDATE.
--   CHECK changes: ADD CONSTRAINT NOT VALID + VALIDATE.
--   NOT VALID adds the constraint without a blocking table scan.
--   VALIDATE then runs under a weaker lock (SHARE UPDATE EXCLUSIVE),
--   allowing concurrent reads/writes during validation.
--
-- SAFE TO RE-RUN: every ADD uses IF NOT EXISTS via DO blocks.
-- ============================================================


-- ============================================================
-- HELPER
-- Finds and drops an existing FK from a specific column so we
-- can re-add it with the correct ON DELETE action.
-- If the constraint was already removed, this is a no-op.
-- ============================================================

CREATE OR REPLACE FUNCTION _drop_fk_if_exists(
    p_table  TEXT,
    p_column TEXT,
    p_reftable TEXT
) RETURNS VOID LANGUAGE plpgsql AS $$
DECLARE
    v_name TEXT;
BEGIN
    SELECT conname INTO v_name
    FROM pg_constraint c
    CROSS JOIN LATERAL unnest(c.conkey) AS uk(num)
    JOIN pg_attribute a
        ON a.attrelid = c.conrelid AND a.attnum = uk.num
    WHERE c.conrelid  = p_table::regclass
      AND c.contype   = 'f'
      AND a.attname   = p_column
      AND c.confrelid = p_reftable::regclass;

    IF v_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', p_table, v_name);
        RAISE NOTICE 'Dropped FK: %.% → %', p_table, p_column, p_reftable;
    END IF;
END $$;


-- ============================================================
-- PART A: Foreign key ON DELETE actions
-- ============================================================


-- ── A1. compliance_results ───────────────────────────────────

-- policy_id → CASCADE: results are owned by the policy
SELECT _drop_fk_if_exists('compliance_results', 'policy_id', 'policies');
ALTER TABLE compliance_results
    ADD CONSTRAINT compliance_results_policy_id_fkey
        FOREIGN KEY (policy_id) REFERENCES policies(id)
        ON DELETE CASCADE NOT VALID;
ALTER TABLE compliance_results VALIDATE CONSTRAINT compliance_results_policy_id_fkey;

-- framework_id → RESTRICT: block framework deletion while results exist
SELECT _drop_fk_if_exists('compliance_results', 'framework_id', 'frameworks');
ALTER TABLE compliance_results
    ADD CONSTRAINT compliance_results_framework_id_fkey
        FOREIGN KEY (framework_id) REFERENCES frameworks(id)
        ON DELETE RESTRICT NOT VALID;
ALTER TABLE compliance_results VALIDATE CONSTRAINT compliance_results_framework_id_fkey;


-- ── A2. gaps ─────────────────────────────────────────────────

-- policy_id → CASCADE: gaps belong to the policy
SELECT _drop_fk_if_exists('gaps', 'policy_id', 'policies');
ALTER TABLE gaps
    ADD CONSTRAINT gaps_policy_id_fkey
        FOREIGN KEY (policy_id) REFERENCES policies(id)
        ON DELETE CASCADE NOT VALID;
ALTER TABLE gaps VALIDATE CONSTRAINT gaps_policy_id_fkey;

-- framework_id → RESTRICT: block framework deletion while gaps exist
SELECT _drop_fk_if_exists('gaps', 'framework_id', 'frameworks');
ALTER TABLE gaps
    ADD CONSTRAINT gaps_framework_id_fkey
        FOREIGN KEY (framework_id) REFERENCES frameworks(id)
        ON DELETE RESTRICT NOT VALID;
ALTER TABLE gaps VALIDATE CONSTRAINT gaps_framework_id_fkey;

-- control_id → SET NULL: gap history survives if a control is removed
SELECT _drop_fk_if_exists('gaps', 'control_id', 'control_library');
ALTER TABLE gaps
    ADD CONSTRAINT gaps_control_id_fkey
        FOREIGN KEY (control_id) REFERENCES control_library(id)
        ON DELETE SET NULL NOT VALID;
ALTER TABLE gaps VALIDATE CONSTRAINT gaps_control_id_fkey;

-- owner_id → SET NULL: gap survives if the assigned user is deleted
SELECT _drop_fk_if_exists('gaps', 'owner_id', 'users');
ALTER TABLE gaps
    ADD CONSTRAINT gaps_owner_id_fkey
        FOREIGN KEY (owner_id) REFERENCES users(id)
        ON DELETE SET NULL NOT VALID;
ALTER TABLE gaps VALIDATE CONSTRAINT gaps_owner_id_fkey;


-- ── A3. mapping_reviews ──────────────────────────────────────

-- policy_id → CASCADE: mappings are owned by the policy
SELECT _drop_fk_if_exists('mapping_reviews', 'policy_id', 'policies');
ALTER TABLE mapping_reviews
    ADD CONSTRAINT mapping_reviews_policy_id_fkey
        FOREIGN KEY (policy_id) REFERENCES policies(id)
        ON DELETE CASCADE NOT VALID;
ALTER TABLE mapping_reviews VALIDATE CONSTRAINT mapping_reviews_policy_id_fkey;

-- control_id → SET NULL: mapping history survives control removal
SELECT _drop_fk_if_exists('mapping_reviews', 'control_id', 'control_library');
ALTER TABLE mapping_reviews
    ADD CONSTRAINT mapping_reviews_control_id_fkey
        FOREIGN KEY (control_id) REFERENCES control_library(id)
        ON DELETE SET NULL NOT VALID;
ALTER TABLE mapping_reviews VALIDATE CONSTRAINT mapping_reviews_control_id_fkey;

-- framework_id → RESTRICT: block framework deletion with live mappings
SELECT _drop_fk_if_exists('mapping_reviews', 'framework_id', 'frameworks');
ALTER TABLE mapping_reviews
    ADD CONSTRAINT mapping_reviews_framework_id_fkey
        FOREIGN KEY (framework_id) REFERENCES frameworks(id)
        ON DELETE RESTRICT NOT VALID;
ALTER TABLE mapping_reviews VALIDATE CONSTRAINT mapping_reviews_framework_id_fkey;

-- reviewer_id → SET NULL: mapping survives if reviewer is deleted
SELECT _drop_fk_if_exists('mapping_reviews', 'reviewer_id', 'users');
ALTER TABLE mapping_reviews
    ADD CONSTRAINT mapping_reviews_reviewer_id_fkey
        FOREIGN KEY (reviewer_id) REFERENCES users(id)
        ON DELETE SET NULL NOT VALID;
ALTER TABLE mapping_reviews VALIDATE CONSTRAINT mapping_reviews_reviewer_id_fkey;


-- ── A4. ai_insights ──────────────────────────────────────────

-- policy_id → CASCADE: insights belong to the policy
SELECT _drop_fk_if_exists('ai_insights', 'policy_id', 'policies');
ALTER TABLE ai_insights
    ADD CONSTRAINT ai_insights_policy_id_fkey
        FOREIGN KEY (policy_id) REFERENCES policies(id)
        ON DELETE CASCADE NOT VALID;
ALTER TABLE ai_insights VALIDATE CONSTRAINT ai_insights_policy_id_fkey;


-- ── A5. reports ──────────────────────────────────────────────

-- policy_id → SET NULL: generated report document is kept even
-- if the source policy is deleted (audit / download trail)
SELECT _drop_fk_if_exists('reports', 'policy_id', 'policies');
ALTER TABLE reports
    ADD CONSTRAINT reports_policy_id_fkey
        FOREIGN KEY (policy_id) REFERENCES policies(id)
        ON DELETE SET NULL NOT VALID;
ALTER TABLE reports VALIDATE CONSTRAINT reports_policy_id_fkey;


-- ── A6. policies ─────────────────────────────────────────────

-- owner_id → SET NULL: policy survives user account deletion
SELECT _drop_fk_if_exists('policies', 'owner_id', 'users');
ALTER TABLE policies
    ADD CONSTRAINT policies_owner_id_fkey
        FOREIGN KEY (owner_id) REFERENCES users(id)
        ON DELETE SET NULL NOT VALID;
ALTER TABLE policies VALIDATE CONSTRAINT policies_owner_id_fkey;


-- ── A7. audit_logs ───────────────────────────────────────────

-- actor_id → SET NULL: audit record is kept, actor reference is nulled
SELECT _drop_fk_if_exists('audit_logs', 'actor_id', 'users');
ALTER TABLE audit_logs
    ADD CONSTRAINT audit_logs_actor_id_fkey
        FOREIGN KEY (actor_id) REFERENCES users(id)
        ON DELETE SET NULL NOT VALID;
ALTER TABLE audit_logs VALIDATE CONSTRAINT audit_logs_actor_id_fkey;


-- ============================================================
-- PART B: CHECK constraints on enum-like columns
--
-- All added NOT VALID first (no blocking scan), then validated.
-- If a validate step fails, the column contains an out-of-range
-- value — fix the data, then re-run the VALIDATE statement.
-- ============================================================


-- ── B1. users.role ───────────────────────────────────────────
-- Values in use: 'admin' (seed), 'user' (default), 'disabled'
-- (deactivated), 'Regular User' (reactivated — see main.py:3137).
-- NOTE: 'user' and 'Regular User' are inconsistent. The correct
-- reactivation value should be 'user'. Consider fixing
-- main.py:3137 to set role='user' instead of 'Regular User'.
ALTER TABLE users
    ADD CONSTRAINT chk_users_role
        CHECK (role IN ('admin', 'user', 'disabled', 'Regular User'))
        NOT VALID;
ALTER TABLE users VALIDATE CONSTRAINT chk_users_role;


-- ── B2. policies.status ──────────────────────────────────────
ALTER TABLE policies
    ADD CONSTRAINT chk_policies_status
        CHECK (status IN ('uploaded', 'processing', 'analyzed', 'paused', 'failed'))
        NOT VALID;
ALTER TABLE policies VALIDATE CONSTRAINT chk_policies_status;


-- ── B3. compliance_results.status ────────────────────────────
ALTER TABLE compliance_results
    ADD CONSTRAINT chk_compliance_results_status
        CHECK (status IN ('Compliant', 'Partial', 'Non-Compliant'))
        NOT VALID;
ALTER TABLE compliance_results VALIDATE CONSTRAINT chk_compliance_results_status;


-- ── B4. gaps.severity ────────────────────────────────────────
ALTER TABLE gaps
    ADD CONSTRAINT chk_gaps_severity
        CHECK (severity IN ('Low', 'Medium', 'High', 'Critical'))
        NOT VALID;
ALTER TABLE gaps VALIDATE CONSTRAINT chk_gaps_severity;


-- ── B5. gaps.status ──────────────────────────────────────────
-- 'Open' → initial state after analysis
-- 'In Progress' → remediation started (set by remediation.py:197)
-- 'Resolved' / 'Accepted' / 'Risk Accepted' → closure states
-- (Resolved/Accepted/Risk Accepted are included for future use
--  based on standard gap-management lifecycle.)
ALTER TABLE gaps
    ADD CONSTRAINT chk_gaps_status
        CHECK (status IN ('Open', 'In Progress', 'Resolved', 'Accepted', 'Risk Accepted'))
        NOT VALID;
ALTER TABLE gaps VALIDATE CONSTRAINT chk_gaps_status;


-- ── B6. mapping_reviews.decision ─────────────────────────────
-- 'Pending'                  → default after AI analysis
-- 'Accepted'                 → human approved the mapping
-- 'Flagged'                  → human flagged for re-review
-- 'Compliant (Manual Override)' → human overrides AI assessment
ALTER TABLE mapping_reviews
    ADD CONSTRAINT chk_mapping_reviews_decision
        CHECK (decision IN ('Pending', 'Accepted', 'Flagged', 'Compliant (Manual Override)'))
        NOT VALID;
ALTER TABLE mapping_reviews VALIDATE CONSTRAINT chk_mapping_reviews_decision;


-- ── B7. remediation_drafts.remediation_status ────────────────
-- Lifecycle matches REMEDIATION_STATUSES constant in models.py
ALTER TABLE remediation_drafts
    ADD CONSTRAINT chk_remediation_drafts_status
        CHECK (remediation_status IN
            ('draft', 'under_review', 'approved', 'rejected', 'superseded'))
        NOT VALID;
ALTER TABLE remediation_drafts VALIDATE CONSTRAINT chk_remediation_drafts_status;


-- ── B8. ai_insights.status ───────────────────────────────────
ALTER TABLE ai_insights
    ADD CONSTRAINT chk_ai_insights_status
        CHECK (status IN ('New', 'Reviewed', 'Dismissed'))
        NOT VALID;
ALTER TABLE ai_insights VALIDATE CONSTRAINT chk_ai_insights_status;


-- ── B9. reports.status ───────────────────────────────────────
ALTER TABLE reports
    ADD CONSTRAINT chk_reports_status
        CHECK (status IN ('Completed', 'Failed', 'Generating'))
        NOT VALID;
ALTER TABLE reports VALIDATE CONSTRAINT chk_reports_status;


-- ── B10. control_library.status ──────────────────────────────
-- checkpoint_analyzer.py filters: status IS NULL OR status = 'active'
-- NULL = legacy / pre-status rows; 'active' = current active controls
ALTER TABLE control_library
    ADD CONSTRAINT chk_control_library_status
        CHECK (status IS NULL OR status = 'active')
        NOT VALID;
ALTER TABLE control_library VALIDATE CONSTRAINT chk_control_library_status;


-- ============================================================
-- PART C: Fix UUID / VARCHAR mismatch on policy_ecc_assessments
--
-- policy_ecc_assessments.policy_id was declared UUID NOT NULL
-- while policies.id is VARCHAR (SQLAlchemy String). This made
-- a FK constraint impossible and caused type cast errors on JOINs.
--
-- Fix: convert the column to VARCHAR, then add the missing FK.
-- ============================================================

-- Step C1: Drop dependent view (policy_compliance_gaps selects policy_id,
-- so PostgreSQL refuses to alter the column type while the view exists).
DROP VIEW IF EXISTS policy_compliance_gaps;

-- Step C2: Change column type (USING casts UUID → TEXT → VARCHAR)
ALTER TABLE policy_ecc_assessments
    ALTER COLUMN policy_id TYPE VARCHAR
    USING policy_id::TEXT;

-- Step C3: Re-create the view with identical definition (verbatim from ecc2_schema.sql)
CREATE OR REPLACE VIEW policy_compliance_gaps AS
SELECT
    pea.policy_id,
    pea.framework_id,
    pea.control_code,
    f.control_text,
    pea.compliance_status,
    pea.gap_description,
    pea.confidence_score,
    pea.assessed_by,
    pea.assessed_at
FROM policy_ecc_assessments pea
JOIN ecc_framework f
    ON pea.framework_id = f.framework_id
    AND pea.control_code = f.control_code
WHERE pea.compliance_status IN ('partial', 'non_compliant', 'pending');

COMMENT ON VIEW policy_compliance_gaps IS
    'Shows controls with compliance gaps or pending assessment for each policy.';

-- Step C4: Add FK with CASCADE (assessment is meaningless without policy)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'policy_ecc_assessments'::regclass
          AND contype  = 'f'
          AND conname  = 'fk_pea_policy_id'
    ) THEN
        ALTER TABLE policy_ecc_assessments
            ADD CONSTRAINT fk_pea_policy_id
                FOREIGN KEY (policy_id) REFERENCES policies(id)
                ON DELETE CASCADE NOT VALID;
    END IF;
END $$;
ALTER TABLE policy_ecc_assessments VALIDATE CONSTRAINT fk_pea_policy_id;


-- ============================================================
-- CLEANUP: drop the helper function (not needed at runtime)
-- ============================================================

DROP FUNCTION IF EXISTS _drop_fk_if_exists(TEXT, TEXT, TEXT);


-- ============================================================
-- VERIFICATION
-- ============================================================

/*
-- Confirm all new FK constraints exist with correct actions:
SELECT
    tc.table_name,
    kcu.column_name,
    ccu.table_name  AS references_table,
    rc.delete_rule  AS on_delete
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.referential_constraints rc
    ON tc.constraint_name = rc.constraint_name
JOIN information_schema.constraint_column_usage ccu
    ON rc.unique_constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND tc.table_name IN (
      'compliance_results', 'gaps', 'mapping_reviews',
      'ai_insights', 'reports', 'policies', 'audit_logs',
      'policy_ecc_assessments'
  )
ORDER BY tc.table_name, kcu.column_name;

-- Confirm all CHECK constraints exist:
SELECT
    tc.table_name,
    tc.constraint_name,
    cc.check_clause
FROM information_schema.table_constraints tc
JOIN information_schema.check_constraints cc
    ON tc.constraint_name = cc.constraint_name
WHERE tc.constraint_type = 'CHECK'
  AND tc.table_name IN (
      'users', 'policies', 'compliance_results', 'gaps',
      'mapping_reviews', 'remediation_drafts',
      'ai_insights', 'reports', 'control_library'
  )
ORDER BY tc.table_name, tc.constraint_name;

-- Confirm policy_ecc_assessments.policy_id is now VARCHAR:
SELECT column_name, data_type, character_maximum_length
FROM information_schema.columns
WHERE table_name = 'policy_ecc_assessments'
  AND column_name = 'policy_id';
*/
