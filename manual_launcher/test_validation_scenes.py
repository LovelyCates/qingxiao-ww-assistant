"""Preparation must leave actual auxiliary inputs to the production helpers."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from model import ROOT,make_request
sys.path.insert(0,str(ROOT/'ok-wuthering-waves-3.7.8'))
from validation_scenes import assist_scene,phone_dialog_scene,verify_assist_event


class ValidationSceneTests(unittest.TestCase):
    def boss(self):
        mouse=SimpleNamespace(run=Mock())
        boss=SimpleNamespace(config={'Teleport to Boss':'No','Which Boss Challenge to Teleport':4,
            'Boss':'Other','Repeat Farm Count':100,'Exit After Task':False},
            executor=SimpleNamespace(get_task_by_class=lambda cls:mouse,interaction=object()))
        for name in ('sleep','ensure_main','manage_boss_parameters','init_parameters',
                     'teleport_to_configured_boss_and_prepare','screenshot','click','combat_once','pick_f','pick_echo'):
            setattr(boss,name,Mock())
        boss.wait_until=Mock(return_value=True)
        boss.find_f_with_text=Mock(return_value=object());boss.absorb_echo_text=lambda:'吸收'
        return boss

    def test_pickup_preparation_cannot_absorb_in_place_of_the_actual_helper(self):
        boss=self.boss();original=dict(boss.config);original_f=boss.pick_f;original_echo=boss.pick_echo
        def approach(**kw):
            self.assertTrue(boss.pick_f());self.assertTrue(boss.pick_echo())
            return True,False
        boss.yolo_find_echo=Mock(side_effect=approach)
        adapter=SimpleNamespace(get_task_by_class=lambda cls:boss)
        with assist_scene(adapter,'pickup_echo',Mock()):
            original_f.assert_not_called();original_echo.assert_not_called()
            self.assertIs(boss.pick_f,original_f);self.assertIs(boss.pick_echo,original_echo)
        self.assertEqual(boss.config,original)

    def test_failed_scene_never_runs_helper_body_and_restores_config(self):
        boss=self.boss();old=dict(boss.config);boss.wait_until.return_value=False
        body=Mock()
        with self.assertRaises(RuntimeError):
            with assist_scene(SimpleNamespace(get_task_by_class=lambda cls:boss),'combat_boss',Mock()):body()
        body.assert_not_called();self.assertEqual(boss.config,old)
        boss.combat_once.assert_not_called()

    def test_scene_names_are_a_finite_action_specific_allowlist(self):
        self.assertEqual(make_request('pickup',validation_scene='pickup_echo')['ValidationScene'],'pickup_echo')
        self.assertEqual(make_request('combat',validation_scene='combat_boss')['ValidationScene'],'combat_boss')
        self.assertEqual(make_request('dialog',validation_scene='dialog_phone')['ValidationScene'],'dialog_phone')
        self.assertEqual(make_request('combat',validation_scene='combat_tacet')['ValidationScene'],'combat_tacet')
        for action,scene in (('dialog','combat_boss'),('pickup','combat_boss'),('combat','pickup_echo'),
                             ('pickup','arbitrary.py'),('pickup',True)):
            with self.subTest(action=action,scene=scene),self.assertRaises(ValueError):
                make_request(action,validation_scene=scene)

    def test_phone_scene_stops_before_auxiliary_actions_if_the_title_is_not_feixun(self):
        task=SimpleNamespace(**{name:Mock() for name in ('ensure_main','send_key_down','send_key_up','click_relative','screenshot','wait_ocr')})
        task.wait_ocr.side_effect=RuntimeError('not NPC Feixun')
        body=Mock()
        with self.assertRaises(RuntimeError):
            with phone_dialog_scene(task,Mock()):body()
        body.assert_not_called()
        task.send_key_up.assert_called_once_with('alt')
        self.assertEqual(task.ensure_main.call_count,2)

    def test_tacet_reward_evidence_approaches_without_opening_claim(self):
        task=SimpleNamespace(ocr=Mock(return_value=[]),screenshot=Mock(),find_treasure_icon=Mock(return_value=True),
                             walk_to_treasure=Mock(),find_f_with_claim_text=Mock(return_value=True))
        self.assertTrue(verify_assist_event(task,'combat_tacet',Mock()))
        task.walk_to_treasure.assert_called_once_with(send_f=False)

    def test_tacet_target_gap_without_reward_evidence_stays_incomplete(self):
        task=SimpleNamespace(ocr=Mock(return_value=[]),screenshot=Mock(),find_treasure_icon=Mock(return_value=False),
                             walk_to_treasure=Mock())
        self.assertFalse(verify_assist_event(task,'combat_tacet',Mock()))
        task.walk_to_treasure.assert_not_called()
