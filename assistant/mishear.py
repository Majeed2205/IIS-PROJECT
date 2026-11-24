"""The planted-error switch (step 5): the assistant mishears one time on purpose.

Status: simulated. It stands in for a speech recogniser that gets a detail wrong,
so the study can show which repair strategy catches the mistake. It is off unless
switched on (python3 -m assistant.chat summarise --mishear).
"""
from __future__ import annotations


def misheard_time(time: str, day: str | None, calendar) -> str | None:
    """The nearest other free time on that day, or None if there is none.

    "17:30" on Friday is heard as "18:15". On a tie the earlier time is used.
    """
    if day is None:
        return None
    others = [slot.time for slot in calendar.find_free(day) if slot.time != time]
    if not others:
        return None
    return min(others, key=lambda other: (abs(minutes(other) - minutes(time)), other))


def minutes(time: str) -> int:
    """Minutes after midnight: "17:30" is 1050."""
    return int(time[:2]) * 60 + int(time[3:])
