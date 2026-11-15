import unittest

from assistant.booking import (
    BOOKED,
    NO_SUCH_SLOT,
    SLOT_TAKEN,
    UNKNOWN_SERVICE,
    BookingDesk,
    describe,
)
from assistant.slots import Calendar, spoken_time


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.calendar = Calendar.load()

    def test_friday_after_five_has_two_free_slots(self):
        slots = self.calendar.find_free("friday", earliest="17:00")
        self.assertEqual([s.time for s in slots], ["17:30", "18:15"])

    def test_saturday_afternoon_has_nothing_free(self):
        self.assertEqual(self.calendar.find_free("saturday", earliest="12:00"), [])

    def test_day_with_no_slots_returns_nothing(self):
        self.assertEqual(self.calendar.find_free("sunday"), [])

    def test_day_name_is_case_insensitive(self):
        self.assertEqual(len(self.calendar.find_free("  Friday ")), 3)

    def test_spoken_time(self):
        self.assertEqual(spoken_time("17:30"), "5:30 pm")
        self.assertEqual(spoken_time("09:30"), "9:30 am")
        self.assertEqual(spoken_time("12:00"), "12 pm")


class BookingTests(unittest.TestCase):
    def setUp(self):
        self.calendar = Calendar.load()
        self.desk = BookingDesk(self.calendar)

    def test_free_slot_is_booked_and_then_unavailable(self):
        result = self.desk.book("r1", "haircut", "friday", "17:30")
        self.assertEqual(result.status, BOOKED)
        self.assertFalse(self.calendar.get("friday", "17:30").free)
        self.assertEqual(describe(result), "Booked: haircut on Friday at 5:30 pm.")

    def test_taken_slot_is_refused(self):
        result = self.desk.book("r1", "haircut", "friday", "19:00")
        self.assertEqual(result.status, SLOT_TAKEN)
        self.assertTrue(describe(result).startswith("Not booked"))

    def test_slot_that_does_not_exist_is_refused(self):
        result = self.desk.book("r1", "haircut", "sunday", "10:00")
        self.assertEqual(result.status, NO_SUCH_SLOT)

    def test_unknown_service_is_refused_and_slot_stays_free(self):
        result = self.desk.book("r1", "massage", "monday", "11:00")
        self.assertEqual(result.status, UNKNOWN_SERVICE)
        self.assertTrue(self.calendar.get("monday", "11:00").free)

    def test_repeating_a_request_does_not_book_twice(self):
        first = self.desk.book("r1", "haircut", "friday", "17:30")
        again = self.desk.book("r1", "haircut", "friday", "17:30")
        self.assertEqual(first.status, BOOKED)
        self.assertEqual(again.status, BOOKED)
        self.assertTrue(again.repeat)
        self.assertIn("not booked it twice", describe(again))

    def test_second_caller_cannot_take_a_slot_just_booked(self):
        self.desk.book("r1", "haircut", "friday", "17:30")
        other = self.desk.book("r2", "colour", "friday", "17:30")
        self.assertEqual(other.status, SLOT_TAKEN)


if __name__ == "__main__":
    unittest.main()
