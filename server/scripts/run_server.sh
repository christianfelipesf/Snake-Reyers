#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

cd "$PROJECT_DIR"

"$PROJECT_DIR/.venv/bin/python" \
    "$PROJECT_DIR/scripts/clean_start_preflight.py" \
    --apply

export PYTHONPATH="$PROJECT_DIR/src"
export COBRINHA_SERVER_DIR="$PROJECT_DIR"

exec "$PROJECT_DIR/.venv/bin/python" \
    -m uvicorn \
    cobrinha_server.main:app \
    --host "${COBRINHA_SERVER_HOST:-127.0.0.1}" \
    --port "${COBRINHA_SERVER_PORT:-9393}"
