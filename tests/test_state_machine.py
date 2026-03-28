import unittest

from src.screening.state_machine import assert_transition


class StateMachineTests(unittest.TestCase):
    def test_valid_transition(self):
        assert_transition("created", "booting_browser")

    def test_invalid_transition(self):
        with self.assertRaises(ValueError):
            assert_transition("created", "scoring_candidate")
