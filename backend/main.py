from contextlib import contextmanager
from functools import lru_cache
import os
from pathlib import Path
import sqlite3

import bcrypt
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = Path(__file__).resolve().parent / "users.db"
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
METER_LOCATIONS = (
    "Oslo",
    "Berlin",
    "Dubai",
    "Toronto",
    "Singapore",
    "Auckland",
    "Stockholm",
    "Zurich",
)

app = FastAPI(title="Secure Access Portal")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CredentialsPayload(BaseModel):
    username: str
    password: str


class PromotePayload(BaseModel):
    username: str


class PasswordPayload(BaseModel):
    oldPassword: str
    newPassword: str


class UserSession:
    def __init__(self):
        self.user = None

session_store = UserSession()


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db_connection():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_username_nocase "
            "ON users (username COLLATE NOCASE)"
        )

        admin = conn.execute(
            "SELECT role FROM users WHERE username = ?", (ADMIN_USERNAME,)
        ).fetchone()
        if admin is None:
            admin_hash = bcrypt.hashpw(
                ADMIN_PASSWORD.encode(), bcrypt.gensalt()
            ).decode()
            conn.execute(
                "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (ADMIN_USERNAME, admin_hash, "admin"),
            )
        elif admin["role"] != "admin":
            conn.execute(
                "UPDATE users SET role = ? WHERE username = ?",
                ("admin", ADMIN_USERNAME),
            )


def get_user_by_username(username: str):
    with db_connection() as conn:
        return conn.execute(
            "SELECT id, username, password, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()


def user_exists(username: str):
    with db_connection() as conn:
        return conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone() is not None


def create_user(username: str, password: str, role: str):
    hashed_password = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with db_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            (username, hashed_password, role),
        )
        user_id = cursor.lastrowid
    return {"id": user_id, "username": username, "role": role}


@lru_cache(maxsize=1024)
def get_meter_profile(username: str):
    seed = sum(ord(ch) for ch in username)
    usage = [
        32 + (seed % 14),
        28 + (seed % 12),
        36 + (seed % 15),
        41 + (seed % 13),
        46 + (seed % 16),
        52 + (seed % 14),
    ]
    bill = 40 + (seed % 25) + usage[5] * 0.9
    return {
        "meterId": f"LG-{(1000 + (seed % 9000)):04d}",
        "location": f"{METER_LOCATIONS[seed % len(METER_LOCATIONS)]} • Grid Node",
        "status": "Online",
        "usage": usage,
        "billing": f"{bill:.2f}",
        "tariff": "TOU • Peak Saver",
        "voltage": f"{218 + (seed % 12)}V",
    }


init_db()


@app.get("/api/me")
def get_me():
    if not session_store.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        )
    return {"authenticated": True, "user": session_store.user}


@app.post("/api/login")
def login(payload: CredentialsPayload):
    user_row = get_user_by_username(payload.username)
    if not user_row:
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    password_matches = bcrypt.checkpw(
        payload.password.encode(), user_row["password"].encode()
    )
    if not password_matches:
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    session_store.user = {
        "id": user_row["id"],
        "username": user_row["username"],
        "role": user_row["role"],
    }
    return {"success": True, "user": session_store.user}


@app.post("/api/register")
def register(payload: CredentialsPayload):
    if user_exists(payload.username):
        raise HTTPException(status_code=409, detail="That username is already taken.")
    try:
        user = create_user(payload.username, payload.password, "user")
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409, detail="That username is already taken."
        ) from None
    session_store.user = user
    return {"success": True, "user": user}


@app.post("/api/admin/add")
def add_admin(payload: CredentialsPayload):
    if not session_store.user or session_store.user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can add new admins.")
    duplicate_message = (
        "That username already exists. Use the promote option for an existing user."
    )
    if user_exists(payload.username):
        raise HTTPException(status_code=409, detail=duplicate_message)
    try:
        user = create_user(payload.username, payload.password, "admin")
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=duplicate_message) from None
    return {"success": True, "user": user}


@app.post("/api/admin/promote")
def promote_user(payload: PromotePayload):
    if not session_store.user or session_store.user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admins can promote users.")
    with db_connection() as conn:
        cursor = conn.execute(
            "UPDATE users SET role = ? WHERE username = ? AND role != ?",
            ("admin", payload.username, "admin"),
        )
        if cursor.rowcount == 0:
            existing_user = conn.execute(
                "SELECT role FROM users WHERE username = ?", (payload.username,)
            ).fetchone()
            if not existing_user:
                raise HTTPException(
                    status_code=404,
                    detail="User not found. Use the create-new-admin form instead.",
                )
            raise HTTPException(
                status_code=409, detail="That user is already an admin."
            )
    return {"success": True, "user": {"username": payload.username, "role": "admin"}}


@app.post("/api/password/change")
def change_password(payload: PasswordPayload):
    if not session_store.user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    with db_connection() as conn:
        user_row = conn.execute(
            "SELECT password FROM users WHERE username = ?",
            (session_store.user["username"],),
        ).fetchone()
        if not user_row:
            raise HTTPException(status_code=404, detail="User not found.")
        if not bcrypt.checkpw(
            payload.oldPassword.encode(), user_row["password"].encode()
        ):
            raise HTTPException(status_code=401, detail="Invalid credentials.")
        hashed_password = bcrypt.hashpw(
            payload.newPassword.encode(), bcrypt.gensalt()
        ).decode()
        conn.execute(
            "UPDATE users SET password = ? WHERE username = ?",
            (hashed_password, session_store.user["username"]),
        )
    return {"success": True}


@app.get("/api/users/search")
def search_users(q: str):
    if not session_store.user or session_store.user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    if not q:
        return []
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, role FROM users "
            "WHERE username != ? AND username LIKE ? COLLATE NOCASE "
            "ORDER BY username COLLATE NOCASE LIMIT 10",
            (session_store.user["username"], f"{q}%"),
        ).fetchall()
    return [dict(row) for row in rows]


@app.get("/api/users/detail")
def user_detail(username: str):
    if not session_store.user or session_store.user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Forbidden")
    with db_connection() as conn:
        row = conn.execute(
            "SELECT id, username, role FROM users WHERE username = ?", (username,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return {**dict(row), "profile": get_meter_profile(row["username"])}


@app.get("/api/me/profile")
def my_profile():
    if not session_store.user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    with db_connection() as conn:
        row = conn.execute(
            "SELECT id, username, role FROM users WHERE username = ?",
            (session_store.user["username"],),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    return {**dict(row), "profile": get_meter_profile(row["username"])}


@app.post("/api/logout")
def logout():
    session_store.user = None
    return {"success": True}
