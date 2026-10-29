from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import reporting
from model import RUNS,atomic_json

class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=RUNS);self.folder=Path(self.temp.name)
        self.path=self.folder/'report.json'
    def tearDown(self):self.temp.cleanup()
    def test_public_report_uses_geometric_icon_without_character_assets(self):
        import runtime_settings
        assets=self.folder/'manual_launcher/assets';assets.mkdir(parents=True)
        (assets/'app-icon.png').write_bytes(b'icon fixture')
        with patch.object(runtime_settings,'ROOT',self.folder):
            page=reporting.render_report({'status':'PROBE_PASSED','mode':'probe'},self.path)
        self.assertIn('src="manual_launcher/assets/app-icon.png"',page)
        self.assertNotIn('src="manual_launcher/assets/qingxiao-icon.png"',page)
    def test_account_reports_link_to_their_own_step_results_and_escape_labels(self):
        child=self.folder/'accounts'/'id'/'0'/'report.json';child.parent.mkdir(parents=True)
        report={'mode':'multiaccount','status':'FAILED','account_results':[dict(label='<script>bad</script>',
            status='failed',completed_steps=1,steps=[dict(action='probe',status='PROBE_PASSED',report=str(child))])]}
        page=reporting.render_report(report,self.path)
        self.assertIn('accounts/id/0/report.html',page);self.assertIn('账号完成',page)
        self.assertNotIn('<script>',page)
        step=reporting.render_report({'mode':'probe','account_scoped':True},child)
        self.assertIn('href="../../../stdout.log"',step)
    def test_unverified_pending_claim_is_not_rendered_as_zero_consumption(self):
        page=reporting.render_report({'mode':'farm','status':'FAILED','stamina_spent':0,'pending_claim':{'before':125,'cost':120}},self.path)
        self.assertIn('体力消耗</small><strong>待核对',page)
        self.assertNotIn('已核实体力消耗</small>',page)
        self.assertIn('不要直接重复领取',page)
    def test_failed_run_can_display_separate_verified_consumption_without_changing_status(self):
        verify=self.folder/'verify.json';atomic_json(verify,{'consumption_verified':True,'source_report':str(self.path),'stamina_spent':120})
        with patch.object(reporting,'VERIFICATION',verify):page=reporting.render_report({'status':'FAILED','mode':'farm'},self.path)
        self.assertIn('已核实体力消耗</small><strong>120',page);self.assertIn('运行中断，请查看日志',page)
        self.assertIn('原始状态保留',page)
    def test_logs_cannot_inject_html_and_screenshots_are_lazy_and_bounded(self):
        screenshots=self.folder/'screenshots';screenshots.mkdir()
        for number in range(15):(screenshots/f'{number:02d}_capture.png').write_bytes(b'test-placeholder')
        page=reporting.render_report({'status':'FAILED','errors':['<script>alert(1)</script>']},self.path)
        self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)
        self.assertEqual(page.count('loading="lazy"'),12);self.assertIn('screenshots/14_capture.png',page)
    def test_completed_echo_report_contains_observed_pickup_and_recovered_notes(self):
        report={'status':'EXECUTION_FINISHED','mode':'echo','echo_count':1,'recovered_log_errors':['kept note'],
                'window_hidden_has_foreground':False,'game_minimized_after_task':True}
        reporting.write_report_html(report,self.path)
        page=self.path.with_suffix('.html').read_text(encoding='utf-8')
        self.assertIn('声骸拾取读数</small><strong>1',page);self.assertIn('已恢复提示',page)
        self.assertIn('游戏未占用前台',page);self.assertIn('原始运行数据',page)
    def test_window_recovery_errors_are_visible_without_expanding_raw_json(self):
        page=reporting.render_report({'status':'FAILED','errors':[],'window_policy_error':'模拟窗口恢复失败'},self.path)
        visible=page.split('<h2>本次截图</h2>')[0]
        self.assertIn('需要核对',visible);self.assertIn('模拟窗口恢复失败',visible)

    def test_task_names_with_slashes_keep_nested_failure_screenshots_visible(self):
        from urllib.parse import quote
        from history import RunHistory
        nested=self.folder/'screenshots'/'简体';nested.mkdir(parents=True)
        capture=nested/'繁体_original.png';capture.write_bytes(b'test-placeholder')
        page=reporting.render_report({'mode':'enhance','status':'FAILED'},self.path)
        self.assertIn('screenshots/'+quote('简体/繁体_original.png',safe='/'),page)
        self.assertEqual(RunHistory().screenshots({'_path':str(self.path)}),[capture])

if __name__=='__main__':unittest.main(verbosity=2)
