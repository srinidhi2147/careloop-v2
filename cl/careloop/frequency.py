"""Turn prescription shorthand (1-0-1, BD, TDS...) into clock times. Pure functions."""
from __future__ import annotations

import re

TIME_RE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")

_NAMED = {
    "OD": ["09:00"], "QD": ["09:00"],
    "BD": ["08:00", "20:00"], "BID": ["08:00", "20:00"],
    "TDS": ["08:00", "14:00", "20:00"], "TID": ["08:00", "14:00", "20:00"],
    "QID": ["08:00", "12:00", "16:00", "20:00"],
    "HS": ["22:00"], "NOCTE": ["22:00"],
}
_SLOTS = ("08:00", "14:00", "21:00")  # morning, afternoon, night for patterns like 1-0-1
_PATTERN = re.compile(r"([0-9])-([0-9])-([0-9])")


def times_from_frequency(frequency: str) -> list[str]:
    """Return dose times for a frequency string, or [] when it cannot be scheduled
    (for example SOS/PRN or free text). The caregiver sets those on the review screen."""
    key = (frequency or "").strip().upper().replace(" ", "")
    if key in _NAMED:
        return list(_NAMED[key])
    match = _PATTERN.fullmatch(key)
    if match:
        return [slot for slot, count in zip(_SLOTS, match.groups(), strict=True) if count != "0"]
    return []
