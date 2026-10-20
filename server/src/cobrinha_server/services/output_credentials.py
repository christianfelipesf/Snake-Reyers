from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from cobrinha_server.services.output_redaction import (
    public_destination,
)


class OutputCredentialError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class OutputCredential:
    destination_url: str
    provider: str = "manual"
    session_id: str = ""
    title: str = ""
    category: str = ""
    created_at: float = 0.0
    expires_at: float = 0.0

    def public_info(
        self,
    ) -> dict[str, Any]:
        return {
            "provider":
                str(self.provider),
            "session_id":
                str(self.session_id),
            "title":
                str(self.title),
            "category":
                str(self.category),
            "created_at":
                float(self.created_at),
            "expires_at":
                float(self.expires_at),
            "destination":
                public_destination(
                    self.destination_url
                ),
        }


class OutputCredentialProvider(
    Protocol
):
    def acquire(
        self,
        *,
        title: str = "",
        category: str = "",
    ) -> OutputCredential:
        ...


def from_parts(
    *,
    base_url: str,
    access_key: str,
    provider: str = "manual",
    session_id: str = "",
    title: str = "",
    category: str = "",
    created_at: float = 0.0,
    expires_at: float = 0.0,
) -> OutputCredential:
    base = str(
        base_url or ""
    ).strip().rstrip("/")

    key = str(
        access_key or ""
    ).strip().lstrip("/")

    if not base:
        raise OutputCredentialError(
            "Base de destino vazia."
        )

    if not key:
        raise OutputCredentialError(
            "Chave de acesso vazia."
        )

    return OutputCredential(
        destination_url=(
            base
            + "/"
            + key
        ),
        provider=str(
            provider or "manual"
        ),
        session_id=str(
            session_id or ""
        ),
        title=str(
            title or ""
        ),
        category=str(
            category or ""
        ),
        created_at=float(
            created_at or 0.0
        ),
        expires_at=float(
            expires_at or 0.0
        ),
    )
