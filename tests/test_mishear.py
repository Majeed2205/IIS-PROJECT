import unittest

from assistant.chat import Conversation, read_args
from assistant.mishear import misheard_time
from assistant.slots import Calendar

READ_BACK = "So that's a haircut on Friday at 5:30 pm. Is that right?"


class MisheardTimeTests(unittest.TestCase):
    def test_the_nearest_other_free_time_that_day(self):
        calendar = Calendar.load()
        self.assertEqual(misheard_time("17:30", "friday", calendar), "18:15")
        self.assertEqual(misheard_time("18:15", "friday", calendar), "17:30")
        self.assertEqual(misheard_time("19:00", "friday", calendar), "18:15")  # a taken time too
        self.assertEqual(misheard_time("11:00", "monday", calendar), "16:00")
        self.assertEqual(misheard_time("12:00", "thursday", calendar), "10:00")  # a tie takes the earlier one

    def test_nothing_to_mishear_it_as(self):
        calendar = Calendar.load()
        self.assertIsNone(misheard_time("17:30", None, calendar))  # no day yet
        self.assertIsNone(misheard_time("10:00", "saturday", calendar))  # nothing free
        self.assertIsNone(misheard_time("10:00", "sunday", calendar))  # no slots at all
        calendar.get("friday", "12:00").free = False
        calendar.get("friday", "18:15").free = False
        self.assertIsNone(misheard_time("17:30", "friday", calendar))  # the only free time is the one said


class PlantedErrorTests(unittest.TestCase):
    def test_21_a_summary_catches_the_misheard_time(self):
        chat = Conversation(Calendar.load(), "summarise", mishear=True)
        self.assertEqual(chat.reply("A haircut on Friday at half five"),
                         "So that's a haircut on Friday at 6:15 pm. Is that right?")
        self.assertEqual(chat.misheard, ("17:30", "18:15"))
        self.assertEqual(chat.reply("No, I said half five"), READ_BACK)  # a correction is heard as said
        self.assertEqual(chat.reply("Yes"), "Booked: haircut on Friday at 5:30 pm.")

    def test_21_repeat_and_clarify_book_the_misheard_time(self):
        for strategy in ["repeat", "clarify"]:
            chat = Conversation(Calendar.load(), strategy, mishear=True)
            self.assertEqual(chat.reply("A haircut on Friday at half five"), "Booked: haircut on Friday at 6:15 pm.",
                             strategy)

    def test_a_picked_time_is_misheard_too(self):
        chat = Conversation(Calendar.load(), "clarify", mishear=True)
        chat.reply("A haircut on Friday after five")  # a range is not changed
        self.assertIsNone(chat.misheard)
        self.assertEqual(chat.reply("5:30"), "Booked: haircut on Friday at 6:15 pm.")

    def test_only_one_time_per_call(self):
        chat = Conversation(Calendar.load(), "summarise", mishear=True)
        chat.reply("A haircut on Friday at half five")  # heard as 6:15
        self.assertEqual(chat.reply("No, half five"), READ_BACK)
        self.assertEqual(chat.reply("No, 6:15"), "So that's a haircut on Friday at 6:15 pm. Is that right?")
        chat = Conversation(Calendar.load(), "summarise", mishear=True)
        chat.reply("A haircut on Friday at half five")
        self.assertEqual(chat.reply("No"), "Which part should I change: the service, the day or the time?")
        self.assertEqual(chat.reply("half five"), READ_BACK)  # not an answer to a read-back, still heard as said

    def test_a_turn_that_is_not_understood_does_not_use_it_up(self):
        chat = Conversation(Calendar.load(), "clarify", mishear=True)
        chat.reply("A haircut on Friday after five")
        chat.reply("No, 6:15")  # a "no" outside a read-back is not understood (rule 7)
        self.assertIsNone(chat.misheard)
        self.assertEqual(chat.reply("5:30"), "Booked: haircut on Friday at 6:15 pm.")

    def test_it_waits_for_a_day(self):
        chat = Conversation(Calendar.load(), "clarify", mishear=True)
        chat.reply("A haircut at half five")  # no day yet, so nothing to mishear it as
        self.assertIsNone(chat.misheard)
        self.assertEqual(chat.reply("Friday"), "Booked: haircut on Friday at 5:30 pm.")

    def test_it_waits_then_mishears_the_next_time(self):
        chat = Conversation(Calendar.load(), "summarise", mishear=True)
        chat.reply("A haircut at half five")  # no day yet
        self.assertEqual(chat.reply("Friday"), READ_BACK)
        chat.reply("No, the time")
        self.assertEqual(chat.reply("6:15"), READ_BACK)
        self.assertEqual(chat.misheard, ("18:15", "17:30"))

    def test_the_day_said_in_the_turn_comes_first(self):
        chat = Conversation(Calendar.load(), "clarify", mishear=True)
        chat.reply("A haircut on Friday")
        self.assertEqual(chat.reply("Monday at 11"), "Booked: haircut on Monday at 4 pm.")
        self.assertEqual(chat.misheard, ("11:00", "16:00"))

    def test_an_answer_to_a_read_back_is_heard_as_said(self):
        chat = Conversation(Calendar.load(), "summarise", mishear=True)
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("Yes, 6:15"), "So that's a haircut on Friday at 6:15 pm. Is that right?")
        self.assertIsNone(chat.misheard)
        chat = Conversation(Calendar.load(), "summarise", mishear=True)
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("Yes, 5:30"), "Booked: haircut on Friday at 5:30 pm.")
        self.assertIsNone(chat.misheard)

    def test_choices_are_not_changed(self):
        chat = Conversation(Calendar.load(), "clarify", mishear=True)
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("the first one"), "Booked: haircut on Friday at 5:30 pm.")
        self.assertIsNone(chat.misheard)

    def test_off_unless_switched_on(self):
        chat = Conversation(Calendar.load(), "summarise")
        self.assertEqual(chat.reply("A haircut on Friday at half five"), READ_BACK)
        self.assertIsNone(chat.misheard)


class ArgsTests(unittest.TestCase):
    def test_read_args(self):
        self.assertEqual(read_args([]), ("clarify", False))
        self.assertEqual(read_args(["summarise"]), ("summarise", False))
        self.assertEqual(read_args(["summarise", "--mishear"]), ("summarise", True))
        self.assertEqual(read_args(["--mishear", "repeat"]), ("repeat", True))


if __name__ == "__main__":
    unittest.main()
