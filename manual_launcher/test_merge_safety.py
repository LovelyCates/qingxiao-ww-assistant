"""Material consumption is gated by filter, count, and observed result."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from model import ROOT
sys.path.insert(0,str(ROOT/'ok-wuthering-waves-3.7.8'))
from src.task.MergeEchoTask import MergeEchoTask, parse_material_count, FULL_BATCH_PATTERN


class MergeSafetyTests(unittest.TestCase):
    def task(self):
        task=object.__new__(MergeEchoTask)
        task.discard_filter_verified=True
        task.select_discarded_batch=Mock(return_value=100)
        task.require_discard_filter_chip=Mock()
        task.read_material_count=Mock(return_value=100)
        task.wait_click_ocr=Mock()
        task.wait_ocr=Mock(side_effect=lambda *args,**kw: ['获得声骸'] if kw.get('match')=='获得声骸' else [])
        task.screenshot=Mock();task.log_info=Mock();task.open_merge_page=Mock()
        return task

    def test_exact_counter_rejects_missing_ambiguous_or_out_of_range_reads(self):
        self.assertEqual(parse_material_count(['已选择融合材料（100/100）']),100)
        self.assertEqual(parse_material_count(['已选择融合材料（0/100)']),0)
        for labels in ([],['100/100'],['已选择融合材料（100/1000）'],
                       ['已选择融合材料（101/100）'],['已选择融合材料（100/100）']*2):
            with self.subTest(labels=labels),self.assertRaises(RuntimeError):parse_material_count(labels)
        self.assertIsNone(FULL_BATCH_PATTERN.search('100/1000'))
        self.assertIsNone(FULL_BATCH_PATTERN.search('1100/100'))

    def test_unverified_filter_never_selects_or_submits(self):
        task=self.task();task.discard_filter_verified=False
        with self.assertRaises(RuntimeError):MergeEchoTask.select_discarded_batch(task)
        task.wait_click_ocr.assert_not_called()

    def test_missing_filter_chip_stops_before_submit(self):
        task=self.task();task.require_discard_filter_chip.side_effect=RuntimeError('filter missing')
        with self.assertRaises(RuntimeError):task.merge_full_batch()
        task.wait_click_ocr.assert_not_called()

    def test_partial_batch_does_not_submit(self):
        task=self.task();task.select_discarded_batch.return_value=99
        self.assertFalse(task.merge_full_batch());task.wait_click_ocr.assert_not_called()

    def test_count_change_stops_before_submit(self):
        task=self.task();task.read_material_count.return_value=99
        with self.assertRaises(RuntimeError):task.merge_full_batch()
        task.wait_click_ocr.assert_not_called()

    def test_missing_result_does_not_count_a_click_as_success(self):
        task=self.task();task.wait_ocr.side_effect=RuntimeError('result missing')
        with self.assertRaises(RuntimeError):task.merge_full_batch()
        task.wait_click_ocr.assert_called_once()
        self.assertFalse(getattr(task,'merge_result_visible',False))

    def test_next_batch_reopens_and_revalidates_after_observed_result(self):
        task=self.task()
        self.assertTrue(task.merge_full_batch());self.assertTrue(task.merge_result_visible)
        self.assertTrue(task.merge_full_batch());task.open_merge_page.assert_called_once()

    def test_quality_warning_is_confirmed_only_for_verified_pending_batch(self):
        task=self.task()
        task.wait_ocr.side_effect=None;task.wait_ocr.return_value=['品质较高的声骸']
        for verified,pending in ((False,100),(True,None),(True,99)):
            task.discard_filter_verified=verified;task.pending_merge_count=pending
            with self.subTest(verified=verified,pending=pending),self.assertRaises(RuntimeError):
                task.confirm_verified_merge_warning()
            task.wait_click_ocr.assert_not_called()
        task.discard_filter_verified=True;task.pending_merge_count=100
        self.assertTrue(task.confirm_verified_merge_warning())
        task.wait_click_ocr.assert_called_once()

if __name__=='__main__':unittest.main()
