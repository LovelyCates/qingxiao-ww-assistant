"""Exercise upstream restart fixes against real local task methods."""
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from model import ROOT
sys.path.insert(0,str(ROOT/'ok-wuthering-waves-3.7.8'))
from src.task.BaseCombatTask import BaseCombatTask
from src.task.WWOneTimeTask import WWOneTimeTask


class RestartTests(unittest.TestCase):
    def test_interrupted_rotation_is_cleared_before_first_startup_sleep(self):
        calls=[]
        task=object.__new__(BaseCombatTask)
        task.chars=[object(),object(),object()];task.freeze_durations=[(1,2,3)]
        task.reset_to_false=Mock(side_effect=lambda reason:calls.append('reset'))
        mouse=SimpleNamespace(run=lambda:calls.append('mouse'))
        task._executor=SimpleNamespace(get_task_by_class=lambda cls:mouse,interaction=object())
        def checked_sleep(seconds):
            self.assertEqual(task.chars,[None,None,None])
            self.assertEqual(task.freeze_durations,[])
            self.assertEqual(calls,['reset','mouse'])
            calls.append('sleep')
        task.sleep=checked_sleep
        WWOneTimeTask.run(task)
        self.assertEqual(calls,['reset','mouse','sleep'])

    def test_noncombat_tasks_still_initialize_normally(self):
        mouse=SimpleNamespace(run=Mock())
        task=SimpleNamespace(executor=SimpleNamespace(get_task_by_class=lambda cls:mouse,interaction=object()),sleep=Mock())
        WWOneTimeTask.run(task)
        mouse.run.assert_called_once();task.sleep.assert_called_once_with(.5)
