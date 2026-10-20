from __future__ import annotations

import re
import threading
import unicodedata
import uuid
import wave
from pathlib import Path
from typing import Any

from cobrinha_server.core.settings import (
    DEFAULT_PIPER_VOICE,
    PIPER_VOICE_DIR,
    RUNS_DIR,
)
from cobrinha_server.services.audio_timeline import (
    analyze_audio_timeline,
    build_audio_timeline_payload,
    write_audio_timeline_json,
)


PREPARED_AUDIO_DIR = RUNS_DIR / "prepared_audio"

_PIPER_LOCK = threading.Lock()
_PIPER_VOICES: dict[str, Any] = {}


def prepare_tts_input(
    text: object,
) -> str:
    clean = " ".join(
        str(text or "").split()
    ).strip()

    if not clean:
        return ""

    clean = unicodedata.normalize(
        "NFC",
        clean,
    )

    clean = _normalize_unicode_digits_for_tts(
        clean
    )

    clean = _restore_common_pt_br_accents(
        clean
    )

    clean = re.sub(
        r"\.{2,}|…+",
        ", ",
        clean,
    )

    clean = re.sub(
        r"(?<!\d)\.(?!\d)",
        ",",
        clean,
    )

    clean = re.sub(
        r"\s+([,!?;:])",
        r"\1",
        clean,
    )

    clean = re.sub(
        r"([,!?;:]){2,}",
        r"\1",
        clean,
    )

    clean = re.sub(
        r"\s+",
        " ",
        clean,
    ).strip(" ,;:")

    return unicodedata.normalize(
        "NFC",
        clean,
    )


def _normalize_unicode_digits_for_tts(
    text: str,
) -> str:
    parts: list[str] = []

    for char in text:
        try:
            parts.append(
                str(
                    unicodedata.digit(char)
                )
            )
        except (TypeError, ValueError):
            parts.append(char)

    return "".join(parts)


def _restore_common_pt_br_accents(
    text: object,
) -> str:
    clean = unicodedata.normalize(
        "NFC",
        str(text or ""),
    )

    replacements = {
        "acao": "ação",
        "acoes": "ações",
        "agradeco": "agradeço",
        "alem": "além",
        "alguem": "alguém",
        "ate": "até",
        "atencao": "atenção",
        "audiencia": "audiência",
        "coracao": "coração",
        "criacao": "criação",
        "decisao": "decisão",
        "direcao": "direção",
        "emocao": "emoção",
        "explicacao": "explicação",
        "funcao": "função",
        "geracao": "geração",
        "historia": "história",
        "ja": "já",
        "maca": "maçã",
        "macas": "maçãs",
        "maça": "maçã",
        "maças": "maçãs",
        "nao": "não",
        "ninguem": "ninguém",
        "operacao": "operação",
        "participacao": "participação",
        "presenca": "presença",
        "producao": "produção",
        "reacao": "reação",
        "relacao": "relação",
        "sequencia": "sequência",
        "silencio": "silêncio",
        "situacao": "situação",
        "tambem": "também",
        "transmissao": "transmissão",
        "voce": "você",
        "voces": "vocês",
    }

    def replace_word(
        match: re.Match[str],
    ) -> str:
        word = match.group(0)

        replacement = replacements.get(
            word.casefold()
        )

        if not replacement:
            return word

        if word.isupper():
            return replacement.upper()

        if word[:1].isupper():
            return (
                replacement[:1].upper()
                + replacement[1:]
            )

        return replacement

    return re.sub(
        r"\b[A-Za-zÀ-ÿ]+\b",
        replace_word,
        clean,
    )


def safe_tts_chunks(
    text: str,
    *,
    max_chars: int = 150,
) -> list[str]:
    clean = prepare_tts_input(
        text
    )

    if not clean:
        return []

    limit = max(
        40,
        min(
            150,
            int(max_chars),
        ),
    )

    chunks: list[str] = []
    remaining = clean

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        window = remaining[: limit + 1]
        split_at = -1

        for token in (
            "! ",
            "? ",
            "; ",
            ", ",
            " ",
        ):
            index = window.rfind(token)

            if index > split_at:
                split_at = (
                    index + 1
                    if token == " "
                    else index + len(token) - 1
                )

        if split_at < 30:
            split_at = limit

        part = remaining[:split_at].strip(
            " ,;:"
        )

        if part:
            chunks.append(part)

        remaining = remaining[split_at:].strip()

    return [
        chunk
        for chunk in chunks
        if chunk
    ]


def available_voice_paths() -> list[Path]:
    if not PIPER_VOICE_DIR.is_dir():
        return []

    voices: list[Path] = []

    for model in sorted(
        PIPER_VOICE_DIR.glob("*.onnx"),
        key=lambda item: item.name.casefold(),
    ):
        if not model.is_file():
            continue

        if not Path(
            f"{model}.json"
        ).is_file():
            continue

        voices.append(model)

    return voices


def default_voice_path() -> Path | None:
    configured = Path(
        DEFAULT_PIPER_VOICE
    ).expanduser()

    if (
        configured.is_file()
        and Path(
            f"{configured}.json"
        ).is_file()
    ):
        return configured

    voices = available_voice_paths()
    return voices[0] if voices else None


def voice_ready() -> bool:
    return default_voice_path() is not None


def tts_model_loaded() -> bool:
    return bool(_PIPER_VOICES)


def _resolve_voice_path(
    voice_path: Path | None,
) -> Path:
    candidate = (
        Path(voice_path).expanduser()
        if voice_path
        else None
    )

    if (
        candidate is not None
        and candidate.suffix.casefold() == ".onnx"
        and candidate.is_file()
        and Path(
            f"{candidate}.json"
        ).is_file()
    ):
        return candidate

    resolved = default_voice_path()

    if resolved is None:
        raise FileNotFoundError(
            "Nenhuma voz Piper instalada. Execute "
            "scripts/prepare_tts_voice.py."
        )

    return resolved


def synthesize_for_job(
    text: str,
    *,
    voice_path: Path | None = None,
    language: str = "pt",
) -> dict[str, Any]:
    chunks = safe_tts_chunks(
        text,
        max_chars=150,
    )

    if not chunks:
        raise ValueError(
            "Texto vazio para sintese."
        )

    resolved_voice = _resolve_voice_path(
        voice_path
    )

    PREPARED_AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    token = uuid.uuid4().hex
    output = (
        PREPARED_AUDIO_DIR
        / f"speech_{token}.wav"
    )

    part_paths: list[Path] = []

    for index, chunk in enumerate(chunks):
        part = (
            PREPARED_AUDIO_DIR
            / f"speech_{token}_part_{index:03d}.wav"
        )

        _synthesize_chunk(
            chunk,
            part,
            voice_path=resolved_voice,
        )

        part_paths.append(part)

    if len(part_paths) == 1:
        source = part_paths[0]

        with wave.open(str(source), "rb") as reader:
            params = reader.getparams()
            frames = reader.readframes(
                reader.getnframes()
            )

        with wave.open(str(output), "wb") as writer:
            writer.setparams(params)
            writer.writeframes(frames)
    else:
        _concat_wavs(
            part_paths,
            output,
        )

    timeline_path = output.with_suffix(
        ".json"
    )

    try:
        timeline = write_audio_timeline_json(
            output,
            timeline_path,
        )
    except Exception:
        timeline = analyze_audio_timeline(
            output
        )

    timeline_payload = build_audio_timeline_payload(
        output,
        timeline,
    )

    return {
        "audio_path": str(
            output.resolve()
        ),
        "timeline_path": str(
            timeline_path.resolve()
        ),
        "timeline": timeline_payload,
        "voice_path": str(
            resolved_voice.resolve()
        ),
        "chunks": chunks,
    }


def _load_piper_voice(
    voice_path: Path,
) -> Any:
    key = str(
        voice_path.resolve()
    )

    cached = _PIPER_VOICES.get(key)

    if cached is not None:
        return cached

    from piper import (
        PiperVoice,
        SynthesisConfig,
    )

    voice = PiperVoice.load(
        str(voice_path)
    )

    _PIPER_VOICES[key] = (
        voice,
        SynthesisConfig(
            volume=1.0,
            length_scale=1.0,
            noise_scale=0.667,
            noise_w_scale=0.8,
            normalize_audio=True,
        ),
    )

    return _PIPER_VOICES[key]


def _synthesize_chunk(
    text: str,
    output: Path,
    *,
    voice_path: Path,
) -> None:
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with _PIPER_LOCK:
        voice, syn_config = _load_piper_voice(
            voice_path
        )

        with wave.open(
            str(output),
            "wb",
        ) as wav_file:
            voice.synthesize_wav(
                unicodedata.normalize(
                    "NFC",
                    text,
                ),
                wav_file,
                syn_config=syn_config,
            )

    if (
        not output.is_file()
        or output.stat().st_size <= 44
    ):
        raise RuntimeError(
            "Piper nao produziu WAV valido."
        )


def _concat_wavs(
    parts: list[Path],
    output: Path,
) -> None:
    if not parts:
        raise ValueError(
            "Nenhuma parte WAV."
        )

    params = None
    payloads: list[bytes] = []

    for part in parts:
        with wave.open(
            str(part),
            "rb",
        ) as handle:
            current = (
                handle.getnchannels(),
                handle.getsampwidth(),
                handle.getframerate(),
                handle.getcomptype(),
                handle.getcompname(),
            )

            if params is None:
                params = current
            elif current != params:
                raise RuntimeError(
                    "Formatos WAV diferentes."
                )

            payloads.append(
                handle.readframes(
                    handle.getnframes()
                )
            )

    if params is None:
        raise RuntimeError(
            "Parametros WAV ausentes."
        )

    channels, width, rate, comptype, compname = params

    with wave.open(
        str(output),
        "wb",
    ) as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        handle.setcomptype(
            comptype,
            compname,
        )

        for payload in payloads:
            handle.writeframes(payload)
