import unittest
from unittest.mock import Mock
from pathlib import Path
import tempfile
import threading
from model import RUNS,read_json
from game_window import GameWindowPolicy

class FocusTests(unittest.TestCase):
    def policy(self,current,previous=200):
        policy=GameWindowPolicy.__new__(GameWindowPolicy);policy.hwnd=100;policy.return_hwnd=previous
        policy.user32=Mock();policy.user32.GetForegroundWindow.return_value=current
        policy.user32.IsWindow.return_value=True
        return policy
    def test_game_activation_returns_to_original_application(self):
        policy=self.policy(100);policy.return_focus();policy.user32.SetForegroundWindow.assert_called_once_with(200)
    def test_users_new_application_keeps_focus(self):
        policy=self.policy(300);policy.return_focus();policy.user32.SetForegroundWindow.assert_not_called()
    def test_no_focus_transfer_to_closed_or_game_window(self):
        for previous in (100,200):
            policy=self.policy(100,previous);policy.user32.IsWindow.return_value=False
            policy.return_focus();policy.user32.SetForegroundWindow.assert_not_called()
    def layered_policy(self):
        policy=self.policy(300);policy.hidden=False;policy.hide_backend=None;policy.original_style=None;policy.write_lease=Mock()
        style=[0x40000]
        policy.user32.GetWindowLongPtrW.side_effect=lambda *_:style[0]
        policy.user32.SetWindowLongPtrW.side_effect=lambda _h,_n,value:style.__setitem__(0,value)
        policy.user32.SetLayeredWindowAttributes.return_value=1
        policy.dwm=Mock();policy.dwm.DwmSetWindowAttribute.return_value=-2147024891;policy.dwm.DwmGetWindowAttribute.return_value=0
        return policy,style
    def test_repeated_hide_keeps_the_original_window_style(self):
        policy,style=self.layered_policy();policy.cloak(True);policy.cloak(True)
        self.assertEqual(policy.original_style,0x40000)
        self.assertEqual(policy.user32.SetWindowLongPtrW.call_count,1)
        policy.cloak(False);self.assertEqual(style[0],0x40000);self.assertFalse(policy.hidden)
        policy.write_lease.assert_called_with(False)
    def test_repeated_show_does_not_modify_already_restored_window(self):
        policy,style=self.layered_policy();policy.cloak(True);policy.cloak(False)
        count=policy.user32.SetWindowLongPtrW.call_count;policy.cloak(False)
        self.assertEqual(policy.user32.SetWindowLongPtrW.call_count,count)
    def test_restore_failure_keeps_recovery_lease_active(self):
        policy,style=self.layered_policy();policy.cloak(True)
        policy.user32.SetWindowLongPtrW.side_effect=lambda *_:None
        with self.assertRaises(RuntimeError):policy.cloak(False)
        self.assertTrue(policy.hidden);policy.write_lease.assert_called_with(True)
    def test_presentation_error_requests_worker_stop_instead_of_silently_dying(self):
        with tempfile.TemporaryDirectory(dir=RUNS) as folder:
            policy=self.policy(300);policy.command_file=Path(folder)/'window-command.json';policy.request_id='test-request'
            policy.save=Mock();policy.stopped=threading.Event();policy._run_loop=Mock(side_effect=RuntimeError('restore failed'))
            policy.run();request=read_json(Path(folder)/'stop-request.json')
            self.assertEqual(request['RequestId'],'test-request');self.assertEqual(request['Reason'],'window_policy_error')
            self.assertTrue(policy.stopped.is_set());self.assertEqual(policy.save.call_args.kwargs['window_policy_error'],'restore failed')

if __name__=='__main__':unittest.main(verbosity=2)
