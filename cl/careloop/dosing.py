"""Turn dosage text such as "1 tablet 1-1-1 (Thrice daily / TDS)" into clock times.

These are standard slots, not times written on the prescription."""
from __future__ import annotations

import re

MORNING, AFTERNOON, EVENING, NIGHT = "08:00", "14:00", "18:00", "21:00"

_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2})\s*[-–]\s*(\d{1,2})\s*[-–]\s*(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?(?!\d)"
)


def times_from_text(text: str) -> list[str]:
    t = (text or "").lower()
    m = _PATTERN.search(t)
    if m:
        counts = [int(g) for g in m.groups() if g is not None]
        slots = [MORNING, AFTERNOON, NIGHT] if len(counts) == 3 else [MORNING, AFTERNOON, EVENING, NIGHT]
        return [slot for slot, n in zip(slots, counts) if n > 0]
    if re.search(r"\b(qid|q\.?i\.?d|four times|4 times)\b", t):
        return [MORNING, AFTERNOON, EVENING, NIGHT]
    if re.search(r"\b(tds|tid|t\.?i\.?d|thrice|three times|3 times)\b", t):
        return [MORNING, AFTERNOON, NIGHT]
    if re.search(r"\b(bd|bid|b\.?i\.?d|twice|two times|2 times)\b", t):
        return [MORNING, NIGHT]
    if re.search(r"\b(hs|bedtime|at night|night)\b", t):
        return [NIGHT]
    if re.search(r"\b(od|qd|once|morning|daily|one time|1 time)\b", t):
        return [MORNING]
    return []