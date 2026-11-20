"""Record the model's answers for replay mode.  Status: implemented (needs an API key).

Run once with your key in .env:  python -m assistant.record
Each sentence below goes to Claude Haiku 5.5 and its answer is saved in
data/replays.json, so anyone can replay them later without a key.
A sentence that is already saved is not sent again. To record again from
scratch, delete data/replays.json first, and always do that after changing
PROMPT in model.py. The output also shows each answer where the model left
out a detail and the keyword reader filled it in.
"""
from __future__ import annotations

from .model import ModelReader
from .slots import Calendar

# The test phrases from docs/dialogue-spec.md, then replies a caller often gives next.
PHRASES = [
    "A haircut on Friday at half five",
    "Can I come in on Friday after five?",
    "A haircut on Friday after five",
    "A haircut on Friday at seven",
    "Colour on Saturday afternoon",
    "A massage on Monday at eleven",
    "Sunday at ten for a haircut",
    "Sometime next week",
    "No, I said Thursday",
    "Yes",
    "Book it",
    "No",
    "Can I come in on Sunday?",
    "I'm busy at 5:30",
    "I'm busy",
    "Friday's fine",
    "5:30, no wait, 6:15",
    "I can't do Monday",
    "A haircut please",
    "the second one",
    "6:15",
    "4 pm",
    "a beard trim then",
    "the day",
    "the time",
    "No, wrong time",
    "Yes, 5:30 is fine",
    "after six",
    "Monday at 11",
    "Monday 11",
    "Good afternoon, can I book a haircut on Friday?",
    "Is 6:15 the latest?",
    "You said Friday?",
    "Thursday at 10 in the morning",
    # More phrases from the spec: rules 7 to 9 and the time words.
    "Is that Friday?",
    "Monday and Tuesday",
    "the first one",
    "the third one",
    "the first one after six",
    "yes, after six",
    "before five",
    "after 6:15",
    "Thursday morning",
    "in the evening",
    # From a chat in the terminal: a mistyped service and an hour on its own.
    "bread trim",
    "10",
    # Test phrase 20 and the request before it
    "A haircut on Tuesday at 6",
    "Thursday",
]


def main() -> None:
    reader = ModelReader()
    if not reader.live:
        print("Live calls are off. Put ANTHROPIC_API_KEY=... in .env (see .env.example), "
              "run pip install -r requirements.txt, then run this again.")
        return
    services = Calendar.load().services
    saved = filled = unsure = 0
    for text in PHRASES:
        heard = reader(text, services)
        key = " ".join(text.lower().split())
        if key in reader.replays:
            saved += 1
            said = {name: value for name, value in heard.items() if value is not None and value is not False and value != []}
            answer = reader.replays[key]
            added = filled_in(answer, heard)
            note = ""
            if added:
                filled += 1
                note = f"   <- the keyword reader filled in: {', '.join(added)}"
            elif answer.get("unclear") and not heard["unclear"]:
                unsure += 1
                note = "   <- the model was unsure; the keyword reader read it"
            print(f"{text!r:52} {said}{note}")
        else:
            print(f"{text!r:52} not saved: the call failed (see the [model] message)")
    print(f"\n{saved} of {len(PHRASES)} answers are saved in {reader.replay_path}")
    print(f"The keyword reader filled in a detail the model left out in {filled} of them.")
    print(f"The model was unsure about {unsure} that were only a time, and the keyword reader read them.")


def filled_in(answer: dict, heard: dict) -> list[str]:
    """The details the keyword reader added because the model left them out (see to_heard)."""
    if heard["unclear"] or answer.get("unclear"):
        return []  # an unsure answer left nothing out; main() reports a time-only turn on its own
    added = [name for name in ("service", "day", "choice") if not answer.get(name) and heard[name] is not None]
    # With no clock time from the model, an exact time came from the keyword reader,
    # and so did a range unless the model gave a part of the day ("afternoon").
    range_from_keywords = not answer.get("part_of_day") and (heard["earliest"] or heard["latest"])
    if not answer.get("time_kind") and (heard["time"] or range_from_keywords):
        added.append("time")
    if not answer.get("change") and heard["parts"]:
        added.append("parts")
    return added


if __name__ == "__main__":
    main()
