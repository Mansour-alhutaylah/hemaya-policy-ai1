-- ============================================================
-- Hemaya Policy AI — DB-4: verify ecc_* FK drift
-- ============================================================
--
-- WHAT THIS DOES
--   READ-ONLY diagnostic. Runs no DDL. Lists every foreign-key
--   constraint on the two ECC-2 child tables so we can confirm
--   whether the live database has the duplicate / mis-pointing
--   constraints flagged by the schema audit.
--
-- BACKGROUND
--   The user-supplied schema dump showed FOUR `fk_ecc_*_framework_
--   control` constraints on each of:
--     - public.ecc_ai_checkpoints
--     - public.ecc_compliance_metadata
--   …with mismatched columns (some pointed framework_id at the
--   parent's control_code column, etc.). The migration script in
--   data/ecc2/ecc2_schema.sql defines only ONE correct constraint
--   per table, so this is schema drift between repo and live DB.
--
-- WHAT TO DO WITH THE OUTPUT
--   Send me (or include in the next commit message) the result of
--   the two queries below. Once we know exactly what's there, the
--   cleanup script (DB-4 apply) will:
--     - DROP the wrong constraints by name
--     - Keep / re-create the one correct constraint per table
--     - VALIDATE
--   No DROP runs from this script.
-- ============================================================


-- ── Query 1: enumerate all FK constraints on ecc_ai_checkpoints ──
SELECT
    c.conname                     AS constraint_name,
    pg_get_constraintdef(c.oid)   AS definition
FROM pg_constraint c
WHERE c.conrelid = 'public.ecc_ai_checkpoints'::regclass
  AND c.contype  = 'f'
ORDER BY c.conname;


-- ── Query 2: enumerate all FK constraints on ecc_compliance_metadata ──
SELECT
    c.conname                     AS constraint_name,
    pg_get_constraintdef(c.oid)   AS definition
FROM pg_constraint c
WHERE c.conrelid = 'public.ecc_compliance_metadata'::regclass
  AND c.contype  = 'f'
ORDER BY c.conname;


-- ── Query 3: confirm the parent ecc_framework has a unique key
--    on (framework_id, control_code) so a child FK is even valid ──
SELECT
    c.conname                     AS constraint_name,
    pg_get_constraintdef(c.oid)   AS definition
FROM pg_constraint c
WHERE c.conrelid = 'public.ecc_framework'::regclass
  AND c.contype  IN ('u', 'p')
ORDER BY c.conname;


-- ── Query 4: any rows that would be orphaned if we cleaned up?
--    (read-only — won't delete anything) ──
SELECT
    'ecc_ai_checkpoints' AS child,
    COUNT(*)             AS rows_with_no_parent
FROM ecc_ai_checkpoints aic
LEFT JOIN ecc_framework ef
       ON ef.framework_id = aic.framework_id
      AND ef.control_code = aic.control_code
WHERE ef.id IS NULL
UNION ALL
SELECT
    'ecc_compliance_metadata',
    COUNT(*)
FROM ecc_compliance_metadata ecm
LEFT JOIN ecc_framework ef
       ON ef.framework_id = ecm.framework_id
      AND ef.control_code = ecm.control_code
WHERE ef.id IS NULL;
