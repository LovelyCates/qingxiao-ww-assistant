"""Exercise OCR decisions and task transitions without game input."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from model import ROOT, make_request, normalize_enhance_rules
from assist_guard import AssistDeadlineReached, executor_deadline, release_inputs
from game_extensions import task_classes

sys.path.insert(0, str(ROOT/'ok-wuthering-waves-3.7.8'))
from src.task.echo_stats import EchoRecognitionError, pair_stats
from src.task.EnhanceEchoTask import EnhanceEchoTask


def boxes(stats):
    return ([SimpleNamespace(name=name,y=30*i,height=20) for i,(name,_) in enumerate(stats)],
            [SimpleNamespace(name=value,y=30*i+2,height=19) for i,(_,value) in enumerate(stats)])


class EchoEvidenceTests(unittest.TestCase):
    def task(self):
        result={'errors':[]}
        def save(**kw):result.update(kw)
        cls=task_classes(None,save,result,make_request('enhance',count=1,confirmed_materials=True),ROOT)['enhance']
        task=object.__new__(cls);task.config={};task.info={};task._executor=SimpleNamespace(debug=False)
        task.info_set=lambda key,value:task.info.update({key:value})
        task.info_get=lambda key:task.info.get(key,0)
        for name in ('click','next_frame','sleep','screenshot','log_info','log_debug','trash_and_esc','lock_and_esc'):
            setattr(task,name,Mock())
        task.find_echo_enhance=Mock(side_effect=[True,False,True])
        task.is_0_level=Mock(return_value=True)
        task.ensure_stage_settings=Mock();task.ensure_material_quality=Mock();task.find_add_mat=Mock(return_value=True)
        task.wait_click_ocr=Mock(return_value=True);task.wait_ocr=Mock(return_value=[])
        task.ocr=Mock(return_value=[])
        return task,result

    def test_bad_ocr_after_first_stage_does_not_spend_again_or_discard(self):
        task,result=self.task();task.find_boxes=Mock(return_value=[])
        with self.assertRaises(EchoRecognitionError):task.run()
        self.assertEqual(task.wait_click_ocr.call_count,1)
        task.trash_and_esc.assert_not_called();task.lock_and_esc.assert_not_called()
        self.assertEqual(result['status'],'NEEDS_REVIEW');self.assertEqual(result['enhance_selected'],1)
        self.assertEqual(result['enhance_rejected'],0);self.assertIn('stop_reason',result)

    def test_good_ocr_must_be_stable_and_stage_count_must_match(self):
        task,_=self.task();props,values=boxes([('暴击','8.1%')])
        task.find_boxes=Mock(side_effect=[props,values]*2)
        task.check_echo_stats=Mock(return_value=True)
        self.assertTrue(task.read_stat_decision(1))
        self.assertEqual(task.ocr.call_count,2)
        task.check_echo_stats.assert_called_once()
        task.find_boxes=Mock(side_effect=[props,values]*4)
        task.check_echo_stats.reset_mock()
        with self.assertRaises(EchoRecognitionError):task.read_stat_decision(2)
        task.check_echo_stats.assert_not_called()

    def test_one_bad_read_can_recover_before_any_decision(self):
        task,_=self.task();props,values=boxes([('暴击','8.1%')])
        task.find_boxes=Mock(side_effect=[[],[],props,values,props,values]);task.check_echo_stats=Mock(return_value=True)
        self.assertTrue(task.read_stat_decision(1));self.assertEqual(task.ocr.call_count,3)

    def test_full_good_candidate_runs_five_stages_and_locks_once(self):
        task,result=self.task()
        stats=[('暴击','8.1%'),('暴击伤害','16.2%'),('攻击','8.6%'),('生命','320'),('防御','40')]
        reads=[]
        for count in range(1,6):
            props,values=boxes(stats[:count]);reads.extend([props,values,props,values])
        task.find_boxes=Mock(side_effect=reads)
        task.lock_and_esc=Mock(side_effect=lambda:task.info.update({'成功声骸数量':1}))
        task.run()
        self.assertEqual(task.wait_click_ocr.call_count,5)
        task.lock_and_esc.assert_called_once();task.trash_and_esc.assert_not_called()
        self.assertEqual(result['enhance_success'],1);self.assertEqual(result['enhance_selected'],1)

    def test_confirmed_low_first_crit_rejects_after_one_stage(self):
        task,result=self.task();props,values=boxes([('暴击','6.3%')])
        task.find_boxes=Mock(side_effect=[props,values]*2)
        task.trash_and_esc=Mock(side_effect=lambda:task.info.update({'失败声骸数量':1}))
        task.run();self.assertEqual(task.wait_click_ocr.call_count,1)
        task.trash_and_esc.assert_called_once();task.lock_and_esc.assert_not_called()
        self.assertEqual(result['enhance_rejected'],1)

    def test_complete_ocr_validates_later_rows_before_rejection(self):
        task,_=self.task();task.config=normalize_enhance_rules()
        # A low first crit must not hide an unreadable later row.
        with self.assertRaises(EchoRecognitionError):task.check_echo_stats(*boxes([('暴击','6.3%'),('攻击','..%')]))

    def test_duplicate_unknown_and_missing_percent_are_uncertain(self):
        for stats in ([('暴击','8.1')],[('未知属性','10%')],[('暴击','8.1%'),('暴击','8.1%')],
                      [('防御','1.2')],[('暴击','0%')],[('攻击','120%')]):
            with self.subTest(stats=stats),self.assertRaises(EchoRecognitionError):pair_stats(*boxes(stats))

    def test_reordered_boxes_and_traditional_labels_pair_correctly(self):
        props,values=boxes([('暴擊','8.1％'),('暴擊傷害','16.2%')])
        self.assertEqual(pair_stats(list(reversed(props)),values),[('暴击','8.1%'),('暴击伤害','16.2%')])
    def test_ocr_row_decoration_preserves_known_stat_but_not_unknown_names(self):
        self.assertEqual(pair_stats(*boxes([('+.防御','12.8%')])),[('防御百分比','12.8%')])
        with self.assertRaises(EchoRecognitionError):pair_stats(*boxes([('+.未知','12.8%')]))

    def test_legacy_rules_migrate_without_hidden_flags_and_no_aliasing(self):
        old={'require_double_crit':False,'valid_stats':['暴击','暴击伤害','攻击百分比'],'minimum_valid':3,'crit_score':13.8,'first_crit':6.9}
        actual=normalize_enhance_rules(old)
        self.assertFalse(actual['require_valid_before_crit']);self.assertFalse(actual['require_first_valid'])
        actual['valid_stats'].clear();self.assertEqual(len(old['valid_stats']),3)

    def test_invalid_rule_values_and_truthy_confirmation_rejected(self):
        for key,value in [('crit_score',float('nan')),('first_crit',float('inf')),('valid_stats',['攻击','攻击']),('require_first_valid','false')]:
            rules=normalize_enhance_rules();rules[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):make_request('enhance',enhance_rules=rules)
        with self.assertRaises(ValueError):make_request('merge',confirmed_materials='false')
    def test_level_zero_requires_explicit_single_level_read(self):
        task,_=self.task()
        del task.is_0_level
        task.ocr=Mock(return_value=[])
        with self.assertRaises(EchoRecognitionError):task.is_0_level()
        task.ocr=Mock(side_effect=[[SimpleNamespace(name='+0')],[]])
        self.assertTrue(task.is_0_level())
        task.ocr=Mock(side_effect=[[],[SimpleNamespace(name='+25')]])
        self.assertFalse(task.is_0_level())
        task.ocr=Mock(return_value=[SimpleNamespace(name='+0')])
        with self.assertRaises(EchoRecognitionError):task.is_0_level()


class DeadlineTests(unittest.TestCase):
    def test_combat_sleep_checks_forward_only_to_active_helper(self):
        cls=task_classes(None,Mock(),{'errors':[]},make_request('combat'),ROOT)['assist']
        task=object.__new__(cls);helper=Mock()
        task.active_helper=helper;task.sleep_check();helper.sleep_check.assert_called_once()
        task.active_helper=None;task.sleep_check();helper.sleep_check.assert_called_once()
    def test_deadline_interrupts_internal_wait_and_restores_executor(self):
        clock=SimpleNamespace(now=0)
        sleeper=lambda seconds:setattr(clock,'now',clock.now+seconds)
        check=Mock();executor=SimpleNamespace(check_enabled=check,sleep=sleeper)
        with self.assertRaises(AssistDeadlineReached):
            with executor_deadline(executor,60,lambda:clock.now):executor.sleep(90)
        self.assertEqual(clock.now,60);self.assertIs(executor.sleep,sleeper);self.assertIs(executor.check_enabled,check)

    def test_deadline_blocks_new_input_checkpoint(self):
        executor=SimpleNamespace(check_enabled=Mock(),sleep=Mock());clock=SimpleNamespace(now=0)
        with executor_deadline(executor,60,lambda:clock.now):
            clock.now=60
            with self.assertRaises(AssistDeadlineReached):executor.check_enabled()
        executor.check_enabled.assert_not_called()

    def test_release_continues_if_one_key_fails(self):
        interaction=Mock();interaction.send_key_up.side_effect=[RuntimeError('lost focus')]+[None]*15
        release_inputs(interaction)
        self.assertEqual(interaction.send_key_up.call_count,16)
        self.assertEqual(interaction.mouse_up.call_count,3)


class MaterialQualityTests(unittest.TestCase):
    def test_unknown_quality_never_opens_or_selects_materials(self):
        task=object.__new__(EnhanceEchoTask)
        task.ocr=Mock(return_value=[]);task.click=Mock();task.wait_click_ocr=Mock()
        with self.assertRaises(EchoRecognitionError):task.ensure_material_quality()
        task.click.assert_not_called();task.wait_click_ocr.assert_not_called()

    def test_switching_quality_requires_verified_final_filter(self):
        task=object.__new__(EnhanceEchoTask)
        task.ocr=Mock(side_effect=[[SimpleNamespace(name='四星及以下道具')],[]])
        task.click=Mock();task.wait_click_ocr=Mock();task.screenshot=Mock()
        with self.assertRaises(EchoRecognitionError):task.ensure_material_quality()

    def test_resuming_candidate_cannot_expand_the_candidate_limit(self):
        with self.assertRaises(ValueError):
            make_request('enhance',count=2,validation_scene='echo_current_resume')

if __name__=='__main__':unittest.main(verbosity=2)
