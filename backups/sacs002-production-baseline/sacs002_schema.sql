-- SACS-002 Three-Layer Database Schema for Himaya Policy AI
-- Saudi Aramco Third Party Cybersecurity Standard, Feb 2022
-- Uses the shared ecc_framework / ecc_compliance_metadata / ecc_ai_checkpoints tables
-- with framework_id = 'SACS-002'. Run this once before sacs002_import.py.

-- ============================================================
-- SACS-002-SPECIFIC TYPES
-- ============================================================

DO $$ BEGIN
    CREATE TYPE sacs002_applicability_enum AS ENUM (
        'all_third_parties',
        'network_connectivity',
        'outsourced_infrastructure',
        'critical_data_processor',
        'customized_software',
        'cloud_computing_service'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE sacs002_section_enum AS ENUM (
        'A',
        'B'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE nist_csf_function_enum AS ENUM (
        'GV',
        'ID',
        'PR',
        'DE',
        'RS',
        'RC'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- SACS-002 EXTENDED METADATA TABLE
-- Supplements ecc_compliance_metadata with SACS-002-specific fields.
-- ============================================================

CREATE TABLE IF NOT EXISTS sacs002_metadata (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id                VARCHAR(50)             NOT NULL DEFAULT 'SACS-002',
    control_code                VARCHAR(30)             NOT NULL,
    section                     sacs002_section_enum    NOT NULL,           -- 'A' (all) or 'B' (conditional)
    nist_function_code          VARCHAR(10),                                -- e.g. 'GV', 'ID', 'PR'
    nist_function_name          TEXT,
    nist_category_code          VARCHAR(20),                                -- e.g. 'GV.OC', 'PR.AT'
    nist_category_name          TEXT,
    applicable_classes          JSONB,                                      -- array of sacs002_applicability_enum values
    governance_control          BOOLEAN                 DEFAULT FALSE,
    technical_control           BOOLEAN                 DEFAULT FALSE,
    operational_control         BOOLEAN                 DEFAULT FALSE,
    review_required             BOOLEAN                 DEFAULT FALSE,
    approval_required           BOOLEAN                 DEFAULT FALSE,
    testing_required            BOOLEAN                 DEFAULT FALSE,
    monitoring_required         BOOLEAN                 DEFAULT FALSE,
    third_party_assessment      BOOLEAN                 DEFAULT FALSE,
    created_at                  TIMESTAMPTZ             DEFAULT NOW(),

    CONSTRAINT fk_sacs002_meta_framework FOREIGN KEY (framework_id, control_code)
        REFERENCES ecc_framework (framework_id, control_code)
        ON DELETE CASCADE,

    CONSTRAINT uq_sacs002_meta_control UNIQUE (framework_id, control_code)
);

COMMENT ON TABLE sacs002_metadata IS
    'SACS-002-specific metadata: NIST CSF mapping, section (A/B), applicability classes, and control type flags. Supplements ecc_compliance_metadata.';

CREATE INDEX IF NOT EXISTS idx_sacs002_meta_nist_cat
    ON sacs002_metadata (nist_category_code);

CREATE INDEX IF NOT EXISTS idx_sacs002_meta_section
    ON sacs002_metadata (section);

-- ============================================================
-- HELPER VIEWS
-- ============================================================

CREATE OR REPLACE VIEW sacs002_full_control_view AS
SELECT
    f.framework_id,
    f.control_code,
    f.control_text,
    f.source_page,
    m.section,
    m.nist_function_code,
    m.nist_function_name,
    m.nist_category_code,
    m.nist_category_name,
    m.applicable_classes,
    m.governance_control,
    m.technical_control,
    m.operational_control,
    m.review_required,
    m.approval_required,
    m.testing_required,
    m.monitoring_required,
    cm.applicability,
    cm.responsible_party,
    cm.frequency
FROM ecc_framework f
LEFT JOIN sacs002_metadata m
    ON f.framework_id = m.framework_id
    AND f.control_code = m.control_code
LEFT JOIN ecc_compliance_metadata cm
    ON f.framework_id = cm.framework_id
    AND f.control_code = cm.control_code
WHERE f.framework_id = 'SACS-002';

COMMENT ON VIEW sacs002_full_control_view IS
    'Layer 1 + Layer 2 for SACS-002. Safe for compliance reports. Does NOT include AI checkpoints.';
