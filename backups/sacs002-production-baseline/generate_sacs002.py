"""
generate_sacs002.py
Generates all three SACS-002 layer JSON files from the official PDF.
Run from repo root: python data/sacs002/generate_sacs002.py
"""
import json
import re
import sys
import os

# ── Resolve PDF path ──────────────────────────────────────────────────────────
PDF_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..",
    "backend", "uploads", "frameworks",
    "20260506210008_SACS-002 Third Party Cybersecurity Standard-Feb22.pdf"
)
PDF_PATH = os.path.normpath(PDF_PATH)

try:
    import pymupdf
except ImportError:
    print("ERROR: pymupdf not installed. Run: pip install pymupdf")
    sys.exit(1)

FRAMEWORK_ID   = "SACS-002"
FRAMEWORK_NAME = "SACS-002 Third Party Cybersecurity Standard"
FRAMEWORK_VER  = "February 2022"
CHECKMARK      = ""

# ── Column x-ranges for applicability marks ───────────────────────────────────
COL_X = {
    "network_connectivity":      (300, 355),
    "outsourced_infrastructure": (365, 420),
    "critical_data_processor":   (425, 475),
    "customized_software":       (475, 530),
    "cloud_computing_service":   (530, 590),
}

# ── Control taxonomy ──────────────────────────────────────────────────────────
# Maps control_code -> (function_code, function_name, category_code, category_name, section, source_page)
TAXONOMY = {
    # === SECTION A — GENERAL REQUIREMENTS (all third parties) ===
    "TPC-1":  ("IDENTIFY",  "Identify",  "GV",  "Governance",                                      "A", 9),
    "TPC-2":  ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "A", 9),
    "TPC-3":  ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "A", 9),
    "TPC-4":  ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "A", 9),
    "TPC-5":  ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "A", 9),
    "TPC-6":  ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "A", 9),
    "TPC-7":  ("PROTECT",   "Protect",   "AT",  "Awareness and Training",                           "A", 9),
    "TPC-8":  ("PROTECT",   "Protect",   "AT",  "Awareness and Training",                           "A", 10),
    "TPC-9":  ("PROTECT",   "Protect",   "AT",  "Awareness and Training",                           "A", 10),
    "TPC-10": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "A", 10),
    "TPC-11": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "A", 10),
    "TPC-12": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "A", 10),
    "TPC-13": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "A", 10),
    "TPC-14": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "A", 10),
    "TPC-15": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "A", 10),
    "TPC-16": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "A", 10),
    "TPC-17": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "A", 10),
    "TPC-18": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "A", 10),
    "TPC-19": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "A", 10),
    "TPC-20": ("PROTECT",   "Protect",   "PT",  "Protective Technology",                            "A", 10),
    "TPC-21": ("PROTECT",   "Protect",   "PT",  "Protective Technology",                            "A", 11),
    "TPC-22": ("PROTECT",   "Protect",   "PT",  "Protective Technology",                            "A", 11),
    "TPC-23": ("RESPOND",   "Respond",   "CO",  "Communications",                                   "A", 11),
    # === SECTION B — SPECIFIC REQUIREMENTS (classified third parties) ===
    "TPC-24": ("IDENTIFY",  "Identify",  "AM",  "Asset Management",                                 "B", 11),
    "TPC-25": ("IDENTIFY",  "Identify",  "GV",  "Governance",                                       "B", 11),
    "TPC-26": ("IDENTIFY",  "Identify",  "GV",  "Governance",                                       "B", 11),
    "TPC-27": ("IDENTIFY",  "Identify",  "RA",  "Risk Assessment",                                  "B", 11),
    "TPC-28": ("IDENTIFY",  "Identify",  "RA",  "Risk Assessment",                                  "B", 11),
    "TPC-29": ("IDENTIFY",  "Identify",  "RA",  "Risk Assessment",                                  "B", 12),
    "TPC-30": ("IDENTIFY",  "Identify",  "RA",  "Risk Assessment",                                  "B", 12),
    "TPC-31": ("IDENTIFY",  "Identify",  "RM",  "Risk Management Strategy",                         "B", 12),
    "TPC-32": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 12),
    "TPC-33": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 12),
    "TPC-34": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 12),
    "TPC-35": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 12),
    "TPC-36": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 12),
    "TPC-37": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 12),
    "TPC-38": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 12),
    "TPC-39": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 12),
    "TPC-40": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 13),
    "TPC-41": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 13),
    "TPC-42": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 13),
    "TPC-43": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 13),
    "TPC-44": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 13),
    "TPC-45": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 13),
    "TPC-46": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 13),
    "TPC-47": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 13),
    "TPC-48": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 13),
    "TPC-49": ("PROTECT",   "Protect",   "AC",  "Access Control",                                   "B", 13),
    "TPC-50": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 14),
    "TPC-51": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 14),
    "TPC-52": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 14),
    "TPC-53": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 14),
    "TPC-54": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 14),
    "TPC-55": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 14),
    "TPC-56": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 14),
    "TPC-57": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 14),
    "TPC-58": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 14),
    "TPC-59": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 14),
    "TPC-60": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 15),
    "TPC-61": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 15),
    "TPC-62": ("PROTECT",   "Protect",   "DS",  "Data Security",                                    "B", 15),
    "TPC-63": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 15),
    "TPC-64": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 15),
    "TPC-65": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 15),
    "TPC-66": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 15),
    "TPC-67": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 15),
    "TPC-68": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 16),
    "TPC-69": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 16),
    "TPC-70": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 16),
    "TPC-71": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 16),
    "TPC-72": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 16),
    "TPC-73": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 16),
    "TPC-74": ("PROTECT",   "Protect",   "IP",  "Information Protection Processes and Procedures",  "B", 16),
    "TPC-75": ("PROTECT",   "Protect",   "PT",  "Protective Technology",                            "B", 17),
    "TPC-76": ("PROTECT",   "Protect",   "PT",  "Protective Technology",                            "B", 17),
    "TPC-77": ("PROTECT",   "Protect",   "PT",  "Protective Technology",                            "B", 17),
    "TPC-78": ("PROTECT",   "Protect",   "PT",  "Protective Technology",                            "B", 17),
    "TPC-79": ("PROTECT",   "Protect",   "PT",  "Protective Technology",                            "B", 17),
    "TPC-80": ("DETECT",    "Detect",    "AE",  "Anomalies and Events",                             "B", 17),
    "TPC-81": ("DETECT",    "Detect",    "AE",  "Anomalies and Events",                             "B", 17),
    "TPC-82": ("DETECT",    "Detect",    "CM",  "Continuous Monitoring",                            "B", 17),
    "TPC-83": ("DETECT",    "Detect",    "CM",  "Continuous Monitoring",                            "B", 18),
    "TPC-84": ("DETECT",    "Detect",    "CM",  "Continuous Monitoring",                            "B", 18),
    "TPC-85": ("DETECT",    "Detect",    "CM",  "Continuous Monitoring",                            "B", 18),
    "TPC-86": ("DETECT",    "Detect",    "CM",  "Continuous Monitoring",                            "B", 18),
    "TPC-87": ("DETECT",    "Detect",    "CM",  "Continuous Monitoring",                            "B", 18),
    "TPC-88": ("RESPOND",   "Respond",   "CO",  "Communications",                                   "B", 18),
    "TPC-89": ("RESPOND",   "Respond",   "AN",  "Analysis",                                         "B", 18),
    "TPC-90": ("RESPOND",   "Respond",   "AN",  "Analysis",                                         "B", 18),
    "TPC-91": ("RESPOND",   "Respond",   "MI",  "Mitigation",                                       "B", 18),
    "TPC-92": ("RESPOND",   "Respond",   "MI",  "Mitigation",                                       "B", 19),
}

# ── Applicability for Section B (extracted from PDF checkmarks) ───────────────
APPLICABILITY = {
    "TPC-24": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-25": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-26": ["network_connectivity","outsourced_infrastructure"],
    "TPC-27": ["network_connectivity","outsourced_infrastructure","customized_software","cloud_computing_service"],
    "TPC-28": ["cloud_computing_service"],
    "TPC-29": ["customized_software"],
    "TPC-30": ["cloud_computing_service"],
    "TPC-31": ["network_connectivity","outsourced_infrastructure"],
    "TPC-32": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-33": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-34": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-35": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software"],
    "TPC-36": ["network_connectivity","outsourced_infrastructure","cloud_computing_service"],
    "TPC-37": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-38": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-39": ["critical_data_processor"],
    "TPC-40": ["network_connectivity","outsourced_infrastructure"],
    "TPC-41": ["network_connectivity","outsourced_infrastructure","critical_data_processor"],
    "TPC-42": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-43": ["cloud_computing_service"],
    "TPC-44": ["cloud_computing_service"],
    "TPC-45": ["cloud_computing_service"],
    "TPC-46": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-47": ["network_connectivity","outsourced_infrastructure","critical_data_processor"],
    "TPC-48": ["network_connectivity","outsourced_infrastructure","critical_data_processor"],
    "TPC-49": ["network_connectivity"],
    "TPC-50": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-51": ["network_connectivity","outsourced_infrastructure"],
    "TPC-52": ["outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-53": ["cloud_computing_service"],
    "TPC-54": ["network_connectivity","outsourced_infrastructure","critical_data_processor","cloud_computing_service"],
    "TPC-55": ["cloud_computing_service"],
    "TPC-56": ["network_connectivity","outsourced_infrastructure","cloud_computing_service"],
    "TPC-57": ["network_connectivity","outsourced_infrastructure","critical_data_processor"],
    "TPC-58": ["critical_data_processor"],
    "TPC-59": ["critical_data_processor"],
    "TPC-60": ["customized_software","cloud_computing_service"],
    "TPC-61": ["customized_software","cloud_computing_service"],
    "TPC-62": ["customized_software","cloud_computing_service"],
    "TPC-63": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-64": ["network_connectivity","outsourced_infrastructure","customized_software","cloud_computing_service"],
    "TPC-65": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-66": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-67": ["network_connectivity","outsourced_infrastructure","customized_software","cloud_computing_service"],
    "TPC-68": ["network_connectivity","outsourced_infrastructure","customized_software","cloud_computing_service"],
    "TPC-69": ["network_connectivity","outsourced_infrastructure","customized_software","cloud_computing_service"],
    "TPC-70": ["network_connectivity","outsourced_infrastructure","customized_software"],
    "TPC-71": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-72": ["customized_software"],
    "TPC-73": ["customized_software"],
    "TPC-74": ["customized_software","cloud_computing_service"],
    "TPC-75": ["network_connectivity","outsourced_infrastructure","customized_software","cloud_computing_service"],
    "TPC-76": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-77": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-78": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-79": ["customized_software","cloud_computing_service"],
    "TPC-80": ["network_connectivity","outsourced_infrastructure","cloud_computing_service"],
    "TPC-81": ["network_connectivity","outsourced_infrastructure","customized_software","cloud_computing_service"],
    "TPC-82": ["network_connectivity","outsourced_infrastructure","critical_data_processor"],
    "TPC-83": ["network_connectivity","outsourced_infrastructure","customized_software","cloud_computing_service"],
    "TPC-84": ["network_connectivity","outsourced_infrastructure","critical_data_processor"],
    "TPC-85": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-86": ["network_connectivity","outsourced_infrastructure","critical_data_processor","cloud_computing_service"],
    "TPC-87": ["network_connectivity","outsourced_infrastructure","customized_software","cloud_computing_service"],
    "TPC-88": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-89": ["network_connectivity","outsourced_infrastructure","customized_software","cloud_computing_service"],
    "TPC-90": ["network_connectivity","outsourced_infrastructure"],
    "TPC-91": ["network_connectivity","outsourced_infrastructure","critical_data_processor","customized_software","cloud_computing_service"],
    "TPC-92": ["customized_software","cloud_computing_service"],
}


def extract_control_texts(pdf_path):
    """Extract verbatim control text from PDF for each TPC-N control."""
    doc = pymupdf.open(pdf_path)

    SECTION_HEADERS = {
        "IDENTIFY", "PROTECT", "DETECT", "RESPOND", "RECOVER",
        "Governance (GV)", "Access Control (AC)", "Awareness and Training (AT)",
        "Data Security (DS)", "Information Protection Processes and Procedures (IP)",
        "Protective Technology (PT)", "Asset Management (AM)",
        "Risk Assessment (RA)", "Risk Management Strategy (RM)",
        "Anomalies and Events (AE)", "Continuous Monitoring (CM)",
        "Communications (CO)", "Analysis (AN)", "Mitigation (MI)",
        "B.", "VIII.", "IX.", "Appendix",
        "CNTL", "No.", "Control Name",
        "Network", "Connectivity", "Outsourced", "Infrastructure",
        "Customized", "Cloud", "Computing", "Service",
        "Saudi Aramco: Company General Use",
    }

    HEADER_PAT = re.compile(
        r"^(Document Responsibility:|Information Security Department|"
        r"SACS-002 \| Issue Date:|February 2022|\d{1,2})$",
        re.IGNORECASE,
    )

    # Gather all text spans
    all_spans = []
    for pg_idx in range(len(doc)):
        page = doc[pg_idx]
        blocks = page.get_text("dict", flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
        for block in blocks["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    txt = span["text"].strip()
                    if txt:
                        all_spans.append((pg_idx + 1, span["bbox"][0], span["bbox"][1], txt))

    ctrl_id_pat = re.compile(r"^TPC-\d+$")
    ctrl_positions = []
    for i, (pg, x, y, txt) in enumerate(all_spans):
        if ctrl_id_pat.match(txt):
            ctrl_positions.append((txt, i, pg))

    ctrl_texts = {}
    for idx, (ctrl_id, start_i, pg) in enumerate(ctrl_positions):
        end_i = ctrl_positions[idx + 1][1] if idx + 1 < len(ctrl_positions) else len(all_spans)

        parts = []
        for j in range(start_i + 1, min(end_i, start_i + 80)):
            s_pg, s_x, s_y, s_txt = all_spans[j]

            if CHECKMARK in s_txt:
                continue
            if HEADER_PAT.match(s_txt):
                continue
            if s_txt in SECTION_HEADERS:
                continue
            if ctrl_id_pat.match(s_txt):
                break
            # Skip applicability column content (x > 295 in Section B pages)
            if s_x > 295 and s_pg >= 12:
                continue
            parts.append(s_txt)

        text = re.sub(r"\s+", " ", " ".join(parts)).strip()
        ctrl_texts[ctrl_id] = text

    # Post-fix: TPC-92 may absorb Reference section
    if "TPC-92" in ctrl_texts:
        t = ctrl_texts["TPC-92"]
        for stop in (" Reference ", "VIII.", "IX."):
            idx2 = t.find(stop)
            if idx2 > 0:
                t = t[:idx2].strip()
        ctrl_texts["TPC-92"] = t

    return ctrl_texts


def build_layer1(ctrl_texts):
    records = []
    for ctrl_id in sorted(ctrl_texts.keys(), key=lambda x: int(x.split("-")[1])):
        tax = TAXONOMY.get(ctrl_id)
        if not tax:
            continue
        fn_code, fn_name, cat_code, cat_name, section, src_page = tax

        # Applicability field
        if section == "A":
            applicability = "all_third_parties"
            applicable_classes = []
        else:
            app_classes = APPLICABILITY.get(ctrl_id, [])
            applicable_classes = app_classes
            if len(app_classes) == 5:
                applicability = "all_classified_third_parties"
            elif len(app_classes) == 1:
                applicability = f"{app_classes[0]}_only"
            else:
                applicability = "conditional_see_applicable_classes"

        records.append({
            "framework_id":       FRAMEWORK_ID,
            "framework_name":     FRAMEWORK_NAME,
            "framework_version":  FRAMEWORK_VER,
            "section":            section,
            "section_name":       "General Requirements" if section == "A" else "Specific Requirements",
            "function_code":      fn_code,
            "function_name":      fn_name,
            "category_code":      cat_code,
            "category_name":      cat_name,
            "control_code":       ctrl_id,
            "control_type":       "main_control",
            "control_text":       ctrl_texts[ctrl_id],
            "parent_control_code": None,
            "objective":          None,
            "applicability":      applicability,
            "applicable_classes": applicable_classes,
            "source_page":        src_page,
            "official_reference": f"SACS-002 Section VII.{section}, {ctrl_id}",
        })
    return records


def build_layer2(layer1):
    FREQ_MAP = {
        "daily": ["daily", "every day"],
        "weekly": ["weekly", "every week"],
        "monthly": ["monthly", "every month", "once a month"],
        "quarterly": ["quarterly", "every quarter"],
        "semiannual": ["semiannual", "semi-annual", "every six months", "every 6 months"],
        "annual": ["annual", "annually", "yearly", "every year", "per year", "once a year", "14 days"],
        "continuous": ["continuous", "real-time", "24/7", "regularly"],
        "on_event": ["upon", "when", "as needed", "on termination", "before deployment", "before moving"],
    }

    def infer_frequency(text):
        t = text.lower()
        for freq, keywords in FREQ_MAP.items():
            if any(k in t for k in keywords):
                return freq
        return "as_required"

    def infer_types(ctrl_id, text, cat_code):
        t = text.lower()
        return {
            "governance_control":    cat_code in ("GV", "RM", "RA"),
            "technical_control":     any(k in t for k in ["firewall","encryption","password","mfa","vpn","ids","ips","antivirus","av software","patch","scan","log","backup","waf","certificate"]),
            "operational_control":   any(k in t for k in ["procedure","process","policy","training","awareness","drill","review","audit","certif"]),
            "policy_based":          any(k in t for k in ["policy","standard","procedure","document"]),
            "process_based":         any(k in t for k in ["process","procedure","step","workflow","plan"]),
            "people_based":          any(k in t for k in ["employee","personnel","user","staff","third party must inform","training","awareness","background check"]),
            "technology_based":      any(k in t for k in ["system","software","hardware","device","network","cloud","firewall","encryption","mfa","patch","av","ids","ips","waf","log"]),
            "review_required":       any(k in t for k in ["review","audit","assess","inspect","evaluate","periodic"]),
            "approval_required":     any(k in t for k in ["approv","authoriz","explicit","waiver","certif","signed"]),
            "testing_required":      any(k in t for k in ["test","penetration","drill","exercise","scan","verif"]),
            "monitoring_required":   any(k in t for k in ["monitor","log","track","detect","alert","surveil","correlate"]),
        }

    records = []
    for rec in layer1:
        ctrl_id  = rec["control_code"]
        tax      = TAXONOMY[ctrl_id]
        cat_code = tax[2]
        text     = rec["control_text"]
        types    = infer_types(ctrl_id, text, cat_code)

        # Responsible party inference
        if cat_code == "GV":
            responsible = "CISO / Information Security Management"
        elif cat_code in ("AC", "DS", "PT", "AT", "IP", "AM", "CM", "AE"):
            responsible = "IT / Information Security Team"
        elif cat_code in ("RA", "RM"):
            responsible = "Risk Management / CISO"
        elif cat_code in ("CO", "AN", "MI"):
            responsible = "Incident Response Team / CISO"
        else:
            responsible = "Third Party Management"

        records.append({
            "AI_GENERATED":             False,
            "METADATA_TYPE":            "inferred_operational_metadata",
            "framework_id":             FRAMEWORK_ID,
            "control_code":             ctrl_id,
            "section":                  rec["section"],
            "applicability":            rec["applicability"],
            "applicable_classes":       rec["applicable_classes"],
            "responsible_party":        responsible,
            "frequency":                infer_frequency(text),
            "implementation_type":      cat_code,
            **types,
            "notes":                    "Metadata inferred from official control text. Not official framework content.",
        })
    return records


def build_layer3(layer1):
    """
    AI-generated audit assistance checkpoints.
    Each control gets 3 audit questions, evidence hints, and maturity signals.
    These are assistance tools only — not regulatory requirements.
    """
    records = []

    AUDIT_TEMPLATES = {
        "GV": {
            "questions": [
                "Is there a documented {subject} policy formally approved and communicated to all personnel?",
                "Does the {subject} policy define scope, responsibilities, and review cycle?",
                "Is the {subject} policy reviewed and updated at least annually?",
            ],
            "evidence": ["Signed policy document", "Policy approval record", "Annual review log"],
            "indicators": ["Policy document exists", "Management approval on file", "Staff acknowledgment records"],
        },
        "AC": {
            "questions": [
                "Is {subject} enforced and documented with configuration evidence?",
                "Are access reviews conducted at the required frequency for {subject}?",
                "Is there logging and monitoring of {subject} events?",
            ],
            "evidence": ["Access control configuration screenshots", "Access review records", "Audit logs"],
            "indicators": ["Technical configuration active", "Review records current", "Log retention policy enforced"],
        },
        "AT": {
            "questions": [
                "Is mandatory {subject} training conducted and tracked for all users?",
                "Do training records show completion dates and topics covered?",
                "Is the training content updated to reflect current threats?",
            ],
            "evidence": ["Training completion records", "Training content/curriculum", "Acknowledgment forms"],
            "indicators": ["All users trained annually", "Records maintained", "Content reviewed for relevance"],
        },
        "DS": {
            "questions": [
                "Is {subject} implemented and verified through technical testing?",
                "Are configuration settings documented and regularly reviewed?",
                "Is there evidence that {subject} covers all in-scope systems?",
            ],
            "evidence": ["Technical configuration evidence", "Test/scan reports", "Asset inventory with coverage mapping"],
            "indicators": ["Control active on all in-scope systems", "No exceptions without approval", "Regular testing conducted"],
        },
        "IP": {
            "questions": [
                "Are formal procedures documented and followed for {subject}?",
                "Are procedures reviewed and updated when processes change?",
                "Is there evidence of procedure execution (logs, records, sign-offs)?",
            ],
            "evidence": ["Written procedure document", "Procedure execution log", "Review/update records"],
            "indicators": ["Procedures documented", "Execution evidence exists", "Annual review conducted"],
        },
        "PT": {
            "questions": [
                "Is {subject} implemented and configured according to best practices?",
                "Are updates/signatures maintained current (within defined timeframes)?",
                "Is coverage verified across all in-scope systems?",
            ],
            "evidence": ["Configuration evidence", "Update/patch log", "Coverage report"],
            "indicators": ["Technology deployed", "Updates current", "Coverage verified"],
        },
        "AM": {
            "questions": [
                "Is there a documented {subject} classification scheme?",
                "Is the classification applied consistently to all relevant assets?",
                "Are classification decisions reviewed regularly?",
            ],
            "evidence": ["Classification policy", "Asset inventory with classification labels", "Review records"],
            "indicators": ["Policy documented", "Applied to all assets", "Periodic review conducted"],
        },
        "RA": {
            "questions": [
                "Is {subject} conducted at the required frequency by qualified personnel?",
                "Are findings documented, tracked, and remediated?",
                "Are results reported to management?",
            ],
            "evidence": ["Assessment report", "Remediation tracking records", "Management report or sign-off"],
            "indicators": ["Assessment conducted on schedule", "Findings remediated", "Management aware"],
        },
        "RM": {
            "questions": [
                "Is there a documented risk management process for {subject}?",
                "Are identified risks tracked in a risk register with owners and treatment plans?",
                "Is the risk register reviewed at the required frequency?",
            ],
            "evidence": ["Risk assessment records", "Risk register", "Risk treatment plans"],
            "indicators": ["Process documented", "Risks tracked", "Register reviewed regularly"],
        },
        "AE": {
            "questions": [
                "Is {subject} monitored continuously with alerts configured?",
                "Are security events logged and retained per policy?",
                "Are anomalies investigated and documented?",
            ],
            "evidence": ["Monitoring tool configuration", "Alert rules evidence", "Incident/anomaly investigation records"],
            "indicators": ["Monitoring active", "Log retention enforced", "Alerts respond to events"],
        },
        "CM": {
            "questions": [
                "Is {subject} monitored on the required schedule?",
                "Are findings from monitoring acted upon within defined timeframes?",
                "Are monitoring results reported to management?",
            ],
            "evidence": ["Monitoring schedule", "Scan/review reports", "Remediation tracking"],
            "indicators": ["Monitoring conducted on schedule", "Findings remediated", "Reports to management"],
        },
        "CO": {
            "questions": [
                "Is there a documented communication plan for {subject}?",
                "Are contacts and escalation paths defined and tested?",
                "Are communication records maintained?",
            ],
            "evidence": ["Communication plan document", "Contact list with roles", "Communication drill records"],
            "indicators": ["Plan documented", "Contacts current", "Communication tested"],
        },
        "AN": {
            "questions": [
                "Is there a documented process for {subject} analysis?",
                "Are all relevant events analyzed and classified?",
                "Are analysis results used to improve security posture?",
            ],
            "evidence": ["Analysis procedure", "Incident classification records", "Lessons learned documentation"],
            "indicators": ["Process documented", "Events classified consistently", "Improvements implemented"],
        },
        "MI": {
            "questions": [
                "Are remediation timeframes defined and tracked for {subject}?",
                "Is there evidence of timely remediation within defined SLAs?",
                "Are unresolved items escalated and tracked?",
            ],
            "evidence": ["Vulnerability/incident tracking records", "SLA compliance reports", "Escalation records"],
            "indicators": ["Timeframes defined", "SLA compliance tracked", "Escalation process active"],
        },
    }

    def get_subject(ctrl_id, text, cat_code):
        """Extract a brief subject from the control text."""
        # Take first ~60 chars of cleaned control text as subject hint
        t = text[:80].lower()
        if "password" in t:
            return "password management"
        if "multi-factor" in t or "mfa" in t:
            return "multi-factor authentication"
        if "firewall" in t:
            return "firewall management"
        if "encryption" in t or "encrypt" in t:
            return "encryption"
        if "backup" in t:
            return "backup management"
        if "patch" in t or "update" in t and "operating" in t:
            return "patch management"
        if "anti-virus" in t or "antivirus" in t:
            return "anti-virus protection"
        if "penetration" in t:
            return "penetration testing"
        if "vulnerability" in t and "scan" in t:
            return "vulnerability scanning"
        if "incident" in t and "response" in t:
            return "incident response"
        if "access" in t and "review" in t:
            return "access review"
        if "training" in t:
            return "cybersecurity training"
        if "log" in t and "audit" in t:
            return "audit logging"
        if "business continuity" in t:
            return "business continuity"
        if "disaster recovery" in t:
            return "disaster recovery"
        if "sanitiz" in t:
            return "data sanitization"
        if "classification" in t:
            return "information classification"
        if "spf" in t:
            return "SPF / email authentication"
        if "waf" in t or "web application firewall" in t:
            return "web application firewall"
        if "ids" in t or "ips" in t or "intrusion" in t:
            return "intrusion detection/prevention"
        if "wireless" in t:
            return "wireless network security"
        if "acceptable use" in t:
            return "acceptable use policy"
        if "off-boarding" in t:
            return "employee off-boarding"
        if "on-boarding" in t:
            return "employee on-boarding"
        if "segregat" in t:
            return "data/network segregation"
        if "visitor" in t:
            return "visitor management"
        return f"{cat_code} requirement"

    for rec in layer1:
        ctrl_id  = rec["control_code"]
        tax      = TAXONOMY[ctrl_id]
        cat_code = tax[2]
        text     = rec["control_text"]
        tmpl     = AUDIT_TEMPLATES.get(cat_code, AUDIT_TEMPLATES["DS"])
        subject  = get_subject(ctrl_id, text, cat_code)

        questions = [q.format(subject=subject) for q in tmpl["questions"]]
        evidence  = tmpl["evidence"]
        indicators = tmpl["indicators"]

        records.append({
            "AI_GENERATED":              True,
            "framework_id":              FRAMEWORK_ID,
            "control_code":              ctrl_id,
            "section":                   rec["section"],
            "category_code":             cat_code,
            "audit_questions":           questions,
            "suggested_evidence":        evidence,
            "indicators_of_implementation": indicators,
            "maturity_signals": {
                "initial":    f"No documented {subject} process or implementation.",
                "developing": f"{subject.capitalize()} partially implemented; gaps in coverage or documentation.",
                "defined":    f"{subject.capitalize()} implemented with documented policy or procedure.",
                "managed":    f"{subject.capitalize()} consistently implemented, monitored, and reviewed.",
                "optimizing": f"{subject.capitalize()} continuously improved based on metrics and incidents.",
            },
            "possible_documents": [
                f"{subject.replace(' ', '_')}_policy.pdf",
                f"{subject.replace(' ', '_')}_procedure.pdf",
                f"{subject.replace(' ', '_')}_evidence.pdf",
            ],
            "possible_technical_evidence": [
                f"Configuration screenshot for {subject}",
                f"Tool/system report for {subject}",
                f"Audit log sample for {subject}",
            ],
        })
    return records


# ── Main execution ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Extracting control texts from: {PDF_PATH}")
    ctrl_texts = extract_control_texts(PDF_PATH)
    print(f"  Extracted: {len(ctrl_texts)} control texts")

    missing = [c for c in TAXONOMY if c not in ctrl_texts or len(ctrl_texts[c]) < 20]
    if missing:
        print(f"  WARNING: short/missing texts for: {missing}")
    else:
        print("  All 92 controls have complete text.")

    print("Building Layer 1 (official control text)...")
    layer1 = build_layer1(ctrl_texts)
    print(f"  {len(layer1)} L1 records")

    print("Building Layer 2 (inferred metadata)...")
    layer2 = build_layer2(layer1)
    print(f"  {len(layer2)} L2 records")

    print("Building Layer 3 (AI audit checkpoints)...")
    layer3 = build_layer3(layer1)
    print(f"  {len(layer3)} L3 records")

    # Output directory
    out_dir = os.path.dirname(os.path.abspath(__file__))

    l1_path = os.path.join(out_dir, "sacs002_layer1_official.json")
    l2_path = os.path.join(out_dir, "sacs002_layer2_metadata.json")
    l3_path = os.path.join(out_dir, "sacs002_layer3_ai_checkpoints.json")

    with open(l1_path, "w", encoding="utf-8") as f:
        json.dump(layer1, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {l1_path}")

    with open(l2_path, "w", encoding="utf-8") as f:
        json.dump(layer2, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {l2_path}")

    with open(l3_path, "w", encoding="utf-8") as f:
        json.dump(layer3, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {l3_path}")

    print("\nDone. Run validation with: python data/sacs002/sacs002_import.py --dry-run")
