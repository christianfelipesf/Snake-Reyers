#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER_DIR="${ROOT_DIR}/server"
MONITOR_DIR="${SERVER_DIR}/external/tiktok-live-monitoring-server"
DOWNLOAD_DIR="${TMPDIR:-/tmp}/snake-reyers-installer"

for command in python3 node npm; do
	if ! command -v "${command}" >/dev/null 2>&1; then
		echo "Dependencia ausente: ${command}" >&2
		exit 2
	fi
done

NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])')"
if (( NODE_MAJOR < 22 )); then
	echo "Node.js 22 ou superior e necessario. Versao atual: $(node --version)" >&2
	exit 2
fi

python3 -m venv "${SERVER_DIR}/.venv"
"${SERVER_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${SERVER_DIR}/.venv/bin/python" -m pip install -r "${SERVER_DIR}/requirements.txt"

PYTHON="${SERVER_DIR}/.venv/bin/python"
"${PYTHON}" -m pip install -r "${SERVER_DIR}/requirements-voice.txt"

export COBRINHA_SERVER_DIR="${SERVER_DIR}"
export PYTHONPATH="${SERVER_DIR}/src"

if [[ "${SNAKE_REYERS_SKIP_TTS_MODEL:-0}" != "1" ]]; then
	"${PYTHON}" "${SERVER_DIR}/scripts/prepare_tts_voice.py"
fi

install_audio_packages() {
	local manifest="${SERVER_DIR}/assets/audio-manifest.json"
	local marker="${SERVER_DIR}/assets/.audio-package-version"
	local manifest_hash

	[[ -f "${manifest}" ]] || {
		echo "Manifesto dos pacotes de audio ausente: ${manifest}" >&2
		echo "As musicas de fundo nao serao instaladas agora." >&2
		return 0
	}

	manifest_hash="$(sha256sum "${manifest}" | awk '{print $1}')"
	if [[ -f "${marker}" ]] && [[ "$(cat "${marker}")" == "${manifest_hash}" ]]; then
		echo "Vozes e musicas ja estao instaladas."
		return
	fi

	mkdir -p "${DOWNLOAD_DIR}"
	"${PYTHON}" - "${manifest}" "${ROOT_DIR}" "${DOWNLOAD_DIR}" <<'PY'
import hashlib
import json
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

manifest_path = Path(sys.argv[1])
root = Path(sys.argv[2])
download_dir = Path(sys.argv[3])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

for pack in manifest["packs"]:
    name = pack["name"]
    expected = pack["sha256"].lower()
    candidates = (root.parent / name, root / name, root / "packages" / name)
    archive = next((path for path in candidates if path.is_file()), download_dir / name)
    if not archive.is_file():
        print(f"Baixando {name}...")
        urllib.request.urlretrieve(pack["url"], archive)
    hasher = hashlib.sha256()
    with archive.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            hasher.update(chunk)
    digest = hasher.hexdigest()
    if digest != expected:
        raise SystemExit(f"Pacote de audio invalido: {archive}")
    print(f"Instalando {name}...")
    with zipfile.ZipFile(archive) as package:
        package.extractall(root)
PY
	printf '%s' "${manifest_hash}" >"${marker}"
}

install_audio_packages

if [[ -f "${MONITOR_DIR}/package-lock.json" ]]; then
	(cd "${MONITOR_DIR}" && npm ci --omit=dev)
else
	(cd "${MONITOR_DIR}" && npm install --omit=dev)
fi

chmod +x "${ROOT_DIR}/game/linux/SnakeReyers.x86_64" 2>/dev/null || true
chmod +x "${ROOT_DIR}/launcher/create_shortcut_linux.sh" 2>/dev/null || true
mkdir -p "${SERVER_DIR}/private" "${SERVER_DIR}/runs/logs"

if ! "${ROOT_DIR}/launcher/create_shortcut_linux.sh"; then
	echo "Aviso: nao foi possivel criar o atalho na Area de Trabalho." >&2
fi

echo "Snake Reyers Lite instalado com voz Piper, jogo e musicas. Use o atalho da Area de Trabalho para iniciar."
