"""Nebius Token Factory adapters (NVIDIA Nemotron). The service depends on small protocols, so tests use fakes."""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any, Protocol

from .config import Settings
from .frequency import TIME_RE, times_from_frequency
from .models import ExtractedMedicine

log = logging.getLogger("careloop.ai")

PROMPT = """You read medical prescriptions. Return JSON only, with no other text:
{"medicines":[{"name":"","strength":"","frequency":"","times":[],"instructions":"","confidence":0.0}]}
Rules:
- name is the medicine name only. Use the key "name".
- strength includes the unit if written (for example 500 mg).
- frequency is exactly what is written (for example 1-0-1, BD, TDS, once daily).
- times only if explicit clock times are written, as HH:MM in 24-hour format.
- confidence is 0 to 1 for how sure you are of that line.
- Use an empty string for anything unreadable. Never guess a medicine name."""

SAMPLE_OUTPUT = json.dumps({"medicines": [
    {"name": "Metformin", "strength": "500 mg", "frequency": "1-0-1", "times": [],
     "instructions": "after food", "confidence": 0.95},
    {"name": "Amlodipine", "strength": "5 mg", "frequency": "OD", "times": [],
     "instructions": "", "confidence": 0.9},
    {"name": "Pantoprazole", "strength": "40 mg", "frequency": "before breakfast", "times": [],
     "instructions": "empty stomach", "confidence": 0.6},
]})

_IMAGE_TYPES = {"image/png": "image/png", "image/jpeg": "image/jpeg",
                "image/jpg": "image/jpeg", "image/webp": "image/webp"}


class PrescriptionReader(Protocol):
    def read(self, data: bytes, content_type: str) -> list[ExtractedMedicine]: ...


def _clean(raw: str) -> str:
    """Drop any <think> block the reasoning model may emit."""
    return re.sub(r"<think>.*?</think>", "", raw or "", flags=re.S).strip()


def parse_model_output(raw: str) -> list[ExtractedMedicine]:
    """Pure function: model text in, checked medicines out. Anything uncertain is flagged."""
    raw = _clean(raw)
    starts = [i for i in (raw.find("{"), raw.find("[")) if i >= 0]
    if not starts:
        raise ValueError("The model did not return readable data. Try a clearer photo.")
    start = min(starts)
    end = raw.rfind("}" if raw[start] == "{" else "]")
    try:
        data = json.loads(raw[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("The model did not return readable data. Try a clearer photo.") from exc
    items = data if isinstance(data, list) else data.get("medicines", [])
    out: list[ExtractedMedicine] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("medicine") or "").strip()
        frequency = str(item.get("frequency") or item.get("timing") or "").strip()
        raw_times = item.get("times") if isinstance(item.get("times"), list) else []
        explicit = [str(t) for t in raw_times if TIME_RE.fullmatch(str(t))]
        times = explicit or times_from_frequency(frequency)
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        out.append(ExtractedMedicine(
            name=name,
            strength=str(item.get("strength", "")).strip(),
            frequency=frequency,
            times=times,
            instructions=str(item.get("instructions", "")).strip(),
            confidence=confidence,
            needs_review=confidence < 0.8 or not name or not times,
        ))
    return out


class MockReader:
    """Offline demo reader: always returns the same sample prescription."""

    def read(self, data: bytes, content_type: str) -> list[ExtractedMedicine]:
        return parse_model_output(SAMPLE_OUTPUT)


class UnconfiguredReader:
    def read(self, data: bytes, content_type: str) -> list[ExtractedMedicine]:
        raise RuntimeError("Set NEBIUS_API_KEY, or set USE_MOCK_AI=1 to demo without the AI.")


class NebiusClient:
    """Reads prescriptions and writes summaries with NVIDIA Nemotron on Nebius Token Factory."""

    def __init__(self, api_key: str, base_url: str, model_id: str, client: Any = None) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._model_id = model_id
        self._client = client

    def _api(self) -> Any:
        if self._client is None:
            from openai import OpenAI  # lazy: tests and mock mode do not need it

            self._client = OpenAI(base_url=self._base_url, api_key=self._api_key, timeout=90)
        return self._client

    def read(self, data: bytes, content_type: str) -> list[ExtractedMedicine]:
        if content_type not in _IMAGE_TYPES:
            raise ValueError("Upload a PNG, JPEG or WEBP photo of the prescription.")
        url = f"data:{_IMAGE_TYPES[content_type]};base64,{base64.b64encode(data).decode()}"
        last_error: ValueError | None = None
        for attempt, temperature in ((1, 0.0), (2, 0.3)):
            try:
                response = self._api().chat.completions.create(
                    model=self._model_id,
                    messages=[{"role": "user", "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image_url", "image_url": {"url": url}},
                    ]}],
                    max_tokens=8000,
                    temperature=temperature,
                )
            except Exception as exc:
                log.warning("Nebius prescription read failed", exc_info=True)
                raise RuntimeError("The AI service could not be reached. Try again in a moment.") from exc
            choice = response.choices[0]
            text = choice.message.content or ""
            try:
                return parse_model_output(text)
            except ValueError as exc:
                last_error = exc
                log.warning(
                    "Nebius output not parseable (attempt %d, finish_reason=%s, length=%d): %.300s",
                    attempt, choice.finish_reason, len(text), text,
                )
        assert last_error is not None
        raise last_error

    def generate(self, prompt: str) -> str | None:
        """Return text, or None on any failure so callers can fall back to a template."""
        try:
            response = self._api().chat.completions.create(
                model=self._model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1500,
                temperature=0.3,
            )
            text = _clean(response.choices[0].message.content or "")
            return text or None
        except Exception:
            log.warning("Nebius text generation failed", exc_info=True)
            return None


def build_ai(settings: Settings) -> tuple[PrescriptionReader, NebiusClient | None]:
    if settings.use_mock_ai:
        return MockReader(), None
    if settings.nebius_api_key:
        client = NebiusClient(settings.nebius_api_key, settings.nebius_base_url,
                              settings.nebius_model_id)
        return client, client
    return UnconfiguredReader(), None