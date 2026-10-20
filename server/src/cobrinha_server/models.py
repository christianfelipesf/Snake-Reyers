from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SegmentKind = Literal[
    "speech",
    "micro_pause",
    "pause",
]

VocalMode = Literal[
    "idle",
    "speech",
    "singing",
]


@dataclass(frozen=True)
class MicroSegment:
    kind: SegmentKind
    start: float
    end: float
    duration: float
    energy: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SpeechJob:
    id: str
    text: str
    audio_path: str = ""
    timeline_path: str = ""
    priority: int = 40
    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "audio_path": self.audio_path,
            "timeline_path": self.timeline_path,
            "priority": self.priority,
            "metadata": dict(self.metadata),
        }
