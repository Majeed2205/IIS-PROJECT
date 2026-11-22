"""The conversation loop. Keeps track of the call from turn to turn.

Status: implemented. Typed input in the terminal:  python -m assistant.chat clarify
The terminal uses the model reader (model.py); the tests use the keyword reader.
With --mishear the planted-error switch (mishear.py, simulated) mishears one time.
"""
from __future__ import annotations

import sys
from dataclasses import replace

from .booking import BOOKED, BookingDesk, describe
from .mishear import misheard_time
from .model import ModelReader
from .policy import ASK_AGAIN, BOOK, CONFIRM, DECLINE, HANDOVER, STRATEGIES, Request, decide
from .slots import Calendar
from .understand import unclear, understand

WHICH_PART = "Which part should I change: the service, the day or the time?"
GIVE_UP = "I'm sorry, I'm having trouble understanding. I'll ask a member of staff to call you back."
MAX_NOT_UNDERSTOOD = 3  # turns in a row before handing over (simulated, like the repeat handover)


class Conversation:
    def __init__(self, calendar: Calendar, strategy: str, call_id: str = "call-1", reader=understand,
                 mishear: bool = False):
        if strategy not in STRATEGIES:
            raise ValueError(f"Unknown strategy: {strategy!r}")
        self.reader = reader  # turns the caller's words into details
        self.mishear = mishear  # the planted-error switch (step 5, simulated)
        self.misheard = None    # (said, heard) once a time has been misheard
        self.calendar = calendar
        self.desk = BookingDesk(calendar)
        self.strategy = strategy
        self.call_id = call_id
        self.request = Request()
        self.last_action = None
        self.asked_which_part = False
        self.repeats_asked = 0
        self.not_understood = 0  # turns in a row we could not understand
        self.booking = None    # the BookingResult once the caller is booked
        self.finished = False  # True after a handover
        self.offered = ()      # the slots the last decline offered

    def reply(self, text: str) -> str:
        """Take one caller turn and return what the assistant says."""
        if self.finished:
            return "This call has ended."

        first_turn = self.request == Request()  # the caller has not asked for anything yet
        heard = self.reader(text, self.calendar.services, first_turn)

        # Already booked: saying "yes" or "book it" again must not book twice.
        if self.booking is not None:
            if heard["yes"]:
                return self.book(self.booking.day, self.booking.time)
            return "You're all booked. Thank you for calling."

        last = self.last_action
        after_read_back = last is not None and last.kind == CONFIRM

        # Outside a read-back, "no 5:30" may mean "not 5:30", so ignore it and ask again.
        if heard["no"] and not after_read_back and not self.asked_which_part:
            heard = understand("", self.calendar.services)
            heard["unclear"] = True
        # Rule 8: a pick by place needs a slot to pick ("the first one" with nothing offered, "the third one"
        # after two). Only the pick is left out, so a time said with it still decides ("the first one after six").
        options = last.options if last is not None else ()
        if heard["choice"] is not None and heard["choice"] >= len(options):
            heard = dict(heard, choice=None)
            if not has_details(heard):
                heard = unclear(heard)  # keeps a "no", so after a read-back it still gets rule 6

        # Step 5 (simulated): after the line above, so a turn that is thrown away does not use it up,
        # and not in an answer to a read-back, so summarise never books a time it has not read back.
        if self.mishear and self.misheard is None and heard["time"] and not after_read_back:
            heard = self.plant_error(heard)

        # Answer to a read-back (summarise).
        if after_read_back:
            if heard["yes"] and agrees(heard, last.slot, self.request.service):
                return self.book(last.slot.day, last.slot.time)
            # Rule 6: a "no" that does not say what is wrong ("No", "I can't do Monday"), or only names
            # what is right ("No, Friday's fine"). "No, wrong time" is handled below.
            same = agrees(heard, last.slot, self.request.service)
            if heard["no"] and not heard["parts"] and (not has_details(heard) or same):
                self.last_action = None
                self.asked_which_part = True
                if heard["unclear"]:
                    return self.count_and_ask(WHICH_PART)  # "I can't do Monday" still counts (rule 7)
                self.not_understood = 0
                return WHICH_PART

        old_request = self.request
        self.update_request(heard)
        # Rule 6: after "Which part?", a turn that names no part and changes nothing gets the question again:
        # one with no detail ("No", "Yes"), or a "no" that only names what is right ("No, Friday's fine").
        if self.asked_which_part and not heard["parts"] and self.request == old_request:
            if heard["no"] or not has_details(heard):
                return self.count_and_ask(("Sorry, I didn't catch that. " if heard["unclear"] else "") + WHICH_PART)
        self.asked_which_part = False
        missed = heard["unclear"] and self.request == old_request  # rule 7: not understood, so nothing changed

        # Rule 7: a turn not understood is not a repeat, so with 0 repeats decide() never hands over for it.
        action = decide(self.request, self.strategy, self.calendar, 0 if missed else self.repeats_asked)
        # Rule 8: the slots a decline offered can still be picked when we ask for the time that day,
        # even after another question ("What would you like to book?") in between.
        if action.kind == DECLINE and action.options:  # "we don't offer massage" keeps the slots
            self.offered = action.options
        if action.detail == "time" and self.offered and all(slot.day == self.request.day for slot in self.offered):
            action = replace(action, options=self.offered)
        self.last_action = action
        if action.kind == BOOK:
            return self.book(action.slot.day, action.slot.time)
        if action.kind == ASK_AGAIN and not missed:
            self.repeats_asked += 1
        if action.kind == HANDOVER:
            self.finished = True
            return action.say

        # Rule 7: the last turn was not understood, so nothing changed.
        if missed:
            if action.kind == ASK_AGAIN:  # under repeat, the normal ask-again question
                return self.count_and_ask(action.say)
            return self.count_and_ask("Sorry, I didn't catch that. " + action.say)
        self.not_understood = 0
        return action.say

    def count_and_ask(self, say: str) -> str:
        """Count a turn that got nowhere (rules 6 and 7), and hand over after three in a row."""
        self.not_understood += 1
        if self.not_understood >= MAX_NOT_UNDERSTOOD:
            self.finished = True
            return GIVE_UP
        return say

    def update_request(self, heard: dict) -> None:
        """Change only the details the caller just gave (rule 5), and forget details when rule 4 or 6 says so."""
        request = self.request
        has_time = heard["time"] or heard["earliest"] or heard["latest"]

        if heard["service"]:
            request = replace(request, service=heard["service"])
        if heard["day"]:
            request = replace(request, day=heard["day"])
        if has_time:
            request = replace(request, time=heard["time"], earliest=heard["earliest"], latest=heard["latest"])

        # "the day" (after "which part?") or "no, wrong day": forget it so it gets asked again.
        if self.asked_which_part or heard["no"]:
            if "service" in heard["parts"] and not heard["service"]:
                request = replace(request, service=None)
            if "day" in heard["parts"] and not heard["day"]:
                request = replace(request, day=None)
            if "time" in heard["parts"] and not has_time:
                request = replace(request, time=None, earliest=None, latest=None)

        # Rule 4: after a decline, naming the offered day without a time ("Thursday") forgets a time
        # that is not free that day, so rule 1 asks for what is missing instead of declining again.
        offered_days = []
        if self.last_action is not None and self.last_action.kind == DECLINE:
            offered_days = [slot.day for slot in self.last_action.options]
        if heard["day"] in offered_days and not has_time:
            earliest = request.time or request.earliest
            latest = request.time or request.latest
            if not self.calendar.find_free(heard["day"], earliest, latest):
                request = replace(request, time=None, earliest=None, latest=None)

        # Picking one of the slots we just offered, e.g. "6:15", "the second one" or "4 pm".
        slot = self.pick_option(heard)
        if slot is not None:
            request = replace(request, day=slot.day, time=slot.time, earliest=None, latest=None)

        self.request = request

    def pick_option(self, heard: dict):
        """Return the offered slot the caller chose, or None."""
        if self.last_action is None or not self.last_action.options:
            return None
        options = self.last_action.options

        # If a time was said too ("the first one after six"), the time decides.
        has_time = heard["time"] or heard["earliest"] or heard["latest"]
        choice = heard["choice"]
        if choice is not None and not has_time and choice < len(options) and heard["day"] in (None, options[choice].day):
            return options[choice]
        if heard["time"] is not None:
            matches = [s for s in options if s.time == heard["time"] and heard["day"] in (None, s.day)]
            if len(matches) == 1:
                return matches[0]
        if heard["yes"] and not has_time and len(options) == 1 and heard["day"] in (None, options[0].day):
            return options[0]
        return None

    def plant_error(self, heard: dict) -> dict:
        """Hear the time as the nearest other free time that day (only once per call)."""
        day = heard["day"] or self.request.day
        wrong = misheard_time(heard["time"], day, self.calendar)
        if wrong is None:
            return heard  # no day yet, or nothing else free that day: wait for the next time
        self.misheard = (heard["time"], wrong)
        return dict(heard, time=wrong)

    def book(self, day: str, time: str) -> str:
        """Book through the booking desk and say what really happened."""
        # Same call and same slot gives the same id, so a repeat is never booked twice.
        request_id = f"{self.call_id}-{day}-{time}"
        result = self.desk.book(request_id, self.request.service, day, time)
        if result.status == BOOKED:
            self.booking = result
        return describe(result)


def has_details(heard: dict) -> bool:
    keys = ("service", "day", "time", "earliest", "latest", "choice")
    return any(heard[key] is not None for key in keys)


def agrees(heard: dict, slot, service: str) -> bool:
    """True if nothing the caller said goes against the read-back."""
    if heard["service"] not in (None, service):
        return False
    if heard["day"] not in (None, slot.day):
        return False
    if heard["time"] not in (None, slot.time):
        return False
    if heard["earliest"] is not None and slot.time < heard["earliest"]:
        return False
    if heard["latest"] is not None and slot.time > heard["latest"]:
        return False
    return heard["choice"] is None and not heard["parts"]


def read_args(args: list[str]) -> tuple[str, bool]:
    """The strategy (clarify if none is given) and whether --mishear was given."""
    words = [arg for arg in args if arg != "--mishear"]
    return (words[0] if words else "clarify"), "--mishear" in args


def main() -> None:
    strategy, mishear = read_args(sys.argv[1:])
    if strategy not in STRATEGIES:
        print("Usage: python -m assistant.chat [repeat | clarify | summarise] [--mishear]")
        return

    reader = ModelReader()
    chat = Conversation(Calendar.load(), strategy, reader=reader, mishear=mishear)
    print(f"Demo Salon booking assistant ({strategy}). Type 'quit' to stop.")
    if mishear:
        print("Planted-error switch: on. One time you say will be misheard (simulated).")
    if reader.live:
        print("Understanding: Claude Haiku 5.5 (live). New answers are saved in data/replays.json.")
    else:
        print("Understanding: replay mode (no live calls). Saved model answers are used, "
              "and any other sentence goes to the simple keyword reader (simulated).")
    print("Assistant: Hello, Demo Salon. How can I help?")
    while not chat.finished:
        try:
            text = input("You: ")
        except EOFError:
            break
        if text.strip().lower() in ("quit", "exit"):
            break
        print("Assistant:", chat.reply(text))


if __name__ == "__main__":
    main()
