"""
checkpoint_analyzer.py
Deterministic 3-layer compliance analysis:
  Layer 1: Keyword search (topic exists in policy?)
  Layer 2: GPT-4o-mini binary YES/NO verification (temperature=0.0)
  Layer 3: Score = checkpoints_met / total x 100 (pure math)
"""
import os
import json
import uuid
import time
import asyncio
import glob
import httpx
from datetime import datetime, timezone
from sqlalchemy import text as sql_text
from backend.vector_store import (
    get_embeddings, search_similar_chunks, store_chunks_with_embeddings,
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


# ── GPT-4o-mini  (temperature=0.0 for deterministic) ────────────────────────

async def call_llm(system, user, force_json=True, temperature=0.0):
    body = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "max_tokens": 2000,
    }
    if force_json:
        body["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json=body,
        )
        if r.status_code != 200:
            raise Exception(f"GPT error {r.status_code}: {r.text[:300]}")
        return r.json()["choices"][0]["message"]["content"]


# ── Layer 1: Keyword Search ──────────────────────────────────────────────────

def keyword_search(text_lower, keywords):
    """Return (bool found, list matched_keywords)."""
    matched = [kw for kw in keywords if kw.lower() in text_lower]
    return len(matched) > 0, matched


# ── Layer 2: GPT Verification Prompt ─────────────────────────────────────────

VERIFIER_PROMPT = """You verify cybersecurity policy compliance checkpoints.
For EACH checkpoint, determine if the policy text provides clear, specific evidence.
Rules:
- YES only if there is EXPLICIT evidence (exact quote or clear statement)
- Generic "best practices" or vague mentions = NO
- Topic mentioned but details missing = NO
- Must find SPECIFIC language, not just the topic

Return ONLY valid JSON:
{
  "checkpoints": [
    {"index": 1, "met": true, "evidence": "exact quote from policy"},
    {"index": 2, "met": false, "evidence": "No evidence found"}
  ]
}"""


async def verify_checkpoints_gpt(checkpoints, policy_text):
    """GPT verifies each checkpoint as binary YES/NO with evidence quote."""
    cp_lines = "\n".join(
        f"CHECKPOINT {cp['checkpoint_index']}: {cp['requirement']}"
        for cp in checkpoints
    )
    user_msg = (
        f"Verify each checkpoint against this policy text:\n\n"
        f"{cp_lines}\n\n"
        f"POLICY TEXT:\n{policy_text[:15000]}"
    )
    try:
        raw = await call_llm(VERIFIER_PROMPT, user_msg)
        data = json.loads(raw)
        return data.get("checkpoints", [])
    except Exception as e:
        print(f"    GPT verify error: {e}")
        return [
            {"index": cp["checkpoint_index"], "met": False,
             "evidence": f"Verification error: {str(e)[:100]}"}
            for cp in checkpoints
        ]


# ── Auto-embed helper ────────────────────────────────────────────────────────

async def _auto_embed(db, policy_id):
    """Embed policy chunks if none exist yet. Returns chunk count."""
    from backend.chunker import chunk_text
    from backend.text_extractor import extract_text

    policy = db.execute(sql_text(
        "SELECT file_name, content_preview FROM policies WHERE id=:pid"
    ), {"pid": policy_id}).fetchone()
    if not policy:
        return 0

    # Try to read from file first
    upload_dir = "backend/uploads"
    fp = os.path.join(upload_dir, policy[0])
    if not os.path.exists(fp):
        matches = glob.glob(os.path.join(upload_dir, f"*{policy[0]}"))
        if matches:
            fp = matches[0]

    content = ""
    if os.path.exists(fp):
        ext = os.path.splitext(fp)[1].lower()
        try:
            content = extract_text(fp, ext)
        except TypeError:
            content = extract_text(fp)

    if not content:
        content = policy[1] or ""

    if not content:
        return 0

    chunks = chunk_text(content)
    if not chunks:
        return 0

    embs = await get_embeddings([c["text"] for c in chunks])
    store_chunks_with_embeddings(db, policy_id, chunks, embs)
    return len(chunks)


# ── Analyze one control (all its checkpoints) ────────────────────────────────

async def _analyze_control(db, policy_id, control_code, checkpoints, embedding, full_text_lower):
    """
    Three-layer analysis for a single control.
    Returns a result dict.
    """
    t0 = time.time()
    framework = checkpoints[0]["framework"]

    # Layer 1: keyword pre-screen per checkpoint
    kw_results = {}
    for cp in checkpoints:
        kw = cp.get("keywords", [])
        if isinstance(kw, str):
            try:
                kw = json.loads(kw)
            except Exception:
                kw = []
        found, matched = keyword_search(full_text_lower, kw)
        kw_results[cp["checkpoint_index"]] = {"found": found, "matched": matched}
    kw_time = round(time.time() - t0, 2)

    # Get relevant policy chunks via vector similarity
    t1 = time.time()
    chunks = search_similar_chunks(db, embedding, policy_id=policy_id, top_k=20)
    chunk_text_joined = "\n---\n".join(c["text"] for c in chunks[:15])
    search_time = round(time.time() - t1, 2)

    # Layer 2: GPT verification (one call per control, covers all checkpoints)
    # For small policies (<15K chars), send the FULL text so nothing is missed
    # For large policies, use vector-matched chunks
    if len(full_text_lower) <= 15000:
        policy_text_for_gpt = full_text_lower
    else:
        policy_text_for_gpt = chunk_text_joined or full_text_lower[:12000]
    print(f"    [{control_code}] Policy text length: {len(policy_text_for_gpt)} chars")
    t1 = time.time()
    gpt_results = await verify_checkpoints_gpt(
        checkpoints,
        policy_text_for_gpt,
    )
    gpt_time = round(time.time() - t1, 2)

    # Build a lookup from GPT results
    gpt_map = {}
    for g in gpt_results:
        gpt_map[g.get("index", 0)] = g

    # Layer 3: Deterministic scoring
    sub_requirements = []
    met_count = 0
    total_weight = 0.0
    met_weight = 0.0

    for cp in checkpoints:
        idx = cp["checkpoint_index"]
        gpt = gpt_map.get(idx, {"met": False, "evidence": "No evidence found"})
        is_met = bool(gpt.get("met", False))
        evidence = gpt.get("evidence", "No evidence found") or "No evidence found"
        w = cp.get("weight", 1.0)

        kw_found = kw_results.get(idx, {}).get("found", False)
        print(f"      [{control_code}] CP{idx}: kw={kw_found} met={is_met} | {cp['requirement'][:60]}")

        if is_met:
            met_count += 1
            met_weight += w
            status = "Met"
        else:
            status = "Not Met"
        total_weight += w

        sub_requirements.append({
            "requirement": cp["requirement"],
            "status": status,
            "policy_evidence": evidence,
            "gap": "None" if is_met else f"Missing: {cp['requirement']}",
            "keyword_found": kw_results.get(idx, {}).get("found", False),
        })

    score = (met_weight / total_weight * 100) if total_weight > 0 else 0
    total = len(checkpoints)

    if score >= 80:
        overall_status = "Compliant"
    elif score >= 30:
        overall_status = "Partial"
    else:
        overall_status = "Non-Compliant"

    confidence = round(min(score / 100, 0.99), 2)

    # Determine control title from control_library if available
    ctrl = db.execute(sql_text(
        "SELECT title FROM control_library WHERE control_code=:cc LIMIT 1"
    ), {"cc": control_code}).fetchone()
    title = ctrl[0] if ctrl else control_code

    total_time = round(time.time() - t0, 2)
    print(f"    {control_code}: kw={kw_time}s search={search_time}s "
          f"gpt={gpt_time}s => {overall_status} ({met_count}/{total}) "
          f"total={total_time}s")

    gaps_text = "; ".join(
        sr["gap"] for sr in sub_requirements if sr["status"] == "Not Met"
    ) or "No gaps"

    recs = []
    for sr in sub_requirements:
        if sr["status"] == "Not Met":
            recs.append({
                "action": f"Address: {sr['requirement']}",
                "priority": "High" if score < 50 else "Medium",
                "effort": "Medium",
            })

    return {
        "control_code": control_code,
        "control_title": title,
        "framework": framework,
        "status": overall_status,
        "score": round(score, 1),
        "confidence": confidence,
        "met": met_count,
        "total": total,
        "sub_requirements": sub_requirements,
        "overall_assessment": (
            f"{control_code} ({title}): {met_count}/{total} checkpoints met "
            f"({round(score, 1)}%). Status: {overall_status}."
        ),
        "gaps_detail": gaps_text,
        "risk_if_not_addressed": (
            "Critical compliance gap" if overall_status == "Non-Compliant"
            else "Partial coverage needs improvement" if overall_status == "Partial"
            else "Compliant"
        ),
        "recommendations": recs,
        "severity_if_missing": "High" if score < 50 else "Medium",
    }


# ── Main entry: run_checkpoint_analysis ──────────────────────────────────────

async def run_checkpoint_analysis(db, policy_id, frameworks):
    """
    Analyze a policy against checkpoint-based compliance controls.
    Saves results to compliance_results, gaps, mapping_reviews,
    ai_insights, and audit_logs.
    """
    t0 = time.time()
    print(f"\n{'='*50}")
    print(f"CHECKPOINT ANALYSIS STARTED at {time.strftime('%H:%M:%S')}")
    print(f"{'='*50}")

    # ── Auto-embed if needed ─────────────────────────────────────────────
    t1 = time.time()
    n = db.execute(sql_text(
        "SELECT COUNT(*) FROM policy_chunks "
        "WHERE policy_id=:pid AND embedding IS NOT NULL"
    ), {"pid": policy_id}).fetchone()[0]
    print(f"  Chunk check: {round(time.time()-t1, 2)}s -- found {n} chunks")

    if n == 0:
        print("  Auto-embedding policy chunks...")
        embedded = await _auto_embed(db, policy_id)
        if embedded == 0:
            return {"error": "No text found in policy. Re-upload the document."}
        print(f"  Auto-embedded {embedded} chunks")
        n = embedded

    # ── Get full policy text for keyword search ──────────────────────────
    policy_row = db.execute(sql_text(
        "SELECT content_preview FROM policies WHERE id=:pid"
    ), {"pid": policy_id}).fetchone()
    full_text_lower = (policy_row[0] or "").lower() if policy_row else ""

    # ── Framework filter ─────────────────────────────────────────────────
    t1 = time.time()
    try:
        loaded = db.execute(sql_text(
            "SELECT DISTINCT f.name FROM framework_chunks fc "
            "JOIN frameworks f ON fc.framework_id = f.id "
            "WHERE fc.embedding IS NOT NULL"
        )).fetchall()
        loaded_names = [r[0] for r in loaded]
        if loaded_names:
            frameworks = [fw for fw in frameworks if fw in loaded_names]
            if not frameworks:
                return {
                    "error": "No loaded frameworks match your request. "
                             "Upload framework documents first."
                }
    except Exception:
        pass  # Continue without filtering if framework_chunks is empty
    print(f"  Framework filter: {round(time.time()-t1, 2)}s -- "
          f"analyzing: {frameworks}")

    all_results = {}

    for fw in frameworks:
        fw_start = time.time()
        print(f"\n  Starting {fw}...")

        # ── Load checkpoints for this framework ──────────────────────────
        t1 = time.time()
        rows = db.execute(sql_text(
            "SELECT control_code, checkpoint_index, requirement, keywords, weight "
            "FROM control_checkpoints WHERE framework=:fw "
            "ORDER BY control_code, checkpoint_index"
        ), {"fw": fw}).fetchall()
        print(f"    Load checkpoints: {round(time.time()-t1, 2)}s -- "
              f"{len(rows)} checkpoints")

        if not rows:
            all_results[fw] = {"error": f"No checkpoints for {fw}"}
            continue

        # Group by control_code
        controls = {}
        for r in rows:
            code = r[0]
            kw = r[3]
            if isinstance(kw, str):
                try:
                    kw = json.loads(kw)
                except Exception:
                    kw = []
            cp = {
                "control_code": code,
                "checkpoint_index": r[1],
                "requirement": r[2],
                "keywords": kw,
                "weight": r[4] or 1.0,
                "framework": fw,
            }
            controls.setdefault(code, []).append(cp)

        # ── Resolve framework_id and control_id FKs ────────────────────
        fw_row = db.execute(sql_text(
            "SELECT id FROM frameworks WHERE name=:fw"
        ), {"fw": fw}).fetchone()
        framework_id = fw_row[0] if fw_row else None

        cl_rows = db.execute(sql_text(
            "SELECT id, control_code FROM control_library "
            "WHERE framework_id=:fwid"
        ), {"fwid": framework_id}).fetchall()
        ctrl_id_map = {r[1]: r[0] for r in cl_rows}  # control_code → control_library.id
        if not ctrl_id_map:
            print(f"    WARNING: ctrl_id_map is empty for framework_id={framework_id}")
            print(f"    Falling back to control_code lookup without framework_id filter")
            cl_rows = db.execute(sql_text(
                "SELECT id, control_code FROM control_library"
            )).fetchall()
            ctrl_id_map = {r[1]: r[0] for r in cl_rows}

        # ── Batch embed all control queries ──────────────────────────────
        control_codes = list(controls.keys())
        queries = [f"{code}: {controls[code][0]['requirement']}"
                   for code in control_codes]
        t1 = time.time()
        embeddings = await get_embeddings(queries)
        print(f"    Batch embed {len(queries)} controls: "
              f"{round(time.time()-t1, 2)}s")

        # ── Analyze in parallel (5 at a time) ────────────────────────────
        sem = asyncio.Semaphore(5)

        async def _run(code, emb):
            async with sem:
                return await _analyze_control(
                    db, policy_id, code, controls[code], emb, full_text_lower
                )

        results_list = []
        batch_size = 5
        for i in range(0, len(control_codes), batch_size):
            t1 = time.time()
            batch_codes = control_codes[i:i + batch_size]
            batch_embs = embeddings[i:i + batch_size]
            batch_out = await asyncio.gather(*[
                _run(batch_codes[j], batch_embs[j])
                for j in range(len(batch_codes))
            ])
            results_list.extend(batch_out)
            done = min(i + batch_size, len(control_codes))
            print(f"    Controls {i+1}-{done}/{len(control_codes)}: "
                  f"{round(time.time()-t1, 2)}s")

        # ── Layer 3: Deterministic scoring ───────────────────────────────
        total = len(results_list)
        comp = sum(1 for r in results_list if r["status"] == "Compliant")
        part = sum(1 for r in results_list if r["status"] == "Partial")
        miss = sum(1 for r in results_list if r["status"] == "Non-Compliant")
        score = ((comp + part * 0.5) / total * 100) if total else 0
        dur = round(time.time() - fw_start, 1)
        print(f"    {fw}: {round(score, 1)}% "
              f"({comp} ok, {part} partial, {miss} missing) in {dur}s")

        # ── Save ComplianceResult ────────────────────────────────────────
        db.execute(sql_text("""
            INSERT INTO compliance_results
            (id, policy_id, framework_id, compliance_score,
             controls_covered, controls_partial, controls_missing,
             status, analyzed_at, analysis_duration, details)
            VALUES (:id,:pid,:fwid,:sc,:cov,:par,:mis,
                    'completed',:at,:dur,:det)
        """), {
            "id": str(uuid.uuid4()), "pid": policy_id, "fwid": framework_id,
            "sc": round(score, 1), "cov": comp, "par": part, "mis": miss,
            "at": datetime.now(timezone.utc), "dur": round(dur, 2),
            "det": json.dumps(results_list),
        })

        # ── Save Gaps ────────────────────────────────────────────────────
        for r in results_list:
            if r["status"] in ("Non-Compliant", "Partial"):
                recs = r.get("recommendations", [])
                rem = "\n".join(
                    f"[{rc.get('priority','Medium')}|{rc.get('effort','Medium')}] "
                    f"{rc.get('action','')}"
                    for rc in recs
                ) if recs else "Manual review required"

                db.execute(sql_text("""
                    INSERT INTO gaps
                    (id, policy_id, framework_id, control_id, control_name,
                     severity, status, description, remediation, created_at)
                    VALUES (:id,:pid,:fwid,:cid,:cn,:sev,'Open',
                            :desc,:rem,:cat)
                """), {
                    "id": str(uuid.uuid4()), "pid": policy_id, "fwid": framework_id,
                    "cid": ctrl_id_map.get(r["control_code"]), "cn": r["control_title"],
                    "sev": (recs[0]["priority"] if recs
                            else r.get("severity_if_missing", "High")),
                    "desc": r.get("gaps_detail", "Gap identified"),
                    "rem": rem,
                    "cat": datetime.now(timezone.utc),
                })

        # ── Save MappingReviews ──────────────────────────────────────────
        for r in results_list:
            ev = "\n".join(
                sr.get("policy_evidence", "")
                for sr in r.get("sub_requirements", [])
                if sr.get("policy_evidence")
                and sr["policy_evidence"] != "No evidence found"
            ) or "No direct evidence found"

            conf = r.get("confidence", 0.5)
            dec = (
                "Accepted" if r["status"] == "Compliant" and conf >= 0.8
                else "Flagged" if r["status"] == "Non-Compliant"
                else "Pending"
            )

            db.execute(sql_text("""
                INSERT INTO mapping_reviews
                (id, policy_id, control_id, framework_id, evidence_snippet,
                 confidence_score, ai_rationale, decision, created_at)
                VALUES (:id,:pid,:cid,:fwid,:ev,:conf,:rat,:dec,:cat)
            """), {
                "id": str(uuid.uuid4()), "pid": policy_id,
                "cid": ctrl_id_map.get(r["control_code"]), "fwid": framework_id,
                "ev": ev, "conf": conf,
                "rat": r.get("overall_assessment", ""),
                "dec": dec,
                "cat": datetime.now(timezone.utc),
            })

        db.commit()

        # Update policy status
        db.execute(sql_text(
            "UPDATE policies SET status='analyzed', "
            "last_analyzed_at=:now WHERE id=:pid"
        ), {"now": datetime.now(timezone.utc), "pid": policy_id})
        db.commit()

        all_results[fw] = {
            "score": round(score, 1),
            "total_controls": total,
            "compliant": comp,
            "partial": part,
            "non_compliant": miss,
        }

    # ── Generate AI insights ─────────────────────────────────────────────
    t1 = time.time()
    try:
        await generate_insights(db, policy_id, all_results)
        print(f"  AI insights: {round(time.time()-t1, 2)}s")
    except Exception as e:
        print(f"  Insights warning: {e}")

    # ── Audit log ────────────────────────────────────────────────────────
    try:
        db.execute(sql_text("""
            INSERT INTO audit_logs
            (id, action, target_type, target_id, details, timestamp)
            VALUES (:id,'analyze_policy','policy',:tid,:det,:ts)
        """), {
            "id": str(uuid.uuid4()), "tid": policy_id,
            "det": json.dumps({
                "frameworks": frameworks,
                "scores": {
                    f: r.get("score", 0)
                    for f, r in all_results.items()
                    if isinstance(r, dict)
                },
            }),
            "ts": datetime.now(timezone.utc),
        })
        db.commit()
    except Exception:
        pass

    print(f"\n{'='*50}")
    print(f"TOTAL ANALYSIS TIME: {round(time.time()-t0, 1)}s")
    print(f"{'='*50}\n")

    return all_results


# ── AI Insights ──────────────────────────────────────────────────────────────

async def generate_insights(db, policy_id, results):
    lines = []
    for fw, d in results.items():
        if isinstance(d, dict) and "score" in d:
            lines.append(
                f"{fw}: {d['score']}% ({d.get('compliant',0)} ok, "
                f"{d.get('partial',0)} partial, "
                f"{d.get('non_compliant',0)} missing)"
            )

    gaps = db.execute(sql_text("""
        SELECT f.name, cl.control_code, g.control_name, g.severity, g.description
        FROM gaps g
        LEFT JOIN frameworks f ON g.framework_id = f.id
        LEFT JOIN control_library cl ON g.control_id = cl.id
        WHERE g.policy_id=:pid AND g.status='Open'
        ORDER BY CASE g.severity
            WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
            WHEN 'Medium' THEN 3 ELSE 4 END
        LIMIT 15
    """), {"pid": policy_id}).fetchall()
    gap_lines = [
        f"[{g[3]}] {g[0] or 'NCA ECC'} {g[1] or ''} {g[2]}: {str(g[4])[:150]}"
        for g in gaps
    ]

    pol = db.execute(sql_text(
        "SELECT file_name FROM policies WHERE id=:pid"
    ), {"pid": policy_id}).fetchone()

    sys_prompt = (
        "Generate exactly 5 specific compliance insights with control IDs "
        "and scores.\n"
        "Types: 1=critical gap, 2=trend across frameworks, 3=quick win, "
        "4=policy text fix, 5=strategic plan.\n"
        'JSON: {"insights":[{"title":"...","description":"3-4 sentences '
        'with specifics","priority":"Critical|High|Medium|Low",'
        '"insight_type":"gap|trend|policy|controls|strategic",'
        '"confidence":0.7-0.95}]}'
    )

    resp = await call_llm(
        sys_prompt,
        f"Policy: {pol[0] if pol else 'Unknown'}\nSCORES:\n"
        + "\n".join(lines)
        + "\nGAPS:\n"
        + "\n".join(gap_lines),
    )

    data = json.loads(resp)
    db.execute(sql_text(
        "DELETE FROM ai_insights WHERE policy_id=:pid"
    ), {"pid": policy_id})

    for ins in data.get("insights", []):
        db.execute(sql_text("""
            INSERT INTO ai_insights
            (id, policy_id, insight_type, title, description,
             priority, confidence, status, created_at)
            VALUES (:id,:pid,:t,:ti,:de,:pr,:co,'new',:ca)
        """), {
            "id": str(uuid.uuid4()), "pid": policy_id,
            "t": ins.get("insight_type", "gap"),
            "ti": ins.get("title", ""),
            "de": ins.get("description", ""),
            "pr": ins.get("priority", "Medium"),
            "co": ins.get("confidence", 0.8),
            "ca": datetime.now(timezone.utc),
        })
    db.commit()
    print(f"  Generated {len(data.get('insights', []))} insights")


# ── Chat with context ────────────────────────────────────────────────────────

async def chat_with_context(db, message, policy_id=None):
    emb = (await get_embeddings([message]))[0]

    # Policy chunks
    pol = ""
    chunks = search_similar_chunks(db, emb, policy_id=policy_id, top_k=8)
    if chunks:
        pol = "\n---\n".join(c["text"] for c in chunks[:5])

    # Framework chunks
    fw = ""
    try:
        from backend.framework_loader import get_framework_context
        for f_name in ["NCA ECC", "ISO 27001", "NIST 800-53"]:
            fc = get_framework_context(db, f_name, emb, top_k=2)
            if fc:
                fw += f"\n[{f_name}]:\n" + "\n".join(c["text"] for c in fc)
    except Exception:
        pass

    # Analysis data
    ctx = ""
    try:
        scores = db.execute(sql_text("""
            SELECT f.name, cr.compliance_score, cr.controls_covered,
                   cr.controls_partial, cr.controls_missing
            FROM compliance_results cr
            LEFT JOIN frameworks f ON cr.framework_id = f.id
            ORDER BY cr.analyzed_at DESC LIMIT 10
        """)).fetchall()
        if scores:
            ctx = "SCORES:\n" + "".join(
                f"  {s[0] or 'Unknown'}: {s[1]}% ({s[2]} ok, {s[3]} partial, "
                f"{s[4]} missing)\n"
                for s in scores
            )

        gps = db.execute(sql_text("""
            SELECT f.name, cl.control_code, g.control_name, g.severity,
                   g.description, g.remediation
            FROM gaps g
            LEFT JOIN frameworks f ON g.framework_id = f.id
            LEFT JOIN control_library cl ON g.control_id = cl.id
            WHERE g.status='Open'
            ORDER BY CASE g.severity
                WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 ELSE 3 END
            LIMIT 10
        """)).fetchall()
        if gps:
            ctx += "GAPS:\n" + "".join(
                f"  [{g[3]}] {g[0] or ''} {g[1] or ''}: {str(g[4])[:100]}\n"
                f"    Fix: {str(g[5])[:100]}\n"
                for g in gps
            )
    except Exception:
        pass

    system = (
        "You are Hemaya AI, senior cybersecurity compliance advisor "
        "for Saudi organizations.\n"
        "NCA ECC, ISO 27001, NIST 800-53 expert.\n"
        "- Reference specific control IDs (ECC-2-2-3, A.8.5, IA-2)\n"
        "- Quote actual policy text when relevant\n"
        "- Give specific actionable advice with section references\n"
        "- Estimate score improvement for each recommendation\n"
        "- Respond in same language as question "
        "(Arabic->Arabic, English->English)\n"
        "- NEVER give generic advice -- always reference THIS "
        "organization's data"
    )

    return await call_llm(
        system,
        f"POLICY:\n{pol or '[None uploaded]'}\n"
        f"FRAMEWORK:\n{fw or '[None loaded]'}\n"
        f"DATA:\n{ctx or '[No analysis yet]'}\n"
        f"QUESTION: {message}",
        force_json=False,
        temperature=0.3,
    )


# ── Simulation ───────────────────────────────────────────────────────────────

async def run_simulation(db, policy_id, selected_controls):
    if not policy_id:
        p = db.execute(sql_text(
            "SELECT id FROM policies ORDER BY created_at DESC LIMIT 1"
        )).fetchone()
        if not p:
            return {"error": "No policies"}
        policy_id = p[0]

    res = db.execute(sql_text("""
        SELECT f.name, cr.compliance_score, cr.controls_covered,
               cr.controls_partial, cr.controls_missing
        FROM compliance_results cr
        LEFT JOIN frameworks f ON cr.framework_id = f.id
        WHERE cr.policy_id=:pid ORDER BY cr.analyzed_at DESC
    """), {"pid": policy_id}).fetchall()
    if not res:
        return {"error": "Run analysis first"}

    gap_rows = db.execute(sql_text(
        "SELECT f.name, cl.control_code FROM gaps g "
        "LEFT JOIN frameworks f ON g.framework_id = f.id "
        "LEFT JOIN control_library cl ON g.control_id = cl.id "
        "WHERE g.policy_id=:pid AND g.status='Open'"
    ), {"pid": policy_id}).fetchall()

    sim = {}
    for r in res:
        fw, sc, cov, par, mis = r
        total = cov + par + mis
        if not total:
            continue
        fixed = sum(
            1 for g in gap_rows
            if g[0] == fw and g[1] in selected_controls
        )
        proj = (cov + fixed + max(0, par - fixed) * 0.5) / total * 100
        sim[fw] = {
            "current_score": round(sc, 1),
            "projected_score": round(proj, 1),
            "improvement": round(proj - sc, 1),
            "gaps_fixed": fixed,
        }
    return sim


# ── Explainability ───────────────────────────────────────────────────────────

async def explain_mapping(db, mapping_id):
    m = db.execute(sql_text("""
        SELECT cl.control_code, f.name, mr.evidence_snippet,
               mr.confidence_score, mr.ai_rationale, mr.decision
        FROM mapping_reviews mr
        LEFT JOIN frameworks f ON mr.framework_id = f.id
        LEFT JOIN control_library cl ON mr.control_id = cl.id
        WHERE mr.id=:mid
    """), {"mid": mapping_id}).fetchone()
    if not m:
        return {"error": "Not found"}

    system = (
        "Explain this AI compliance decision transparently. Be specific.\n"
        'JSON: {"explanation":"plain language what AI found",'
        '"evidence_analysis":"how evidence supports decision",'
        '"confidence_breakdown":"why confidence is at this level",'
        '"what_would_make_compliant":"exact policy changes needed",'
        '"reviewer_guidance":"what human should verify"}'
    )

    try:
        r = await call_llm(
            system,
            f"Control: {m[0]} ({m[1]})\n"
            f"Evidence: {m[2] or 'None'}\n"
            f"Confidence: {m[3]}\n"
            f"Rationale: {m[4] or 'None'}\n"
            f"Decision: {m[5]}",
        )
        return json.loads(r)
    except Exception as e:
        return {"explanation": f"Error: {str(e)}"}
