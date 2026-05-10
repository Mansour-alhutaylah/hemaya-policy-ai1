-- ============================================================
-- migration_ccc2_cache.sql
-- Creates the CCC-2:2024 per-control AI analysis cache table.
-- Mirrors sacs002_verification_cache schema exactly.
-- Run via: python scripts/run_migration.py scripts/migration_ccc2_cache.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS ccc2_verification_cache (
    cache_key       TEXT        PRIMARY KEY,
    control_code    TEXT        NOT NULL,
    policy_hash     TEXT        NOT NULL,
    prompt_version  TEXT        NOT NULL,
    model           TEXT        NOT NULL,
    result          JSONB       NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    ttl_expiration  TIMESTAMPTZ
);

COMMENT ON TABLE ccc2_verification_cache IS
    'Per-control GPT result cache for CCC-2:2024 analysis. '
    'Cache key is a SHA-256 of (control_code, policy_hash, prompt_version, model, '
    'retrieval_floor, grounding_version, grounding_sim). TTL: 30 days.';

CREATE INDEX IF NOT EXISTS idx_ccc2vc_policy_hash
    ON ccc2_verification_cache (policy_hash);

CREATE INDEX IF NOT EXISTS idx_ccc2vc_control_code
    ON ccc2_verification_cache (control_code);

CREATE INDEX IF NOT EXISTS idx_ccc2vc_prompt_version
    ON ccc2_verification_cache (prompt_version);

CREATE INDEX IF NOT EXISTS idx_ccc2vc_updated_at
    ON ccc2_verification_cache (updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_ccc2vc_ttl
    ON ccc2_verification_cache (ttl_expiration)
    WHERE ttl_expiration IS NOT NULL;

ALTER TABLE ccc2_verification_cache ENABLE ROW LEVEL SECURITY;
