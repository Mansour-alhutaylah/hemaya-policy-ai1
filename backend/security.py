"""Phase 13 security helpers.

Single source of truth for admin detection. Replaces the legacy pattern
of comparing `current_user.email` against a hardcoded constant scattered
across two files (main.py, routers/explainability.py) at 19 sites.

Two paths to admin (either is sufficient):
  1. user.email matches the ADMIN_EMAIL env var (operator-level admin).
  2. user.role == "admin" in the users table (DB-driven admin; promotes
     to admin without code deploy via plain UPDATE).

ADMIN_EMAIL is loaded from env. If unset, only role-based admin works,
which is fine — operators just need to set users.role='admin' on the
intended account.

The require_admin FastAPI dependency lives in main.py to avoid a
circular import (it depends on get_current_user, which lives in
main.py); this module exposes only the pure is_admin() helper.
"""
from __future__ import annotations

import os
from typing import Any, Optional


# Empty string disables email-based admin (role-based still works).
ADMIN_EMAIL: str = os.environ.get("ADMIN_EMAIL", "")


def is_admin(user: Optional[Any]) -> bool:
    """Return True iff the user is an admin via either path.

    Accepts the SQLAlchemy User object (or any object with .email and
    .role attributes). Returns False on None to avoid AttributeError
    in callers that may receive an unauthenticated user.
    """
    if user is None:
        return False
    # Path 1: env-configured admin email
    if ADMIN_EMAIL:
        email = getattr(user, "email", None)
        if email == ADMIN_EMAIL:
            return True
    # Path 2: DB-driven role
    if getattr(user, "role", None) == "admin":
        return True
    return False
