"""Exercise installed upstream loops with all game input replaced by test doubles."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch
from model import ROOT,RUNS,make_request
sys.path.insert(0,str(ROOT/'ok-wuthering-waves-3.7.8'))
from game_extensions import task_classes
import src.task.EnhanceEchoTask as enhance_module

class MaterialAdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=RUNS);self.updates=[]
    def tearDown(self):self.temp.cleanup()
    def task(self,action,confirmed=True,count=1):
        options=make_request(action,count=count,confirmed_materials=confirmed)
        classes=task_classes(None,lambda **values:self.updates.append(values),{'errors':[]},options,Path(self.temp.name))
        task=object.__new__(classes[action]);task.config={};task.info={};task.key_config={}
        task._executor=SimpleNamespace(debug=False)
        for name in ('ensure_main','send_key','sleep','screenshot','click','click_relative','log_info',
                     'wait_click_feature','wait_click_skip_dialog_confirm','click_dialog_left_button','next_frame'):
            setattr(task,name,Mock())
        task.info_set=lambda key,value:task.info.update({key:value})
        return task
    def test_unconfirmed_material_tasks_never_touch_game_input(self):
        for action in ('merge','enhance'):
            task=self.task(action,confirmed=False)
            with self.subTest(action=action),self.assertRaises(RuntimeError):task.run()
            task.ensure_main.assert_not_called();task.click.assert_not_called();task.send_key.assert_not_called()
    def test_echo_preflight_is_read_only_without_material_confirmation(self):
        result={}
        cls=task_classes(None,lambda **kw:result.update(kw),result,
                         make_request('enhance',check_only=True),ROOT)['enhance']
        task=object.__new__(cls)
        task.find_echo_enhance=Mock(return_value=True);task.read_selected_level=Mock(return_value=25)
        task.screenshot=Mock();task.click=Mock();task.send_key=Mock()
        task.run()
        task.click.assert_not_called();task.send_key.assert_not_called()
        self.assertEqual(result['selected_echo_level'],25)
        self.assertEqual(result['status'],'PROBE_PASSED')
    def test_merge_preflight_never_submits_materials(self):
        result={}
        cls=task_classes(None,lambda **kw:result.update(kw),result,
                         make_request('merge',check_only=True),ROOT)['merge']
        task=object.__new__(cls);task.inspect_merge_filter=Mock(return_value=['已弃置'])
        task.select_discarded_batch=Mock(return_value=100)
        task.merge_full_batch=Mock()
        task.run()
        task.merge_full_batch.assert_not_called()
        self.assertTrue(result['check_only']);self.assertEqual(result['merge_batches'],0)
        self.assertEqual(result['merge_selected_materials'],100)
    def test_real_upstream_merge_loop_stops_at_requested_batch_limit(self):
        task=self.task('merge',count=2)
        def verified_page():task.discard_filter_verified=True
        task.open_merge_page=Mock(side_effect=verified_page)
        task.select_discarded_batch=Mock(return_value=100)
        task.require_discard_filter_chip=Mock();task.read_material_count=Mock(return_value=100)
        task.wait_click_ocr=Mock()
        task.wait_ocr=Mock(side_effect=lambda *args,**kw: ['获得声骸'] if kw.get('match')=='获得声骸' else [])
        task.run()
        self.assertEqual(task.completed_batches,2)
        self.assertEqual(task.wait_click_ocr.call_count,2)
        self.assertEqual(sum(c.kwargs.get('match')=='获得声骸' for c in task.wait_ocr.call_args_list),2)
        self.assertEqual(task.open_merge_page.call_count,2)
        self.assertEqual(self.updates[-1]['merge_batches'],2)
    def test_real_upstream_enhance_loop_cannot_select_a_second_candidate(self):
        task=self.task('enhance',count=1)
        task.find_echo_enhance=Mock(side_effect=[True,False,True]);task.is_0_level=Mock(return_value=True)
        task.ensure_stage_settings=Mock();task.ensure_material_quality=Mock();task.find_add_mat=Mock(return_value=True);task.wait_click_ocr=Mock(return_value=True)
        task.wait_ocr=Mock(return_value=[]);task.ocr=Mock(return_value=[]);task.find_boxes=Mock(return_value=[])
        task.read_stat_decision=Mock(return_value=False)
        task.trash_and_esc=Mock(side_effect=lambda:task.info.update({'失败声骸数量':1}))
        original_startfile=enhance_module.os.startfile
        with patch.object(enhance_module,'clear_folder',Mock()) as clear:
            task.run();clear.assert_not_called()
        self.assertEqual(task.selected_count,1);self.assertEqual(task.is_0_level.call_count,1)
        self.assertEqual(task.wait_click_ocr.call_count,1);self.assertIs(enhance_module.os.startfile,original_startfile)
        self.assertEqual(self.updates[-1]['enhance_selected'],1)
    def test_enhance_precondition_error_restores_scoped_file_hooks(self):
        task=self.task('enhance');task.find_echo_enhance=Mock(side_effect=RuntimeError('not in filtered bag'))
        original_clear=enhance_module.clear_folder;original_startfile=enhance_module.os.startfile
        with self.assertRaises(RuntimeError):task.run()
        self.assertIs(enhance_module.clear_folder,original_clear);self.assertIs(enhance_module.os.startfile,original_startfile)
        task.click.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
