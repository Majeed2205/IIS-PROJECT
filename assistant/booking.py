"""The booking function.  Status: implemented.

This is the only code that changes the calendar. It returns a BookingResult
saying what actually happened, and describe() turns that result into the
sentence the caller hears. The spoken status is therefore built from the
return value, not from anything a language model says.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .slots import Calendar, spoken_time

BOOKED = "booked"
SLOT_TAKEN = "slot_taken"
NO_SUCH_SLOT = "no_such_slot"
UNKNOWN_SERVICE = "unknown_service"


@dataclass(frozen=True)
class BookingResult:
    status: str          # BOOKED, SLOT_TAKEN, NO_SUCH_SLOT or UNKNOWN_SERVICE
    service: str
    day: str
    time: str
    repeat: bool = False  # True when the same request was sent again


class BookingDesk:
    """Books slots in a Calendar and remembers each request it has handled."""

    def __init__(self, calendar: Calendar):
        self.calendar = calendar
        self._handled: dict[str, BookingResult] = {}

    def book(self, request_id: str, service: str, day: str, time: str) -> BookingResult:
        """Try to book one slot.

        request_id identifies one booking attempt. Sending the same request_id
        again returns the first result with repeat=True and changes nothing,
        so a caller who repeats themselves is never booked twice.
        """
        if request_id in self._handled:
            return replace(self._handled[request_id], repeat=True)

        service, day = service.strip().lower(), day.strip().lower()
        slot = self.calendar.get(day, time)

        if service not in self.calendar.services:
            status = UNKNOWN_SERVICE
        elif slot is None:
            status = NO_SUCH_SLOT
        elif not slot.free:
            status = SLOT_TAKEN
        else:
            slot.free = False
            status = BOOKED

        result = BookingResult(status, service, day, time)
        self._handled[request_id] = result
        return result


def describe(result: BookingResult) -> str:
    """The status sentence for the caller, built only from the booking result."""
    when = f"{result.day.capitalize()} at {spoken_time(result.time)}"
    if result.status == BOOKED:
        if result.repeat:
            return f"Your {result.service} is already booked for {when}. I have not booked it twice."
        return f"Booked: {result.service} on {when}."
    if result.status == SLOT_TAKEN:
        return f"Not booked: {when} is already taken."
    if result.status == NO_SUCH_SLOT:
        return f"Not booked: the salon has no appointment slot on {when}."
    if result.status == UNKNOWN_SERVICE:
        return f"Not booked: the salon does not offer {result.service}."
    raise ValueError(f"Unknown booking status: {result.status!r}")
