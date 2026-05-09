-- ============================================================
-- Hemaya Policy AI — Performance Index Migration
-- Generated: 2026-05-09
--
-- WHAT THIS FIXES:
--   Every FK column used in WHERE / JOIN across the analysis
--   pipeline lacked an index. Without indexes PostgreSQL performs
--   sequential scans — this causes progressively slower response
--   times as policy count grows.
--
--   Also adds HNSW vector indexes on the embedding columns so
--   similarity searches use ANN (approximate nearest neighbour)
--   instead of exact full-table scans.
--
-- HOW TO RUN:
--   psql $DATABASE_URL -f migration_indexes.sql
--
--   B-tree indexes use CREATE INDEX CONCURRENTLY — they build
--   in the background without locking reads or writes.
--   Run outside a transaction (no BEGIN/COMMIT wrapper needed).
--
--   HNSW indexes are built synchronously (no CONCURRENTLY).
--   They may take 30–120 s on large tables. Run during low
--   traffic or a maintenance window.
--
-- SAFE TO RE-RUN: every statement uses IF NOT EXISTS.
-- ============================================================


-- ============================================================
-- 1. gaps
--
-- Most heavily queried user table during analysis.
-- Every checkpoint scan does:
--   WHERE policy_id = :pid AND status = 'Open'
-- The compound index covers this in one lookup.
-- ============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gaps_policy_id
    ON gaps (policy_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gaps_framework_id
    ON gaps (framework_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gaps_control_id
    ON gaps (control_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gaps_status
    ON gaps (status);

-- Compound: covers the most common filter: policy_id + status = 'Open'
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_gaps_policy_status
    ON gaps (policy_id, status);


-- ============================================================
-- 2. compliance_results
--
-- Queried on every policy load and every analysis resume check.
-- The compound index covers:
--   WHERE policy_id = :pid AND framework_id = :fid
-- which is used to check if a framework was already analyzed
-- (the "skip already-done frameworks on resume" logic).
-- ============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_compliance_results_policy_id
    ON compliance_results (policy_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_compliance_results_framework_id
    ON compliance_results (framework_id);

-- Compound: covers the "already analyzed?" resume-skip lookup
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_compliance_results_policy_framework
    ON compliance_results (policy_id, framework_id);


-- ============================================================
-- 3. mapping_reviews
--
-- Written in bulk during analysis (one row per control per policy),
-- then read back during gap generation and explainability queries.
-- ============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mapping_reviews_policy_id
    ON mapping_reviews (policy_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mapping_reviews_control_id
    ON mapping_reviews (control_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mapping_reviews_framework_id
    ON mapping_reviews (framework_id);

-- Compound: covers the common "all mappings for a policy + framework" fetch
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_mapping_reviews_policy_framework
    ON mapping_reviews (policy_id, framework_id);


-- ============================================================
-- 4. ai_insights
--
-- Filtered by policy_id on every policy detail page load.
-- ============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ai_insights_policy_id
    ON ai_insights (policy_id);

-- Compound: covers insight-type-filtered queries (e.g. fetch only 'risk' insights)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_ai_insights_policy_type
    ON ai_insights (policy_id, insight_type);


-- ============================================================
-- 5. reports
--
-- Filtered by policy_id when loading the policy detail view.
-- Sorted by generated_at DESC on the reports dashboard.
-- ============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reports_policy_id
    ON reports (policy_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_reports_generated_at
    ON reports (generated_at DESC);


-- ============================================================
-- 6. audit_logs
--
-- Three common query patterns:
--   a) Actor timeline:   WHERE actor_id = :uid ORDER BY timestamp DESC
--   b) Target history:   WHERE target_type = :t AND target_id = :id
--   c) Recent activity:  ORDER BY timestamp DESC LIMIT N
-- ============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_actor_id
    ON audit_logs (actor_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_timestamp
    ON audit_logs (timestamp DESC);

-- Compound: covers target-scoped audit history (e.g. all events on policy X)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_audit_logs_target
    ON audit_logs (target_type, target_id);


-- ============================================================
-- 7. control_library
--
-- Queried by control_code in the gap-saving loop inside
-- checkpoint_analyzer.py — once per control per analysis run.
-- Without this index, every gap creation does a full scan
-- of control_library to find the title.
--
-- Note: framework_id index already exists (set via index=True
-- in models.py:120). The compound index below supersedes it
-- for dual-filter queries (framework_id AND control_code).
-- ============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_control_library_control_code
    ON control_library (control_code);

-- Compound: covers the common lookup (framework_id, control_code)
-- used in checkpoint_analyzer and framework_loader joins.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_control_library_fw_code
    ON control_library (framework_id, control_code);


-- ============================================================
-- 8. policies
--
-- Dashboard queries filter by owner_id + status.
-- The compound index covers the user's "my policies" view.
-- ============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_policies_status
    ON policies (status);

-- Compound: covers user-scoped dashboard: WHERE owner_id = :uid
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_policies_owner_status
    ON policies (owner_id, status);


-- ============================================================
-- 9. policy_chunks — B-tree indexes
--
-- policy_id: used in DELETE (on policy removal) and in the
--   source-attribution backfill query.
-- policy_version_id: used in version-specific chunk deletion
--   (delete_policy_chunks with policy_version_id param).
-- ============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_policy_chunks_policy_id
    ON policy_chunks (policy_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_policy_chunks_version_id
    ON policy_chunks (policy_version_id);


-- ============================================================
-- 10. framework_chunks — B-tree index
--
-- framework_id: used in DELETE (atomic swap on re-upload)
--   and in SELECT ... ORDER BY chunk_index for text reassembly.
-- ============================================================

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_framework_chunks_framework_id
    ON framework_chunks (framework_id);


-- ============================================================
-- 11. HNSW vector indexes
--
-- The <=> (cosine distance) operator used in similarity searches
-- currently triggers exact full-table scans.
-- HNSW (Hierarchical Navigable Small World) replaces this with
-- approximate nearest-neighbour search: O(log n) instead of O(n).
--
-- Parameters chosen for a compliance-document workload:
--   m = 16             connections per layer (pgvector default)
--   ef_construction = 64  index build quality (pgvector default)
--
-- These run SYNCHRONOUSLY (no CONCURRENTLY support for HNSW).
-- Expect 30–120 s per table depending on row count.
-- Run during low-traffic period or scheduled maintenance.
--
-- Requires: pgvector extension installed (already in use).
-- ============================================================

-- Vector similarity on uploaded policy document chunks
CREATE INDEX IF NOT EXISTS idx_policy_chunks_embedding_hnsw
    ON policy_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Vector similarity on framework reference document chunks
CREATE INDEX IF NOT EXISTS idx_framework_chunks_embedding_hnsw
    ON framework_chunks
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);


-- ============================================================
-- VERIFICATION
--
-- After running, confirm all indexes exist:
-- ============================================================

/*
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND tablename IN (
      'gaps', 'compliance_results', 'mapping_reviews',
      'ai_insights', 'reports', 'audit_logs',
      'control_library', 'policies',
      'policy_chunks', 'framework_chunks'
  )
ORDER BY tablename, indexname;
*/
