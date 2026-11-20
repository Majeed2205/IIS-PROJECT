import unittest

from assistant.policy import (
    ASK,
    ASK_AGAIN,
    BOOK,
    CLARIFY,
    CONFIRM,
    DAY_PARTS,
    DECLINE,
    HANDOVER,
    MAX_OPTIONS,
    STRATEGIES,
    Request,
    decide,
)
from assistant.slots import Calendar, Slot


class SpecPhraseTests(unittest.TestCase):
    """Test phrases 1 to 8 and 13 from docs/dialogue-spec.md.

    Each phrase is written as the Request the understanding step (step 4,
    model.py) should produce for it. Phrases 9 to 12 and 14 to 20 need the
    conversation loop (step 3) and are tested in test_chat.py.
    """

    def setUp(self):
        self.calendar = Calendar.load()

    def test_1_complete_and_free(self):
        # "A haircut on Friday at half five"
        request = Request(service="haircut", day="friday", time="17:30")
        for strategy in ("repeat", "clarify"):
            action = decide(request, strategy, self.calendar)
            self.assertEqual(action.kind, BOOK)
            self.assertEqual((action.slot.day, action.slot.time), ("friday", "17:30"))
            self.assertEqual(action.say, "")  # the loop speaks describe(result)
        action = decide(request, "summarise", self.calendar)
        self.assertEqual(action.kind, CONFIRM)
        self.assertEqual(action.say, "So that's a haircut on Friday at 5:30 pm. Is that right?")

    def test_2_service_missing_and_time_ambiguous(self):
        # "Can I come in on Friday after five?"
        request = Request(day="friday", earliest="17:01")
        for strategy in STRATEGIES:
            action = decide(request, strategy, self.calendar)
            self.assertEqual(action.kind, ASK)
            self.assertEqual(action.detail, "service")
            self.assertEqual(action.say, "What would you like to book? We offer haircut, colour or beard trim.")

    def test_3_clarify_offers_both_times(self):
        # "A haircut on Friday after five"
        request = Request(service="haircut", day="friday", earliest="17:01")
        action = decide(request, "clarify", self.calendar)
        self.assertEqual(action.kind, CLARIFY)
        self.assertEqual([s.time for s in action.options], ["17:30", "18:15"])
        self.assertEqual(action.say, "On Friday after 5 pm I have 5:30 pm or 6:15 pm. Which would you like?")

    def test_3_repeat_asks_again_then_hands_over(self):
        request = Request(service="haircut", day="friday", earliest="17:01")
        self.assertEqual(decide(request, "repeat", self.calendar, repeats_asked=0).kind, ASK_AGAIN)
        self.assertEqual(decide(request, "repeat", self.calendar, repeats_asked=1).kind, ASK_AGAIN)
        action = decide(request, "repeat", self.calendar, repeats_asked=2)
        self.assertEqual(action.kind, HANDOVER)
        self.assertEqual(
            action.say,
            "I'm sorry, I couldn't find one time that fits. I'll ask a member of staff to call you back.",
        )

    def test_3_summarise_reads_back_the_earliest(self):
        request = Request(service="haircut", day="friday", earliest="17:01")
        action = decide(request, "summarise", self.calendar)
        self.assertEqual(action.kind, CONFIRM)
        self.assertEqual(action.slot.time, "17:30")

    def test_4_taken_slot_is_declined_with_same_day_options(self):
        # "A haircut on Friday at seven"
        request = Request(service="haircut", day="friday", time="19:00")
        for strategy in STRATEGIES:
            action = decide(request, strategy, self.calendar)
            self.assertEqual(action.kind, DECLINE)
            self.assertEqual([s.time for s in action.options], ["17:30", "18:15"])
            self.assertEqual(
                action.say,
                "I have nothing free on Friday at 7 pm. "
                "I can offer Friday at 5:30 pm or 6:15 pm, or you can name another day.",
            )

    def test_5_nothing_free_offers_the_next_day(self):
        # "Colour on Saturday afternoon"
        request = Request(service="colour", day="saturday", earliest="12:00", latest="16:59")
        action = decide(request, "clarify", self.calendar)
        self.assertEqual(action.kind, DECLINE)
        self.assertEqual([(s.day, s.time) for s in action.options], [("monday", "11:00"), ("monday", "16:00")])
        # Word for word the Decline example in the spec.
        self.assertEqual(
            action.say,
            "I have nothing free on Saturday afternoon. "
            "I can offer Monday at 11 am or 4 pm, or you can name another day.",
        )

    def test_6_service_not_offered(self):
        # "A massage on Monday at eleven"
        request = Request(service="massage", day="monday", time="11:00")
        action = decide(request, "clarify", self.calendar)
        self.assertEqual(action.kind, DECLINE)
        self.assertEqual(action.options, ())
        self.assertEqual(action.say, "Sorry, we don't offer massage. We offer haircut, colour or beard trim.")

    def test_7_no_slots_on_sunday(self):
        # "Sunday at ten for a haircut"
        request = Request(service="haircut", day="sunday", time="10:00")
        action = decide(request, "summarise", self.calendar)
        self.assertEqual(action.kind, DECLINE)
        self.assertEqual([(s.day, s.time) for s in action.options], [("monday", "11:00"), ("monday", "16:00")])
        self.assertTrue(action.say.endswith("or you can name another day."))

    def test_8_too_vague(self):
        # "Sometime next week": nothing usable was said.
        action = decide(Request(), "clarify", self.calendar)
        self.assertEqual(action.kind, ASK)
        self.assertEqual(action.detail, "day")

    def test_13_decline_early_instead_of_asking_for_the_service(self):
        # "Can I come in on Sunday?"
        for strategy in STRATEGIES:
            action = decide(Request(day="sunday"), strategy, self.calendar)
            self.assertEqual(action.kind, DECLINE)
            self.assertEqual([(s.day, s.time) for s in action.options], [("monday", "11:00"), ("monday", "16:00")])
            self.assertEqual(
                action.say,
                "I have nothing free on Sunday. I can offer Monday at 11 am or 4 pm, or you can name another day.",
            )


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.calendar = Calendar.load()

    def decide(self, request, strategy="clarify", repeats_asked=0):
        return decide(request, strategy, self.calendar, repeats_asked)

    # Rule 1: missing details, asked for day, then service, then time.

    def test_missing_details_are_asked_for_day_then_service_then_time(self):
        self.assertEqual(self.decide(Request(service="haircut", time="17:30")).detail, "day")
        self.assertEqual(self.decide(Request(day="friday", time="17:30")).detail, "service")
        self.assertEqual(self.decide(Request(day="friday")).detail, "service")
        action = self.decide(Request(service="haircut", day="friday"))
        self.assertEqual(action.detail, "time")
        self.assertEqual(action.say, "What time on Friday would you like?")

    def test_a_word_that_is_not_a_weekday_counts_as_no_day(self):
        self.assertEqual(self.decide(Request(service="haircut", day="tomorrow", time="17:30")).detail, "day")

    def test_an_empty_word_counts_as_not_said(self):
        self.assertEqual(self.decide(Request(service="", day="friday", time="17:30")).detail, "service")

    def test_words_are_matched_without_case_or_spaces(self):
        self.assertEqual(self.decide(Request(service=" Haircut ", day="FRIDAY", time="17:30")).kind, BOOK)

    # Rules 2 and 3, and the time words.

    def test_time_words_match_the_spec_table(self):
        self.assertEqual(DAY_PARTS, {
            "morning": ("00:00", "11:59"),
            "afternoon": ("12:00", "16:59"),
            "evening": ("17:00", "23:59"),
        })

    def test_friday_evening_offers_both_evening_slots(self):
        action = self.decide(Request(service="haircut", day="friday", earliest="17:00", latest="23:59"))
        self.assertEqual([s.time for s in action.options], ["17:30", "18:15"])
        self.assertEqual(action.say, "On Friday evening I have 5:30 pm or 6:15 pm. Which would you like?")

    def test_a_before_range_with_one_match_is_booked(self):
        # Thursday "before twelve": only 10:00 is free.
        action = self.decide(Request(service="haircut", day="thursday", latest="11:59"))
        self.assertEqual((action.kind, action.slot.time), (BOOK, "10:00"))

    def test_more_than_three_matches_offers_the_earliest_three(self):
        times = ["09:00", "10:00", "11:00", "14:00", "15:00"]
        calendar = Calendar(["haircut"], [Slot("monday", t) for t in times])
        action = decide(Request(service="haircut", day="monday", earliest="09:00"), "clarify", calendar)
        self.assertEqual(action.kind, CLARIFY)
        self.assertEqual([s.time for s in action.options], ["09:00", "10:00", "11:00"])

    def test_repeat_hands_over_only_when_still_ambiguous(self):
        action = self.decide(Request(service="haircut", day="friday", time="17:30"), "repeat", repeats_asked=2)
        self.assertEqual(action.kind, BOOK)

    # Rule 4: declining, and which nearby slots are offered.

    def test_a_service_not_offered_is_declined_before_asking_for_the_day(self):
        # "Can I book a massage?" (decline early, rule 4)
        action = self.decide(Request(service="massage"))
        self.assertEqual(action.kind, DECLINE)
        self.assertEqual(action.say, "Sorry, we don't offer massage. We offer haircut, colour or beard trim.")

    def test_friday_morning_is_declined_with_the_closest_friday_slots(self):
        action = self.decide(Request(service="haircut", day="friday", earliest="00:00", latest="11:59"))
        self.assertEqual(
            action.say,
            "I have nothing free on Friday morning. "
            "I can offer Friday at 12 pm or 5:30 pm, or you can name another day.",
        )

    def test_nearby_counts_slots_after_the_time_asked_for(self):
        # Friday at 1 pm: 12:00 is 1 hour before, 17:30 is 4.5 hours after, 18:15 is further.
        action = self.decide(Request(service="haircut", day="friday", time="13:00"))
        self.assertEqual([s.time for s in action.options], ["12:00", "17:30"])

    def test_nearby_looks_forward_from_the_day_asked_for(self):
        # Tuesday has no slots; Thursday is the next day with free slots, not Monday.
        action = self.decide(Request(service="haircut", day="tuesday", time="10:00"))
        self.assertEqual([(s.day, s.time) for s in action.options], [("thursday", "10:00"), ("thursday", "14:00")])

    def test_nearby_wraps_round_the_whole_week(self):
        calendar = Calendar(["haircut"], [Slot("monday", "11:00")])
        action = decide(Request(service="haircut", day="tuesday", time="11:00"), "clarify", calendar)
        self.assertEqual([(s.day, s.time) for s in action.options], [("monday", "11:00")])

    def test_next_day_offers_its_first_two_free_slots(self):
        calendar = Calendar(["haircut"], [Slot("monday", t) for t in ("09:00", "10:00", "11:00")])
        action = decide(Request(service="haircut", day="sunday", time="10:00"), "clarify", calendar)
        self.assertEqual([s.time for s in action.options], ["09:00", "10:00"])

    def test_one_nearby_slot_is_offered_on_its_own(self):
        calendar = Calendar(["haircut"], [Slot("monday", "11:00")])
        action = decide(Request(service="haircut", day="monday", time="12:00"), "clarify", calendar)
        self.assertEqual(
            action.say,
            "I have nothing free on Monday at 12 pm. I can offer Monday at 11 am, or you can name another day.",
        )

    def test_a_full_week_is_declined_without_options(self):
        calendar = Calendar(["haircut"], [Slot("monday", "11:00", free=False)])
        action = decide(Request(service="haircut", day="monday", time="11:00"), "clarify", calendar)
        self.assertEqual(action.kind, DECLINE)
        self.assertEqual(action.options, ())
        self.assertIn("no free appointments this week", action.say)

    def test_declines_describe_a_between_range(self):
        action = self.decide(Request(service="haircut", day="friday", earliest="13:00", latest="16:00"))
        self.assertTrue(action.say.startswith("I have nothing free on Friday between 1 pm and 4 pm."))

    def test_declines_describe_a_before_range(self):
        # latest is included, so "before twelve" is latest="11:59".
        action = self.decide(Request(service="haircut", day="friday", latest="11:59"))
        self.assertTrue(action.say.startswith("I have nothing free on Friday before 12 pm."))

    def test_unknown_strategy_is_an_error(self):
        with self.assertRaises(ValueError):
            self.decide(Request(), "guess")


class SafetyTests(unittest.TestCase):
    """The limits in docs/dialogue-spec.md that must hold for every request and strategy."""

    REQUESTS = [
        Request(),
        Request(day="friday", earliest="17:01"),
        Request(service="haircut", day="friday", earliest="17:01"),
        Request(service="haircut", day="friday", time="19:00"),
        Request(service="colour", day="saturday", earliest="12:00", latest="16:59"),
        Request(service="haircut", day="sunday", time="10:00"),
        Request(service="massage", day="monday", time="11:00"),
        Request(service="beard trim", day="thursday"),
        Request(service="haircut", day="friday", latest="11:59"),
    ]

    def setUp(self):
        self.calendar = Calendar.load()

    def every_action(self):
        """decide() for every request, every strategy and 0 to 2 repeats."""
        actions = []
        for request in self.REQUESTS:
            for strategy in STRATEGIES:
                for repeats_asked in range(3):
                    actions.append(decide(request, strategy, self.calendar, repeats_asked))
        return actions

    def test_every_slot_offered_or_chosen_is_free_and_in_the_calendar(self):
        for action in self.every_action():
            slots = list(action.options)
            if action.slot is not None:
                slots.append(action.slot)
            for slot in slots:
                self.assertIs(self.calendar.get(slot.day, slot.time), slot)
                self.assertTrue(slot.free)

    def test_never_more_than_three_options(self):
        for action in self.every_action():
            self.assertLessEqual(len(action.options), MAX_OPTIONS)

    def test_deciding_never_changes_the_calendar(self):
        before = [(s.day, s.time, s.free) for s in self.calendar.slots]
        self.every_action()
        self.assertEqual([(s.day, s.time, s.free) for s in self.calendar.slots], before)


if __name__ == "__main__":
    unittest.main()
