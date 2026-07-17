from base64 import urlsafe_b64encode
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import time

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request, Response


SESSION_COOKIE = "portal_session"
SESSION_MAX_AGE = 60 * 60 * 8

_db_path: Path | None = None
_fernet: Fernet | None = None


@dataclass(frozen=True)
class PortalSession:
    user_id: int
    auth_type: str
    id_token: str | None
    expires_at: int


def configure_session_store(db_path: Path, encryption_secret: str):
    global _db_path, _fernet
    if len(encryption_secret) < 32:
        raise RuntimeError("OIDC_SESSION_SECRET must contain at least 32 characters.")
    _db_path = Path(db_path)
    key = urlsafe_b64encode(hashlib.sha256(encryption_secret.encode()).digest())
    _fernet = Fernet(key)
    with _connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portal_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                auth_type TEXT NOT NULL CHECK (auth_type IN ('local', 'oidc')),
                encrypted_id_token TEXT,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_portal_sessions_user_id "
            "ON portal_sessions (user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_portal_sessions_expires_at "
            "ON portal_sessions (expires_at)"
        )


@contextmanager
def _connection():
    if _db_path is None:
        raise RuntimeError("Portal session store has not been configured.")
    conn = sqlite3.connect(_db_path, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _token_hash(token: str):
    return hashlib.sha256(token.encode()).hexdigest()


def _encrypt(value: str | None):
    if not value:
        return None
    if _fernet is None:
        raise RuntimeError("Portal session encryption has not been configured.")
    return _fernet.encrypt(value.encode()).decode()


def _decrypt(value: str | None):
    if not value:
        return None
    if _fernet is None:
        raise RuntimeError("Portal session encryption has not been configured.")
    return _fernet.decrypt(value.encode()).decode()


def create_session(
    response: Response,
    user_id: int,
    auth_type: str = "local",
    id_token: str | None = None,
):
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    expires_at = now + SESSION_MAX_AGE
    with _connection() as conn:
        conn.execute("DELETE FROM portal_sessions WHERE expires_at <= ?", (now,))
        conn.execute(
            """
            INSERT INTO portal_sessions
                (token_hash, user_id, auth_type, encrypted_id_token, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _token_hash(token),
                user_id,
                auth_type,
                _encrypt(id_token),
                now,
                expires_at,
            ),
        )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    )
    return token


def get_session(request: Request):
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token:
        return None
    now = int(time.time())
    token_hash = _token_hash(token)
    with _connection() as conn:
        row = conn.execute(
            """
            SELECT user_id, auth_type, encrypted_id_token, expires_at
            FROM portal_sessions WHERE token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
        if not row or row["expires_at"] <= now:
            conn.execute("DELETE FROM portal_sessions WHERE token_hash = ?", (token_hash,))
            return None
    try:
        id_token = _decrypt(row["encrypted_id_token"])
    except InvalidToken:
        with _connection() as conn:
            conn.execute("DELETE FROM portal_sessions WHERE token_hash = ?", (token_hash,))
        return None
    return PortalSession(row["user_id"], row["auth_type"], id_token, row["expires_at"])


def discard_session(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with _connection() as conn:
            conn.execute(
                "DELETE FROM portal_sessions WHERE token_hash = ?", (_token_hash(token),)
            )


def clear_session(request: Request, response: Response):
    discard_session(request)
    response.delete_cookie(SESSION_COOKIE)


def invalidate_user_sessions(user_id: int):
    with _connection() as conn:
        conn.execute("DELETE FROM portal_sessions WHERE user_id = ?", (user_id,))
