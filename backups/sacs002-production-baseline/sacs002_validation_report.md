# SACS-002 Validation Report
**Generated:** 2026-05-07  
**Source:** Saudi Aramco Third Party Cybersecurity Standard (SACS-002), February 2022  
**Framework ID:** `SACS-002`

---

## Layer Counts

| Layer | Records | Expected |
|-------|---------|----------|
| L1 (Official Control Text) | 92 | 92 |
| L2 (Inferred Metadata) | 92 | 92 |
| L3 (AI Audit Checkpoints) | 92 | 92 |

All layers pass orphan checks — every L2 and L3 record maps to an L1 `control_code`.

---

## Section Distribution

| Section | Controls | Description |
|---------|----------|-------------|
| A | 23 | General Requirements — apply to all third parties |
| B | 69 | Specific Requirements — conditional by applicability class |

---

## NIST CSF Function Distribution

| Function | Count |
|----------|-------|
| IDENTIFY | 9 |
| PROTECT | 69 |
| DETECT | 8 |
| RESPOND | 6 |

---

## NIST CSF Category Distribution

| Category Code | Count | Full Name |
|--------------|-------|-----------|
| AC | 23 | Access Control |
| DS | 21 | Data Security |
| IP | 14 | Information Protection Processes |
| PT | 8 | Protective Technology |
| CM | 6 | Continuous Monitoring |
| RA | 4 | Risk Assessment |
| GV | 3 | Governance |
| AT | 3 | Awareness and Training |
| AE | 2 | Anomalies and Events |
| AN | 2 | Analysis |
| CO | 2 | Communications |
| MI | 2 | Mitigation |
| AM | 1 | Asset Management |
| RM | 1 | Risk Management Strategy |

---

## Section B Applicability Class Distribution

Controls in Section B may apply to one or more of the five third-party classes:

| Class | Controls Applicable |
|-------|-------------------|
| Network Connectivity | 49 |
| Outsourced Infrastructure | 49 |
| Cloud Computing Service | 49 |
| Customized Software | 42 |
| Critical Data Processor | 33 |

---

## Layer 2 Control Type Flags

| Flag | Controls |
|------|----------|
| technical_control | 38 |
| operational_control | 31 |
| monitoring_required | 22 |
| approval_required | 16 |
| review_required | 14 |
| testing_required | 9 |
| governance_control | 8 |

---

## Control Text Quality

- All 92 controls have non-empty `control_text`
- Text lengths: min=50 chars, max=549 chars, avg=169 chars
- Source page range: pages 9–24 of the official PDF

---

## Known Assumptions and Notes

1. **NIST CSF mapping**: The TAXONOMY dict in `generate_sacs002.py` maps each TPC-N to a NIST CSF function/category. These mappings were derived from the PDF's table of contents and section headers — the PDF organises controls by NIST function but does not always state function names inline with each control. Where the PDF was ambiguous, conservative/closest-fit categories were used.

2. **Applicability checkmarks**: Section B checkmarks were extracted from PDF word positions (Unicode `` at known x-coordinates per column: NC≈327, OI≈390, CDP≈448, CS≈500, CCS≈556). Any control not listed in the APPLICABILITY dict has no checkmarks recorded in the PDF at those positions.

3. **TPC-92 boundary**: The last control in the PDF is TPC-92. Its text was post-fixed to stop at the "Reference" section header to avoid absorbing the appendix text.

4. **Section B controls with no applicable_classes**: If any TPC in Section B has an empty `applicable_classes` list, it means no checkmarks were detected at the standard x-positions for that control in the PDF. This can indicate a table layout anomaly; manual review of the PDF page is recommended for those controls.

5. **L3 AI provenance**: All 92 L3 records have `AI_GENERATED: true` enforced both in the JSON and in the `ecc_ai_checkpoints` table's CHECK constraint. L3 data must never be presented to auditors as official regulatory text.

6. **Shared table architecture**: SACS-002 shares `ecc_framework`, `ecc_compliance_metadata`, and `ecc_ai_checkpoints` tables with ECC-2:2024, distinguished by `framework_id = 'SACS-002'`. SACS-002-specific fields (section, NIST category, applicability classes, control type flags) are in the dedicated `sacs002_metadata` table.

---

## Import Instructions

```bash
# Dry run — validates JSON only
DATABASE_URL=postgresql://... python data/sacs002/sacs002_import.py --dry-run

# First-time import
DATABASE_URL=postgresql://... python data/sacs002/sacs002_import.py

# Re-import (drops existing SACS-002 rows first)
DATABASE_URL=postgresql://... python data/sacs002/sacs002_import.py --force
```

Run `data/sacs002/sacs002_schema.sql` against the target database before the first import to create the `sacs002_metadata` table and associated types.
