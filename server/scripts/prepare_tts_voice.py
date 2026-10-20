from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cobrinha_server.core.settings import PIPER_VOICE_DIR


DEFAULT_VOICES = (
    "pt_BR-faber-medium",
    "pt_BR-cadu-medium",
    "pt_BR-jeff-medium",
)


def _voice_ready(
    name: str,
) -> bool:
    model = PIPER_VOICE_DIR / f"{name}.onnx"
    return (
        model.is_file()
        and Path(f"{model}.json").is_file()
        and model.stat().st_size > 1024
    )


def _download_voice(
    name: str,
) -> None:
    print(
        f"Baixando voz Piper {name}...",
        flush=True,
    )

    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "piper.download_voices",
            name,
            "--data-dir",
            str(PIPER_VOICE_DIR),
        ]
    )


def main(
    argv: list[str] | None = None,
) -> int:
    names = [
        str(value).strip()
        for value in (
            argv
            if argv is not None
            else sys.argv[1:]
        )
        if str(value).strip()
    ]

    if not names:
        names = list(DEFAULT_VOICES)

    PIPER_VOICE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for name in names:
        if _voice_ready(name):
            print(
                f"Voz Piper {name} ja instalada.",
                flush=True,
            )
            continue

        _download_voice(name)

        if not _voice_ready(name):
            raise SystemExit(
                f"Falha ao instalar a voz Piper {name}."
            )

    print(
        f"Vozes Piper prontas em {PIPER_VOICE_DIR}.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
