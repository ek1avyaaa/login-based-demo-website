import asyncio
from dataclasses import dataclass
import os
import time
from urllib.parse import quote

import httpx

from oidc import (
    KEYCLOAK_CLIENT_ID,
    KEYCLOAK_CLIENT_SECRET,
    KEYCLOAK_ISSUER,
    KEYCLOAK_REALM,
    KEYCLOAK_SERVER,
)


MANAGEMENT_CLIENT_ID = os.getenv("KEYCLOAK_MANAGEMENT_CLIENT_ID", "").strip()
MANAGEMENT_CLIENT_SECRET = os.getenv("KEYCLOAK_MANAGEMENT_CLIENT_SECRET", "").strip()
PORTAL_ACCESS_ROLE = os.getenv("KEYCLOAK_ACCESS_ROLE", "portal_access").strip()

_token: str | None = None
_token_expires_at = 0.0
_token_lock = asyncio.Lock()
_client_context: tuple[str, dict] | None = None
_client_context_lock = asyncio.Lock()


class KeycloakProvisioningError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProvisioningResult:
    user_id: str
    user_created: bool
    access_granted: bool
    email: str | None = None
    first_name: str = ""
    last_name: str = ""
    email_verified: bool = False
    profile_updated: bool = False


@dataclass(frozen=True)
class RevocationResult:
    user_id: str | None
    access_revoked: bool


def is_keycloak_management_configured():
    return all(
        (
            KEYCLOAK_SERVER,
            KEYCLOAK_REALM,
            KEYCLOAK_CLIENT_ID,
            KEYCLOAK_CLIENT_SECRET,
            MANAGEMENT_CLIENT_ID,
            MANAGEMENT_CLIENT_SECRET,
            PORTAL_ACCESS_ROLE,
        )
    )


def _require_configuration():
    if not is_keycloak_management_configured():
        raise KeycloakProvisioningError(
            "Keycloak user management is not configured. Set the "
            "KEYCLOAK_MANAGEMENT_CLIENT_* backend variables."
        )


async def _service_token(force_refresh: bool = False):
    global _token, _token_expires_at
    _require_configuration()
    async with _token_lock:
        now = time.monotonic()
        if not force_refresh and _token and now < _token_expires_at:
            return _token

        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.post(
                    f"{KEYCLOAK_ISSUER}/protocol/openid-connect/token",
                    data={"grant_type": "client_credentials"},
                    auth=(MANAGEMENT_CLIENT_ID, MANAGEMENT_CLIENT_SECRET),
                )
        except httpx.HTTPError as error:
            raise KeycloakProvisioningError(
                "Keycloak user management is currently unavailable."
            ) from error

        if response.status_code != 200:
            raise KeycloakProvisioningError(
                "Keycloak rejected the management service account. Enable Service "
                "Accounts and assign its required realm-management permissions."
            )

        payload = response.json()
        _token = payload.get("access_token")
        if not _token:
            raise KeycloakProvisioningError(
                "Keycloak did not return a management access token."
            )
        _token_expires_at = now + max(5, int(payload.get("expires_in", 60)) - 15)
        return _token


async def _admin_request(method: str, path: str, **kwargs):
    global _token, _token_expires_at
    token = await _service_token()
    url = f"{KEYCLOAK_SERVER}/admin/realms/{quote(KEYCLOAK_REALM, safe='')}/{path}"

    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.request(
                    method,
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    **kwargs,
                )
        except httpx.HTTPError as error:
            raise KeycloakProvisioningError(
                "Keycloak user management is currently unavailable."
            ) from error

        if response.status_code != 401 or attempt == 1:
            return response
        _token = None
        _token_expires_at = 0
        token = await _service_token(force_refresh=True)

    return response


def _permission_error(response: httpx.Response):
    if response.status_code in (401, 403):
        return KeycloakProvisioningError(
            "The Keycloak management service account is not authorized. Assign "
            "realm-management manage-users and view-clients roles."
        )
    return KeycloakProvisioningError(
        f"Keycloak user management failed with HTTP {response.status_code}."
    )


async def _portal_client_context():
    global _client_context
    if _client_context:
        return _client_context

    async with _client_context_lock:
        if _client_context:
            return _client_context
        response = await _admin_request(
            "GET", "clients", params={"clientId": KEYCLOAK_CLIENT_ID}
        )
        if response.status_code != 200:
            raise _permission_error(response)
        clients = [
            item for item in response.json() if item.get("clientId") == KEYCLOAK_CLIENT_ID
        ]
        if len(clients) != 1:
            raise KeycloakProvisioningError(
                f"Keycloak client {KEYCLOAK_CLIENT_ID!r} was not found uniquely."
            )
        client_uuid = clients[0]["id"]

        response = await _admin_request(
            "GET",
            f"clients/{quote(client_uuid, safe='')}/roles/"
            f"{quote(PORTAL_ACCESS_ROLE, safe='')}",
        )
        if response.status_code == 404:
            raise KeycloakProvisioningError(
                f"Create the client role {PORTAL_ACCESS_ROLE!r} on Keycloak client "
                f"{KEYCLOAK_CLIENT_ID!r}."
            )
        if response.status_code != 200:
            raise _permission_error(response)
        _client_context = (client_uuid, response.json())
        return _client_context


async def _find_user(username: str):
    response = await _admin_request(
        "GET",
        "users",
        params={"username": username, "exact": "true", "max": 2},
    )
    if response.status_code != 200:
        raise _permission_error(response)
    matches = [
        item
        for item in response.json()
        if (item.get("username") or "").casefold() == username.casefold()
    ]
    if len(matches) > 1:
        raise KeycloakProvisioningError(
            "Keycloak returned multiple users for the same exact username."
        )
    return matches[0] if matches else None


async def _get_user(user_id: str):
    response = await _admin_request("GET", f"users/{quote(user_id, safe='')}")
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise _permission_error(response)
    return response.json()


def _provisioning_result(
    user: dict,
    user_created: bool,
    access_granted: bool,
    profile_updated: bool = False,
):
    return ProvisioningResult(
        user_id=user["id"],
        user_created=user_created,
        access_granted=access_granted,
        email=user.get("email"),
        first_name=user.get("firstName") or "",
        last_name=user.get("lastName") or "",
        email_verified=bool(user.get("emailVerified", False)),
        profile_updated=profile_updated,
    )


async def _create_user(
    username: str,
    password: str,
    email: str | None,
    first_name: str,
    last_name: str,
    email_verified: bool,
):
    representation = {
        "username": username,
        "enabled": True,
        "credentials": [
            {"type": "password", "value": password, "temporary": True}
        ],
    }
    if email:
        representation.update(
            {
                "email": email,
                "emailVerified": email_verified,
            }
        )
    if first_name:
        representation["firstName"] = first_name
    if last_name:
        representation["lastName"] = last_name

    response = await _admin_request(
        "POST",
        "users",
        json=representation,
    )
    if response.status_code == 409:
        user = await _find_user(username)
        if user:
            return user, False
        raise KeycloakProvisioningError(
            "Keycloak rejected the new identity because its username or email "
            "already belongs to another Keycloak user."
        )
    if response.status_code != 201:
        raise _permission_error(response)

    location = response.headers.get("Location", "")
    user_id = location.rstrip("/").rsplit("/", 1)[-1]
    user = await _get_user(user_id) if user_id else None
    if not user:
        user = await _find_user(username)
    if not user:
        raise KeycloakProvisioningError(
            "Keycloak created the user but did not return its identifier."
        )
    return user, True


async def _fill_missing_user_profile(
    user: dict,
    email: str,
    first_name: str,
    last_name: str,
    email_verified: bool,
):
    """Fill missing identity data while preserving every existing profile value."""
    authoritative = await _get_user(user["id"]) or user
    representation = dict(authoritative)
    representation.pop("access", None)
    updated_fields = []

    existing_email = (representation.get("email") or "").strip()
    if not existing_email:
        representation["email"] = email
        existing_email = email
        updated_fields.append("email")
    if not (representation.get("firstName") or "").strip():
        representation["firstName"] = first_name
        updated_fields.append("firstName")
    if not (representation.get("lastName") or "").strip():
        representation["lastName"] = last_name
        updated_fields.append("lastName")

    # Verify only the supplied address. Never use this form to verify a different
    # email that was already owned by the shared Keycloak identity.
    if (
        email_verified
        and not bool(representation.get("emailVerified", False))
        and existing_email.casefold() == email.casefold()
    ):
        representation["emailVerified"] = True
        updated_fields.append("emailVerified")

    if not updated_fields:
        return authoritative, False

    response = await _admin_request(
        "PUT",
        f"users/{quote(user['id'], safe='')}",
        json=representation,
    )
    if response.status_code == 409:
        raise KeycloakProvisioningError(
            "Keycloak could not add the missing profile details because the email "
            "address is already assigned to another identity."
        )
    if response.status_code != 204:
        raise _permission_error(response)

    updated = await _get_user(user["id"])
    if not updated:
        raise KeycloakProvisioningError(
            "The Keycloak identity disappeared while its missing profile details "
            "were being added."
        )
    return updated, True


async def _mapped_roles(user_id: str, client_uuid: str):
    response = await _admin_request(
        "GET",
        f"users/{quote(user_id, safe='')}/role-mappings/clients/"
        f"{quote(client_uuid, safe='')}",
    )
    if response.status_code == 404:
        return []
    if response.status_code != 200:
        raise _permission_error(response)
    return response.json()


async def grant_portal_access_by_id(user_id: str):
    client_uuid, access_role = await _portal_client_context()
    roles = await _mapped_roles(user_id, client_uuid)
    if any(role.get("id") == access_role.get("id") for role in roles):
        return False
    response = await _admin_request(
        "POST",
        f"users/{quote(user_id, safe='')}/role-mappings/clients/"
        f"{quote(client_uuid, safe='')}",
        json=[access_role],
    )
    if response.status_code != 204:
        raise _permission_error(response)
    return True


async def ensure_portal_user(
    username: str,
    password: str,
    email: str,
    first_name: str,
    last_name: str,
    email_verified: bool = False,
):
    _require_configuration()
    user = await _find_user(username)
    user_created = False
    if not user:
        user, user_created = await _create_user(
            username,
            password,
            email,
            first_name,
            last_name,
            email_verified,
        )
    if not user.get("enabled", False):
        raise KeycloakProvisioningError(
            "The matching Keycloak identity is disabled. A Keycloak administrator "
            "must enable the shared identity before portal access can be granted."
        )
    profile_updated = False
    if not user_created:
        user, profile_updated = await _fill_missing_user_profile(
            user,
            email,
            first_name,
            last_name,
            email_verified,
        )
    access_granted = await grant_portal_access_by_id(user["id"])
    return _provisioning_result(
        user, user_created, access_granted, profile_updated
    )


async def grant_existing_portal_access(
    username: str, user_id: str | None = None
):
    """Grant access only when an existing Keycloak identity can be resolved."""
    _require_configuration()
    user = await _get_user(user_id) if user_id else await _find_user(username)
    if not user or not user.get("enabled", False):
        return None
    access_granted = await grant_portal_access_by_id(user["id"])
    return _provisioning_result(user, False, access_granted)


async def user_has_portal_access(user_id: str):
    _require_configuration()
    if not await _get_user(user_id):
        return False
    client_uuid, access_role = await _portal_client_context()
    roles = await _mapped_roles(user_id, client_uuid)
    return any(role.get("id") == access_role.get("id") for role in roles)


async def revoke_portal_access(username: str, user_id: str | None = None):
    _require_configuration()
    user = await _get_user(user_id) if user_id else None
    if not user:
        user = await _find_user(username)
    if not user:
        return RevocationResult(None, False)

    client_uuid, access_role = await _portal_client_context()
    roles = await _mapped_roles(user["id"], client_uuid)
    if not any(role.get("id") == access_role.get("id") for role in roles):
        return RevocationResult(user["id"], False)

    response = await _admin_request(
        "DELETE",
        f"users/{quote(user['id'], safe='')}/role-mappings/clients/"
        f"{quote(client_uuid, safe='')}",
        json=[access_role],
    )
    if response.status_code != 204:
        raise _permission_error(response)
    return RevocationResult(user["id"], True)
