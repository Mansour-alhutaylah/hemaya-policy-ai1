# SACS-002 Production Baseline

**Created:** 2026-05-07  
**Framework:** Saudi Aramco Third Party Cybersecurity Standard (SACS-002), February 2022  
**Git Tag:** `sacs002-production-v1`

## Contents

| File | Description |
|------|-------------|
| `generate_sacs002.py` | Generator script — reproduces all three JSON layers from the official PDF |
| `sacs002_layer1_official.json` | L1: Official verbatim control text for all 92 controls |
| `sacs002_layer2_metadata.json` | L2: Inferred metadata (section, NIST mapping, applicability, control flags) |
| `sacs002_layer3_ai_checkpoints.json` | L3: AI-generated audit hints (AI_GENERATED: true enforced) |
| `sacs002_schema.sql` | PostgreSQL schema for `sacs002_metadata` table and views |
| `sacs002_import.py` | Import script with `--dry-run` and `--force` flags |
| `sacs002_validation_report.md` | Validation report: counts, distributions, assumptions |
| `sacs002_analyzer.py` | Analyzer snapshot at baseline tag |
| `checksums.txt` | SHA-256 hashes for all files |

## Statistics at Baseline

- 92 total controls (TPC-1 to TPC-92)
- Section A: 23 controls (all third parties)
- Section B: 69 controls (conditional by applicability class)
- 4 NIST CSF functions: IDENTIFY (9), PROTECT (69), DETECT (8), RESPOND (6)

## Restore Instructions

To restore from this baseline:

```bash
# Apply schema first (if sacs002_metadata table doesn't exist)
psql $DATABASE_URL < backups/sacs002-production-baseline/sacs002_schema.sql

# Import all three layers
DATABASE_URL=... python data/sacs002/sacs002_import.py --force

# Verify checksums
sha256sum backups/sacs002-production-baseline/*.json
```

## Integrity Verification

All files are checksummed in `checksums.txt`. Verify with:

```bash
cd backups/sacs002-production-baseline
sha256sum -c checksums.txt
```
