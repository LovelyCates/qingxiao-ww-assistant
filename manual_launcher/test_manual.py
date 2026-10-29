import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from model import JOBS, ROOT, make_request

SHELL = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'


class DispatchTests(unittest.TestCase):
    def dispatch(self, request, mode):
        with tempfile.TemporaryDirectory(dir=ROOT / 'local-runs') as folder:
            path = Path(folder) / 'request.json'
            path.write_text(json.dumps(request, ensure_ascii=False), encoding='utf-8')
            return subprocess.run([str(SHELL), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(ROOT / 'Run-Local.ps1'), '-ValidateOnly', '-RequestFile', str(path), '-Mode', mode],
                capture_output=True, timeout=20)

    def test_all_buttons_route_without_executing(self):
        for action, (_, mode, task) in JOBS.items():
            with self.subTest(action=action):
                extra={'accounts':[dict(id='11111111-1111-4111-8111-111111111111',label='测试账号',account_key='190****0001',enabled=True,steps=[])]} if action=='multiaccount' else {}
                request = make_request(action, index=21 if action == 'tacet' else 1,confirmed_materials=action in ('enhance','merge','reconstruct'),**extra)
                request['Comment'] = '中文配置，不能被旧版 PowerShell 误读'
                result = self.dispatch(request, task.removeprefix('MC-Auto-'))
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                data = json.loads(result.stdout.decode('utf-8-sig'))
                self.assertEqual(data['Mode'], mode)
                self.assertEqual(data['Action'], action)

    def test_expired_request_never_runs(self):
        request = make_request('tacet')
        request['CreatedAt'] = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        self.assertNotEqual(self.dispatch(request, 'daily').returncode, 0)

    def test_domain_stamina_limit_survives_dispatch_and_rejects_invalid_units(self):
        for action,cost in (('tacet',60),('forgery',40),('simulation',40)):
            self.assertEqual(self.dispatch(make_request(action,stamina_limit=cost),'daily').returncode,0)
        for value in (True,20,60,280,'40'):
            request=make_request('forgery');request['StaminaLimit']=value
            self.assertNotEqual(self.dispatch(request,'daily').returncode,0)

    def test_wrong_task_never_runs(self):
        self.assertNotEqual(self.dispatch(make_request('weekly'), 'daily').returncode, 0)
    def test_weekly_check_requires_a_boolean_and_the_weekly_task(self):
        self.assertEqual(self.dispatch(make_request('weekly',check_only=True),'weekly').returncode,0)
        request=make_request('weekly');request['CheckOnly']='false'
        self.assertNotEqual(self.dispatch(request,'weekly').returncode,0)
    def test_material_preflight_dispatch_does_not_authorize_consumption(self):
        request=make_request('enhance',check_only=True)
        self.assertEqual(self.dispatch(request,'daily').returncode,0)
        request['CheckOnly']=False
        self.assertNotEqual(self.dispatch(request,'daily').returncode,0)
        request['CheckOnly']='true'
        self.assertNotEqual(self.dispatch(request,'daily').returncode,0)

    def test_command_text_is_not_accepted_as_a_target(self):
        request = make_request('echo')
        request['Scope'] = 'boss; Write-Output injected'
        self.assertNotEqual(self.dispatch(request, 'daily').returncode, 0)

    def test_bad_index_never_runs(self):
        request = make_request('forgery')
        request['Index'] = 21
        self.assertNotEqual(self.dispatch(request, 'daily').returncode, 0)

    def test_daily_target_bounds_match_python_protocol(self):
        for farm,index in (('tacet',21),('forgery',20),('simulation',1)):
            request=make_request('daily',daily_farm=farm,index=index)
            self.assertEqual(self.dispatch(request,'daily').returncode,0)
            request['Index']=index+1
            self.assertNotEqual(self.dispatch(request,'daily').returncode,0)

    def test_ui_construction_has_no_game_side_effects(self):
        os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PySide6.QtWidgets import QApplication
        from qingxiao_panel import Panel,configure_fonts
        app = QApplication.instance() or QApplication([])
        configure_fonts(app)
        window = Panel()
        window.timer.stop()
        self.assertEqual(len(window.buttons), 18)
        self.assertEqual(window.pages.count(),9)
        self.assertIsNone(window.active_id)
        window.controls['scope'].setCurrentIndex(1)
        self.assertEqual(window.controls['echo_index'].maximum(), 9)
        window.controls['scope'].setCurrentIndex(2)
        self.assertEqual(window.controls['echo_index'].maximum(), 10)
        self.assertTrue(all(button.isEnabled() for button in window.buttons))
        window.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
