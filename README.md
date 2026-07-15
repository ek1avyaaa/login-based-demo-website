# Secure Access Portal

React and FastAPI role-based authentication dashboard with administrator user
search, account promotion, password management, and generated energy-meter
profiles.

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

The local SQLite database is created automatically at `backend/users.db`. It is
ignored by Git so local account data is never committed.

For a fresh database, the demo administrator login is `admin` / `change-me`.
Override both values when starting the app if needed:

```bash
ADMIN_USERNAME=my-admin ADMIN_PASSWORD=my-password ./dev.sh
```
