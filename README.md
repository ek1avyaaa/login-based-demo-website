# Secure Access Portal

React and FastAPI role-based authentication dashboard with server-enforced data
access, regional sales workspaces, aggregate business analytics, utilities meter
profiles, and administrator credential management.

## Roles and access

- **Administrator**: creates and manages non-admin accounts, usernames,
  passwords, roles, and sales-region assignments. Administrators can permanently
  delete a managed account after typing `delete` in the confirmation dialog.
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

## Keycloak SSO frontend option

The login page includes a **Continue with SSO** button. Copy
`frontend/.env.example` to `frontend/.env` and set `VITE_KEYCLOAK_LOGIN_URL` to
your Keycloak authorization URL or your application's SSO-start endpoint. The
button only provides the frontend redirect; token exchange, callback handling,
role mapping, and backend session creation must be connected as part of your
Keycloak configuration.

## Run locally

### First-time setup

From the project root:

```bash
sudo apt install python3.14-venv
python3 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
sudo apt install npm
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
region column and sample regional data are added safely.

For a fresh database, the demo administrator login is `admin` / `change-me`.
Override both values when starting the app if needed:

```bash
ADMIN_USERNAME=my-admin ADMIN_PASSWORD=my-password ./dev.sh
```
