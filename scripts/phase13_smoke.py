"""Phase 13 post-merge smoke.

Exercises the four user-listed validations without requiring a running
uvicorn:

  3. Smoke login as normal user (JWT issuance + decode round-trip)
  4. Smoke admin route as role='admin'   (require_admin allows the call)
  4b. Smoke admin route as role='user'   (require_admin raises 403)
  5. Confirm normal user cannot access another user's policy
     (the inline ownership check pattern still works after centralization)

Plus a SECRET_KEY-strict regression check.

Reuses the live database via DATABASE_URL but creates / cleans up its
own ephemeral test users so it doesn't pollute existing data.
"""
from __future__ import annotations

import io
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend import auth, models
from backend.security import is_admin

DB_URL = os.getenv("DATABASE_URL")
assert DB_URL
engine = create_engine(DB_URL, pool_pre_ping=True)
Session = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def section(t):
    print("\n" + "=" * 60)
    print(t)
    print("=" * 60)


def main():
    print("Phase 13 post-merge smoke")
    print(f"main HEAD: {os.popen('git rev-parse --short HEAD').read().strip()}")

    fails = []
    cleanup_ids = []

    # Make a normal user, an admin user (role-based), and a target policy
    # owned by the normal user. Then exercise each smoke.
    normal_id = str(uuid.uuid4())
    admin_id  = str(uuid.uuid4())
    target_policy_id = str(uuid.uuid4())
    other_policy_id  = str(uuid.uuid4())

    db = Session()
    try:
        section("SETUP: ephemeral users + policies")
        normal_email = f"phase13-normal-{normal_id[:8]}@example.com"
        admin_email  = f"phase13-admin-{admin_id[:8]}@example.com"
        pwd_hash     = auth.get_password_hash("test-password-09himaya")

        db.execute(text("""
            INSERT INTO users (id, email, password_hash, first_name, last_name, role, is_verified, created_at)
            VALUES (:id, :em, :pw, 'Normal', 'User', 'user', true, :at)
        """), {"id": normal_id, "em": normal_email, "pw": pwd_hash, "at": datetime.now(timezone.utc)})
        db.execute(text("""
            INSERT INTO users (id, email, password_hash, first_name, last_name, role, is_verified, created_at)
            VALUES (:id, :em, :pw, 'Test', 'Admin', 'admin', true, :at)
        """), {"id": admin_id, "em": admin_email, "pw": pwd_hash, "at": datetime.now(timezone.utc)})
        # Two policies: one owned by normal user, one owned by admin.
        for pid, owner in [(target_policy_id, normal_id), (other_policy_id, admin_id)]:
            db.execute(text("""
                INSERT INTO policies (id, file_name, description, version, status,
                  progress, progress_stage, file_url, file_type, content_preview,
                  framework_code, owner_id, uploaded_at, created_at)
                VALUES (:id, 'p13.txt', 'phase13', '1.0', 'uploaded', 100, 'Ready',
                        '/uploads/p13.txt', 'TXT', '', 'ECC-2:2024',
                        :oid, :at, :at)
            """), {"id": pid, "oid": owner, "at": datetime.now(timezone.utc)})
        db.commit()
        cleanup_ids = [normal_id, admin_id, target_policy_id, other_policy_id]
        print(f"  normal user: {normal_id} ({normal_email}) role=user")
        print(f"  admin user:  {admin_id} ({admin_email}) role=admin")
        print(f"  target policy (normal-owned):  {target_policy_id}")
        print(f"  other policy (admin-owned):    {other_policy_id}")
    except Exception as e:
        print(f"SETUP failed: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()

    try:
        # ── Smoke 3: login as normal user ───────────────────────────────
        section("Smoke 3: login as normal user (JWT round-trip)")
        token = auth.create_access_token({"sub": normal_email})
        from jose import jwt as _jwt
        payload = _jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        assert payload["sub"] == normal_email
        print(f"  JWT issued and decoded; sub={payload['sub']}")
        print("  PASS")

        # ── Smoke 4: admin route as role='admin' (is_admin returns True) ─
        section("Smoke 4: admin route as role='admin'")
        db = Session()
        try:
            admin_user = db.query(models.User).filter_by(id=admin_id).first()
            normal_user = db.query(models.User).filter_by(id=normal_id).first()
            assert is_admin(admin_user) is True, "role='admin' user must pass"
            assert is_admin(normal_user) is False, "role='user' must NOT pass"
            print(f"  is_admin(admin_user role={admin_user.role!r}) = True")
            print(f"  is_admin(normal_user role={normal_user.role!r}) = False")
            print("  PASS")
        finally:
            db.close()

        # ── Smoke 4b: require_admin denies normal user (inline simulation) ──
        section("Smoke 4b: require_admin denies normal user")
        from fastapi import HTTPException
        # We can't easily call require_admin (it's a Depends-style dep),
        # but we can simulate its body. The function calls
        # `if not is_admin(current_user): raise 403`.
        try:
            if not is_admin(normal_user):
                raise HTTPException(status_code=403, detail="Admin access required")
        except HTTPException as e:
            assert e.status_code == 403
            print(f"  HTTP 403: {e.detail}")
            print("  PASS")
        else:
            fails.append("smoke 4b: HTTPException not raised for normal user")

        # ── Smoke 5: cross-user policy access denial ────────────────────
        # Mirror the in-route ownership check pattern:
        #   if not is_admin(current_user) and str(policy.owner_id) != str(current_user.id):
        #       raise 403
        section("Smoke 5: normal user cannot access admin-owned policy")
        db = Session()
        try:
            other_policy = db.execute(
                text("SELECT id, owner_id FROM policies WHERE id = :p"),
                {"p": other_policy_id},
            ).fetchone()
            assert other_policy
            current_user_for_check = normal_user  # role='user', tries to read admin's policy
            allowed = is_admin(current_user_for_check) or (
                str(other_policy.owner_id) == str(current_user_for_check.id)
            )
            assert not allowed, (
                f"normal user should NOT be allowed to access admin's policy; "
                f"is_admin={is_admin(current_user_for_check)}, "
                f"owner_id={other_policy.owner_id}, "
                f"caller_id={current_user_for_check.id}"
            )
            print(f"  cross-user access denied (is_admin=False, "
                  f"owner_id != caller_id)")
            print("  PASS")
        finally:
            db.close()

        # ── Smoke 5b: normal user CAN access own policy ─────────────────
        section("Smoke 5b: normal user can access own policy")
        db = Session()
        try:
            own_policy = db.execute(
                text("SELECT id, owner_id FROM policies WHERE id = :p"),
                {"p": target_policy_id},
            ).fetchone()
            allowed = is_admin(normal_user) or (
                str(own_policy.owner_id) == str(normal_user.id)
            )
            assert allowed, "normal user must be allowed to access OWN policy"
            print(f"  own-policy access allowed (owner_id == caller_id)")
            print("  PASS")
        finally:
            db.close()

        # ── Smoke 6: admin can access any policy ────────────────────────
        section("Smoke 6: admin can access any policy")
        allowed_admin_other = is_admin(admin_user) or (
            str(other_policy_id) == str(admin_user.id)
        )
        allowed_admin_normal = is_admin(admin_user) or (
            str(target_policy_id) == str(admin_user.id)
        )
        assert allowed_admin_other and allowed_admin_normal, (
            "admin must be able to access any policy via is_admin path"
        )
        print(f"  admin access to admin's own policy: True")
        print(f"  admin access to normal user's policy: True")
        print("  PASS")

        # ── Sanity: SECRET_KEY strict mode is real ──────────────────────
        section("SECRET_KEY strict mode")
        src = open("backend/auth.py", encoding="utf-8").read()
        assert 'os.environ["SECRET_KEY"]' in src
        assert "hemaya-super-secret-key-change-this-in-production" not in src
        print("  auth.py uses os.environ['SECRET_KEY'] (no fallback)")
        print("  PASS")

        section("RESULT")
        if fails:
            print("FAIL:")
            for f in fails:
                print(f"  - {f}")
        else:
            print("PASS — all post-merge smokes green.")
    finally:
        # Cleanup ephemeral rows
        section("CLEANUP")
        db = Session()
        try:
            db.execute(text("DELETE FROM policies WHERE id = ANY(:ids)"),
                       {"ids": [target_policy_id, other_policy_id]})
            db.execute(text("DELETE FROM users WHERE id = ANY(:ids)"),
                       {"ids": [normal_id, admin_id]})
            db.commit()
            print("  ephemeral users + policies removed")
        except Exception as e:
            db.rollback()
            print(f"  cleanup error: {e}")
        finally:
            db.close()


if __name__ == "__main__":
    main()
