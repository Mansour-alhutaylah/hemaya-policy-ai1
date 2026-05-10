"""
CCC-2:2024 Framework Import Script
Loads all three layers from JSON files into PostgreSQL/Supabase.

Usage:
    DATABASE_URL=postgresql://... python data/ccc2/ccc2_import.py
    DATABASE_URL=postgresql://... python data/ccc2/ccc2_import.py --force
    DATABASE_URL=postgresql://... python data/ccc2/ccc2_import.py --dry-run

--force     : Deletes existing CCC-2:2024 rows before import
--dry-run   : Validates JSON structure without touching the database
"""

import json
import os
import sys
from pathlib import Path

# Auto-load DATABASE_URL from .env if not already set (avoids needing to
# export the variable manually when running locally).
if not os.getenv("DATABASE_URL"):
    _env = Path(__file__).parent.parent.parent / ".env"
    if _env.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(_env)
        except ImportError:
            pass

BASE_DIR = Path(__file__).parent
FRAMEWORK_ID = "CCC-2:2024"

L1_FILE = BASE_DIR / "ccc2_layer1_official.json"
L2_FILE = BASE_DIR / "ccc2_layer2_metadata.json"
L3_FILE = BASE_DIR / "ccc2_layer3_ai_checkpoints.json"

EXPECTED_DOMAINS     = 4
EXPECTED_SUBDOMAINS  = 24
EXPECTED_MAIN        = 55
EXPECTED_SUBCONTROLS = 120
EXPECTED_ECC_ROWS    = EXPECTED_DOMAINS + EXPECTED_SUBDOMAINS + EXPECTED_MAIN + EXPECTED_SUBCONTROLS  # 203
EXPECTED_META_ROWS   = EXPECTED_MAIN + EXPECTED_SUBCONTROLS  # 175


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def flatten_l1(l1_data: dict) -> list[dict]:
    """
    Walk the nested L1 structure and return a flat list of dicts, one per
    ecc_framework row (domains, subdomains, main controls, subcontrols).
    """
    rows = []
    for domain in l1_data["domains"]:
        d_code = domain["domain_code"]
        d_name = domain["domain_name"]

        rows.append({
            "control_code":       d_code,
            "control_type":       "domain",
            "domain_code":        d_code,
            "domain_name":        d_name,
            "subdomain_code":     None,
            "subdomain_name":     None,
            "control_text":       d_name,
            "parent_control_code": None,
            "source_page":        None,
            "applicability_type": None,
            "ecc_references":     None,
        })

        for subdomain in domain["subdomains"]:
            sd_code = subdomain["subdomain_code"]
            sd_name = subdomain["subdomain_name"]

            rows.append({
                "control_code":       sd_code,
                "control_type":       "subdomain",
                "domain_code":        d_code,
                "domain_name":        d_name,
                "subdomain_code":     sd_code,
                "subdomain_name":     sd_name,
                "control_text":       sd_name,
                "parent_control_code": d_code,
                "source_page":        None,
                "applicability_type": None,
                "ecc_references":     None,
            })

            for ctrl in subdomain["controls"]:
                rows.append({
                    "control_code":       ctrl["control_code"],
                    "control_type":       "main_control",
                    "domain_code":        d_code,
                    "domain_name":        d_name,
                    "subdomain_code":     sd_code,
                    "subdomain_name":     sd_name,
                    "control_text":       ctrl["control_text"],
                    "parent_control_code": sd_code,
                    "source_page":        ctrl.get("source_page"),
                    "applicability_type": ctrl.get("applicability_type"),
                    "ecc_references":     ctrl.get("ecc_references"),
                })

                for sub in ctrl.get("subcontrols", []):
                    rows.append({
                        "control_code":       sub["control_code"],
                        "control_type":       "subcontrol",
                        "domain_code":        d_code,
                        "domain_name":        d_name,
                        "subdomain_code":     sd_code,
                        "subdomain_name":     sd_name,
                        "control_text":       sub["control_text"],
                        "parent_control_code": ctrl["control_code"],
                        "source_page":        sub.get("source_page"),
                        "applicability_type": ctrl.get("applicability_type"),
                        "ecc_references":     ctrl.get("ecc_references"),
                    })

    return rows


def validate(l1_data: dict, l2_data: dict, l3_data: dict) -> list[str]:
    errors = []

    # Flatten L1 and count
    all_rows = flatten_l1(l1_data)
    domains     = [r for r in all_rows if r["control_type"] == "domain"]
    subdomains  = [r for r in all_rows if r["control_type"] == "subdomain"]
    main_ctrls  = [r for r in all_rows if r["control_type"] == "main_control"]
    subcontrols = [r for r in all_rows if r["control_type"] == "subcontrol"]

    if len(domains) != EXPECTED_DOMAINS:
        errors.append(f"L1 domains: expected {EXPECTED_DOMAINS}, got {len(domains)}")
    if len(subdomains) != EXPECTED_SUBDOMAINS:
        errors.append(f"L1 subdomains: expected {EXPECTED_SUBDOMAINS}, got {len(subdomains)}")
    if len(main_ctrls) != EXPECTED_MAIN:
        errors.append(f"L1 main controls: expected {EXPECTED_MAIN}, got {len(main_ctrls)}")
    if len(subcontrols) != EXPECTED_SUBCONTROLS:
        errors.append(f"L1 subcontrols: expected {EXPECTED_SUBCONTROLS}, got {len(subcontrols)}")

    # L1 framework_id header check
    if l1_data.get("framework_id") != FRAMEWORK_ID:
        errors.append(f"L1 header framework_id '{l1_data.get('framework_id')}' != '{FRAMEWORK_ID}'")

    # The 175 codes that L2 and L3 must cover
    meta_codes = {r["control_code"] for r in main_ctrls + subcontrols}

    # L2 checks
    l2_records = l2_data.get("controls_metadata", [])
    if len(l2_records) != EXPECTED_META_ROWS:
        errors.append(f"L2 expected {EXPECTED_META_ROWS} records, got {len(l2_records)}")
    if l2_data.get("AI_GENERATED") is not False:
        errors.append("L2 AI_GENERATED must be false")

    l2_codes = set()
    for r in l2_records:
        code = r.get("control_id")
        if not code:
            errors.append("L2 record missing control_id field")
            continue
        l2_codes.add(code)
        if code not in meta_codes:
            errors.append(f"L2 orphan: {code} not in L1 main/sub controls")

    for code in meta_codes - l2_codes:
        errors.append(f"L2 missing entry for L1 control: {code}")

    # L3 checks
    l3_records = l3_data.get("checkpoints", [])
    if len(l3_records) != EXPECTED_META_ROWS:
        errors.append(f"L3 expected {EXPECTED_META_ROWS} records, got {len(l3_records)}")
    if l3_data.get("AI_GENERATED") is not True:
        errors.append("L3 AI_GENERATED must be true")

    l3_codes = set()
    for r in l3_records:
        code = r.get("control_code")
        if not code:
            errors.append("L3 record missing control_code field")
            continue
        l3_codes.add(code)
        if code not in meta_codes:
            errors.append(f"L3 orphan: {code} not in L1 main/sub controls")
        if not r.get("AI_GENERATED", False):
            errors.append(f"L3 {code}: AI_GENERATED is not True")

    for code in meta_codes - l3_codes:
        errors.append(f"L3 missing entry for L1 control: {code}")

    return errors


def import_framework(l1_data: dict, l2_data: dict, l3_data: dict, conn, force: bool) -> None:
    from psycopg2.extras import execute_values

    all_rows = flatten_l1(l1_data)
    l2_map = {r["control_id"]: r for r in l2_data["controls_metadata"]}
    l3_map = {r["control_code"]: r for r in l3_data["checkpoints"]}

    meta_rows = [r for r in all_rows if r["control_type"] in ("main_control", "subcontrol")]

    with conn:
        cur = conn.cursor()

        if force:
            print(f"  Deleting existing {FRAMEWORK_ID} rows...")
            cur.execute("DELETE FROM ecc_ai_checkpoints WHERE framework_id = %s", (FRAMEWORK_ID,))
            cur.execute("DELETE FROM ccc_metadata WHERE framework_id = %s", (FRAMEWORK_ID,))
            cur.execute("DELETE FROM ecc_compliance_metadata WHERE framework_id = %s", (FRAMEWORK_ID,))
            cur.execute("DELETE FROM ecc_framework WHERE framework_id = %s", (FRAMEWORK_ID,))
            conn.commit()

        # Layer 1 — ecc_framework (203 rows)
        print("  Inserting Layer 1 (ecc_framework)...")
        l1_rows = [
            (
                FRAMEWORK_ID,
                r["domain_code"],
                r["domain_name"],
                r["subdomain_code"],
                r["subdomain_name"],
                r["control_code"],
                r["control_type"],
                r["control_text"],
                r["parent_control_code"],
                False,   # is_ecc2_new
                None,    # ecc2_change_note
                r["source_page"],
            )
            for r in all_rows
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

        # Layer 2 — ecc_compliance_metadata (175 rows, main + subcontrols only)
        # applicability is NULL: CCC-2 uses ccc_metadata.applicability_type instead of the
        # ECC-specific applicability_enum.
        print("  Inserting Layer 2 (ecc_compliance_metadata)...")
        l2_cm_rows = []
        for r in meta_rows:
            m = l2_map.get(r["control_code"], {})
            l2_cm_rows.append((
                FRAMEWORK_ID,
                r["control_code"],
                None,                   # applicability — NULL; use ccc_metadata instead
                None,                   # applicability_note
                m.get("responsible_party"),
                m.get("frequency"),
                FRAMEWORK_ID,           # ecc_version_introduced
                None,                   # change_from_ecc1
                False,                  # deleted_in_ecc2
            ))
        execute_values(cur, """
            INSERT INTO ecc_compliance_metadata
                (framework_id, control_code, applicability, applicability_note,
                 responsible_party, frequency, ecc_version_introduced,
                 change_from_ecc1, deleted_in_ecc2)
            VALUES %s
            ON CONFLICT (framework_id, control_code) DO NOTHING
        """, l2_cm_rows)
        print(f"    {cur.rowcount} rows inserted into ecc_compliance_metadata")

        # Layer 2 — ccc_metadata (175 rows, CCC-2-specific extended metadata)
        print("  Inserting Layer 2 (ccc_metadata)...")
        ccc_meta_rows = []
        for r in meta_rows:
            m = l2_map.get(r["control_code"], {})
            ccc_meta_rows.append((
                FRAMEWORK_ID,
                r["control_code"],
                m.get("applicability_type", r.get("applicability_type", "CSP")),
                json.dumps(m.get("ecc_references", r.get("ecc_references") or [])),
                m.get("mandatory_level_1", True),
                m.get("mandatory_level_2", True),
                m.get("mandatory_level_3", True),
                m.get("mandatory_level_4", True),
                None,   # optional_subcontrols_l3
                None,   # optional_subcontrols_l4
                None,   # not_applicable_subcontrols
                m.get("governance_control", False),
                m.get("technical_control", False),
                m.get("operational_control", False),
                m.get("review_required", False),
                m.get("approval_required", False),
                m.get("testing_required", False),
                m.get("monitoring_required", False),
            ))
        execute_values(cur, """
            INSERT INTO ccc_metadata
                (framework_id, control_code, applicability_type, ecc_references,
                 mandatory_level_1, mandatory_level_2, mandatory_level_3, mandatory_level_4,
                 optional_subcontrols_l3, optional_subcontrols_l4, not_applicable_subcontrols,
                 governance_control, technical_control, operational_control,
                 review_required, approval_required, testing_required, monitoring_required)
            VALUES %s
            ON CONFLICT (framework_id, control_code) DO NOTHING
        """, ccc_meta_rows)
        print(f"    {cur.rowcount} rows inserted into ccc_metadata")

        # Layer 3 — ecc_ai_checkpoints (175 rows)
        print("  Inserting Layer 3 (ecc_ai_checkpoints)...")
        l3_rows = []
        for r in meta_rows:
            cp = l3_map.get(r["control_code"], {})
            maturity = cp.get("maturity_signals")
            l3_rows.append((
                FRAMEWORK_ID,
                r["control_code"],
                True,
                cp.get("model_version", "claude-sonnet-4-6"),
                json.dumps(cp.get("audit_questions", [])),
                json.dumps(cp.get("suggested_evidence", [])),
                json.dumps(cp.get("indicators_of_implementation", [])),
                json.dumps(maturity) if maturity else json.dumps({}),
                json.dumps(cp.get("possible_documents", [])),
                json.dumps(cp.get("possible_technical_evidence", [])),
            ))
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
        """, (FRAMEWORK_ID, "ccc2_import.py", len(meta_rows), len(l3_rows),
              "Initial CCC-2:2024 import"))
        conn.commit()
        print("  Load logged in framework_load_log")


def main():
    dry_run = "--dry-run" in sys.argv
    force   = "--force"   in sys.argv

    print(f"CCC-2:2024 Import — {'DRY RUN' if dry_run else 'LIVE'}")
    print("Loading JSON layers...")
    l1_data = load_json(L1_FILE)
    l2_data = load_json(L2_FILE)
    l3_data = load_json(L3_FILE)
    l2_count = len(l2_data.get("controls_metadata", []))
    l3_count = len(l3_data.get("checkpoints", []))
    print(f"  L2: {l2_count} records, L3: {l3_count} records")

    print("Validating...")
    errors = validate(l1_data, l2_data, l3_data)
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

    import_framework(l1_data, l2_data, l3_data, conn, force=force)
    conn.close()
    print("Import complete.")


if __name__ == "__main__":
    main()
