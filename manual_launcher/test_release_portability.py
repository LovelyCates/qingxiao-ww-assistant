"""Portable configuration and permission-task ownership; never mutate real tasks."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from model import ROOT
from runtime_settings import game_executable,save_game_executable,load_runtime_settings,panel_instance_key

class RuntimePaths(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.environment=patch.dict(os.environ,{},clear=False);self.environment.start();os.environ.pop('WW_GAME_EXE',None)
    def tearDown(self):self.environment.stop();self.temp.cleanup()
    def test_unconfigured_install_has_no_machine_specific_fallback(self):
        self.assertIsNone(game_executable(self.root));self.assertFalse((self.root/'local-config.json').exists())
    def test_game_path_roundtrip_with_unicode_and_spaces(self):
        path=self.root/'鸣潮 game.exe';path.write_bytes(b'fixture')
        save_game_executable(path,self.root);self.assertEqual(game_executable(self.root),path)
        self.assertEqual(set(load_runtime_settings(self.root)),{'game_executable'})
    def test_missing_or_non_exe_paths_never_replace_config(self):
        path=self.root/'notes.txt';path.write_text('fixture')
        for candidate in [path,self.root/'missing.exe']:
            with self.assertRaises(ValueError):save_game_executable(candidate,self.root)
        self.assertFalse((self.root/'local-config.json').exists())
    def test_invalid_json_and_unknown_fields_fail_explicitly(self):
        path=self.root/'local-config.json'
        for text in ['not JSON',json.dumps({'game_executable':42}),json.dumps({'unexpected':True})]:
            path.write_text(text)
            with self.assertRaises(ValueError):game_executable(self.root)
    def test_environment_override_and_directory_specific_instance_key(self):
        with patch.dict(os.environ,{'WW_GAME_EXE':str(self.root/'override.exe')}):
            self.assertEqual(game_executable(self.root),self.root/'override.exe')
        self.assertEqual(panel_instance_key(self.root),panel_instance_key(self.root))
        self.assertNotEqual(panel_instance_key(self.root),panel_instance_key(self.root/'another copy'))

class TaskOwnership(unittest.TestCase):
    def assert_ownership(self,*,actual=None,arguments=None,command=None):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);expected=folder/'中文 path with spaces'
            task=ET.Element('Task',xmlns='http://schemas.microsoft.com/windows/2004/02/mit/task')
            exe=ET.SubElement(ET.SubElement(task,'Actions'),'Exec')
            ET.SubElement(exe,'Command').text=command or str(Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe')
            ET.SubElement(exe,'Arguments').text=arguments or '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+str(expected/'Run-Local.ps1')+'" -Mode probe'
            ET.SubElement(exe,'WorkingDirectory').text=str(actual or expected)
            fixture=folder/'task.xml';fixture.write_bytes(ET.tostring(task,encoding='utf-8'))
            script=folder/'check.ps1';script.write_text('param($OwnershipFile,$FixtureFile,$Root)\n$ErrorActionPreference="Stop"\n. $OwnershipFile\nAssert-ManualTaskOwnership (Get-Content -Raw -Encoding UTF8 -LiteralPath $FixtureFile) $Root "MC-Auto-probe"\n',encoding='utf-8-sig')
            return subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),str(ROOT/'manual_launcher/Task-Ownership.ps1'),str(fixture),str(expected)],capture_output=True,timeout=15)
    def test_owned_task_with_unicode_and_spaces_is_accepted(self):
        result=self.assert_ownership();self.assertEqual(result.returncode,0,result.stderr.decode(errors='replace'))
    def test_another_project_cannot_start_or_stop_this_projects_tasks(self):
        self.assertNotEqual(self.assert_ownership(actual=ROOT).returncode,0)
    def test_unexpected_command_or_arguments_are_rejected(self):
        self.assertNotEqual(self.assert_ownership(command='cmd.exe').returncode,0)
        self.assertNotEqual(self.assert_ownership(arguments='-Command Write-Output unexpected').returncode,0)

if __name__=='__main__':unittest.main()
