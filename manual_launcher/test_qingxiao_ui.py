"""Native UI behavior tests with the scheduler bridge isolated."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
import assistant
import legacy_panel
import qingxiao_panel as ui

class ConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);ui.configure_fonts(cls.app);cls.app.setStyleSheet(ui.STYLE)
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory(dir=ui.RUNS);self.runs=Path(self.folder.name);self.calls=[]
        def bridge(panel,action,callback):
            self.calls.append(action);callback({'Ok':True,'Tasks':[]})
        self.patches=[patch.object(ui,'RUNS',self.runs),patch.object(legacy_panel,'RUNS',self.runs),
                      patch.object(assistant,'CONFIG',self.runs/'assistant-settings.json'),patch.object(ui.Panel,'bridge',bridge)]
        for item in self.patches:item.start()
        self.window=ui.Panel();self.window.timer.stop()
    def tearDown(self):
        self.window.active_id=None;self.window.active_task=None;self.window.close()
        self.app.processEvents()
        for item in reversed(self.patches):item.stop()
        self.folder.cleanup()
    def test_opening_panel_does_not_start_any_game_job(self):
        self.app.processEvents()
        self.assertIsNone(self.window.active_id);self.assertNotIn('start',self.calls)
        self.assertFalse((self.runs/'pending-manual.json').exists());self.assertEqual(self.window.pages.count(),9);self.assertEqual(len(self.window.buttons),18)
    def test_queued_target_is_frozen_when_widgets_change(self):
        self.window.active_id='a-running-job';self.window.controls['tacet_index'].setValue(3)
        self.window.start_job('tacet');self.window.controls['tacet_index'].setValue(7)
        self.assertEqual(self.window.queue[0]['options']['index'],3)
        self.assertNotIn('start',self.calls)
    def test_stop_clears_waiting_jobs_without_starting_them(self):
        self.window.queue.append({'action':'probe','options':{}});self.window.queue_autorun=True
        self.window.stop_job();self.assertFalse(self.window.queue);self.assertFalse(self.window.queue_autorun)
        self.assertNotIn('start',self.calls)
    def test_queue_controls_reflect_available_actions(self):
        self.assertFalse(self.window.resume_button.isEnabled())
        self.assertFalse(self.window.clear_queue_button.isEnabled())
        self.window.queue.append({'action':'probe','options':{}});self.window.persist_queue()
        self.assertTrue(self.window.resume_button.isEnabled())
        self.assertTrue(self.window.clear_queue_button.isEnabled())
        self.window.active_id='running';self.window.set_busy(True)
        self.assertFalse(self.window.resume_button.isEnabled())
        self.window.clear_queue();self.assertFalse(self.window.clear_queue_button.isEnabled())
    def test_task_cards_reflow_without_horizontal_scrolling(self):
        self.window.switch_page(1);self.window.show()
        for width,height,columns in ((1120,760,1),(1440,960,2),(1120,760,1)):
            self.window.resize(width,height);self.app.processEvents();self.app.processEvents()
            scroll=self.window.findChild(legacy_panel.TaskScroll)
            self.assertEqual(scroll.columns,columns)
            self.assertEqual(scroll.horizontalScrollBar().maximum(),0)
            if columns==2:self.assertLessEqual(scroll.widget().height(),scroll.viewport().height()+1)
    def test_record_refresh_keeps_identity_and_clears_removed_preview(self):
        older={'_run':'older','_path':str(self.runs/'older/report.json'),'status':'PROBE_PASSED'}
        newer={'_run':'newer','_path':str(self.runs/'newer/report.json'),'status':'PROBE_PASSED'}
        with patch.object(self.window.history,'refresh',return_value=[older]):self.window.refresh_dashboard(True)
        self.window.table.selectRow(0)
        with patch.object(self.window.history,'refresh',return_value=[newer,older]):self.window.refresh_dashboard(True)
        self.assertEqual(self.window.selected_record()['_run'],'older')
        self.assertEqual(self.window.table.currentRow(),1)
        with patch.object(self.window.history,'refresh',return_value=[newer]):self.window.refresh_dashboard(True)
        self.assertIsNone(self.window.selected_record())
        self.assertFalse(self.window.open_record_button.isEnabled())
        self.assertEqual(self.window.record_note.text(),'选择记录查看截图与报告。')
    def test_log_refresh_preserves_reading_position_and_follows_bottom(self):
        folder=self.runs/'log-run';folder.mkdir();log=folder/'stdout.log'
        log.write_text(''.join(f'line {n}\n' for n in range(300)),encoding='utf-8')
        ui.atomic_json(self.runs/'manual-state.json',{'RequestId':'log-run','State':'running','RunDirectory':str(folder),'Action':'probe'})
        self.window.active_id='log-run';self.window.active_since=time.monotonic()
        self.window.switch_page(1);self.window.show();self.app.processEvents();self.window.poll()
        scroll=self.window.log.verticalScrollBar();self.assertGreater(scroll.maximum(),10)
        scroll.setValue(5)
        with log.open('a',encoding='utf-8') as stream:stream.write('next line\n')
        self.window.poll();self.assertEqual(scroll.value(),5)
        scroll.setValue(scroll.maximum())
        with log.open('a',encoding='utf-8') as stream:stream.write('last line\n')
        self.window.poll();self.assertEqual(scroll.value(),scroll.maximum())
    def test_offline_conversation_worker_returns_and_cleans_up(self):
        self.window.chat_input.setPlainText('你好，你是谁');self.window.send_chat()
        end=time.monotonic()+3
        while self.window.chat_busy and time.monotonic()<end:self.app.processEvents();time.sleep(0.01)
        self.assertFalse(self.window.chat_busy);self.assertFalse(self.window.workers)
        self.assertIn('本地指令模式',self.window.chat_messages[-1]['content']);self.assertNotIn('start',self.calls)
    def test_hostile_model_plan_is_displayed_but_never_started(self):
        self.window.pending_plan={'reply':'执行','steps':[{'action':'powershell','options':{}}]}
        self.window.execute_plan();self.assertNotIn('start',self.calls);self.assertFalse(self.window.queue)
    def test_mode_and_material_rules_make_valid_requests(self):
        self.window.window_mode.setCurrentIndex(1)
        parameters=self.window.job_parameters('enhance')
        self.assertEqual(parameters['background'],'hidden');self.assertEqual(parameters['count'],1)
        self.assertIsNone(self.window.active_id)
    def test_account_run_uses_a_snapshot_and_retry_skips_completed_accounts(self):
        from test_accounts import profile
        from accounts import fingerprint
        first,second=profile(),profile(2)
        self.window.start_job('multiaccount',{'accounts':[first,second]})
        request=ui.read_json(self.runs/'pending-manual.json')
        self.assertEqual(request['Background'],'foreground');self.assertEqual(len(request['Accounts']),2)
        self.window.active_id=None
        folder=self.runs/'batch';folder.mkdir();ui.atomic_json(folder/'manual-request.json',request)
        ui.atomic_json(folder/'report.json',{'account_results':[{'id':first['id'],'fingerprint':fingerprint(first),'status':'completed'}]})
        original=self.window.original_request({'_path':str(folder/'report.json')})
        self.assertEqual([p['id'] for p in original['options']['accounts']],[second['id']])
    def test_completed_readback_is_reported_without_another_model_call(self):
        report=self.runs/'result.json'
        ui.atomic_json(report,{'status':'PROBE_PASSED','activity_points':0,'detection_only':True})
        self.window.announce_result({'Action':'probe','State':'completed','Report':str(report)})
        text=self.window.chat_messages[-1]['content']
        self.assertIn('活跃度 0/100',text);self.assertIn('未消耗体力',text)
        self.assertNotIn('start',self.calls);self.assertFalse(self.window.workers)
    def test_retry_uses_original_target_and_requires_new_material_confirmation(self):
        from PySide6.QtWidgets import QMessageBox
        folder=self.runs/'prior';folder.mkdir();request=ui.make_request('enhance',count=2,confirmed_materials=True)
        ui.atomic_json(folder/'manual-request.json',request)
        record={'_path':str(folder/'report.json')}
        with patch.object(self.window,'selected_record',return_value=record),patch.object(self.window,'confirm_materials',return_value=False):
            self.window.retry_selected()
        self.assertNotIn('start',self.calls);self.assertIsNone(self.window.active_id)
        request=ui.make_request('echo',index=4,count=2);ui.atomic_json(folder/'manual-request.json',request)
        self.window.controls['echo_index'].setValue(9)
        with patch.object(self.window,'selected_record',return_value=record):self.window.retry_selected()
        submitted=ui.read_json(self.runs/'pending-manual.json')
        self.assertEqual(submitted['Index'],4);self.assertEqual(submitted['Count'],2)
    def test_configured_model_roundtrip_from_chat_to_validated_task(self):
        import json
        import threading
        from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                seen.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                content=json.dumps({'reply':'只检查今日进度','steps':[{'action':'probe','options':{}}]},ensure_ascii=False)
                body=json.dumps({'output':[{'type':'message','content':[{'type':'output_text','text':content}]}]}).encode()
                self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            assistant.save_settings({'enabled':True,'base_url':f'http://127.0.0.1:{server.server_port}/v1','model':'local-acceptance','protocol':'responses'},remember=False)
            self.window.session_key='fake-local-test-key';self.window.chat_input.setPlainText('帮我看看今天还做了多少');self.window.send_chat()
            end=time.monotonic()+3
            while self.window.chat_busy and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
            self.assertFalse(self.window.chat_busy);self.assertEqual(self.calls.count('start'),1)
            request=ui.read_json(self.runs/'pending-manual.json')
            self.assertEqual(request['Action'],'probe');self.assertTrue(seen)
            self.assertIn('只检查今日进度',self.window.chat_messages[-1]['content'])
        finally:server.shutdown();server.server_close()

    def test_retry_preserves_an_explicit_natural_stamina_limit(self):
        folder=self.runs/'limited';folder.mkdir()
        ui.atomic_json(folder/'manual-request.json',ui.make_request('forgery',index=1,stamina_limit=40))
        with patch.object(self.window,'selected_record',return_value={'_path':str(folder/'report.json')}):
            self.window.retry_selected()
        self.assertEqual(ui.read_json(self.runs/'pending-manual.json')['StaminaLimit'],40)
    def test_completion_question_displays_recorded_result_without_starting_again(self):
        self.window.last_metrics={'activity':0,'weekly':6000,'recent_tasks':[{'mode':'echo','status':'EXECUTION_FINISHED','echo_count':1}]}
        self.window.chat_input.setPlainText('Boss刷完了吗');self.window.send_chat()
        end=time.monotonic()+3
        while self.window.chat_busy and time.monotonic()<end:self.app.processEvents();time.sleep(.01)
        self.assertNotIn('start',self.calls)
        self.assertIn('Boss声骸：执行结束',self.window.chat_messages[-1]['content'])
        self.assertIn('声骸拾取读数 1',self.window.chat_messages[-1]['content'])

if __name__=='__main__':unittest.main(verbosity=2)
