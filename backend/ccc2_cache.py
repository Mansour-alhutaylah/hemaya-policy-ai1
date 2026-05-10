"""
CCC-2:2024 verification cache utility.
Mirrors sacs002_cache.py — same table schema, separate table and stats.

Table: ccc2_verification_cache
TTL:   30 days (refreshed on cache hit re-analysis)
"""

import time
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from threading import Lock

from sqlalchemy import text as _sql

TABLE = "ccc2_verification_cache"
CACHE_TTL_DAYS = 30


@dataclass
class _Stats:
    cache_hits:      int = 0
    cache_misses:    int = 0
    write_ok:        int = 0
    write_failures:  int = 0
    lookup_failures: int = 0
    total_lookup_ms: float = 0.0
    _lock: Lock = field(default_factory=Lock, compare=False, repr=False)

    @property
    def hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total else 0.0

    @property
    def avg_lookup_ms(self) -> float:
        total = self.cache_hits + self.cache_misses
        return self.total_lookup_ms / total if total else 0.0


_stats = _Stats()


def _safe_rollback(db) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def build_cache_key(
    control_code: str,
    policy_hash: str,
    prompt_version: str,
    model: str,
    retrieval_floor: float,
    grounding_version: str,
    grounding_sim: float,
) -> str:
    return (
        f"CCC2|{control_code}|{policy_hash}|{prompt_version}|{model}"
        f"|floor={retrieval_floor:.3f}|grounding={grounding_version}|gsim={grounding_sim:.3f}"
    )


def lookup(db, cache_key: str) -> dict | None:
    t0 = time.monotonic()
    try:
        row = db.execute(_sql(f"""
            SELECT result FROM {TABLE}
            WHERE cache_key = :ck
              AND (ttl_expiration IS NULL OR ttl_expiration > NOW())
        """), {"ck": cache_key}).fetchone()
        elapsed = (time.monotonic() - t0) * 1000
        with _stats._lock:
            _stats.total_lookup_ms += elapsed
            if row:
                _stats.cache_hits += 1
            else:
                _stats.cache_misses += 1
        if row:
            val = row[0]
            if isinstance(val, dict):
                return val
            if isinstance(val, str):
                return json.loads(val)
            return val
        return None
    except Exception as e:
        _safe_rollback(db)
        with _stats._lock:
            _stats.lookup_failures += 1
            _stats.cache_misses += 1
        print(f"  [CCC2_CACHE] lookup error (non-fatal): {e}")
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
    ttl = datetime.now(timezone.utc) + timedelta(days=CACHE_TTL_DAYS)
    try:
        db.execute(_sql(f"""
            INSERT INTO {TABLE}
                (cache_key, control_code, policy_hash, prompt_version, model,
                 result, created_at, updated_at, ttl_expiration)
            VALUES
                (:ck, :cc, :ph, :pv, :mo,
                 CAST(:res AS jsonb), NOW(), NOW(), :ttl)
            ON CONFLICT (cache_key) DO UPDATE SET
                result         = EXCLUDED.result,
                updated_at     = NOW(),
                ttl_expiration = EXCLUDED.ttl_expiration
        """), {
            "ck":  cache_key,
            "cc":  control_code,
            "ph":  policy_hash,
            "pv":  prompt_version,
            "mo":  model,
            "res": json.dumps(result),
            "ttl": ttl,
        })
        db.commit()
        with _stats._lock:
            _stats.write_ok += 1
        return True
    except Exception as e:
        _safe_rollback(db)
        with _stats._lock:
            _stats.write_failures += 1
        print(f"  [CCC2_CACHE] write error (non-fatal): {e}")
        return False


def invalidate_policy(db, policy_hash: str) -> int:
    try:
        r = db.execute(_sql(f"DELETE FROM {TABLE} WHERE policy_hash = :ph"),
                       {"ph": policy_hash})
        db.commit()
        return r.rowcount
    except Exception as e:
        _safe_rollback(db)
        print(f"  [CCC2_CACHE] invalidate_policy error: {e}")
        return 0


def invalidate_prompt_version(db, prompt_version: str) -> int:
    try:
        r = db.execute(_sql(f"DELETE FROM {TABLE} WHERE prompt_version = :pv"),
                       {"pv": prompt_version})
        db.commit()
        return r.rowcount
    except Exception as e:
        _safe_rollback(db)
        print(f"  [CCC2_CACHE] invalidate_prompt_version error: {e}")
        return 0


def invalidate_all(db) -> int:
    try:
        r = db.execute(_sql(f"DELETE FROM {TABLE}"))
        db.commit()
        return r.rowcount
    except Exception as e:
        _safe_rollback(db)
        print(f"  [CCC2_CACHE] invalidate_all error: {e}")
        return 0


def purge_expired(db) -> int:
    try:
        r = db.execute(_sql(
            f"DELETE FROM {TABLE} WHERE ttl_expiration IS NOT NULL AND ttl_expiration <= NOW()"
        ))
        db.commit()
        return r.rowcount
    except Exception as e:
        _safe_rollback(db)
        print(f"  [CCC2_CACHE] purge_expired error: {e}")
        return 0


def get_stats(db=None) -> dict:
    with _stats._lock:
        out = {
            "cache_hits":      _stats.cache_hits,
            "cache_misses":    _stats.cache_misses,
            "hit_rate":        _stats.hit_rate,
            "write_ok":        _stats.write_ok,
            "write_failures":  _stats.write_failures,
            "lookup_failures": _stats.lookup_failures,
            "avg_lookup_ms":   _stats.avg_lookup_ms,
        }
    if db is not None:
        try:
            row = db.execute(_sql(f"""
                SELECT
                    COUNT(*)                                          AS total,
                    COUNT(DISTINCT policy_hash)                       AS policies,
                    COUNT(*) FILTER (
                        WHERE ttl_expiration IS NOT NULL
                          AND ttl_expiration <= NOW()
                    )                                                 AS expired
                FROM {TABLE}
            """)).fetchone()
            out.update({
                "db_total_rows":        row[0],
                "db_distinct_policies": row[1],
                "db_expired_rows":      row[2],
            })
        except Exception:
            pass
    return out


def reset_process_stats() -> None:
    with _stats._lock:
        _stats.cache_hits      = 0
        _stats.cache_misses    = 0
        _stats.write_ok        = 0
        _stats.write_failures  = 0
        _stats.lookup_failures = 0
        _stats.total_lookup_ms = 0.0
