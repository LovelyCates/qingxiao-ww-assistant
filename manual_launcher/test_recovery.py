import json
from pathlib import Path
import tempfile
import unittest
from model import RUNS,atomic_json,read_json
from finalize_run import finalize

class ReportRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=RUNS);self.folder=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def test_crashed_worker_keeps_last_claim_evidence_and_never_reports_success(self):
        atomic_json(self.folder/'report.json',{'mode':'farm','status':'STARTING','stage':'claiming_reward',
                    'pending_claim':{'before':125,'cost':120},'errors':[]})
        finalize(self.folder,-1073741819)
        report=read_json(self.folder/'report.json',{})
        self.assertEqual(report['status'],'FAILED');self.assertEqual(report['pending_claim']['cost'],120)
        self.assertEqual(report['worker_last_status'],'STARTING');self.assertTrue(report['ended_at'])
        self.assertIn('没有自动重试',report['errors'][-1]);self.assertTrue((self.folder/'report.html').exists())
    def test_completed_readback_is_preserved_on_clean_exit(self):
        report={'status':'PROBE_PASSED','activity_points':0,'ended_at':'2026-10-24T05:00:00+08:00'}
        atomic_json(self.folder/'report.json',report)
        self.assertFalse(finalize(self.folder,0)['Changed']);self.assertEqual(read_json(self.folder/'report.json'),report)
    def test_nonzero_shutdown_after_success_requires_review(self):
        atomic_json(self.folder/'report.json',{'status':'PROBE_PASSED','activity_points':100,'ended_at':'2026-10-24T05:00:00+08:00'})
        finalize(self.folder,1);report=read_json(self.folder/'report.json')
        self.assertEqual(report['status'],'NEEDS_REVIEW');self.assertEqual(report['activity_points'],100)
        self.assertEqual(report['worker_last_status'],'PROBE_PASSED')
    def test_no_eligible_echoes_remains_an_explicit_noop(self):
        report={'status':'NO_ELIGIBLE_ECHOES','merge_batches':0,'ended_at':'2026-10-27T02:00:00+08:00'}
        atomic_json(self.folder/'report.json',report)
        self.assertFalse(finalize(self.folder,0)['Changed'])
        self.assertEqual(read_json(self.folder/'report.json'),report)
    def test_timeout_creates_report_and_exit_evidence_even_before_first_save(self):
        finalize(self.folder,3,True)
        self.assertEqual(read_json(self.folder/'report.json')['status'],'TIMEOUT')
        self.assertEqual(read_json(self.folder/'process-result.json')['ExitCode'],3)
    def test_explicit_cancellation_is_not_relabelled_as_a_crash(self):
        report={'status':'CANCELLED','ended_at':'2026-10-24T05:00:00+08:00'}
        atomic_json(self.folder/'report.json',report)
        self.assertFalse(finalize(self.folder,4)['Changed']);self.assertEqual(read_json(self.folder/'report.json'),report)
    def test_finalizer_cannot_write_outside_a_direct_run_folder(self):
        with self.assertRaises(ValueError):finalize(RUNS.parent,1)
        with self.assertRaises(ValueError):finalize(self.folder/'nested',1)

if __name__=='__main__':unittest.main(verbosity=2)
