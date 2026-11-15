"""A short walk through the calendar, booking function and repair policy.  Status: implemented.

Run from the repository root:  python -m assistant.demo
"""
from __future__ import annotations

from .booking import BookingDesk, describe
from .policy import STRATEGIES, Request, decide
from .slots import Calendar, spoken_time


def main() -> None:
    calendar = Calendar.load()
    desk = BookingDesk(calendar)

    print('Caller: "Can I come in on Friday after five?"')
    options = calendar.find_free("friday", earliest="17:00")
    print("Free slots found:", ", ".join(spoken_time(s.time) for s in options))

    print("\nBook a haircut on Friday at 5:30 pm:")
    print(" ", describe(desk.book("call-1", "haircut", "friday", "17:30")))

    print("\nThe caller repeats the same request:")
    print(" ", describe(desk.book("call-1", "haircut", "friday", "17:30")))

    print("\nA different caller asks for the slot that was already taken:")
    print(" ", describe(desk.book("call-2", "colour", "friday", "19:00")))

    print("\nSaturday afternoon:")
    saturday = calendar.find_free("saturday", earliest="12:00")
    print("  Free slots found:", len(saturday), "(the assistant must decline, not invent one)")

    print('\nRepair policy, fresh calendar. Caller: "A haircut on Friday after five"')
    request = Request(service="haircut", day="friday", earliest="17:00")
    for strategy in STRATEGIES:
        action = decide(request, strategy, Calendar.load())
        print(f"  {strategy:<9} -> {action.kind}: {action.say}")


if __name__ == "__main__":
    main()
