"""Material, deadline and UI boundaries for the new upstream adapters.

Inputs are mocked; these tests never connect to the game.
"""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'manual_launcher'))
sys.path.insert(0,str(ROOT/'ok-wuthering-waves-3.7.8'))
import assistant
import game_extensions
from model import make_request,normalize_helper_options,atomic_json
from assist_guard import AssistDeadlineReached
from src.task.TacetEliminationTask import TacetEliminationTask


class ProtocolBoundaries(unittest.TestCase):
    def test_no_implicit_coercion_or_unknown_helper_settings(self):
        for value in ({'use_liberation':'false'},{'auto_target':1},{'password':'x'},
                      {'pickup_whitelist':'吸收'},{'pickup_blacklist':['a\nb']}):
            with self.subTest(value=value),self.assertRaises(ValueError):normalize_helper_options(value)
    def test_no_empty_quest_composition(self):
        with self.assertRaises(ValueError):
            make_request('quest',helper_options={k:False for k in ('quest_dialog','quest_combat','quest_pickup','quest_fasttravel')})
    def test_new_actions_require_valid_targets_and_foreground(self):
        with self.assertRaises(ValueError):make_request('reconstruct',main_stat='未知词条')
        with self.assertRaises(ValueError):make_request('elimination',main_stat='攻击')
        for action in ('fasttravel','quest','reconstruct','elimination'):
            self.assertEqual(make_request(action,background='hidden')['Background'],'foreground')
    def test_daily_target_index_depends_on_selected_farm(self):
        self.assertEqual(make_request('daily',daily_farm='forgery',index=20)['Index'],20)
        with self.assertRaises(ValueError):make_request('daily',daily_farm='forgery',index=21)
        with self.assertRaises(ValueError):make_request('daily',daily_farm='simulation',index=2)
    def test_reconstruct_plans_preserve_units_and_exact_target(self):
        plan=assistant.offline_plan('重构2个声骸为暴击伤害')
        self.assertEqual(plan['steps'][0]['options'],{'count':2,'main_stat':'暴击伤害'})
        for text in ('重构声骸','重构1.5个声骸为暴击','重构1到5个声骸为暴击',
                     '重构五个声骸为暴击','重构2次声骸为暴击'):
            with self.subTest(text=text):self.assertFalse(assistant.offline_plan(text)['steps'])
    def test_llm_cannot_omit_reconstruction_target(self):
        with self.assertRaisesRegex(ValueError,'明确指定'):
            assistant.validate_plan({'reply':'开始重构','steps':[{'action':'reconstruct','options':{'count':1}}]})


class HelperComposition(unittest.TestCase):
    def test_only_selected_helpers_run_and_receive_frozen_settings(self):
        calls=[];instances={};clock=SimpleNamespace(now=0);result={'errors':[]}
        def helper(name):
            class Helper:
                def __init__(self,**kw):self.config={};instances[name]=self
                def after_init(self,**kw):pass
                def post_init(self):pass
                def run(self):calls.append(name);return True
            return Helper
        patches=[patch(path,helper(name)) for name,path in (
            ('dialog','src.task.SkipDialogTask.AutoDialogTask'),('combat','src.task.AutoCombatTask.AutoCombatTask'),
            ('pickup','src.task.AutoPickTask.AutoPickTask'),('travel','src.task.FastTravelTask.FastTravelTask'))]
        for p in patches:p.start()
        try:
            opts=make_request('quest',duration=1,helper_options={'quest_dialog':False,'quest_fasttravel':True,
                'use_liberation':False,'pickup_whitelist':['吸收','薄荷']})
            cls=game_extensions.task_classes(None,lambda **kw:result.update(kw),result,opts,ROOT)['assist']
        finally:
            for p in reversed(patches):p.stop()
        task=object.__new__(cls);task._app=None
        task._executor=SimpleNamespace(scene=object(),check_enabled=Mock(),sleep=lambda seconds:setattr(clock,'now',clock.now+seconds))
        # One complete helper cycle, then the enforced executor deadline.
        task.sleep=lambda seconds:task.executor.sleep(60)
        with patch.object(game_extensions,'time',SimpleNamespace(monotonic=lambda:clock.now)):task.run()
        self.assertEqual(calls,['combat','pickup','travel']);self.assertNotIn('dialog',instances)
        self.assertFalse(instances['combat'].config['Use Liberation'])
        self.assertEqual(instances['pickup'].config['Pick Up White List'],['吸收','薄荷'])
        self.assertEqual(result['travel_actions'],1);self.assertEqual(result['combat_sessions'],1)


class ReconstructBoundaries(unittest.TestCase):
    def build(self,**options):
        self.result={'errors':[]};self.updates=[]
        def save(**kw):self.result.update(kw);self.updates.append(kw)
        cls=game_extensions.task_classes(None,save,self.result,make_request('reconstruct',**options),ROOT)['mainstat']
        task=object.__new__(cls);task.config={};task._executor=SimpleNamespace(debug=False)
        task.info={};task.info_set=lambda k,v:task.info.__setitem__(k,v)
        task.info_get=lambda k:task.info.get(k,0)
        task.info_incr=lambda k:task.info.__setitem__(k,task.info.get(k,0)+1)
        for name in ('click','sleep','screenshot','log_info','log_error','esc','wait_click_ocr'):
            setattr(task,name,Mock())
        task.find_echo_enhance=Mock(side_effect=[True,False,True,False,True])
        task.read_selected_level=Mock(return_value=0)
        def ocr(*args,**kw):
            match=kw.get('match')
            return [SimpleNamespace(name='暴击伤害' if match is None else '暴击' if isinstance(match,re.Pattern) else match)]
        task.wait_ocr=Mock(side_effect=ocr)
        return task
    def test_candidate_limit_stops_actual_upstream_loop(self):
        task=self.build(count=1,main_stat='暴击',confirmed_materials=True);task.run()
        submits=[c for c in task.wait_click_ocr.call_args_list if c.kwargs.get('match')=='数据重构']
        self.assertEqual(len(submits),1);self.assertEqual(self.result['reconstruct_completed'],1)
        self.assertIsNone(self.result['pending_reconstruct'])
        self.assertFalse(self.result['main_attribute_independently_verified'])
        self.assertFalse(self.result['material_consumption_independently_verified'])
    def test_two_candidates_have_two_separate_receipts(self):
        task=self.build(count=2,main_stat='暴击',confirmed_materials=True);task.run()
        self.assertEqual(self.result['reconstruct_completed'],2)
        self.assertEqual(sum(bool(r.get('pending_reconstruct')) for r in self.updates),2)
    def test_uncertain_post_submit_leaves_receipt_and_never_repeats(self):
        task=self.build(count=2,main_stat='暴击',confirmed_materials=True)
        original=task.wait_ocr.side_effect
        def ocr(*args,**kw):
            if kw.get('match')=='获得声骸':raise RuntimeError('result not observed')
            return original(*args,**kw)
        task.wait_ocr.side_effect=ocr
        with self.assertRaisesRegex(RuntimeError,'result not observed'):task.run()
        self.assertEqual(self.result['status'],'NEEDS_REVIEW')
        self.assertEqual(self.result['pending_reconstruct']['target'],'暴击')
        self.assertEqual(sum(c.kwargs.get('match')=='数据重构' for c in task.wait_click_ocr.call_args_list),1)
    def test_nonzero_level_never_submits(self):
        task=self.build(count=1,confirmed_materials=True);task.read_selected_level.return_value=5;task.run()
        task.click.assert_not_called();task.wait_click_ocr.assert_not_called()
        self.assertEqual(self.result['status'],'NO_ELIGIBLE_ECHOES')
    def test_ambiguous_target_never_submits(self):
        task=self.build(count=1,main_stat='暴击',confirmed_materials=True)
        original=task.wait_ocr.side_effect
        task.wait_ocr.side_effect=lambda *a,**kw:[Mock(),Mock()] if isinstance(kw.get('match'),re.Pattern) else original(*a,**kw)
        with self.assertRaisesRegex(RuntimeError,'唯一'):task.run()
        task.wait_click_ocr.assert_not_called();self.assertNotIn('pending_reconstruct',self.result)
    def test_same_attribute_never_submits(self):
        task=self.build(count=1,main_stat='暴击伤害',confirmed_materials=True)
        with self.assertRaisesRegex(Exception,'相同'):task.run()
        task.wait_click_ocr.assert_not_called()
    def test_preflight_has_no_input_or_confirmation(self):
        task=self.build(count=1,check_only=True);task.run()
        task.click.assert_not_called();task.wait_click_ocr.assert_not_called()
        self.assertEqual(self.result['status'],'PROBE_PASSED')
    def test_no_confirmation_means_no_input(self):
        task=self.build(count=1)
        with self.assertRaises(RuntimeError):task.run()
        task.click.assert_not_called();task.find_echo_enhance.assert_not_called()


class EventBoundaries(unittest.TestCase):
    def build(self,**options):
        self.result={'errors':[]}
        self.runtime=SimpleNamespace(assist_deadline=None,device_manager=SimpleNamespace(interaction=Mock()))
        cls=game_extensions.task_classes(self.runtime,lambda **kw:self.result.update(kw),self.result,
                                        make_request('elimination',duration=1,**options),ROOT)['event']
        task=object.__new__(cls);task._executor=SimpleNamespace(check_enabled=Mock(),sleep=Mock())
        task.screenshot=Mock();task.prepare_event=Mock();return task
    def test_preflight_does_not_start_challenge(self):
        task=self.build(check_only=True)
        with patch.object(TacetEliminationTask,'run') as execute:task.run()
        execute.assert_not_called();task.prepare_event.assert_called_once()
        self.assertEqual(self.result['status'],'PROBE_PASSED');self.assertFalse(self.result['event_completed'])
    def test_deadline_restores_executor_and_does_not_claim_all_complete(self):
        task=self.build();check=task.executor.check_enabled;sleep=task.executor.sleep
        task.completed_stages=2;task.claimed_rewards=1
        with patch.object(TacetEliminationTask,'run',side_effect=AssistDeadlineReached):task.run()
        self.assertIs(task.executor.check_enabled,check);self.assertIs(task.executor.sleep,sleep)
        self.assertIsNone(self.runtime.assist_deadline);self.assertTrue(self.runtime.device_manager.interaction.send_key_up.called)
        self.assertEqual(self.result['event_stages'],2);self.assertEqual(self.result['event_end_reason'],'time_limit')
        self.assertFalse(self.result['event_completed'])
    def test_unknown_error_propagates_but_always_releases_input(self):
        task=self.build()
        with patch.object(TacetEliminationTask,'run',side_effect=RuntimeError('unreadable board')):
            with self.assertRaisesRegex(RuntimeError,'unreadable board'):task.run()
        self.assertIsNone(self.runtime.assist_deadline);self.assertTrue(self.runtime.device_manager.interaction.mouse_up.called)
        self.assertNotEqual(self.result.get('status'),'EXECUTION_FINISHED')


class NewUIBoundaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        import qingxiao_panel as ui
        cls.app=QApplication.instance() or QApplication([]);ui.configure_fonts(cls.app);cls.app.setStyleSheet(ui.STYLE)
    def setUp(self):
        import qingxiao_panel as ui
        import legacy_panel
        self.ui=ui;self.temp=tempfile.TemporaryDirectory(dir=ROOT/'local-runs');self.runs=Path(self.temp.name);self.calls=[]
        def bridge(panel,action,callback):self.calls.append(action);callback({'Ok':True,'Tasks':[]})
        self.patches=[patch.object(ui,'RUNS',self.runs),patch.object(legacy_panel,'RUNS',self.runs),
            patch.object(assistant,'CONFIG',self.runs/'settings.json'),patch.object(ui.Panel,'bridge',bridge)]
        for p in self.patches:p.start()
        self.window=ui.Panel();self.window.timer.stop()
    def tearDown(self):
        self.window.active_id=None;self.window.close();self.app.processEvents()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_material_confirmation_cancel_prevents_dispatch(self):
        with patch.object(self.window,'confirm_materials',return_value=False):self.window.start_job('reconstruct')
        self.assertNotIn('start',self.calls);self.assertFalse((self.runs/'pending-manual.json').exists())
    def test_queued_daily_and_helpers_remain_frozen(self):
        self.window.active_id='running'
        self.window.prefs['daily_options']={'daily_farm':'forgery','index':3,'material':'Shell Credit'}
        self.window.start_job('daily');self.window.prefs['daily_options']['index']=8
        self.assertEqual(self.window.queue[0]['options']['index'],3)
        self.window.prefs['helper_options']=normalize_helper_options({'use_liberation':False,'pickup_whitelist':['吸收','薄荷']})
        self.window.start_job('quest');self.window.prefs['helper_options']['pickup_whitelist'].append('调查')
        self.assertFalse(self.window.queue[1]['options']['helper_options']['use_liberation'])
        self.assertEqual(self.window.queue[1]['options']['helper_options']['pickup_whitelist'],['吸收','薄荷'])
    def test_pending_reconstruct_receipt_blocks_direct_retry(self):
        folder=self.runs/'uncertain';folder.mkdir()
        atomic_json(folder/'manual-request.json',make_request('reconstruct',count=1,main_stat='暴击',confirmed_materials=True))
        report=folder/'report.json';atomic_json(report,{'pending_reconstruct':{'target':'暴击'}})
        self.assertIsNone(self.window.original_request({'_path':str(report)}))
    def test_target_and_limits_reach_request(self):
        self.window.reconstruct_target.setCurrentText('暴击伤害')
        self.window.controls['tacet_limit'].setValue(120)
        self.assertEqual(self.window.job_parameters('reconstruct')['main_stat'],'暴击伤害')
        self.assertEqual(self.window.job_parameters('tacet')['stamina_limit'],120)


if __name__=='__main__':unittest.main()
