# Secure Access Portal

React and FastAPI role-based authentication dashboard with server-enforced data
access, regional sales workspaces, aggregate business analytics, utilities meter
profiles, and administrator credential management.

## Roles and access

- **Administrator**: creates and manages this portal's non-admin accounts,
  local passwords, roles, and sales-region assignments. Creation reuses or
  creates a Keycloak identity and grants this portal's client role. Deletion
  revokes only that client role after the administrator types `delete`; the
  shared Keycloak identity is preserved.
- **Utilities**: sees only their own meter and billing profile. Utilities
  accounts can only be created by an administrator (the former `user` role is
  migrated automatically).
- **Sales Person**: sees customer records only for their assigned region. The
  initial regions are Texas, Noida, Alpharetta, and Germany.
- **Business Analyst**: sees aggregate totals by region without customer-level
  sales records or user credentials.

Role and region restrictions are checked by the FastAPI endpoints. The React
pages are role-specific, but hiding UI is not relied upon for authorization.
There is no public registration endpoint; all new accounts are created from the
administrator dashboard.

## Demo accounts

On first startup the app creates these accounts if their usernames do not
already exist:

| Role | Username | Password | Region |
| --- | --- | --- | --- |
| Administrator | `admin` | `change-me` | All account management |
| Utilities | `utilities_demo` | `utilities-demo` | Personal account only |
| Business Analyst | `business_analyst` | `analyst-demo` | Aggregates only |
| Sales Person | `sales_texas` | `sales-demo` | Texas |
| Sales Person | `sales_noida` | `sales-demo` | Noida |
| Sales Person | `sales_alpharetta` | `sales-demo` | Alpharetta |
| Sales Person | `sales_germany` | `sales-demo` | Germany |

Change demo passwords before using the portal beyond local demonstration.

## Keycloak SSO

The login page includes a **Continue with SSO** button backed by the FastAPI
authorization-code flow. Copy `backend/.env.example` to `backend/.env`, fill in
the Keycloak server, realm, client ID, client secret, redirect URI, and a long
random OIDC session secret, then restart the app.

Configure these URLs on the Keycloak client for local development:

- Valid redirect URI: `http://localhost:8000/api/auth/sso/callback`
- Valid post-logout redirect URI: `http://localhost:5173/`
- Web origin: `http://localhost:5173`

On the first SSO login, the Keycloak `preferred_username` must match an account
created in the portal by an administrator. The portal then binds that account to
Keycloak's immutable issuer and subject identifiers; later username changes do
not change the linked identity. The local portal account remains the source of
the user's role and sales region. Client secrets belong only in `backend/.env`
and must never be placed in a frontend `VITE_*` variable.

### Client-specific user lifecycle

Keycloak is the global identity store, while this portal owns its local role and
region. The portal uses a Keycloak client role named `portal_access` by default:

- Adding an existing Keycloak username preserves its global password, existing
  profile values, and other client access. Missing email/name values are filled
  from the registration form, the matching email can optionally be verified,
  and `fastapi-app:portal_access` is granted without changing other clients.
- Adding a new username creates a Keycloak identity with the supplied temporary
  password, email, first name, last name, and email-verification selection;
  grants only this portal's access role; and creates the local role.
- Deleting a portal account revokes only `fastapi-app:portal_access`. It never
  deletes the Keycloak user or changes roles belonging to another website.
- Local role, region, username, and password edits do not modify the shared
  Keycloak identity or its password.

Create a dedicated confidential Keycloak client named `portal-user-manager`:

1. Enable **Client authentication** and **Service account roles**. Disable
   browser flows because this client is only for backend administration.
2. On client `fastapi-app`, create the client role `portal_access`.
3. On `portal-user-manager` -> **Service account roles**, assign
   `realm-management:manage-users` and `realm-management:view-clients`.
4. Copy its client secret into `KEYCLOAK_MANAGEMENT_CLIENT_SECRET` in
   `backend/.env`, then restart the portal.
5. Sign in as the portal administrator and select **Sync Keycloak access** once
   to migrate all matching existing accounts, including the portal administrator.
   Missing identities and stale bindings are reported and never silently changed.

Use Keycloak fine-grained admin permissions in production when the management
service account must be restricted beyond the built-in roles.

Portal sessions are stored server-side, expire after eight hours, and are
revoked when an administrator resets a password or deletes an account. The
`OIDC_SESSION_SECRET` encrypts stored Keycloak logout tokens and must be at least
32 characters.

For SSO accounts, **Log Out** ends only the portal session and preserves the
Keycloak session, allowing a subsequent SSO login without entering credentials
again. **Log Out of Keycloak** performs a full identity-provider logout and
requires credentials on the next SSO login.

### Local Keycloak

The default local configuration expects Keycloak at `127.0.0.1:8080`. Start
Keycloak with the matching published issuer URL:

```bat
bin\kc.bat start-dev --hostname=http://127.0.0.1:8080
```

When the portal runs inside WSL but Keycloak runs on Windows, first verify that
WSL loopback forwarding is available with `curl http://127.0.0.1:8080`. If it is
not reachable, Keycloak must instead listen on a Windows interface accessible
from WSL. This is a local-development setup; use HTTPS and an appropriate
public hostname outside development.

## Run locally

### First-time setup

From the project root:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
npm install --prefix frontend
```

### Start the website

Start the backend and frontend together:

```bash
./dev.sh
```

Open [http://localhost:5173](http://localhost:5173) in your browser. Press
`Ctrl+C` in the terminal to stop both servers.

The launcher uses `backend/.venv` and `frontend/node_modules`. If either is
missing, it prints the setup command you need.

The local SQLite database is created automatically at `backend/users.db`. On
startup, existing `user` accounts are migrated to `utilities`, and the sales
region and Keycloak profile columns and sample regional data are added safely.

For a fresh database, the demo administrator login is `admin` / `change-me`.
Override both values when starting the app if needed:

```bash
ADMIN_USERNAME=my-admin ADMIN_PASSWORD=my-password ./dev.sh
```
