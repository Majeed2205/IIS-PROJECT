"""Turns what the caller typed into the details the policy needs.

Status: simulated. A simple keyword reader, used when model.py has no saved
or live model answer for a sentence.

It only acts on a turn when it knows every word in it. Otherwise it hears
nothing and the assistant asks again: an extra question is better than a
wrong booking.
"""
from __future__ import annotations

from .policy import DAY_PARTS
from .slots import DAYS

NUMBERS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
}
MINUTES = {"fifteen": 15, "thirty": 30, "forty-five": 45}
OTHER_SERVICES = ["massage", "manicure", "nails", "facial", "waxing"]
CHOICES = {"first": 0, "second": 1, "third": 2}
PARTS = ["service", "day", "time"]
TIME_WORDS = ["at", "half", "past", "after", "before", "around", "about"]

YES_WORDS = ["yes", "yeah", "yep", "yup", "correct", "right", "sure", "ok", "okay", "fine", "perfect"]
YES_PHRASES = ["book it", "go ahead", "sounds good"]
# The "no" words in rule 6 of the spec. Any word ending in "n't" counts too (is_negative).
NO_WORDS = ["no", "nope", "nah", "not", "never", "nothing", "none", "wrong", "incorrect", "cannot",
            "dont", "cant", "isnt", "arent", "wasnt", "werent", "doesnt", "didnt", "wont", "wouldnt",
            "couldnt", "shouldnt", "havent", "hasnt", "hadnt", "aint", "mustnt", "neednt", "mightnt", "shant"]
# A turn starting like this asks about something ("is that Friday?"), it is not a request.
QUESTION_STARTS = ["is", "are", "was", "were", "did", "do", "does", "anything", "any"]
QUESTION_WORDS = ["what", "which", "when", "where", "how", "why"]
# A "?" makes a question too ("You said Friday?"), unless the turn asks for something:
# "Can I come in on Sunday?", "Would you have the 6:15?" or "Friday at 5:30 please?".
REQUEST_WORDS = ["can", "could", "may", "would"]
# Words that can come just before the "is" of a question with no "?" ("Thanks, is 6:15 ok").
OPENERS = ["and", "then", "please", "thanks", "you", "great", "lovely", "good", "hello", "hi"]

# Words that can go with a yes, as in "yes please, that's great".
YES_FILLER = ["please", "that", "it", "is", "a", "an", "the", "on", "for", "then", "great", "lovely",
              "thanks", "thank", "you", "good", "book", "go", "ahead", "sounds", "works", "me", "all"]
# Other words we know. A turn with any word not in a list here is not understood.
OTHER_WORDS = ["in", "and", "can", "could", "may", "i", "i'd", "id", "like", "want", "would", "get",
               "have", "come", "said", "same", "appointment", "just", "one", "hello", "hi",
               "thing", "quarter", "o'clock", "am", "pm"]


def understand(text: str, services: list[str], first_turn: bool = False) -> dict:
    """Return what was said. Anything not said (or not clear) is None, False or empty."""
    text = text.lower().replace("’", "'").replace("‘", "'")
    text = text.replace("p.m.", "pm").replace("a.m.", "am").replace("color", "colour")
    all_services = services + OTHER_SERVICES
    for service in all_services:
        text = text.replace(service, service.replace(" ", "_"))  # "beard trim" -> "beard_trim"
    service_words = [s.replace(" ", "_") for s in all_services]

    words = []
    for word in text.split():
        word = word.strip("?,.!'\"")
        if word.endswith("'s"):
            word = word[:-2]  # "friday's" -> "friday"
        words.append(word)

    heard = {
        "service": None, "day": None, "time": None, "earliest": None, "latest": None,
        "yes": False, "no": False, "choice": None, "parts": [], "unclear": False,
    }
    heard["parts"] = [word for word in PARTS if word in words]

    # A "no" at the start is an answer ("No, I said Thursday").
    starts_with_no = len(words) > 0 and words[0] in ("no", "nope", "nah")
    rest = words[1:] if starts_with_no else words
    heard["no"] = starts_with_no or any(is_negative(word) for word in words)

    is_question = (len(words) > 0 and words[0] in QUESTION_STARTS) or any(w in QUESTION_WORDS for w in words)
    if asks_about_something(text, words):
        is_question = True
    # We only act on a turn if we know every word in it. A "no" or "not" in the
    # middle is not a known word, because we can't tell what is being turned down.
    unknown = any(not is_known(word, service_words) for word in rest)
    if is_question or unknown:
        return unclear(heard)

    # Two services, days or choices: we can't tell which one the caller wants.
    found_services = [s for s in all_services if s.replace(" ", "_") in words]
    found_days = [word for word in words if word in DAYS]
    choices = []
    for i, word in enumerate(words):
        before = words[i - 1] if i > 0 else ""
        after = words[i + 1] if i + 1 < len(words) else ""
        # "the second" or "second one", but not "just a second" or "the first thing".
        if word in CHOICES and (before == "the" or after == "one") and after != "thing":
            choices.append(CHOICES[word])
    if len(set(found_services)) > 1 or len(set(found_days)) > 1 or len(set(choices)) > 1:
        return unclear(heard)
    if found_services:
        heard["service"] = found_services[0]
    if found_days:
        heard["day"] = found_days[0]
    if choices:
        heard["choice"] = choices[0]

    parts_of_day = []
    for i, word in enumerate(words):
        before = words[i - 1] if i > 0 else ""
        # "Good afternoon", or "Morning!" before the caller has asked for anything, is a greeting.
        greeting = before == "good" or (first_turn and (i == 0 or before in ("hi", "hello")))
        if word in DAY_PARTS and not greeting:
            parts_of_day.append(word)
    if "first thing" in text:
        parts_of_day.append("morning")

    kind, time = find_time(words)
    if kind == "unclear" or len(set(parts_of_day)) > 1:
        return unclear(heard)
    if parts_of_day and kind is not None:
        # "at 10 in the evening": the time and the part of the day must fit together.
        start, end = DAY_PARTS[parts_of_day[0]]
        if kind != "at" or not start <= time <= end:
            return unclear(heard)
    if kind == "after":
        heard["earliest"] = time
    elif kind == "before":
        heard["latest"] = time
    elif kind == "at":
        heard["time"] = time
    elif parts_of_day:
        heard["earliest"], heard["latest"] = DAY_PARTS[parts_of_day[0]]

    if "?" not in text and (any(w in YES_WORDS for w in words) or any(p in text for p in YES_PHRASES)):
        heard["yes"] = only_yes_words(words, heard, service_words)
        # "Friday's fine" only agrees with the day. A full yes with details starts with yes.
        details = heard["service"] or heard["day"] or heard["time"] or heard["earliest"] or heard["latest"]
        if details and words[0] not in YES_WORDS:
            heard["yes"] = False
    return heard


def find_time(words: list[str]) -> tuple[str | None, str | None]:
    """Find a time like "at seven", "half five", "ten thirty" or "after five".

    Returns ("at", "17:30"), ("after", "17:00"), ("before", "11:59") or (None, None).
    Returns ("unclear", None) if two different times are said, or if there is a
    number we can't place, as in "Monday 11" or "three in the afternoon".
    """
    found = []
    left_over = False
    used_as_minutes = []
    for i, word in enumerate(words):
        # "quarter" or "half" must be followed by a number or "past", so "quarter after four" is unclear.
        after = words[i + 1] if i + 1 < len(words) else ""
        if word in ("quarter", "half") and after != "past" and read_number(after) is None:
            return "unclear", None

    for i, word in enumerate(words):
        number = read_number(word)
        if number is None or i in used_as_minutes:
            continue
        hour, minute, suffix = number
        before = words[i - 1] if i > 0 else ""
        two_back = words[i - 2] if i > 1 else ""
        after = words[i + 1] if i + 1 < len(words) else ""

        # "one" in "the first one" or "the 4 one" is not a number.
        if word == "one" and (before in CHOICES or read_number(before) is not None):
            continue

        # "ten thirty" or "10 30"
        has_minutes = after in MINUTES or (after.isdigit() and len(after) == 2)
        if has_minutes:
            minute = MINUTES[after] if after in MINUTES else int(after)
            used_as_minutes.append(i + 1)
            after = words[i + 2] if i + 2 < len(words) else ""

        # "half five", "half past five", "quarter past five"
        start = i
        if before == "half":
            minute, start = 30, i - 1
        elif before == "past":
            if two_back == "half":
                minute, start = 30, i - 2
            elif two_back == "quarter":
                minute, start = 15, i - 2
            else:
                left_over = True  # "ten past four" is not understood
                continue
        range_word = words[start - 1] if start > 0 else ""

        # A bare number only counts as a time if something says so.
        is_time = (suffix or ":" in word or "." in word or has_minutes or start < i
                   or range_word in TIME_WORDS or after in ("am", "pm", "o'clock", "one")
                   or len(words) == 1 or (len(words) == 2 and after in ("please", "then")))
        if not is_time:
            left_over = True
            continue

        if not suffix and after in ("am", "pm"):
            suffix = after
        if suffix == "pm" and hour < 12:
            hour += 12
        elif suffix == "am" and hour == 12:
            hour = 0
        elif not suffix and hour < 9:
            hour += 12  # the salon opens at 9, so "five" means 5 pm

        if range_word == "after":
            minutes = hour * 60 + minute + 1  # "after five" leaves 5 pm out, so it starts at 17:01
            found.append(("after", f"{minutes // 60:02d}:{minutes % 60:02d}"))
        elif range_word == "before":
            minutes = hour * 60 + minute - 1  # the range includes its end, so "before 12" is 11:59
            found.append(("before", f"{minutes // 60:02d}:{minutes % 60:02d}"))
        else:
            found.append(("at", f"{hour:02d}:{minute:02d}"))

    # "after" and "before" must come just before a time, so "after Monday" and "after the 5:30" are unclear.
    ranges = [kind for kind, _ in found if kind != "at"]
    if left_over or len(set(found)) > 1 or len(ranges) < words.count("after") + words.count("before"):
        return "unclear", None
    if found:
        return found[0]
    return None, None


def read_number(word: str) -> tuple[int, int, str] | None:
    """"seven" -> (7, 0, ""), "5:30pm" -> (5, 30, "pm"), anything else -> None."""
    if word in ("noon", "midday"):
        return 12, 0, "pm"
    suffix = ""
    if word.endswith("am") or word.endswith("pm"):
        word, suffix = word[:-2], word[-2:]
    if word in NUMBERS:
        return NUMBERS[word], 0, suffix

    word = word.replace(".", ":")
    hour, _, minute = word.partition(":")
    if not hour.isdigit() or not (minute.isdigit() or minute == ""):
        return None
    hour, minute = int(hour), int(minute or 0)
    if hour > 23 or minute > 59:
        return None
    return hour, minute, suffix


def unclear(heard: dict) -> dict:
    """Forget every detail, so the assistant asks again."""
    for key in ("service", "day", "time", "earliest", "latest", "choice"):
        heard[key] = None
    heard["yes"] = False
    heard["unclear"] = True
    return heard


def is_negative(word: str) -> bool:
    return word in NO_WORDS or word.endswith("n't")


def is_known(word: str, service_words: list[str]) -> bool:
    lists = [YES_WORDS, YES_FILLER, OTHER_WORDS, DAYS, DAY_PARTS, CHOICES, PARTS,
             TIME_WORDS, MINUTES, service_words]
    return any(word in known for known in lists) or word.isdigit() or read_number(word) is not None


def only_yes_words(words: list[str], heard: dict, service_words: list[str]) -> bool:
    """True if the turn is just a yes, maybe with details, so "ok, let me check" is not a yes."""
    has_time = heard["time"] or heard["earliest"] or heard["latest"]
    for word in words:
        if word in YES_WORDS or word in YES_FILLER or word in DAYS or word in DAY_PARTS:
            continue
        if word in service_words or word in TIME_WORDS or word in ("am", "pm"):
            continue
        if has_time and (read_number(word) is not None or word in MINUTES):
            continue
        return False
    return True


def asks_about_something(text: str, words: list[str]) -> bool:
    """True for a "?" turn that does not ask for something ("You said Friday?"), or a turn that
    asks_with_is() finds ("OK, is that right") (rule 7). A "?" turn that asks for something is
    a request (v0.8).

    Both readers use it. understand() also counts a turn that starts with a word in QUESTION_STARTS
    ("Is 6:15 free") or has one in QUESTION_WORDS ("How about 6:15 please?") as a question.
    """
    return ("?" in text and not asks_for_something(words)) or asks_with_is(words)


def asks_with_is(words: list[str]) -> bool:
    """True for "OK, is that right", "Thanks, is 6:15 ok" or "6:15, is it", even with no "?".

    The "is" comes just after a yes word or an opener, or just before "that" or "it".
    "That is it", "5:30 is fine", "it sure is" and "yes, is fine" are statements, and
    "Can I have the 6:15, is that ok?" is a request (v0.8).
    """
    if asks_for_something(words):
        return False
    for i, word in enumerate(words):
        before = words[i - 1] if i > 0 else ""
        after = words[i + 1] if i + 1 < len(words) else ""
        if word != "is" or after == "" or after in YES_WORDS or after in ("good", "great", "lovely"):
            continue
        if before in YES_WORDS or before in OPENERS or (after in ("that", "it") and before not in ("that", "it")):
            return True
    return False


def asks_for_something(words: list[str]) -> bool:
    """True for "can I come in on Sunday" or "Friday at 5:30 please", not for "you said I can come Friday"."""
    if "said" in words:
        return False
    for word, after in zip(words, words[1:]):
        if word in REQUEST_WORDS and after in ("i", "you"):
            return True
    return len(words) > 0 and words[-1] == "please" and not any(w in QUESTION_STARTS for w in words)
