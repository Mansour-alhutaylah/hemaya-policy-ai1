import os
import json
import uuid
import time
import asyncio
import httpx
from datetime import datetime
from sqlalchemy import text as sql_text
from backend.vector_store import get_embeddings, search_similar_chunks, store_chunks_with_embeddings

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# ── GPT-4o-mini ──────────────────────────────────────────────────────────────

async def call_llm(system, user, force_json=True):
    body = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": 0.1,
        "max_tokens": 1500,
    }
    if force_json:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}",
                     "Content-Type": "application/json"},
            json=body,
        )
        if r.status_code != 200:
            raise Exception(f"GPT error {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]


# ── ANALYSIS: Single control ─────────────────────────────────────────────────

AUDITOR = """You are a senior cybersecurity compliance auditor (15 years experience)
specializing in Saudi NCA ECC, ISO 27001:2022, NIST 800-53 Rev 5.

METHOD:
1. Break the control into 2-5 testable sub-requirements
2. For each, find EXACT evidence in the policy (quote it)
3. Never invent evidence -- if not found say "No evidence found"
4. Overall: ALL met="Compliant", SOME="Partial", NONE="Non-Compliant"

RULES:
- "should" is weaker than "shall"/"must" -> Partial
- Generic "best practices" without specifics -> Not compliant
- Topic mentioned but details missing -> Partial
- Topic absent -> Non-Compliant

Return ONLY JSON:
{
  "status": "Compliant"|"Partial"|"Non-Compliant",
  "confidence": 0.0-1.0,
  "sub_requirements": [
    {"requirement":"what framework requires",
     "status":"Met"|"Partially Met"|"Not Met",
     "policy_evidence":"exact quote or 'No evidence found'",
     "gap":"what is missing or 'None'"}
  ],
  "overall_assessment": "3-4 sentence auditor summary explaining what IS and ISN'T covered",
  "gaps_detail": "Detailed paragraph: every gap with specific references to what framework requires vs what policy says",
  "risk_if_not_addressed": "Concrete consequences (not just 'security risk')",
  "recommendations": [
    {"action":"specific fix with section reference",
     "priority":"Critical"|"High"|"Medium"|"Low",
     "effort":"Low"|"Medium"|"High"}
  ]
}"""


async def analyze_one(db, policy_id, control, framework, embedding):
    """Analyze a single control using a pre-computed embedding."""
    t0 = time.time()

    # Framework reference context
    t1 = time.time()
    fw_text = ""
    try:
        from backend.framework_loader import get_framework_context
        fc = get_framework_context(db, framework, embedding, top_k=3)
        fw_text = "\n---\n".join([c["text"] for c in fc])
    except Exception:
        pass
    fw_time = round(time.time() - t1, 2)

    if not fw_text.strip():
        kw = control.get("keywords", [])
        if isinstance(kw, str):
            try:
                kw = json.loads(kw)
            except Exception:
                kw = []
        fw_text = (f"{control['control_code']} - {control['title']}\n"
                   f"Keywords: {', '.join(kw) if kw else 'N/A'}")

    # Policy text from vector search
    t1 = time.time()
    chunks = search_similar_chunks(db, embedding, policy_id=policy_id, top_k=20)
    # For small policies, send ALL chunks so nothing is missed
    # For large policies, keep top 10 to stay within token limits
    max_chunks = min(len(chunks), 15)
    pol_text = "\n---\n".join([c["text"] for c in chunks[:max_chunks]])
    search_time = round(time.time() - t1, 2)

    user = f"""CONTROL: {control['control_code']} - {control['title']}
FRAMEWORK: {framework}
SEVERITY: {control.get('severity_if_missing', 'High')}

REQUIREMENT:
{fw_text}

POLICY TEXT:
{pol_text if pol_text.strip() else '[NO policy text found -- mark Non-Compliant]'}"""

    # GPT call
    t1 = time.time()
    try:
        r = await call_llm(AUDITOR, user)
        result = json.loads(r)
    except Exception as e:
        result = {
            "status": "Non-Compliant" if not pol_text.strip() else "Partial",
            "confidence": 0.1,
            "sub_requirements": [],
            "overall_assessment": f"Error: {str(e)[:200]}",
            "gaps_detail": "Manual review required",
            "risk_if_not_addressed": "Unknown",
            "recommendations": [{"action": "Review manually",
                                  "priority": "High", "effort": "Low"}],
        }
    gpt_time = round(time.time() - t1, 2)

    total_time = round(time.time() - t0, 2)
    print(f"    {control['control_code']}: fw={fw_time}s search={search_time}s gpt={gpt_time}s total={total_time}s")

    result.setdefault("status", "Non-Compliant")
    result.setdefault("confidence", 0.5)
    result.setdefault("sub_requirements", [])
    result.setdefault("overall_assessment", "")
    result.setdefault("gaps_detail", "")
    result.setdefault("risk_if_not_addressed", "")
    result.setdefault("recommendations", [])
    result["control_code"] = control["control_code"]
    result["control_title"] = control["title"]
    result["framework"] = framework
    result["severity_if_missing"] = control.get("severity_if_missing", "High")
    return result


# ── FULL ANALYSIS ─────────────────────────────────────────────────────────────

async def run_full_analysis(db, policy_id, frameworks):
    """Analyze policy against all controls. Batch embeds for speed. Saves everything to DB."""
    t0 = time.time()
    print(f"\n{'='*50}")
    print(f"ANALYSIS STARTED at {time.strftime('%H:%M:%S')}")
    print(f"{'='*50}")

    # Verify embeddings exist
    t1 = time.time()
    n = db.execute(sql_text(
        "SELECT COUNT(*) FROM policy_chunks WHERE policy_id=:pid AND embedding IS NOT NULL"
    ), {"pid": policy_id}).fetchone()[0]
    print(f"  Chunk check: {round(time.time()-t1, 2)}s — found {n} chunks")
    if n == 0:
        print("  Auto-embedding policy chunks...")
        import os
        from backend.chunker import chunk_text
        from backend.text_extractor import extract_text

        policy = db.execute(sql_text(
            "SELECT file_name, content_preview FROM policies WHERE id=:pid"
        ), {"pid": policy_id}).fetchone()

        if not policy:
            return {"error": "Policy not found"}

        # Try to find the file (might have timestamp prefix)
        import glob
        upload_dir = "backend/uploads"
        fp = os.path.join(upload_dir, policy[0])

        if not os.path.exists(fp):
            # Search for file with timestamp prefix
            pattern = os.path.join(upload_dir, f"*{policy[0]}")
            matches = glob.glob(pattern)
            if matches:
                fp = matches[0]

        content = ""
        if os.path.exists(fp):
            ext = os.path.splitext(fp)[1].lower()
            try:
                content = extract_text(fp, ext)
            except TypeError:
                content = extract_text(fp)

        # Fallback to content_preview from database (stores full text)
        if not content:
            content = policy[1] or ""

        if not content:
            return {"error": "No text found in policy. Re-upload."}

        chunks = chunk_text(content)
        if chunks:
            embs = await get_embeddings([c["text"] for c in chunks])
            store_chunks_with_embeddings(db, policy_id, chunks, embs)
            print(f"  Auto-embedded {len(chunks)} chunks")
        else:
            return {"error": "Could not create chunks from policy."}

    # FILTER: Only analyze frameworks with uploaded documents
    t1 = time.time()
    loaded = db.execute(sql_text(
        "SELECT DISTINCT f.name FROM framework_chunks fc "
        "JOIN frameworks f ON fc.framework_id = f.id "
        "WHERE fc.embedding IS NOT NULL"
    )).fetchall()
    loaded_names = [r[0] for r in loaded]
    if loaded_names:
        frameworks = [fw for fw in frameworks if fw in loaded_names]
        if not frameworks:
            return {"error": "No loaded frameworks match your request. Upload framework documents first."}
    print(f"  Framework filter: {round(time.time()-t1, 2)}s — analyzing: {frameworks}")

    all_results = {}

    for fw in frameworks:
        fw_start = time.time()
        print(f"\n  Starting {fw}...")

        # Get controls
        t1 = time.time()
        controls = db.execute(sql_text(
            "SELECT id, control_code, title, keywords, severity_if_missing "
            "FROM control_library WHERE framework=:fw"
        ), {"fw": fw}).fetchall()
        print(f"    Load controls: {round(time.time()-t1, 2)}s — {len(controls)} controls")

        if not controls:
            all_results[fw] = {"error": f"No controls for {fw}"}
            continue

        # BATCH EMBED: 1 API call for all controls instead of N calls
        cds = [{"control_code": c[1], "title": c[2], "keywords": c[3],
                "severity_if_missing": c[4]} for c in controls]
        queries = [f"{c[1]}: {c[2]}" for c in controls]
        t1 = time.time()
        embeddings = await get_embeddings(queries)
        print(f"    Batch embed {len(queries)} controls: {round(time.time()-t1, 2)}s")

        # Analyze 5 controls at the same time (parallel)
        results = []
        batch_size = 5
        for i in range(0, len(cds), batch_size):
            t1 = time.time()
            batch = [(cds[j], embeddings[j]) for j in range(i, min(i+batch_size, len(cds)))]
            batch_results = await asyncio.gather(*[
                analyze_one(db, policy_id, cd, fw, emb)
                for cd, emb in batch
            ])
            results.extend(batch_results)
            done = min(i + batch_size, len(cds))
            print(f"    Controls {i+1}-{done}/{len(cds)}: {round(time.time()-t1, 2)}s")

        # Scores
        total = len(results)
        comp = sum(1 for r in results if r["status"] == "Compliant")
        part = sum(1 for r in results if r["status"] == "Partial")
        miss = sum(1 for r in results if r["status"] == "Non-Compliant")
        score = ((comp + part * 0.5) / total * 100) if total else 0
        dur = round(time.time() - fw_start, 1)
        print(f"    {fw}: {round(score, 1)}% ({comp} ok, {part} partial, {miss} missing) in {dur}s")

        # Save ComplianceResult
        db.execute(sql_text("""
            INSERT INTO compliance_results
            (id, policy_id, framework, compliance_score, controls_covered,
             controls_partial, controls_missing, status, analyzed_at,
             analysis_duration, details)
            VALUES (:id,:pid,:fw,:sc,:cov,:par,:mis,'completed',:at,:dur,:det)
        """), {
            "id": str(uuid.uuid4()), "pid": policy_id, "fw": fw,
            "sc": round(score, 1), "cov": comp, "par": part, "mis": miss,
            "at": datetime.utcnow(), "dur": round(dur, 2),
            "det": json.dumps(results),
        })

        # Save Gaps
        for r in results:
            if r["status"] in ("Non-Compliant", "Partial"):
                recs = r.get("recommendations", [])
                rem = "\n".join(
                    f"[{rc.get('priority','Medium')}|{rc.get('effort','Medium')}] {rc.get('action','')}"
                    for rc in recs
                ) if recs else "Manual review required"

                db.execute(sql_text("""
                    INSERT INTO gaps
                    (id, policy_id, framework, control_id, control_name,
                     severity, status, description, remediation, created_at)
                    VALUES (:id,:pid,:fw,:cid,:cn,:sev,'Open',:desc,:rem,:cat)
                """), {
                    "id": str(uuid.uuid4()), "pid": policy_id, "fw": fw,
                    "cid": r["control_code"], "cn": r["control_title"],
                    "sev": recs[0]["priority"] if recs else r.get("severity_if_missing", "High"),
                    "desc": r.get("gaps_detail", "Gap identified"),
                    "rem": rem, "cat": datetime.utcnow(),
                })

        # Save MappingReviews (all controls — even compliant ones)
        for r in results:
            ev = "\n".join(
                s.get("policy_evidence", "")
                for s in r.get("sub_requirements", [])
                if s.get("policy_evidence") and s["policy_evidence"] != "No evidence found"
            ) or "No direct evidence found"

            conf = r.get("confidence", 0.5)
            dec = ("Accepted" if r["status"] == "Compliant" and conf >= 0.8
                   else "Flagged" if r["status"] == "Non-Compliant"
                   else "Pending")

            db.execute(sql_text("""
                INSERT INTO mapping_reviews
                (id, policy_id, control_id, framework, evidence_snippet,
                 confidence_score, ai_rationale, decision, created_at)
                VALUES (:id,:pid,:cid,:fw,:ev,:conf,:rat,:dec,:cat)
            """), {
                "id": str(uuid.uuid4()), "pid": policy_id,
                "cid": r["control_code"], "fw": fw,
                "ev": ev, "conf": conf,
                "rat": r.get("overall_assessment", ""),
                "dec": dec, "cat": datetime.utcnow(),
            })

        db.commit()

        # Update policy status
        db.execute(sql_text(
            "UPDATE policies SET status='analyzed', last_analyzed_at=:now WHERE id=:pid"
        ), {"now": datetime.utcnow(), "pid": policy_id})
        db.commit()

        all_results[fw] = {
            "score": round(score, 1), "total_controls": total,
            "compliant": comp, "partial": part, "non_compliant": miss,
        }

    # Generate insights
    t1 = time.time()
    try:
        await generate_ai_insights(db, policy_id, all_results)
        print(f"  AI insights: {round(time.time()-t1, 2)}s")
    except Exception as e:
        print(f"  Insights warning: {e}")

    # Audit log
    try:
        db.execute(sql_text("""
            INSERT INTO audit_logs (id, actor, action, target_type, target_id, details, timestamp)
            VALUES (:id,'system','analyze_policy','policy',:tid,:det,:ts)
        """), {
            "id": str(uuid.uuid4()), "tid": policy_id,
            "det": json.dumps({
                "frameworks": frameworks,
                "scores": {f: r.get("score", 0) for f, r in all_results.items()
                           if isinstance(r, dict)},
            }),
            "ts": datetime.utcnow(),
        })
        db.commit()
    except Exception:
        pass

    print(f"\n{'='*50}")
    print(f"TOTAL ANALYSIS TIME: {round(time.time()-t0, 1)}s")
    print(f"{'='*50}\n")

    return all_results


# ── AI INSIGHTS ───────────────────────────────────────────────────────────────

async def generate_ai_insights(db, policy_id, results):
    lines = []
    for fw, d in results.items():
        if isinstance(d, dict) and "score" in d:
            lines.append(f"{fw}: {d['score']}% ({d.get('compliant',0)} ok, "
                         f"{d.get('partial',0)} partial, {d.get('non_compliant',0)} missing)")

    gaps = db.execute(sql_text("""
        SELECT framework, control_id, control_name, severity, description
        FROM gaps WHERE policy_id=:pid AND status='Open'
        ORDER BY CASE severity WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                 WHEN 'Medium' THEN 3 ELSE 4 END LIMIT 15
    """), {"pid": policy_id}).fetchall()

    gap_lines = [f"[{g[3]}] {g[0]} {g[1]} {g[2]}: {str(g[4])[:150]}" for g in gaps]

    pol = db.execute(sql_text("SELECT file_name FROM policies WHERE id=:pid"),
                     {"pid": policy_id}).fetchone()

    sys_prompt = """Generate exactly 5 specific compliance insights with control IDs and scores.
Types: 1=critical gap, 2=trend across frameworks, 3=quick win, 4=policy text fix, 5=strategic plan.
JSON: {"insights":[{"title":"...","description":"3-4 sentences with specifics",
"priority":"Critical|High|Medium|Low","insight_type":"gap|trend|policy|controls|strategic",
"confidence":0.7-0.95}]}"""

    resp = await call_llm(
        sys_prompt,
        f"Policy: {pol[0] if pol else 'Unknown'}\nSCORES:\n" +
        "\n".join(lines) + "\nGAPS:\n" + "\n".join(gap_lines)
    )

    data = json.loads(resp)
    db.execute(sql_text("DELETE FROM ai_insights WHERE policy_id=:pid"), {"pid": policy_id})

    for ins in data.get("insights", []):
        db.execute(sql_text("""
            INSERT INTO ai_insights
            (id, policy_id, insight_type, title, description, priority, confidence, status, created_at)
            VALUES (:id,:pid,:t,:ti,:de,:pr,:co,'new',:ca)
        """), {
            "id": str(uuid.uuid4()), "pid": policy_id,
            "t": ins.get("insight_type", "gap"),
            "ti": ins.get("title", ""),
            "de": ins.get("description", ""),
            "pr": ins.get("priority", "Medium"),
            "co": ins.get("confidence", 0.8),
            "ca": datetime.utcnow(),
        })
    db.commit()
    print(f"Generated {len(data.get('insights', []))} insights")


# ── CHAT ──────────────────────────────────────────────────────────────────────

async def chat_with_context(db, message, policy_id=None):
    emb = (await get_embeddings([message]))[0]

    # Policy chunks
    pol = ""
    chunks = search_similar_chunks(db, emb, policy_id=policy_id, top_k=8)
    if chunks:
        pol = "\n---\n".join([c["text"] for c in chunks[:5]])

    # Framework chunks
    fw = ""
    try:
        from backend.framework_loader import get_framework_context
        for f in ["NCA ECC", "ISO 27001", "NIST 800-53"]:
            fc = get_framework_context(db, f, emb, top_k=2)
            if fc:
                fw += f"\n[{f}]:\n" + "\n".join([c["text"] for c in fc])
    except Exception:
        pass

    # Analysis data
    ctx = ""
    try:
        scores = db.execute(sql_text("""
            SELECT framework, compliance_score, controls_covered,
                   controls_partial, controls_missing
            FROM compliance_results ORDER BY analyzed_at DESC LIMIT 10
        """)).fetchall()
        if scores:
            ctx = "SCORES:\n" + "".join(
                f"  {s[0]}: {s[1]}% ({s[2]} ok, {s[3]} partial, {s[4]} missing)\n"
                for s in scores
            )

        gps = db.execute(sql_text("""
            SELECT framework, control_id, control_name, severity, description, remediation
            FROM gaps WHERE status='Open'
            ORDER BY CASE severity WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 ELSE 3 END
            LIMIT 10
        """)).fetchall()
        if gps:
            ctx += "GAPS:\n" + "".join(
                f"  [{g[3]}] {g[0]} {g[1]}: {str(g[4])[:100]}\n    Fix: {str(g[5])[:100]}\n"
                for g in gps
            )
    except Exception:
        pass

    system = """You are Himaya AI, senior cybersecurity compliance advisor for Saudi organizations.
NCA ECC, ISO 27001, NIST 800-53 expert.
- Reference specific control IDs (ECC-2-2-3, A.8.5, IA-2)
- Quote actual policy text when relevant
- Give specific actionable advice with section references
- Estimate score improvement for each recommendation
- Respond in same language as question (Arabic->Arabic, English->English)
- NEVER give generic advice -- always reference THIS organization's data"""

    return await call_llm(
        system,
        f"POLICY:\n{pol or '[None uploaded]'}\nFRAMEWORK:\n{fw or '[None loaded]'}\n"
        f"DATA:\n{ctx or '[No analysis yet]'}\nQUESTION: {message}",
        force_json=False,
    )


# ── SIMULATION ────────────────────────────────────────────────────────────────

async def run_simulation(db, policy_id, selected_controls):
    if not policy_id:
        p = db.execute(sql_text(
            "SELECT id FROM policies ORDER BY created_at DESC LIMIT 1"
        )).fetchone()
        if not p:
            return {"error": "No policies"}
        policy_id = p[0]

    res = db.execute(sql_text("""
        SELECT framework, compliance_score, controls_covered, controls_partial, controls_missing
        FROM compliance_results WHERE policy_id=:pid ORDER BY analyzed_at DESC
    """), {"pid": policy_id}).fetchall()
    if not res:
        return {"error": "Run analysis first"}

    gaps = db.execute(sql_text(
        "SELECT framework, control_id FROM gaps WHERE policy_id=:pid AND status='Open'"
    ), {"pid": policy_id}).fetchall()

    sim = {}
    for r in res:
        fw, sc, cov, par, mis = r
        total = cov + par + mis
        if not total:
            continue
        fixed = sum(1 for g in gaps if g[0] == fw and g[1] in selected_controls)
        proj = (cov + fixed + max(0, par - fixed) * 0.5) / total * 100
        sim[fw] = {
            "current_score": round(sc, 1),
            "projected_score": round(proj, 1),
            "improvement": round(proj - sc, 1),
            "gaps_fixed": fixed,
        }
    return sim


# ── EXPLAINABILITY ────────────────────────────────────────────────────────────

async def explain_mapping(db, mapping_id):
    m = db.execute(sql_text("""
        SELECT control_id, framework, evidence_snippet, confidence_score, ai_rationale, decision
        FROM mapping_reviews WHERE id=:mid
    """), {"mid": mapping_id}).fetchone()
    if not m:
        return {"error": "Not found"}

    system = """Explain this AI compliance decision transparently. Be specific.
JSON: {"explanation":"plain language what AI found",
"evidence_analysis":"how evidence supports decision",
"confidence_breakdown":"why confidence is at this level",
"what_would_make_compliant":"exact policy changes needed",
"reviewer_guidance":"what human should verify"}"""

    try:
        r = await call_llm(system,
            f"Control: {m[0]} ({m[1]})\nEvidence: {m[2] or 'None'}\n"
            f"Confidence: {m[3]}\nRationale: {m[4] or 'None'}\nDecision: {m[5]}")
        return json.loads(r)
    except Exception as e:
        return {"explanation": f"Error: {str(e)}"}
