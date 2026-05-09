"""Phase 13 backend security configuration tests.

Locks the four hardening surfaces:
  1. SECRET_KEY has no hardcoded default (auth.py)
  2. _validate_required_env() refuses to start if critical env is missing
  3. is_admin(user) is the single source of truth (email path OR role path)
  4. routers/explainability.py calls set_user_context

Plus test 13: a real RLS enforcement check against the live DB. Either
confirms RLS is active for the backend role, or surfaces the bypass mode
loud enough that nobody assumes RLS is the real protection when it isn't.

Run from repo root:
  python -m pytest backend/tests/test_phase13_security_config.py -v
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s)


# ─────────────────────────────────────────────────────────────────────────
# 1. SECRET_KEY has no hardcoded default fallback
# ─────────────────────────────────────────────────────────────────────────
def test_secret_key_has_no_hardcoded_default():
    """auth.py must use os.environ['SECRET_KEY'] (strict), not
    os.environ.get('SECRET_KEY', '<fallback>') (silent)."""
    src = open("backend/auth.py", encoding="utf-8").read()
    norm = _normalize(src)
    assert 'SECRET_KEY = os.environ["SECRET_KEY"]' in norm, (
        "SECRET_KEY must be loaded with strict-mode os.environ[...]; "
        "the previous fallback default made every JWT forgeable"
    )
    # Also assert no string starting with the legacy placeholder value
    assert "hemaya-super-secret-key-change-this-in-production" not in src, (
        "the legacy default fallback string must be gone"
    )


# ─────────────────────────────────────────────────────────────────────────
# 2. backend.auth fails to import when SECRET_KEY is unset
# ─────────────────────────────────────────────────────────────────────────
def test_missing_secret_key_fails_at_import():
    """Spawn a subprocess with SECRET_KEY explicitly removed from env;
    importing backend.auth must raise KeyError. Subprocess isolation is
    needed because the test process already has SECRET_KEY set by
    conftest.py and the module is cached in sys.modules."""
    env = os.environ.copy()
    env.pop("SECRET_KEY", None)
    # Block the .env file from being loaded by stripping CWD interpretation.
    # backend.auth imports cleanly with no dotenv side effects of its own,
    # so we just need to ensure the env var is missing in the child process.
    result = subprocess.run(
        [sys.executable, "-c", "import backend.auth"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(Path("backend").parent),
    )
    assert result.returncode != 0, (
        "backend.auth import should fail when SECRET_KEY is unset; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "KeyError" in result.stderr and "SECRET_KEY" in result.stderr, (
        f"expected KeyError on SECRET_KEY; got stderr={result.stderr!r}"
    )


# ─────────────────────────────────────────────────────────────────────────
# 3. _validate_required_env lists missing env vars
# ─────────────────────────────────────────────────────────────────────────
def test_required_env_validator_lists_missing(monkeypatch):
    from backend.main import _validate_required_env, _REQUIRED_ENV_VARS

    # Strip OPENAI_API_KEY from env
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert "OPENAI_API_KEY" in _REQUIRED_ENV_VARS

    with pytest.raises(RuntimeError) as exc_info:
        _validate_required_env()
    assert "OPENAI_API_KEY" in str(exc_info.value)
    assert "Missing required environment variables" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────────────
# 4. _validate_required_env passes silently when all set
# ─────────────────────────────────────────────────────────────────────────
def test_required_env_validator_passes_when_all_set(monkeypatch):
    from backend.main import _validate_required_env, _REQUIRED_ENV_VARS
    for k in _REQUIRED_ENV_VARS:
        monkeypatch.setenv(k, os.environ.get(k) or f"test-{k}")
    # No exception
    _validate_required_env()


# ─────────────────────────────────────────────────────────────────────────
# 5-8. is_admin helper unit tests
# ─────────────────────────────────────────────────────────────────────────
def test_is_admin_helper_email_match(monkeypatch):
    """Email path: user.email == ADMIN_EMAIL -> True."""
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    # Reload security module to pick up the new env value
    import importlib, backend.security
    importlib.reload(backend.security)
    user = SimpleNamespace(email="boss@example.com", role="user")
    assert backend.security.is_admin(user) is True


def test_is_admin_helper_role_match(monkeypatch):
    """Role path: user.role == 'admin' -> True even with mismatched email."""
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    import importlib, backend.security
    importlib.reload(backend.security)
    user = SimpleNamespace(email="other@example.com", role="admin")
    assert backend.security.is_admin(user) is True


def test_is_admin_helper_neither_match(monkeypatch):
    """Neither email nor role matches -> False."""
    monkeypatch.setenv("ADMIN_EMAIL", "boss@example.com")
    import importlib, backend.security
    importlib.reload(backend.security)
    user = SimpleNamespace(email="other@example.com", role="user")
    assert backend.security.is_admin(user) is False


def test_is_admin_helper_handles_none_user():
    """is_admin(None) returns False, no AttributeError."""
    from backend.security import is_admin
    assert is_admin(None) is False


def test_is_admin_helper_email_disabled_when_unset(monkeypatch):
    """When ADMIN_EMAIL env is empty, only role path can succeed."""
    monkeypatch.setenv("ADMIN_EMAIL", "")
    import importlib, backend.security
    importlib.reload(backend.security)
    # Email match path is disabled
    user_email_only = SimpleNamespace(email="anyone@example.com", role="user")
    assert backend.security.is_admin(user_email_only) is False
    # Role path still works
    user_role = SimpleNamespace(email="anyone@example.com", role="admin")
    assert backend.security.is_admin(user_role) is True


# ─────────────────────────────────────────────────────────────────────────
# 9. ADMIN_EMAIL constant only in security module
# ─────────────────────────────────────────────────────────────────────────
def test_admin_email_constant_only_in_security_module():
    """The literal admin email and any ADMIN_EMAIL = "..." assignment
    must only appear in backend/security.py. main.py + explainability.py
    import the value rather than re-declaring it.

    Test files are excluded from the literal-email scan because this
    test file itself contains the string we're searching for (in this
    very docstring + the search literal below). Production-code-only
    is what matters.
    """
    legacy_email_literal = "himayaadmin" + "@gmail.com"  # split to dodge self-match
    leaks = []
    for p in Path("backend").rglob("*.py"):
        # Skip the test directory — these tests reference the legacy email
        # string in source-grep assertions and would otherwise self-match.
        s = str(p).replace("\\", "/")
        if "/tests/" in s:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if legacy_email_literal in text:
            leaks.append(str(p))
    assert not leaks, (
        "Hardcoded admin email leaked back into backend/: " + ", ".join(leaks)
    )

    # ADMIN_EMAIL should only be ASSIGNED in backend/security.py. Other
    # production files import it. Match `ADMIN_EMAIL = ...` and the
    # type-annotated form `ADMIN_EMAIL: str = ...`. Skip kwarg use
    # (`email=ADMIN_EMAIL`) by anchoring at line start with optional
    # whitespace.
    assignments = []
    pat = re.compile(r"^\s*ADMIN_EMAIL\s*(?::\s*[A-Za-z_]\w*\s*)?=", re.MULTILINE)
    for p in Path("backend").rglob("*.py"):
        s = str(p).replace("\\", "/")
        if "/tests/" in s:
            continue  # skip test directory's grep references
        text = p.read_text(encoding="utf-8", errors="replace")
        for m in pat.finditer(text):
            assignments.append(s)
    assert len(assignments) == 1, (
        f"ADMIN_EMAIL must be assigned in exactly one production file "
        f"(backend/security.py); found {len(assignments)}: {assignments}"
    )
    assert assignments[0].endswith("backend/security.py"), (
        f"ADMIN_EMAIL must live in backend/security.py; found at: {assignments[0]}"
    )


# ─────────────────────────────────────────────────────────────────────────
# 10. is_admin used in main.py + routers/explainability.py
# ─────────────────────────────────────────────────────────────────────────
def test_is_admin_used_in_main_and_explainability():
    """Both files import is_admin from backend.security AND have replaced
    inline `current_user.email == ADMIN_EMAIL` patterns."""
    main_src = open("backend/main.py", encoding="utf-8").read()
    expl_src = open("backend/routers/explainability.py", encoding="utf-8").read()

    assert "from backend.security import" in main_src
    assert "is_admin" in main_src
    assert "from backend.security import is_admin" in expl_src

    # No surviving inline `current_user.email == ADMIN_EMAIL` or
    # `current_user.email != ADMIN_EMAIL` patterns
    assert not re.search(r"current_user\.email\s*==\s*ADMIN_EMAIL", main_src)
    assert not re.search(r"current_user\.email\s*!=\s*ADMIN_EMAIL", main_src)
    assert not re.search(r"user\.email\s*!=\s*ADMIN_EMAIL", expl_src)


# ─────────────────────────────────────────────────────────────────────────
# 11. explainability calls set_user_context
# ─────────────────────────────────────────────────────────────────────────
def test_explainability_calls_set_user_context():
    """The router's _get_current_user must call set_user_context so RLS
    fires for queries through this router."""
    src = open("backend/routers/explainability.py", encoding="utf-8").read()
    norm = _normalize(src)
    assert "from backend.database import get_db, set_user_context" in norm
    assert "set_user_context(db, user.id)" in norm


# ─────────────────────────────────────────────────────────────────────────
# 12. require_admin uses the is_admin helper
# ─────────────────────────────────────────────────────────────────────────
def test_require_admin_uses_is_admin_helper():
    src = open("backend/main.py", encoding="utf-8").read()
    # Find the require_admin function body
    m = re.search(
        r"def require_admin\([^)]*\)[^:]*:\s*\"{0,3}.*?\"{0,3}\s*"
        r"(?P<body>.*?)(?=\n(?:def |class |@app\.|#\s*━))",
        src, re.DOTALL,
    )
    assert m, "require_admin definition not found"
    body = m.group("body")
    assert "is_admin(current_user)" in body, (
        f"require_admin must call is_admin(current_user); body was:\n{body}"
    )
    assert (
        "current_user.email == ADMIN_EMAIL" not in body
        and "current_user.email != ADMIN_EMAIL" not in body
    ), "require_admin must not contain inline email comparisons"


# ─────────────────────────────────────────────────────────────────────────
# 13. Real RLS enforcement verification (per user correction 1)
#     Either confirms RLS active for backend role, or documents the
#     bypass mode. Test passes either way; the print line in CI logs
#     captures which mode this deploy is in.
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set; skipping live RLS check",
)
def test_rls_enforces_policy_isolation_or_documents_bypass():
    """Live DB test. SET LOCAL app.current_user_id to user A; query a
    policy owned by user B; assert the count is 0 (RLS active) OR 1
    (RLS bypassed for backend role) AND log which mode this is.

    Either outcome is a documented mode. The test surfaces the truth so
    nobody silently assumes RLS is the real protection.
    """
    from sqlalchemy import create_engine, text as sql_text
    db_url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://", 1)
    engine = create_engine(db_url, pool_pre_ping=True)

    with engine.connect() as conn:
        # Find two distinct users that own policies
        a = conn.execute(sql_text(
            "SELECT DISTINCT owner_id FROM policies "
            "WHERE owner_id IS NOT NULL ORDER BY owner_id LIMIT 1"
        )).fetchone()
        b = conn.execute(sql_text(
            "SELECT DISTINCT owner_id FROM policies "
            "WHERE owner_id IS NOT NULL AND owner_id != :a ORDER BY owner_id LIMIT 1"
        ), {"a": a[0] if a else None}).fetchone()
        if not a or not b:
            pytest.skip("test environment lacks two distinct policy owners")

        b_policy = conn.execute(sql_text(
            "SELECT id FROM policies WHERE owner_id = :owner LIMIT 1"
        ), {"owner": str(b[0])}).fetchone()
        assert b_policy

        # Probe whether the backend's current role bypasses RLS
        rls_attr = conn.execute(sql_text(
            "SELECT rolbypassrls, current_user FROM pg_roles "
            "WHERE rolname = current_user"
        )).fetchone()
        bypass_attr = bool(rls_attr[0]) if rls_attr else False
        role_name = str(rls_attr[1]) if rls_attr else "?"

        # Need a transaction for SET LOCAL
        with engine.begin() as tx:
            tx.execute(sql_text("SET LOCAL app.current_user_id = :uid"),
                       {"uid": str(a[0])})
            visible = tx.execute(sql_text(
                "SELECT COUNT(*) FROM policies WHERE id = :pid"
            ), {"pid": str(b_policy[0])}).fetchone()[0]

        if visible == 0:
            print(
                f"\n[Phase 13][RLS] role={role_name!r} bypassrls={bypass_attr} "
                f"-> RLS ACTIVE for backend role: cross-user policy not visible. "
                f"Defense-in-depth confirmed."
            )
        else:
            print(
                f"\n[Phase 13][RLS] role={role_name!r} bypassrls={bypass_attr} "
                f"-> RLS BYPASSED for backend role: cross-user policy visible "
                f"(count={visible}). Backend ownership checks remain the real "
                f"protection. RLS in this deploy guards only direct DB access "
                f"(Supabase Dashboard / REST API)."
            )

        # Sanity: must be 0 or 1, not a weird number
        assert visible in (0, 1), (
            f"unexpected visible count {visible} for cross-user policy"
        )
