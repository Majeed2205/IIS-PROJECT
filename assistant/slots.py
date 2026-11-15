"""Salon availability.  Status: implemented (the calendar itself is a mock).

The calendar is the only source of truth for which appointment slots exist
and which are free. The assistant must look slots up here and never invent one.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "calendar.json"
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


@dataclass
class Slot:
    day: str    # lower-case weekday, e.g. "friday"
    time: str   # 24-hour "HH:MM", e.g. "17:30"
    free: bool = True


class Calendar:
    """One demo week of appointment slots for a fictional salon."""

    def __init__(self, services: list[str], slots: list[Slot]):
        self.services = [s.lower() for s in services]
        self.slots = slots

    @classmethod
    def load(cls, path: Path | str = DEFAULT_PATH) -> "Calendar":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        slots = []
        for raw in data["slots"]:
            day, time = raw["day"].lower(), raw["time"]
            if day not in DAYS:
                raise ValueError(f"Unknown day in calendar: {day!r}")
            if not _TIME.match(time):
                raise ValueError(f"Time must be 24-hour HH:MM, got {time!r}")
            slots.append(Slot(day, time, bool(raw.get("free", True))))
        return cls(data["services"], slots)

    def get(self, day: str, time: str) -> Slot | None:
        """Return the slot at this day and time, or None if the salon has no such slot."""
        day = day.strip().lower()
        for slot in self.slots:
            if slot.day == day and slot.time == time:
                return slot
        return None

    def find_free(self, day: str, earliest: str | None = None, latest: str | None = None) -> list[Slot]:
        """Free slots on a day, optionally limited to a time range (inclusive).

        "Friday after five" is find_free("friday", earliest="17:00").
        Zero-padded HH:MM strings sort correctly as text.
        """
        day = day.strip().lower()
        found = []
        for slot in self.slots:
            if slot.day != day or not slot.free:
                continue
            if earliest is not None and slot.time < earliest:
                continue
            if latest is not None and slot.time > latest:
                continue
            found.append(slot)
        return sorted(found, key=lambda s: s.time)


def spoken_time(time: str) -> str:
    """Turn "17:30" into "5:30 pm", the form a caller would hear."""
    hour, minute = int(time[:2]), time[3:]
    suffix = "am" if hour < 12 else "pm"
    hour12 = hour % 12 or 12
    return f"{hour12} {suffix}" if minute == "00" else f"{hour12}:{minute} {suffix}"
