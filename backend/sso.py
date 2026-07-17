import os
from urllib.parse import urlencode

from authlib.common.errors import AuthlibBaseError
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
import httpx

from keycloak_admin import (
    KeycloakProvisioningError,
    is_keycloak_management_configured,
    user_has_portal_access,
)
from oidc import get_keycloak_client, get_keycloak_issuer
from session import clear_session, create_session, discard_session, get_session


FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")


def frontend_redirect(**parameters):
    url = f"{FRONTEND_URL}/"
    if parameters:
        url = f"{url}?{urlencode(parameters)}"
    return url


def build_sso_router(resolve_oidc_user):
    router = APIRouter(prefix="/api/auth/sso", tags=["SSO"])

    @router.get("/login")
    async def sso_login(request: Request):
        try:
            keycloak = get_keycloak_client()
        except RuntimeError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
            ) from error

        # In the proxied local flow, use the same browser hostname as FRONTEND_URL
        # so the OAuth state and portal session cookies remain available.
        redirect_uri = os.getenv("OIDC_REDIRECT_URI") or str(
            request.url_for("sso_callback")
        )
        try:
            return await keycloak.authorize_redirect(request, redirect_uri)
        except (AuthlibBaseError, httpx.HTTPError) as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Keycloak is configured but currently unavailable.",
            ) from error

    @router.get("/callback", name="sso_callback")
    async def sso_callback(request: Request):
        try:
            keycloak = get_keycloak_client()
            token = await keycloak.authorize_access_token(request)
            claims = token.get("userinfo")
            if not claims:
                claims = await keycloak.userinfo(token=token)
        except (AuthlibBaseError, httpx.HTTPError, RuntimeError):
            return RedirectResponse(frontend_redirect(sso_error="Keycloak login failed."))

        username = (claims.get("preferred_username") or "").strip()
        subject = (claims.get("sub") or "").strip()
        configured_issuer = get_keycloak_issuer().rstrip("/")
        claimed_issuer = (claims.get("iss") or configured_issuer).strip().rstrip("/")
        if not username or not subject:
            return RedirectResponse(
                frontend_redirect(sso_error="Keycloak did not return a complete identity.")
            )
        if claimed_issuer != configured_issuer:
            return RedirectResponse(
                frontend_redirect(sso_error="Keycloak returned an unexpected issuer.")
            )

        if is_keycloak_management_configured():
            try:
                has_access = await user_has_portal_access(subject)
            except KeycloakProvisioningError:
                return RedirectResponse(
                    frontend_redirect(
                        sso_error="Portal access could not be verified with Keycloak."
                    )
                )
            if not has_access:
                return RedirectResponse(
                    frontend_redirect(
                        sso_error="Your Keycloak account is not assigned to this portal."
                    )
                )

        try:
            account = resolve_oidc_user(configured_issuer, subject, username)
        except HTTPException as error:
            return RedirectResponse(frontend_redirect(sso_error=str(error.detail)))
        if not account:
            return RedirectResponse(
                frontend_redirect(
                    sso_error=(
                        "Your SSO identity is valid but no portal account is assigned. "
                        "Ask an administrator to create the matching username."
                    )
                )
            )

        response = RedirectResponse(frontend_redirect(sso="success"))
        discard_session(request)
        create_session(
            response,
            account["id"],
            auth_type="oidc",
            id_token=token.get("id_token"),
        )
        request.session.clear()
        return response

    @router.get("/logout")
    async def sso_logout(request: Request):
        portal_session = get_session(request)
        target = frontend_redirect(sso="logged_out")

        if portal_session and portal_session.id_token:
            try:
                keycloak = get_keycloak_client()
                metadata = await keycloak.load_server_metadata()
                logout_endpoint = metadata.get("end_session_endpoint")
                if logout_endpoint:
                    target = f"{logout_endpoint}?{urlencode({
                        'id_token_hint': portal_session.id_token,
                        'post_logout_redirect_uri': FRONTEND_URL + '/',
                    })}"
            except (AuthlibBaseError, httpx.HTTPError, RuntimeError):
                pass

        response = RedirectResponse(target)
        clear_session(request, response)
        request.session.clear()
        return response

    return router
