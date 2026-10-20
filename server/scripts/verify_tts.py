from __future__ import annotations

import json
from pathlib import Path

from cobrinha_server.services.tts_service import (
    synthesize_for_job,
    voice_ready,
)


def main() -> int:
    if not voice_ready():
        raise SystemExit("A voz padrao nao esta instalada.")

    result = synthesize_for_job(
        "O sistema de voz do Snake Reyers esta funcionando.",
    )
    audio_path = Path(result["audio_path"])
    if not audio_path.is_file() or audio_path.stat().st_size <= 44:
        raise SystemExit("O Piper nao gerou um arquivo WAV valido.")

    print(
        json.dumps(
            {
                "ok": True,
                "audio_path": str(audio_path),
                "bytes": audio_path.stat().st_size,
                "voice_path": result["voice_path"],
            },
            ensure_ascii=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
