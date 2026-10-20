#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESKTOP_DIR="${XDG_DESKTOP_DIR:-}"

if [[ -z "${DESKTOP_DIR}" ]] && command -v xdg-user-dir >/dev/null 2>&1; then
	DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
if [[ -z "${DESKTOP_DIR}" ]]; then
	for candidate in "${HOME}/Área de Trabalho" "${HOME}/Desktop"; do
		if [[ -d "${candidate}" ]]; then
			DESKTOP_DIR="${candidate}"
			break
		fi
	done
fi
if [[ -z "${DESKTOP_DIR}" ]]; then
	DESKTOP_DIR="${HOME}/Desktop"
fi

mkdir -p "${DESKTOP_DIR}"
SHORTCUT="${DESKTOP_DIR}/Snake Reyers.desktop"
cat >"${SHORTCUT}" <<EOF
[Desktop Entry]
Type=Application
Name=Snake Reyers
Comment=Iniciar o Snake Reyers e abrir o painel
Exec="${ROOT_DIR}/launcher/start_linux.sh"
Icon=applications-games
Terminal=false
Categories=Game;
StartupNotify=true
EOF

chmod +x "${SHORTCUT}"
if command -v gio >/dev/null 2>&1; then
	gio set "${SHORTCUT}" metadata::trusted true >/dev/null 2>&1 || true
fi

printf 'Atalho criado na Area de Trabalho: %s\n' "${SHORTCUT}"
