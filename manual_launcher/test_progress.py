import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from progress import parse_daily_activity, read_daily_activity, read_weekly_progress


class DailyProgressTests(unittest.TestCase):
    def test_points_beyond_final_reward_remain_valid(self):
        for value in (0,20,80,100,120,140,200):
            self.assertEqual(parse_daily_activity([str(value)]),value)

    def test_missing_or_ambiguous_values_do_not_become_zero(self):
        for values in ([],[''],['100/100'],['140','20'],['8704222'],['-20'],['14O']):
            with self.subTest(values=values),self.assertRaises(ValueError):
                parse_daily_activity(values)

    def test_readback_retains_actual_140_from_game(self):
        task=SimpleNamespace(ocr=Mock(return_value=[SimpleNamespace(name='140')]),screenshot=Mock())
        self.assertEqual(read_daily_activity(task),140)
        task.screenshot.assert_not_called()

    def test_failed_readback_saves_evidence(self):
        task=SimpleNamespace(ocr=Mock(return_value=[]),screenshot=Mock())
        with self.assertRaises(ValueError):read_daily_activity(task)
        task.screenshot.assert_called_once_with('activity-unreadable')

    def test_weekly_rejects_decimal_artifacts_and_disagreeing_reads(self):
        for labels in ((['60.00'],['6000']),(['600'],['6000']),(['6000/6000'],['6000/6000'])):
            task=SimpleNamespace(ocr=Mock(side_effect=[[SimpleNamespace(name=s) for s in row] for row in labels]),screenshot=Mock())
            with self.subTest(labels=labels),self.assertRaises(ValueError):read_weekly_progress(task)

    def test_weekly_accepts_only_two_consistent_current_scores(self):
        for value in (0,1000,6000):
            task=SimpleNamespace(ocr=Mock(return_value=[SimpleNamespace(name=str(value))]),screenshot=Mock())
            self.assertEqual(read_weekly_progress(task),value)
