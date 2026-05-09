"""Read-only DB reconnaissance for the Phase 10 live smoke.

Prints:
  - candidate MID-style ECC-2 policies (must have policy_chunks rows)
  - candidate SACS-002-style policies
  - prior compliance_results / policy_ecc_assessments / sacs002_assessments
    counts per candidate (BEFORE snapshot baseline)
  - any existing ecc2_verification_cache rows (key prefixes only — we don't
    need to delete them because grounding=v2 segregates the new run)

NO writes. NO analysis. Just inspection.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # type: ignore

load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, text  # noqa: E402

DB_URL = os.getenv("DATABASE_URL")
assert DB_URL, "DATABASE_URL not set"
engine = create_engine(DB_URL, pool_pre_ping=True)


def section(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main():
    with engine.connect() as conn:
        # Frameworks present
        section("Frameworks")
        for row in conn.execute(text(
            "SELECT id, name FROM frameworks ORDER BY name"
        )):
            print(f"  {row.id} | {row.name}")

        # Find candidate policies with chunks
        section("Candidate policies (has policy_chunks)")
        rows = conn.execute(text("""
            SELECT p.id, p.file_name, p.framework_code, p.status,
                   (SELECT COUNT(*) FROM policy_chunks pc WHERE pc.policy_id = p.id) AS chunks,
                   (SELECT COUNT(*) FROM compliance_results cr WHERE cr.policy_id = p.id) AS cr_rows,
                   (SELECT COUNT(*) FROM policy_ecc_assessments e WHERE e.policy_id::text = p.id::text) AS ecc_rows
            FROM policies p
            WHERE p.id IN (SELECT DISTINCT policy_id FROM policy_chunks)
            ORDER BY chunks DESC
            LIMIT 30
        """)).fetchall()
        for r in rows:
            print(f"  {r.id} | {(r.file_name or '')[:50]:50} | fc={r.framework_code or '-':10} | "
                  f"st={r.status or '-':10} | chunks={r.chunks:3d} | cr={r.cr_rows:3d} | ecc={r.ecc_rows:3d}")

        # ECC-2 assessments table
        section("policy_ecc_assessments per policy")
        for r in conn.execute(text("""
            SELECT policy_id, COUNT(*) AS n
            FROM policy_ecc_assessments
            GROUP BY policy_id
            ORDER BY n DESC
            LIMIT 10
        """)):
            print(f"  {r.policy_id} | rows={r.n}")

        # SACS-002 assessments
        section("SACS-002 candidate tables")
        for r in conn.execute(text("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema='public' AND table_name ILIKE '%sacs%'
            ORDER BY table_name
        """)):
            print(f"  {r.table_name}")

        section("compliance_results for SACS-002 policy 41645d6e-...")
        for r in conn.execute(text("""
            SELECT framework_id, COUNT(*) AS n
            FROM compliance_results
            WHERE policy_id::text = '41645d6e-802f-4bfd-bdc2-bad771602f07'
            GROUP BY framework_id
        """)):
            print(f"  framework_id={r.framework_id} | rows={r.n}")
        for r in conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='compliance_results' ORDER BY ordinal_position
        """)):
            print(f"  col: {r.column_name}")

        section("MID ECC-2 BEFORE status distribution (policy 16b0987f-...)")
        for r in conn.execute(text("""
            SELECT compliance_status, COUNT(*) AS n
            FROM policy_ecc_assessments
            WHERE policy_id::text = '16b0987f-0c45-4a21-b155-3276b3442dd2'
              AND framework_id ILIKE '%ECC%'
            GROUP BY compliance_status ORDER BY n DESC
        """)):
            print(f"  {r.compliance_status} | {r.n}")

        section("SACS-002 policy 41645d6e-... rows in policy_ecc_assessments by framework_id")
        for r in conn.execute(text("""
            SELECT framework_id, compliance_status, COUNT(*) AS n
            FROM policy_ecc_assessments
            WHERE policy_id::text = '41645d6e-802f-4bfd-bdc2-bad771602f07'
            GROUP BY framework_id, compliance_status
            ORDER BY framework_id, n DESC
        """)):
            print(f"  fw={r.framework_id:20} st={r.compliance_status} n={r.n}")

        section("Distinct framework_id values in policy_ecc_assessments")
        for r in conn.execute(text("""
            SELECT framework_id, COUNT(DISTINCT policy_id) AS policies, COUNT(*) AS rows
            FROM policy_ecc_assessments GROUP BY framework_id ORDER BY rows DESC
        """)):
            print(f"  fw={r.framework_id} | policies={r.policies} | rows={r.rows}")

        # ECC-2 verification cache footprint
        section("ecc2_verification_cache footprint")
        try:
            r = conn.execute(text(
                "SELECT COUNT(*) AS n FROM ecc2_verification_cache"
            )).fetchone()
            print(f"  total rows: {r.n}")
        except Exception as e:
            print(f"  (error: {e})")


if __name__ == "__main__":
    main()
