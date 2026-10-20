#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALLER="${ROOT_DIR}/installer/linux/install.sh"

cat <<'BANNER'
============================================================
            Snake Reyers Lite - Instalador
============================================================

Este assistente prepara tudo o que o programa precisa: o
ambiente Python, as dependencias do monitor, a voz em
portugues, as musicas e o atalho "Snake Reyers Lite" na Area
de Trabalho.

A primeira instalacao pode demorar e precisa de alguns
gigabytes livres.

BANNER

if [[ ! -f "${INSTALLER}" ]]; then
	echo "Instalador nao encontrado: ${INSTALLER}" >&2
	exit 1
fi

chmod +x "${INSTALLER}"
"${INSTALLER}"

cat <<'BANNER'

============================================================
   Instalacao concluida com sucesso!
============================================================

Abra o atalho "Snake Reyers Lite" na Area de Trabalho para
iniciar o programa e abrir o painel no navegador.
BANNER