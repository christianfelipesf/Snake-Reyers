from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any, Callable

from cobrinha_server.services.social_text_ai import (
    generate_chat_reply,
    generate_gift_reply,
)


def _clip(
    value: object,
    limit: int = 150,
) -> str:
    clean = " ".join(
        str(value or "").split()
    )

    if len(clean) <= limit:
        return clean

    return (
        clean[
            : max(1, limit - 1)
        ].rstrip(" ,.;:")
        + "."
    )


def _norm(
    value: object,
) -> str:
    text = unicodedata.normalize(
        "NFKD",
        str(value or "").casefold(),
    )
    text = "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    )
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact_repeated_letters(
    value: str,
) -> str:
    return re.sub(
        r"([a-z0-9])\1+",
        r"\1",
        value,
    )


def _simple_greeting_reply(
    *,
    display_name: str,
    comment: str,
    user_key: str,
) -> str:
    normalized = _norm(comment)
    compacted = _compact_repeated_letters(
        normalized
    )
    greeting_terms = {
        "oi",
        "ola",
        "olá",
        "bom dia",
        "boa tarde",
        "boa noite",
        "tudo bem",
        "tudo bom",
        "tudo certo",
        "td bem",
        "como vai",
        "e ai",
        "eai",
        "eae",
        "opa",
        "salve",
    }

    if (
        normalized not in greeting_terms
        and compacted not in greeting_terms
    ):
        return ""

    key = (
        normalized
        if normalized in greeting_terms
        else compacted
    )
    name = _clip(display_name or "visitante", 32)
    if key.startswith("bom dia"):
        options = (
            f"Bom dia, {name}.",
            f"{name}, bom dia.",
            f"Bom dia, tudo bem, {name}?",
            f"{name}, bom dia. Como vai?",
        )
    elif key.startswith("boa tarde"):
        options = (
            f"Boa tarde, {name}.",
            f"{name}, boa tarde.",
            f"Boa tarde, tudo bem, {name}?",
            f"{name}, boa tarde. Como vai?",
        )
    elif key.startswith("boa noite"):
        options = (
            f"Boa noite, {name}.",
            f"{name}, boa noite.",
            f"Boa noite, tudo bem, {name}?",
            f"{name}, boa noite. Como vai?",
        )
    elif key in {
        "tudo bem",
        "tudo bom",
        "tudo certo",
        "td bem",
        "como vai",
    }:
        options = (
            f"Tudo bem, {name}?",
            f"{name}, tudo bem?",
            f"Como vai, {name}?",
            f"{name}, como vai?",
            f"Tudo certo, {name}?",
        )
    else:
        options = (
            f"Oi, {name}.",
            f"{name}, oi.",
            f"Olá, {name}.",
            f"{name}, olá.",
            f"Como vai, {name}?",
            f"{name}, tudo bem?",
        )
    seed = (
        str(user_key or name)
        + "\n"
        + key
    ).encode("utf-8", errors="ignore")
    return options[hashlib.sha256(seed).digest()[0] % len(options)]


def build_main_reply(
    *,
    display_name: str,
    comment: str,
    user_key: str = "",
    current_game: str = "Cobrinha",
    ai_transport: Callable[
        [dict[str, Any]],
        str,
    ]
    | None = None,
) -> str:
    name = _clip(
        display_name
        or "visitante",
        48,
    )

    message = _clip(
        comment,
        150,
    )

    simple_reply = _simple_greeting_reply(
        display_name=name,
        comment=message,
        user_key=user_key,
    )

    if simple_reply:
        return _clip(
            simple_reply,
            150,
        )

    ai_reply = generate_chat_reply(
        display_name=name,
        comment=message,
        user_key=user_key,
        current_game=current_game,
        transport=ai_transport,
    )

    if ai_reply:
        return _clip(
            ai_reply,
            150,
        )

    seed = (
        str(user_key or name)
        + "\n"
        + message
    ).encode(
        "utf-8",
        errors="ignore",
    )

    choice = (
        hashlib.sha256(seed).digest()[0]
        % 4
    )

    if "?" in message:
        options = (
            f"{name}, boa pergunta. A Serpente do Abismo ouviu e esta pensando sem bater a cabeça na parede.",
            f"{name}, pergunta registrada. Eu tenho uma maçã, um tabuleiro e confiança demais para uma serpente.",
            f"{name}, ouvi a pergunta. Vou responder enquanto tento não virar meu próprio obstáculo.",
            f"{name}, essa veio boa. A Serpente do Abismo pensa e caça maçã ao mesmo tempo.",
        )
    else:
        options = (
            f"{name}, ouvi você. A Serpente do Abismo segue atenta, mesmo fingindo que só pensa em maçã.",
            f"{name}, mensagem recebida. Agora é minha vez de falar sem enrolar o próprio corpo.",
            f"{name}, eu escutei. Continue por aí que a Serpente do Abismo tenta sobreviver ao tabuleiro.",
            f"{name}, anotado. A plateia fala e eu respondo enquanto a maçã tenta fugir do Abismo.",
        )

    return _clip(
        options[choice],
        150,
    )


def build_gift_reply(
    *,
    display_name: str,
    gift_name: str,
    gift_count: int = 1,
    user_key: str = "",
    current_game: str = "Cobrinha",
    ai_transport: Callable[
        [dict[str, Any]],
        str,
    ]
    | None = None,
) -> str:
    name = _clip(
        display_name
        or "visitante",
        48,
    )
    gift = _clip(
        gift_name
        or "presente",
        60,
    )
    count = max(
        1,
        int(gift_count or 1),
    )

    ai_reply = generate_gift_reply(
        display_name=name,
        gift_name=gift,
        gift_count=count,
        user_key=user_key,
        current_game=current_game,
        transport=ai_transport,
    )

    if ai_reply:
        return _clip(
            ai_reply,
            150,
        )

    seed = (
        str(user_key or name)
        + "\n"
        + gift
        + "\n"
        + str(count)
    ).encode(
        "utf-8",
        errors="ignore",
    )
    choice = (
        hashlib.sha256(seed).digest()[0]
        % 4
    )

    quantity = (
        f" x{count}"
        if count > 1
        else ""
    )
    options = (
        f"{name}, valeu pelo {gift}{quantity}. A Serpente guardou isso com cara de quem sabe demais.",
        f"{name}, obrigado pelo {gift}{quantity}. Minha cauda ate fingiu elegancia agora.",
        f"{name}, presente recebido: {gift}{quantity}. A arena ficou mais alimentada e menos normal.",
        f"{name}, valeu pelo {gift}{quantity}. A Cobrinha agradece sem derrubar a maçã da boca.",
    )

    return _clip(
        options[choice],
        150,
    )
