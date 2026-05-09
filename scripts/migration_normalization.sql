-- ============================================================
-- Hemaya Policy AI — Normalization Migration
-- Migration #4 of 4
-- Run after: migration_indexes, migration_integrity, migration_rls
--
-- WHAT THIS FIXES:
--
--   PART A — Missing UNIQUE constraints:
--     Three tables allow logically duplicate rows because no
--     UNIQUE constraint was declared. Duplicates accumulate
--     silently on re-analysis and cause incorrect aggregates
--     in the dashboard (double-counted scores, inflated gap
--     counts, ambiguous "latest" version lookups).
--
--     compliance_results (policy_id, framework_id)
--       → Only one result row should exist per policy + framework
--         combination. Re-analysis must overwrite, not append.
--
--     control_library (framework_id, control_code)
--       → A framework cannot have two controls with the same
--         code. ecc2_schema.sql already enforces this on
--         ecc_framework; control_library needs the same guard.
--
--     policy_versions (policy_id, version_number)
--       → The PolicyVersion docstring explicitly states this
--         constraint must exist for monotonic versioning, but
--         it was never declared in __table_args__.
--
--   PART B — ecc_compliance_metadata.frequency uses TEXT
--     instead of the frequency_enum type already defined in
--     the schema (DO $$ CREATE TYPE frequency_enum ... $$).
--     The enum exists but the column ignores it, allowing
--     arbitrary strings that silently break AI context queries.
--
--   NOTE — gaps.control_name:
--     This column is a partial 2NF violation: for gaps created
--     by checkpoint_analyzer and main.py it duplicates
--     control_library.title. However, ecc2_analyzer.py writes
--     gaps with control_id = NULL and stores the control label
--     only in control_name, so the column cannot be dropped
--     at the DB level without application changes first.
--     A separate application-layer migration will:
--       1. Remove control_name from INSERTs that also set control_id.
--       2. Update SELECTs to COALESCE(cl.title, g.control_name).
--     The column is left intact here intentionally.
--
-- STRATEGY:
--   UNIQUE constraints:
--     CREATE UNIQUE INDEX CONCURRENTLY  — builds in the background
--     without blocking reads or writes.
--     ALTER TABLE … ADD CONSTRAINT … USING INDEX — promotes the
--     index to a named constraint with zero additional lock time.
--     If duplicates exist, the CONCURRENTLY step will fail with
--     a clear error listing the conflicting rows. Fix the data,
--     then re-run.
--
--   frequency_enum:
--     Step 1: NULL out any values not in the enum (a pre-flight
--             UPDATE so the ALTER does not fail mid-migration).
--     Step 2: ALTER COLUMN … TYPE frequency_enum USING cast.
--             Short ACCESS EXCLUSIVE lock — table is small (one
--             row per control), so this completes in <1 ms.
--
-- HOW TO RUN:
--   The CONCURRENTLY statements MUST run outside a transaction.
--   The frequency_enum steps CAN run inside a transaction.
--   Run the file as:
--     psql $DATABASE_URL -f migration_normalization.sql
--
-- SAFE TO RE-RUN:
--   UNIQUE INDEX uses IF NOT EXISTS.
--   ALTER TABLE ADD CONSTRAINT uses DO $$ IF NOT EXISTS $$.
--   frequency UPDATE is idempotent.
--   ALTER COLUMN USING is guarded by a DO $$ IF NOT EXISTS $$.
-- ============================================================


-- ============================================================
-- PRE-FLIGHT: check for duplicates before creating indexes.
-- Run these queries manually before executing the migration.
-- Each should return 0 rows. If not, fix the data first.
-- ============================================================

/*
-- compliance_results duplicates:
SELECT policy_id, framework_id, COUNT(*)
FROM compliance_results
GROUP BY policy_id, framework_id
HAVING COUNT(*) > 1;

-- control_library duplicates:
SELECT framework_id, control_code, COUNT(*)
FROM control_library
GROUP BY framework_id, control_code
HAVING COUNT(*) > 1;

-- policy_versions duplicates:
SELECT policy_id, version_number, COUNT(*)
FROM policy_versions
GROUP BY policy_id, version_number
HAVING COUNT(*) > 1;

-- frequency values outside the enum:
SELECT DISTINCT frequency
FROM ecc_compliance_metadata
WHERE frequency IS NOT NULL
  AND frequency NOT IN ('continuously', 'periodically', 'annually', 'on_event');
*/


-- ============================================================
-- PART A-1: compliance_results UNIQUE(policy_id, framework_id)
--
-- One compliance result row per policy per framework.
-- Without this, re-analysis appends a new row instead of
-- updating, causing the dashboard to double-count scores.
--
-- Application fix (run before this migration if duplicates
-- exist): keep only the latest row per (policy_id, framework_id)
--   DELETE FROM compliance_results a
--   USING compliance_results b
--   WHERE a.policy_id    = b.policy_id
--     AND a.framework_id = b.framework_id
--     AND a.analyzed_at  < b.analyzed_at;
-- ============================================================

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    uq_compliance_results_policy_framework
    ON compliance_results (policy_id, framework_id);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'compliance_results'::regclass
          AND contype  = 'u'
          AND conname  = 'uq_compliance_results_policy_framework'
    ) THEN
        ALTER TABLE compliance_results
            ADD CONSTRAINT uq_compliance_results_policy_framework
            UNIQUE USING INDEX uq_compliance_results_policy_framework;
        RAISE NOTICE 'Added: compliance_results UNIQUE(policy_id, framework_id)';
    ELSE
        RAISE NOTICE 'Already exists: compliance_results uq constraint';
    END IF;
END $$;


-- ============================================================
-- PART A-2: control_library UNIQUE(framework_id, control_code)
--
-- A framework cannot have two controls sharing the same code.
-- ecc_framework already enforces this (uq_ecc_framework_control).
-- control_library (the non-ECC uploaded-framework controls) needs
-- the same protection.
-- ============================================================

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS
    uq_control_library_framework_code
    ON control_library (framework_id, control_code);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'control_library'::regclass
          AND contype  = 'u'
          AND conname  = 'uq_control_library_framework_code'
    ) THEN
        ALTER TABLE control_library
            ADD CONSTRAINT uq_control_library_framework_code
            UNIQUE USING INDEX uq_control_library_framework_code;
        RAISE NOTICE 'Added: control_library UNIQUE(framework_id, control_code)';
    ELSE
        RAISE NOTICE 'Already exists: control_library uq constraint';
    END IF;
END $$;


-- ============================================================
-- PART A-3: policy_versions UNIQUE(policy_id, version_number)
--
-- SKIPPED — constraint already exists.
--
-- The startup migration in main.py (CREATE TABLE IF NOT EXISTS
-- policy_versions) declares UNIQUE (policy_id, version_number)
-- inline, so the constraint is already present on any database
-- that has run the application at least once.
--
-- Adding it again would create a second redundant unique index
-- on the same columns, wasting disk space and write overhead.
-- ============================================================

-- (no-op — already enforced by startup migration)


-- ============================================================
-- PART B: ecc_compliance_metadata.frequency → frequency_enum
--
-- frequency_enum was defined in ecc2_schema.sql:
--   CREATE TYPE frequency_enum AS ENUM (
--       'continuously', 'periodically', 'annually', 'on_event'
--   );
-- The column was declared TEXT with a comment: "Using TEXT for
-- flexibility; see frequency_enum for valid values." This allowed
-- arbitrary strings — the enum was effectively bypassed.
--
-- Step B-1: NULL out any values not matching the enum.
--           These are bad data; keeping them would block the
--           ALTER (cannot cast arbitrary TEXT to frequency_enum).
-- Step B-2: Change the column type to frequency_enum.
-- ============================================================

BEGIN;

-- B-1: Sanitise values not in the enum
UPDATE ecc_compliance_metadata
SET frequency = NULL
WHERE frequency IS NOT NULL
  AND frequency NOT IN ('continuously', 'periodically', 'annually', 'on_event');

-- B-2: Drop the dependent view.
--      ecc_full_control_view selects m.frequency, so PostgreSQL
--      refuses to change the column type while the view exists.
--      The view is recreated verbatim in B-4.
DROP VIEW IF EXISTS ecc_full_control_view;

-- B-3: Convert column type (guarded so re-run is safe)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'ecc_compliance_metadata'
          AND column_name  = 'frequency'
          AND data_type    = 'text'   -- only run if still TEXT
    ) THEN
        ALTER TABLE ecc_compliance_metadata
            ALTER COLUMN frequency TYPE frequency_enum
            USING frequency::frequency_enum;
        RAISE NOTICE 'Converted: ecc_compliance_metadata.frequency TEXT → frequency_enum';
    ELSE
        RAISE NOTICE 'Skipped: ecc_compliance_metadata.frequency already typed (not TEXT)';
    END IF;
END $$;

-- B-4: Recreate ecc_full_control_view (verbatim from ecc2_schema.sql).
--      Now m.frequency is typed as frequency_enum, which the view
--      inherits automatically.
CREATE OR REPLACE VIEW ecc_full_control_view AS
SELECT
    f.framework_id,
    f.domain_code,
    f.domain_name,
    f.subdomain_code,
    f.subdomain_name,
    f.control_code,
    f.control_type,
    f.control_text,
    f.parent_control_code,
    f.is_ecc2_new,
    f.ecc2_change_note,
    f.source_page,
    m.applicability,
    m.applicability_note,
    m.responsible_party,
    m.frequency,
    m.ecc_version_introduced,
    m.change_from_ecc1,
    m.deleted_in_ecc2
FROM ecc_framework f
LEFT JOIN ecc_compliance_metadata m
    ON f.framework_id = m.framework_id
    AND f.control_code = m.control_code;

COMMENT ON VIEW ecc_full_control_view IS
    'Combines Layer 1 and Layer 2 only. Does NOT include AI checkpoints. Safe to use in compliance reports.';

COMMIT;


-- ============================================================
-- VERIFICATION
-- ============================================================

/*
-- A: Confirm all three UNIQUE constraints exist:
SELECT
    tc.table_name,
    tc.constraint_name,
    string_agg(kcu.column_name, ', ' ORDER BY kcu.ordinal_position) AS columns
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
WHERE tc.constraint_type = 'UNIQUE'
  AND tc.table_name IN ('compliance_results', 'control_library', 'policy_versions')
  AND tc.constraint_name LIKE 'uq_%'
GROUP BY tc.table_name, tc.constraint_name
ORDER BY tc.table_name;

-- B: Confirm frequency column is now an enum type:
SELECT
    column_name,
    udt_name AS type_name,
    data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name   = 'ecc_compliance_metadata'
  AND column_name  = 'frequency';
-- Expected: udt_name = 'frequency_enum', data_type = 'USER-DEFINED'

-- B: Confirm no out-of-range frequency values remain:
SELECT DISTINCT frequency
FROM ecc_compliance_metadata
WHERE frequency IS NOT NULL
ORDER BY frequency;
-- Expected: only values from ('continuously', 'periodically', 'annually', 'on_event')
*/
