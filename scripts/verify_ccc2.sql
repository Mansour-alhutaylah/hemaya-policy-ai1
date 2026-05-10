-- ============================================================
-- CCC-2:2024 Verification Queries
-- Run after deployment to confirm all structured data is loaded.
-- Execute via: python scripts/run_migration.py scripts/verify_ccc2.sql
-- (or paste directly into your Supabase SQL editor)
-- ============================================================

-- ── Layer 1: ecc_framework row counts ───────────────────────
-- Expected:
--   domain        →   4
--   subdomain     →  24
--   main_control  →  55
--   subcontrol    → 120
--   TOTAL         → 203
SELECT
    control_type,
    COUNT(*) AS row_count,
    CASE
        WHEN control_type = 'domain'       AND COUNT(*) =   4 THEN 'OK'
        WHEN control_type = 'subdomain'    AND COUNT(*) =  24 THEN 'OK'
        WHEN control_type = 'main_control' AND COUNT(*) =  55 THEN 'OK'
        WHEN control_type = 'subcontrol'   AND COUNT(*) = 120 THEN 'OK'
        ELSE 'UNEXPECTED'
    END AS status
FROM ecc_framework
WHERE framework_id = 'CCC-2:2024'
GROUP BY control_type
ORDER BY control_type;

-- ── Layer 2a: ccc_metadata (CCC-2-specific, 175 rows) ────────
-- Expected: 175 rows (main_control + subcontrol only)
SELECT
    COUNT(*) AS ccc_metadata_rows,
    CASE WHEN COUNT(*) = 175 THEN 'OK' ELSE 'UNEXPECTED — expected 175' END AS status
FROM ccc_metadata
WHERE framework_id = 'CCC-2:2024';

-- ── Layer 2b: ecc_compliance_metadata (shared, 175 rows) ────
SELECT
    COUNT(*) AS ecc_compliance_metadata_rows,
    CASE WHEN COUNT(*) = 175 THEN 'OK' ELSE 'UNEXPECTED — expected 175' END AS status
FROM ecc_compliance_metadata
WHERE framework_id = 'CCC-2:2024';

-- ── Layer 3: ecc_ai_checkpoints (175 rows) ───────────────────
SELECT
    COUNT(*) AS ai_checkpoint_rows,
    CASE WHEN COUNT(*) = 175 THEN 'OK' ELSE 'UNEXPECTED — expected 175' END AS status
FROM ecc_ai_checkpoints
WHERE framework_id = 'CCC-2:2024';

-- ── frameworks master table (dropdown row) ───────────────────
SELECT
    id,
    name,
    version,
    CASE WHEN id IS NOT NULL THEN 'OK' ELSE 'MISSING — restart backend' END AS status
FROM frameworks
WHERE name = 'CCC-2:2024';

-- ── Orphan check: L3 entries without matching L1 ─────────────
-- Expected: 0 orphans
SELECT
    COUNT(*) AS orphan_l3_count,
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'ORPHANS FOUND' END AS status
FROM ecc_ai_checkpoints c
LEFT JOIN ecc_framework f
    ON c.framework_id = f.framework_id AND c.control_code = f.control_code
WHERE c.framework_id = 'CCC-2:2024' AND f.control_code IS NULL;

-- ── Missing L2 check: main/subcontrols without ccc_metadata ──
-- Expected: 0 missing
SELECT
    COUNT(*) AS missing_ccc_metadata_count,
    CASE WHEN COUNT(*) = 0 THEN 'OK' ELSE 'CONTROLS WITHOUT METADATA' END AS status
FROM ecc_framework f
LEFT JOIN ccc_metadata cm
    ON f.framework_id = cm.framework_id AND f.control_code = cm.control_code
WHERE f.framework_id = 'CCC-2:2024'
  AND f.control_type IN ('main_control', 'subcontrol')
  AND cm.control_code IS NULL;

-- ── CSP vs CST split in ccc_metadata ─────────────────────────
SELECT
    applicability_type,
    COUNT(*) AS count
FROM ccc_metadata
WHERE framework_id = 'CCC-2:2024'
GROUP BY applicability_type
ORDER BY applicability_type;

-- ── Cache table (created by migration_ccc2_cache.sql) ─────────
-- Expected: table exists, 0 rows initially
SELECT
    COUNT(*) AS cache_rows,
    'OK — table exists' AS status
FROM ccc2_verification_cache;

-- ── Summary readiness check ───────────────────────────────────
SELECT
    'CCC-2:2024'                          AS framework,
    (SELECT COUNT(*) FROM ecc_framework WHERE framework_id = 'CCC-2:2024')
                                           AS l1_total,
    (SELECT COUNT(*) FROM ccc_metadata WHERE framework_id = 'CCC-2:2024')
                                           AS l2_ccc_meta,
    (SELECT COUNT(*) FROM ecc_ai_checkpoints WHERE framework_id = 'CCC-2:2024')
                                           AS l3_checkpoints,
    (SELECT EXISTS(SELECT 1 FROM frameworks WHERE name = 'CCC-2:2024'))
                                           AS in_frameworks_table,
    CASE
        WHEN (SELECT COUNT(*) FROM ecc_framework WHERE framework_id = 'CCC-2:2024') >= 203
         AND (SELECT COUNT(*) FROM ccc_metadata WHERE framework_id = 'CCC-2:2024') >= 175
         AND (SELECT COUNT(*) FROM ecc_ai_checkpoints WHERE framework_id = 'CCC-2:2024') >= 175
        THEN 'READY — is_ready=True structured=True'
        ELSE 'NOT READY — run python data/ccc2/ccc2_import.py'
    END AS readiness;
