"""Pytest fixtures shared across the backend test suite.

Phase 13 introduced `os.environ["SECRET_KEY"]` as a hard requirement at
backend.auth import time. The dev .env carries the value, but pytest may
not have loaded dotenv before the first test collects backend.auth (the
order depends on which test triggers the import first). This autouse
session fixture sets a placeholder SECRET_KEY (and a placeholder
ADMIN_EMAIL) so test imports never hit a KeyError on a clean checkout
of the repo. Production code is unaffected; these values are only ever
seen by the test process.
"""
import os

import pytest

# Load .env early so DATABASE_URL and other real values are available
# to tests that hit the live DB (e.g. the Phase 13 RLS verification).
# setdefault below still wins for SECRET_KEY etc on a clean checkout.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@pytest.fixture(autouse=True, scope="session")
def _ensure_required_env_for_tests():
    # Use setdefault so a real .env or CI-injected value wins.
    os.environ.setdefault("SECRET_KEY", "test-secret-not-for-prod")
    os.environ.setdefault("ADMIN_EMAIL", "test-admin@example.com")
    # OPENAI_API_KEY and DATABASE_URL are validated by main.py's
    # _validate_required_env at app startup, but most unit tests don't
    # boot the app — they import individual helpers. Set placeholders
    # so importing main doesn't blow up in tests that monkey-patch
    # the OpenAI client.
    os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-for-prod")
    yield
