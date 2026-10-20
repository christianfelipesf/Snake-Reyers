from __future__ import annotations

import re
import unicodedata

from cobrinha_server.core.settings import (
    BLACKLIST_FILE,
)


_BLACKLIST_CACHE: set[str] = set()
_BLACKLIST_MTIME_NS = -1

_OUTPUT_FILTER_EXCLUSIONS = {
    "manda",
    "mande",
    "mandar",
    "manda salve",
    "manda um salve",
    "manda beijo",
    "me manda beijo",
    "manda oi pro",
    "manda oi pra",
    "manda oi para",
    "mandou uma",
    "enviou",
    "enviou um",
    "me da",
    "me dá",
    "dinheiro",
}


_USER_MENTION_RE = re.compile(
    r"(?<![0-9A-Za-zÀ-ÿ_])@\s*"
    r"[0-9A-Za-zÀ-ÿ_]"
    r"[0-9A-Za-zÀ-ÿ_.-]*",
    re.IGNORECASE,
)
_PORTUGUESE_COMMENT_PUNCTUATION = set(".,!?;:'\"()[]{}-")
_PORTUGUESE_EXTRA_LETTERS = set(
    "áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ"
)


def has_blocked_term(
    text: object,
) -> bool:
    normalized = _norm(text)

    if not normalized:
        return False

    terms = _load_blacklist()

    if not terms:
        return False

    return _matches_terms(
        normalized,
        terms,
    )


def has_blocked_output_term(
    text: object,
) -> bool:
    normalized = _norm(text)

    if not normalized:
        return False

    terms = _load_blacklist()

    if not terms:
        return False

    return _matches_terms(
        normalized,
        terms
        - {
            _norm(term)
            for term in _OUTPUT_FILTER_EXCLUSIONS
        },
    )


def _norm(value: object) -> str:
    text = unicodedata.normalize(
        "NFKD",
        str(value or "").casefold(),
    )

    text = "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    )

    text = (
        text
        .replace("0", "o")
        .replace("1", "i")
        .replace("2", "z")
        .replace("3", "e")
        .replace("4", "a")
        .replace("5", "s")
        .replace("7", "t")
        .replace("8", "b")
        .replace("9", "g")
        .replace("@", "a")
    )

    text = re.sub(
        r"[^0-9a-zà-ÿ]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _load_blacklist() -> set[str]:
    global _BLACKLIST_CACHE
    global _BLACKLIST_MTIME_NS

    try:
        stat = BLACKLIST_FILE.stat()
    except OSError:
        _BLACKLIST_CACHE = set()
        _BLACKLIST_MTIME_NS = -1
        return set()

    if (
        _BLACKLIST_CACHE
        and stat.st_mtime_ns
        == _BLACKLIST_MTIME_NS
    ):
        return _BLACKLIST_CACHE

    try:
        lines = BLACKLIST_FILE.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError:
        lines = []

    terms: set[str] = set()

    for line in lines:
        clean = line.split(
            "#",
            1,
        )[0].strip()

        if clean:
            terms.add(
                _norm(clean)
            )

    _BLACKLIST_CACHE = terms
    _BLACKLIST_MTIME_NS = (
        stat.st_mtime_ns
    )

    return terms


def _matches_terms(
    normalized: str,
    terms: set[str],
) -> bool:
    tokens = set(
        normalized.split()
    )
    compact = normalized.replace(
        " ",
        "",
    )

    for term in terms:
        if not term:
            continue

        if " " in term:
            if term in normalized:
                return True

            compact_term = term.replace(
                " ",
                "",
            )

            if (
                len(compact_term) >= 8
                and compact_term in compact
            ):
                return True

            continue

        if term in tokens:
            return True

        if _matches_spaced_word(
            normalized,
            term,
        ):
            return True

    return False


def _matches_spaced_word(
    normalized: str,
    term: str,
) -> bool:
    if (
        len(term) < 4
        or " " not in normalized
    ):
        return False

    letters = r"\s*".join(
        re.escape(char)
        for char in term
    )

    return bool(
        re.search(
            rf"(?<![0-9a-zà-ÿ]){letters}(?![0-9a-zà-ÿ])",
            normalized,
        )
    )


def has_user_mention(text: object) -> bool:
    raw = str(text or "")
    return bool(
        raw
        and _USER_MENTION_RE.search(raw)
    )


def has_low_value_noise_pattern(
    text: object,
) -> bool:
    raw = str(text or "").strip()

    if not raw:
        return True

    if len(raw) > 150:
        return True

    normalized = _norm(raw)

    words = re.findall(
        r"[A-Za-zÀ-ÿ0-9]+",
        raw,
    )

    if not words:
        return True

    if any(
        len(word) >= 25
        for word in words
    ):
        return True

    if re.search(
        r"([^\w\sÀ-ÿ])\1+",
        raw,
    ):
        return True

    compact = normalized.replace(
        " ",
        "",
    )

    if re.fullmatch(
        r"(?:kk+|rs+|\d+|\W+)",
        compact,
    ):
        return True

    if (
        len(words) >= 3
        and len(
            {
                word.casefold()
                for word in words
            }
        ) == 1
    ):
        return True

    return False


def has_disallowed_comment_content(
    text: object,
) -> bool:
    raw = unicodedata.normalize(
        "NFC",
        str(text or "").strip(),
    )

    if not raw:
        return True

    if any(char.isdigit() for char in raw):
        return True

    has_letter = False
    for char in raw:
        if char.isspace() or char in _PORTUGUESE_COMMENT_PUNCTUATION:
            continue

        if _is_portuguese_letter(char):
            has_letter = True
            continue

        return True

    if not has_letter:
        return True

    words = [
        _norm(word)
        for word in re.findall(
            r"[A-Za-zÀ-ÿ]+",
            raw,
        )
    ]
    counts: dict[str, int] = {}
    for word in words:
        if len(word) < 2:
            continue
        counts[word] = counts.get(word, 0) + 1
        if counts[word] >= 3:
            return True

    return False


def _is_portuguese_letter(
    char: str,
) -> bool:
    if "a" <= char <= "z" or "A" <= char <= "Z":
        return True

    if char in _PORTUGUESE_EXTRA_LETTERS:
        return True

    return False


def comment_is_eligible(
    text: object,
) -> bool:
    return not (
        has_user_mention(text)
        or has_disallowed_comment_content(text)
        or has_low_value_noise_pattern(text)
        or has_blocked_term(text)
    )
