import os
from pathlib import Path

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent / ".env")

KEYCLOAK_SERVER = os.getenv("KEYCLOAK_SERVER", "").rstrip("/")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "").strip()
KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "").strip()
KEYCLOAK_CLIENT_SECRET = os.getenv("KEYCLOAK_CLIENT_SECRET", "").strip()
KEYCLOAK_ISSUER = (
    f"{KEYCLOAK_SERVER}/realms/{KEYCLOAK_REALM}"
    if KEYCLOAK_SERVER and KEYCLOAK_REALM
    else ""
)


def is_oidc_configured():
    return all(
        (KEYCLOAK_SERVER, KEYCLOAK_REALM, KEYCLOAK_CLIENT_ID, KEYCLOAK_CLIENT_SECRET)
    )


oauth = OAuth()
if is_oidc_configured():
    oauth.register(
        name="keycloak",
        client_id=KEYCLOAK_CLIENT_ID,
        client_secret=KEYCLOAK_CLIENT_SECRET,
        server_metadata_url=f"{KEYCLOAK_ISSUER}/.well-known/openid-configuration",
        client_kwargs={"scope": "openid profile email"},
    )


def get_keycloak_client():
    if not is_oidc_configured():
        raise RuntimeError(
            "Keycloak SSO is not configured. Set the KEYCLOAK_* backend variables."
        )
    return oauth.keycloak


def get_keycloak_issuer():
    if not is_oidc_configured():
        raise RuntimeError(
            "Keycloak SSO is not configured. Set the KEYCLOAK_* backend variables."
        )
    return KEYCLOAK_ISSUER
