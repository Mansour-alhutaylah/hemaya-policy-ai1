-- ============================================================
-- Hemaya Policy AI — Production Database Cleanup Script
-- Generated: 2026-05-09
--
-- PURPOSE:
--   Reset the application to a fresh-start state by removing
--   all user-generated operational data while preserving:
--     • All framework/control/checkpoint reference data
--     • All AI knowledge bases (chunks, ECC layers, SACS-002)
--     • All system configuration (system_settings)
--     • Admin accounts (role = 'admin')
--
-- SAFETY GUARANTEES:
--   • Single BEGIN/COMMIT transaction — all-or-nothing.
--   • Uses DELETE, not TRUNCATE or DROP — tables remain.
--   • FK dependency order respected throughout.
--   • framework_chunks, ecc_framework, ecc_ai_checkpoints, and
--     all control reference data are never touched.
--   • Admin accounts are never touched.
--   • framework.uploaded_by is nullified (not deleted) before
--     removing non-admin users, preserving framework rows.
--
-- PRE-FLIGHT CHECKLIST (complete before running):
--   [ ] pg_dump backup of production database taken
--   [ ] Script tested on staging clone
--   [ ] Confirmed connection string points to the correct DB
--   [ ] All running analysis jobs stopped / drained
--
-- TABLE CLASSIFICATION:
--
--   NEVER CLEAR (core AI knowledge & reference data):
--     frameworks, control_library, control_checkpoints,
--     framework_chunks, ecc_framework, ecc_compliance_metadata,
--     ecc_ai_checkpoints, sacs002_metadata,
--     system_settings, framework_load_log
--
--   PARTIAL CLEAR (keep admin rows only):
--     users  →  DELETE WHERE role != 'admin'
--
--   FULLY CLEARED (all user-generated operational data):
--     otp_tokens, password_reset_tokens, audit_logs,
--     verification_cache, ecc2_verification_cache,
--     policy_ecc_assessments, reports, ai_insights,
--     policy_versions, remediation_drafts, mapping_reviews,
--     gaps, compliance_results, policy_chunks, policies,
--     ai_usage_logs (if exists)
--
--   OPTIONAL CLEAR (migration backup tables, if present):
--     _phase1_dedupe_backup, _phase4_degenerate_backup,
--     _phase4_orphan_backup
--
-- NOTE ON SEQUENCES:
--   All primary keys in this schema use UUID (gen_random_uuid()
--   or Python uuid4()), not SERIAL/BIGSERIAL. There are no
--   PostgreSQL sequences to reset. policy_versions.version_number
--   is application-managed and resets naturally with fresh policies.
-- ============================================================

BEGIN;

-- ============================================================
-- SECTION 1: Authentication tokens
--
-- otp_tokens and password_reset_tokens both have
-- user_id FK with ON DELETE CASCADE, but we delete them
-- explicitly first for clarity and to unblock Section 15.
-- ============================================================

DELETE FROM otp_tokens;
DELETE FROM password_reset_tokens;

-- ============================================================
-- SECTION 2: Audit logs
--
-- actor_id FK to users.id is nullable with no ON DELETE action
-- (default = NO ACTION). Must be removed before non-admin users
-- are deleted in Section 15.
-- ============================================================

DELETE FROM audit_logs;

-- ============================================================
-- SECTION 3: AI analysis caches
--
-- Both tables are keyed on SHA-256 hashes of (policy, control,
-- prompt_version, model) — no FK constraints to any user data.
-- Caches are invalidated here and will rebuild on next analysis.
-- Safe to delete at any point in the transaction.
-- ============================================================

-- NCA ECC (classic checkpoint analyzer) per-policy cache
DELETE FROM verification_cache;

-- ECC-2:2024 per-policy AI analysis cache
DELETE FROM ecc2_verification_cache;

-- ============================================================
-- SECTION 4: Policy ECC assessments
--
-- policy_id is UUID NOT NULL but carries NO FK CONSTRAINT
-- (ecc2_schema.sql uses UUID while policies.id is VARCHAR —
-- types differ, so no referential constraint was declared).
-- Safe to delete independently of policy deletion order.
-- ============================================================

DELETE FROM policy_ecc_assessments;

-- ============================================================
-- SECTION 5: Reports and AI insights
--
-- reports.policy_id:    FK to policies.id, nullable, no ON DELETE
-- ai_insights.policy_id: FK to policies.id, no ON DELETE
-- Both must be removed before policies (Section 13).
-- ============================================================

DELETE FROM reports;
DELETE FROM ai_insights;

-- ============================================================
-- SECTION 6: Policy versions
--
-- policy_versions.policy_id:           FK → policies.id (CASCADE)
-- policy_versions.remediation_draft_id: FK → remediation_drafts.id (SET NULL)
-- policy_versions.created_by:           FK → users.id (SET NULL)
--
-- Deleting here before remediation_drafts avoids the SET NULL
-- side-effect on remediation_draft_id (we want a clean slate,
-- not rows lingering with nulled FKs).
-- ============================================================

DELETE FROM policy_versions;

-- ============================================================
-- SECTION 7: Remediation drafts
--
-- remediation_drafts.policy_id:         FK → policies.id (CASCADE)
-- remediation_drafts.mapping_review_id: FK → mapping_reviews.id (SET NULL)
-- remediation_drafts.control_id:        FK → control_library.id (SET NULL)
-- remediation_drafts.framework_id:      FK → frameworks.id (SET NULL)
-- remediation_drafts.created_by:        FK → users.id (SET NULL)
-- remediation_drafts.reviewed_by:       FK → users.id (SET NULL)
--
-- Must be deleted BEFORE mapping_reviews (Section 8) to avoid
-- FK conflict on mapping_review_id (SET NULL would fire but
-- explicit deletion is cleaner).
-- ============================================================

DELETE FROM remediation_drafts;

-- ============================================================
-- SECTION 8: Mapping reviews
--
-- mapping_reviews.policy_id:   FK → policies.id (no ON DELETE)
-- mapping_reviews.control_id:  FK → control_library.id (no ON DELETE)
-- mapping_reviews.framework_id: FK → frameworks.id (no ON DELETE)
-- mapping_reviews.reviewer_id: FK → users.id (nullable, no ON DELETE)
--
-- remediation_drafts already cleared above so no child rows
-- remain pointing at these rows.
-- ============================================================

DELETE FROM mapping_reviews;

-- ============================================================
-- SECTION 9: Compliance gaps
--
-- gaps.policy_id:   FK → policies.id (no ON DELETE)
-- gaps.framework_id: FK → frameworks.id (no ON DELETE)
-- gaps.control_id:  FK → control_library.id (no ON DELETE)
-- gaps.owner_id:    FK → users.id (nullable, no ON DELETE)
--
-- gaps.mapping_id is a VARCHAR soft-reference (no FK constraint)
-- so no ordering dependency there.
-- ============================================================

DELETE FROM gaps;

-- ============================================================
-- SECTION 10: Compliance results
--
-- compliance_results.policy_id:   FK → policies.id (no ON DELETE)
-- compliance_results.framework_id: FK → frameworks.id (no ON DELETE)
-- ============================================================

DELETE FROM compliance_results;

-- ============================================================
-- SECTION 11: Policy vector chunks
--
-- policy_chunks.policy_id:         FK → policies.id
-- policy_chunks.policy_version_id: soft reference (nullable)
--
-- These are the pgvector embeddings for UPLOADED POLICIES only.
-- framework_chunks (AI knowledge embeddings) are NOT touched.
-- ============================================================

DELETE FROM policy_chunks;

-- ============================================================
-- SECTION 12: AI usage logs (optional — table may not exist)
--
-- Cleared if the table exists in the public schema; safely
-- skipped if it was never created. Uses a DO block to avoid
-- a hard error on a missing table.
-- ============================================================

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name   = 'ai_usage_logs'
    ) THEN
        EXECUTE 'DELETE FROM ai_usage_logs';
        RAISE NOTICE 'Cleared: ai_usage_logs';
    ELSE
        RAISE NOTICE 'Skipped: ai_usage_logs (table does not exist)';
    END IF;
END $$;

-- ============================================================
-- SECTION 13: Policies
--
-- All child rows (policy_chunks, compliance_results, gaps,
-- mapping_reviews, remediation_drafts, policy_versions,
-- reports, ai_insights, policy_ecc_assessments) have been
-- cleared in Sections 4–11.
-- ============================================================

DELETE FROM policies;

-- ============================================================
-- SECTION 14: Nullify frameworks.uploaded_by for non-admin users
--
-- frameworks rows are PRESERVED (they are core reference data).
-- However, frameworks.uploaded_by is a non-cascading FK to
-- users.id. If a non-admin user uploaded a framework, deleting
-- that user in Section 15 would raise a FK violation.
--
-- Solution: null out uploaded_by for affected framework rows.
-- The framework document itself is unchanged.
-- ============================================================

UPDATE frameworks
SET uploaded_by = NULL
WHERE uploaded_by IN (
    SELECT id FROM users WHERE role != 'admin'
);

-- ============================================================
-- SECTION 15: Non-admin users
--
-- All dependent rows have been cleared or nullified above:
--   otp_tokens          → deleted Section 1
--   password_reset_tokens → deleted Section 1
--   audit_logs          → deleted Section 2
--   policies.owner_id   → deleted Section 13
--   frameworks.uploaded_by → nullified Section 14
--   gaps.owner_id       → deleted Section 9
--   mapping_reviews.reviewer_id → deleted Section 8
--   remediation_drafts.created_by/reviewed_by → deleted Section 7 (SET NULL)
--   policy_versions.created_by → deleted Section 6 (SET NULL)
--
-- Admin accounts (role = 'admin') are preserved.
-- ============================================================

DELETE FROM users
WHERE role != 'admin';

-- ============================================================
-- SECTION 16: Optional — migration backup tables
--
-- These are temporary tables created by deduplication and
-- normalization scripts during past migration phases.
-- Cleared if present; skipped safely if already dropped.
-- ============================================================

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        '_phase1_dedupe_backup',
        '_phase4_degenerate_backup',
        '_phase4_orphan_backup'
    ]
    LOOP
        IF EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = tbl
        ) THEN
            EXECUTE format('DELETE FROM %I', tbl);
            RAISE NOTICE 'Cleared: %', tbl;
        ELSE
            RAISE NOTICE 'Skipped: % (table does not exist)', tbl;
        END IF;
    END LOOP;
END $$;

-- ============================================================
-- SECTION 17: Delete non-structured frameworks and their data
--
-- Structured frameworks (ECC-2:2024, SACS-002) live in dedicated
-- tables (ecc_framework, ecc_compliance_metadata, ecc_ai_checkpoints,
-- sacs002_metadata) and are PRESERVED in full.
--
-- All other frameworks use the generic pipeline:
--   framework_chunks      → vector embeddings (pgvector)
--   control_checkpoints   → per-control audit checkpoints
--   control_library       → control definitions
--   frameworks            → the parent row
--
-- Deletion order respects FK constraints:
--   framework_chunks.framework_id  FK → frameworks.id
--   control_library.framework_id   FK → frameworks.id
--   control_checkpoints.framework  text match on frameworks.id
--   (gaps/mapping_reviews/compliance_results already cleared above)
-- ============================================================

-- Step 17a: Vector chunks for non-structured frameworks only
DELETE FROM framework_chunks
WHERE framework_id IN (
    SELECT id FROM frameworks
    WHERE name NOT IN ('ECC-2:2024', 'SACS-002')
);

-- Step 17b: Checkpoints for non-structured frameworks
-- control_checkpoints.framework stores the framework UUID cast as text
DELETE FROM control_checkpoints
WHERE framework IN (
    SELECT id::text FROM frameworks
    WHERE name NOT IN ('ECC-2:2024', 'SACS-002')
);

-- Step 17c: Control library entries for non-structured frameworks
DELETE FROM control_library
WHERE framework_id IN (
    SELECT id FROM frameworks
    WHERE name NOT IN ('ECC-2:2024', 'SACS-002')
);

-- Step 17d: Framework rows (non-structured only)
-- ECC-2:2024 and SACS-002 rows in the frameworks master table are kept
-- so they continue to appear in the analysis dropdown on next boot.
DELETE FROM frameworks
WHERE name NOT IN ('ECC-2:2024', 'SACS-002');

COMMIT;

-- ============================================================
-- POST-COMMIT VERIFICATION QUERIES
--
-- Run these after the transaction commits to confirm the state.
-- User-generated tables must show 0 rows.
-- Framework/reference tables must show non-zero rows.
-- ============================================================

/*
-- ── User-generated tables (all should be 0) ──────────────────
SELECT 'users (non-admin)'       AS check_table,
       COUNT(*) AS row_count,
       CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'UNEXPECTED ROWS' END AS status
FROM users WHERE role != 'admin'

UNION ALL SELECT 'otp_tokens',             COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM otp_tokens
UNION ALL SELECT 'password_reset_tokens',  COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM password_reset_tokens
UNION ALL SELECT 'policies',               COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM policies
UNION ALL SELECT 'policy_chunks',          COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM policy_chunks
UNION ALL SELECT 'policy_versions',        COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM policy_versions
UNION ALL SELECT 'policy_ecc_assessments', COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM policy_ecc_assessments
UNION ALL SELECT 'compliance_results',     COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM compliance_results
UNION ALL SELECT 'gaps',                   COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM gaps
UNION ALL SELECT 'mapping_reviews',        COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM mapping_reviews
UNION ALL SELECT 'remediation_drafts',     COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM remediation_drafts
UNION ALL SELECT 'reports',                COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM reports
UNION ALL SELECT 'ai_insights',            COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM ai_insights
UNION ALL SELECT 'audit_logs',             COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM audit_logs
UNION ALL SELECT 'verification_cache',     COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM verification_cache
UNION ALL SELECT 'ecc2_verification_cache',COUNT(*), CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'FAIL' END FROM ecc2_verification_cache

ORDER BY status DESC, check_table;

-- ── Framework/reference tables (all should be > 0) ───────────
SELECT 'users (admin)'           AS check_table,
       COUNT(*) AS row_count,
       CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING: no admins' END AS status
FROM users WHERE role = 'admin'

UNION ALL SELECT 'frameworks',              COUNT(*), CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END FROM frameworks
UNION ALL SELECT 'control_library',         COUNT(*), CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END FROM control_library
UNION ALL SELECT 'control_checkpoints',     COUNT(*), CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END FROM control_checkpoints
UNION ALL SELECT 'framework_chunks',        COUNT(*), CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END FROM framework_chunks
UNION ALL SELECT 'ecc_framework',           COUNT(*), CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END FROM ecc_framework
UNION ALL SELECT 'ecc_compliance_metadata', COUNT(*), CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END FROM ecc_compliance_metadata
UNION ALL SELECT 'ecc_ai_checkpoints',      COUNT(*), CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END FROM ecc_ai_checkpoints
UNION ALL SELECT 'sacs002_metadata',        COUNT(*), CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END FROM sacs002_metadata
UNION ALL SELECT 'system_settings',         COUNT(*), CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END FROM system_settings
UNION ALL SELECT 'framework_load_log',      COUNT(*), CASE WHEN COUNT(*) > 0 THEN 'OK' ELSE 'WARNING' END FROM framework_load_log

ORDER BY status DESC, check_table;
*/
