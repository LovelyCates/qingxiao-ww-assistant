from datetime import datetime
import unittest
from unittest.mock import patch
import history

class PeriodTests(unittest.TestCase):
    def summary_at(self,now,records):
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return datetime.fromisoformat(now)
        index=history.RunHistory()
        with patch.object(history,'datetime',Clock),patch.object(index,'refresh',return_value=records):
            return index.summary()
    def record(self,at,**values):return dict(status='PROBE_PASSED',ended_at=at,updated_at=at,**values)
    def test_four_am_reset_removes_yesterdays_full_activity(self):
        rows=[self.record('2026-10-24T03:59:00+08:00',activity_points=100)]
        self.assertEqual(self.summary_at('2026-10-24T03:59:30+08:00',rows)['activity'],100)
        self.assertIsNone(self.summary_at('2026-10-24T04:00:00+08:00',rows)['activity'])
    def test_monday_four_am_reset_does_not_claim_last_weeks_garden_complete(self):
        rows=[self.record('2026-10-25T23:00:00+08:00',weekly_progress_points=6000)]
        self.assertEqual(self.summary_at('2026-10-26T03:59:00+08:00',rows)['weekly'],6000)
        self.assertIsNone(self.summary_at('2026-10-26T04:00:00+08:00',rows)['weekly'])
    def test_current_zero_is_visible_and_failures_cannot_supply_valid_metrics(self):
        failed=dict(self.record('2026-10-24T05:01:00+08:00',activity_points=100),status='FAILED')
        rows=[failed,self.record('2026-10-24T05:00:00+08:00',activity_points=0)]
        self.assertEqual(self.summary_at('2026-10-24T06:00:00+08:00',rows)['activity'],0)
    def test_switching_accounts_invalidates_previous_global_readings(self):
        old=self.record('2026-10-30T00:30:00+08:00',started_at='2026-10-30T00:29:00+08:00',activity_points=110,weekly_progress_points=6000)
        batch=self.record('2026-10-30T01:00:00+08:00',started_at='2026-10-30T00:59:00+08:00',mode='multiaccount',status_override='unused')
        batch['status']='FAILED'
        summary=self.summary_at('2026-10-30T01:10:00+08:00',[batch,old])
        self.assertIsNone(summary['activity']);self.assertIsNone(summary['weekly'])
        current=self.record('2026-10-30T01:05:00+08:00',started_at='2026-10-30T01:04:00+08:00',activity_points=0)
        self.assertEqual(self.summary_at('2026-10-30T01:10:00+08:00',[current,batch,old])['activity'],0)

if __name__=='__main__':unittest.main(verbosity=2)
