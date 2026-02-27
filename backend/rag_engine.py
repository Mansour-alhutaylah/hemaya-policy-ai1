"""
Hemaya RAG Engine — Powers all AI features using OpenAI GPT-4o-mini.
"""
import json
import uuid
import httpx
from datetime import datetime
from sqlalchemy import text as sql_text
from backend.ai_config import OPENAI_API_KEY, MODELS, TOP_K_RETRIEVAL, TOP_K_RERANK
from backend.vector_store import get_embeddings, search_similar_chunks


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE: Call GPT-4o-mini
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def call_llm(system_prompt: str, user_prompt: str, force_json: bool = True) -> str:
    """Call OpenAI GPT-4o-mini. Returns the response text."""
    body = {
        "model": MODELS["llm"]["name"],
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": MODELS["llm"]["temperature"],
        "max_tokens": MODELS["llm"]["max_tokens"],
    }
    if force_json:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        if response.status_code != 200:
            raise Exception(f"OpenAI error ({response.status_code}): {response.text[:300]}")

        data = response.json()
        return data["choices"][0]["message"]["content"]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RERANK: Simple similarity-based (no separate model needed)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def rerank_chunks(query: str, chunks: list, top_k: int = TOP_K_RERANK) -> list:
    """Return top-k chunks by similarity. GPT-4o-mini is smart enough to
    work with these directly without a separate reranker model."""
    return chunks[:top_k]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ANALYSIS: Analyze one control
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def analyze_control_compliance(
    db, policy_id: str, control: dict, framework_name: str
) -> dict:
    """Run full RAG analysis for a single control against a policy."""

    control_query = f"{control['control_code']}: {control['title']}"

    # Get framework reference
    framework_text = ""
    query_embedding = None
    try:
        from backend.framework_loader import get_framework_context
        query_embedding = (await get_embeddings([control_query]))[0]
        framework_context = get_framework_context(db, framework_name, query_embedding, top_k=3)
        framework_text = "\n---\n".join([c["text"] for c in framework_context])
    except Exception:
        pass

    if not framework_text.strip():
        keywords = control.get("keywords", [])
        if isinstance(keywords, str):
            try:
                keywords = json.loads(keywords)
            except Exception:
                keywords = []
        framework_text = (
            f"Control: {control['control_code']} - {control['title']}\n"
            f"Keywords: {', '.join(keywords) if keywords else 'N/A'}\n"
            f"Severity if missing: {control.get('severity_if_missing', 'High')}"
        )

    # Get policy text (reuse embedding or create new)
    if query_embedding is None:
        query_embedding = (await get_embeddings([control_query]))[0]

    policy_chunks = search_similar_chunks(
        db, query_embedding, policy_id=policy_id, top_k=TOP_K_RETRIEVAL
    )
    best_chunks = await rerank_chunks(control_query, policy_chunks, top_k=TOP_K_RERANK)
    policy_text = "\n---\n".join([c["text"] for c in best_chunks])

    # Build prompts
    system_prompt = """You are a senior cybersecurity compliance auditor with 15 years of experience
auditing Saudi Arabian organizations against NCA ECC, ISO 27001, and NIST 800-53.

You are methodical, precise, and thorough. A policy is only "Compliant" if it FULLY
and EXPLICITLY addresses every aspect of the control requirement.

METHOD:
1. Break the control into specific sub-requirements
2. For each, search the policy for evidence
3. Overall status = WEAKEST sub-requirement

RULES:
- "Should" is WEAKER than "shall"/"must" — mark as Partial
- Generic statements like "follow best practices" = NOT compliant
- Topic mentioned but specifics missing = Partial
- Topic not mentioned at all = Non-Compliant

Respond with valid JSON:
{
  "status": "Compliant" | "Partial" | "Non-Compliant",
  "confidence": 0.0 to 1.0,
  "sub_requirements": [
    {"requirement": "text", "status": "Met"|"Partially Met"|"Not Met",
     "policy_evidence": "quote or 'No evidence found'", "gap": "what's missing or 'None'"}
  ],
  "overall_assessment": "2-3 sentence auditor summary",
  "gaps_detail": "Detailed explanation of what's missing and why it matters",
  "risk_if_not_addressed": "Specific consequences of this gap",
  "recommendations": [
    {"action": "specific fix", "priority": "Critical"|"High"|"Medium"|"Low", "effort": "Low"|"Medium"|"High"}
  ]
}"""

    user_prompt = f"""CONTROL: {control['control_code']} - {control['title']}
FRAMEWORK: {framework_name}
SEVERITY IF MISSING: {control.get('severity_if_missing', 'High')}

FRAMEWORK REQUIREMENT:
{framework_text}

ORGANIZATION'S POLICY:
{policy_text if policy_text.strip() else '[No relevant policy text found]'}

Analyze compliance. Break into sub-requirements and assess each."""

    try:
        llm_response = await call_llm(system_prompt, user_prompt, force_json=True)
        result = json.loads(llm_response)
    except Exception as e:
        result = {
            "status": "Non-Compliant" if not policy_text.strip() else "Partial",
            "confidence": 0.2,
            "sub_requirements": [],
            "overall_assessment": f"Analysis error: {str(e)[:200]}",
            "gaps_detail": "Manual review required",
            "risk_if_not_addressed": "Cannot assess",
            "recommendations": [{"action": "Review manually", "priority": "High", "effort": "Low"}],
        }

    # Ensure all fields exist
    result.setdefault("status", "Non-Compliant")
    result.setdefault("confidence", 0.5)
    result.setdefault("sub_requirements", [])
    result.setdefault("overall_assessment", "")
    result.setdefault("gaps_detail", "")
    result.setdefault("risk_if_not_addressed", "")
    result.setdefault("recommendations", [])

    if result["status"] not in {"Compliant", "Partial", "Non-Compliant"}:
        result["status"] = "Non-Compliant"

    result["control_code"] = control["control_code"]
    result["control_title"] = control["title"]
    result["framework"] = framework_name
    result["severity_if_missing"] = control.get("severity_if_missing", "High")

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FULL ANALYSIS: All controls, all frameworks
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_full_analysis(db, policy_id: str, frameworks: list) -> dict:
    """Analyze a policy against all controls in selected frameworks.
    Creates ComplianceResult, Gap, MappingReview, AIInsight, and AuditLog records."""

    all_results = {}
    analysis_start = datetime.utcnow()

    for framework_name in frameworks:
        controls = db.execute(sql_text(
            "SELECT id, control_code, title, keywords, severity_if_missing "
            "FROM control_library WHERE framework = :fw"
        ), {"fw": framework_name}).fetchall()

        if not controls:
            all_results[framework_name] = {"error": f"No controls found for {framework_name}"}
            continue

        framework_results = []
        for ctrl in controls:
            control_dict = {
                "control_code": ctrl[1],
                "title": ctrl[2],
                "keywords": ctrl[3],
                "severity_if_missing": ctrl[4],
            }
            result = await analyze_control_compliance(db, policy_id, control_dict, framework_name)
            framework_results.append(result)

        # Calculate scores
        total = len(framework_results)
        compliant = sum(1 for r in framework_results if r["status"] == "Compliant")
        partial = sum(1 for r in framework_results if r["status"] == "Partial")
        missing = sum(1 for r in framework_results if r["status"] == "Non-Compliant")
        score = ((compliant + partial * 0.5) / total * 100) if total > 0 else 0.0
        duration = (datetime.utcnow() - analysis_start).total_seconds()
        status_label = "Compliant" if score >= 80 else "Partially Compliant" if score >= 60 else "Not Compliant"

        # ── Save ComplianceResult ──
        result_id = str(uuid.uuid4())
        db.execute(sql_text("""
            INSERT INTO compliance_results
            (id, policy_id, framework, compliance_score, controls_covered,
             controls_partial, controls_missing, status, analyzed_at,
             analysis_duration, details)
            VALUES (:id, :pid, :fw, :score, :covered, :partial, :missing,
                    :status, :at, :dur, :details)
        """), {
            "id": result_id,
            "pid": policy_id,
            "fw": framework_name,
            "score": round(score, 1),
            "covered": compliant,
            "partial": partial,
            "missing": missing,
            "status": status_label,
            "at": datetime.utcnow(),
            "dur": round(duration, 2),
            "details": json.dumps({"per_control": framework_results}),
        })

        # ── Save Gaps for Partial/Non-Compliant controls ──
        for r in framework_results:
            if r["status"] in ("Non-Compliant", "Partial"):
                recs = r.get("recommendations", [])
                remediation_text = "\n".join(
                    f"[{rec.get('priority', 'Medium')}] {rec.get('action', '')}"
                    for rec in recs
                ) if recs else "Manual review required"

                gap_severity = (
                    recs[0].get("priority", r.get("severity_if_missing", "High"))
                    if recs else r.get("severity_if_missing", "High")
                )

                db.execute(sql_text("""
                    INSERT INTO gaps
                    (id, policy_id, framework, control_id, control_name,
                     severity, status, description, remediation, created_at)
                    VALUES (:id, :pid, :fw, :cid, :cname, :sev, :stat,
                            :desc, :rem, :cat)
                """), {
                    "id": str(uuid.uuid4()),
                    "pid": policy_id,
                    "fw": framework_name,
                    "cid": r["control_code"],
                    "cname": r["control_title"],
                    "sev": gap_severity,
                    "stat": "Open",
                    "desc": r.get("gaps_detail", "Gap identified during analysis"),
                    "rem": remediation_text,
                    "cat": datetime.utcnow(),
                })

        # ── Save MappingReviews for ALL controls ──
        for r in framework_results:
            evidence = "\n".join(
                sr.get("policy_evidence", "")
                for sr in r.get("sub_requirements", [])
                if sr.get("policy_evidence") and sr["policy_evidence"] != "No evidence found"
            ) or "No direct evidence found"

            db.execute(sql_text("""
                INSERT INTO mapping_reviews
                (id, policy_id, control_id, framework, evidence_snippet,
                 confidence_score, ai_rationale, decision, created_at)
                VALUES (:id, :pid, :cid, :fw, :ev, :conf, :rat, :dec, :cat)
            """), {
                "id": str(uuid.uuid4()),
                "pid": policy_id,
                "cid": r["control_code"],
                "fw": framework_name,
                "ev": evidence,
                "conf": r.get("confidence", 0.5),
                "rat": r.get("overall_assessment", ""),
                "dec": "Accepted" if r["status"] == "Compliant" else "Pending",
                "cat": datetime.utcnow(),
            })

        db.commit()

        # ── Update policy status ──
        db.execute(sql_text("""
            UPDATE policies SET status = 'analyzed', last_analyzed_at = :now
            WHERE id = :pid
        """), {"now": datetime.utcnow(), "pid": policy_id})
        db.commit()

        all_results[framework_name] = {
            "score": round(score, 1),
            "total_controls": total,
            "compliant": compliant,
            "partial": partial,
            "non_compliant": missing,
        }

    # ── Generate AI Insights after all frameworks analyzed ──
    await generate_ai_insights(db, policy_id, all_results)

    # ── Log to audit trail ──
    db.execute(sql_text("""
        INSERT INTO audit_logs (id, actor, action, target_type, target_id, details, timestamp)
        VALUES (:id, :actor, :action, :tt, :tid, :details, :ts)
    """), {
        "id": str(uuid.uuid4()),
        "actor": "system",
        "action": "analyze_policy",
        "tt": "policy",
        "tid": policy_id,
        "details": json.dumps({
            "frameworks": frameworks,
            "results": {
                fw: {"score": r.get("score", 0)}
                for fw, r in all_results.items()
                if isinstance(r, dict)
            },
        }),
        "ts": datetime.utcnow(),
    })
    db.commit()

    return all_results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AI INSIGHTS: Generate after analysis
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def generate_ai_insights(db, policy_id: str, analysis_results: dict):
    """Generate AI insights based on analysis results. Powers the AI Insights page."""

    # Build context from results
    context = "Analysis Results:\n"
    for fw, data in analysis_results.items():
        if isinstance(data, dict) and "score" in data:
            context += (
                f"  {fw}: {data['score']}% "
                f"({data.get('compliant', 0)} compliant, "
                f"{data.get('partial', 0)} partial, "
                f"{data.get('non_compliant', 0)} missing)\n"
            )

    # Get open gaps for context
    gaps = db.execute(sql_text("""
        SELECT framework, control_id, control_name, severity, description
        FROM gaps WHERE policy_id = :pid AND status = 'Open'
        ORDER BY CASE severity
            WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
            WHEN 'Medium' THEN 3 ELSE 4 END
        LIMIT 20
    """), {"pid": policy_id}).fetchall()

    if gaps:
        context += "\nTop Gaps:\n"
        for g in gaps:
            context += f"  [{g[3]}] {g[0]} {g[1]} - {g[2]}: {str(g[4])[:150]}\n"

    system_prompt = """You are a cybersecurity compliance advisor. Based on the analysis
results, generate 3-5 actionable insights. Each insight should identify a pattern,
trend, or critical issue and provide specific advice.

Respond with JSON:
{
  "insights": [
    {
      "title": "Short descriptive title",
      "description": "2-3 sentence explanation with specific details and actions",
      "priority": "Critical" | "High" | "Medium" | "Low",
      "insight_type": "gap" | "policy" | "controls" | "trend",
      "confidence": 0.0 to 1.0
    }
  ]
}"""

    try:
        response = await call_llm(system_prompt, context, force_json=True)
        insights_data = json.loads(response)

        for insight in insights_data.get("insights", []):
            db.execute(sql_text("""
                INSERT INTO ai_insights
                (id, policy_id, insight_type, title, description, priority,
                 confidence, status, created_at)
                VALUES (:id, :pid, :type, :title, :desc, :pri, :conf, :stat, :cat)
            """), {
                "id": str(uuid.uuid4()),
                "pid": policy_id,
                "type": insight.get("insight_type", "gap"),
                "title": insight.get("title", ""),
                "desc": insight.get("description", ""),
                "pri": insight.get("priority", "Medium"),
                "conf": insight.get("confidence", 0.7),
                "stat": "New",
                "cat": datetime.utcnow(),
            })
        db.commit()
    except Exception as e:
        print(f"⚠️ Insight generation warning: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHAT: AI Assistant with full context
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def chat_with_context(db, message: str, policy_id: str = None) -> str:
    """RAG-powered chat. Uses policy text, framework knowledge, and analysis results."""

    query_embedding = (await get_embeddings([message]))[0]

    # Policy context
    policy_context = ""
    chunks = search_similar_chunks(db, query_embedding, policy_id=policy_id, top_k=10)
    if chunks:
        policy_context = "\n---\n".join([c["text"] for c in chunks[:5]])

    # Framework context
    framework_context = ""
    try:
        from backend.framework_loader import get_framework_context
        for fw in ["NCA ECC", "ISO 27001", "NIST 800-53"]:
            fw_chunks = get_framework_context(db, fw, query_embedding, top_k=2)
            if fw_chunks:
                framework_context += f"\n[{fw}]:\n"
                framework_context += "\n".join([c["text"] for c in fw_chunks])
    except Exception:
        pass

    # Analysis results context
    analysis_context = ""
    try:
        results = db.execute(sql_text("""
            SELECT framework, compliance_score, controls_covered,
                   controls_partial, controls_missing
            FROM compliance_results ORDER BY analyzed_at DESC LIMIT 10
        """)).fetchall()
        if results:
            analysis_context = "COMPLIANCE SCORES:\n"
            for r in results:
                analysis_context += (
                    f"  {r[0]}: {r[1]}% "
                    f"({r[2]} covered, {r[3]} partial, {r[4]} missing)\n"
                )

        gaps_data = db.execute(sql_text("""
            SELECT framework, control_id, control_name, severity, description
            FROM gaps WHERE status = 'Open'
            ORDER BY CASE severity
                WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                WHEN 'Medium' THEN 3 ELSE 4 END
            LIMIT 15
        """)).fetchall()
        if gaps_data:
            analysis_context += "\nOPEN GAPS:\n"
            for g in gaps_data:
                analysis_context += (
                    f"  [{g[3]}] {g[0]} {g[1]} - {g[2]}: {str(g[4])[:150]}\n"
                )
    except Exception:
        pass

    system_prompt = """You are Hemaya AI, a senior cybersecurity compliance advisor
for Saudi Arabian organizations. You specialize in NCA ECC, ISO 27001, and NIST 800-53.

You have access to: the organization's policies, framework requirements, and
compliance analysis results.

Rules:
- Reference specific control IDs (ECC-2-2-3, A.8.5, IA-2)
- Quote from actual policy text when relevant
- Give specific, actionable advice — never generic
- If asked about scores, explain what drives them
- Respond in the same language as the question (Arabic or English)
- When suggesting improvements, estimate the score impact"""

    user_prompt = f"""POLICY CONTEXT:
{policy_context if policy_context else '[No policies uploaded yet]'}

FRAMEWORK REFERENCE:
{framework_context if framework_context else '[No framework docs loaded]'}

ANALYSIS RESULTS:
{analysis_context if analysis_context else '[No analysis run yet]'}

QUESTION: {message}"""

    return await call_llm(system_prompt, user_prompt, force_json=False)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIMULATION: What-if score projection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def run_simulation(db, policy_id: str, selected_controls: list) -> dict:
    """Simulate score improvement if selected controls are implemented.
    Powers the Simulation page."""

    # Get current results
    results = db.execute(sql_text("""
        SELECT framework, compliance_score, controls_covered,
               controls_partial, controls_missing
        FROM compliance_results
        WHERE policy_id = :pid
        ORDER BY analyzed_at DESC
    """), {"pid": policy_id}).fetchall()

    if not results:
        return {"error": "No analysis results found. Run analysis first."}

    simulation = {}
    seen_frameworks = set()

    for r in results:
        fw = r[0]
        # Use only the most recent result per framework
        if fw in seen_frameworks:
            continue
        seen_frameworks.add(fw)

        current_score = r[1] or 0
        covered = r[2] or 0
        part = r[3] or 0
        miss = r[4] or 0
        total = covered + part + miss

        # Count how many selected controls are open gaps in this framework
        fixed = 0
        if selected_controls:
            try:
                gaps_fixed = db.execute(sql_text("""
                    SELECT COUNT(*) FROM gaps
                    WHERE policy_id = :pid AND framework = :fw
                    AND control_id = ANY(:controls) AND status = 'Open'
                """), {
                    "pid": policy_id,
                    "fw": fw,
                    "controls": selected_controls,
                }).fetchone()
                fixed = gaps_fixed[0] if gaps_fixed else 0
            except Exception:
                # Fallback: estimate based on count
                fixed = min(len(selected_controls), miss)

        # Project new score
        new_covered = min(total, covered + fixed)
        new_partial = max(0, part)
        new_missing = max(0, total - new_covered - new_partial)
        new_score = ((new_covered + new_partial * 0.5) / total * 100) if total > 0 else 0

        simulation[fw] = {
            "current_score": round(current_score, 1),
            "projected_score": round(new_score, 1),
            "improvement": round(new_score - current_score, 1),
            "gaps_fixed": fixed,
            "controls_total": total,
        }

    return simulation


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EXPLAINABILITY: Get detailed control explanation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def explain_mapping(db, mapping_id: str) -> dict:
    """Generate detailed explanation for a specific mapping decision.
    Powers the Explainability (XAI) page."""

    mapping = db.execute(sql_text("""
        SELECT control_id, framework, evidence_snippet, confidence_score,
               ai_rationale, decision, policy_id
        FROM mapping_reviews WHERE id = :mid
    """), {"mid": mapping_id}).fetchone()

    if not mapping:
        return {"error": "Mapping not found"}

    system_prompt = """You are explaining an AI compliance decision to a human reviewer.
Be transparent about why the decision was made, what evidence was found,
and what the confidence level means.

Respond with JSON:
{
  "explanation": "Plain language explanation of the decision",
  "evidence_analysis": "How the evidence supports or contradicts the decision",
  "confidence_breakdown": "Why confidence is at this level",
  "alternative_interpretation": "Could this be interpreted differently?",
  "reviewer_guidance": "What should the human reviewer look for"
}"""

    user_prompt = f"""Control: {mapping[0]} ({mapping[1]})
Evidence found: {mapping[2]}
AI Rationale: {mapping[4]}
Confidence: {mapping[3]}
Decision: {mapping[5]}

Explain this decision in detail."""

    try:
        response = await call_llm(system_prompt, user_prompt, force_json=True)
        return json.loads(response)
    except Exception as e:
        return {"explanation": f"Could not generate explanation: {str(e)}"}
