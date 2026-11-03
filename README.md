# HIMAYA | AI-Assisted Cybersecurity Compliance Platform

**Computer Science Graduation Project · Team of 5 · 2025–2026**

HIMAYA is a cybersecurity compliance platform developed as a university graduation project. It explores how AI-assisted document retrieval and analysis can support the review of policies and evidence against cybersecurity frameworks, including NCA ECC and SACS-002.

**Live project:** [ai-himaya.site](https://ai-himaya.site)

## The problem

Reviewing cybersecurity policies and supporting documents can involve searching through long files to find relevant evidence. HIMAYA uses a document-retrieval workflow to make that information easier to locate and review. AI-generated analysis is intended to support, not replace, human judgment.

## My contributions

I contributed to the project as one member of a **five-person team**, focusing on:

- **RAG and semantic retrieval:** Implemented document retrieval using text embeddings, semantic search, and PostgreSQL with pgvector.
- **Authentication and access control:** Implemented email-based one-time-password (OTP) authentication and worked on login and user/admin permissions.
- **Testing:** Tested login, permissions, and core application workflows.
- **Deployment support:** Configured the project's custom domain.

These are my individual contributions; the complete application was a collaborative team effort.

## Technology overview

| Area | Technologies and approach |
| --- | --- |
| Backend | Python, FastAPI, SQLAlchemy, REST APIs |
| AI and retrieval | RAG, OpenAI API integration, text embeddings, semantic search |
| Database | PostgreSQL, pgvector |
| Frontend | React, Vite |
| Testing | Backend and functional testing; evaluation scripts included in the repository |

## How the RAG workflow works

```text
Documents
   |
   v
Text extraction and chunking
   |
   v
Embedding generation
   |
   v
PostgreSQL + pgvector
   |
   v
User question --> semantic retrieval --> relevant passages
                                           |
                                           v
                              AI model with retrieved context
                                           |
                                           v
                                  Result for human review
```

The diagram simplifies the retrieval process; exact behavior depends on the application workflow and configuration.

## Repository structure

- `backend/` — Python API, document processing, authentication, and retrieval components
- `src/` — React frontend
- `eval/` — evaluation and regression scripts
- `docs/` — supporting project documentation

## Running locally

You will need the appropriate local configuration and environment variables. **Do not commit API keys, database credentials, or real confidential documents.**

Frontend:

```bash
npm install
npm run dev
```

Backend dependencies:

```bash
pip install -r backend/requirements.txt
```

Start the backend:

```bash
python run_backend.py
```

The backend expects environment configuration such as `DATABASE_URL` and `OPENAI_API_KEY`. Some frontend features require application-specific configuration, so a local setup may differ from the deployed environment.

---

**Project note:** HIMAYA is a student engineering project. It does not certify regulatory compliance and should not be treated as a substitute for a professional cybersecurity assessment.
