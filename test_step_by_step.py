"""
Step-by-step test to find WHERE exactly the freeze happens.
Run: python test_step_by_step.py
Each step prints immediately — the last printed step = where it froze.
"""
import sys
import os

# Flush output immediately so we see each line as it happens
def step(msg):
    print(msg, flush=True)

step("Step 1: Loading .env ...")
from dotenv import load_dotenv
load_dotenv()
step("Step 1: OK")

step("Step 2: Importing backend.database ...")
from backend.database import engine, SessionLocal
step("Step 2: OK")

step("Step 3: Importing backend.models ...")
from backend import models
step("Step 3: OK")

step("Step 4: Running create_all (creates/checks tables in Supabase) ...")
models.Base.metadata.create_all(bind=engine)
step("Step 4: OK")

step("Step 5: Importing backend.main (loads FastAPI app) ...")
from backend.main import app
step("Step 5: OK")

step("Step 6: Creating TestClient (no context manager — avoids lifespan deadlock) ...")
from starlette.testclient import TestClient
client = TestClient(app, raise_server_exceptions=False)
step("Step 6: OK")

step("Step 7: Skipped (__enter__ deadlocks on newer Starlette — using client directly)")

step("Step 8: Sending POST /api/auth/register ...")
r = client.post("/api/auth/register", json={
    "first_name": "Test",
    "last_name": "Step",
    "phone": "0500000001",
    "email": "test_step@hemaya.sa",
    "password": "TestPass123!",
})
step(f"Step 8: Got response: {r.status_code}")
if r.status_code not in (200, 400):
    step(f"  Body: {r.text[:300]}")

step("Step 9: Sending POST /api/auth/login ...")
r = client.post("/api/auth/login", json={
    "email": "test_step@hemaya.sa",
    "password": "TestPass123!",
})
step(f"Step 9: Got response: {r.status_code}")

step("Step 10: Exiting TestClient context ...")
client.__exit__(None, None, None)
step("Step 10: OK")

step("\n=== ALL STEPS PASSED — TestClient + DB are working ===")
