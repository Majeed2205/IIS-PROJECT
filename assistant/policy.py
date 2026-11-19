"""The repair policy.  Status: implemented.

decide() applies the rules in docs/dialogue-spec.md. It takes what the caller
has asked for so far, the repair strategy and the calendar, and returns one
Action: what the assistant should do next and the words it should say.

decide() is a pure function. It never changes the calendar and never books
anything: a BOOK action is carried out by the conversation loop (chat.py),
which calls BookingDesk.book() and speaks describe(result).
A language model never decides what happens next; it may only fill in a
Request (step 4, planned).
"""
from __future__ import annotations

from dataclasses import dataclass

from .slots import DAYS, Calendar, Slot, spoken_time

STRATEGIES = ("repeat", "clarify", "summarise")

# The kinds of action decide() can return.
ASK = "ask"              # ask for one missing detail (rule 1)
ASK_AGAIN = "ask_again"  # repeat strategy: ask for the whole request again
CLARIFY = "clarify"      # offer the matching free slots and ask which one
CONFIRM = "confirm"      # read back service, day and time; wait for yes or no
BOOK = "book"            # book this slot now
DECLINE = "decline"      # nothing free matches, or the service is not offered
HANDOVER = "handover"    # repeat failed twice; hand over to staff (simulated)

MAX_REPEATS = 2   # still-ambiguous repeats before handing over
MAX_OPTIONS = 3   # spoken options in one turn
MAX_NEARBY = 2    # slots offered when declining

# "Time words" in the spec. Times are 24-hour "HH:MM", like the calendar.
DAY_PARTS = {
    "morning": ("00:00", "11:59"),
    "afternoon": ("12:00", "16:59"),
    "evening": ("17:00", "23:59"),
}


@dataclass(frozen=True)
class Request:
    """What the caller has asked for so far. None means "not said yet".

    The time is either exact (time="17:30") or a range. Both ends of a range
    are included, as in Calendar.find_free(). "After five" and "before five"
    both leave 5 pm out, so they are earliest="17:01" and latest="16:59".
    "Afternoon" is earliest, latest = DAY_PARTS["afternoon"].
    """
    service: str | None = None
    day: str | None = None
    time: str | None = None
    earliest: str | None = None
    latest: str | None = None


@dataclass(frozen=True)
class Action:
    kind: str                       # one of the kinds above
    say: str                        # the assistant's words; "" for BOOK, where
                                    # the loop speaks describe(result) instead
    slot: Slot | None = None        # for CONFIRM and BOOK: the chosen slot
    options: tuple[Slot, ...] = ()  # for CLARIFY and DECLINE: the slots offered
    detail: str | None = None       # for ASK: "day", "service" or "time"


def decide(request: Request, strategy: str, calendar: Calendar, repeats_asked: int = 0) -> Action:
    """Return the next action for this request.

    repeats_asked is how many times the repeat strategy has already asked the
    caller to say the whole request again during this call.
    """
    if strategy not in STRATEGIES:
        raise ValueError(f"Unknown strategy: {strategy!r}")

    service = _clean(request.service)
    day = _clean(request.day)

    # Rule 4, decline early: the salon does not offer this service.
    if service is not None and service not in calendar.services:
        return Action(DECLINE, f"Sorry, we don't offer {service}. We offer {_join(calendar.services)}.")

    # Rule 1: ask for the day first.
    if day not in DAYS:
        return Action(ASK, "Which day would you like to come in?", detail="day")

    # Rule 4, decline early: nothing free matches what has been said so far,
    # so decline before asking for the service or the time.
    earliest, latest = _time_range(request)
    matches = calendar.find_free(day, earliest, latest)
    if not matches:
        return _decline(calendar, day, earliest, latest)

    # Rule 1: then ask for the service, then the time.
    if service is None:
        return Action(ASK, f"What would you like to book? We offer {_join(calendar.services)}.", detail="service")
    if earliest is None and latest is None:
        return Action(ASK, f"What time on {day.capitalize()} would you like?", detail="time")

    # Rule 3: exactly one free slot matches.
    if len(matches) == 1:
        if strategy == "summarise":
            return _confirm(service, matches[0])
        return Action(BOOK, "", slot=matches[0])

    # Rule 2: more than one free slot matches, so the strategy decides.
    if strategy == "clarify":
        options = matches[:MAX_OPTIONS]
        when = _when(day, earliest, latest)
        return Action(CLARIFY, f"On {when} I have {_join_times(options)}. Which would you like?",
                      options=tuple(options))
    if strategy == "summarise":
        return _confirm(service, matches[0])  # the earliest match
    if repeats_asked >= MAX_REPEATS:
        return Action(HANDOVER, "I'm sorry, I couldn't find one time that fits. "
                                "I'll ask a member of staff to call you back.")
    return Action(ASK_AGAIN, "Sorry, could you say your whole request again?")


def _confirm(service: str, slot: Slot) -> Action:
    when = f"{slot.day.capitalize()} at {spoken_time(slot.time)}"
    return Action(CONFIRM, f"So that's a {service} on {when}. Is that right?", slot=slot)


def _decline(calendar: Calendar, day: str, earliest: str | None, latest: str | None) -> Action:
    said = f"I have nothing free on {_when(day, earliest, latest)}."
    options = _nearby(calendar, day, earliest, latest)
    if not options:
        return Action(DECLINE, f"{said} I have no free appointments this week.")
    offer_day = options[0].day.capitalize()
    offer = f"I can offer {offer_day} at {_join_times(options)}, or you can name another day."
    return Action(DECLINE, f"{said} {offer}", options=tuple(options))


def _nearby(calendar: Calendar, day: str, earliest: str | None, latest: str | None) -> list[Slot]:
    """Up to two free slots near what was asked for (spec rule 4).

    The closest free times on the same day; if that day has none, the first
    free slots on the next day that has any, wrapping round to Monday.
    """
    same_day = calendar.find_free(day)
    if same_day:
        closest = sorted(same_day, key=lambda s: _distance(s.time, earliest, latest))
        return sorted(closest[:MAX_NEARBY], key=lambda s: s.time)
    start = DAYS.index(day)
    for step in range(1, len(DAYS)):
        free = calendar.find_free(DAYS[(start + step) % len(DAYS)])
        if free:
            return free[:MAX_NEARBY]
    return []


def _time_range(request: Request) -> tuple[str | None, str | None]:
    """An exact time is treated as a range that starts and ends at that time."""
    if request.time is not None:
        return request.time, request.time
    return request.earliest, request.latest


def _when(day: str, earliest: str | None, latest: str | None) -> str:
    """Words for what the caller asked, e.g. "Friday at 7 pm" or "Saturday afternoon"."""
    day = day.capitalize()
    for name, (start, end) in DAY_PARTS.items():
        if (earliest, latest) == (start, end):
            return f"{day} {name}"
    if earliest is not None and earliest == latest:
        return f"{day} at {spoken_time(earliest)}"
    if earliest is not None and latest is not None:
        return f"{day} between {spoken_time(earliest)} and {spoken_time(latest)}"
    if earliest is not None:
        # earliest is included, so earliest="17:01" is spoken as "after 5 pm".
        return f"{day} after {spoken_time(_clock(_minutes(earliest) - 1))}"
    if latest is not None:
        # latest is included, so latest="16:59" is spoken as "before 5 pm".
        return f"{day} before {spoken_time(_clock(_minutes(latest) + 1))}"
    return day


def _distance(time: str, earliest: str | None, latest: str | None) -> int:
    """Minutes between a slot time and the range asked for (0 if inside it)."""
    t = _minutes(time)
    if earliest is not None and t < _minutes(earliest):
        return _minutes(earliest) - t
    if latest is not None and t > _minutes(latest):
        return t - _minutes(latest)
    return 0


def _minutes(time: str) -> int:
    """"17:30" -> 1050 minutes after midnight."""
    return int(time[:2]) * 60 + int(time[3:])


def _clock(minutes: int) -> str:
    """1050 minutes after midnight -> "17:30"."""
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _clean(text: str | None) -> str | None:
    """Lower-case and trim a word from the request; empty counts as not said."""
    if text is None or not text.strip():
        return None
    return text.strip().lower()


def _join(words: list[str]) -> str:
    """["a", "b", "c"] -> "a, b or c"."""
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " or " + words[-1]


def _join_times(slots: list[Slot] | tuple[Slot, ...]) -> str:
    return _join([spoken_time(s.time) for s in slots])
