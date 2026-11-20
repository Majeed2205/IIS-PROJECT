import io
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import assistant.record as record
from assistant.chat import WHICH_PART, Conversation
from assistant.model import (
    REPLAY_PATH,
    SCHEMA,
    ModelReader,
    ask_model,
    build_request,
    has_key,
    load_env,
    load_replays,
    read_response,
    shift,
    to_heard,
)
from assistant.policy import DAY_PARTS
from assistant.slots import DAYS, Calendar
from assistant.understand import CHOICES, understand

SERVICES = ["haircut", "colour", "beard trim"]


def answer(**fields):
    """A hand-written model answer for the tests. Not a real recording."""
    empty = {"service": "", "day": "", "time_kind": "", "clock": "", "part_of_day": "",
             "choice": "", "yes": False, "no": False, "change": [], "unclear": False}
    empty.update(fields)
    return empty


def response(stop_reason, text, thinking_first=False):
    """A stand-in for the API's reply object."""
    blocks = [SimpleNamespace(type="text", text=text)]
    if thinking_first:
        blocks.insert(0, SimpleNamespace(type="thinking", thinking=""))
    return SimpleNamespace(stop_reason=stop_reason, content=blocks)


def fail_if_called(text, services):
    raise AssertionError("the model should not be called")


def fake_anthropic(reply=None, error=None):
    """A stand-in for the anthropic package, with no key and no network."""
    module = types.ModuleType("anthropic")
    module.sent = []

    class APIStatusError(Exception):
        def __init__(self, status_code, message=""):
            super().__init__(message)
            self.status_code = status_code
            self.message = message

    class AuthenticationError(APIStatusError):
        pass

    class APIConnectionError(Exception):
        pass

    def create(**request):
        module.sent.append(request)
        if error == "auth":
            raise AuthenticationError(401)
        if error == "connection":
            raise APIConnectionError()
        if error == "status":
            raise APIStatusError(400, "Error code: 400 - Your credit balance is too low")
        return reply

    module.APIStatusError = APIStatusError
    module.AuthenticationError = AuthenticationError
    module.APIConnectionError = APIConnectionError
    module.Anthropic = lambda timeout=None: SimpleNamespace(messages=SimpleNamespace(create=create))
    return module


class ToHeardTests(unittest.TestCase):
    """The model's answer becomes the same details the keyword reader gives."""

    def test_an_exact_time(self):
        heard = to_heard(answer(service="haircut", day="friday", time_kind="at", clock="17:30"),
                         "A haircut on Friday at half five", SERVICES)
        self.assertEqual((heard["service"], heard["day"], heard["time"]), ("haircut", "friday", "17:30"))
        self.assertFalse(heard["unclear"])

    def test_an_answer_the_keyword_reader_cannot_read_is_still_understood(self):
        heard = to_heard(answer(time_kind="at", clock="18:15"), "I'd prefer quarter past six", SERVICES)
        self.assertEqual(heard["time"], "18:15")
        self.assertFalse(heard["unclear"])

    def test_after_and_before_leave_the_time_itself_out(self):
        self.assertEqual(to_heard(answer(time_kind="after", clock="17:00"), "after five", SERVICES)["earliest"], "17:01")
        self.assertEqual(to_heard(answer(time_kind="before", clock="12:00"), "before twelve", SERVICES)["latest"], "11:59")

    def test_a_part_of_the_day(self):
        heard = to_heard(answer(day="saturday", part_of_day="afternoon"), "Saturday afternoon", SERVICES)
        self.assertEqual((heard["earliest"], heard["latest"]), ("12:00", "16:59"))

    def test_a_time_and_a_part_of_the_day_must_fit(self):
        heard = to_heard(answer(time_kind="at", clock="10:00", part_of_day="morning"), "ten in the morning", SERVICES)
        self.assertEqual(heard["time"], "10:00")
        for odd in [answer(time_kind="at", clock="10:00", part_of_day="evening"),
                    answer(time_kind="at", clock="13:00", part_of_day="morning"),
                    answer(time_kind="after", clock="09:00", part_of_day="morning")]:
            self.assertTrue(to_heard(odd, "...", SERVICES)["unclear"], odd)

    def test_choice_yes_no_and_parts(self):
        self.assertEqual(to_heard(answer(choice="second"), "the second one", SERVICES)["choice"], 1)
        self.assertTrue(to_heard(answer(yes=True), "Yes", SERVICES)["yes"])
        heard = to_heard(answer(no=True, change=["time"]), "No, wrong time", SERVICES)
        self.assertTrue(heard["no"])
        self.assertFalse(heard["yes"])
        self.assertEqual(heard["parts"], ["time"])

    def test_yes_and_no_together_is_not_understood(self):
        heard = to_heard(answer(yes=True, no=True), "Yeah no", SERVICES)
        self.assertTrue(heard["unclear"])
        self.assertFalse(heard["yes"])

    def test_unclear_forgets_every_detail(self):
        heard = to_heard(answer(unclear=True, day="friday", time_kind="at", clock="17:30"),
                         "I'm busy at 5:30", SERVICES)
        self.assertTrue(heard["unclear"])
        self.assertIsNone(heard["day"])
        self.assertIsNone(heard["time"])

    def test_an_unclear_turn_keeps_a_no_word_like_the_keyword_reader(self):
        for text in ["I can't do Monday", "5:30, no wait, 6:15", "Yeah no"]:
            self.assertTrue(to_heard(answer(unclear=True), text, SERVICES)["no"], text)
        self.assertFalse(to_heard(answer(unclear=True), "I'm busy at 5:30", SERVICES)["no"])
        # The words decide, not the model, so both readers agree.
        self.assertFalse(to_heard(answer(unclear=True, no=True), "I'm busy at 5:30", SERVICES)["no"])
        self.assertEqual(to_heard(answer(unclear=True, change=["day"]), "5:30, no wait, 6:15", SERVICES)["parts"], [])

    def test_an_unclear_answer_is_never_a_yes_or_a_detail(self):
        for text in ["Yes", "Book it", "Monday at 11"]:
            heard = to_heard(answer(unclear=True), text, SERVICES)
            self.assertTrue(heard["unclear"], text)
            self.assertFalse(heard["yes"], text)
            self.assertEqual((heard["day"], heard["time"]), (None, None), text)

    def test_the_keyword_reader_fills_in_a_detail_the_model_left_out(self):
        # Real recordings left these out: "after six" twice, Thursday once and the part once.
        heard = to_heard(answer(choice="first"), "the first one after six", SERVICES)
        self.assertEqual((heard["choice"], heard["earliest"]), (0, "18:01"))
        heard = to_heard(answer(yes=True), "yes, after six", SERVICES)
        self.assertEqual((heard["yes"], heard["earliest"]), (True, "18:01"))
        self.assertEqual(to_heard(answer(no=True), "No, I said Thursday", SERVICES)["day"], "thursday")
        self.assertEqual(to_heard(answer(), "the time", SERVICES)["parts"], ["time"])
        self.assertEqual(to_heard(answer(day="friday"), "A haircut on Friday", SERVICES)["service"], "haircut")
        self.assertEqual(to_heard(answer(), "the second one", SERVICES)["choice"], 1)
        heard = to_heard(answer(service="haircut", day="friday", part_of_day="afternoon"),
                         "A haircut on Friday afternoon at 3", SERVICES)
        self.assertEqual((heard["time"], heard["earliest"], heard["latest"]), ("15:00", None, None))

    def test_the_keyword_reader_only_fills_gaps(self):
        # It keeps what the model said.
        self.assertEqual(to_heard(answer(choice="first"), "First, please", SERVICES)["choice"], 0)
        self.assertEqual(to_heard(answer(day="tuesday"), "Thursday", SERVICES)["day"], "tuesday")
        heard = to_heard(answer(time_kind="before", clock="18:00"), "after six", SERVICES)
        self.assertEqual((heard["earliest"], heard["latest"]), (None, "17:59"))  # the two readers' times are not mixed
        self.assertEqual(to_heard(answer(time_kind="at", clock="18:30"), "6:15", SERVICES)["time"], "18:30")
        self.assertEqual(to_heard(answer(change=["day"]), "the day and the time", SERVICES)["parts"], ["day"])
        # It adds nothing to a turn it does not fully understand.
        self.assertEqual(to_heard(answer(), "Yes, that time suits me", SERVICES)["parts"], [])  # "suits"
        self.assertIsNone(to_heard(answer(service="haircut", time_kind="at", clock="16:00"),
                                   "A haircut after Monday at four", SERVICES)["day"])  # "after Monday" is not Monday
        self.assertTrue(to_heard(answer(unclear=True), "the first one after six", SERVICES)["unclear"])
        # A greeting is not a time, and a "no" or a new detail gets no part to change.
        for text in ["Morning! Can I book a haircut on Thursday?", "Morning! Thursday please"]:
            self.assertIsNone(to_heard(answer(day="thursday"), text, SERVICES)["earliest"], text)
        self.assertEqual(to_heard(answer(no=True, day="thursday"), "No, Thursday, same time", SERVICES)["parts"], [])
        self.assertEqual(to_heard(answer(no=True, time_kind="at", clock="18:15"), "No, same day, at 6:15",
                                  SERVICES)["parts"], [])
        self.assertEqual(to_heard(answer(no=True), "No, the time is fine", SERVICES)["parts"], [])

    def test_the_fill_comes_before_the_rule_9_check(self):
        heard = to_heard(answer(yes=True), "Friday's fine", SERVICES)
        self.assertEqual((heard["day"], heard["yes"]), ("friday", False))  # agrees with one detail only

    def test_an_odd_answer_is_checked_for_a_no_word_too(self):
        heard = to_heard(answer(no=True, service="men's cut", change=["service"]), "No, a men's cut", SERVICES)
        self.assertEqual((heard["unclear"], heard["no"], heard["parts"], heard["service"]), (True, True, [], None))
        self.assertFalse(to_heard(answer(no=True, day="someday"), "someday maybe", SERVICES)["no"])

    def test_an_odd_answer_is_not_understood(self):
        odd_answers = [
            answer(time_kind="at", clock="5:30"), answer(time_kind="at", clock="25:00"),
            answer(time_kind="at", clock="24:00"), answer(time_kind="at", clock="17:60"),
            answer(time_kind="at", clock="²³:00"), answer(time_kind="at", clock=""),
            answer(day="someday"), answer(choice="fourth"), answer(part_of_day="night"),
            answer(time_kind="soon", clock="17:00"), answer(service=None, day="friday"),
            answer(service="haircut available friday at 5:30"), answer(service="cut & colour"),
            answer(service="a haircut that is free on friday afternoon"),
            answer(unclear="true", day="friday"), answer(yes="yes"), answer(change=None),
        ]
        for odd in odd_answers:
            self.assertTrue(to_heard(odd, "...", SERVICES)["unclear"], odd)

    def test_rule_9_a_yes_with_details_must_start_with_yes(self):
        heard = to_heard(answer(yes=True, time_kind="at", clock="17:30"), "Yes, 5:30 is fine", SERVICES)
        self.assertTrue(heard["yes"])
        agreeing_with_one_detail = {
            "Friday's fine": answer(yes=True, day="friday"),
            "The haircut's fine": answer(yes=True, service="haircut"),
            "5:30 is ok": answer(yes=True, time_kind="at", clock="17:30"),
            "After five is fine": answer(yes=True, time_kind="after", clock="17:00"),
        }
        for text, said in agreeing_with_one_detail.items():
            self.assertFalse(to_heard(said, text, SERVICES)["yes"], text)

    def test_service_names_are_tidied(self):
        self.assertEqual(to_heard(answer(service=" Haircut "), "...", SERVICES)["service"], "haircut")
        self.assertEqual(to_heard(answer(service="massage"), "...", SERVICES)["service"], "massage")
        self.assertEqual(to_heard(answer(service="beard trim"), "...", SERVICES)["service"], "beard trim")

    def test_shift_stays_inside_the_day(self):
        self.assertEqual(shift("17:00", 1), "17:01")
        self.assertEqual(shift("23:59", 1), "23:59")
        self.assertEqual(shift("00:00", -1), "00:00")


class RequestTests(unittest.TestCase):
    def test_the_request_for_one_turn(self):
        request = build_request("A haircut on Friday", SERVICES)
        self.assertEqual(request["model"], "claude-haiku-5-5")
        self.assertEqual(request["messages"], [{"role": "user", "content": "A haircut on Friday"}])
        self.assertIn("haircut, colour, beard trim", request["system"])
        self.assertEqual(request["output_config"]["format"], {"type": "json_schema", "schema": SCHEMA})
        for setting in ("temperature", "top_p", "top_k"):
            self.assertNotIn(setting, request)  # Haiku 5.5 does not accept these

    def test_the_schema_matches_the_answers(self):
        self.assertEqual(sorted(SCHEMA["required"]), sorted(SCHEMA["properties"]))
        self.assertEqual(sorted(answer()), sorted(SCHEMA["properties"]))
        self.assertFalse(SCHEMA["additionalProperties"])

    def test_the_schema_allows_what_to_heard_reads(self):
        fields = SCHEMA["properties"]
        self.assertEqual(fields["day"]["enum"], DAYS + [""])
        self.assertEqual(fields["time_kind"]["enum"], ["at", "after", "before", ""])
        self.assertEqual(fields["part_of_day"]["enum"], list(DAY_PARTS) + [""])
        self.assertEqual(fields["choice"]["enum"], list(CHOICES) + [""])
        self.assertEqual(fields["change"]["items"]["enum"], ["service", "day", "time"])
        for flag in ("yes", "no", "unclear"):
            self.assertEqual(fields[flag]["type"], "boolean")


class ResponseTests(unittest.TestCase):
    def test_a_finished_answer_is_read(self):
        text = json.dumps(answer(day="friday"))
        self.assertEqual(read_response(response("end_turn", text))["day"], "friday")
        self.assertEqual(read_response(response("end_turn", text, thinking_first=True))["day"], "friday")

    def test_a_refused_or_cut_off_answer_is_not_used(self):
        good_json = json.dumps(answer(day="friday"))
        self.assertIsNone(read_response(response("refusal", good_json)))
        self.assertIsNone(read_response(response("max_tokens", good_json)))

    def test_broken_or_missing_json_is_not_used(self):
        self.assertIsNone(read_response(response("end_turn", "not json")))
        self.assertIsNone(read_response(SimpleNamespace(stop_reason="end_turn", content=[])))


class AskModelTests(unittest.TestCase):
    """The live call, with a fake anthropic package: no key and no network."""

    def ask(self, module):
        with mock.patch.dict(sys.modules, {"anthropic": module}), mock.patch("sys.stderr", io.StringIO()):
            return ask_model("A haircut on Friday", SERVICES)

    def test_a_good_reply_is_read_and_the_request_is_sent(self):
        module = fake_anthropic(reply=response("end_turn", json.dumps(answer(day="friday"))))
        self.assertEqual(self.ask(module)["day"], "friday")
        self.assertEqual(module.sent, [build_request("A haircut on Friday", SERVICES)])

    def test_a_failed_call_gives_nothing(self):
        for error in ("auth", "connection", "status"):
            self.assertIsNone(self.ask(fake_anthropic(error=error)), error)
        self.assertIsNone(self.ask(fake_anthropic(reply=response("refusal", json.dumps(answer())))))

    def test_the_reason_from_the_api_is_printed(self):
        printed = io.StringIO()
        with mock.patch.dict(sys.modules, {"anthropic": fake_anthropic(error="status")}), \
                mock.patch("sys.stderr", printed):
            ask_model("A haircut on Friday", SERVICES)
        self.assertIn("credit balance is too low", printed.getvalue())


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / "replays.json"

    def tearDown(self):
        self.folder.cleanup()

    def test_a_saved_answer_is_used_without_calling_the_model(self):
        self.path.write_text(json.dumps({
            "a haircut on friday after five": answer(service="haircut", day="friday", time_kind="after", clock="17:00"),
        }))
        reader = ModelReader(live=True, replay_path=self.path, ask=fail_if_called)
        heard = reader("  A HAIRCUT on Friday   after five ", SERVICES)
        self.assertEqual((heard["service"], heard["earliest"]), ("haircut", "17:01"))

    def test_without_a_key_an_unsaved_sentence_goes_to_the_keyword_reader(self):
        reader = ModelReader(live=False, replay_path=self.path, ask=fail_if_called)
        self.assertEqual(reader("A haircut on Friday at half five", SERVICES)["time"], "17:30")

    def test_the_keyword_reader_still_knows_a_greeting_at_the_start(self):
        reader = ModelReader(live=False, replay_path=self.path, ask=fail_if_called)
        heard = reader("Afternoon! Can I book a haircut on Friday?", SERVICES, first_turn=True)
        self.assertIsNone(heard["earliest"])

    def test_a_live_answer_is_saved_and_replayed(self):
        calls = []

        def ask(text, services):
            calls.append(text)
            return answer(day="monday")

        reader = ModelReader(live=True, replay_path=self.path, ask=ask)
        reader("Monday please", SERVICES)
        reader("monday   please", SERVICES)
        self.assertEqual(calls, ["Monday please"])  # the second time is a replay
        self.assertEqual(json.loads(self.path.read_text()), {"monday please": answer(day="monday")})
        replayed = ModelReader(live=False, replay_path=self.path, ask=fail_if_called)("Monday please", SERVICES)
        self.assertEqual(replayed["day"], "monday")

    def test_every_live_answer_is_kept(self):
        reader = ModelReader(live=True, replay_path=self.path, ask=lambda text, services: answer(day="monday"))
        reader("Monday please", SERVICES)
        reader("Monday then", SERVICES)
        self.assertEqual(sorted(json.loads(self.path.read_text())), ["monday please", "monday then"])

    def test_a_failed_call_falls_back_and_is_not_saved(self):
        reader = ModelReader(live=True, replay_path=self.path, ask=lambda text, services: None)
        self.assertEqual(reader("A haircut on Friday at half five", SERVICES)["time"], "17:30")
        self.assertFalse(self.path.exists())

    def test_an_empty_turn_is_not_sent(self):
        reader = ModelReader(live=True, replay_path=self.path, ask=fail_if_called)
        self.assertIsNone(reader("   ", SERVICES)["service"])


class LiveSwitchTests(unittest.TestCase):
    """Live mode needs a key and the package. A fake key is used; no real key is read."""

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "replays.json"

    def test_a_key_turns_live_mode_on(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            self.assertTrue(ModelReader(replay_path=self.path, ask=fail_if_called).live)

    def test_an_empty_key_is_no_key(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": ""}):
            self.assertFalse(has_key())
            self.assertFalse(ModelReader(replay_path=self.path).live)

    def test_without_the_package_live_mode_is_off(self):
        with mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}), \
                mock.patch("importlib.util.find_spec", return_value=None), \
                mock.patch("sys.stderr", io.StringIO()):
            self.assertFalse(ModelReader(replay_path=self.path).live)


class ChatWithModelTests(unittest.TestCase):
    """The loop works the same with model answers. These answers are hand-written."""

    def chat(self, strategy, replays):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "replays.json"
        path.write_text(json.dumps(replays))
        return Conversation(Calendar.load(), strategy, reader=ModelReader(live=False, replay_path=path))

    def test_clarify_then_a_reply_only_the_model_understands(self):
        chat = self.chat("clarify", {
            "a haircut on friday after five": answer(service="haircut", day="friday", time_kind="after", clock="17:00"),
            "i'd prefer quarter past six": answer(time_kind="at", clock="18:15"),
        })
        self.assertEqual(chat.reply("A haircut on Friday after five"),
                         "On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?")
        self.assertEqual(chat.reply("I'd prefer quarter past six"), "Booked: haircut on Friday at 6:15 pm.")

    def test_an_unclear_model_answer_books_nothing(self):
        chat = self.chat("clarify", {
            "a haircut on friday after five": answer(service="haircut", day="friday", time_kind="after", clock="17:00"),
            "i'm busy at 5:30": answer(unclear=True),
        })
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("I'm busy at 5:30"), "Sorry, I didn't catch that. "
                                                         "On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?")
        self.assertIsNone(chat.booking)

    def test_summarise_still_waits_for_yes(self):
        chat = self.chat("summarise", {
            "a haircut on friday at half five": answer(service="haircut", day="friday", time_kind="at", clock="17:30"),
            "friday's fine": answer(yes=True, day="friday"),
            "yeah no": answer(yes=True, no=True),
            "yes": answer(yes=True),
        })
        chat.reply("A haircut on Friday at half five")
        chat.reply("Friday's fine")
        self.assertIsNone(chat.booking)
        self.assertEqual(chat.reply("Yeah no"), WHICH_PART)  # "yeah no" means no
        self.assertIsNone(chat.booking)
        chat.reply("yes")  # the read-back is said again
        self.assertEqual(chat.reply("yes"), "Booked: haircut on Friday at 5:30 pm.")

    def test_a_no_from_the_model_asks_which_part(self):
        chat = self.chat("summarise", {
            "a haircut on friday at half five": answer(service="haircut", day="friday", time_kind="at", clock="17:30"),
            "no": answer(no=True),
        })
        chat.reply("A haircut on Friday at half five")
        self.assertEqual(chat.reply("No"), WHICH_PART)
        self.assertIsNone(chat.booking)

    def test_18_a_no_word_at_a_read_back_asks_which_part(self):
        for text in ["I can't do Monday", "5:30, no wait, 6:15", "I cannot do Monday"]:
            chat = self.chat("summarise", {
                "a haircut on monday at 11": answer(service="haircut", day="monday", time_kind="at", clock="11:00"),
                text.lower(): answer(unclear=True),  # like the saved answers
            })
            chat.reply("A haircut on Monday at 11")
            self.assertEqual(chat.reply(text), WHICH_PART, text)
            self.assertIsNone(chat.booking, text)

    def test_19_a_turn_down_without_a_no_word_at_a_read_back_is_not_understood(self):
        chat = self.chat("summarise", {
            "a haircut on monday at 11": answer(service="haircut", day="monday", time_kind="at", clock="11:00"),
            "i'm busy at 5:30": answer(unclear=True),
        })
        chat.reply("A haircut on Monday at 11")
        self.assertEqual(chat.reply("I'm busy at 5:30"),
                         "Sorry, I didn't catch that. So that's a haircut on Monday at 11 am. Is that right?")
        self.assertIsNone(chat.booking)

    def test_an_unclear_yes_at_a_read_back_books_nothing(self):
        chat = self.chat("summarise", {
            "a haircut on friday at half five": answer(service="haircut", day="friday", time_kind="at", clock="17:30"),
            "yes": answer(unclear=True),
        })
        chat.reply("A haircut on Friday at half five")
        self.assertEqual(chat.reply("Yes"),
                         "Sorry, I didn't catch that. So that's a haircut on Friday at 5:30 pm. Is that right?")
        self.assertIsNone(chat.booking)

    def test_both_readers_reply_the_same_to_a_turn_they_do_not_understand(self):
        situations = [
            ("clarify", []),
            ("clarify", ["A haircut on Friday after five"]),
            ("clarify", ["Colour on Saturday afternoon"]),
            ("summarise", ["A haircut on Friday at half five"]),
            ("summarise", ["A haircut on Friday at half five", "No"]),
            ("repeat", ["A haircut on Friday after five"]),
        ]
        not_understood = ["5:30, no wait, 6:15", "I can't do Monday", "I cannot do Monday", "That's incorrect",
                          "I'm busy at 5:30", "Is that Friday?", "You said Friday?", "Monday and Tuesday", "Monday 11",
                          "Sometime next week", "Yeah no"]
        # The model says it is unsure, or gives an answer that can't be used.
        model_answers = [answer(unclear=True), answer(no=True, day="someday"), answer(no="yes"),
                         answer(no=True, time_kind="after", clock="09:00", part_of_day="morning")]
        for strategy, turns in situations:
            for text in not_understood:
                for said in model_answers:
                    keyword_chat = Conversation(Calendar.load(), strategy)
                    model_chat = self.chat(strategy, {text.lower(): said})
                    for turn in turns:  # not saved, so both chats read these with the keyword reader
                        keyword_chat.reply(turn)
                        model_chat.reply(turn)
                    with self.subTest(strategy=strategy, turns=turns, text=text, answer=said):
                        self.assertEqual(model_chat.reply(text), keyword_chat.reply(text))

    def test_a_yes_that_names_another_time_is_a_correction(self):
        chat = self.chat("summarise", {
            "a haircut on friday at 6:15": answer(service="haircut", day="friday", time_kind="at", clock="18:15"),
            "yes, 5:30 is fine": answer(yes=True, time_kind="at", clock="17:30"),
        })
        chat.reply("A haircut on Friday at 6:15")
        self.assertEqual(chat.reply("Yes, 5:30 is fine"), "So that's a haircut on Friday at 5:30 pm. Is that right?")
        self.assertIsNone(chat.booking)  # rule 9: 6:15 must not be booked

    def test_a_time_the_model_left_out_does_not_book_the_wrong_slot(self):
        chat = self.chat("summarise", {
            "a haircut on friday at half five": answer(service="haircut", day="friday", time_kind="at", clock="17:30"),
            "yes, after six": answer(yes=True),  # "after six" left out, as in a real recording
        })
        chat.reply("A haircut on Friday at half five")
        self.assertEqual(chat.reply("yes, after six"), "So that's a haircut on Friday at 6:15 pm. Is that right?")
        self.assertIsNone(chat.booking)  # rule 9: a correction, so 5:30 must not be booked
        chat = self.chat("clarify", {
            "a haircut on friday after five": answer(service="haircut", day="friday", time_kind="after", clock="17:00"),
            "the first one after six": answer(choice="first"),
        })
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("the first one after six"), "Booked: haircut on Friday at 6:15 pm.")  # rule 8

    def test_a_greeting_is_not_filled_in_as_a_time(self):
        chat = self.chat("clarify", {"morning! can i book a haircut on thursday?": answer(service="haircut", day="thursday")})
        self.assertEqual(chat.reply("Morning! Can I book a haircut on Thursday?"), "What time on Thursday would you like?")
        chat = self.chat("clarify", {"morning! thursday please": answer(day="thursday")})
        chat.reply("A haircut please")
        self.assertEqual(chat.reply("Morning! Thursday please"), "What time on Thursday would you like?")

    def test_after_a_day_is_not_that_day(self):
        chat = self.chat("clarify", {"a haircut after monday at four": answer(service="haircut", time_kind="at", clock="16:00")})
        self.assertEqual(chat.reply("A haircut after Monday at four"), "Which day would you like to come in?")

    def test_agreeing_with_the_time_only_books_nothing(self):
        chat = self.chat("summarise", {
            "a haircut on friday at half five": answer(service="haircut", day="friday", time_kind="at", clock="17:30"),
            "the time's fine": answer(yes=True),
        })
        chat.reply("A haircut on Friday at half five")
        self.assertEqual(chat.reply("The time's fine"), "So that's a haircut on Friday at 5:30 pm. Is that right?")
        self.assertIsNone(chat.booking)  # rule 9: it agrees with one part only


class RecordTests(unittest.TestCase):
    def test_only_saved_answers_are_reported_as_saved(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        reader = ModelReader(live=True, replay_path=Path(folder.name) / "replays.json",
                             ask=lambda text, services: None if text == "No" else answer(yes=True))
        printed = io.StringIO()
        with mock.patch.object(record, "ModelReader", return_value=reader), \
                mock.patch.object(record, "PHRASES", ["Yes", "No"]), mock.patch("sys.stdout", printed):
            record.main()
        self.assertIn("'No'", printed.getvalue())
        self.assertIn("not saved", printed.getvalue())
        self.assertIn("1 of 2 answers are saved", printed.getvalue())

    def test_without_live_calls_nothing_is_recorded(self):
        printed = io.StringIO()
        reader = SimpleNamespace(live=False)
        with mock.patch.object(record, "ModelReader", return_value=reader), mock.patch("sys.stdout", printed):
            record.main()
        self.assertIn("Live calls are off", printed.getvalue())

    def test_the_details_the_keyword_reader_filled_in_are_reported(self):
        said = answer(choice="first")
        self.assertEqual(record.filled_in(said, to_heard(said, "the first one after six", SERVICES)), ["time"])
        said = answer(no=True)
        self.assertEqual(record.filled_in(said, to_heard(said, "No, I said Thursday", SERVICES)), ["day"])
        said = answer(service="haircut", day="friday", time_kind="at", clock="17:30")
        self.assertEqual(record.filled_in(said, to_heard(said, "A haircut on Friday at half five", SERVICES)), [])
        said = answer(unclear=True)
        self.assertEqual(record.filled_in(said, to_heard(said, "I can't do Monday", SERVICES)), [])
        self.assertEqual(record.filled_in(said, to_heard(said, "the time", SERVICES)), [])  # not a fill (rule 6 parts)
        said = answer(service="colour", day="saturday", part_of_day="afternoon")
        self.assertEqual(record.filled_in(said, to_heard(said, "Colour on Saturday afternoon", SERVICES)), [])
        said = answer(service="haircut", day="friday", part_of_day="afternoon")
        self.assertEqual(record.filled_in(said, to_heard(said, "A haircut on Friday afternoon at 3", SERVICES)), ["time"])

    def test_the_report_counts_the_answers_the_keyword_reader_filled_in(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        answers = {"Yes": answer(yes=True), "the first one after six": answer(choice="first")}
        reader = ModelReader(live=True, replay_path=Path(folder.name) / "replays.json",
                             ask=lambda text, services: answers[text])
        printed = io.StringIO()
        with mock.patch.object(record, "ModelReader", return_value=reader), \
                mock.patch.object(record, "PHRASES", list(answers)), mock.patch("sys.stdout", printed):
            record.main()
        self.assertIn("'the first one after six'", printed.getvalue())
        self.assertEqual(printed.getvalue().count("<- the keyword reader filled in: time"), 1)
        self.assertIn("filled in a detail the model left out in 1 of them", printed.getvalue())

    def test_every_recorded_phrase_has_a_reading_to_check(self):
        listed = {" ".join(phrase.lower().split()) for phrase in record.PHRASES}
        self.assertEqual(listed, set(SPEC_READINGS))


class EnvTests(unittest.TestCase):
    def test_load_env_reads_key_value_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text('# a comment\nJUST_A_WORD\nIIS_TEST_VALUE="abc"\n\nIIS_TEST_OTHER=1\n')
            os.environ.pop("IIS_TEST_VALUE", None)
            os.environ["IIS_TEST_OTHER"] = "kept"
            try:
                load_env(path)
                self.assertEqual(os.environ["IIS_TEST_VALUE"], "abc")
                self.assertEqual(os.environ["IIS_TEST_OTHER"], "kept")  # a value already set wins
            finally:
                os.environ.pop("IIS_TEST_VALUE", None)
                os.environ.pop("IIS_TEST_OTHER", None)

    def test_no_env_file_is_fine(self):
        with tempfile.TemporaryDirectory() as folder:
            load_env(Path(folder) / ".env")  # no such file: nothing happens


# What each recorded phrase should be heard as, following the spec. A detail that is not
# listed must be empty. ANY marks a detail the spec does not decide, so it is not checked.
# Checked once the real answers are recorded with a key (python -m assistant.record).
ANY = "not checked"
SPEC_READINGS = {
    # The test phrases in the spec
    "a haircut on friday at half five": {"service": "haircut", "day": "friday", "time": "17:30"},
    "can i come in on friday after five?": {"day": "friday", "earliest": "17:01"},
    "a haircut on friday after five": {"service": "haircut", "day": "friday", "earliest": "17:01"},
    "a haircut on friday at seven": {"service": "haircut", "day": "friday", "time": "19:00"},
    "colour on saturday afternoon": {"service": "colour", "day": "saturday", "earliest": "12:00", "latest": "16:59"},
    "a massage on monday at eleven": {"service": "massage", "day": "monday", "time": "11:00"},
    "sunday at ten for a haircut": {"service": "haircut", "day": "sunday", "time": "10:00"},
    "sometime next week": {"unclear": True},
    "no, i said thursday": {"no": True, "day": "thursday", "parts": ANY},
    "yes": {"yes": True},
    "book it": {"yes": True},
    "no": {"no": True, "unclear": ANY},
    "can i come in on sunday?": {"day": "sunday"},
    "i'm busy at 5:30": {"unclear": True},  # no "no" word, so rule 7 even after a read-back
    "i'm busy": {"unclear": True},
    "friday's fine": {"day": "friday"},  # not a yes (rule 9)
    "5:30, no wait, 6:15": {"unclear": True, "no": True},  # after a read-back the "no" word counts (rule 6)
    "i can't do monday": {"unclear": True, "no": True},
    # Replies a caller often gives next
    "a haircut please": {"service": "haircut"},
    "the second one": {"choice": 1},
    "6:15": {"time": "18:15"},
    "4 pm": {"time": "16:00"},
    "a beard trim then": {"service": "beard trim", "parts": ANY},
    "the day": {"parts": ["day"]},
    "the time": {"parts": ["time"]},
    "no, wrong time": {"no": True, "parts": ["time"], "unclear": ANY},
    "yes, 5:30 is fine": {"yes": True, "time": "17:30"},
    "after six": {"earliest": "18:01", "parts": ANY},
    "monday at 11": {"day": "monday", "time": "11:00"},
    "monday 11": {"unclear": True},
    "good afternoon, can i book a haircut on friday?": {"service": "haircut", "day": "friday"},
    "is 6:15 the latest?": {"unclear": True},
    "you said friday?": {"unclear": True},  # a question about something, not a request (rule 7)
    "thursday at 10 in the morning": {"day": "thursday", "time": "10:00", "earliest": ANY, "latest": ANY},
    # More phrases from the spec
    "is that friday?": {"unclear": True},
    "monday and tuesday": {"unclear": True},
    "the first one": {"choice": 0},
    "the third one": {"choice": 2},
    "the first one after six": {"earliest": "18:01", "choice": ANY},  # rule 8: the time decides
    "yes, after six": {"earliest": "18:01", "yes": ANY},  # rule 9: a correction
    "before five": {"latest": "16:59"},
    "after 6:15": {"earliest": "18:16"},
    "thursday morning": {"day": "thursday", "earliest": "00:00", "latest": "11:59"},
    "in the evening": {"earliest": "17:00", "latest": "23:59"},
}


class RecordedAnswerTests(unittest.TestCase):
    """The real model's saved answers, as the assistant reads them (with the keyword reader
    filling in any detail the model left out), checked against the spec."""

    def setUp(self):
        self.replays = load_replays(REPLAY_PATH)
        if not self.replays:
            self.skipTest("no recorded answers yet (run python -m assistant.record)")

    def test_every_spec_phrase_has_a_recorded_answer(self):
        missing = [text for text in SPEC_READINGS if text not in self.replays]
        self.assertEqual(missing, [], "run python -m assistant.record")

    def test_recorded_answers_are_well_formed(self):
        for text, saved in self.replays.items():
            self.assertEqual(text, " ".join(text.lower().split()))
            self.assertEqual(sorted(saved), sorted(SCHEMA["properties"]), text)

    def test_recorded_answers_match_the_spec(self):
        services = Calendar.load().services
        empty = understand("", services)
        for text, details in SPEC_READINGS.items():
            if text not in self.replays:
                continue  # reported by the test above
            heard = to_heard(self.replays[text], text, services)
            for key, value in {**empty, **details}.items():
                if value == ANY:
                    continue
                with self.subTest(text=text, detail=key):
                    self.assertEqual(heard[key], value)


if __name__ == "__main__":
    unittest.main()
