import unittest

from assistant.understand import understand

SERVICES = ["haircut", "colour", "beard trim"]


def hear(text):
    return understand(text, SERVICES)


def heard_nothing(heard):
    keys = ("service", "day", "time", "earliest", "latest", "choice")
    return all(heard[key] is None for key in keys) and not heard["yes"]


class TimeTests(unittest.TestCase):
    def test_exact_times(self):
        cases = {
            "A haircut on Friday at half five": "17:30",
            "A haircut on Friday at seven": "19:00",
            "A massage on Monday at eleven": "11:00",
            "Sunday at ten for a haircut": "10:00",
            "half past six": "18:30",
            "quarter past four": "16:15",
            "ten thirty": "10:30",
            "10 30": "10:30",
            "6 15": "18:15",
            "six fifteen": "18:15",
            "5:30": "17:30",
            "5.30": "17:30",
            "the 6.15 one": "18:15",
            "the 4 one": "16:00",
            "6:15 pm": "18:15",
            "Monday 4 pm": "16:00",
            "10am": "10:00",
            "Monday at 8 am": "08:00",
            "Friday at 12 pm": "12:00",
            "at 17:30": "17:30",
            "half nine": "09:30",
            "at eight": "20:00",
            "seven": "19:00",
            "seven please": "19:00",
            "A haircut on Friday around six": "18:00",
            "A haircut on Friday about six": "18:00",
        }
        for text, time in cases.items():
            self.assertEqual(hear(text)["time"], time, text)

    def test_after_and_before(self):
        self.assertEqual(hear("Friday after five")["earliest"], "17:01")
        self.assertEqual(hear("after half five")["earliest"], "17:31")
        self.assertEqual(hear("after 6:15")["earliest"], "18:16")  # "after" leaves 6:15 out
        self.assertEqual(hear("before twelve")["latest"], "11:59")
        self.assertEqual(hear("before half five")["latest"], "17:29")

    def test_part_of_the_day(self):
        heard = hear("Colour on Saturday afternoon")
        self.assertEqual((heard["earliest"], heard["latest"]), ("12:00", "16:59"))
        self.assertIsNone(heard["time"])
        self.assertEqual(hear("first thing Friday")["latest"], "11:59")

    def test_not_a_time(self):
        for text in ["the first one please", "the second one", "one second", "Two haircuts", "2 people",
                     "about 2 hours", "for 2", "ten to two", "twenty past four", "ten past two", "5:30 or 6:15",
                     "5:30 and 6:15",
                     "Good afternoon, a haircut on Friday please", "late afternoon"]:
            heard = hear(text)
            self.assertIsNone(heard["time"], text)
            self.assertIsNone(heard["earliest"], text)
            self.assertIsNone(heard["latest"], text)

    def test_a_greeting_only_at_the_start_of_a_call(self):
        heard = understand("Morning! Can I book a haircut on Thursday?", SERVICES, first_turn=True)
        self.assertIsNone(heard["earliest"])
        self.assertEqual(heard["day"], "thursday")
        self.assertEqual(hear("Morning on Monday, please")["latest"], "11:59")
        heard = understand("Hi, morning! Can I get a haircut on Monday?", SERVICES, first_turn=True)
        self.assertIsNone(heard["earliest"])

    def test_a_number_we_cannot_place_makes_the_turn_unclear(self):
        for text in ["three in the afternoon", "Monday 11", "Thursday 2", "ten past four", "for 2",
                     "just past four", "morning and afternoon"]:
            heard = hear(text)
            self.assertTrue(heard["unclear"], text)
            self.assertIsNone(heard["day"], text)

    def test_a_time_and_a_part_of_the_day_must_fit(self):
        self.assertEqual(hear("Friday evening at 6")["time"], "18:00")
        for text in ["at 10 in the evening", "before 11 in the evening", "quarter after four", "half after 4"]:
            self.assertTrue(hear(text)["unclear"], text)

    def test_noon(self):
        self.assertEqual(hear("Friday at noon")["time"], "12:00")

    def test_nothing_useful(self):
        self.assertTrue(heard_nothing(hear("Sometime next week")))


class WordTests(unittest.TestCase):
    def test_services_and_days(self):
        heard = hear("A beard trim on Thursday")
        self.assertEqual((heard["service"], heard["day"]), ("beard trim", "thursday"))
        self.assertEqual(hear("a color please")["service"], "colour")
        self.assertEqual(hear("a massage")["service"], "massage")
        self.assertEqual(hear("Friday's good")["day"], "friday")

    def test_two_of_something_is_not_clear(self):
        self.assertIsNone(hear("A haircut and a beard trim")["service"])
        self.assertIsNone(hear("Monday or Tuesday")["day"])
        self.assertIsNone(hear("Monday and Tuesday")["day"])
        heard = hear("6:15 for a colour and a beard trim")
        self.assertTrue(heard["unclear"])
        self.assertIsNone(heard["time"])

    def test_choices(self):
        self.assertEqual(hear("the first one please")["choice"], 0)
        for text in ["just a second", "one second", "first thing Friday", "what was the second one",
                     "the first thing in the morning"]:
            self.assertIsNone(hear(text)["choice"], text)

    def test_yes(self):
        for text in ["Yes", "Book it", "that's right", "correct", "sounds good", "yes please", "Yes, Friday's fine",
                     "Yes, 5:30 is fine", "yes, a haircut on Friday"]:
            self.assertTrue(hear(text)["yes"], text)

    def test_not_a_yes(self):
        for text in ["Are you sure?", "are you sure", "is that right", "ok how much is it", "5:30, right?",
                     "ok, just a second", "Friday's fine", "The haircut's fine", "5:30 is ok", "right?", "ok?",
                     "Don't book it yet", "wait", "I don't think that's right", "OK, let me check my diary",
                     "Right, I'll call back later", "ok one sec", "fine, six then", "Yes, but later",
                     "OK, but tomorrow", "Sure, I can’t do 5:30 though"]:
            self.assertFalse(hear(text)["yes"], text)

    def test_no(self):
        for text in ["No", "No, I said Thursday", "that's not right", "that's wrong", "That isn't right",
                     "That isn’t right", "that isnt right", "dont book it yet", "nah",
                     "I cannot do Monday", "That's incorrect", "none of them", "I havent got time", "we arent free"]:
            heard = hear(text)
            self.assertTrue(heard["no"], text)
            self.assertFalse(heard["yes"], text)
        self.assertEqual(hear("No, I said Thursday")["day"], "thursday")
        self.assertEqual(hear("No, 6:15")["time"], "18:15")

    def test_a_no_inside_the_sentence_means_we_heard_nothing(self):
        for text in ["I can't do 5:30", "5:30 is too early", "Any day but Friday", "Not Friday",
                     "Just a haircut, no colour", "Thursday please, Monday's no good", "Not in the morning",
                     "5:30, no wait, 6:15", "5:30, sorry I mean 6:15", "not 5:30, 6:15 please",
                     "The first one doesn't work for me", "Later than 5:30", "I finish work at 2",
                     "the second, not the first"]:
            self.assertTrue(heard_nothing(hear(text)), text)

    def test_after_or_before_must_come_just_before_a_time(self):
        for text in ["after Monday", "before Friday", "after the 5:30", "after about eleven", "after the morning",
                     "A haircut after Monday at four", "the second one after the 5:30"]:
            self.assertTrue(hear(text)["unclear"], text)
        self.assertEqual(hear("after six")["earliest"], "18:01")
        self.assertEqual(hear("just after 4")["earliest"], "16:01")
        self.assertEqual(hear("before five")["latest"], "16:59")

    def test_which_part(self):
        self.assertEqual(hear("the day")["parts"], ["day"])
        self.assertEqual(hear("the day and the time")["parts"], ["day", "time"])
        self.assertEqual(hear("No, wrong time")["parts"], ["time"])


if __name__ == "__main__":
    unittest.main()
