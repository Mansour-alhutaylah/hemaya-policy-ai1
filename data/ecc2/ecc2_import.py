"""
ECC-2:2024 Framework Import Script
Loads all three layers from JSON files into PostgreSQL/Supabase.

Usage:
    DATABASE_URL=postgresql://... python data/ecc2/ecc2_import.py
    DATABASE_URL=postgresql://... python data/ecc2/ecc2_import.py --force
    DATABASE_URL=postgresql://... python data/ecc2/ecc2_import.py --dry-run

--force     : Deletes existing ECC-2:2024 rows before import
--dry-run   : Validates JSON structure without touching the database
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).parent
FRAMEWORK_ID = "ECC-2:2024"

L1_FILE = BASE_DIR / "ecc2_layer1_official.json"
L2_FILE = BASE_DIR / "ecc2_layer2_metadata.json"
L3_FILE = BASE_DIR / "ecc2_layer3_ai_checkpoints.json"


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def flatten_layer1(data: dict) -> list[dict]:
    """Flatten nested domain/subdomain/control structure into a flat list of rows.

    Layer 1 JSON nests subcontrols inside their parent's 'subcontrols' array.
    This function walks both levels to produce a single flat list.
    """
    rows = []

    def _append_control(control, domain, subdomain, parent_code=None):
        rows.append({
            "framework_id": FRAMEWORK_ID,
            "domain_code": domain["domain_code"],
            "domain_name": domain["domain_name"],
            "subdomain_code": subdomain["subdomain_code"],
            "subdomain_name": subdomain["subdomain_name"],
            "control_code": control["control_code"],
            "control_type": control["control_type"],
            "control_text": control["control_text"],
            "parent_control_code": control.get("parent_control_code") or parent_code,
            "is_ecc2_new": control.get("is_ecc2_new", False),
            "ecc2_change_note": control.get("ecc2_change") or control.get("ecc2_change_note"),
            "source_page": control.get("source_page"),
        })
        for subcontrol in control.get("subcontrols", []):
            _append_control(subcontrol, domain, subdomain, control["control_code"])

    for domain in data["domains"]:
        for subdomain in domain["subdomains"]:
            for control in subdomain["controls"]:
                _append_control(control, domain, subdomain)

    return rows


def import_layer1(conn, rows: list[dict], dry_run: bool) -> int:
    if dry_run:
        print(f"[DRY RUN] Layer 1: would insert {len(rows)} control rows")
        return len(rows)

    from sqlalchemy import text
    inserted = 0
    for row in rows:
        conn.execute(text("""
            INSERT INTO ecc_framework (
                id, framework_id, domain_code, domain_name,
                subdomain_code, subdomain_name, control_code,
                control_type, control_text, parent_control_code,
                is_ecc2_new, ecc2_change_note, source_page
            ) VALUES (
                :id, :framework_id, :domain_code, :domain_name,
                :subdomain_code, :subdomain_name, :control_code,
                :control_type, :control_text, :parent_control_code,
                :is_ecc2_new, :ecc2_change_note, :source_page
            )
            ON CONFLICT (framework_id, control_code) DO UPDATE SET
                control_text       = EXCLUDED.control_text,
                is_ecc2_new        = EXCLUDED.is_ecc2_new,
                ecc2_change_note   = EXCLUDED.ecc2_change_note,
                source_page        = EXCLUDED.source_page
        """), {**row, "id": str(uuid.uuid4())})
        inserted += 1
    return inserted


def import_layer2(conn, data: dict, dry_run: bool) -> int:
    rows = data["controls_metadata"]
    if dry_run:
        print(f"[DRY RUN] Layer 2: would insert {len(rows)} metadata rows")
        return len(rows)

    from sqlalchemy import text
    inserted = 0
    for row in rows:
        conn.execute(text("""
            INSERT INTO ecc_compliance_metadata (
                id, framework_id, control_code, applicability,
                applicability_note, responsible_party, frequency,
                ecc_version_introduced, change_from_ecc1, deleted_in_ecc2
            ) VALUES (
                :id, :framework_id, :control_code, :applicability,
                :applicability_note, :responsible_party, :frequency,
                :ecc_version_introduced, :change_from_ecc1, :deleted_in_ecc2
            )
            ON CONFLICT (framework_id, control_code) DO UPDATE SET
                applicability          = EXCLUDED.applicability,
                applicability_note     = EXCLUDED.applicability_note,
                responsible_party      = EXCLUDED.responsible_party,
                frequency              = EXCLUDED.frequency,
                ecc_version_introduced = EXCLUDED.ecc_version_introduced,
                change_from_ecc1       = EXCLUDED.change_from_ecc1,
                deleted_in_ecc2        = EXCLUDED.deleted_in_ecc2
        """), {
            "id": str(uuid.uuid4()),
            "framework_id": FRAMEWORK_ID,
            "control_code": row["control_id"],
            "applicability": row.get("applicability"),
            "applicability_note": row.get("applicability_note"),
            "responsible_party": row.get("responsible_party"),
            "frequency": row.get("frequency"),
            "ecc_version_introduced": row.get("ecc_version_introduced"),
            "change_from_ecc1": row.get("change_from_ecc1"),
            "deleted_in_ecc2": row.get("deleted_in_ecc2", False),
        })
        inserted += 1
    return inserted


def import_layer3(conn, data: dict, dry_run: bool) -> int:
    checkpoints = data["checkpoints"]
    model_version = data.get("model_version", "unknown")
    generated_at = data.get("generated_at", datetime.now(timezone.utc).isoformat())

    if dry_run:
        print(f"[DRY RUN] Layer 3: would insert {len(checkpoints)} AI checkpoint rows")
        return len(checkpoints)

    from sqlalchemy import text
    inserted = 0
    for cp in checkpoints:
        conn.execute(text("""
            INSERT INTO ecc_ai_checkpoints (
                id, framework_id, control_code, ai_generated,
                model_version, generated_at,
                audit_questions, suggested_evidence,
                indicators_of_implementation, maturity_signals,
                possible_documents, possible_technical_evidence
            ) VALUES (
                :id, :framework_id, :control_code, TRUE,
                :model_version, :generated_at,
                CAST(:audit_questions AS jsonb),
                CAST(:suggested_evidence AS jsonb),
                CAST(:indicators_of_implementation AS jsonb),
                CAST(:maturity_signals AS jsonb),
                CAST(:possible_documents AS jsonb),
                CAST(:possible_technical_evidence AS jsonb)
            )
            ON CONFLICT DO NOTHING
        """), {
            "id": str(uuid.uuid4()),
            "framework_id": FRAMEWORK_ID,
            "control_code": cp["control_id"],
            "model_version": model_version,
            "generated_at": generated_at,
            "audit_questions": json.dumps(cp.get("audit_questions", [])),
            "suggested_evidence": json.dumps(cp.get("suggested_evidence", [])),
            "indicators_of_implementation": json.dumps(cp.get("indicators_of_implementation", [])),
            "maturity_signals": json.dumps(cp.get("maturity_signals", {})),
            "possible_documents": json.dumps(cp.get("possible_documents", [])),
            "possible_technical_evidence": json.dumps(cp.get("possible_technical_evidence", [])),
        })
        inserted += 1
    return inserted


def purge_existing(conn):
    from sqlalchemy import text
    conn.execute(text(
        "DELETE FROM ecc_ai_checkpoints WHERE framework_id = :fid"
    ), {"fid": FRAMEWORK_ID})
    conn.execute(text(
        "DELETE FROM ecc_compliance_metadata WHERE framework_id = :fid"
    ), {"fid": FRAMEWORK_ID})
    conn.execute(text(
        "DELETE FROM ecc_framework WHERE framework_id = :fid"
    ), {"fid": FRAMEWORK_ID})
    print(f"Purged existing {FRAMEWORK_ID} rows from all three layers.")


def main():
    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv

    print(f"ECC-2:2024 Import | force={force} | dry_run={dry_run}")
    print("=" * 60)

    # Load JSON files
    l1 = load_json(L1_FILE)
    l2 = load_json(L2_FILE)
    l3 = load_json(L3_FILE)

    l1_rows = flatten_layer1(l1)
    print(f"Layer 1: {len(l1_rows)} control rows loaded from JSON")
    print(f"Layer 2: {len(l2['controls_metadata'])} metadata rows loaded from JSON")
    print(f"Layer 3: {len(l3['checkpoints'])} AI checkpoint rows loaded from JSON")

    # Validate AI_GENERATED flag in Layer 3
    bad = [c for c in l3["checkpoints"] if not c.get("AI_GENERATED", False)]
    if bad:
        print(f"ERROR: {len(bad)} Layer 3 entries missing AI_GENERATED=true. Aborting.")
        sys.exit(1)

    if dry_run:
        import_layer1(None, l1_rows, dry_run=True)
        import_layer2(None, l2, dry_run=True)
        import_layer3(None, l3, dry_run=True)
        print("\n[DRY RUN] Validation passed. No database changes made.")
        return

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL environment variable not set.")
        sys.exit(1)

    from sqlalchemy import create_engine
    engine = create_engine(database_url)

    with engine.begin() as conn:
        if force:
            purge_existing(conn)

        n1 = import_layer1(conn, l1_rows, dry_run=False)
        print(f"Layer 1: inserted/updated {n1} rows into ecc_framework")

        n2 = import_layer2(conn, l2, dry_run=False)
        print(f"Layer 2: inserted/updated {n2} rows into ecc_compliance_metadata")

        n3 = import_layer3(conn, l3, dry_run=False)
        print(f"Layer 3: inserted {n3} rows into ecc_ai_checkpoints")

        # Log the load
        from sqlalchemy import text
        conn.execute(text("""
            INSERT INTO framework_load_log (id, framework_id, controls_count, checkpoints_count, notes)
            VALUES (:id, :fid, :cc, :nc, :notes)
        """), {
            "id": str(uuid.uuid4()),
            "fid": FRAMEWORK_ID,
            "cc": n1,
            "nc": n3,
            "notes": f"force={force}",
        })

    print("\nImport complete.")
    print(f"  ecc_framework rows:           {n1}")
    print(f"  ecc_compliance_metadata rows: {n2}")
    print(f"  ecc_ai_checkpoints rows:      {n3}")


if __name__ == "__main__":
    main()
