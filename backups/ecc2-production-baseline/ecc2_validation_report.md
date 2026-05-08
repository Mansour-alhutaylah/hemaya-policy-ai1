# ECC-2:2024 Data Layer Validation Report

**Framework:** Essential Cybersecurity Controls v2 (ECC-2:2024)  
**Issued by:** National Cybersecurity Authority (NCA), Kingdom of Saudi Arabia  
**Report updated:** 2026-05-07  
**AI model:** claude-sonnet-4-6  

---

## ⚠️ Important Disclaimer

All Layer 3 content is **AI-generated** for audit preparation assistance only.

- Layer 3 has **NO regulatory authority**
- It must **NEVER** be presented to auditors as official ECC-2 text or regulatory requirements
- Official compliance determinations must reference **Layer 1 verbatim text** from the official ECC-2:2024 document
- The Arabic version of ECC-2:2024 is the binding regulatory text

---

## 1. File Inventory

| File | Layer | Description | Records | Size |
|------|-------|-------------|---------|------|
| `ecc2_layer1_official.json` | 1 | Official ECC-2:2024 regulatory text | 200 controls | 83 KB |
| `ecc2_layer2_metadata.json` | 2 | Human-validated compliance metadata | 200 records | 54 KB |
| `ecc2_layer3_domain1.json` | 3 | AI checkpoints — Domain 1 only | 57 | 110 KB |
| `ecc2_layer3_domain2.json` | 3 | AI checkpoints — Domain 2 only | 121 | 193 KB |
| `ecc2_layer3_domain3.json` | 3 | AI checkpoints — Domain 3 only | 7 | 16 KB |
| `ecc2_layer3_domain4.json` | 3 | AI checkpoints — Domain 4 only | 15 | 36 KB |
| `ecc2_layer3_ai_checkpoints.json` | 3 | **Master merged file — all domains** | **200** | **358 KB** |

---

## 2. Structural Verification

### Layer 1 Verified Counts (Source of Truth)

| Metric | L1 Verified Count |
|--------|-------------------|
| Domains | 4 |
| Subdomains | 28 |
| Main controls | 108 |
| Subcontrols | 92 |
| **Total controls** | **200** |

### Layer 3 Coverage vs Layer 1 & Layer 2

| Check | Result | Status |
|-------|--------|--------|
| Total checkpoints | 200 / 200 | ✅ PASS |
| L2 ID coverage | 200 / 200 | ✅ PASS |
| Duplicate control_ids | 0 | ✅ PASS |
| Missing control_ids | 0 | ✅ PASS |
| Extra / orphan control_ids | 0 | ✅ PASS |
| Parent mapping errors | 0 | ✅ PASS |
| Main controls matched | 108 / 108 | ✅ PASS |
| Subcontrols matched | 92 / 92 | ✅ PASS |
| Domains covered | 4 / 4 | ✅ PASS |
| Subdomains covered | 28 / 28 | ✅ PASS |

---

## 3. Domain Summary

### Domain 1 — Cybersecurity Governance (57 checkpoints)

| Subdomain | Name | Checkpoints |
|-----------|------|-------------|
| 1-1 | Cybersecurity Strategy | 3 |
| 1-2 | Cybersecurity Management | 3 |
| 1-3 | Cybersecurity Policies and Procedures | 4 |
| 1-4 | Cybersecurity Roles and Responsibilities | 2 |
| 1-5 | Cybersecurity Risk Management | 8 |
| 1-6 | Cybersecurity in IT Project Management | 11 |
| 1-7 | Compliance with Cybersecurity Standards, Laws and Regulations | 1 |
| 1-8 | Periodical Cybersecurity Review and Audit | 3 |
| 1-9 | Cybersecurity in Human Resources | 10 |
| 1-10 | Cybersecurity Awareness and Training Program | 12 |
| **Total** | | **57** |

### Domain 2 — Cybersecurity Defense (121 checkpoints)

| Subdomain | Name | Checkpoints |
|-----------|------|-------------|
| 2-1 | Asset Management | 6 |
| 2-2 | Identity and Access Management | 9 |
| 2-3 | Information System and Processing Facilities Protection | 8 |
| 2-4 | Email Protection | 9 |
| 2-5 | Networks Security Management | 13 |
| 2-6 | Mobile Devices Security | 8 |
| 2-7 | Data and Information Protection | 3 |
| 2-8 | Cryptography | 7 |
| 2-9 | Backup and Recovery Management | 7 |
| 2-10 | Vulnerabilities Management | 9 |
| 2-11 | Penetration Testing | 6 |
| 2-12 | Cybersecurity Event Logs and Monitoring Management | 9 |
| 2-13 | Cybersecurity Incident and Threat Management | 9 |
| 2-14 | Physical Security | 9 |
| 2-15 | Web Application Security | 9 |
| **Total** | | **121** |

### Domain 3 — Cybersecurity Resilience (7 checkpoints)

| Subdomain | Name | Checkpoints |
|-----------|------|-------------|
| 3-1 | Cybersecurity Resilience Aspects of BCM | 7 |
| **Total** | | **7** |

### Domain 4 — Third-Party and Cloud Computing Cybersecurity (15 checkpoints)

| Subdomain | Name | Checkpoints |
|-----------|------|-------------|
| 4-1 | Third-Party Cybersecurity | 9 |
| 4-2 | Cloud Computing and Hosting Cybersecurity | 6 |
| **Total** | | **15** |

---

## 4. Layer 3 Checkpoint Structure

Each checkpoint record contains the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `control_id` | string | ECC-2 control code (e.g., `2-2-3-4`) — matches L1 and L2 exactly |
| `parent_control_id` | string \| null | Parent control for subcontrols; null for main controls |
| `control_type` | string | `"main_control"` or `"subcontrol"` |
| `subdomain` | string | Two-level subdomain code (e.g., `"2-2"`) |
| `AI_GENERATED` | boolean | Always `true` — present at record level for traceability |
| `audit_questions` | array | 3–5 questions auditors can use to assess the control |
| `suggested_evidence` | array | Specific artefacts that demonstrate compliance |
| `indicators_of_implementation` | array | Observable signs that the control is operational |
| `maturity_signals` | object | Four levels: `initial`, `developing`, `defined`, `advanced` |
| `possible_documents` | array | Policy/procedural artefacts likely to be requested |
| `possible_technical_evidence` | array | Technical configuration evidence and tool outputs |

---

## 5. Design Principles Applied

### Technical depth prioritisation
Domain 2 (Cybersecurity Defense) checkpoints are intentionally more detailed, with named tools, specific configuration parameters, and realistic technical evidence examples (e.g., scanner output formats, SIEM rule exports, DNS record checks). This reflects the higher technical auditor scrutiny for operational security controls.

### Governance control treatment
Controls following the `x.x.1 / x.x.2 / x.x.4` pattern (identify/document/approve — implement — review periodically) are kept lightweight with 3–4 focused questions. Depth is reserved for the technical subcontrols within `x.x.3`.

### ECC-2 delta awareness
Layer 3 checkpoints for controls that changed between ECC-1 and ECC-2 reflect the updated ECC-2 text:
- **1-2-2**: Full-time Saudi national requirement extended to all cybersecurity positions (not just head and critical roles)
- **1-7-1**: Renumbered; previous 1-7-1 (comply with national laws) deleted; previous 1-7-2 renumbered
- **4-2-3**: KSA data localization subcontrol (old 4-2-3-3) removed; now governed by NDMO/Saudi Data and AI Authority
- **4-2-3-1**: Focus shifted from pre-hosting classification to ongoing protection per classification level

### Parent-child integrity
All 92 subcontrol records have a `parent_control_id` pointing to a valid main control within the same domain. Zero orphan references exist across all 200 records.

---

## 6. Known Limitations

1. **AI-generated content**: All Layer 3 content was generated by an AI model. While designed to be accurate to ECC-2:2024 control intent, it has not been reviewed by a qualified NCA-certified auditor or legal counsel.

2. **No regulatory authority**: Layer 3 checkpoints are audit preparation aids. They do not replace official NCA audit methodology, sector-specific guidance, or auditor professional judgment.

3. **Tool names are illustrative**: Named tools in `possible_technical_evidence` (e.g., CrowdStrike, Qualys, Splunk) are examples only. Compliance is determined by control effectiveness, not by the specific tool used.

4. **Maturity model is non-normative**: The four maturity levels (initial/developing/defined/advanced) are AI-generated guidance. ECC-2:2024 itself does not define a maturity model; the entity is either compliant or non-compliant with each control.

5. **Sector-specific controls**: Some entities may be subject to additional sector regulator requirements beyond ECC-2 (e.g., SAMA, CITC, MOH). Layer 3 covers ECC-2 only.

---

## 7. Generation Metadata

| Attribute | Value |
|-----------|-------|
| Generation model | claude-sonnet-4-6 |
| Generation date | 2026-05-07 |
| Generation method | Incremental by domain (D1 → D2 → D3 → D4) |
| Source for L1 | Official ECC-2:2024 PDF, NCA (Arabic binding) |
| Source for L2 | Human-validated metadata derived from official ECC-2:2024 |
| L3 validated against | L1 verified_counts + L2 control_id index (200 records) |

---

*End of validation report.*
