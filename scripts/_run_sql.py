"""Tiny SQL runner for the DB-* prep scripts.

Reads DATABASE_URL from .env, connects via SQLAlchemy, executes the
file passed on argv[1]. Modes:
    --autocommit       run each statement individually with autocommit
                       (required for CREATE INDEX CONCURRENTLY)
    (default)          run the whole file in one transaction

Splits on ';' at end of statement boundaries. Skips empty / comment-only
statements. Prints up to the first 30 result rows of each SELECT.

This is a one-shot helper, not a long-lived tool.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"


def load_env() -> str:
    text = ENV_PATH.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.strip().startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("DATABASE_URL not in .env")


_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")


def split_statements(sql: str) -> list[str]:
    """Strip block + line comments first, THEN split on `;` outside of
    $$-quoted blocks. Stripping comments before splitting keeps the
    splitter from being confused by a `;` inside a `--` comment line
    (which is real in our scripts). Good enough for the small,
    hand-written scripts in scripts/db*.sql; not meant for arbitrary
    SQL containing `--` inside string literals.
    """
    sql = _BLOCK_COMMENT.sub("", sql)
    sql = _LINE_COMMENT.sub("", sql)
    out: list[str] = []
    buf: list[str] = []
    in_dollar = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if not in_dollar and sql.startswith("$$", i):
            in_dollar = True
            buf.append("$$")
            i += 2
            continue
        if in_dollar and sql.startswith("$$", i):
            in_dollar = False
            buf.append("$$")
            i += 2
            continue
        if ch == ";" and not in_dollar:
            stmt = "".join(buf).strip()
            if stmt:
                out.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: _run_sql.py <path-to-sql> [--autocommit]")
        return 2
    path = Path(argv[1])
    autocommit = "--autocommit" in argv[2:]
    if not path.exists():
        print(f"missing: {path}")
        return 2

    db_url = load_env()
    # Mask password in any echoed line
    masked = re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", db_url)
    print(f"[run_sql] db = {masked}")
    print(f"[run_sql] file = {path}")
    print(f"[run_sql] mode = {'autocommit per-statement' if autocommit else 'single transaction'}")

    from sqlalchemy import create_engine, text
    engine = create_engine(db_url, future=True)

    sql = path.read_text(encoding="utf-8")
    statements = split_statements(sql)
    print(f"[run_sql] {len(statements)} statement(s) to run\n")

    if autocommit:
        # Each statement in its own autocommit context — needed for
        # CREATE INDEX CONCURRENTLY.
        for i, stmt in enumerate(statements, 1):
            preview = re.sub(r"\s+", " ", _LINE_COMMENT.sub("", stmt)).strip()[:120]
            print(f"--- [{i}/{len(statements)}] {preview} ...")
            with engine.connect() as conn:
                conn = conn.execution_options(isolation_level="AUTOCOMMIT")
                result = conn.execute(text(stmt))
                if result.returns_rows:
                    rows = result.fetchmany(30)
                    cols = list(result.keys())
                    print("    columns:", cols)
                    for r in rows:
                        print("   ", dict(zip(cols, r)))
            print(f"    OK")
    else:
        with engine.begin() as conn:  # one transaction
            for i, stmt in enumerate(statements, 1):
                preview = re.sub(r"\s+", " ", _LINE_COMMENT.sub("", stmt)).strip()[:120]
                print(f"--- [{i}/{len(statements)}] {preview} ...")
                result = conn.execute(text(stmt))
                if result.returns_rows:
                    rows = result.fetchmany(30)
                    cols = list(result.keys())
                    print("    columns:", cols)
                    for r in rows:
                        print("   ", dict(zip(cols, r)))
                print(f"    OK")
        print("\n[run_sql] committed")

    print("\n[run_sql] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
