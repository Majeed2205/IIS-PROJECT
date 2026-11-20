"""The understanding step: Claude Haiku 5.5 turns the caller's words into details.

Status: implemented. A live call needs an API key in .env (see .env.example)
and the anthropic package (pip install -r requirements.txt).

Without a key it runs in replay mode: it uses answers the model gave before,
saved in data/replays.json. A sentence with no saved answer, or a live call
that fails, goes to the simple keyword reader in understand.py (simulated).
The keyword reader also fills in a detail the model left out, when it knows
every word of the turn (see to_heard).

The model only fills in what the caller said. It never decides what the
assistant does next: that is decide() in policy.py.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from .policy import DAY_PARTS
from .slots import DAYS
from .understand import CHOICES, YES_WORDS, understand, unclear

MODEL = "claude-haiku-5-5"
ROOT = Path(__file__).resolve().parent.parent
REPLAY_PATH = ROOT / "data" / "replays.json"
ENV_PATH = ROOT / ".env"

# The shape of every answer. An empty string, false or [] means "not said".
SCHEMA = {
    "type": "object",
    "properties": {
        "service": {"type": "string"},
        "day": {"type": "string", "enum": DAYS + [""]},
        "time_kind": {"type": "string", "enum": ["at", "after", "before", ""]},
        "clock": {"type": "string"},
        "part_of_day": {"type": "string", "enum": ["morning", "afternoon", "evening", ""]},
        "choice": {"type": "string", "enum": ["first", "second", "third", ""]},
        "yes": {"type": "boolean"},
        "no": {"type": "boolean"},
        "change": {"type": "array", "items": {"type": "string", "enum": ["service", "day", "time"]}},
        "unclear": {"type": "boolean"},
    },
    "required": ["service", "day", "time_kind", "clock", "part_of_day", "choice", "yes", "no", "change", "unclear"],
    "additionalProperties": False,
}

PROMPT = """You read one thing a caller said to a hair salon's phone booking assistant and fill in the fields.
Only report what the caller said. Leave a field empty ("", false or []) if they did not say it.
You never decide what the assistant does next.

The salon's services are: {services}. If the caller asks for one of them, use exactly that name.
If they ask for something else, such as a massage, write what they asked for in one or two words.

service: the service asked for.
day: the weekday asked for.
time_kind and clock: "at" for an exact time ("at half five" is at 17:30), "after" for "after five"
(after 17:00), "before" for "before twelve" (before 12:00). Write clock as 24-hour HH:MM.
The salon is open 9 am to 7 pm, so an hour from 1 to 8 with no am or pm means the afternoon or
evening ("five" is 17:00), and 9, 10 or 11 mean the morning. A number on its own, or with "please"
or "then", is a time ("seven", "6:15 then").
part_of_day: "morning", "afternoon" or "evening" if the caller asks for one ("Saturday afternoon").
A greeting such as "Good afternoon" is not a time.
choice: "first", "second" or "third" if the caller picks an option by its place ("the second one").
yes: true only if the caller agrees, as in "yes", "that's right" or "book it".
no: true if the caller says no to what they were told, as in "No" or "No, I said Thursday".
A yes, a no or a choice can come with details. Fill those in too, so they can be checked against
what the caller was told: "No, I meant Tuesday" also has day "tuesday", "Yes, 4:15 is good"
also has time_kind "at" and clock "16:15", and "the third one before noon" also has time_kind
"before" and clock "12:00".
change: the parts the caller says are wrong or wants to change ("No, wrong time" is ["time"],
"the day" is ["day"]). A reply that only names a part is clear: "the service" is ["service"].
"Can I come in on Friday after five?" is a request, not a question.

unclear: set this to true, and leave the other fields empty, if the caller
- turns something down or says what they cannot do ("I'm busy at 5:30", "not Friday"),
- asks about something instead of asking for it ("is that Friday?"),
- names two different values for the same thing ("Monday and Tuesday"), or changes their mind
  within the sentence ("5:30, no wait, 6:15"),
- gives a number with no word that makes it a time ("Monday 11"),
- asks for a day or time that is not a weekday or a clock time ("sometime next week", "tomorrow"),
- or says anything else you are not sure about."""


class ModelReader:
    """Reads one caller turn: a saved answer, else the model, else the keyword reader."""

    def __init__(self, live: bool | None = None, replay_path: Path = REPLAY_PATH, ask=None):
        self.replay_path = Path(replay_path)
        self.replays = load_replays(self.replay_path)
        self.live = has_key() if live is None else live
        self.ask = ask if ask is not None else ask_model
        if self.live and ask is None and importlib.util.find_spec("anthropic") is None:
            warn("The anthropic package is not installed (pip install -r requirements.txt), so replay mode is used.")
            self.live = False

    def __call__(self, text: str, services: list[str], first_turn: bool = False) -> dict:
        key = " ".join(text.lower().split())
        answer = self.replays.get(key)
        if answer is None and self.live and key:
            answer = self.ask(text, services)
            if answer is not None:
                self.replays[key] = answer
                save_replays(self.replays, self.replay_path)
        if answer is None:
            return understand(text, services, first_turn)  # the simple keyword reader
        return to_heard(answer, text, services)


def to_heard(answer: dict, text: str, services: list[str]) -> dict:
    """Turn the model's answer into the same details the keyword reader gives.

    The answer is checked like any other input: anything odd means "not understood".
    A turn that is not understood is checked for a "no" word ("I can't do Monday") and a part
    the same way as in the keyword reader, so both readers give the same reply (rule 6).
    """
    words_heard = understand(text, services, first_turn=True)  # "Morning!" at the start is a greeting
    not_understood = unclear(dict(words_heard))
    heard = understand("", services)  # every detail empty
    flags = [answer.get("yes"), answer.get("no"), answer.get("unclear")]
    change = answer.get("change")
    if not all(isinstance(flag, bool) for flag in flags) or not isinstance(change, list):
        return not_understood
    heard["no"] = answer["no"]
    heard["parts"] = [part for part in change if part in ("service", "day", "time")]
    if answer["unclear"] or (answer["yes"] and answer["no"]):  # "yeah no" is not clear either
        return not_understood

    service = answer.get("service")
    day = answer.get("day")
    choice = answer.get("choice")
    kind = answer.get("time_kind")
    clock = answer.get("clock")
    part = answer.get("part_of_day")
    if not isinstance(service, str) or len(service) > 30:
        return not_understood
    if service and not service.replace(" ", "").isalpha():
        return not_understood  # a service is a word or two, like "beard trim"
    if day not in DAYS + [""] or choice not in list(CHOICES) + [""] or part not in list(DAY_PARTS) + [""]:
        return not_understood
    if kind not in ("at", "after", "before", "") or (kind and not is_clock(clock)):
        return not_understood

    heard["service"] = service.strip().lower() or None
    heard["day"] = day or None
    heard["choice"] = CHOICES[choice] if choice else None

    # The time words in the spec: "after five" leaves 5 pm out (17:01), so does "before".
    if kind == "at":
        heard["time"] = clock
    elif kind == "after":
        heard["earliest"] = shift(clock, 1)
    elif kind == "before":
        heard["latest"] = shift(clock, -1)

    if part:
        start, end = DAY_PARTS[part]
        if kind == "":
            heard["earliest"], heard["latest"] = start, end
        elif kind != "at" or not start <= clock <= end:
            return not_understood  # "at 10 in the morning" fits, "after 6 in the morning" does not

    # The model can leave out one detail of a turn with two parts ("the first one after six").
    # If the keyword reader understands the whole turn, it fills in what the model left out.
    if not words_heard["unclear"]:
        for key in ("service", "day", "choice"):
            if heard[key] is None:
                heard[key] = words_heard[key]
        if not (heard["time"] or heard["earliest"] or heard["latest"]):
            for key in ("time", "earliest", "latest"):
                heard[key] = words_heard[key]
        if not kind and words_heard["time"]:  # "afternoon at 3" where the model kept only "afternoon"
            heard["time"], heard["earliest"], heard["latest"] = words_heard["time"], None, None
        if not heard["parts"] and not (service or day or kind or part or choice or answer["no"]):
            heard["parts"] = words_heard["parts"]  # "the time", not "No, same time" or "No, the time is fine"

    # Rule 9: "Friday's fine" agrees with one detail only. A full yes with details starts with yes.
    heard["yes"] = answer["yes"]
    details = heard["service"] or heard["day"] or heard["time"] or heard["earliest"] or heard["latest"]
    words = text.lower().split()
    first_word = words[0].strip("?,.!'\"") if words else ""
    if details and first_word not in YES_WORDS:
        heard["yes"] = False
    return heard


def build_request(text: str, services: list[str]) -> dict:
    """Everything sent to the model for one caller turn."""
    return {
        "model": MODEL,
        "max_tokens": 1024,
        "system": PROMPT.format(services=", ".join(services)),
        "messages": [{"role": "user", "content": text}],
        "thinking": {"type": "disabled"},  # a short reading task, so a quick reply matters more
        "output_config": {"format": {"type": "json_schema", "schema": SCHEMA}},
    }


def read_response(response) -> dict | None:
    """The model's answer as a dict, or None if it refused or was cut off."""
    if response.stop_reason != "end_turn":
        return None
    texts = [block.text for block in response.content if block.type == "text"]
    try:
        return json.loads(texts[0])
    except (IndexError, json.JSONDecodeError):
        return None


def ask_model(text: str, services: list[str]) -> dict | None:
    """One live call to Claude Haiku 5.5. Returns its answer, or None if the call failed."""
    import anthropic  # only needed for live calls, so replay mode works without it

    client = anthropic.Anthropic(timeout=30)  # reads ANTHROPIC_API_KEY; a caller won't wait longer
    try:
        response = client.messages.create(**build_request(text, services))
    except anthropic.AuthenticationError:
        warn("The API key in .env was not accepted.")
        return None
    except anthropic.APIConnectionError:
        warn("Could not reach the API.")
        return None
    except anthropic.APIStatusError as error:
        warn(f"The API returned an error: {error.message}")  # e.g. no credit on the account
        return None
    answer = read_response(response)
    if answer is None:
        warn(f"The model gave no usable answer (stop reason: {response.stop_reason}).")
    return answer


def is_clock(clock) -> bool:
    """True for a 24-hour time like "17:30"."""
    if not isinstance(clock, str) or len(clock) != 5 or clock[2] != ":":
        return False
    hour, minute = clock[:2], clock[3:]
    if not all(digit in "0123456789" for digit in hour + minute):
        return False
    return int(hour) < 24 and int(minute) < 60


def shift(clock: str, minutes: int) -> str:
    """"17:00" moved by 1 minute is "17:01"."""
    total = int(clock[:2]) * 60 + int(clock[3:]) + minutes
    total = max(0, min(total, 23 * 60 + 59))
    return f"{total // 60:02d}:{total % 60:02d}"


def load_env(path: Path = ENV_PATH) -> None:
    """Copy KEY=VALUE lines from .env into the environment. A value already set wins."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("\"'"))


def has_key() -> bool:
    load_env()
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def load_replays(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_replays(replays: dict, path: Path) -> None:
    path.write_text(json.dumps(replays, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def warn(message: str) -> None:
    print(f"[model] {message}", file=sys.stderr)
