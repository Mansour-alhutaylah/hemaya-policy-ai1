-- ECC-2:2024 Three-Layer Database Schema for Himaya Policy AI
-- Compatible with PostgreSQL 14+ and Supabase
-- Run this file once against the target database before running ecc2_import.sql

-- ============================================================
-- TYPES
-- ============================================================

DO $$ BEGIN
    CREATE TYPE control_type_enum AS ENUM (
        'domain',
        'subdomain',
        'main_control',
        'subcontrol'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE applicability_enum AS ENUM (
        'mandatory_all',
        'conditional_cloud_users_only',
        'conditional_ot_users',
        'mandatory_cloud_users',
        'deleted'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE frequency_enum AS ENUM (
        'continuously',
        'periodically',
        'annually',
        'on_event'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE compliance_status_enum AS ENUM (
        'compliant',
        'partial',
        'non_compliant',
        'not_applicable',
        'pending'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE assessed_by_enum AS ENUM (
        'AI',
        'human'
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ============================================================
-- LAYER 1: Official Regulatory Text
-- Never modified by AI. Source of truth for all compliance.
-- ============================================================

CREATE TABLE IF NOT EXISTS ecc_framework (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id          VARCHAR(50)          NOT NULL,  -- e.g. 'ECC-2:2024'
    domain_code           VARCHAR(10),                    -- e.g. '1', '2'
    domain_name           TEXT,
    subdomain_code        VARCHAR(20),                    -- e.g. '1-1', '2-4'
    subdomain_name        TEXT,
    control_code          VARCHAR(30)          NOT NULL,  -- e.g. '1-1-1', '2-4-3-5'
    control_type          control_type_enum   NOT NULL,
    control_text          TEXT                NOT NULL,
    parent_control_code   VARCHAR(30),                    -- NULL for main controls
    is_ecc2_new           BOOLEAN             DEFAULT FALSE,
    ecc2_change_note      TEXT,
    source_page           INTEGER,
    created_at            TIMESTAMPTZ         DEFAULT NOW(),

    CONSTRAINT uq_ecc_framework_control UNIQUE (framework_id, control_code)
);

COMMENT ON TABLE ecc_framework IS
    'Layer 1 — Official ECC regulatory text only. Rows are effectively immutable after initial load. Any update requires an explicit migration with version tracking.';

COMMENT ON COLUMN ecc_framework.control_text IS
    'Verbatim or close-paraphrase of official ECC control text. Never AI-generated.';

CREATE INDEX IF NOT EXISTS idx_ecc_framework_domain
    ON ecc_framework (framework_id, domain_code);

CREATE INDEX IF NOT EXISTS idx_ecc_framework_subdomain
    ON ecc_framework (framework_id, subdomain_code);

CREATE INDEX IF NOT EXISTS idx_ecc_framework_parent
    ON ecc_framework (framework_id, parent_control_code);

-- ============================================================
-- LAYER 2: Compliance Metadata
-- Human-validated operational metadata. Supplements Layer 1.
-- ============================================================

CREATE TABLE IF NOT EXISTS ecc_compliance_metadata (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id            VARCHAR(50)         NOT NULL,
    control_code            VARCHAR(30)         NOT NULL,
    applicability           applicability_enum,
    applicability_note      TEXT,
    responsible_party       TEXT,
    frequency               TEXT,               -- Using TEXT for flexibility; see frequency_enum for valid values
    ecc_version_introduced  VARCHAR(20),        -- 'ECC-1' or 'ECC-2'
    change_from_ecc1        TEXT,
    deleted_in_ecc2         BOOLEAN             DEFAULT FALSE,
    created_at              TIMESTAMPTZ         DEFAULT NOW(),

    CONSTRAINT fk_ecm_framework FOREIGN KEY (framework_id, control_code)
        REFERENCES ecc_framework (framework_id, control_code)
        ON DELETE CASCADE,

    CONSTRAINT uq_ecm_control UNIQUE (framework_id, control_code)
);

COMMENT ON TABLE ecc_compliance_metadata IS
    'Layer 2 — Compliance metadata derived from official ECC document. Human-validated. Does not contain regulatory text.';

-- ============================================================
-- LAYER 3: AI Audit Checkpoints
-- AI-generated audit aids. Must NEVER be presented as official ECC content.
-- ============================================================

CREATE TABLE IF NOT EXISTS ecc_ai_checkpoints (
    id                              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id                    VARCHAR(50)     NOT NULL,
    control_code                    VARCHAR(30)     NOT NULL,
    ai_generated                    BOOLEAN         NOT NULL DEFAULT TRUE
                                        CONSTRAINT chk_ai_generated CHECK (ai_generated = TRUE),
    model_version                   VARCHAR(100),
    generated_at                    TIMESTAMPTZ     DEFAULT NOW(),
    audit_questions                 JSONB,          -- array of strings
    suggested_evidence              JSONB,          -- array of strings
    indicators_of_implementation    JSONB,          -- array of strings
    maturity_signals                JSONB,          -- object: {initial, developing, defined, advanced}
    possible_documents              JSONB,          -- array of strings
    possible_technical_evidence     JSONB,          -- array of strings
    human_reviewed                  BOOLEAN         DEFAULT FALSE,
    human_reviewer                  VARCHAR(200),
    human_review_date               DATE,
    created_at                      TIMESTAMPTZ     DEFAULT NOW()
);

COMMENT ON TABLE ecc_ai_checkpoints IS
    'Layer 3 — AI-generated audit preparation aids. ai_generated is constrained to TRUE. Never join-present this data to auditors as if it were from ecc_framework.';

COMMENT ON COLUMN ecc_ai_checkpoints.ai_generated IS
    'Always TRUE. Enforced by CHECK constraint. Prevents accidental removal of AI provenance flag.';

CREATE INDEX IF NOT EXISTS idx_ecc_ai_checkpoints_control
    ON ecc_ai_checkpoints (framework_id, control_code);

-- ============================================================
-- POLICY ASSESSMENT RESULTS
-- Per-policy compliance assessments linking uploaded policies to ECC controls.
-- ============================================================

CREATE TABLE IF NOT EXISTS policy_ecc_assessments (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_id         UUID                    NOT NULL,  -- FK to policies table
    framework_id      VARCHAR(50)             NOT NULL,
    control_code      VARCHAR(30)             NOT NULL,
    compliance_status compliance_status_enum  NOT NULL DEFAULT 'pending',
    evidence_text     TEXT,                              -- extracted supporting text from policy
    gap_description   TEXT,
    confidence_score  FLOAT
                        CONSTRAINT chk_confidence CHECK (confidence_score BETWEEN 0.0 AND 1.0),
    assessed_by       assessed_by_enum        NOT NULL DEFAULT 'AI',
    assessed_at       TIMESTAMPTZ             DEFAULT NOW(),
    human_override    BOOLEAN                 DEFAULT FALSE,
    override_by       VARCHAR(200),
    override_at       TIMESTAMPTZ,
    notes             TEXT,

    CONSTRAINT uq_policy_control UNIQUE (policy_id, control_code)
);

COMMENT ON TABLE policy_ecc_assessments IS
    'Links uploaded policies to ECC control assessments. human_override=true preserves audit trail when humans correct AI assessments.';

CREATE INDEX IF NOT EXISTS idx_pea_policy
    ON policy_ecc_assessments (policy_id);

CREATE INDEX IF NOT EXISTS idx_pea_control
    ON policy_ecc_assessments (framework_id, control_code);

CREATE INDEX IF NOT EXISTS idx_pea_status
    ON policy_ecc_assessments (compliance_status);

-- ============================================================
-- FRAMEWORK LOAD TRACKING
-- Tracks when frameworks were loaded or reloaded.
-- ============================================================

CREATE TABLE IF NOT EXISTS framework_load_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    framework_id    VARCHAR(50)     NOT NULL,
    loaded_at       TIMESTAMPTZ     DEFAULT NOW(),
    loaded_by       VARCHAR(200),
    controls_count  INTEGER,
    checkpoints_count INTEGER,
    notes           TEXT
);

COMMENT ON TABLE framework_load_log IS
    'Audit trail for framework data loads and reloads.';

-- ============================================================
-- HELPER VIEWS
-- ============================================================

-- Full control view joining all three layers
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

-- Controls with outstanding assessment gaps per policy
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
