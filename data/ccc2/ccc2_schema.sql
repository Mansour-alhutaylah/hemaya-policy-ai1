-- CCC-2:2024 Three-Layer Database Schema for Hemaya Policy AI
-- Cloud Cybersecurity Controls — National Cybersecurity Authority (NCA), Saudi Arabia
-- Compatible with PostgreSQL 14+ and Supabase
-- Uses the shared ecc_framework / ecc_compliance_metadata / ecc_ai_checkpoints tables
-- with framework_id = 'CCC-2:2024'. Run this file once before ccc2_import.py.

-- ============================================================
-- CCC-2-SPECIFIC TYPES
-- ============================================================

DO $$ BEGIN
    CREATE TYPE ccc2_applicability_type_enum AS ENUM (
        'CSP',
        'CST',
        'both'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

COMMENT ON TYPE ccc2_applicability_type_enum IS
    'CCC-2:2024 distinguishes between Cloud Service Provider (CSP) and Cloud Service Tenant (CST) obligations. Controls are notated X-Y-P-Z (Provider) or X-Y-T-Z (Tenant).';

-- ============================================================
-- CCC-2-SPECIFIC METADATA TABLE
-- Supplements ecc_compliance_metadata with CCC-2 unique fields.
-- Uses the shared ecc_framework table (framework_id = ''CCC-2:2024'').
-- ============================================================

CREATE TABLE IF NOT EXISTS ccc_metadata (
    id                          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id                VARCHAR(50) NOT NULL DEFAULT 'CCC-2:2024',
    control_code                VARCHAR(40) NOT NULL,

    -- CSP / CST applicability
    applicability_type          ccc2_applicability_type_enum NOT NULL,

    -- ECC-2 cross-reference: controls this CCC-2 control extends
    ecc_references              JSONB,                          -- e.g. ["1-4-1"] or ["2-2-3"]

    -- Classification level applicability (Table 2 / Table 3 in CCC-2:2024)
    -- true = mandatory at that level, false = optional (recommended)
    mandatory_level_1           BOOLEAN     NOT NULL DEFAULT TRUE,
    mandatory_level_2           BOOLEAN     NOT NULL DEFAULT TRUE,
    mandatory_level_3           BOOLEAN     NOT NULL DEFAULT TRUE,
    mandatory_level_4           BOOLEAN     NOT NULL DEFAULT TRUE,

    -- Specific subcontrol exceptions noted in the annex footnotes
    optional_subcontrols_l3     JSONB,                          -- codes optional at Level 3
    optional_subcontrols_l4     JSONB,                          -- codes optional at Level 4
    not_applicable_subcontrols  JSONB,                          -- codes not applicable at any level

    -- Control type flags
    governance_control          BOOLEAN     NOT NULL DEFAULT FALSE,
    technical_control           BOOLEAN     NOT NULL DEFAULT FALSE,
    operational_control         BOOLEAN     NOT NULL DEFAULT FALSE,
    review_required             BOOLEAN     NOT NULL DEFAULT FALSE,
    approval_required           BOOLEAN     NOT NULL DEFAULT FALSE,
    testing_required            BOOLEAN     NOT NULL DEFAULT FALSE,
    monitoring_required         BOOLEAN     NOT NULL DEFAULT FALSE,

    created_at                  TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT fk_ccc_meta_framework FOREIGN KEY (framework_id, control_code)
        REFERENCES ecc_framework (framework_id, control_code)
        ON DELETE CASCADE,

    CONSTRAINT uq_ccc_meta_control UNIQUE (framework_id, control_code)
);

COMMENT ON TABLE ccc_metadata IS
    'CCC-2:2024-specific metadata: CSP/CST applicability, ECC-2 cross-references, mandatory classification levels, and control type flags. Supplements ecc_compliance_metadata for CCC-2 rows.';

CREATE INDEX IF NOT EXISTS idx_ccc_meta_applicability
    ON ccc_metadata (applicability_type);

CREATE INDEX IF NOT EXISTS idx_ccc_meta_framework
    ON ccc_metadata (framework_id, control_code);

-- ============================================================
-- CCC-2 FULL CONTROL VIEW
-- Combines Layer 1 (ecc_framework) + Layer 2 (ecc_compliance_metadata)
-- + CCC-2 metadata. Safe to use in compliance reports.
-- Does NOT include AI checkpoints (Layer 3).
-- ============================================================

DROP VIEW IF EXISTS ccc_full_control_view;

CREATE OR REPLACE VIEW ccc_full_control_view AS
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
    f.source_page,
    cm.applicability_type,
    cm.ecc_references,
    cm.mandatory_level_1,
    cm.mandatory_level_2,
    cm.mandatory_level_3,
    cm.mandatory_level_4,
    cm.optional_subcontrols_l3,
    cm.optional_subcontrols_l4,
    cm.not_applicable_subcontrols,
    cm.governance_control,
    cm.technical_control,
    cm.operational_control,
    cm.monitoring_required,
    em.responsible_party,
    em.frequency,
    em.applicability       AS nca_applicability,
    em.applicability_note
FROM ecc_framework f
LEFT JOIN ccc_metadata cm
    ON f.framework_id = cm.framework_id
    AND f.control_code = cm.control_code
LEFT JOIN ecc_compliance_metadata em
    ON f.framework_id = em.framework_id
    AND f.control_code = em.control_code
WHERE f.framework_id = 'CCC-2:2024';

COMMENT ON VIEW ccc_full_control_view IS
    'Combines CCC-2:2024 Layer 1 (official text) and Layer 2 (metadata) only. Does NOT include AI checkpoints. Safe to use in compliance reports.';

-- ============================================================
-- VERIFICATION QUERIES (run manually to confirm import)
-- ============================================================

/*
-- Confirm CCC-2 row counts:
SELECT control_type, COUNT(*)
FROM ecc_framework
WHERE framework_id = 'CCC-2:2024'
GROUP BY control_type
ORDER BY control_type;
-- Expected:
--   domain      →  4
--   subdomain   →  24
--   main_control → 55  (37 CSP + 18 CST)
--   subcontrol  → 120  (94 CSP + 26 CST)

-- Confirm CSP vs CST split:
SELECT applicability_type, COUNT(*)
FROM ccc_metadata
WHERE framework_id = 'CCC-2:2024'
GROUP BY applicability_type;

-- Confirm all main controls have metadata:
SELECT f.control_code
FROM ecc_framework f
LEFT JOIN ccc_metadata cm ON f.framework_id = cm.framework_id
    AND f.control_code = cm.control_code
WHERE f.framework_id = 'CCC-2:2024'
  AND f.control_type = 'main_control'
  AND cm.id IS NULL;
-- Should return 0 rows.

-- Sample view output:
SELECT control_code, applicability_type, mandatory_level_4, ecc_references
FROM ccc_full_control_view
WHERE control_type = 'main_control'
ORDER BY control_code
LIMIT 10;
*/
