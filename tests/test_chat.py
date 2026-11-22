import unittest

from assistant.booking import describe
from assistant.chat import GIVE_UP, WHICH_PART, Conversation, read_args
from assistant.slots import Calendar, Slot

READ_BACK = "So that's a haircut on Friday at 5:30 pm. Is that right?"


class ChatTests(unittest.TestCase):
    """Test phrases 1 to 20 from docs/dialogue-spec.md, typed into the loop."""

    def start(self, strategy, calendar=None):
        self.calendar = calendar or Calendar.load()
        return Conversation(self.calendar, strategy)

    def taken(self):
        return [(s.day, s.time) for s in self.calendar.slots if not s.free]

    def test_1_complete_request_is_booked(self):
        for strategy in ("repeat", "clarify"):
            chat = self.start(strategy)
            self.assertEqual(chat.reply("A haircut on Friday at half five"), "Booked: haircut on Friday at 5:30 pm.")

    def test_1_and_10_summarise_reads_back_then_books_on_yes(self):
        chat = self.start("summarise")
        before = self.taken()
        self.assertEqual(chat.reply("A haircut on Friday at half five"), READ_BACK)
        self.assertEqual(self.taken(), before)  # nothing booked yet
        reply = chat.reply("Yes")
        self.assertEqual(reply, describe(chat.booking))
        self.assertEqual(reply, "Booked: haircut on Friday at 5:30 pm.")

    def test_2_asks_for_the_service_then_uses_the_strategy(self):
        expected = {
            "repeat": "Sorry, could you say your whole request again?",
            "clarify": "On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?",
            "summarise": READ_BACK,
        }
        for strategy, reply in expected.items():
            chat = self.start(strategy)
            self.assertEqual(chat.reply("Can I come in on Friday after five?"),
                             "What would you like to book? We offer haircut, colour or beard trim.")
            self.assertEqual(chat.reply("A haircut please"), reply)

    def test_3_clarify_then_pick_an_option(self):
        for answer in ["the second one", "6:15", "six fifteen"]:
            chat = self.start("clarify")
            chat.reply("A haircut on Friday after five")
            self.assertEqual(chat.reply(answer), "Booked: haircut on Friday at 6:15 pm.", answer)

    def test_3_third_of_three_options(self):
        chat = self.start("clarify")
        chat.reply("A haircut on Friday after eleven")
        self.assertEqual(chat.reply("the third one"), "Booked: haircut on Friday at 6:15 pm.")

    def test_3_a_choice_that_was_not_offered(self):
        chat = self.start("clarify")
        question = chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("the third one"), "Sorry, I didn't catch that. " + question)  # rule 8
        self.assertIsNone(chat.booking)

    def test_3_repeat_hands_over_after_two_repeats(self):
        chat = self.start("repeat")
        for _ in range(2):
            self.assertEqual(chat.reply("A haircut on Friday after five"),
                             "Sorry, could you say your whole request again?")
        self.assertIn("member of staff", chat.reply("A haircut on Friday after five"))
        self.assertTrue(chat.finished)
        self.assertEqual(chat.reply("hello?"), "This call has ended.")

    def test_3_repeat_only_counts_asking_again(self):
        chat = self.start("repeat")
        chat.reply("Can I come in on Friday after five?")
        chat.reply("A haircut")  # first ask-again
        self.assertEqual(chat.reply("A haircut on Friday after five"), "Sorry, could you say your whole request again?")
        self.assertFalse(chat.finished)

    def test_3_repeat_books_once_the_time_is_clear(self):
        chat = self.start("repeat")
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("A haircut on Friday at 5:30"), "Booked: haircut on Friday at 5:30 pm.")

    def test_3_summarise_reads_back_the_earliest_then_books_it(self):
        chat = self.start("summarise")
        self.assertEqual(chat.reply("A haircut on Friday after five"), READ_BACK)
        self.assertEqual(chat.reply("yes"), "Booked: haircut on Friday at 5:30 pm.")

    def test_4_taken_slot_then_choose_another(self):
        chat = self.start("clarify")
        self.assertEqual(chat.reply("A haircut on Friday at seven"),
                         "I have nothing free on Friday at 7 pm. "
                         "I can offer Friday at 5:30 pm or 6:15 pm, or you can name another day.")
        self.assertEqual(chat.reply("6:15 then"), "Booked: haircut on Friday at 6:15 pm.")

    def test_4_a_range_replaces_an_exact_time(self):
        chat = self.start("clarify")
        chat.reply("A haircut on Friday at seven")
        self.assertEqual(chat.reply("after five"), "On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?")

    def test_5_offer_on_another_day_can_be_taken(self):
        chat = self.start("clarify")
        self.assertEqual(chat.reply("Colour on Saturday afternoon"),
                         "I have nothing free on Saturday afternoon. "
                         "I can offer Monday at 11 am or 4 pm, or you can name another day.")
        self.assertEqual(chat.reply("4 pm"), "Booked: colour on Monday at 4 pm.")

    def test_5_same_time_on_another_day_is_not_the_offer(self):
        chat = self.start("clarify")
        chat.reply("Colour on Saturday afternoon")
        chat.reply("Tuesday at 4 pm")
        self.assertIsNone(chat.booking)
        self.assertTrue(self.calendar.get("monday", "16:00").free)

    def test_5_yes_to_two_offers_books_nothing(self):
        chat = self.start("clarify")
        chat.reply("Colour on Saturday afternoon")
        chat.reply("yes")
        self.assertIsNone(chat.booking)

    def test_5_a_choice_on_another_day_is_not_the_offer(self):
        chat = self.start("clarify")
        chat.reply("Colour on Saturday afternoon")
        chat.reply("the second one on Tuesday")
        self.assertIsNone(chat.booking)
        self.assertTrue(self.calendar.get("monday", "16:00").free)

    def test_5_yes_takes_a_single_offer(self):
        calendar = Calendar(["haircut"], [Slot("friday", "17:30"), Slot("friday", "19:00", free=False)])
        chat = self.start("clarify", calendar)
        chat.reply("A haircut on Friday at seven")
        self.assertEqual(chat.reply("yes"), "Booked: haircut on Friday at 5:30 pm.")

    def test_6_service_not_offered(self):
        chat = self.start("clarify")
        self.assertEqual(chat.reply("A massage on Monday at eleven"),
                         "Sorry, we don't offer massage. We offer haircut, colour or beard trim.")
        self.assertEqual(chat.reply("a beard trim then"), "Booked: beard trim on Monday at 11 am.")

    def test_7_no_sunday_slots(self):
        chat = self.start("summarise")
        self.assertEqual(chat.reply("Sunday at ten for a haircut"),
                         "I have nothing free on Sunday at 10 am. "
                         "I can offer Monday at 11 am or 4 pm, or you can name another day.")

    def test_8_too_vague(self):
        chat = self.start("clarify")
        self.assertEqual(chat.reply("Sometime next week"), "Sorry, I didn't catch that. Which day would you like to come in?")
        chat.reply("a haircut on Thursday")
        self.assertEqual(chat.reply("before twelve"), "Booked: haircut on Thursday at 10 am.")

    def test_9_correction_changes_only_the_day(self):
        chat = self.start("summarise")
        chat.reply("A haircut on Friday at half five")
        reply = chat.reply("No, I said Thursday")
        self.assertEqual((chat.request.service, chat.request.day, chat.request.time), ("haircut", "thursday", "17:30"))
        self.assertEqual(reply, "I have nothing free on Thursday at 5:30 pm. "
                                "I can offer Thursday at 10 am or 2 pm, or you can name another day.")

    def test_9_corrections_to_the_service_or_time(self):
        cases = {
            "No, a beard trim": "So that's a beard trim on Friday at 5:30 pm. Is that right?",
            "No, 6:15": "So that's a haircut on Friday at 6:15 pm. Is that right?",
            "No, after six": "So that's a haircut on Friday at 6:15 pm. Is that right?",
        }
        for answer, reply in cases.items():
            chat = self.start("summarise")
            chat.reply("A haircut on Friday at half five")
            self.assertEqual(chat.reply(answer), reply, answer)

    def test_10_a_yes_with_a_different_detail_is_a_correction(self):
        cases = {
            "yes, after six": "So that's a haircut on Friday at 6:15 pm. Is that right?",
            "yes, a beard trim": "So that's a beard trim on Friday at 5:30 pm. Is that right?",
            "yes, on Monday": "I have nothing free on Monday after 5 pm. "
                              "I can offer Monday at 11 am or 4 pm, or you can name another day.",
        }
        for answer, reply in cases.items():
            chat = self.start("summarise")
            chat.reply("A haircut on Friday after five")
            self.assertEqual(chat.reply(answer), reply, answer)
            self.assertIsNone(chat.booking, answer)

    def test_10_a_yes_but_is_read_back_again(self):
        for answer in ["yes, but after six", "Yes, but on Monday"]:
            chat = self.start("summarise")
            chat.reply("A haircut on Friday after five")
            self.assertEqual(chat.reply(answer), "Sorry, I didn't catch that. " + READ_BACK, answer)
            self.assertIsNone(chat.booking, answer)

    def test_10_a_yes_that_repeats_the_details_books(self):
        for answer in ["Yes, 5:30 is fine", "yes, Friday at 5:30", "yes, a haircut on Friday"]:
            chat = self.start("summarise")
            chat.reply("A haircut on Friday at half five")
            self.assertEqual(chat.reply(answer), "Booked: haircut on Friday at 5:30 pm.", answer)

    def test_11_book_it_twice_books_once(self):
        chat = self.start("summarise")
        before = len(self.taken())
        chat.reply("A haircut on Friday at half five")
        self.assertEqual(chat.reply("Book it"), "Booked: haircut on Friday at 5:30 pm.")
        self.assertEqual(chat.reply("Book it"),
                         "Your haircut is already booked for Friday at 5:30 pm. I have not booked it twice.")
        self.assertEqual(len(self.taken()), before + 1)

    def test_12_plain_no_asks_which_part(self):
        answers = {
            "the day": "Which day would you like to come in?",
            "the service": "What would you like to book? We offer haircut, colour or beard trim.",
            "the time": "What time on Friday would you like?",
            "the day and the time": "Which day would you like to come in?",
        }
        for answer, reply in answers.items():
            chat = self.start("summarise")
            chat.reply("A haircut on Friday at half five")
            self.assertEqual(chat.reply("No"), WHICH_PART)
            self.assertEqual(chat.reply(answer), reply, answer)

    def test_12_which_part_only_applies_to_the_next_turn(self):
        chat = self.start("summarise")
        chat.reply("A haircut on Friday at half five")
        chat.reply("No")
        chat.reply("the day")
        self.assertEqual(chat.reply("Monday, same time"),
                         "I have nothing free on Monday at 5:30 pm. "
                         "I can offer Monday at 11 am or 4 pm, or you can name another day.")

    def test_12_no_that_names_the_part_skips_the_question(self):
        for answer in ["No, wrong time", "No, the time is wrong"]:
            chat = self.start("summarise")
            chat.reply("A haircut on Friday at half five")
            self.assertEqual(chat.reply(answer), "What time on Friday would you like?", answer)

    def test_14_turning_an_offer_down_is_not_understood(self):
        chat = self.start("clarify")
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("I'm busy at 5:30"),
                         "Sorry, I didn't catch that. On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?")
        self.assertIsNone(chat.booking)

    def test_after_leaves_the_time_itself_out(self):
        chat = self.start("clarify")
        chat.reply("A haircut on Friday after five")
        reply = chat.reply("after 6:15")
        self.assertTrue(reply.startswith("I have nothing free on Friday after 6:15 pm."), reply)
        self.assertIsNone(chat.booking)
        chat = self.start("clarify")
        chat.reply("A haircut on Monday just after 4")
        self.assertIsNone(chat.booking)

    def test_16_friday_is_fine_is_not_a_yes(self):
        chat = self.start("summarise")
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("Friday's fine"), READ_BACK)
        self.assertIsNone(chat.booking)

    def test_17_a_change_of_mind_is_not_understood(self):
        chat = self.start("clarify")
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("5:30, no wait, 6:15"),
                         "Sorry, I didn't catch that. On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?")
        self.assertIsNone(chat.booking)

    def test_18_turning_a_read_back_down_asks_which_part(self):
        chat = self.start("summarise")
        self.assertEqual(chat.reply("A haircut on Monday at 11"), "So that's a haircut on Monday at 11 am. Is that right?")
        self.assertEqual(chat.reply("I can't do Monday"), WHICH_PART)
        self.assertEqual(chat.reply("the day"), "Which day would you like to come in?")
        self.assertIsNone(chat.booking)
        for answer in ["5:30, no wait, 6:15", "I cannot do Friday", "That's incorrect"]:  # other "no" words
            chat = self.start("summarise")
            chat.reply("A haircut on Friday at half five")
            self.assertEqual(chat.reply(answer), WHICH_PART, answer)
            self.assertIsNone(chat.booking, answer)

    def test_20_taking_an_offered_day_after_a_decline_asks_for_the_time(self):
        for strategy in ("repeat", "clarify", "summarise"):
            chat = self.start(strategy)
            self.assertEqual(chat.reply("A haircut on Tuesday at 6"), "I have nothing free on Tuesday at 6 pm. "
                             "I can offer Thursday at 10 am or 2 pm, or you can name another day.", strategy)
            self.assertEqual(chat.reply("Thursday"), "What time on Thursday would you like?", strategy)
            self.assertIsNone(chat.booking, strategy)
        chat = self.start("summarise")
        chat.reply("A haircut on Friday at half five")
        chat.reply("No, I said Thursday")  # test phrase 9: declined, Thursday at 10 am or 2 pm offered
        self.assertEqual(chat.reply("Thursday"), "What time on Thursday would you like?")

    def test_after_a_decline_a_time_that_is_free_on_the_offered_day_is_kept(self):
        chat = self.start("clarify")
        chat.reply("Colour on Saturday at 4 pm")  # declined: Monday at 11 am or 4 pm is offered
        self.assertEqual(chat.reply("Monday"), "Booked: colour on Monday at 4 pm.")

    def test_after_a_decline_a_day_that_was_not_offered_keeps_the_time(self):
        chat = self.start("clarify")
        chat.reply("A haircut on Tuesday at 6")  # declined: Thursday is offered
        self.assertEqual(chat.reply("Friday"), "I have nothing free on Friday at 6 pm. "
                         "I can offer Friday at 5:30 pm or 6:15 pm, or you can name another day.")

    def test_after_a_decline_a_time_said_with_an_offered_day_is_kept(self):
        for answer, when in [("Thursday at 6", "Thursday at 6 pm"), ("Thursday evening", "Thursday evening")]:
            chat = self.start("clarify")
            chat.reply("A haircut on Tuesday at 6")  # declined: Thursday at 10 am or 2 pm is offered
            self.assertEqual(chat.reply(answer), f"I have nothing free on {when}. "
                             "I can offer Thursday at 10 am or 2 pm, or you can name another day.", answer)

    def test_after_a_decline_an_old_time_or_range_that_is_not_free_is_forgotten(self):
        for first in ["A haircut on Tuesday at 12", "A haircut on Thursday evening"]:  # 12 pm is between 10 am and 2 pm
            chat = self.start("clarify")
            chat.reply(first)  # declined: Thursday at 10 am or 2 pm is offered
            self.assertEqual(chat.reply("Thursday"), "What time on Thursday would you like?", first)

    def test_after_a_decline_a_range_that_is_free_on_the_offered_day_is_kept(self):
        chat = self.start("clarify")
        chat.reply("Colour on Saturday afternoon")  # test phrase 5: Monday at 11 am or 4 pm is offered
        self.assertEqual(chat.reply("Monday"), "Booked: colour on Monday at 4 pm.")

    def test_after_test_phrase_20_an_offered_slot_can_still_be_picked(self):
        expected = {"repeat": "Booked: haircut on Thursday at 10 am.", "clarify": "Booked: haircut on Thursday at 10 am.",
                    "summarise": "So that's a haircut on Thursday at 10 am. Is that right?"}
        for strategy, said in expected.items():
            chat = self.start(strategy)
            chat.reply("A haircut on Tuesday at 6")
            chat.reply("Thursday")  # "What time on Thursday would you like?"
            self.assertEqual(chat.reply("the first one"), said, strategy)

    def test_an_offered_slot_can_still_be_picked_after_the_service_question(self):
        chat = self.start("clarify")  # the terminal chat that found this
        for said in ["at 6", "tuesday", "thursday"]:  # Tuesday at 6 pm is declined; Thursday at 10 am or 2 pm offered
            chat.reply(said)
        self.assertEqual(chat.reply("beard trim"), "What time on Thursday would you like?")
        self.assertEqual(chat.reply("the first one"), "Booked: beard trim on Thursday at 10 am.")

    def test_an_offered_slot_can_still_be_picked_after_a_turn_that_is_not_understood(self):
        chat = self.start("clarify")
        chat.reply("A haircut on Tuesday at 6")
        chat.reply("Thursday")
        self.assertEqual(chat.reply("hmm"), "Sorry, I didn't catch that. What time on Thursday would you like?")
        self.assertEqual(chat.reply("the first one"), "Booked: haircut on Thursday at 10 am.")

    def test_slots_offered_for_another_day_cannot_be_picked(self):
        chat = self.start("clarify")
        chat.reply("A haircut on Sunday")  # declined: Monday at 11 am or 4 pm is offered
        self.assertEqual(chat.reply("Friday"), "What time on Friday would you like?")
        self.assertEqual(chat.reply("the first one"),  # not Monday at 11 am: nothing on Friday was offered
                         "Sorry, I didn't catch that. What time on Friday would you like?")
        self.assertIsNone(chat.booking)

    def test_the_first_one_after_the_service_question_is_not_a_pick(self):
        chat = self.start("clarify")
        chat.reply("Can I come in on Tuesday at 6?")  # declined: Thursday at 10 am or 2 pm is offered
        chat.reply("Thursday at 2 pm")  # "What would you like to book? We offer haircut, colour or beard trim."
        chat.reply("the first one")
        self.assertEqual(chat.reply("a haircut please"), "Booked: haircut on Thursday at 2 pm.")

    def test_a_yes_that_names_another_day_does_not_take_a_single_offer(self):
        calendar = Calendar(["haircut"], [Slot("thursday", "10:00"), Slot("friday", "17:30")])
        chat = self.start("clarify", calendar)
        self.assertEqual(chat.reply("A haircut on Tuesday at 6"), "I have nothing free on Tuesday at 6 pm. "
                         "I can offer Thursday at 10 am, or you can name another day.")
        self.assertEqual(chat.reply("Yes, Friday"), "I have nothing free on Friday at 6 pm. "
                         "I can offer Friday at 5:30 pm, or you can name another day.")
        self.assertIsNone(chat.booking)  # rule 8: a pick that names a different day does not count

    def test_a_yes_that_names_the_offered_day_takes_a_single_offer(self):
        for said, booked in [("Yes, Thursday", ("thursday", "10:00")), ("Yes, Tuesday", None)]:
            calendar = Calendar(["haircut"], [Slot("thursday", "10:00"), Slot("friday", "17:30")])
            chat = self.start("clarify", calendar)
            chat.reply("A haircut on Tuesday at 6")  # declined: Thursday at 10 am is offered
            chat.reply(said)
            self.assertEqual(chat.booking and (chat.booking.day, chat.booking.time), booked, said)

    def test_a_yes_with_a_time_does_not_take_a_single_offer(self):
        for turns in [["A haircut on Tuesday at 6", "yes, after six"], ["A haircut on Tuesday at 6", "Thursday", "Sure, at 3"],
                      ["A haircut on Wednesday", "Thursday", "OK, 6 pm"]]:
            calendar = Calendar(["haircut"], [Slot("thursday", "10:00"), Slot("friday", "17:30")])
            chat = self.start("clarify", calendar)
            for said in turns:
                reply = chat.reply(said)
            self.assertIsNone(chat.booking, turns)  # rule 8: the time decides, and 10 am is not after six, at 3 or at 6
            self.assertTrue(reply.startswith("I have nothing free"), reply)

    def test_offered_slots_can_still_be_picked_after_a_service_decline(self):
        chat = self.start("clarify")
        chat.reply("A haircut on Tuesday at 6")  # declined: Thursday at 10 am or 2 pm is offered
        chat.reply("Thursday")
        self.assertEqual(chat.reply("a massage"), "Sorry, we don't offer massage. We offer haircut, colour or beard trim.")
        chat.reply("a haircut")  # "What time on Thursday would you like?"
        self.assertEqual(chat.reply("the first one"), "Booked: haircut on Thursday at 10 am.")

    def test_19_turning_a_read_back_down_without_a_no_word_is_not_understood(self):
        chat = self.start("summarise")
        chat.reply("A haircut on Friday at half five")
        self.assertEqual(chat.reply("I'm busy at 5:30"), "Sorry, I didn't catch that. " + READ_BACK)
        self.assertIsNone(chat.booking)

    def test_15_three_turns_not_understood_hand_over(self):
        for strategy in ("repeat", "clarify", "summarise"):
            chat = self.start(strategy)
            chat.reply("A haircut on Friday")
            for _ in range(2):
                self.assertTrue(chat.reply("I'm busy").startswith("Sorry, I didn't catch that."), strategy)
            self.assertEqual(chat.reply("I'm busy"), GIVE_UP, strategy)
            self.assertTrue(chat.finished)
            self.assertIsNone(chat.booking)

    def test_repeat_does_not_say_sorry_twice(self):
        chat = self.start("repeat")
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("I'm busy"), "Sorry, could you say your whole request again?")

    def test_an_understood_turn_starts_the_count_again(self):
        chat = self.start("clarify")
        chat.reply("A haircut on Friday")
        chat.reply("I'm busy")
        chat.reply("I'm busy")
        self.assertEqual(chat.reply("after five"), "On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?")
        chat.reply("I'm busy")
        chat.reply("I'm busy")
        self.assertFalse(chat.finished)

    def test_a_no_to_a_read_back_starts_the_count_again(self):
        chat = self.start("summarise")
        chat.reply("A haircut on Friday at half five")
        chat.reply("I'm busy")
        chat.reply("I'm busy")
        self.assertEqual(chat.reply("No"), WHICH_PART)
        chat.reply("I'm busy")
        self.assertFalse(chat.finished)

    def test_a_no_that_is_not_understood_still_counts_towards_the_handover(self):
        chat = self.start("summarise")
        chat.reply("A haircut on Friday at half five")
        chat.reply("I'm busy")
        chat.reply("I'm busy")
        self.assertEqual(chat.reply("I can't do Friday"), GIVE_UP)
        self.assertTrue(chat.finished)
        chat = self.start("summarise")
        chat.reply("A haircut on Monday at 11")
        for _ in range(3):
            reply = chat.reply("I can't do Monday")
        self.assertEqual(reply, GIVE_UP)  # the call cannot go round in circles
        self.assertIsNone(chat.booking)

    def test_an_understood_turn_that_changes_nothing_starts_the_count_again(self):
        chat = self.start("summarise")
        chat.reply("A haircut on Friday at half five")
        chat.reply("I'm busy")
        chat.reply("I'm busy")
        self.assertEqual(chat.reply("Friday's fine"), READ_BACK)  # understood, but not a yes (rule 9)
        self.assertEqual(chat.reply("I'm busy"), "Sorry, I didn't catch that. " + READ_BACK)
        self.assertFalse(chat.finished)

    def test_a_no_that_names_the_part_starts_the_count_again(self):
        chat = self.start("summarise")
        chat.reply("A haircut on Friday at half five")
        chat.reply("I'm busy")
        chat.reply("I'm busy")
        self.assertEqual(chat.reply("No, wrong time"), "What time on Friday would you like?")
        self.assertEqual(chat.reply("I'm busy"), "Sorry, I didn't catch that. What time on Friday would you like?")
        self.assertFalse(chat.finished)

    def test_a_handover_ends_the_call(self):
        cases = [("repeat", ["A haircut on Friday after five"] * 3),
                 ("clarify", ["A haircut on Friday", "I'm busy", "I'm busy", "I'm busy"])]
        for strategy, turns in cases:
            chat = self.start(strategy)
            for turn in turns:
                chat.reply(turn)
            self.assertTrue(chat.finished, strategy)
            self.assertEqual(chat.reply("A haircut on Friday at half five"), "This call has ended.", strategy)
            self.assertIsNone(chat.booking, strategy)

    def test_a_no_after_a_booking_gets_all_booked(self):
        for answer in ["No", "not Friday"]:
            chat = self.start("summarise")
            chat.reply("A haircut on Friday at half five")
            chat.reply("Yes")
            self.assertEqual(chat.reply(answer), "You're all booked. Thank you for calling.", answer)

    def test_13_decline_early(self):
        chat = self.start("clarify")
        self.assertEqual(chat.reply("Can I come in on Sunday?"),
                         "I have nothing free on Sunday. "
                         "I can offer Monday at 11 am or 4 pm, or you can name another day.")


class SafetyTests(unittest.TestCase):
    """The caller must never get a booking they did not ask for."""

    def test_summarise_books_nothing_until_yes(self):
        for answer in ["That isn't right", "I don't think that's right", "Are you sure?",
                       "Don't book it yet", "wait", "No"]:
            calendar = Calendar.load()
            chat = Conversation(calendar, "summarise")
            chat.reply("A haircut on Friday at half five")
            chat.reply(answer)
            self.assertIsNone(chat.booking, answer)
            self.assertTrue(calendar.get("friday", "17:30").free, answer)

    def test_yes_after_which_part_books_nothing(self):
        chat = Conversation(Calendar.load(), "summarise")
        chat.reply("A haircut on Friday at half five")
        chat.reply("No")
        self.assertEqual(chat.reply("yes"), WHICH_PART)  # a yes names no part (rule 6)
        self.assertIsNone(chat.booking)

    def test_offers_are_not_chosen_by_accident(self):
        cases = [
            ("A haircut on Friday after five", "just a second"),
            ("A haircut on Friday after five", "Good afternoon"),
            ("A haircut on Thursday at 5:30", "first thing Friday then"),
        ]
        for first, second in cases:
            calendar = Calendar.load()
            chat = Conversation(calendar, "clarify")
            chat.reply(first)
            chat.reply(second)
            self.assertIsNone(chat.booking, second)

    def test_turning_something_down_books_nothing(self):
        offer = "Sorry, I didn't catch that. On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?"
        for answer in ["not 5:30, 6:15 please", "I can't do 5:30", "5:30 is too early", "no 5:30",
                       "5:30, no wait, 6:15", "The first one doesn't work for me", "what was the second one?"]:
            chat = Conversation(Calendar.load(), "clarify")
            chat.reply("A haircut on Friday after five")
            self.assertEqual(chat.reply(answer), offer, answer)
            self.assertIsNone(chat.booking, answer)

    def test_a_question_books_nothing(self):
        cases = [
            ("clarify", "A haircut on Thursday after six", "You said Friday?"),
            ("clarify", "A haircut on Thursday after six", "You said I can come Friday?"),
            ("clarify", "A haircut on Thursday after six", "Friday at 5:30?"),
            ("clarify", "A haircut on Friday after five", "6:15?"),
            ("clarify", "A haircut on Friday after five", "The first one?"),
            ("repeat", "A haircut on Friday after five", "6:15, is it?"),
            # No "?", but still a question (rule 7).
            ("summarise", "A haircut on Friday at half five", "OK, is that right"),
            ("summarise", "A haircut on Friday at half five", "Yes, is that Friday"),
            ("summarise", "A haircut on Friday at half five", "OK great, is 5:30 right"),
            ("clarify", "A haircut on Thursday after six", "And is that Friday"),
            ("clarify", "A haircut on Friday after five", "Right, is that the 6:15"),
            ("clarify", "Colour on Saturday afternoon", "Yes thanks, is Friday ok"),
            ("repeat", "A haircut on Friday after five", "6:15, is it"),
        ]
        for strategy, first, question in cases:
            chat = Conversation(Calendar.load(), strategy)
            said = chat.reply(first)
            again = said if strategy == "repeat" else "Sorry, I didn't catch that. " + said
            self.assertEqual(chat.reply(question), again, question)
            self.assertIsNone(chat.booking, question)

    def test_a_no_word_question_at_a_read_back_asks_which_part(self):
        chat = Conversation(Calendar.load(), "summarise")
        chat.reply("A haircut on Friday at half five")
        self.assertEqual(chat.reply("No, is it 6:15"), WHICH_PART)  # rule 6
        self.assertIsNone(chat.booking)

    def test_a_request_with_a_question_mark_still_books(self):
        chat = Conversation(Calendar.load(), "clarify")
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("Could I have the 6:15?"), "Booked: haircut on Friday at 6:15 pm.")

    def test_a_no_outside_a_read_back_changes_nothing(self):
        cases = [
            ([], "No, a haircut on Friday at half five", "Which day would you like to come in?"),
            (["A haircut on Friday at seven"], "No, 6:15",
             "I have nothing free on Friday at 7 pm. I can offer Friday at 5:30 pm or 6:15 pm, or you can name another day."),
            (["Can I come in on Friday after five?"], "No, a haircut",
             "What would you like to book? We offer haircut, colour or beard trim."),
            (["A haircut on Friday after five"], "No, the time",
             "On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?"),
        ]
        for before, answer, question in cases:
            chat = Conversation(Calendar.load(), "clarify")
            for turn in before:
                chat.reply(turn)
            self.assertEqual(chat.reply(answer), "Sorry, I didn't catch that. " + question, answer)
            self.assertIsNone(chat.booking, answer)

    def test_hesitating_at_a_read_back_books_nothing(self):
        for answer in ["OK, let me check my diary", "Right, I'll call back later", "ok hang on", "5:30, right?",
                       "ok, just a second",
                       "are you sure", "Yes, but later", "fine, six then", "That isn’t right", "dont book it yet",
                       "5:30, no wait, 6:15", "I can't do Friday"]:
            chat = Conversation(Calendar.load(), "summarise")
            chat.reply("A haircut on Friday at half five")
            chat.reply(answer)
            self.assertIsNone(chat.booking, answer)

    def test_rejecting_a_day_or_service_books_nothing(self):
        cases = [
            ("clarify", "A haircut at half five", "Any day but Friday"),
            ("clarify", "Colour on Saturday afternoon", "I can't do Monday"),
            ("clarify", "Can I come in on Friday at half five?", "Just a haircut, no colour"),
            ("repeat", "A haircut in the afternoon", "Thursday please, Monday's no good"),
            ("clarify", "A haircut on Thursday", "Not in the morning"),
            ("clarify", "A haircut on Thursday", "Two haircuts"),
            ("clarify", "A haircut on Thursday", "at ten to two"),
        ]
        for strategy, first, second in cases:
            chat = Conversation(Calendar.load(), strategy)
            chat.reply(first)
            chat.reply(second)
            self.assertIsNone(chat.booking, second)

    def test_a_greeting_does_not_pick_a_time(self):
        for text in ["Good afternoon, can I book a haircut on Friday?", "Afternoon! Can I book a haircut on Friday?"]:
            chat = Conversation(Calendar.load(), "clarify")
            self.assertEqual(chat.reply(text), "What time on Friday would you like?", text)

    def test_a_time_of_day_later_in_the_call_is_not_a_greeting(self):
        chat = Conversation(Calendar.load(), "clarify")
        chat.reply("Colour on Saturday afternoon")
        self.assertEqual(chat.reply("Morning on Monday, please"), "Booked: colour on Monday at 11 am.")

    def test_sentences_the_reader_does_not_fully_understand_book_nothing(self):
        cases = [
            ("clarify", "A haircut on Friday after five", ["I'm busy at 5:30", "5:30 is a bit early for me",
                                                        "Is 6:15 the latest?", "How long is the 5:30 one?",
                                                        "Anything after 6:15?", "quarter to 6pm"]),
            ("clarify", "Colour on Saturday afternoon", ["I work on Monday", "Monday's bad", "did you say Friday?",
                                                       "was that Thursday"]),
            ("repeat", "A haircut on Thursday", ["between 3 and 5", "twenty past ten in the morning",
                                               "ten to 2pm", "afternoon, 3ish"]),
            ("clarify", "Can I come in on Friday at half five?", ["cut and colour", "a cut and a beard trim"]),
            ("clarify", "A haircut on Friday after five", ["5:30 and 6:15", "the first one and the second one"]),
            ("clarify", "A haircut on Thursday", ["ten past two", "three in the afternoon", "four in the afternoon"]),
            ("clarify", "Colour on Saturday afternoon", ["Monday 11", "Thursday 10", "11 on Monday"]),
            ("clarify", "A haircut on Friday after five", ["6:15 for a colour and a beard trim"]),
            ("clarify", "A haircut on Monday", ["quarter after four", "a quarter after 3"]),
            ("clarify", "A haircut on Thursday", ["at 10 in the evening", "before 11 in the evening"]),
        ]
        for strategy, first, answers in cases:
            for answer in answers:
                chat = Conversation(Calendar.load(), strategy)
                chat.reply(first)
                chat.reply(answer)
                self.assertIsNone(chat.booking, answer)

    def test_agreeing_with_one_detail_is_not_a_yes(self):
        for answer in ["Friday's fine", "The haircut's fine", "5:30 is ok"]:
            chat = Conversation(Calendar.load(), "summarise")
            chat.reply("A haircut on Friday after five")
            chat.reply(answer)
            self.assertIsNone(chat.booking, answer)

    def test_a_greeting_after_hello_is_still_a_greeting(self):
        chat = Conversation(Calendar.load(), "clarify")
        chat.reply("Hello")
        self.assertEqual(chat.reply("Afternoon! Can I book a haircut on Friday?"), "What time on Friday would you like?")

    def test_a_yes_with_another_part_of_the_day_or_service_is_not_a_yes(self):
        for answer in ["Evening is fine", "yes, a trim please", "Yes, the beard"]:
            chat = Conversation(Calendar.load(), "summarise")
            chat.reply("A haircut on Friday after eleven")
            chat.reply(answer)
            self.assertIsNone(chat.booking, answer)

    def test_a_choice_with_a_time_goes_by_the_time(self):
        chat = Conversation(Calendar.load(), "clarify")
        chat.reply("A haircut on Friday after eleven")
        self.assertEqual(chat.reply("the first one after six"), "Booked: haircut on Friday at 6:15 pm.")
        chat = Conversation(Calendar.load(), "clarify")
        chat.reply("A haircut on Friday after eleven")
        self.assertEqual(chat.reply("the first one in the evening"),
                         "On Friday evening I have 5:30 pm or 6:15 pm. Which would you like?")

    def test_a_no_outside_a_read_back_is_not_taken(self):
        chat = Conversation(Calendar.load(), "clarify")
        chat.reply("A haircut on Friday after five")
        self.assertEqual(chat.reply("No, a beard trim"),
                         "Sorry, I didn't catch that. On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?")

    def test_noon_replaces_the_old_time(self):
        chat = Conversation(Calendar.load(), "clarify")
        chat.reply("A haircut on Thursday at 5:30")
        self.assertEqual(chat.reply("Friday at noon"), "Booked: haircut on Friday at 12 pm.")

    def test_after_booking_other_input_does_not_book_again(self):
        calendar = Calendar.load()
        chat = Conversation(calendar, "clarify")
        chat.reply("A haircut on Friday at half five")
        self.assertEqual(chat.reply("thanks"), "You're all booked. Thank you for calling.")
        self.assertEqual(chat.reply("A colour on Monday at eleven"), "You're all booked. Thank you for calling.")
        self.assertTrue(calendar.get("monday", "11:00").free)

    def test_a_failed_booking_is_not_kept(self):
        calendar = Calendar.load()
        first = Conversation(calendar, "summarise", call_id="call-1")
        second = Conversation(calendar, "clarify", call_id="call-2")
        first.reply("A haircut on Friday at half five")
        second.reply("A haircut on Friday at half five")
        self.assertEqual(first.reply("yes"), "Not booked: Friday at 5:30 pm is already taken.")
        self.assertIsNone(first.booking)
        first.reply("6:15")
        self.assertEqual(first.reply("yes"), "Booked: haircut on Friday at 6:15 pm.")

    def test_unknown_strategy_is_an_error(self):
        with self.assertRaises(ValueError):
            Conversation(Calendar.load(), "guess")


class LoopTests(unittest.TestCase):
    """A call must not go round in circles (v0.6), and repeat must only count real repeats."""

    def replies(self, strategy, turns):
        chat = Conversation(Calendar.load(), strategy)
        return [chat.reply(turn) for turn in turns], chat

    def test_a_turn_not_understood_is_not_a_repeat(self):
        again = "Sorry, could you say your whole request again?"
        handover = "I'm sorry, I couldn't find one time that fits. I'll ask a member of staff to call you back."
        said, chat = self.replies("repeat", ["A haircut on Friday after five", "I'm busy",
                                             "A haircut on Friday after five", "A haircut on Friday after five"])
        self.assertEqual(said, [again, again, again, handover])
        said, chat = self.replies("repeat", ["A haircut on Friday after five", "A haircut on Friday after five",
                                             "A haircut on Friday after five", "I'm busy"])
        self.assertEqual(said[2:], [handover, "This call has ended."])
        said, chat = self.replies("repeat", ["A haircut on Friday after five", "A haircut on Friday after five",
                                             "I'm busy", "A haircut on Friday after five"])
        self.assertEqual(said, [again, again, again, handover])  # rule 7, then the second real repeat
        said, chat = self.replies("repeat", ["A haircut on Friday after five", "I'm busy", "I'm busy", "I'm busy"])
        self.assertEqual(said[3], GIVE_UP)  # three turns not understood still hand over

    def test_a_plain_no_after_which_part_asks_again_and_counts(self):
        said, chat = self.replies("summarise", ["A haircut on Friday at half five", "No", "No", "Yes", "No"])
        self.assertEqual(said[1:4], [WHICH_PART, WHICH_PART, WHICH_PART])
        self.assertEqual(said[4], GIVE_UP)
        self.assertIsNone(chat.booking)
        said, chat = self.replies("summarise", ["A haircut on Friday at half five", "No", "Thursday?"])
        self.assertEqual(said[2], "Sorry, I didn't catch that. " + WHICH_PART)

    def test_after_which_part_a_part_or_a_detail_still_works(self):
        said, chat = self.replies("summarise", ["A haircut on Friday at half five", "No", "No", "the time"])
        self.assertEqual(said[3], "What time on Friday would you like?")
        said, chat = self.replies("summarise", ["A haircut on Friday at half five", "No", "No", "6:15"])
        self.assertEqual(said[3], "So that's a haircut on Friday at 6:15 pm. Is that right?")

    def test_a_no_that_repeats_the_read_back_asks_which_part(self):
        for text in ["No, Friday's fine", "No, 5:30 is fine", "No, a haircut", "No, after five"]:
            said, chat = self.replies("summarise", ["A haircut on Friday at half five", text])
            self.assertEqual(said[1], WHICH_PART, text)
        said, chat = self.replies("summarise", ["A haircut on Friday at half five"] + ["No, Friday's fine"] * 5)
        self.assertEqual(said[1:], [WHICH_PART] * 3 + [GIVE_UP, "This call has ended."])  # rule 6, then rule 7
        said, chat = self.replies("summarise", ["A haircut on Friday at half five", "No", "Friday"])
        self.assertEqual(said[2], READ_BACK)  # a detail without a "no" is still read back
        said, chat = self.replies("summarise", ["A haircut on Friday at half five", "No, I said Thursday"])
        self.assertNotEqual(said[1], WHICH_PART)  # a new detail is still a correction (rule 5)

    def test_a_pick_with_nothing_to_pick_is_not_understood(self):
        said, chat = self.replies("clarify", ["the first one", "the first one", "the first one"])
        self.assertEqual(said[:2], ["Sorry, I didn't catch that. Which day would you like to come in?"] * 2)
        self.assertEqual(said[2], GIVE_UP)
        offer = "On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?"
        said, chat = self.replies("clarify", ["A haircut on Friday after five", "the third one", "the second one"])
        self.assertEqual(said[1:], ["Sorry, I didn't catch that. " + offer, "Booked: haircut on Friday at 6:15 pm."])

    def test_a_time_said_with_a_pick_that_cannot_be_made_still_decides(self):
        said, chat = self.replies("clarify", ["A haircut on Friday", "the first one after six"])
        self.assertEqual(said[1], "Booked: haircut on Friday at 6:15 pm.")
        said, chat = self.replies("clarify", ["A haircut on Friday after five", "the third one at 6:15"])
        self.assertEqual(said[1], "Booked: haircut on Friday at 6:15 pm.")
        said, chat = self.replies("clarify", ["A beard trim", "the first one on Monday"])
        self.assertEqual(said[1], "What time on Monday would you like?")

    def test_a_no_with_a_pick_that_cannot_be_made_asks_which_part(self):
        said, chat = self.replies("summarise", ["A haircut on Friday at half five", "No, the first one"])
        self.assertEqual(said[1], WHICH_PART)  # not understood, with a "no" after a read-back (rule 7)
        self.assertEqual(chat.not_understood, 1)
        said, chat = self.replies("summarise", ["A haircut on Friday at half five", "No", "the first one, the time"])
        self.assertEqual(said[2], "What time on Friday would you like?")


class ArgsTests(unittest.TestCase):
    def test_read_args(self):
        self.assertEqual(read_args([]), ("clarify", False, False))
        self.assertEqual(read_args(["summarise"]), ("summarise", False, False))
        self.assertEqual(read_args(["summarise", "--mishear"]), ("summarise", True, False))
        self.assertEqual(read_args(["--mishear", "repeat"]), ("repeat", True, False))
        self.assertEqual(read_args(["repeat", "--log"]), ("repeat", False, True))
        self.assertEqual(read_args(["--log", "--mishear", "summarise"]), ("summarise", True, True))


if __name__ == "__main__":
    unittest.main()
