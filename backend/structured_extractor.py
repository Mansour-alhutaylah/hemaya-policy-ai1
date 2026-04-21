"""
structured_extractor.py
Rule-based sentence classification and entity extraction.
No ML models — just regex and keyword matching.
"""
import re


def classify_sentence(sentence):
    """Classify a sentence as mandatory, advisory, or descriptive."""
    lower = sentence.lower()
    if re.search(r'\b(shall|must|required|mandatory)\b', lower):
        return "mandatory"
    elif re.search(r'\b(should|may|recommended|encouraged)\b', lower):
        return "advisory"
    return "descriptive"


def extract_entities(text):
    """Extract durations, roles, and technologies from text using regex."""
    lower = text.lower()

    durations = re.findall(
        r'\b(\d+)\s*(days?|weeks?|months?|years?|hours?)\b', lower
    )
    durations = [f"{num} {unit}" for num, unit in durations]

    role_patterns = [
        r'\bCISO\b', r'\bCEO\b', r'\bCTO\b', r'\bCOO\b', r'\bCIO\b',
        r'\bSOC\b', r'\bCSIRT\b', r'\bCERT\b',
        r'\bIT manager\b', r'\bsecurity officer\b',
        r'\bchief information security officer\b',
        r'\bdata protection officer\b', r'\bDPO\b',
        r'\bsecurity team\b', r'\bincident response team\b',
    ]
    roles = []
    for pat in role_patterns:
        if re.search(pat, text, re.IGNORECASE):
            match = re.search(pat, text, re.IGNORECASE).group()
            if match.upper() not in [r.upper() for r in roles]:
                roles.append(match)

    tech_patterns = [
        r'\bMFA\b', r'\b2FA\b', r'\bVPN\b', r'\bAES[- ]?256\b',
        r'\bTLS\b', r'\bSSL\b', r'\bHTTPS\b',
        r'\bSIEM\b', r'\bWAF\b', r'\bDLP\b', r'\bEDR\b',
        r'\bIDS\b', r'\bIPS\b', r'\bNGFW\b',
        r'\bMDM\b', r'\bCASB\b', r'\bPAM\b',
        r'\bSPF\b', r'\bDKIM\b', r'\bDMARC\b',
    ]
    technologies = []
    for pat in tech_patterns:
        if re.search(pat, text, re.IGNORECASE):
            match = re.search(pat, text, re.IGNORECASE).group()
            if match.upper() not in [t.upper() for t in technologies]:
                technologies.append(match)

    return {
        "durations": durations,
        "roles": roles,
        "technologies": technologies,
    }
