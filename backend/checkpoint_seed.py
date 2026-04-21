"""
checkpoint_seed.py
Auto-creates control_checkpoints table and seeds 107 NCA ECC checkpoints
across 31 controls. Also seeds control_library with titles.
Called once on server startup. Idempotent.
"""
import json
import uuid
from sqlalchemy import text as sql_text


# ── Control titles (used for control_library + display) ──────────────────────

CONTROL_TITLES = {
    "ECC-1-1-1": "Cybersecurity Governance",
    "ECC-1-2-1": "Cybersecurity Department",
    "ECC-1-3-1": "Cybersecurity Roles and Responsibilities",
    "ECC-1-4-1": "Cybersecurity Policies and Procedures",
    "ECC-1-5-1": "Cybersecurity Awareness and Training",
    "ECC-1-6-1": "Cybersecurity in Project Management",
    "ECC-2-1-1": "Asset Management",
    "ECC-2-2-1": "Identity Management",
    "ECC-2-2-2": "Access Control",
    "ECC-2-2-3": "Authentication",
    "ECC-2-3-1": "Information System Protection",
    "ECC-2-4-1": "Cryptography",
    "ECC-2-5-1": "Email Security",
    "ECC-2-6-1": "Network Security Management",
    "ECC-2-7-1": "Mobile Device Security",
    "ECC-2-8-1": "Data Protection and Privacy",
    "ECC-2-9-1": "Web Application Security",
    "ECC-2-10-1": "Physical Security",
    "ECC-3-1-1": "Cybersecurity Event Management",
    "ECC-3-2-1": "Cybersecurity Incident Management",
    "ECC-3-3-1": "Cybersecurity Monitoring",
    "ECC-3-4-1": "Vulnerability Management",
    "ECC-3-4-2": "Penetration Testing",
    "ECC-3-5-1": "Threat Management",
    "ECC-3-6-1": "Cybersecurity Log Management",
    "ECC-4-1-1": "Business Continuity Management",
    "ECC-4-2-1": "Disaster Recovery",
    "ECC-4-3-1": "Backup Management",
    "ECC-5-1-1": "Third Party Security",
    "ECC-5-2-1": "Cloud Computing Security",
    "ECC-5-3-1": "Industrial Control Systems Security",
}


# ── 107 checkpoints across 31 NCA ECC controls ──────────────────────────────
# (framework, control_code, checkpoint_index, requirement, keywords, weight)

CHECKPOINTS = [
    # ━━━ Domain 1: Cybersecurity Governance & Strategy ━━━

    # ECC-1-1-1  Cybersecurity Governance (4)
    ("NCA ECC", "ECC-1-1-1", 1,
     "Cybersecurity policy approved by senior management or board",
     ["cybersecurity policy", "approved", "senior management", "board"], 1.0),
    ("NCA ECC", "ECC-1-1-1", 2,
     "CISO or equivalent role formally appointed",
     ["CISO", "chief information security officer", "appointed", "designated"], 1.0),
    ("NCA ECC", "ECC-1-1-1", 3,
     "Cybersecurity governance committee established",
     ["governance committee", "cybersecurity committee", "steering committee"], 0.8),
    ("NCA ECC", "ECC-1-1-1", 4,
     "Policy reviewed and updated at least annually",
     ["annual review", "policy review", "updated annually", "periodic review"], 0.8),

    # ECC-1-2-1  Cybersecurity Department (3)
    ("NCA ECC", "ECC-1-2-1", 1,
     "Dedicated cybersecurity department or function established",
     ["cybersecurity department", "security team", "security function", "security unit"], 1.0),
    ("NCA ECC", "ECC-1-2-1", 2,
     "Cybersecurity department reports to senior management",
     ["reports to", "reporting line", "senior management", "executive"], 0.8),
    ("NCA ECC", "ECC-1-2-1", 3,
     "Adequate staffing and budget allocated for cybersecurity",
     ["staffing", "budget", "resources", "cybersecurity budget", "headcount"], 0.8),

    # ECC-1-3-1  Roles & Responsibilities (3)
    ("NCA ECC", "ECC-1-3-1", 1,
     "Cybersecurity roles and responsibilities clearly defined",
     ["roles", "responsibilities", "duties", "accountable"], 1.0),
    ("NCA ECC", "ECC-1-3-1", 2,
     "Segregation of duties implemented for critical functions",
     ["segregation of duties", "separation of duties", "dual control"], 0.8),
    ("NCA ECC", "ECC-1-3-1", 3,
     "Accountability for cybersecurity assigned at each organizational level",
     ["accountability", "organizational level", "management accountability"], 0.8),

    # ECC-1-4-1  Policies & Procedures (4)
    ("NCA ECC", "ECC-1-4-1", 1,
     "Comprehensive cybersecurity policies documented",
     ["cybersecurity policies", "security policy", "information security policy"], 1.0),
    ("NCA ECC", "ECC-1-4-1", 2,
     "Procedures and standards for policy implementation exist",
     ["procedures", "standards", "guidelines", "implementation"], 1.0),
    ("NCA ECC", "ECC-1-4-1", 3,
     "Policies communicated to all relevant stakeholders",
     ["communicated", "distributed", "stakeholders", "awareness"], 0.8),
    ("NCA ECC", "ECC-1-4-1", 4,
     "Policy compliance monitoring mechanism in place",
     ["compliance monitoring", "policy compliance", "enforcement", "monitoring mechanism"], 0.8),

    # ECC-1-5-1  Awareness & Training (4)
    ("NCA ECC", "ECC-1-5-1", 1,
     "Security awareness program for all employees",
     ["awareness program", "security awareness", "employee awareness", "training program"], 1.0),
    ("NCA ECC", "ECC-1-5-1", 2,
     "Specialized training for IT and security staff",
     ["specialized training", "technical training", "security certification"], 0.8),
    ("NCA ECC", "ECC-1-5-1", 3,
     "Training conducted at least annually",
     ["annual training", "yearly training", "training schedule", "conducted annually"], 0.8),
    ("NCA ECC", "ECC-1-5-1", 4,
     "Training records and attendance maintained",
     ["training records", "attendance", "training log", "completion records"], 0.6),

    # ECC-1-6-1  Projects Security (3)
    ("NCA ECC", "ECC-1-6-1", 1,
     "Security requirements included in project lifecycle",
     ["project lifecycle", "security requirements", "SDLC", "project security"], 1.0),
    ("NCA ECC", "ECC-1-6-1", 2,
     "Security review performed before system deployment",
     ["security review", "pre-deployment", "go-live review", "deployment approval"], 0.8),
    ("NCA ECC", "ECC-1-6-1", 3,
     "Change management process includes security assessment",
     ["change management", "change control", "security assessment", "change review"], 0.8),

    # ━━━ Domain 2: Cybersecurity Defense ━━━

    # ECC-2-1-1  Asset Management (4)
    ("NCA ECC", "ECC-2-1-1", 1,
     "IT asset inventory maintained and up-to-date",
     ["asset inventory", "asset register", "asset list", "IT assets"], 1.0),
    ("NCA ECC", "ECC-2-1-1", 2,
     "Asset classification scheme implemented",
     ["asset classification", "classification scheme", "information classification"], 1.0),
    ("NCA ECC", "ECC-2-1-1", 3,
     "Asset owners formally assigned",
     ["asset owner", "ownership", "assigned owner", "responsible person"], 0.8),
    ("NCA ECC", "ECC-2-1-1", 4,
     "Asset handling and disposal procedures documented",
     ["asset handling", "disposal", "decommission", "sanitization", "media disposal"], 0.8),

    # ECC-2-2-1  Identity Management (3)
    ("NCA ECC", "ECC-2-2-1", 1,
     "Unique user IDs assigned to all users",
     ["unique user", "user ID", "individual account", "unique identifier"], 1.0),
    ("NCA ECC", "ECC-2-2-1", 2,
     "User provisioning and de-provisioning process defined",
     ["provisioning", "de-provisioning", "onboarding", "offboarding", "user lifecycle"], 1.0),
    ("NCA ECC", "ECC-2-2-1", 3,
     "Identity verification performed before granting access",
     ["identity verification", "identity validation", "background check", "verification"], 0.8),

    # ECC-2-2-2  Access Control (4)
    ("NCA ECC", "ECC-2-2-2", 1,
     "Access control policy based on least privilege principle",
     ["least privilege", "need to know", "access control policy", "minimum access"], 1.0),
    ("NCA ECC", "ECC-2-2-2", 2,
     "Access reviews conducted periodically",
     ["access review", "access recertification", "periodic review", "user access review"], 1.0),
    ("NCA ECC", "ECC-2-2-2", 3,
     "Privileged accounts identified and restricted",
     ["privileged account", "admin account", "administrator", "superuser", "restricted"], 0.8),
    ("NCA ECC", "ECC-2-2-2", 4,
     "Access rights revoked upon role change or termination",
     ["revoked", "terminated", "role change", "access removal", "offboarding"], 0.8),

    # ECC-2-2-3  Authentication (3)
    ("NCA ECC", "ECC-2-2-3", 1,
     "Multi-factor authentication (MFA) implemented for critical systems",
     ["MFA", "multi-factor", "two-factor", "2FA", "multi factor authentication"], 1.0),
    ("NCA ECC", "ECC-2-2-3", 2,
     "Password policy enforced with complexity requirements",
     ["password policy", "password complexity", "strong password", "password length"], 1.0),
    ("NCA ECC", "ECC-2-2-3", 3,
     "Session management controls implemented (timeout, lockout)",
     ["session timeout", "account lockout", "session management", "idle timeout"], 0.8),

    # ECC-2-3-1  System Protection (4)
    ("NCA ECC", "ECC-2-3-1", 1,
     "Endpoint protection (antivirus/EDR) deployed on all systems",
     ["antivirus", "endpoint protection", "EDR", "anti-malware", "endpoint detection"], 1.0),
    ("NCA ECC", "ECC-2-3-1", 2,
     "System hardening standards applied",
     ["hardening", "baseline", "CIS benchmark", "secure configuration", "system hardening"], 1.0),
    ("NCA ECC", "ECC-2-3-1", 3,
     "Patch management process defined with SLAs",
     ["patch management", "patching", "security updates", "patch cycle", "software update"], 1.0),
    ("NCA ECC", "ECC-2-3-1", 4,
     "Security configuration baselines documented",
     ["configuration baseline", "secure baseline", "golden image", "standard build"], 0.8),

    # ECC-2-4-1  Cryptography (4)
    ("NCA ECC", "ECC-2-4-1", 1,
     "Encryption standards and algorithms defined",
     ["encryption standard", "AES", "RSA", "cryptographic algorithm", "encryption policy"], 1.0),
    ("NCA ECC", "ECC-2-4-1", 2,
     "Data at rest encryption implemented for sensitive data",
     ["data at rest", "disk encryption", "database encryption", "storage encryption"], 1.0),
    ("NCA ECC", "ECC-2-4-1", 3,
     "Data in transit encryption (TLS/SSL) enforced",
     ["TLS", "SSL", "data in transit", "transport encryption", "HTTPS"], 1.0),
    ("NCA ECC", "ECC-2-4-1", 4,
     "Cryptographic key management procedures defined",
     ["key management", "key rotation", "key lifecycle", "KMS", "certificate management"], 0.8),

    # ECC-2-5-1  Email Security (3)
    ("NCA ECC", "ECC-2-5-1", 1,
     "Email filtering and anti-spam solution deployed",
     ["email filter", "anti-spam", "spam filter", "email gateway", "email security"], 1.0),
    ("NCA ECC", "ECC-2-5-1", 2,
     "SPF, DKIM, and DMARC configured for email domains",
     ["SPF", "DKIM", "DMARC", "email authentication", "sender policy"], 0.8),
    ("NCA ECC", "ECC-2-5-1", 3,
     "Email encryption used for sensitive communications",
     ["email encryption", "encrypted email", "S/MIME", "TLS email", "secure email"], 0.8),

    # ECC-2-6-1  Network Security (4)
    ("NCA ECC", "ECC-2-6-1", 1,
     "Firewalls deployed at all network boundaries",
     ["firewall", "network boundary", "perimeter", "next-gen firewall", "NGFW"], 1.0),
    ("NCA ECC", "ECC-2-6-1", 2,
     "Network segmentation implemented for critical systems",
     ["network segmentation", "VLAN", "segmentation", "zone", "DMZ"], 1.0),
    ("NCA ECC", "ECC-2-6-1", 3,
     "Intrusion detection or prevention system (IDS/IPS) deployed",
     ["IDS", "IPS", "intrusion detection", "intrusion prevention"], 0.8),
    ("NCA ECC", "ECC-2-6-1", 4,
     "Network traffic monitoring and analysis active",
     ["network monitoring", "traffic analysis", "NetFlow", "network traffic"], 0.8),

    # ECC-2-7-1  Mobile Security (3)
    ("NCA ECC", "ECC-2-7-1", 1,
     "Mobile device management (MDM) solution deployed",
     ["MDM", "mobile device management", "mobile management", "device management"], 1.0),
    ("NCA ECC", "ECC-2-7-1", 2,
     "Mobile device security policy defined",
     ["mobile policy", "BYOD", "mobile device policy", "mobile security"], 0.8),
    ("NCA ECC", "ECC-2-7-1", 3,
     "Remote wipe capability enabled for lost or stolen devices",
     ["remote wipe", "device wipe", "lost device", "stolen device"], 0.8),

    # ECC-2-8-1  Data Protection (4)
    ("NCA ECC", "ECC-2-8-1", 1,
     "Data classification policy defined and enforced",
     ["data classification", "information classification", "classification levels"], 1.0),
    ("NCA ECC", "ECC-2-8-1", 2,
     "Data loss prevention (DLP) controls implemented",
     ["DLP", "data loss prevention", "data leakage", "data exfiltration"], 1.0),
    ("NCA ECC", "ECC-2-8-1", 3,
     "Personal data protection measures in place (PDPL compliance)",
     ["personal data", "privacy", "PDPL", "data protection", "PII"], 0.8),
    ("NCA ECC", "ECC-2-8-1", 4,
     "Data retention and secure disposal procedures defined",
     ["data retention", "disposal", "data destruction", "retention schedule"], 0.8),

    # ECC-2-9-1  Web Security (3)
    ("NCA ECC", "ECC-2-9-1", 1,
     "Web application firewall (WAF) deployed",
     ["WAF", "web application firewall", "application firewall"], 1.0),
    ("NCA ECC", "ECC-2-9-1", 2,
     "Secure development lifecycle (SDLC) followed",
     ["SDLC", "secure development", "secure coding", "code review"], 1.0),
    ("NCA ECC", "ECC-2-9-1", 3,
     "OWASP Top 10 vulnerabilities assessed and mitigated",
     ["OWASP", "Top 10", "SQL injection", "XSS", "web vulnerability"], 0.8),

    # ECC-2-10-1  Physical Security (4)
    ("NCA ECC", "ECC-2-10-1", 1,
     "Physical access controls for data centers and server rooms",
     ["physical access", "data center", "server room", "access badge", "biometric"], 1.0),
    ("NCA ECC", "ECC-2-10-1", 2,
     "Visitor management procedures in place",
     ["visitor management", "visitor log", "escort", "visitor badge"], 0.8),
    ("NCA ECC", "ECC-2-10-1", 3,
     "CCTV surveillance for critical areas",
     ["CCTV", "surveillance", "camera", "video monitoring"], 0.8),
    ("NCA ECC", "ECC-2-10-1", 4,
     "Environmental controls (fire suppression, power backup)",
     ["fire suppression", "UPS", "power backup", "environmental control", "HVAC"], 0.8),

    # ━━━ Domain 3: Cybersecurity Resilience ━━━

    # ECC-3-1-1  Event Management (3)
    ("NCA ECC", "ECC-3-1-1", 1,
     "Security event logging enabled on all critical systems",
     ["event logging", "security log", "audit log", "logging enabled"], 1.0),
    ("NCA ECC", "ECC-3-1-1", 2,
     "Event correlation and analysis performed",
     ["event correlation", "log correlation", "SIEM", "log analysis"], 0.8),
    ("NCA ECC", "ECC-3-1-1", 3,
     "Event escalation procedures defined",
     ["escalation", "event escalation", "alert escalation", "notification"], 0.8),

    # ECC-3-2-1  Incident Management (4)
    ("NCA ECC", "ECC-3-2-1", 1,
     "Incident response plan documented and approved",
     ["incident response plan", "IRP", "incident management plan", "incident procedure"], 1.0),
    ("NCA ECC", "ECC-3-2-1", 2,
     "Incident response team (CSIRT/CERT) designated",
     ["incident response team", "CSIRT", "CERT", "incident team", "response team"], 1.0),
    ("NCA ECC", "ECC-3-2-1", 3,
     "Incident classification and severity scheme defined",
     ["incident classification", "severity level", "incident category", "priority matrix"], 0.8),
    ("NCA ECC", "ECC-3-2-1", 4,
     "Post-incident review and lessons learned process in place",
     ["post-incident", "lessons learned", "after action", "incident review", "root cause"], 0.8),

    # ECC-3-3-1  Monitoring (4)
    ("NCA ECC", "ECC-3-3-1", 1,
     "Security operations center (SOC) or monitoring function exists",
     ["SOC", "security operations center", "monitoring team", "security monitoring"], 1.0),
    ("NCA ECC", "ECC-3-3-1", 2,
     "24/7 monitoring for critical systems implemented",
     ["24/7", "continuous monitoring", "round the clock", "24x7", "real-time monitoring"], 1.0),
    ("NCA ECC", "ECC-3-3-1", 3,
     "SIEM or log analysis platform deployed",
     ["SIEM", "security information", "event management", "log platform", "Splunk"], 0.8),
    ("NCA ECC", "ECC-3-3-1", 4,
     "Alerting thresholds and correlation rules configured",
     ["alerting", "threshold", "correlation rule", "alert rule", "detection rule"], 0.8),

    # ECC-3-4-1  Vulnerability Management (3)
    ("NCA ECC", "ECC-3-4-1", 1,
     "Vulnerability scanning conducted regularly",
     ["vulnerability scan", "vulnerability assessment", "scanning", "Nessus", "Qualys"], 1.0),
    ("NCA ECC", "ECC-3-4-1", 2,
     "Vulnerability remediation SLAs defined by severity",
     ["remediation SLA", "patch SLA", "remediation timeline", "fix timeline"], 1.0),
    ("NCA ECC", "ECC-3-4-1", 3,
     "Critical vulnerabilities patched within defined timeline",
     ["critical patch", "emergency patch", "zero-day", "critical vulnerability"], 0.8),

    # ECC-3-4-2  Penetration Testing (3)
    ("NCA ECC", "ECC-3-4-2", 1,
     "Penetration testing conducted at least annually",
     ["penetration test", "pen test", "pentest", "ethical hacking", "red team"], 1.0),
    ("NCA ECC", "ECC-3-4-2", 2,
     "Penetration test scope covers all critical systems",
     ["test scope", "critical systems", "in-scope", "pentest scope"], 0.8),
    ("NCA ECC", "ECC-3-4-2", 3,
     "Remediation of penetration test findings tracked to closure",
     ["pentest findings", "remediation tracking", "finding closure"], 0.8),

    # ECC-3-5-1  Threat Management (3)
    ("NCA ECC", "ECC-3-5-1", 1,
     "Threat intelligence sources monitored and integrated",
     ["threat intelligence", "threat feed", "CTI", "threat source"], 1.0),
    ("NCA ECC", "ECC-3-5-1", 2,
     "Threat assessment process defined",
     ["threat assessment", "threat analysis", "threat evaluation", "threat landscape"], 0.8),
    ("NCA ECC", "ECC-3-5-1", 3,
     "Threat indicators integrated into monitoring and detection",
     ["IOC", "indicator of compromise", "threat indicator", "detection signature"], 0.8),

    # ECC-3-6-1  Log Management (4)
    ("NCA ECC", "ECC-3-6-1", 1,
     "Log retention policy defined with minimum 12 months retention",
     ["log retention", "12 months", "retention policy", "retention period"], 1.0),
    ("NCA ECC", "ECC-3-6-1", 2,
     "Logs protected from unauthorized access and tampering",
     ["log integrity", "tamper-proof", "log protection", "immutable log"], 1.0),
    ("NCA ECC", "ECC-3-6-1", 3,
     "Centralized log management system deployed",
     ["centralized log", "log aggregation", "log server", "syslog", "log collector"], 0.8),
    ("NCA ECC", "ECC-3-6-1", 4,
     "Log review procedures documented and followed",
     ["log review", "log analysis", "audit trail review", "log monitoring"], 0.8),

    # ━━━ Domain 4: Business Continuity ━━━

    # ECC-4-1-1  Business Continuity (4)
    ("NCA ECC", "ECC-4-1-1", 1,
     "Business continuity plan (BCP) documented and approved",
     ["business continuity", "BCP", "continuity plan", "continuity management"], 1.0),
    ("NCA ECC", "ECC-4-1-1", 2,
     "Business impact analysis (BIA) conducted",
     ["business impact", "BIA", "impact analysis", "critical process"], 1.0),
    ("NCA ECC", "ECC-4-1-1", 3,
     "BCP testing performed at least annually",
     ["BCP test", "continuity test", "tabletop exercise", "BCP drill"], 0.8),
    ("NCA ECC", "ECC-4-1-1", 4,
     "Recovery time objectives (RTO) and recovery point objectives (RPO) defined",
     ["RTO", "RPO", "recovery time", "recovery point", "recovery objective"], 0.8),

    # ECC-4-2-1  Disaster Recovery (3)
    ("NCA ECC", "ECC-4-2-1", 1,
     "Disaster recovery plan (DRP) documented",
     ["disaster recovery", "DRP", "DR plan", "recovery plan"], 1.0),
    ("NCA ECC", "ECC-4-2-1", 2,
     "DR site or alternative processing facility available",
     ["DR site", "disaster recovery site", "hot site", "warm site", "alternative site"], 1.0),
    ("NCA ECC", "ECC-4-2-1", 3,
     "DR testing conducted periodically",
     ["DR test", "disaster recovery test", "DR drill", "failover test"], 0.8),

    # ECC-4-3-1  Backup (3)
    ("NCA ECC", "ECC-4-3-1", 1,
     "Backup policy and procedures defined",
     ["backup policy", "backup procedure", "backup schedule", "backup strategy"], 1.0),
    ("NCA ECC", "ECC-4-3-1", 2,
     "Regular backups performed and verified",
     ["regular backup", "daily backup", "automated backup", "backup verification"], 1.0),
    ("NCA ECC", "ECC-4-3-1", 3,
     "Backup restoration testing conducted periodically",
     ["restore test", "backup test", "restoration test", "recovery test"], 0.8),

    # ━━━ Domain 5: Third Party & Cloud ━━━

    # ECC-5-1-1  Third Party Security (3)
    ("NCA ECC", "ECC-5-1-1", 1,
     "Third party risk assessment conducted before engagement",
     ["third party risk", "vendor risk", "supplier risk", "vendor assessment"], 1.0),
    ("NCA ECC", "ECC-5-1-1", 2,
     "Security requirements included in vendor contracts",
     ["vendor contract", "SLA", "security clause", "contractual", "NDA"], 1.0),
    ("NCA ECC", "ECC-5-1-1", 3,
     "Third party access monitored and reviewed periodically",
     ["third party access", "vendor access", "supplier access", "third party review"], 0.8),

    # ECC-5-2-1  Cloud Security (3)
    ("NCA ECC", "ECC-5-2-1", 1,
     "Cloud security policy defined",
     ["cloud security", "cloud policy", "cloud computing policy"], 1.0),
    ("NCA ECC", "ECC-5-2-1", 2,
     "Cloud service provider risk assessment conducted",
     ["cloud provider", "CSP", "cloud risk", "provider assessment"], 1.0),
    ("NCA ECC", "ECC-5-2-1", 3,
     "Data sovereignty and residency requirements addressed",
     ["data sovereignty", "data residency", "data location", "Saudi Arabia", "local hosting"], 0.8),

    # ECC-5-3-1  ICS Security (3)
    ("NCA ECC", "ECC-5-3-1", 1,
     "ICS/SCADA security policy defined",
     ["ICS", "SCADA", "industrial control", "OT security", "operational technology"], 1.0),
    ("NCA ECC", "ECC-5-3-1", 2,
     "ICS network segregated from corporate IT network",
     ["ICS network", "OT network", "air gap", "ICS segmentation", "IT/OT separation"], 1.0),
    ("NCA ECC", "ECC-5-3-1", 3,
     "ICS-specific monitoring and incident response procedures",
     ["ICS monitoring", "SCADA monitoring", "OT incident", "ICS incident response"], 0.8),
]


def seed_checkpoints(db):
    """Create control_checkpoints table and seed 107 checkpoints. Idempotent."""
    print("Checking control_checkpoints table...")

    db.execute(sql_text("""
        CREATE TABLE IF NOT EXISTS control_checkpoints (
            id TEXT PRIMARY KEY,
            framework TEXT NOT NULL,
            control_code TEXT NOT NULL,
            checkpoint_index INTEGER NOT NULL,
            requirement TEXT NOT NULL,
            keywords JSONB DEFAULT '[]'::jsonb,
            weight FLOAT DEFAULT 1.0,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """))
    db.commit()

    # Ensure "NCA ECC" exists in frameworks table FIRST (FK target)
    fw_row = db.execute(sql_text(
        "SELECT id FROM frameworks WHERE name='NCA ECC'"
    )).fetchone()
    if fw_row:
        nca_fw_id = fw_row[0]
    else:
        nca_fw_id = str(uuid.uuid4())
        db.execute(sql_text(
            "INSERT INTO frameworks (id, name, description) "
            "VALUES (:id, 'NCA ECC', "
            "'National Cybersecurity Authority Essential Cybersecurity Controls')"
        ), {"id": nca_fw_id})
        db.commit()
        print(f"  Created 'NCA ECC' framework (id={nca_fw_id[:8]}...)")

    count = db.execute(sql_text(
        "SELECT COUNT(*) FROM control_checkpoints"
    )).fetchone()[0]

    if count >= len(CHECKPOINTS):
        print(f"  Already seeded ({count} checkpoints). Skipping.")
        return

    # Clear and re-seed
    db.execute(sql_text("DELETE FROM control_checkpoints"))

    # Build framework name → id map for FK
    fw_id_map = {"NCA ECC": nca_fw_id}

    for fw, code, idx, req, kw, weight in CHECKPOINTS:
        db.execute(sql_text("""
            INSERT INTO control_checkpoints
            (id, framework, control_code, checkpoint_index,
             requirement, keywords, weight)
            VALUES (:id, :fw, :code, :idx, :req, :kw, :weight)
        """), {
            "id": str(uuid.uuid4()),
            "fw": fw_id_map.get(fw, fw), "code": code, "idx": idx,
            "req": req, "kw": json.dumps(kw), "weight": weight,
        })

    db.commit()
    codes = set(c[1] for c in CHECKPOINTS)
    print(f"  Seeded {len(CHECKPOINTS)} checkpoints across {len(codes)} controls.")

    # Seed control_library with framework_id FK
    existing = db.execute(sql_text(
        "SELECT COUNT(*) FROM control_library WHERE framework_id=:fwid"
    ), {"fwid": nca_fw_id}).fetchone()[0]

    if existing < len(CONTROL_TITLES):
        db.execute(sql_text(
            "DELETE FROM control_library WHERE framework_id=:fwid"
        ), {"fwid": nca_fw_id})
        for code, title in CONTROL_TITLES.items():
            db.execute(sql_text("""
                INSERT INTO control_library
                (id, framework_id, control_code, title, keywords,
                 severity_if_missing, created_at)
                VALUES (:id, :fwid, :code, :title, :kw, 'High', NOW())
            """), {
                "id": str(uuid.uuid4()),
                "fwid": nca_fw_id,
                "code": code,
                "title": title,
                "kw": json.dumps([code, title.lower()]),
            })
        db.commit()
        print(f"  Seeded {len(CONTROL_TITLES)} control_library entries.")

    # Always sync: create control_library entries for any orphan checkpoint codes
    ensure_control_library_sync(db)


def ensure_control_library_sync(db):
    """Auto-create control_library entries for any checkpoint control_codes
    that don't have a matching entry. Runs on every startup."""
    from datetime import datetime

    # cp.framework now stores framework_id (UUID), not name
    missing = db.execute(sql_text("""
        SELECT DISTINCT cp.framework, cp.control_code
        FROM control_checkpoints cp
        WHERE NOT EXISTS (
            SELECT 1 FROM control_library cl
            WHERE cl.control_code = cp.control_code
            AND cl.framework_id = cp.framework
        )
    """)).fetchall()

    if not missing:
        return

    print(f"  Syncing {len(missing)} missing control_library entries...")

    for fw_id, control_code in missing:
        # Check race condition
        exists = db.execute(sql_text(
            "SELECT id FROM control_library "
            "WHERE control_code = :cc AND framework_id = :fid"
        ), {"cc": control_code, "fid": fw_id}).fetchone()

        if exists:
            continue

        # Use checkpoint requirement as title, checkpoint keywords as keywords
        cp_row = db.execute(sql_text("""
            SELECT requirement, keywords FROM control_checkpoints
            WHERE framework = :fwid AND control_code = :cc
            LIMIT 1
        """), {"fwid": fw_id, "cc": control_code}).fetchone()

        title = CONTROL_TITLES.get(control_code, cp_row[0] if cp_row else control_code)
        keywords = cp_row[1] if cp_row else []

        # Get framework name for logging
        fw_name_row = db.execute(sql_text(
            "SELECT name FROM frameworks WHERE id = :fid"
        ), {"fid": fw_id}).fetchone()
        fw_display = fw_name_row[0] if fw_name_row else fw_id[:8]

        db.execute(sql_text("""
            INSERT INTO control_library
            (id, control_code, title, keywords, severity_if_missing,
             framework_id, created_at)
            VALUES (:id, :cc, :title, :kw, 'High', :fid, :cat)
        """), {
            "id": str(uuid.uuid4()),
            "cc": control_code,
            "title": title,
            "kw": json.dumps(keywords if isinstance(keywords, list) else []),
            "fid": fw_id,
            "cat": datetime.utcnow(),
        })
        print(f"    Created: {control_code} in {fw_display}")

    db.commit()
    print(f"  Synced {len(missing)} control_library entries")
