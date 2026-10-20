from __future__ import annotations

import re
import threading
import unicodedata
import uuid
import wave
from pathlib import Path
from typing import Any

from cobrinha_server.core.settings import (
    DEFAULT_VOICE_PATH,
    RUNS_DIR,
)
from cobrinha_server.services.audio_timeline import (
    analyze_audio_timeline,
    build_audio_timeline_payload,
    write_audio_timeline_json,
)


XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
PREPARED_AUDIO_DIR = RUNS_DIR / "prepared_audio"

_XTTS_LOCK = threading.Lock()
_XTTS_MODEL: Any | None = None


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

    # O XTTS desta voz pode vocalizar o ponto como palavra.
    # Igual ao projeto de referencia, ponto de frase vira pausa.
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

    clean = _apply_pt_br_tts_pronunciation(
        clean
    )

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


def _apply_pt_br_tts_pronunciation(
    text: str,
) -> str:
    clean = unicodedata.normalize(
        "NFC",
        text,
    )

    # Regras verificadas no Snake Reyers para esta pilha XTTS.
    replacements = (
        (r"\bexpli", "espli"),
        (r"\bexplic", "esplic"),
        (r"\bexper", "esper"),
        (r"\bexped", "esped"),
        (r"\bexpos", "espos"),
        (r"\bexpress", "espress"),
        (r"\bexplo", "esplo"),
        (r"\bexpul", "espul"),
        (r"\bextra", "estra"),
        (r"\bextre", "estre"),
        (r"\bexter", "ester"),
        (r"\bexces", "esses"),
        (r"\bexce", "esse"),
        (r"\bexempl", "ezempl"),
        (r"\bexat", "ezat"),
        (r"\bexist", "ezist"),
        (r"\bexecut", "ezecut"),
        (r"\bexib", "ezib"),
        (r"\bexag", "ezag"),
        (r"\bexam", "ezam"),
    )

    for pattern, value in replacements:
        clean = re.sub(
            pattern,
            value,
            clean,
            flags=re.IGNORECASE,
        )

    # Correcao fonetica usada no projeto de referencia.
    clean = clean.replace(
        "Ç",
        "SS",
    ).replace(
        "ç",
        "ss",
    )

    return clean


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


def voice_ready() -> bool:
    return (
        DEFAULT_VOICE_PATH.is_file()
        and DEFAULT_VOICE_PATH.stat().st_size > 1024
    )


def xtts_model_loaded() -> bool:
    return _XTTS_MODEL is not None


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

    resolved_voice = Path(
        voice_path or DEFAULT_VOICE_PATH
    ).expanduser()

    if not resolved_voice.is_file():
        raise FileNotFoundError(
            f"Voz XTTS nao encontrada: {resolved_voice}"
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
            language=language,
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


def _load_xtts_model() -> Any:
    global _XTTS_MODEL

    if _XTTS_MODEL is not None:
        return _XTTS_MODEL

    import torch
    from TTS.api import TTS

    device = (
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    _XTTS_MODEL = TTS(
        model_name=XTTS_MODEL_NAME
    ).to(device)

    return _XTTS_MODEL


def _synthesize_chunk(
    text: str,
    output: Path,
    *,
    voice_path: Path,
    language: str,
) -> None:
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with _XTTS_LOCK:
        model = _load_xtts_model()

        model.tts_to_file(
            text=unicodedata.normalize(
                "NFC",
                text,
            ),
            speaker_wav=[
                str(voice_path),
            ],
            language=str(
                language or "pt"
            ),
            file_path=str(output),
            split_sentences=True,
        )

    if (
        not output.is_file()
        or output.stat().st_size <= 44
    ):
        raise RuntimeError(
            "XTTS nao produziu WAV valido."
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
