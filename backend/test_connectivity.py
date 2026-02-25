"""
Connectivity & Health Test Script
Run from the project root:  python -m backend.test_connectivity
Tests: DB connection, password hashing, register, login, JWT, authenticated endpoint.
"""
import sys
import uuid
import os

# Force UTF-8 output on Windows so arrow/emoji characters print correctly
if sys.stdout.encoding != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests

BASE = "http://localhost:8000"
TEST_EMAIL = f"test_{uuid.uuid4().hex[:8]}@hemaya.test"
TEST_PASSWORD = "Hemaya@1234"

PASS = "\033[92m[PASS]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
INFO = "\033[94m[INFO]\033[0m"


def section(title: str):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print("=" * 55)


# ─────────────────────────────────────────────────────────
# PHASE 1: Local unit checks (no HTTP)
# ─────────────────────────────────────────────────────────
section("PHASE 1 — Local: Database & Auth")

# 1a. DB connection
try:
    from backend.database import engine
    with engine.connect() as conn:
        conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    print(f"{PASS} Database connection OK  ({engine.url})")
except Exception as e:
    print(f"{FAIL} Database connection FAILED: {e}")
    sys.exit(1)

# 1b. Tables exist
try:
    from backend import models
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    expected = ["users", "policies", "compliance_results", "gaps",
                "mapping_reviews", "reports", "audit_logs", "ai_insights"]
    missing = [t for t in expected if t not in tables]
    if missing:
        print(f"{FAIL} Missing DB tables: {missing}")
    else:
        print(f"{PASS} All {len(expected)} tables present: {tables}")
except Exception as e:
    print(f"{FAIL} Table inspection failed: {e}")

# 1c. Password hashing
try:
    from backend.auth import get_password_hash, verify_password
    h = get_password_hash(TEST_PASSWORD)
    assert verify_password(TEST_PASSWORD, h), "verify returned False"
    assert not verify_password("wrong", h), "verify should fail for wrong password"
    print(f"{PASS} bcrypt hash/verify OK")
except Exception as e:
    print(f"{FAIL} bcrypt hash/verify FAILED: {e}")
    sys.exit(1)

# 1d. JWT creation/decode
try:
    from backend.auth import create_access_token, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
    from jose import jwt as jose_jwt
    token = create_access_token({"sub": "test@test.com"})
    payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload.get("sub") == "test@test.com"
    print(f"{PASS} JWT create/decode OK  (expires in {ACCESS_TOKEN_EXPIRE_MINUTES} min)")
except Exception as e:
    print(f"{FAIL} JWT FAILED: {e}")


# ─────────────────────────────────────────────────────────
# PHASE 2: HTTP — backend must be running
# ─────────────────────────────────────────────────────────
section("PHASE 2 — HTTP: Backend API Connectivity")

# 2a. Health check
try:
    r = requests.get(f"{BASE}/api/functions/db_health", timeout=5)
    r.raise_for_status()
    print(f"{PASS} GET /api/functions/db_health -> {r.json()}")
except requests.ConnectionError:
    print(f"{FAIL} Cannot reach backend at {BASE}. Is uvicorn running?")
    sys.exit(1)
except Exception as e:
    print(f"{FAIL} Health check failed: {e}")


# ─────────────────────────────────────────────────────────
# PHASE 3: Register -> Login -> /me flow
# ─────────────────────────────────────────────────────────
section("PHASE 3 — Auth Flow: Register -> Login -> /me")

# 3a. Register
token = None
try:
    payload = {
        "first_name": "Test",
        "last_name": "User",
        "phone": "0500000000",
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
    }
    r = requests.post(f"{BASE}/api/auth/register", json=payload, timeout=10)
    if r.status_code == 200:
        data = r.json()
        print(f"{PASS} POST /api/auth/register -> id={data.get('id')}, email={data.get('email')}")
    else:
        print(f"{FAIL} Register returned {r.status_code}: {r.text[:300]}")
        sys.exit(1)
except Exception as e:
    print(f"{FAIL} Register request failed: {e}")
    sys.exit(1)

# 3b. Login
try:
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=10)
    if r.status_code == 200:
        data = r.json()
        token = data.get("token") or data.get("access_token")
        user = data.get("user", {})
        print(f"{PASS} POST /api/auth/login -> token present={bool(token)}, user={user.get('email')}")
    else:
        print(f"{FAIL} Login returned {r.status_code}: {r.text[:300]}")
        sys.exit(1)
except Exception as e:
    print(f"{FAIL} Login request failed: {e}")
    sys.exit(1)

# 3c. Wrong-password login -> should get 401
try:
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": TEST_EMAIL, "password": "wrongpass"}, timeout=10)
    if r.status_code == 401:
        print(f"{PASS} Wrong-password login correctly returns 401")
    else:
        print(f"{FAIL} Expected 401 for wrong password, got {r.status_code}")
except Exception as e:
    print(f"{FAIL} Wrong-password test failed: {e}")

# 3d. GET /auth/me with valid token
try:
    r = requests.get(f"{BASE}/api/auth/me",
                     headers={"Authorization": f"Bearer {token}"}, timeout=10)
    if r.status_code == 200:
        me = r.json()
        print(f"{PASS} GET /api/auth/me -> email={me.get('email')}, role={me.get('role')}")
    else:
        print(f"{FAIL} /auth/me returned {r.status_code}: {r.text[:300]}")
except Exception as e:
    print(f"{FAIL} /auth/me request failed: {e}")

# 3e. /auth/me with no token -> should get 401
try:
    r = requests.get(f"{BASE}/api/auth/me", timeout=10)
    if r.status_code == 401:
        print(f"{PASS} /auth/me without token correctly returns 401")
    else:
        print(f"{FAIL} Expected 401 without token, got {r.status_code}")
except Exception as e:
    print(f"{FAIL} Unauthenticated /auth/me test failed: {e}")


# ─────────────────────────────────────────────────────────
# PHASE 4: Entities CRUD
# ─────────────────────────────────────────────────────────
section("PHASE 4 — CRUD: Policy Entity")

policy_id = None
try:
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.post(f"{BASE}/api/entities/Policy", json={
        "file_name": "test_policy.txt",
        "description": "Connectivity test policy",
        "department": "IT Security",
        "version": "1.0",
        "status": "uploaded",
        "content_preview": "access control encryption authentication",
    }, headers=headers, timeout=10)
    if r.status_code == 200:
        policy_id = r.json().get("id")
        print(f"{PASS} Create Policy -> id={policy_id}")
    else:
        print(f"{FAIL} Create Policy returned {r.status_code}: {r.text[:200]}")
except Exception as e:
    print(f"{FAIL} Create Policy failed: {e}")

if policy_id:
    try:
        r = requests.get(f"{BASE}/api/entities/Policy/{policy_id}", headers=headers, timeout=10)
        if r.status_code == 200:
            print(f"{PASS} Read Policy -> file_name={r.json().get('file_name')}")
        else:
            print(f"{FAIL} Read Policy returned {r.status_code}")
    except Exception as e:
        print(f"{FAIL} Read Policy failed: {e}")

    try:
        r = requests.delete(f"{BASE}/api/entities/Policy/{policy_id}", headers=headers, timeout=10)
        if r.status_code == 200:
            print(f"{PASS} Delete Policy -> {r.json()}")
        else:
            print(f"{FAIL} Delete Policy returned {r.status_code}")
    except Exception as e:
        print(f"{FAIL} Delete Policy failed: {e}")


# ─────────────────────────────────────────────────────────
# PHASE 5: Frontend -> Backend contract check
# ─────────────────────────────────────────────────────────
section("PHASE 5 — Frontend/Backend Contract")

from backend import schemas, models as m

register_fields = set(schemas.RegisterRequest.model_fields.keys())
policy_fields   = set(f for f in dir(m.Policy) if not f.startswith("_"))

results = {
    "Register schema has first_name":   "first_name"  in register_fields,
    "Register schema has last_name":    "last_name"   in register_fields,
    "Register schema has phone":        "phone"       in register_fields,
    "Register schema has email":        "email"       in register_fields,
    "Register schema has password":     "password"    in register_fields,
    "Policy model has content_preview": "content_preview" in policy_fields,
    "Policy model has file_url":        "file_url"    in policy_fields,
}

for label, ok in results.items():
    icon = PASS if ok else FAIL
    print(f"{icon} {label}")


# ─────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────
section("DONE")
print("If all checks show [PASS], your stack is healthy.")
print(f"Test user created: {TEST_EMAIL} / {TEST_PASSWORD}")
print("(You can delete it from the DB or just leave it — it's a unique email.)\n")
