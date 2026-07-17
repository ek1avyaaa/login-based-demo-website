from contextlib import contextmanager
from functools import lru_cache
import os
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Literal
import bcrypt
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from keycloak_admin import (
    KeycloakProvisioningError,
    ensure_portal_user,
    grant_existing_portal_access,
    grant_portal_access_by_id,
    is_keycloak_management_configured,
    revoke_portal_access,
)
from oidc import get_keycloak_issuer, is_oidc_configured
from session import (
    clear_session,
    configure_session_store,
    create_session,
    discard_session,
    get_session,
    invalidate_user_sessions,
)


DB_PATH = Path(os.getenv("PORTAL_DB_PATH", Path(__file__).resolve().parent / "users.db"))
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me")
OIDC_SESSION_SECRET = os.getenv("OIDC_SESSION_SECRET", "")
if is_oidc_configured() and len(OIDC_SESSION_SECRET) < 32:
    raise RuntimeError(
        "OIDC_SESSION_SECRET must contain at least 32 characters when SSO is enabled."
    )
# Local-only development without SSO still receives a strong, process-scoped key.
SESSION_SECRET = OIDC_SESSION_SECRET or secrets.token_urlsafe(32)

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
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="oidc_state",
    max_age=10 * 60,
    same_site="lax",
    https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)


class CredentialsPayload(BaseModel):
    username: str = Field(max_length=60)
    password: str = Field(max_length=72)


class PasswordPayload(BaseModel):
    oldPassword: str
    newPassword: str = Field(min_length=8, max_length=72)


class AccountCreatePayload(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    password: str = Field(min_length=8, max_length=72)
    email: str = Field(min_length=3, max_length=254)
    firstName: str = Field(min_length=1, max_length=80)
    lastName: str = Field(min_length=1, max_length=80)
    emailVerified: bool = False
    role: Role
    region: str | None = None


class AccountUpdatePayload(BaseModel):
    username: str = Field(min_length=3, max_length=60)
    password: str | None = Field(default=None, min_length=8, max_length=72)
    role: Role
    region: str | None = None


class DeleteAccountPayload(BaseModel):
    confirmation: str


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
    encoded = password.encode()
    if len(encoded) > 72:
        raise HTTPException(
            status_code=422, detail="Password must be no more than 72 UTF-8 bytes."
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode()


def verify_password(password: str, password_hash: str):
    encoded = password.encode()
    if len(encoded) > 72:
        return False
    return bcrypt.checkpw(encoded, password_hash.encode())


def public_user(row):
    data = {
        "id": row["id"],
        "username": row["username"],
        "role": row["role"],
        "roleLabel": ROLE_LABELS.get(row["role"], row["role"]),
        "region": row["region"],
    }
    if "email" in row.keys():
        data.update(
            {
                "email": row["email"] or "",
                "firstName": row["first_name"] or "",
                "lastName": row["last_name"] or "",
                "emailVerified": bool(row["email_verified"]),
            }
        )
    if "oidc_subject" in row.keys():
        data["ssoLinked"] = bool(row["oidc_subject"] and row["oidc_issuer"])
    return data


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


def clean_email(email: str):
    value = email.strip()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return value


def clean_name(value: str, label: str):
    cleaned = " ".join(value.split())
    if not cleaned or any(ord(character) < 32 for character in cleaned):
        raise HTTPException(status_code=422, detail=f"Enter a valid {label}.")
    return cleaned


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
        if "oidc_subject" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN oidc_subject TEXT")
        if "oidc_issuer" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN oidc_issuer TEXT")
        if "email" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "first_name" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN first_name TEXT")
        if "last_name" not in columns:
            conn.execute("ALTER TABLE users ADD COLUMN last_name TEXT")
        if "email_verified" not in columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 0"
            )

        # Migrate the former user role without invalidating existing accounts.
        conn.execute("UPDATE users SET role = 'utilities' WHERE role = 'user'")
        conn.execute("DROP INDEX IF EXISTS idx_users_username_nocase")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username_nocase "
            "ON users (username COLLATE NOCASE)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_oidc_identity "
            "ON users (oidc_issuer, oidc_subject) "
            "WHERE oidc_issuer IS NOT NULL AND oidc_subject IS NOT NULL"
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


def resolve_oidc_user(issuer: str, subject: str, username: str):
    """Resolve and permanently bind a trusted OIDC identity to a portal account."""
    issuer = issuer.strip().rstrip("/")
    subject = subject.strip()
    username = username.strip()
    if not issuer or not subject or not username:
        raise HTTPException(status_code=403, detail="Keycloak identity is incomplete.")

    with db_connection() as conn:
        row = conn.execute(
            "SELECT id, username, password, role, region, oidc_issuer, oidc_subject "
            "FROM users WHERE oidc_issuer = ? AND oidc_subject = ?",
            (issuer, subject),
        ).fetchone()
        if row:
            return row

        row = conn.execute(
            "SELECT id, username, password, role, region, oidc_issuer, oidc_subject "
            "FROM users WHERE username = ? COLLATE NOCASE",
            (username,),
        ).fetchone()
        if not row:
            return None
        if row["oidc_subject"] or row["oidc_issuer"]:
            raise HTTPException(
                status_code=403,
                detail="This portal account is linked to a different SSO identity.",
            )

        try:
            cursor = conn.execute(
                "UPDATE users SET oidc_issuer = ?, oidc_subject = ? "
                "WHERE id = ? AND oidc_issuer IS NULL AND oidc_subject IS NULL",
                (issuer, subject, row["id"]),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=403,
                detail="This SSO identity is linked to a different portal account.",
            ) from error

        if cursor.rowcount != 1:
            linked = conn.execute(
                "SELECT oidc_issuer, oidc_subject FROM users WHERE id = ?", (row["id"],)
            ).fetchone()
            if not linked or (linked["oidc_issuer"], linked["oidc_subject"]) != (
                issuer,
                subject,
            ):
                raise HTTPException(
                    status_code=403,
                    detail="This portal account is linked to a different SSO identity.",
                )

        return conn.execute(
            "SELECT id, username, password, role, region, oidc_issuer, oidc_subject "
            "FROM users WHERE id = ?",
            (row["id"],),
        ).fetchone()


def create_user(
    username: str,
    password: str,
    role: str,
    region: str | None = None,
    oidc_issuer: str | None = None,
    oidc_subject: str | None = None,
    email: str | None = None,
    first_name: str = "",
    last_name: str = "",
    email_verified: bool = False,
):
    username = clean_username(username)
    region = normalize_region(role, region)
    try:
        with db_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users "
                "(username, password, role, region, oidc_issuer, oidc_subject, "
                "email, first_name, last_name, email_verified) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    username,
                    hash_password(password),
                    role,
                    region,
                    oidc_issuer,
                    oidc_subject,
                    email,
                    first_name,
                    last_name,
                    int(email_verified),
                ),
            )
            row = conn.execute(
                "SELECT id, username, role, region, oidc_issuer, oidc_subject, "
                "email, first_name, last_name, email_verified "
                "FROM users WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
    except sqlite3.IntegrityError as error:
        raise HTTPException(status_code=409, detail="That username is already taken.") from error
    return public_user(row)


def current_user(request: Request):
    portal_session = get_session(request)
    if not portal_session:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    with db_connection() as conn:
        row = conn.execute(
            "SELECT id, username, role, region FROM users WHERE id = ?",
            (portal_session.user_id,),
        ).fetchone()
    if not row:
        discard_session(request)
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return {**public_user(row), "authType": portal_session.auth_type}


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
configure_session_store(DB_PATH, SESSION_SECRET)


@app.get("/api/config")
def get_config():
    return {
        "roles": ROLE_LABELS,
        "regions": list(REGIONS),
        "sso": {
            "enabled": is_oidc_configured(),
            "loginUrl": "/api/auth/sso/login",
            "userManagementEnabled": is_keycloak_management_configured(),
        },
    }


@app.get("/api/me")
def get_me(request: Request):
    return {"authenticated": True, "user": current_user(request)}


@app.post("/api/login")
def login(payload: CredentialsPayload, request: Request, response: Response):
    user_row = get_user_by_username(payload.username)
    if not user_row or not verify_password(payload.password, user_row["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    discard_session(request)
    create_session(response, user_row["id"], auth_type="local")
    return {
        "success": True,
        "user": {**public_user(user_row), "authType": "local"},
    }


@app.post("/api/logout")
def logout(request: Request, response: Response):
    clear_session(request, response)
    return {"success": True}


@app.post("/api/password/change")
def change_password(payload: PasswordPayload, request: Request, response: Response):
    user = current_user(request)
    if user["authType"] == "oidc":
        raise HTTPException(
            status_code=403,
            detail="Password changes for SSO accounts are managed in Keycloak.",
        )
    with db_connection() as conn:
        row = conn.execute("SELECT password FROM users WHERE id = ?", (user["id"],)).fetchone()
        if not row or not verify_password(payload.oldPassword, row["password"]):
            raise HTTPException(status_code=401, detail="Current password is incorrect.")
        conn.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (hash_password(payload.newPassword), user["id"]),
        )
    invalidate_user_sessions(user["id"])
    create_session(response, user["id"], auth_type="local")
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
            SELECT id, username, role, region, oidc_issuer, oidc_subject,
                   email, first_name, last_name, email_verified FROM users
            WHERE id != ? AND role != 'admin'
            ORDER BY role, username COLLATE NOCASE
            """,
            (user["id"],),
        ).fetchall()
    return [public_user(row) for row in rows]


@app.post("/api/admin/users")
async def admin_create_user(payload: AccountCreatePayload, request: Request):
    require_role(request, "admin")
    if payload.role == "admin":
        raise HTTPException(status_code=422, detail="Use the dedicated admin account flow for administrators.")
    username = clean_username(payload.username)
    email = clean_email(payload.email)
    first_name = clean_name(payload.firstName, "first name")
    last_name = clean_name(payload.lastName, "last name")
    if get_user_by_username(username):
        raise HTTPException(status_code=409, detail="That username is already taken.")

    try:
        provisioning = await ensure_portal_user(
            username,
            payload.password,
            email,
            first_name,
            last_name,
            payload.emailVerified,
        )
    except KeycloakProvisioningError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    try:
        user = create_user(
            username,
            payload.password,
            payload.role,
            payload.region,
            oidc_issuer=get_keycloak_issuer(),
            oidc_subject=provisioning.user_id,
            email=provisioning.email,
            first_name=provisioning.first_name,
            last_name=provisioning.last_name,
            email_verified=provisioning.email_verified,
        )
    except Exception:
        if provisioning.access_granted:
            try:
                await revoke_portal_access(username, provisioning.user_id)
            except KeycloakProvisioningError:
                pass
        raise

    return {
        "success": True,
        "user": user,
        "keycloak": {
            "userCreated": provisioning.user_created,
            "accessGranted": provisioning.access_granted,
            "identityPreserved": True,
            "profilePreserved": not provisioning.user_created,
            "profileUpdated": provisioning.profile_updated,
        },
    }


@app.post("/api/admin/keycloak/reconcile")
async def admin_reconcile_keycloak_access(request: Request):
    require_role(request, "admin")
    with db_connection() as conn:
        rows = conn.execute(
            "SELECT id, username, oidc_issuer, oidc_subject FROM users "
            "ORDER BY username COLLATE NOCASE"
        ).fetchall()

    summary = {
        "matched": 0,
        "accessGranted": 0,
        "alreadyGranted": 0,
        "missingInKeycloak": [],
        "staleBindings": [],
    }
    for row in rows:
        if row["oidc_issuer"] and not row["oidc_subject"]:
            summary["staleBindings"].append(row["username"])
            continue
        try:
            result = await grant_existing_portal_access(
                row["username"], row["oidc_subject"]
            )
        except KeycloakProvisioningError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

        if not result:
            target = (
                summary["staleBindings"]
                if row["oidc_subject"]
                else summary["missingInKeycloak"]
            )
            target.append(row["username"])
            continue

        summary["matched"] += 1
        if result.access_granted:
            summary["accessGranted"] += 1
        else:
            summary["alreadyGranted"] += 1

        with db_connection() as conn:
            conn.execute(
                "UPDATE users SET email = ?, first_name = ?, last_name = ?, "
                "email_verified = ? WHERE id = ?",
                (
                    result.email,
                    result.first_name,
                    result.last_name,
                    int(result.email_verified),
                    row["id"],
                ),
            )
            if not row["oidc_subject"] and not row["oidc_issuer"]:
                conn.execute(
                    "UPDATE users SET oidc_issuer = ?, oidc_subject = ? "
                    "WHERE id = ? AND oidc_issuer IS NULL AND oidc_subject IS NULL",
                    (get_keycloak_issuer(), result.user_id, row["id"]),
                )
            elif row["oidc_subject"] and row["oidc_issuer"] != get_keycloak_issuer():
                conn.execute(
                    "UPDATE users SET oidc_issuer = ? "
                    "WHERE id = ? AND oidc_subject = ?",
                    (get_keycloak_issuer(), row["id"], result.user_id),
                )

    return {"success": True, "summary": summary}


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
            "SELECT id, username, role, region, email, first_name, last_name, "
            "email_verified FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    if payload.password:
        invalidate_user_sessions(user_id)
    get_meter_profile.cache_clear()
    return {"success": True, "user": public_user(row)}


@app.delete("/api/admin/users/{user_id}")
async def admin_delete_user(user_id: int, payload: DeleteAccountPayload, request: Request):
    require_role(request, "admin")
    if payload.confirmation != "delete":
        raise HTTPException(status_code=422, detail='Type "delete" to confirm account deletion.')
    with db_connection() as conn:
        target = conn.execute(
            "SELECT id, username, role, oidc_subject FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not target or target["role"] == "admin":
            raise HTTPException(status_code=404, detail="Managed account not found.")

    try:
        revocation = await revoke_portal_access(
            target["username"], target["oidc_subject"]
        )
    except KeycloakProvisioningError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    try:
        with db_connection() as conn:
            deleted = conn.execute(
                "DELETE FROM users WHERE id = ? AND role != 'admin'", (user_id,)
            )
            if deleted.rowcount != 1:
                raise HTTPException(status_code=409, detail="The account changed; retry deletion.")
    except Exception:
        if revocation.access_revoked and revocation.user_id:
            try:
                await grant_portal_access_by_id(revocation.user_id)
            except KeycloakProvisioningError:
                pass
        raise

    # Immediately sign the deleted account out on every active browser session.
    invalidate_user_sessions(user_id)
    get_meter_profile.cache_clear()
    return {
        "success": True,
        "deletedUser": target["username"],
        "keycloakAccessRevoked": revocation.access_revoked,
        "keycloakIdentityPreserved": True,
    }


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

# Imported after the account/session helpers so the OIDC router can reuse them
# without duplicating the portal's authorization model.
from sso import build_sso_router  # noqa: E402

app.include_router(build_sso_router(resolve_oidc_user))
