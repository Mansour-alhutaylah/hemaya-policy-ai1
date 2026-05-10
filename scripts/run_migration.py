"""
run_migration.py
Execute a SQL migration file against DATABASE_URL without needing psql.

Usage (from repo root):
    DATABASE_URL=postgresql://... python scripts/run_migration.py scripts/migration_sacs002_cache.sql
    DATABASE_URL=postgresql://... python scripts/run_migration.py scripts/migration_indexes.sql

The script splits the file on semicolons, skipping blank statements and
block comments, then executes each statement individually so that DDL
errors (e.g. constraint already exists) are reported per-statement rather
than aborting the entire file.
"""

import os
import re
import sys
from pathlib import Path


def _split_statements(sql: str) -> list[str]:
    """
    Split SQL on semicolons while respecting:
      - single-quoted strings
      - double-dollar-quoted blocks ($$...$$)
      - block comments (/* ... */)
      - line comments (-- ...)
    Returns non-empty statements only.
    """
    stmts = []
    current: list[str] = []
    i = 0
    n = len(sql)
    in_single_quote = False
    in_dollar_quote = False

    while i < n:
        ch = sql[i]

        # Line comment — skip to end of line
        if not in_single_quote and not in_dollar_quote and ch == "-" and i + 1 < n and sql[i + 1] == "-":
            end = sql.find("\n", i)
            i = end + 1 if end != -1 else n
            continue

        # Block comment — skip to */
        if not in_single_quote and not in_dollar_quote and ch == "/" and i + 1 < n and sql[i + 1] == "*":
            end = sql.find("*/", i + 2)
            i = end + 2 if end != -1 else n
            continue

        # Dollar-quoting toggle
        if not in_single_quote and ch == "$":
            m = re.match(r"\$([^$]*)\$", sql[i:])
            if m:
                tag = m.group(0)
                if not in_dollar_quote:
                    in_dollar_quote = True
                    current.append(sql[i:i + len(tag)])
                    i += len(tag)
                    continue
                else:
                    # Check if this closing tag matches the opening
                    in_dollar_quote = False
                    current.append(sql[i:i + len(tag)])
                    i += len(tag)
                    continue

        # Single-quote toggle
        if ch == "'" and not in_dollar_quote:
            in_single_quote = not in_single_quote

        # Statement terminator
        if ch == ";" and not in_single_quote and not in_dollar_quote:
            stmt = "".join(current).strip()
            if stmt:
                stmts.append(stmt)
            current = []
            i += 1
            continue

        current.append(ch)
        i += 1

    # Trailing statement without semicolon
    stmt = "".join(current).strip()
    if stmt:
        stmts.append(stmt)

    return stmts


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/run_migration.py <sql_file>")
        sys.exit(1)

    sql_file = Path(sys.argv[1])
    if not sql_file.exists():
        print(f"ERROR: file not found: {sql_file}")
        sys.exit(1)

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        # Try loading from .env in the repo root
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            try:
                from dotenv import load_dotenv
                load_dotenv(env_path)
                database_url = os.getenv("DATABASE_URL", "")
                if database_url:
                    print("Loaded DATABASE_URL from .env")
            except ImportError:
                pass
    if not database_url:
        print("ERROR: DATABASE_URL not set. Export it or add it to .env")
        sys.exit(1)

    # Supabase / Heroku may give postgres:// — psycopg2 needs postgresql://
    database_url = database_url.replace("postgres://", "postgresql://", 1)

    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    print(f"Connecting to database...")
    try:
        conn = psycopg2.connect(database_url, sslmode="require", connect_timeout=30)
    except Exception as e:
        print(f"ERROR: could not connect: {e}")
        sys.exit(1)
    conn.autocommit = False
    print(f"Connected.")

    sql = sql_file.read_text(encoding="utf-8")
    statements = _split_statements(sql)
    print(f"Executing {len(statements)} statement(s) from {sql_file.name}...\n")

    ok = 0
    skipped = 0
    failed = 0

    for idx, stmt in enumerate(statements, 1):
        # Print first 80 chars as a progress label
        label = stmt[:80].replace("\n", " ")
        print(f"  [{idx}/{len(statements)}] {label}...")
        cur = conn.cursor()
        try:
            cur.execute(stmt)
            conn.commit()
            print(f"           OK")
            ok += 1
        except psycopg2.errors.DuplicateObject as e:
            conn.rollback()
            print(f"           SKIPPED (already exists): {e.pgerror.strip()}")
            skipped += 1
        except psycopg2.errors.DuplicateTable as e:
            conn.rollback()
            print(f"           SKIPPED (table exists): {e.pgerror.strip()}")
            skipped += 1
        except Exception as e:
            conn.rollback()
            print(f"           FAILED: {e}")
            failed += 1
        finally:
            cur.close()

    conn.close()

    print(f"\n{'='*50}")
    print(f"Done: {ok} OK  |  {skipped} skipped  |  {failed} failed")
    if failed:
        print("One or more statements failed. Review the errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
