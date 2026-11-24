import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from assistant.chat import GIVE_UP, WHICH_PART, Conversation
from assistant.chat import main as chat_main
from assistant.model import ModelReader
from assistant.slots import Calendar
from assistant import turnlog
from assistant.turnlog import TurnFile, new_log_path

FIELDS = ["call", "turn", "seconds", "strategy", "mishear", "said", "reader", "read", "misheard", "decided",
          "booking", "reply", "not_understood", "finished"]


def logged_call(strategy, turns, **options):
    log = []
    chat = Conversation(Calendar.load(), strategy, log=log, **options)
    replies = [chat.reply(turn) for turn in turns]
    return log, replies


class TurnRecordTests(unittest.TestCase):
    def test_one_record_per_turn(self):
        log, replies = logged_call("summarise", ["A haircut on Friday at half five", "Yes"])
        self.assertEqual([record["turn"] for record in log], [1, 2])
        for record, reply in zip(log, replies):
            self.assertEqual(list(record), FIELDS)
            self.assertEqual(record["reply"], reply)
            self.assertEqual((record["call"], record["strategy"], record["mishear"]), ("call-1", "summarise", False))
        self.assertLessEqual(0, log[0]["seconds"])
        self.assertLessEqual(log[0]["seconds"], log[1]["seconds"])
        self.assertLess(log[1]["seconds"], 60)  # counted from the start of the call

    def test_what_was_said_read_decided_and_booked(self):
        log, replies = logged_call("summarise", ["A haircut on Friday at half five", "Yes"])
        first, second = log
        self.assertEqual(first["said"], "A haircut on Friday at half five")
        self.assertEqual(first["reader"], "keyword reader")
        self.assertEqual((first["read"]["service"], first["read"]["day"], first["read"]["time"]),
                         ("haircut", "friday", "17:30"))
        self.assertEqual(first["decided"], {"kind": "confirm", "detail": None, "slot": "friday 17:30", "options": []})
        self.assertIsNone(first["booking"])
        self.assertTrue(second["read"]["yes"])
        self.assertIsNone(second["decided"])  # the loop books a yes to a read-back, without asking the policy
        self.assertEqual(second["booking"],
                         {"status": "booked", "service": "haircut", "day": "friday", "time": "17:30", "repeat": False})

    def test_an_offer_and_a_pick(self):
        log, replies = logged_call("clarify", ["A haircut on Friday after five", "the second one"])
        self.assertEqual(log[0]["decided"]["kind"], "clarify")
        self.assertEqual(log[0]["decided"]["options"], ["friday 17:30", "friday 18:15"])
        self.assertEqual(log[1]["read"]["choice"], 1)
        self.assertEqual(log[1]["decided"]["kind"], "book")
        self.assertEqual(log[1]["booking"]["time"], "18:15")

    def test_the_planted_error_is_logged_on_its_turn(self):
        log, replies = logged_call("summarise", ["A haircut on Friday at half five", "No, I said half five"], mishear=True)
        self.assertEqual(log[0]["misheard"], ["17:30", "18:15"])
        self.assertEqual(log[0]["read"]["time"], "17:30")  # what the reader heard, before the planted error
        self.assertEqual(log[0]["decided"]["slot"], "friday 18:15")
        self.assertIsNone(log[1]["misheard"])
        self.assertTrue(log[1]["mishear"])

    def test_counts_and_the_end_of_the_call(self):
        log, replies = logged_call("summarise", ["A haircut on Friday at half five", "No", "No", "No", "No", "No"])
        self.assertEqual(log[1]["reply"], WHICH_PART)
        self.assertIsNone(log[1]["decided"])
        self.assertEqual([record["not_understood"] for record in log[1:5]], [0, 1, 2, 3])
        self.assertEqual(log[4]["reply"], GIVE_UP)
        self.assertEqual([record["finished"] for record in log], [False, False, False, False, True, True])
        self.assertIsNone(log[5]["read"])  # the call had ended, so nothing was read

    def test_a_turn_that_books_or_hands_over_starts_the_count_again(self):
        # Rule 7: any understood turn starts the count again, so the log shows 0 on it.
        calls = [("clarify", ["A haircut on Friday after five", "I'm busy", "I'm busy", "6:15"], [0, 1, 2, 0]),
                 ("summarise", ["A haircut on Friday at half five", "I'm busy", "Yes"], [0, 1, 0]),
                 ("repeat", ["A haircut on Friday after five"] * 2 + ["I'm busy", "A haircut on Friday after five"],
                  [0, 0, 1, 0])]
        for strategy, turns, counts in calls:
            log, replies = logged_call(strategy, turns)
            self.assertEqual([record["not_understood"] for record in log], counts, strategy)

    def test_no_log_unless_one_is_given(self):
        chat = Conversation(Calendar.load(), "summarise")
        chat.reply("A haircut on Friday at half five")
        self.assertIsNone(chat.log)

    def test_which_reader_read_the_turn(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "replays.json"
        path.write_text(json.dumps({"a haircut on friday at half five": {
            "service": "haircut", "day": "friday", "time_kind": "at", "clock": "17:30", "part_of_day": "",
            "choice": "", "yes": False, "no": False, "change": [], "unclear": False}}))
        log = []
        chat = Conversation(Calendar.load(), "summarise", reader=ModelReader(live=False, replay_path=path), log=log)
        chat.reply("A haircut on Friday at half five")
        chat.reply("Yes")  # not saved, so the keyword reader reads it
        self.assertEqual([record["reader"] for record in log], ["saved model answer", "keyword reader"])

    def test_the_live_model_is_named(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "replays.json"
        answer = {"service": "", "day": "", "time_kind": "", "clock": "", "part_of_day": "", "choice": "",
                  "yes": True, "no": False, "change": [], "unclear": False}
        reader = ModelReader(live=True, replay_path=path, ask=lambda text, services: answer)  # no real call
        log = []
        chat = Conversation(Calendar.load(), "summarise", reader=reader, log=log)
        chat.reply("yes")
        self.assertEqual(log[0]["reader"], "live model")

    def test_the_keyword_reader_is_named_when_it_reads_the_turn(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "replays.json"
        path.write_text(json.dumps({"10": {"service": "", "day": "", "time_kind": "", "clock": "", "part_of_day": "",
                                           "choice": "", "yes": False, "no": False, "change": [], "unclear": True}}))
        log = []
        chat = Conversation(Calendar.load(), "clarify", reader=ModelReader(live=False, replay_path=path), log=log)
        chat.reply("A haircut on Thursday")
        chat.reply("10")  # the model was unsure, so the keyword reader reads a turn that is only a time (v0.8)
        self.assertEqual(log[1]["reader"], "keyword reader")
        self.assertEqual(log[1]["booking"]["time"], "10:00")
        reader = ModelReader(live=True, replay_path=path, ask=lambda text, services: None)  # a live call that fails
        log = []
        Conversation(Calendar.load(), "clarify", reader=reader, log=log).reply("A haircut on Thursday")
        self.assertEqual(log[0]["reader"], "keyword reader")


class TurnFileTests(unittest.TestCase):
    def test_each_record_is_one_line_of_json(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "logs" / "call.jsonl"
        log = TurnFile(path)
        chat = Conversation(Calendar.load(), "clarify", log=log)
        chat.reply("A haircut on Friday after five")
        chat.reply("6:15")
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[1])["booking"]["time"], "18:15")

    def test_a_new_file_name_for_each_call(self):
        path = new_log_path("summarise")
        self.assertEqual(path.parent.name, "logs")
        self.assertTrue(path.name.endswith("-summarise.jsonl"), path.name)

    def test_two_calls_in_the_same_second_get_two_files(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with mock.patch.object(turnlog, "LOG_DIR", Path(folder.name)), mock.patch("time.strftime", return_value="x"):
            first = new_log_path("summarise")
            TurnFile(first)
            second = new_log_path("summarise")
        self.assertEqual((first.name, second.name), ("x-summarise.jsonl", "x-2-summarise.jsonl"))


class MainTests(unittest.TestCase):
    def run_chat(self, args):
        """Run python3 -m assistant.chat with these arguments and one turn, and return the log files it made."""
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        logs = Path(folder.name) / "logs"
        offline = lambda: ModelReader(live=False, replay_path=Path(folder.name) / "none.json")  # never a live call
        with mock.patch.object(turnlog, "LOG_DIR", logs), mock.patch("assistant.chat.ModelReader", offline), \
                mock.patch("sys.argv", ["chat"] + args), mock.patch("builtins.print"), \
                mock.patch("builtins.input", side_effect=["A haircut on Friday at half five", "quit"]):
            chat_main()
        return sorted(logs.glob("*.jsonl"))

    def test_a_log_only_with_the_switch(self):
        self.assertEqual(self.run_chat(["summarise"]), [])
        files = self.run_chat(["summarise", "--log"])
        self.assertEqual(len(files), 1)
        record = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual((record["call"], record["turn"]), (files[0].stem, 1))


if __name__ == "__main__":
    unittest.main()
