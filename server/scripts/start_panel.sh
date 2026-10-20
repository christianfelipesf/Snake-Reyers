#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

HOST="${COBRINHA_SERVER_HOST:-127.0.0.1}"
PORT="${COBRINHA_SERVER_PORT:-9393}"
PANEL_URL="http://${HOST}:${PORT}/"

cd "$PROJECT_DIR"

export PYTHONPATH="$PROJECT_DIR/src"
export COBRINHA_SERVER_DIR="$PROJECT_DIR"

server_ready() {
    "$PROJECT_DIR/.venv/bin/python" - "$HOST" "$PORT" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

host = sys.argv[1]
port = int(sys.argv[2])

try:
    with urllib.request.urlopen(
        f"http://{host}:{port}/api/health",
        timeout=0.7,
    ) as response:
        raise SystemExit(
            0 if response.status == 200 else 1
        )
except Exception:
    raise SystemExit(1)
PY
}

open_panel() {
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$PANEL_URL" >/dev/null 2>&1 &
        return
    fi

    if command -v gio >/dev/null 2>&1; then
        gio open "$PANEL_URL" >/dev/null 2>&1 &
        return
    fi

    printf 'Abra no navegador: %s\n' "$PANEL_URL"
}

echo "COBRINHA"
echo "Painel: $PANEL_URL"
echo "Executando reinício limpo do servidor..."

if ! systemctl --user restart cobrinha-server.service; then
    echo "Falha ao solicitar reinício do servidor Cobrinha."
    exit 1
fi

READY=0

for _ in $(seq 1 150); do
    if server_ready; then
        READY=1
        break
    fi

    sleep 0.10
done

if [ "$READY" -ne 1 ]; then
    echo "Falha: servidor não respondeu após o reinício limpo."
    systemctl --user status         cobrinha-server.service         --no-pager         -l         || true
    exit 1
fi

echo "Servidor reiniciado e saudável. Abrindo painel..."
open_panel

echo
echo "A pré-limpeza é executada antes do novo backend subir."
echo "Este atalho não inicia transmissão."
