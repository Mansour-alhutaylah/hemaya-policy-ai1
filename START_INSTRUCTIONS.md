# Hemaya Policy AI — How to Start

## Prerequisites
- Python 3.10+ installed
- Node.js 18+ installed
- `.env` file in the project root with these variables:
  ```
  DATABASE_URL=postgresql://postgres:<password>@<host>:5432/postgres
  SECRET_KEY=<your-secret-key>
  HF_API_TOKEN=<your-huggingface-token>
  ```

## Step 1: Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

Key packages: fastapi, uvicorn, sqlalchemy, psycopg2-binary, httpx, numpy,
python-jose, bcrypt, python-dotenv, pymupdf, python-docx, openpyxl, chardet, watchfiles

## Step 2: Start the Backend Server

```bash
# From the project root:
python run_backend.py
```

Expected output:
```
INFO:     Started server process [XXXX]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

> **Do NOT use `uvicorn backend.main:app --reload`** — Python 3.14 on Windows
> has a bug where `asyncio.run()` hangs in spawned subprocesses, which is exactly
> what `--reload` does. Use `run_backend.py` instead (no reload, no subprocess).
>
> The server starts fast (no DB calls at startup). First DB connection
> happens only on the first HTTP request.

## Step 3: Install Frontend Dependencies

```bash
# From the project root:
npm install
```

## Step 4: Start the Frontend Dev Server

```bash
npm run dev
```

The frontend runs on http://localhost:5173 (or similar Vite port).
API requests are proxied to the backend at http://localhost:8000.

## Step 5: Verify Everything Works

1. Open http://localhost:5173 in your browser
2. Register a new account or log in
3. Upload a policy document (PDF, DOCX, TXT, XLSX)
4. Run compliance analysis — select frameworks (NCA ECC, ISO 27001, NIST 800-53)
5. View results in the Analyses, Gaps, and Explainability pages

## Troubleshooting

### Server freezes / never shows "Application startup complete"
- **Use `python run_backend.py` instead of `uvicorn ... --reload`**
- Python 3.14 on Windows: `asyncio.run()` hangs in spawned subprocesses — `--reload` spawns a subprocess, so it always freezes
- Do NOT add `models.Base.metadata.create_all()` — all tables already exist in Supabase

### HuggingFace API errors (503)
- The AI models are loaded on demand — first call may take 20-30 seconds
- The system automatically retries once after 10 seconds
- Make sure `HF_API_TOKEN` is set in your `.env` file

### Database connection errors
- Verify `DATABASE_URL` in your `.env` file points to your Supabase instance
- The URL format: `postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`

### CORS errors in browser
- Backend must be running on port 8000
- Check `vite.config.js` for the proxy configuration

## Environment Variables Reference

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string (Supabase) |
| `SECRET_KEY` | JWT signing secret (any random string, keep secret) |
| `HF_API_TOKEN` | HuggingFace Inference API token (free at huggingface.co) |
