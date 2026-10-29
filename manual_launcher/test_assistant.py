"""Exercise credential handling, hostile plans and both real HTTP wire formats."""
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import assistant as a
from history import IncrementalTail,RunHistory
from model import make_request

class AssistantTests(unittest.TestCase):
    def test_catalog_plans_cannot_become_commands(self):
        for plan in (
            {'reply':'x','steps':[{'action':'powershell','options':{}}]},
            {'reply':'x','steps':[{'action':'probe','options':{'command':'calc.exe'}}]},
            {'reply':'x','steps':[{'action':'echo','options':{'count':True}}]},
            {'reply':'x','steps':[{'action':'pickup'},{'action':'daily'}]},
            {'reply':'x','steps':[{'action':'echo','options':{'index':99}}]},
            {'reply':'x','steps':[{'action':'probe','options':{'confirmed_materials':True}}]},
            {'reply':'x','steps':[{'action':'tacet','options':{'count':1}}]},
            {'reply':'x','steps':[{'action':'probe','options':{'duration':1}}]},
        ):
            with self.subTest(plan=plan),self.assertRaises(ValueError):a.validate_plan(plan)
        plan=a.validate_plan({'reply':'先检查再周常','steps':[{'action':'probe'},{'action':'weekly'}]})
        self.assertEqual(len(plan['steps']),2)

    def test_local_intents_keep_ambiguous_materials_unexecuted(self):
        self.assertEqual(a.offline_plan('检查今天进度')['steps'][0]['action'],'probe')
        self.assertEqual(a.offline_plan('刷模拟贝币')['steps'][0]['options']['material'],'Shell Credit')
        self.assertFalse(a.offline_plan('刷凝素')['steps'])
        self.assertEqual(a.offline_plan('停止任务')['steps'][0]['action'],'stop')
        self.assertEqual(a.offline_plan('凝素第3项')['steps'][0]['options']['index'],3)
        with self.assertRaises(ValueError):a.offline_plan('凝素第999项')
    def test_inspection_requests_cannot_silently_become_weekly_runs(self):
        plan=a.offline_plan('检查这周乐园完成了没')
        self.assertTrue(plan['steps'][0]['options']['check_only'])
        self.assertNotIn('check_only',a.offline_plan('帮我完成乐园周常')['steps'][0]['options'])
        self.assertEqual(a.offline_plan('自动拾取5分钟')['steps'][0]['options']['duration'],5)
        with self.assertRaises(ValueError):a.validate_plan({'reply':'x','steps':[{'action':'daily','options':{'check_only':True}}]})
    def test_boss_request_keeps_target_and_round_limit(self):
        plan=a.offline_plan('刷Boss第1项，1次')
        self.assertEqual(plan['steps'][0]['action'],'echo')
        self.assertEqual(plan['steps'][0]['options'],{'scope':'boss','index':1,'count':1})
        self.assertEqual(a.offline_plan('刷首领第 2个，3次')['steps'][0]['options'],{'scope':'boss','index':2,'count':3})
        self.assertFalse(a.offline_plan('无音区第1项，1次')['steps'])
        self.assertFalse(a.offline_plan('模拟贝币1次')['steps'])
        self.assertEqual(a.offline_plan('Boss刷完了吗')['steps'][0]['action'],'status')
        self.assertFalse(a.offline_plan('怎么自动打Boss')['steps'])

    def test_dpapi_roundtrip_and_no_plaintext_on_disk(self):
        key='test-only-not-a-real-key'
        encrypted=a.protect_secret(key)
        self.assertNotIn(key,encrypted)
        self.assertEqual(a.protect_secret(encrypted,decrypt=True),key)
        with tempfile.TemporaryDirectory() as folder,patch.object(a,'CONFIG',Path(folder)/'settings.json'):
            a.save_settings({'enabled':True,'base_url':'https://api.example.com/v1','model':'test-model','protocol':'responses'},key=key)
            self.assertNotIn(key,a.CONFIG.read_text())
            self.assertEqual(a.get_key(),key)
            self.assertTrue(a.load_settings()['key_saved'])

    def test_endpoint_credentials_and_insecure_remote_rejected(self):
        for value in ('http://remote.example/v1','https://secret@api.example/v1','https://api.example/v1?key=secret','file:///x'):
            with self.subTest(value=value),self.assertRaises(ValueError):a.validate_endpoint(value)
        self.assertEqual(a.validate_endpoint('http://127.0.0.1:8000/v1/'),'http://127.0.0.1:8000/v1')

    def test_real_http_responses_and_compat_chat(self):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append((self.path,body,self.headers.get('Authorization')))
                content=json.dumps({'reply':'读取今日进度','steps':[{'action':'probe','options':{}}]},ensure_ascii=False)
                data={'output':[{'type':'message','content':[{'type':'output_text','text':content}]}]} if self.path.endswith('/responses') else {'choices':[{'message':{'content':content}}]}
                payload=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as folder,patch.object(a,'CONFIG',Path(folder)/'settings.json'):
                for protocol in ('responses','chat'):
                    a.save_settings({'enabled':True,'base_url':f'http://127.0.0.1:{server.server_port}/v1','model':'wire-test','protocol':protocol},remember=False)
                    result=a.llm_plan('检查今天',snapshot={'activity':100},session_key='test-only-key')
                    self.assertEqual(result['source'],'llm');self.assertEqual(result['steps'][0]['action'],'probe')
                self.assertEqual(seen[0][0],'/v1/responses');self.assertFalse(seen[0][1]['store'])
                self.assertEqual(seen[1][0],'/v1/chat/completions');self.assertEqual(seen[1][2],'Bearer test-only-key')
        finally:server.shutdown();server.server_close()

    def test_log_incremental_rotation_and_bounding(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'stdout.log';path.write_text('one\n',encoding='utf-8');tail=IncrementalTail(limit=40)
            text,changed=tail.read(folder);self.assertTrue(changed);self.assertIn('one',text)
            self.assertFalse(tail.read(folder)[1])
            with path.open('a') as stream:stream.write('two\n')
            self.assertIn('two',tail.read(folder)[0]);path.write_text('new\n');self.assertIn('new',tail.read(folder)[0])
            path.write_text('x'*200);self.assertLessEqual(len(tail.read(folder)[0]),41)

    def test_enhancement_rules_fail_closed(self):
        with self.assertRaises(ValueError):make_request('enhance',enhance_rules={'command':'x'})
        request=make_request('enhance',count=1,confirmed_materials=True)
        self.assertTrue(request['ConfirmedMaterials']);self.assertTrue(request['EnhanceRules']['require_double_crit'])

if __name__=='__main__':unittest.main(verbosity=2)
