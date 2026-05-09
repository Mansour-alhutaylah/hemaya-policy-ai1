# Himaya Product Map

A grounded reference of what every page does, what backend it calls, what tables it touches, and what AI logic sits behind it. This is the source of truth for onboarding and for any cross-page consistency work. Update it when surface area changes.

Companion to: project plan at `C:\Users\saif1\.claude\plans\i-want-you-to-snappy-honey.md` (planning artifact; not committed) and `CLAUDE.md` (project guidelines).

---

## 1. Architecture at a glance

```
React SPA (Vite, lazy-loaded routes)            FastAPI (Python)            PostgreSQL (Supabase)
─────────────────────────────────────           ────────────────            ─────────────────────
src/pages/* (14 pages)         ───►  /api/*  ───►  routers + main.py  ───►  20+ tables
src/api/apiClient.js                                                         pgvector embeddings
React Query (60s staleTime)               OpenAI (gpt-4o-mini, embeddings)
```

Phase invariants frozen (do not modify without explicit approval):

| Phase | Invariant |
|---|---|
| 9  | RAG relevance floor (`RAG_MIN_RELEVANCE_SCORE`, default `0.10`) |
| 10 | Grounding v2 (`GROUNDING_VERSION="v2"`, sentence-bounded windows, `GROUNDING_MIN_SIMILARITY=0.75`) |
| 11 | Source attribution: `policy_chunks.page_number`, `paragraph_index`; `_attribute_evidence_to_chunk()` |
| 12 | Atomic upload (prepare-then-commit; rollback on error) |
| 13 | Per-request RLS via `set_user_context(db, user_id)`; `is_admin()` consolidated; hard-fail env validation |
| 14 | Lazy routes; conditional 3 s polling on Policies; persistent httpx client |

---

## 2. Pages

All routes are lazy-loaded via [src/pages.config.js](../src/pages.config.js).

| Page | File | Purpose | Backend endpoints | Tables read | AI |
|---|---|---|---|---|---|
| Home | [src/pages/Home.jsx](../src/pages/Home.jsx) | Welcome + 4 action cards + 5 recent policies | `GET /api/entities/Policy` | `policies` | — |
| Dashboard | [src/pages/Dashboard.jsx](../src/pages/Dashboard.jsx) | Stats hero, severity bar, framework pie, audit log | `GET /api/dashboard/stats`, `GET /api/entities/Policy`, `GET /api/entities/AuditLog` | `compliance_results`, `gaps`, `frameworks`, `audit_logs` | — |
| Policies | [src/pages/Policies.jsx](../src/pages/Policies.jsx) | List, upload, pause/resume, report-from-policy | `GET /api/entities/Policy`, `POST /api/integrations/upload`, `POST /api/functions/{pause,resume}_policy`, `POST /api/reports/export` | `policies`, `frameworks` (write `policy_chunks`) | embeddings on upload |
| Analyses | [src/pages/Analyses.jsx](../src/pages/Analyses.jsx) | Result list + per-result detail + bar/pie | `GET /api/entities/ComplianceResult`, `GET /api/entities/Policy` | `compliance_results`, `policies` | — |
| Frameworks | [src/pages/Frameworks.jsx](../src/pages/Frameworks.jsx) | Framework cards + score trend | `GET /api/entities/Framework`, `GET /api/entities/ComplianceResult` | `frameworks`, `ecc_framework`, `sacs002_metadata` | — |
| MappingReview | [src/pages/MappingReview.jsx](../src/pages/MappingReview.jsx) | Per-control mapping cards + accept/reject | `GET /api/mapping-reviews`, `POST /api/mappings/{id}/{accept,reject}` | `mapping_reviews`, `ecc_framework`, `policy_ecc_assessments` | — |
| GapsRisks | [src/pages/GapsRisks.jsx](../src/pages/GapsRisks.jsx) | Gap table + create/edit + severity charts | `GET/POST/PATCH /api/entities/Gap`, `GET /api/entities/Policy` | `gaps`, `policies`, `control_library` | — |
| PolicyVersions | [src/pages/PolicyVersions.jsx](../src/pages/PolicyVersions.jsx) | Version diff + PDF + reanalyse | `GET /api/policy-versions`, `POST /api/policy-versions/generate`, `GET /policies/{p}/versions/{v}/download/pdf`, `POST .../reanalyze` | `policy_versions`, `policies`, `compliance_results`, `remediation_drafts` | GPT-4o-mini (improved policy text) |
| AIInsights | [src/pages/AIInsights.jsx](../src/pages/AIInsights.jsx) | Tabs (gap_priority, risk_alert, etc.) + insight cards | `GET /api/entities/AIInsight` | `ai_insights`, `compliance_results`, `gaps` | display-only (LLM populated this on analysis) |
| Explainability | [src/pages/Explainability.jsx](../src/pages/Explainability.jsx) | Mapping rationale cards | `GET /api/entities/MappingReview` | `mapping_reviews`, `policies` | — |
| Reports | [src/pages/Reports.jsx](../src/pages/Reports.jsx) | Generate / list / delete reports | `GET /api/entities/Report`, `POST /api/functions/generate_report`, `POST /api/reports/export`, `DELETE /api/entities/Report` | `reports`, `compliance_results`, `gaps`, `remediation_drafts` | GPT-4o-mini T=0.5 (insights) |
| AIAssistant | [src/pages/AIAssistant.jsx](../src/pages/AIAssistant.jsx) | Chat (RAG) | `POST /api/assistant/chat` | `policy_chunks`, `compliance_results`, `gaps` | embeddings + GPT-4o-mini T=0.1, 50 s timeout |
| Settings | [src/pages/Settings.jsx](../src/pages/Settings.jsx) | Profile + change password | `GET /api/auth/me`, `POST /api/auth/{change-password,updateMe}` | `users` | — |
| Simulation | [src/pages/Simulation.jsx](../src/pages/Simulation.jsx) | BETA — what-if scenarios | `POST /api/functions/run_simulation` | `compliance_results`, `gaps` | predictive |
| Admin | [src/pages/Admin.jsx](../src/pages/Admin.jsx) | Users / policies / audit / settings | `/api/admin/*` (15 endpoints) | `users`, `policies`, `audit_logs`, settings | — |

---

## 3. Backend layout

Entry: [backend/main.py](../backend/main.py). Sub-routers:

- [backend/routers/remediation.py](../backend/routers/remediation.py) — `/api/remediation/{generate,drafts}`
- [backend/routers/reports_export.py](../backend/routers/reports_export.py) — `/api/reports/export` (DOCX compliance package)
- [backend/routers/explainability.py](../backend/routers/explainability.py) — `/api/mapping-reviews`, `/api/policy-versions`, version PDF + reanalyse

Endpoint groups in `main.py`: auth (10), upload + analysis (7), reporting (3), chat + insights (4), framework management (4), entity CRUD (16), mapping accept/reject (2), admin (15).

---

## 4. AI engines

| File | Purpose | Model | Temp | Cache |
|---|---|---|---|---|
| [backend/checkpoint_analyzer.py](../backend/checkpoint_analyzer.py) | Generic framework checkpoint verification + chat RAG | gpt-4o-mini | 0.0 | `verification_cache` |
| [backend/ecc2_analyzer.py](../backend/ecc2_analyzer.py) | ECC-2:2024 verification (L1 + L3) | gpt-4o-mini | 0.0 | `ecc2_verification_cache` |
| [backend/sacs002_analyzer.py](../backend/sacs002_analyzer.py) | SACS-002 verification | gpt-4o-mini | 0.0 | none |
| [backend/rag_engine.py](../backend/rag_engine.py) | Retrieval helpers / chat fallback | gpt-4o-mini | 0.1 | none |
| [backend/remediation_engine.py](../backend/remediation_engine.py) | Additive policy draft generation | gpt-4o-mini | 0.0 (ECC) / 0.1 (generic) | none |
| [backend/framework_loader.py](../backend/framework_loader.py) | Framework upload & extraction | gpt-4o-mini | 0.0 | — |
| [backend/vector_store.py](../backend/vector_store.py) | pgvector retrieval + embeddings | text-embedding-3-small | n/a | implicit (chunks live in DB) |

Cache keys for `ecc2_verification_cache` include `prompt_version`, `model`, `retrieval_min_score`, `grounding_version`, `grounding_min_similarity`. Bumping any invalidates old rows.

---

## 5. Database

Tables defined in [backend/models.py](../backend/models.py). User-facing core:

```
users (UUID, role, settings)
  └── policies (owner_id, status, progress)
        ├── policy_chunks (pgvector embedding, page_number, paragraph_index)
        ├── policy_versions (audit trail; original | ai_draft | final)
        ├── compliance_results (per-framework summary)
        ├── policy_ecc_assessments (ECC-2 detailed per-control)
        ├── gaps (severity, status, owner_id, mapping_id soft-ref)
        ├── mapping_reviews (per-control evidence + decision)
        ├── remediation_drafts (additive suggested_policy_text)
        ├── reports (DOCX/PDF/JSON exports)
        └── ai_insights

frameworks
  ├── control_library              (generic frameworks)
  ├── ecc_framework + ecc_compliance_metadata + ecc_ai_checkpoints   (ECC-2)
  └── sacs002_metadata             (SACS-002)

verification_cache, ecc2_verification_cache
otp_tokens, password_reset_tokens, audit_logs
```

Ownership: all user-data queries scope by `policies.owner_id` (admins bypass via `is_admin()`).

---

## 6. End-to-end flows

### Upload (atomic — Phase 12)
`POST /api/integrations/upload` → extract text (page/paragraph metadata retained) → chunk → batch embed (50 / batch via persistent httpx client) → prepare all writes → commit in one transaction → rollback deletes the row + file on error. Frontend polls `policies` at 3 s while `status='processing'`.

### Analysis
`POST /api/functions/analyze_policy` → routes to `run_ecc2_analysis` / `run_sacs002_analysis` / `run_checkpoint_analysis` per framework. Per control: retrieve chunks (Phase 9 floor) → check verification cache → call GPT JSON verifier (T=0.0) → ground evidence (Phase 10 v2) → attribute to chunk (Phase 11). Cooperative pause checked between controls. Writes `compliance_results`, `policy_ecc_assessments` (ECC-2), `mapping_reviews`, `gaps`. Then `generate_insights()` (T=0.5) writes `ai_insights`.

### Dashboard counts
`GET /api/dashboard/stats` (`backend/main.py:dashboard_stats`). Latest `compliance_results` per framework via `DISTINCT ON (f.name) ORDER BY f.name, cr.analyzed_at DESC, cr.id DESC`. Severity distribution from `gaps WHERE status='Open'`. Returns `controls_total = covered + partial + missing` and `controls_compliant = sum(covered)`. Also returns the legacy `controls_mapped` field as an alias of `controls_total` for one release (it previously equalled sum-of-covered, which contradicted the "Controls Mapped" KPI label); remove afterwards.

### Mapping review
`POST /api/mappings/{id}/{accept,reject}` updates `decision`, `reviewer_id`, `reviewed_at`. Does not auto-update gap status; rejection optionally triggers `generate_remediation_draft()`.

### Remediation
`POST /api/remediation/generate` → [backend/remediation_engine.py](../backend/remediation_engine.py) returns `suggested_policy_text` (additive only). `score_remediation_draft()` re-runs analysis and reports checkpoint diffs.

### Chatbot (current)
`POST /api/assistant/chat` → `chat_with_user_context` → resolve user's policies → load compliance snapshot → fast paths for `status_summary / top_gaps / framework_score / remediation` → fallback RAG over user's policy chunks → GPT-4o-mini T=0.1, 50 s timeout. Output: answer + `sources` + `has_data`. (Page-citation rendering is on the roadmap.)

### Reports
`POST /api/reports/export` (DOCX compliance package): cover, exec summary, open gaps, remediation drafts, version history, disclaimer. `POST /api/functions/generate_report` is the legacy path.

---

## 7. Auth & security

JWT bearer on every request. `_get_current_user` decodes the token, looks up the user, then calls `set_user_context(db, user_id)` so PostgreSQL RLS policies can filter rows by `app.current_user_id`. Admin = `user.role == "admin"` OR `user.email == ADMIN_EMAIL`. Helper: `backend/security.is_admin(user)`.

Session timeout configurable; frontend tracks inactivity (mousedown / keydown / click / scroll / touch), throttled to 5 s, and force-logs-out on expiry.

---

## 8. Performance notes

- All pages lazy-loaded; recharts / framer-motion / jspdf pulled in only when their consuming page mounts.
- Persistent httpx client in `vector_store.py` avoids per-request TLS handshake overhead.
- Embeddings batched 50 / call.
- Conditional polling (3 s) on Policies stops when no policy is processing and when the tab is inactive.
- React Query `staleTime: 60s`, `refetchOnWindowFocus: false`, `retry: 1`.

---

## 9. Conventions for new work

- New API calls go through [src/api/apiClient.js](../src/api/apiClient.js) (do not introduce another fetch helper).
- New chart components go through `src/components/charts/Chart.jsx` (planned wrapper) — no inline colour strings; use severity tokens.
- Severity colour helper: `getSeverityColor(level)` (planned). Until it lands, keep new code consistent with existing token usage in `tailwind.config.js`.
- Admin gating on the frontend: read `user.is_admin` (planned on `/api/auth/me`) — do not compare emails.
- All user-data queries must filter by `owner_id` or rely on RLS context.
