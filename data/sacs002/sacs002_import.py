"""
SACS-002 Framework Import Script
Loads all three layers from JSON files into PostgreSQL/Supabase.

Usage:
    DATABASE_URL=postgresql://... python data/sacs002/sacs002_import.py
    DATABASE_URL=postgresql://... python data/sacs002/sacs002_import.py --force
    DATABASE_URL=postgresql://... python data/sacs002/sacs002_import.py --dry-run

--force     : Deletes existing SACS-002 rows before import
--dry-run   : Validates JSON structure without touching the database
"""

import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
FRAMEWORK_ID = "SACS-002"

L1_FILE = BASE_DIR / "sacs002_layer1_official.json"
L2_FILE = BASE_DIR / "sacs002_layer2_metadata.json"
L3_FILE = BASE_DIR / "sacs002_layer3_ai_checkpoints.json"

REQUIRED_L1_FIELDS = {"framework_id", "control_code", "control_text", "source_page", "section",
                      "function_code", "function_name", "category_code", "category_name"}
REQUIRED_L2_FIELDS = {"framework_id", "control_code"}
REQUIRED_L3_FIELDS = {"framework_id", "control_code", "AI_GENERATED", "audit_questions",
                      "suggested_evidence", "indicators_of_implementation"}


def load_json(path: Path) -> list:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def validate_layers(l1: list, l2: list, l3: list) -> list[str]:
    errors = []

    # Count check
    if len(l1) != 92:
        errors.append(f"L1 expected 92 records, got {len(l1)}")
    if len(l2) != 92:
        errors.append(f"L2 expected 92 records, got {len(l2)}")
    if len(l3) != 92:
        errors.append(f"L3 expected 92 records, got {len(l3)}")

    l1_codes = {r["control_code"] for r in l1}

    # L1 required fields and non-empty control_text
    for r in l1:
        missing = REQUIRED_L1_FIELDS - set(r.keys())
        if missing:
            errors.append(f"L1 {r.get('control_code','?')}: missing fields {missing}")
        if not r.get("control_text", "").strip():
            errors.append(f"L1 {r['control_code']}: empty control_text")
        if r.get("framework_id") != FRAMEWORK_ID:
            errors.append(f"L1 {r['control_code']}: wrong framework_id '{r.get('framework_id')}'")

    # L2 orphan check
    for r in l2:
        if r["control_code"] not in l1_codes:
            errors.append(f"L2 orphan: {r['control_code']} not in L1")

    # L3 AI_GENERATED check + orphan check
    for r in l3:
        if r["control_code"] not in l1_codes:
            errors.append(f"L3 orphan: {r['control_code']} not in L1")
        if not r.get("AI_GENERATED", False):
            errors.append(f"L3 {r['control_code']}: AI_GENERATED is not True")

    # Section distribution
    sec_a = [r for r in l1 if r.get("section") == "A"]
    sec_b = [r for r in l1 if r.get("section") == "B"]
    if len(sec_a) != 23:
        errors.append(f"Expected 23 Section A controls, got {len(sec_a)}")
    if len(sec_b) != 69:
        errors.append(f"Expected 69 Section B controls, got {len(sec_b)}")

    return errors


def import_framework(l1: list, l2: list, l3: list, conn, force: bool) -> None:
    from psycopg2.extras import execute_values

    l2_map = {r["control_code"]: r for r in l2}
    l3_map = {r["control_code"]: r for r in l3}

    with conn:
        cur = conn.cursor()

        if force:
            print(f"  Deleting existing {FRAMEWORK_ID} rows...")
            cur.execute("DELETE FROM ecc_ai_checkpoints WHERE framework_id = %s", (FRAMEWORK_ID,))
            cur.execute("DELETE FROM sacs002_metadata WHERE framework_id = %s", (FRAMEWORK_ID,))
            cur.execute("DELETE FROM ecc_compliance_metadata WHERE framework_id = %s", (FRAMEWORK_ID,))
            cur.execute("DELETE FROM ecc_framework WHERE framework_id = %s", (FRAMEWORK_ID,))
            conn.commit()

        # Layer 1 — ecc_framework
        print("  Inserting Layer 1 (ecc_framework)...")
        l1_rows = [
            (
                FRAMEWORK_ID,
                None,                           # domain_code — SACS-002 uses NIST functions, not ECC domains
                None,                           # domain_name
                None,                           # subdomain_code
                None,                           # subdomain_name
                r["control_code"],
                "main_control",
                r["control_text"],
                None,                           # parent_control_code
                False,                          # is_ecc2_new
                None,                           # ecc2_change_note
                r.get("source_page"),
            )
            for r in l1
        ]
        execute_values(cur, """
            INSERT INTO ecc_framework
                (framework_id, domain_code, domain_name, subdomain_code, subdomain_name,
                 control_code, control_type, control_text, parent_control_code,
                 is_ecc2_new, ecc2_change_note, source_page)
            VALUES %s
            ON CONFLICT (framework_id, control_code) DO NOTHING
        """, l1_rows)
        print(f"    {cur.rowcount} rows inserted into ecc_framework")

        # Layer 2 — ecc_compliance_metadata
        # applicability is NULL for all SACS-002 controls: the shared
        # applicability_enum has ECC-specific values that don't map cleanly to
        # SACS-002's section/class scheme. Applicability is stored instead in
        # sacs002_metadata.section and sacs002_metadata.applicable_classes.
        print("  Inserting Layer 2 (ecc_compliance_metadata)...")
        l2_cm_rows = [
            (
                FRAMEWORK_ID,
                r["control_code"],
                None,                           # applicability — NULL; use sacs002_metadata instead
                None,                           # applicability_note
                r.get("responsible_party"),
                r.get("frequency"),
                "SACS-002",                     # ecc_version_introduced
                None,                           # change_from_ecc1
                False,                          # deleted_in_ecc2
            )
            for r in l2
        ]
        execute_values(cur, """
            INSERT INTO ecc_compliance_metadata
                (framework_id, control_code, applicability, applicability_note,
                 responsible_party, frequency, ecc_version_introduced,
                 change_from_ecc1, deleted_in_ecc2)
            VALUES %s
            ON CONFLICT (framework_id, control_code) DO NOTHING
        """, l2_cm_rows)
        print(f"    {cur.rowcount} rows inserted into ecc_compliance_metadata")

        # Layer 2 — sacs002_metadata (SACS-002-specific extended metadata)
        print("  Inserting Layer 2 (sacs002_metadata)...")
        l2_sacs_rows = []
        for r in l2:
            l1r = next((x for x in l1 if x["control_code"] == r["control_code"]), {})
            l2_sacs_rows.append((
                FRAMEWORK_ID,
                r["control_code"],
                l1r.get("section", "A"),
                l1r.get("function_code"),
                l1r.get("function_name"),
                l1r.get("category_code"),
                l1r.get("category_name"),
                json.dumps(l1r.get("applicable_classes", [])),
                r.get("governance_control", False),
                r.get("technical_control", False),
                r.get("operational_control", False),
                r.get("review_required", False),
                r.get("approval_required", False),
                r.get("testing_required", False),
                r.get("monitoring_required", False),
                r.get("third_party_assessment", False),
            ))
        execute_values(cur, """
            INSERT INTO sacs002_metadata
                (framework_id, control_code, section,
                 nist_function_code, nist_function_name,
                 nist_category_code, nist_category_name,
                 applicable_classes,
                 governance_control, technical_control, operational_control,
                 review_required, approval_required, testing_required,
                 monitoring_required, third_party_assessment)
            VALUES %s
            ON CONFLICT (framework_id, control_code) DO NOTHING
        """, l2_sacs_rows)
        print(f"    {cur.rowcount} rows inserted into sacs002_metadata")

        # Layer 3 — ecc_ai_checkpoints
        print("  Inserting Layer 3 (ecc_ai_checkpoints)...")
        l3_rows = [
            (
                FRAMEWORK_ID,
                r["control_code"],
                True,                           # ai_generated
                r.get("model_version", "claude-sonnet-4-6"),
                json.dumps(r.get("audit_questions", [])),
                json.dumps(r.get("suggested_evidence", [])),
                json.dumps(r.get("indicators_of_implementation", [])),
                json.dumps(r.get("maturity_signals", {})),
                json.dumps(r.get("possible_documents", [])),
                json.dumps(r.get("possible_technical_evidence", [])),
            )
            for r in l3
        ]
        execute_values(cur, """
            INSERT INTO ecc_ai_checkpoints
                (framework_id, control_code, ai_generated, model_version,
                 audit_questions, suggested_evidence, indicators_of_implementation,
                 maturity_signals, possible_documents, possible_technical_evidence)
            VALUES %s
            ON CONFLICT DO NOTHING
        """, l3_rows)
        print(f"    {cur.rowcount} rows inserted into ecc_ai_checkpoints")

        # Log the load
        cur.execute("""
            INSERT INTO framework_load_log
                (framework_id, loaded_by, controls_count, checkpoints_count, notes)
            VALUES (%s, %s, %s, %s, %s)
        """, (FRAMEWORK_ID, "sacs002_import.py", len(l1), len(l3), "Initial SACS-002 import"))
        conn.commit()
        print("  Load logged in framework_load_log")


def main():
    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    print(f"SACS-002 Import — {'DRY RUN' if dry_run else 'LIVE'}")
    print("Loading JSON layers...")
    l1 = load_json(L1_FILE)
    l2 = load_json(L2_FILE)
    l3 = load_json(L3_FILE)
    print(f"  L1: {len(l1)}, L2: {len(l2)}, L3: {len(l3)}")

    print("Validating...")
    errors = validate_layers(l1, l2, l3)
    if errors:
        print("VALIDATION FAILED:")
        for e in errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    print("  Validation passed.")

    if dry_run:
        print("Dry run complete — no database changes made.")
        return

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set.")
        sys.exit(1)

    database_url = database_url.replace("postgres://", "postgresql://", 1)

    import psycopg2
    print("Connecting to database...")
    conn = psycopg2.connect(database_url, sslmode="require", connect_timeout=30)
    print("  Connected.")

    import_framework(l1, l2, l3, conn, force=force)
    conn.close()
    print("Import complete.")


if __name__ == "__main__":
    main()
