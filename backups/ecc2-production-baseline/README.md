# ECC-2:2024 Framework Data

This directory contains the structured ECC-2:2024 framework split into three layers.

## Files

| File | Description |
|---|---|
| `ecc2_layer1_official.json` | Layer 1 — Official regulatory text. Never AI-modified. |
| `ecc2_layer2_metadata.json` | Layer 2 — Compliance metadata (applicability, frequency, responsible party). |
| `ecc2_layer3_ai_checkpoints.json` | Layer 3 — AI-generated audit aids. `AI_GENERATED: true` on every entry. |
| `ecc2_validation_report.md` | Full validation report documenting 11 issues found in original extraction. |
| `ecc2_schema.sql` | PostgreSQL/Supabase DDL for all tables, indexes, and views. |
| `ecc2_import.py` | Import script loading all three layers from JSON into PostgreSQL. |

## Import Instructions

**Step 1** — Create the schema (run once):
```bash
psql $DATABASE_URL -f data/ecc2/ecc2_schema.sql
```

**Step 2** — Dry run to validate JSON:
```bash
DATABASE_URL=... python data/ecc2/ecc2_import.py --dry-run
```

**Step 3** — Full import (first time):
```bash
DATABASE_URL=... python data/ecc2/ecc2_import.py
```

**Step 4** — Force reload (purges existing ECC-2:2024 rows first):
```bash
DATABASE_URL=... python data/ecc2/ecc2_import.py --force
```

## Layer Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Layer 1 — ecc_framework                                 │
│  Official regulatory text only. INSERT-only after load.  │
│  Source of truth for all compliance determinations.      │
├──────────────────────────────────────────────────────────┤
│  Layer 2 — ecc_compliance_metadata                       │
│  Applicability, responsible party, frequency.            │
│  Human-validated. Supplements Layer 1.                   │
├──────────────────────────────────────────────────────────┤
│  Layer 3 — ecc_ai_checkpoints                            │
│  AI_GENERATED = TRUE (enforced by CHECK constraint).     │
│  Audit preparation aids only. Not regulatory content.    │
└──────────────────────────────────────────────────────────┘
```

## Key ECC-2 Changes Captured

- **New:** 2-4-3-5 DKIM + DMARC requirement
- **New:** 2-5-3-9 DDoS protection (consolidated)
- **New:** 2-8-3 NCA cryptographic standards reference
- **New:** 2-2-3-2 MFA for cloud management consoles
- **New:** 2-4-3-2 MFA for webmail
- **New:** 2-15-3-5 MFA for privileged remote administration
- **Deleted:** 4-2-3-3 data localization requirement
- **Deleted:** Old 2-7-3 privacy subcontrols
