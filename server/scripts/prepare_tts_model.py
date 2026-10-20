from __future__ import annotations

import os


MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"


def main() -> int:
    if os.getenv("COQUI_TOS_AGREED") != "1":
        raise SystemExit(
            "A licenca CPML do modelo XTTS precisa ser aceita antes do download."
        )

    import torch
    from TTS.api import TTS

    device = "cuda" if torch.cuda.is_available() else "cpu"
    TTS(model_name=MODEL_NAME).to(device)
    print(f"XTTS preparado com sucesso em {device}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
