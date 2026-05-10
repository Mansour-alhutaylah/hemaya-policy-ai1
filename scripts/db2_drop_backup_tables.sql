-- ============================================================
-- Hemaya Policy AI — DB-2: drop migration backup tables
-- ============================================================
--
-- WHAT THIS DROPS
--   Three orphan tables left behind by Phase 1 / Phase 4 migration
--   work. The schema audit (code search across backend/ and src/)
--   confirmed zero references in any source file. They are listed
--   in scripts/production_cleanup.sql Section 16 only as DELETE
--   targets — never DROPped — so the empty husks have been sitting
--   in public for some time:
--
--     - public._phase1_dedupe_backup
--     - public._phase4_degenerate_backup
--     - public._phase4_orphan_backup
--
-- PRE-FLIGHT (do this BEFORE running)
--   1. Take a Supabase backup snapshot from the dashboard
--      (Project Settings → Database → Backups → Take new snapshot),
--      OR run pg_dump on the three tables specifically:
--
--      pg_dump -Fc \
--        --table=public._phase1_dedupe_backup \
--        --table=public._phase4_degenerate_backup \
--        --table=public._phase4_orphan_backup \
--        "$DATABASE_URL" > backups/db2-pre-drop-$(date +%F).dump
--
--   2. (Optional) Run the inventory query at the bottom of this
--      script first to confirm row counts; if every table is empty
--      the backup step is even cheaper.
--
-- HOW TO RUN
--   Paste the entire script into Supabase SQL Editor and Run.
--   (No CONCURRENTLY here — DROP TABLE works inside a transaction.)
--
-- ROLLBACK
--   pg_restore -d "$DATABASE_URL" backups/db2-pre-drop-<date>.dump
-- ============================================================


-- ── Inventory query (read-only) — uncomment to inspect first ──
-- SELECT
--     '_phase1_dedupe_backup'    AS tbl,
--     COUNT(*)                   AS rows
-- FROM public._phase1_dedupe_backup
-- UNION ALL
-- SELECT '_phase4_degenerate_backup', COUNT(*)
-- FROM public._phase4_degenerate_backup
-- UNION ALL
-- SELECT '_phase4_orphan_backup', COUNT(*)
-- FROM public._phase4_orphan_backup;


-- ── Drops — wrapped in a transaction so it's all-or-nothing ──
BEGIN;

DROP TABLE IF EXISTS public._phase1_dedupe_backup;
DROP TABLE IF EXISTS public._phase4_degenerate_backup;
DROP TABLE IF EXISTS public._phase4_orphan_backup;

COMMIT;


-- ============================================================
-- VERIFICATION
-- ============================================================
/*
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name LIKE '_phase%';
-- Expected: zero rows.
*/
