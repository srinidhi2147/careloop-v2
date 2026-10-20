"""Plain data types shared by every layer. No framework or database imports here."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


class DoseStatus:
    PENDING = "pending"
    TAKEN = "taken"
    MISSED = "missed"


class AlertLevel:
    INFO = "info"
    URGENT = "urgent"


class ValidationError(ValueError):
    """Raised when caller input is invalid. The API maps it to HTTP 400."""


@dataclass(frozen=True)
class Dose:
    id: int
    name: str
    strength: str
    time: str
    instructions: str
    status: str
    at: str

    @property
    def label(self) -> str:
        return f"{self.name} {self.strength}".strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Alert:
    id: int
    level: str
    text: str
    at: str
    resolved: bool


@dataclass(frozen=True)
class Appointment:
    id: int
    time: str
    title: str


@dataclass(frozen=True)
class PrescriptionItem:
    name: str
    times: list[str]
    strength: str = ""
    instructions: str = ""


@dataclass(frozen=True)
class ExtractedMedicine:
    name: str
    strength: str
    frequency: str
    times: list[str]
    instructions: str
    confidence: float
    needs_review: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Reply:
    """Result of a voice-style action. `speech` is what Alexa+ reads aloud."""

    ok: bool
    speech: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "speech": self.speech, **self.data}


@dataclass(frozen=True)
class Summary:
    text: str
    source: str  # "ai" or "template"
