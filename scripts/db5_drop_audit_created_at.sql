-- ============================================================
-- Hemaya Policy AI — DB-5: drop unused audit_logs.created_at
-- ============================================================
--
-- WHAT THIS DROPS
--   audit_logs.created_at — a duplicate timestamp column. The
--   ORM (backend/models.py) defines only `timestamp`, and every
--   INSERT in the backend writes to `timestamp` (no-tz). The
--   `created_at` column is a leftover from an earlier schema
--   revision and is never written. Dropping it removes ~16 bytes
--   per row of dead storage and clarifies the schema.
--
-- PRE-FLIGHT (do this BEFORE running)
--   1. Take a Supabase backup snapshot. The whole audit_logs
--      table should be backed up because DROP COLUMN is not
--      reversible without restore.
--
--   2. Run Step A below as a read-only sanity check:
--        - If `non_null_count` is > 0, the column has historical
--          data we'd lose. Stop and decide whether to backfill
--          into `timestamp` first (Step B template, commented out).
--        - If `non_null_count` is 0, proceed straight to Step C.
--
-- HOW TO RUN
--   Paste into Supabase SQL Editor. The DROP COLUMN takes a brief
--   ACCESS EXCLUSIVE lock on audit_logs (~milliseconds for typical
--   sizes). If audit_logs is huge, schedule for a quiet window.
--
-- ROLLBACK
--   ALTER TABLE audit_logs ADD COLUMN created_at timestamptz;
--   (The historical values cannot be recovered without the backup.)
-- ============================================================


-- ── Step A: read-only sanity check ────────────────────────────
-- Run this FIRST. If it returns 0, proceed to Step C.
-- If it returns > 0, decide whether to backfill via Step B.
SELECT
    COUNT(*)                                  AS total_rows,
    COUNT(created_at)                         AS non_null_count,
    MIN(created_at)                           AS earliest,
    MAX(created_at)                           AS latest
FROM audit_logs;


-- ── Step B (OPTIONAL): backfill into `timestamp` ─────────────
-- Uncomment ONLY if Step A reports a non-zero non_null_count
-- AND those rows have a NULL `timestamp` (otherwise the
-- existing timestamp wins). This is paranoia; the codebase
-- has always written `timestamp`, so this should be a no-op.
--
-- UPDATE audit_logs
-- SET    timestamp = created_at
-- WHERE  timestamp IS NULL
--   AND  created_at IS NOT NULL;


-- ── Step C: drop the column ───────────────────────────────────
ALTER TABLE audit_logs DROP COLUMN IF EXISTS created_at;


-- ============================================================
-- VERIFICATION
-- ============================================================
/*
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name   = 'audit_logs'
ORDER BY ordinal_position;
-- Expected: no row with column_name = 'created_at'.
*/
