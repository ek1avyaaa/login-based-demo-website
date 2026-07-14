#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_PYTHON="$BACKEND_DIR/.venv/bin/python"

if [[ ! -x "$BACKEND_PYTHON" ]]; then
    echo "Backend environment not found at backend/.venv."
    echo "Create it with: python3 -m venv backend/.venv"
    exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
    echo "npm is required but was not found in PATH."
    exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "Frontend dependencies are not installed."
    echo "Install them with: cd frontend && npm install"
    exit 1
fi

if ! "$BACKEND_PYTHON" -c "import uvicorn" >/dev/null 2>&1; then
    echo "uvicorn is not installed in backend/.venv."
    echo "Install the backend dependencies, then run this script again."
    exit 1
fi

pids=()

cleanup() {
    trap - EXIT INT TERM
    for pid in "${pids[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null || true
    done
}

trap cleanup EXIT INT TERM

echo "Starting backend at http://127.0.0.1:8000"
(
    cd "$BACKEND_DIR"
    exec "$BACKEND_PYTHON" -m uvicorn main:app --reload
) &
pids+=("$!")

echo "Starting frontend at http://localhost:5173"
(
    cd "$FRONTEND_DIR"
    exec npm run dev
) &
pids+=("$!")

echo "Press Ctrl+C to stop both servers."

status=0
wait -n "${pids[@]}" || status=$?
exit "$status"
