from __future__ import annotations

import os
import re
from typing import Any

from cobrinha_server.core.json_store import read_json, write_json_atomic
from cobrinha_server.core.settings import SOCIAL_TEXT_AI_CONFIG_FILE
from cobrinha_server.services import social_text_ai


_DEFAULT_MODEL = "gpt-4.1-mini"
_MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,80}$")


def _raw() -> dict[str, Any]:
    value = read_json(SOCIAL_TEXT_AI_CONFIG_FILE, {})
    return value if isinstance(value, dict) else {}


def public_status() -> dict[str, Any]:
    status = social_text_ai.status()
    return {
        "enabled": bool(status.get("enabled")),
        "provider": str(status.get("provider") or "disabled"),
        "model": str(status.get("model") or _DEFAULT_MODEL),
        "api_key_present": bool(status.get("api_key_present")),
        "auto_external_call": bool(status.get("auto_external_call")),
    }


def update(payload: dict[str, Any]) -> dict[str, Any]:
    current = _raw()
    clear_key = bool(payload.get("clear_key"))
    supplied_key = str(payload.get("api_key") or "").strip()

    if clear_key:
        current.pop("openai_api_key", None)
        current.pop("api_key", None)
    elif supplied_key:
        if len(supplied_key) < 20 or any(character.isspace() for character in supplied_key):
            raise ValueError("Chave da API OpenAI invalida.")
        current["openai_api_key"] = supplied_key
        current.pop("api_key", None)

    model = str(payload.get("model") or current.get("model") or _DEFAULT_MODEL).strip()
    if not _MODEL_PATTERN.fullmatch(model):
        raise ValueError("Nome de modelo invalido.")

    enabled = bool(payload.get("enabled"))
    key_present = bool(str(current.get("openai_api_key") or "").strip())
    if enabled and not key_present:
        raise ValueError("Informe uma chave da API OpenAI antes de ativar a IA.")

    current.update(
        {
            "enabled": enabled,
            "provider": "openai" if key_present else "disabled",
            "model": model,
        }
    )
    write_json_atomic(SOCIAL_TEXT_AI_CONFIG_FILE, current)
    try:
        os.chmod(SOCIAL_TEXT_AI_CONFIG_FILE, 0o600)
    except OSError:
        pass
    return public_status()
