#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER_DIR="${ROOT_DIR}/server"
PYTHON="${SERVER_DIR}/.venv/bin/python"

if [[ -x "${ROOT_DIR}/launcher/create_shortcut_linux.sh" ]]; then
	"${ROOT_DIR}/launcher/create_shortcut_linux.sh" >/dev/null 2>&1 || true
fi

if [[ ! -x "${PYTHON}" ]]; then
	echo "Execute installer/linux/install.sh primeiro." >&2
	exit 2
fi

if curl -fsS http://127.0.0.1:9393/api/health >/dev/null 2>&1; then
	if [[ "${SNAKE_REYERS_SKIP_BROWSER:-0}" != "1" ]]; then
		xdg-open http://127.0.0.1:9393 >/dev/null 2>&1 || true
	fi
	exit 0
fi

mkdir -p "${SERVER_DIR}/runs/logs"
export COBRINHA_SERVER_DIR="${SERVER_DIR}"
export PYTHONPATH="${SERVER_DIR}/src"
export TTS_HOME="${SERVER_DIR}/runtime/tts"

if ! "${PYTHON}" "${ROOT_DIR}/launcher/update.py" --install; then
	echo "Nao foi possivel atualizar agora; iniciando a versao instalada." >&2
fi

nohup "${PYTHON}" -m uvicorn cobrinha_server.main:app \
	--host 127.0.0.1 --port 9393 \
	>"${SERVER_DIR}/runs/logs/server.log" 2>&1 &

for _ in $(seq 1 40); do
	if curl -fsS http://127.0.0.1:9393/api/health >/dev/null 2>&1; then
		if [[ "${SNAKE_REYERS_SKIP_BROWSER:-0}" != "1" ]]; then
			xdg-open http://127.0.0.1:9393 >/dev/null 2>&1 || true
		fi
		exit 0
	fi
	sleep 0.25
done

echo "O servidor nao iniciou. Consulte server/runs/logs/server.log" >&2
exit 3
