"""Business acceptance contracts; failures are open defects, never expected passes.

Game input is mocked. Run separately from the existing regression suite.
"""
import json
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch,PropertyMock

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'manual_launcher'))
sys.path.insert(0,str(ROOT/'ok-wuthering-waves-3.7.8'))
import assistant
import game_extensions
import legacy_panel
import qingxiao_panel as ui
from model import make_request,normalize_enhance_rules
from src.task.AutoPickTask import AutoPickTask
from src.task.EnhanceEchoTask import EnhanceEchoTask
from src.task.MergeEchoTask import MergeEchoTask
from PySide6.QtWidgets import QApplication,QMessageBox

class EnhancementContracts(unittest.TestCase):
    def setUp(self):
        self.task=object.__new__(EnhanceEchoTask)
        self.task.config=json.loads((ROOT/'manual_launcher/fixtures/enhancement-config.json').read_text(encoding='utf-8'))
        for name in ('log_info','log_debug','info_set'):setattr(self.task,name,Mock())
    def decide(self,stats):
        return self.task.check_echo_stats([SimpleNamespace(name=p,y=n*30) for n,(p,v) in enumerate(stats)],
            [SimpleNamespace(name=v,y=n*30) for n,(p,v) in enumerate(stats)])
    def test_complete_good_stats_pass(self):
        self.assertTrue(self.decide([('暴击','8.1%'),('暴击伤害','16.2%'),('攻击','8.6%'),('防御','40'),('生命','320')]))
    def test_low_first_crit_rejected(self):self.assertFalse(self.decide([('暴击','6.3%')]))
    def test_insufficient_final_valid_stats_rejected(self):
        self.assertFalse(self.decide([('暴击','8.1%'),('暴击伤害','16.2%'),('生命','320'),('防御','40'),('防御','8.1%')]))
    def test_missing_value_must_pause_not_discard(self):
        with self.assertRaises((ValueError,RuntimeError)):
            self.task.check_echo_stats([SimpleNamespace(name='暴击',y=0)],[])
    def test_empty_ocr_must_pause_not_continue_spending(self):
        with self.assertRaises((ValueError,RuntimeError)):self.task.check_echo_stats([],[])
    def test_non_numeric_value_must_pause(self):
        with self.assertRaises((ValueError,RuntimeError)):self.decide([('暴击','..%')])
    def test_values_on_unrelated_rows_must_pause(self):
        with self.assertRaises((ValueError,RuntimeError)):
            self.task.check_echo_stats([SimpleNamespace(name='暴击',y=0)],[SimpleNamespace(name='8.1%',y=900)])
    def test_disabling_double_crit_does_not_keep_hidden_early_rejection(self):
        self.task.config['必须有双爆']=False
        # These previously hidden switches now have explicit, disabled defaults
        # in the panel protocol. Verify that exact public configuration.
        rules=normalize_enhance_rules()
        self.task.config['双爆出现之前必须全有效词条']=rules['require_valid_before_crit']
        self.task.config['第一条必须为有效词条']=rules['require_first_valid']
        self.assertTrue(self.decide([('防御','40')]),'With 4 slots left, 3 valid stats are still achievable under the visible rules')

class PickupContracts(unittest.TestCase):
    def setUp(self):
        self.task=object.__new__(AutoPickTask);self.task.scene=SimpleNamespace(in_team=Mock(return_value=True))
        self.task.in_team_and_world=Mock();self.task.find_one=Mock(return_value=SimpleNamespace(width=10,height=10,copy=Mock(return_value=SimpleNamespace(width=20,copy=Mock()))))
        self.task.find_one.side_effect=lambda name,**kwargs: self.task.find_one.return_value if name=='pick_up_f_hcenter_vcenter' else None
        box_patch=patch.object(AutoPickTask,'f_search_box',new_callable=PropertyMock,return_value=Mock());box_patch.start();self.addCleanup(box_patch.stop)
        self.task.calculate_color_percentage=Mock(return_value=.9);self.task.find_feature=Mock(return_value=False)
        self.task.find_f_with_text=Mock(return_value=False)
        self.task.ocr=Mock(return_value=[SimpleNamespace(name='薄荷')])
        self.task.config={'Pick Up White List':['吸收'],'Pick Up Black List':['领取奖励','开始合成']}
        self.task.send_key=Mock();self.task.sleep=Mock()
    def test_no_world_means_no_input(self):
        self.task.scene.in_team.return_value=False;self.task.run();self.task.send_key.assert_not_called()
    def test_no_prompt_means_no_input(self):
        self.task.find_one.return_value=None;self.task.run();self.task.send_key.assert_not_called()
    def test_blacklisted_reward_is_not_clicked(self):
        self.task.ocr.return_value=[SimpleNamespace(name='领取奖励')]
        self.assertFalse(self.task.run());self.task.send_key.assert_not_called()
    def test_absorb_whitelist_is_actionable(self):
        self.task.find_feature.return_value=True;self.task.ocr.return_value=[SimpleNamespace(name='吸收')]
        self.assertTrue(self.task.run());self.assertGreater(self.task.send_key.call_count,0)
    def test_revalidate_after_one_interaction(self):
        self.task.run();self.assertEqual(self.task.send_key.call_count,1,'Do not send another F without identifying the new target')
    def test_unreadable_prompt_is_not_treated_as_allowed(self):
        self.task.ocr.return_value=[]
        self.assertFalse(self.task.run());self.task.send_key.assert_not_called()
    def test_dialog_without_exact_whitelist_is_not_activated(self):
        self.task.find_feature.return_value=True;self.task.ocr.return_value=[SimpleNamespace(name='调查')]
        self.task.next_frame=Mock()
        # One timeout-free observation path for a denied dialog.
        prompts=iter([self.task.find_one.return_value,None])
        self.task.find_one.side_effect=lambda name,**kwargs: next(prompts) if name=='pick_up_f_hcenter_vcenter' else None
        self.task.run();self.task.send_key.assert_not_called()

class PlanContracts(unittest.TestCase):
    def test_explicit_merge_batches_preserved(self):
        self.assertEqual(assistant.offline_plan('合成2批声骸')['steps'][0]['options']['count'],2)
    def test_individual_echo_count_not_interpreted_as_batches(self):
        self.assertFalse(assistant.offline_plan('合成5个声骸')['steps'])
    def test_unspecified_merge_times_require_units(self):
        self.assertFalse(assistant.offline_plan('合成声骸2次')['steps'])
    def test_enhance_candidate_count_preserved(self):
        self.assertEqual(assistant.offline_plan('强化2个声骸')['steps'][0]['options']['count'],2)
    def test_material_units_cannot_silently_drop_chinese_decimals_or_ranges(self):
        for text in ('合成五个声骸','合成两批声骸','合成1.5批声骸','合成1到5批声骸','强化声骸2次'):
            with self.subTest(text=text):self.assertFalse(assistant.offline_plan(text)['steps'])
    def test_explicit_stop_plans_stop(self):self.assertEqual(assistant.offline_plan('停止任务')['steps'][0]['action'],'stop')

class AdapterContracts(unittest.TestCase):
    def helpers(self,action):
        clock=SimpleNamespace(now=0);calls=[];result={'errors':[]};updates=[]
        def save(**kw):result.update(kw);updates.append(kw)
        class Helper:
            def __init__(self,**kw):self.executor=kw['executor'];self.config={}
            def after_init(self,**kw):pass
            def post_init(self):pass
            def run(self):
                calls.append('run');self.executor.sleep(90)
                raise AssertionError('Input after deadline must be unreachable')
        target='src.task.SkipDialogTask.AutoDialogTask' if action=='dialog' else 'src.task.AutoPickTask.AutoPickTask'
        with patch(target,Helper):classes=game_extensions.task_classes(None,save,result,make_request(action,duration=1),ROOT)
        task=object.__new__(classes['assist']);task._executor=SimpleNamespace(scene=object(),check_enabled=Mock(),sleep=lambda seconds:setattr(clock,'now',clock.now+seconds));task._app=None
        task.ensure_main=Mock();task.sleep=lambda seconds:task.executor.sleep(seconds)
        with patch.object(game_extensions,'time',SimpleNamespace(monotonic=lambda:clock.now)):task.run()
        return task,result
    def test_assist_deadline_applies_inside_helpers(self):
        _,result=self.helpers('pickup');self.assertLessEqual(result['assist_elapsed_seconds'],61)
    def test_dialog_start_does_not_escape_current_dialog(self):
        task,_=self.helpers('dialog');task.ensure_main.assert_not_called()
    def test_zero_merged_batches_not_reported_as_execution_finished(self):
        result={'errors':[]}
        def save(**kw):result.update(kw)
        classes=game_extensions.task_classes(None,save,result,make_request('merge',confirmed_materials=True,count=1),ROOT)
        task=object.__new__(classes['merge']);task.screenshot=Mock();task.ensure_main=Mock()
        with patch.object(MergeEchoTask,'merge_echoes',return_value=None):task.run()
        self.assertNotEqual(result['status'],'EXECUTION_FINISHED')
    def test_material_confirmation_required(self):
        classes=game_extensions.task_classes(None,Mock(),{'errors':[]},make_request('merge',confirmed_materials=False),ROOT)
        task=object.__new__(classes['merge']);task.ensure_main=Mock()
        with self.assertRaises(RuntimeError):task.run()
        task.ensure_main.assert_not_called()

class UIContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);ui.configure_fonts(cls.app);cls.app.setStyleSheet(ui.STYLE)
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=ROOT/'local-runs');runs=Path(self.temp.name);self.calls=[]
        def bridge(panel,action,callback):self.calls.append(action);callback({'Ok':True,'Tasks':[]})
        self.patches=[patch.object(ui,'RUNS',runs),patch.object(legacy_panel,'RUNS',runs),patch.object(assistant,'CONFIG',runs/'settings.json'),patch.object(ui.Panel,'bridge',bridge)]
        for p in self.patches:p.start()
        self.window=ui.Panel();self.window.timer.stop()
    def tearDown(self):
        self.window.active_id=None;self.window.close();self.app.processEvents()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_manual_play_helpers_stay_visible(self):
        self.window.window_mode.setCurrentIndex(1)
        self.assertEqual(self.window.job_parameters('pickup')['background'],'foreground')
    def test_cancel_material_confirmation_never_dispatches(self):
        with patch.object(self.window,'confirm_materials',return_value=False):self.window.start_job('enhance')
        self.assertNotIn('start',self.calls)
    def test_stopping_invalidates_pending_plan(self):
        self.window.pending_plan={'reply':'准备强化','steps':[{'action':'enhance','options':{'count':1}}]}
        self.window.stop_job();self.assertIsNone(self.window.pending_plan)
    def test_enhance_summary_contains_processed_counts(self):
        report=Path(self.temp.name)/'report.json';ui.atomic_json(report,{'status':'EXECUTION_FINISHED','enhance_selected':3,'enhance_success':1,'enhance_rejected':2})
        self.window.announce_result({'Action':'enhance','Report':str(report),'State':'completed'})
        self.assertIn('3',self.window.chat_messages[-1]['content'])

if __name__=='__main__':unittest.main(verbosity=2)
