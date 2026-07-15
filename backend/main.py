from contextlib import contextmanager
from functools import lru_cache
import os
from pathlib import Path
import secrets
import sqlite3
from typing import Literal

import bcrypt
from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


DB_PATH = Path(os.getenv("PORTAL_DB_PATH", Path(__file__).resolve().parent / "users.db"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
SESSION_COOKIE = "portal_session"
SESSION_MAX_AGE = 60 * 60 * 8

Role = Literal["admin", "utilities", "business_analyst", "sales_person"]
REGIONS = ("texas", "noida", "alpharetta", "germany")
ROLE_LABELS = {
    "admin": "Administrator",
    "utilities": "Utilities",
    "business_analyst": "Business Analyst",
    "sales_person": "Sales Person",
}

DEMO_ACCOUNTS = (
    ("utilities_demo", "utilities-demo", "utilities", None),
    ("business_analyst", "analyst-demo", "business_analyst", None),
    ("sales_texas", "sales-demo", "sales_person", "texas"),
    ("sales_noida", "sales-demo", "sales_person", "noida"),
    ("sales_alpharetta", "sales-demo", "sales_person", "alpharetta"),
    ("sales_germany", "sales-demo", "sales_person", "germany"),
)

CUSTOMER_DATA = (
    ("Lone Star Energy", "texas", "Electricity", 1840, 126000, "Active"),
    ("Austin Municipal Grid", "texas", "Electricity", 1425, 98500, "Active"),
    ("Gulf Water Services", "texas", "Water", 960, 67400, "Renewal due"),
    ("Noida Power Works", "noida", "Electricity", 2110, 118000, "Active"),
    ("Yamuna Utilities", "noida", "Water", 1260, 74400, "Active"),
    ("Sector 62 Microgrid", "noida", "Electricity", 880, 51900, "New"),
    ("North Fulton Energy", "alpharetta", "Electricity", 1560, 109000, "Active"),
    ("Alpharetta Water Board", "alpharetta", "Water", 1030, 72100, "Active"),
    ("Windward Smart Campus", "alpharetta", "Electricity", 790, 58300, "New"),
    ("Rhein Energie Partner", "germany", "Electricity", 2450, 172000, "Active"),
    ("Bavaria Stadtwerke", "germany", "Gas", 1980, 149000, "Active"),
    ("Nordsee Grid GmbH", "germany", "Electricity", 1375, 101500, "Renewal due"),
)

METER_LOCATIONS = (
    "Texas", "Noida", "Alpharetta", "Germany", "Toronto", "Singapore"
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


class PasswordPayload(BaseModel):
    oldPassword: str
    newPassword: str = Field(min_length=8)


class AccountCreatePayload(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=8, max_length=128)
    role: Role
    region: str | None = None


class AccountUpdatePayload(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Role
    region: str | None = None


class DeleteAccountPayload(BaseModel):
    confirmation: str


# Session ids contain no user information. The associated user is reloaded from the
# database on every request so role and region changes take effect immediately.
session_store: dict[str, int] = {}


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


def hash_password(password: str):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def public_user(row):
    return {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "roleLabel": ROLE_LABELS.get(row["role"], row["role"]),
        "region": row["region"],
    }


def normalize_region(role: str, region: str | None):
    if role != "sales_person":
        return None
    normalized = (region or "").strip().lower()
    if normalized not in REGIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Sales people must be assigned to one of: {', '.join(REGIONS)}.",
        )
    return normalized


def clean_username(username: str):
    value = username.strip()
    if len(value) < 3 or not all(ch.isalnum() or ch in "._-" for ch in value):
        raise HTTPException(
            status_code=422,
            detail="Username must be at least 3 characters and use only letters, numbers, ., _ or -.",
        )
    return value


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL,
                region TEXT
            )
            """
        )
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
        if "region" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN region TEXT")

        # Migrate the former user role without invalidating existing accounts.
        conn.execute("UPDATE users SET role = 'utilities' WHERE role = 'user'")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_username_nocase "
            "ON users (username COLLATE NOCASE)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS customer_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_name TEXT NOT NULL,
                region TEXT NOT NULL,
                utility_type TEXT NOT NULL,
                usage_mwh INTEGER NOT NULL,
                revenue INTEGER NOT NULL,
                status TEXT NOT NULL,
                UNIQUE(customer_name, region)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS portal_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        admin = conn.execute(
            "SELECT id, role FROM users WHERE username = ? COLLATE NOCASE",
            (ADMIN_USERNAME,),
        ).fetchone()
        if admin is None:
            conn.execute(
                "INSERT INTO users (username, password, role, region) VALUES (?, ?, 'admin', NULL)",
                (ADMIN_USERNAME, hash_password(ADMIN_PASSWORD)),
            )
        elif admin["role"] != "admin":
            conn.execute(
                "UPDATE users SET role = 'admin', region = NULL WHERE id = ?", (admin["id"],)
            )

        demo_accounts_seeded = conn.execute(
            "SELECT 1 FROM portal_metadata WHERE key = 'demo_accounts_seeded'"
        ).fetchone()
        if not demo_accounts_seeded:
            for username, password, role, region in DEMO_ACCOUNTS:
                exists = conn.execute(
                    "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (username,)
                ).fetchone()
                if not exists:
                    conn.execute(
                        "INSERT INTO users (username, password, role, region) VALUES (?, ?, ?, ?)",
                        (username, hash_password(password), role, region),
                    )
            conn.execute(
                "INSERT INTO portal_metadata (key, value) VALUES ('demo_accounts_seeded', 'true')"
            )

        conn.executemany(
            """
            INSERT OR IGNORE INTO customer_data
                (customer_name, region, utility_type, usage_mwh, revenue, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            CUSTOMER_DATA,
        )


def get_user_by_username(username: str):
    with db_connection() as conn:
        return conn.execute(
            "SELECT id, username, password, role, region FROM users "
            "WHERE username = ? COLLATE NOCASE",
            (username.strip(),),
        ).fetchone()


def create_user(username: str, password: str, role: str, region: str | None = None):
    username = clean_username(username)
    region = normalize_region(role, region)
    with db_connection() as conn:
        if conn.execute(
            "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE", (username,)
        ).fetchone():
            raise HTTPException(status_code=409, detail="That username is already taken.")
        cursor = conn.execute(
            "INSERT INTO users (username, password, role, region) VALUES (?, ?, ?, ?)",
            (username, hash_password(password), role, region),
        )
        row = conn.execute(
            "SELECT id, username, role, region FROM users WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
    return public_user(row)


def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    user_id = session_store.get(token or "")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    with db_connection() as conn:
        row = conn.execute(
            "SELECT id, username, role, region FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if not row:
        session_store.pop(token, None)
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return public_user(row)


def require_role(request: Request, *roles: str):
    user = current_user(request)
    if user["role"] not in roles:
        raise HTTPException(status_code=403, detail="You do not have access to this data.")
    return user


@lru_cache(maxsize=1024)
def get_meter_profile(username: str):
    seed = sum(ord(ch) for ch in username)
    usage = [
        32 + (seed % 14), 28 + (seed % 12), 36 + (seed % 15),
        41 + (seed % 13), 46 + (seed % 16), 52 + (seed % 14),
    ]
    bill = 40 + (seed % 25) + usage[5] * 0.9
    return {
        "meterId": f"LG-{(1000 + (seed % 9000)):04d}",
        "location": f"{METER_LOCATIONS[seed % len(METER_LOCATIONS)]} - Grid Node",
        "status": "Online",
        "usage": usage,
        "billing": f"{bill:.2f}",
        "tariff": "TOU - Peak Saver",
        "voltage": f"{218 + (seed % 12)}V",
    }


init_db()


@app.get("/api/config")
def get_config():
    return {"roles": ROLE_LABELS, "regions": list(REGIONS)}


@app.get("/api/me")
def get_me(request: Request):
    return {"authenticated": True, "user": current_user(request)}


@app.post("/api/login")
def login(payload: CredentialsPayload, response: Response):
    user_row = get_user_by_username(payload.username)
    if not user_row or not bcrypt.checkpw(
        payload.password.encode(), user_row["password"].encode()
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    token = secrets.token_urlsafe(32)
    session_store[token] = user_row["id"]
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    )
    return {"success": True, "user": public_user(user_row)}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        session_store.pop(token, None)
    response.delete_cookie(SESSION_COOKIE)
    return {"success": True}


@app.post("/api/password/change")
def change_password(payload: PasswordPayload, request: Request):
    user = current_user(request)
    with db_connection() as conn:
        row = conn.execute("SELECT password FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not row or not bcrypt.checkpw(payload.oldPassword.encode(), row["password"].encode()):
            raise HTTPException(status_code=401, detail="Current password is incorrect.")
        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hash_password(payload.newPassword), user["id"]),
        )
    return {"success": True}


@app.get("/api/me/profile")
def my_profile(request: Request):
    user = require_role(request, "utilities")
    return {**user, "profile": get_meter_profile(user["username"])}


@app.get("/api/sales/region")
def sales_region_data(request: Request):
    user = require_role(request, "sales_person")
    if user["region"] not in REGIONS:
        raise HTTPException(status_code=403, detail="No valid sales region is assigned.")
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, customer_name AS customerName, region,
                   utility_type AS utilityType, usage_mwh AS usageMwh,
                   revenue, status
            FROM customer_data WHERE region = ? ORDER BY customer_name
            """,
            (user["region"],),
        ).fetchall()
    return {"region": user["region"], "records": [dict(row) for row in rows]}


@app.get("/api/analytics")
def analytics(request: Request):
    require_role(request, "business_analyst")
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT region, COUNT(*) AS accounts, SUM(usage_mwh) AS usageMwh,
                   SUM(revenue) AS revenue,
                   SUM(CASE WHEN status = 'Active' THEN 1 ELSE 0 END) AS activeAccounts
            FROM customer_data GROUP BY region ORDER BY region
            """
        ).fetchall()
    summaries = [dict(row) for row in rows]
    return {
        "regions": summaries,
        "totals": {
            "accounts": sum(row["accounts"] for row in summaries),
            "usageMwh": sum(row["usageMwh"] for row in summaries),
            "revenue": sum(row["revenue"] for row in summaries),
        },
        "privacyNote": "Aggregate regional metrics only; customer-level records are excluded.",
    }


@app.get("/api/admin/users")
def admin_users(request: Request):
    user = require_role(request, "admin")
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, username, role, region FROM users
            WHERE id != ? AND role != 'admin'
            ORDER BY role, username COLLATE NOCASE
            """,
            (user["id"],),
        ).fetchall()
    return [public_user(row) for row in rows]


@app.post("/api/admin/users")
def admin_create_user(payload: AccountCreatePayload, request: Request):
    require_role(request, "admin")
    if payload.role == "admin":
        raise HTTPException(status_code=422, detail="Use the dedicated admin account flow for administrators.")
    return {"success": True, "user": create_user(payload.username, payload.password, payload.role, payload.region)}


@app.put("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, payload: AccountUpdatePayload, request: Request):
    require_role(request, "admin")
    if payload.role == "admin":
        raise HTTPException(status_code=422, detail="Managed accounts cannot be promoted to administrator here.")
    username = clean_username(payload.username)
    region = normalize_region(payload.role, payload.region)
    with db_connection() as conn:
        target = conn.execute(
            "SELECT id, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not target or target["role"] == "admin":
            raise HTTPException(status_code=404, detail="Managed account not found.")
        duplicate = conn.execute(
            "SELECT 1 FROM users WHERE username = ? COLLATE NOCASE AND id != ?",
            (username, user_id),
        ).fetchone()
        if duplicate:
            raise HTTPException(status_code=409, detail="That username is already taken.")
        if payload.password:
            conn.execute(
                "UPDATE users SET username = ?, password = ?, role = ?, region = ? WHERE id = ?",
                (username, hash_password(payload.password), payload.role, region, user_id),
            )
        else:
            conn.execute(
                "UPDATE users SET username = ?, role = ?, region = ? WHERE id = ?",
                (username, payload.role, region, user_id),
            )
        row = conn.execute(
            "SELECT id, username, role, region FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    get_meter_profile.cache_clear()
    return {"success": True, "user": public_user(row)}


@app.delete("/api/admin/users/{user_id}")
def admin_delete_user(user_id: int, payload: DeleteAccountPayload, request: Request):
    require_role(request, "admin")
    if payload.confirmation != "delete":
        raise HTTPException(status_code=422, detail='Type "delete" to confirm account deletion.')
    with db_connection() as conn:
        target = conn.execute(
            "SELECT id, username, role FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not target or target["role"] == "admin":
            raise HTTPException(status_code=404, detail="Managed account not found.")
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    # Immediately sign the deleted account out on every active browser session.
    for token, session_user_id in list(session_store.items()):
        if session_user_id == user_id:
            session_store.pop(token, None)
    get_meter_profile.cache_clear()
    return {"success": True, "deletedUser": target["username"]}


# Backward-compatible admin creation endpoint retained for the original UI/API.
@app.post("/api/admin/add")
def add_admin(payload: CredentialsPayload, request: Request):
    require_role(request, "admin")
    if len(payload.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters.")
    return {"success": True, "user": create_user(payload.username, payload.password, "admin")}


@app.get("/api/users/search")
def search_users(q: str, request: Request):
    user = require_role(request, "admin")
    if not q.strip():
        return []
    with db_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, username, role, region FROM users
            WHERE id != ? AND username LIKE ? COLLATE NOCASE
            ORDER BY username COLLATE NOCASE LIMIT 10
            """,
            (user["id"], f"{q.strip()}%"),
        ).fetchall()
    return [public_user(row) for row in rows]


@app.get("/api/users/detail")
def user_detail(username: str, request: Request):
    require_role(request, "admin")
    row = get_user_by_username(username)
    if not row:
        raise HTTPException(status_code=404, detail="User not found.")
    data = public_user(row)
    if row["role"] == "utilities":
        data["profile"] = get_meter_profile(row["username"])
    return data
