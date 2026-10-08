"""Admin accounts, password hashing, sessions and login throttling."""
import hashlib
import ipaddress
import logging
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import HTTPException, Request

from .config import settings
from .db import pool

log = logging.getLogger("ashwheelz.auth")

SESSION_COOKIE = "aw_admin"
BCRYPT_MAX_BYTES = 72
# Compared against when the username does not exist, so a wrong username
# takes as long as a wrong password and usernames cannot be probed by timing.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(12))


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("ascii")


def verify_password(password: str, password_hash: bytes) -> bool:
    raw = password.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, password_hash)
    except ValueError:
        return False


def _token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode("ascii")).digest()


def ensure_default_admin() -> None:
    """Create the first admin from ADMIN_USERNAME / ADMIN_PASSWORD if none exists."""
    with pool.connection() as conn:
        exists = conn.execute("SELECT 1 FROM admin_users LIMIT 1").fetchone()
        if exists:
            return
        conn.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (%s, %s)",
            (settings.admin_username, hash_password(settings.admin_password)),
        )
        log.info("Created admin user '%s'.", settings.admin_username)
    if settings.admin_password == "1234":
        log.warning(
            "The admin password is the default '1234'. Change it from the dashboard "
            "(Change password) before sharing the site."
        )


# ----------------------------------------------------------------- sessions
def authenticate(username: str, password: str) -> dict | None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash FROM admin_users "
            "WHERE username = %s AND is_active",
            (username.strip().lower(),),
        ).fetchone()
    if row is None:
        verify_password(password, _DUMMY_HASH)
        return None
    if not verify_password(password, row["password_hash"].encode("ascii")):
        return None
    return {"id": row["id"], "username": row["username"]}


def _valid_ip(ip: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        return None


def create_session(admin_id: int, ip: str | None, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)
    with pool.connection() as conn:
        conn.execute("DELETE FROM admin_sessions WHERE expires_at < now()")
        conn.execute(
            "INSERT INTO admin_sessions (admin_user_id, token_hash, ip_address, user_agent, expires_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (admin_id, _token_hash(token), _valid_ip(ip), (user_agent or "")[:500], expires),
        )
        conn.execute("UPDATE admin_users SET last_login_at = now() WHERE id = %s", (admin_id,))
    return token


def delete_session(token: str) -> None:
    with pool.connection() as conn:
        conn.execute("DELETE FROM admin_sessions WHERE token_hash = %s", (_token_hash(token),))


def delete_other_sessions(admin_id: int, keep_token: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            "DELETE FROM admin_sessions WHERE admin_user_id = %s AND token_hash <> %s",
            (admin_id, _token_hash(keep_token)),
        )


def current_admin(request: Request) -> dict:
    """FastAPI dependency: the signed-in admin, or 401."""
    token = request.cookies.get(SESSION_COOKIE)
    if not token or len(token) > 100:
        raise HTTPException(status_code=401, detail="Please sign in.")
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT u.id, u.username FROM admin_sessions s "
            "JOIN admin_users u ON u.id = s.admin_user_id "
            "WHERE s.token_hash = %s AND s.expires_at > now() AND u.is_active",
            (_token_hash(token),),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Your session has ended. Please sign in again.")
    return {"id": row["id"], "username": row["username"], "token": token}


def change_password(admin_id: int, current: str, new: str) -> bool:
    with pool.connection() as conn:
        row = conn.execute("SELECT password_hash FROM admin_users WHERE id = %s", (admin_id,)).fetchone()
        if row is None or not verify_password(current, row["password_hash"].encode("ascii")):
            return False
        conn.execute(
            "UPDATE admin_users SET password_hash = %s WHERE id = %s",
            (hash_password(new), admin_id),
        )
    return True
