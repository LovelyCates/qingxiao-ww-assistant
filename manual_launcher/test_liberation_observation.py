"""A missed animation is not a missed cast when the numeric cooldown is visible."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from model import ROOT
sys.path.insert(0,str(ROOT/'ok-wuthering-waves-3.7.8'))
from src.char.BaseChar import BaseChar


class LiberationObservationTests(unittest.TestCase):
    def character(self,cooldown):
        char=object.__new__(BaseChar)
        char.task=SimpleNamespace(use_liberation=True,in_liberation=False,
            next_frame=Mock(),wait_until=Mock(return_value=False),get_cd=Mock(return_value=cooldown),screenshot=Mock())
        char.logger=Mock();char.liberation_available=Mock(side_effect=[True,False])
        char.send_liberation_key=Mock();char.record_liberation_use=Mock()
        return char

    def test_short_animation_can_be_confirmed_by_actual_cooldown(self):
        char=self.character(18.2)
        self.assertTrue(char.click_liberation())
        char.record_liberation_use.assert_called_once()
        char.logger.error.assert_not_called()
        self.assertFalse(char.task.in_liberation)

    def test_no_observed_cooldown_keeps_the_failure_and_screenshot(self):
        for value in (0,-1,None,True,'18',float('nan'),10000):
            char=self.character(value)
            with self.subTest(value=value):self.assertFalse(char.click_liberation())
            char.record_liberation_use.assert_not_called()
            char.task.screenshot.assert_called_once_with('liberation-not-observed')
