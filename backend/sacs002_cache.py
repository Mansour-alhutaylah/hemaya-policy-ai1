"""
sacs002_cache.py
Production-grade caching layer for SACS-002 verification results.

Architecture note
-----------------
This module is the single authoritative source for all cache I/O in the
SACS-002 pipeline.  sacs002_analyzer.py imports and calls these helpers;
it does not touch sacs002_verification_cache directly.

Cache key invariants
--------------------
The SHA-256 key encodes every input that affects the GPT verdict:
  control_code      — which control is being assessed
  policy_hash       — which policy document (first 16 hex chars of SHA-256(text))
  prompt_version    — SACS002_PROMPT_VERSION in sacs002_analyzer.py
  model             — SACS002_MODEL in sacs002_analyzer.py
  retrieval_floor   — RAG_MIN_RELEVANCE_SCORE (float, 3 d.p.)
  grounding_version — GROUNDING_VERSION in checkpoint_analyzer.py
  grounding_sim     — GROUNDING_MIN_SIMILARITY (float, 3 d.p.)

Bumping SACS002_PROMPT_VERSION produces a new key for every entry, so
stale rows become unreachable with no DELETE required.

TTL
---
Each write sets ttl_expiration = NOW() + CACHE_TTL_DAYS days.
Lookups filter: ttl_expiration IS NULL OR ttl_expiration > NOW().
purge_expired() hard-deletes truly stale rows for maintenance.

Concurrency safety
------------------
INSERT … ON CONFLICT (cache_key) DO UPDATE is an atomic upsert so
concurrent writers for the same key do not produce duplicate rows.
The PRIMARY KEY on cache_key is the sole uniqueness guard.

Observability
-------------
A process-level _Stats singleton counts hits, misses, write_ok,
write_failures, and lookup_failures with a threading.Lock.
get_stats(db) adds a live DB row-count query when db is supplied.

Error handling
--------------
Every DB operation is wrapped in try/except.  On any error the
connection is rolled back so the PostgreSQL transaction is not left
in an aborted state (which would cause all subsequent queries on the
same session to fail with "current transaction is aborted").
Cache failures are always non-fatal — the caller continues with a
fresh GPT call.
"""

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text as sql_text

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TABLE = "sacs002_verification_cache"
CACHE_TTL_DAYS = 30


# ---------------------------------------------------------------------------
# Process-level statistics
# ---------------------------------------------------------------------------

@dataclass
class _Stats:
    hits:           int   = 0
    misses:         int   = 0
    write_ok:       int   = 0
    write_fail:     int   = 0
    lookup_fail:    int   = 0
    total_lookup_ms: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


_stats = _Stats()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_cache_key(
    control_code: str,
    policy_hash: str,
    prompt_version: str,
    model: str,
    retrieval_floor: float,
    grounding_version: str,
    grounding_sim: float,
) -> str:
    """Return a deterministic 64-char hex cache key for the given inputs."""
    raw = (
        f"SACS002|{control_code}|{policy_hash}|"
        f"{prompt_version}|{model}|"
        f"floor={retrieval_floor:.3f}|"
        f"grounding={grounding_version}|"
        f"gsim={grounding_sim:.3f}"
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def lookup(db, cache_key: str) -> Optional[dict]:
    """
    Look up a cache entry by key.

    Returns the cached result dict on hit, or None on miss / error / expiry.
    Never raises — any exception rolls back the connection and returns None.
    """
    t0 = time.monotonic()
    try:
        row = db.execute(
            sql_text(
                f"SELECT result FROM {TABLE} "
                f"WHERE cache_key = :ck "
                f"  AND (ttl_expiration IS NULL OR ttl_expiration > NOW())"
            ),
            {"ck": cache_key},
        ).fetchone()

        elapsed_ms = (time.monotonic() - t0) * 1000
        with _stats._lock:
            _stats.total_lookup_ms += elapsed_ms

        if row is None:
            with _stats._lock:
                _stats.misses += 1
            return None

        result = row[0]
        if isinstance(result, str):
            result = json.loads(result)

        with _stats._lock:
            _stats.hits += 1
        return result

    except Exception as exc:
        # Any DB error leaves the PostgreSQL transaction in an aborted state.
        # Rollback here so that every subsequent query in this session works.
        _record_lookup_failure(exc)
        _safe_rollback(db)
        return None


def write(
    db,
    cache_key: str,
    control_code: str,
    policy_hash: str,
    prompt_version: str,
    model: str,
    result: dict,
) -> bool:
    """
    Upsert a result into the cache.

    Uses ON CONFLICT DO UPDATE so:
      - concurrent inserts for the same key are safe (no duplicate rows)
      - re-analysis of the same (policy, control, prompt) refreshes the TTL

    Returns True on success, False on any error (after rollback).
    Never raises.
    """
    try:
        db.execute(
            sql_text(f"""
                INSERT INTO {TABLE}
                    (cache_key, control_code, policy_hash, prompt_version,
                     model, result, ttl_expiration)
                VALUES
                    (:ck, :cc, :ph, :pv, :md, CAST(:res AS JSONB),
                     NOW() + INTERVAL '{CACHE_TTL_DAYS} days')
                ON CONFLICT (cache_key) DO UPDATE
                    SET result         = EXCLUDED.result,
                        updated_at     = NOW(),
                        ttl_expiration = EXCLUDED.ttl_expiration
            """),
            {
                "ck":  cache_key,
                "cc":  control_code,
                "ph":  policy_hash,
                "pv":  prompt_version,
                "md":  model,
                "res": json.dumps(result, default=str),
            },
        )
        db.commit()
        with _stats._lock:
            _stats.write_ok += 1
        return True

    except Exception as exc:
        with _stats._lock:
            _stats.write_fail += 1
        print(f"[sacs002_cache] write failed ({type(exc).__name__}): {exc}")
        _safe_rollback(db)
        return False


def invalidate_policy(db, policy_hash: str) -> int:
    """
    Delete all cache entries for a given policy hash.

    Call this when a policy is re-uploaded or its text changes so that
    the next analysis re-runs through GPT instead of serving stale results.
    Returns the number of rows deleted (0 on error).
    """
    try:
        res = db.execute(
            sql_text(f"DELETE FROM {TABLE} WHERE policy_hash = :ph"),
            {"ph": policy_hash},
        )
        db.commit()
        n = res.rowcount
        print(f"[sacs002_cache] invalidated {n} entries for policy_hash={policy_hash}")
        return n
    except Exception as exc:
        print(f"[sacs002_cache] invalidate_policy failed: {exc}")
        _safe_rollback(db)
        return 0


def invalidate_prompt_version(db, prompt_version: str) -> int:
    """
    Delete all cache entries for a given prompt version.

    Use this when SACS002_PROMPT_VERSION is bumped but you want to
    immediately purge the now-unreachable old rows (saves storage).
    Returns the number of rows deleted (0 on error).
    """
    try:
        res = db.execute(
            sql_text(f"DELETE FROM {TABLE} WHERE prompt_version = :pv"),
            {"pv": prompt_version},
        )
        db.commit()
        n = res.rowcount
        print(f"[sacs002_cache] invalidated {n} entries for prompt_version={prompt_version}")
        return n
    except Exception as exc:
        print(f"[sacs002_cache] invalidate_prompt_version failed: {exc}")
        _safe_rollback(db)
        return 0


def invalidate_all(db) -> int:
    """
    Delete every row in the cache table.

    Reserved for use when the scoring algorithm changes in a way that
    does not fit into a prompt_version bump (e.g. action_coverage thresholds).
    Returns the number of rows deleted (0 on error).
    """
    try:
        res = db.execute(sql_text(f"DELETE FROM {TABLE}"))
        db.commit()
        n = res.rowcount
        print(f"[sacs002_cache] global invalidation: {n} entries deleted")
        return n
    except Exception as exc:
        print(f"[sacs002_cache] invalidate_all failed: {exc}")
        _safe_rollback(db)
        return 0


def purge_expired(db) -> int:
    """
    Hard-delete all rows whose TTL has passed.

    Safe to run as a periodic maintenance task (e.g. daily cron).
    Returns the number of rows deleted (0 on error).
    """
    try:
        res = db.execute(sql_text(
            f"DELETE FROM {TABLE} "
            f"WHERE ttl_expiration IS NOT NULL AND ttl_expiration < NOW()"
        ))
        db.commit()
        n = res.rowcount
        print(f"[sacs002_cache] purged {n} expired entries")
        return n
    except Exception as exc:
        print(f"[sacs002_cache] purge_expired failed: {exc}")
        _safe_rollback(db)
        return 0


def get_stats(db=None) -> dict:
    """
    Return cache performance statistics.

    Process-level counters are always included.  When db is supplied,
    also queries the DB for row-level aggregates (total rows, distinct
    policies, expired row count, oldest/newest entry).

    Designed to be called at the end of run_sacs002_analysis() and
    surfaced in /api/cache-stats or printed to logs.
    """
    with _stats._lock:
        total_lookups = _stats.hits + _stats.misses
        hit_rate      = (_stats.hits / total_lookups) if total_lookups > 0 else 0.0
        avg_lookup_ms = (
            _stats.total_lookup_ms / total_lookups
        ) if total_lookups > 0 else 0.0

        base: dict = {
            "cache_hits":       _stats.hits,
            "cache_misses":     _stats.misses,
            "hit_rate":         round(hit_rate, 4),
            "write_ok":         _stats.write_ok,
            "write_failures":   _stats.write_fail,
            "lookup_failures":  _stats.lookup_fail,
            "avg_lookup_ms":    round(avg_lookup_ms, 2),
        }

    if db is not None:
        try:
            row = db.execute(sql_text(f"""
                SELECT
                    COUNT(*)                                         AS total_rows,
                    COUNT(DISTINCT policy_hash)                      AS distinct_policies,
                    COUNT(DISTINCT control_code)                     AS distinct_controls,
                    COUNT(*) FILTER (
                        WHERE ttl_expiration IS NOT NULL
                          AND ttl_expiration < NOW()
                    )                                                AS expired_rows,
                    MIN(created_at)                                  AS oldest_entry,
                    MAX(updated_at)                                  AS newest_update
                FROM {TABLE}
            """)).fetchone()
            if row:
                base.update({
                    "db_total_rows":         row[0],
                    "db_distinct_policies":  row[1],
                    "db_distinct_controls":  row[2],
                    "db_expired_rows":       row[3],
                    "db_oldest_entry":       str(row[4]) if row[4] else None,
                    "db_newest_update":      str(row[5]) if row[5] else None,
                })
        except Exception:
            pass

    return base


def reset_process_stats() -> None:
    """
    Zero all process-level counters.

    Useful in tests that want a clean slate between runs.
    Not safe to call during an active analysis run.
    """
    with _stats._lock:
        _stats.hits           = 0
        _stats.misses         = 0
        _stats.write_ok       = 0
        _stats.write_fail     = 0
        _stats.lookup_fail    = 0
        _stats.total_lookup_ms = 0.0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _record_lookup_failure(exc: Exception) -> None:
    with _stats._lock:
        _stats.misses      += 1
        _stats.lookup_fail += 1
    print(f"[sacs002_cache] lookup failed ({type(exc).__name__}): {exc}")


def _safe_rollback(db) -> None:
    """Best-effort rollback — swallowed if the connection is already closed."""
    try:
        db.rollback()
    except Exception:
        pass
