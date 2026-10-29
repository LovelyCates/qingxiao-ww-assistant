import json
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock,patch
from accounts import (account_key,normalize_accounts,normalize_step,execute_accounts,
                      fingerprint,retry_accounts,load_accounts,save_accounts)
from model import ROOT,make_request


def profile(n=1,**updates):
    row=dict(id=f'{n:08d}-1111-4111-8111-111111111111',label=f'账号{n}',
             account_key=f'190****{n:04d}',enabled=True,
             steps=[{'action':'probe','options':{}},{'action':'weekly','options':{}}])
    row.update(updates);return normalize_accounts([row])[0]


class AccountPlans(unittest.TestCase):
    def test_snapshot_is_frozen_and_account_switching_is_foreground(self):
        rows=[profile()];request=make_request('multiaccount',accounts=rows,background='hidden')
        rows[0]['steps'].clear()
        self.assertEqual(len(request['Accounts'][0]['steps']),2)
        self.assertEqual(request['Background'],'foreground')
        with self.assertRaises(ValueError):make_request('probe',accounts=rows)

    def test_masked_identifiers_are_exact_and_case_insensitive(self):
        self.assertEqual(account_key('190****0001'),'1900001')
        self.assertEqual(account_key('A***@EXAMPLE.COM'),'a@example.com')
        with self.assertRaises(ValueError):normalize_accounts([profile(),profile(2,account_key='1900001')])

    def test_no_credentials_commands_recursive_or_material_tasks(self):
        rows=[profile()];rows[0]['password']='not-a-real-password'
        with self.assertRaises(ValueError):normalize_accounts(rows)
        for action in ('multiaccount','enhance','merge','powershell','combat'):
            with self.subTest(action=action),self.assertRaises(ValueError):normalize_step({'action':action})
        for opts in ({'index':99},{'command':'x'},{'stamina_limit':True}):
            with self.assertRaises(ValueError):normalize_step({'action':'tacet','options':opts})

    def test_daily_validates_the_chosen_domain_target(self):
        self.assertEqual(normalize_step({'action':'daily','options':{'daily_farm':'tacet','index':21}})['options']['index'],21)
        with self.assertRaises(ValueError):normalize_step({'action':'daily','options':{'daily_farm':'forgery','index':21}})

    def test_disabled_accounts_and_path_identifiers_cannot_bypass_validation(self):
        with self.assertRaises(ValueError):normalize_accounts([profile(enabled=False)],require_enabled=True)
        for field,value in (('id','{11111111-1111-4111-8111-111111111111}'),('enabled','false'),('label','\n')):
            with self.assertRaises(ValueError):normalize_accounts([{**profile(),field:value}])

    def test_invalid_save_preserves_the_previous_file(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'accounts.json';save_accounts(p,[profile()]);before=p.read_bytes()
            with self.assertRaises(ValueError):save_accounts(p,[{**profile(),'account_key':''}])
            self.assertEqual(before,p.read_bytes());self.assertEqual(load_accounts(p),[profile()])

    def test_sequential_results_skip_disabled_accounts_and_keep_parameters(self):
        log=[];public=[]
        def step(p,s,i):log.append((p['id'],s['action'],i));return {'status':'PROBE_PASSED','errors':[]}
        rows=execute_accounts([profile(),profile(2,enabled=False),profile(3)],lambda:log.append('prepare'),
            lambda key:log.append(key),step,lambda rows,label:public.append(rows))
        self.assertEqual([r['completed_steps'] for r in rows],[2,2]);self.assertEqual(len(log),7)
        self.assertTrue(all(r['status']=='pending' for r in public[0]))

    def test_failure_or_unknown_outcome_stops_before_the_next_account(self):
        for receipt in ({'status':'FAILED','errors':['x']},{'status':'STARTING'},
                        {'status':'PROBE_PASSED','errors':['unknown']},
                        {'status':'FAILED','pending_claim':{'cost':60}}):
            login=Mock();updates=[]
            with self.assertRaises(RuntimeError):execute_accounts([profile(),profile(2)],lambda:None,login,
                lambda *args:receipt,lambda rows,label:updates.append(rows))
            self.assertEqual(login.call_count,1);self.assertEqual(updates[-1][0]['status'],'failed')
            self.assertEqual(updates[-1][1]['status'],'pending')

    def test_stop_at_account_boundary_never_logs_in_to_the_next_account(self):
        class TaskDisabledException(Exception):pass
        check=Mock(side_effect=[None,None,TaskDisabledException('stopped')]);login=Mock();updates=[]
        with self.assertRaises(TaskDisabledException):execute_accounts([profile(),profile(2)],lambda:None,login,
            Mock(),lambda rows,label:updates.append(rows),check)
        self.assertEqual(login.call_count,1);self.assertEqual(updates[-1][0]['status'],'cancelled')

    def test_retry_skips_completed_accounts_and_steps_with_original_options(self):
        a,b=profile(),profile(2)
        report={'account_results':[{'id':a['id'],'fingerprint':fingerprint(a),'status':'completed'},
            {'id':b['id'],'fingerprint':fingerprint(b),'status':'failed','completed_steps':1}]}
        rows=retry_accounts([a,b],report)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['steps'],b['steps'][1:])
        report['account_results'][1]['pending_claim']={'cost':60}
        with self.assertRaises(ValueError):retry_accounts([a,b],report)

    def test_stop_after_receipt_keeps_the_completed_step_acknowledged(self):
        class TaskDisabledException(Exception):pass
        stopped=False;updates=[]
        def check():
            if stopped:raise TaskDisabledException('stopped')
        def step(*unused):
            nonlocal stopped
            stopped=True;return {'status':'FARM_PASSED','errors':[]}
        with self.assertRaises(TaskDisabledException):execute_accounts([profile()],lambda:None,lambda key:None,
            step,lambda rows,label:updates.append(rows),check)
        self.assertEqual(updates[-1][0]['completed_steps'],1)
        rows=retry_accounts([profile()],{'account_results':updates[-1]})
        self.assertEqual(rows[0]['steps'],profile()['steps'][1:])


class AccountSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import sys
        sys.path.insert(0,str(ROOT/'ok-wuthering-waves-3.7.8'))
        import src.task.MultiAccountConfigTask as module
        cls.module=module

    def task(self):
        task=object.__new__(self.module.MultiAccountConfigTask)
        for name in ('sleep','log_warning','log_info','click','click_relative','ensure_main'):
            setattr(task,name,Mock())
        task._login_combo=Mock(return_value=123)
        return task

    def test_native_combo_checks_selected_identity_before_logging_in(self):
        task=self.task()
        with patch.object(self.module,'combo_items',return_value=['190****0001','190****0002']),\
             patch.object(self.module,'select_combo_item',return_value=True) as select,\
             patch.object(self.module,'combo_selected_item',return_value='190****0002'):
            task._select_target_account('1900002')
        select.assert_called_once_with(123,1);task.click.assert_not_called()

    def test_missing_or_mismatched_target_never_submits_login(self):
        task=self.task();task.find_account_drop_down=Mock(side_effect=RuntimeError('not found'))
        with patch.object(self.module,'combo_items',return_value=['190****0001']),self.assertRaises(RuntimeError):
            task._select_target_account('1900002')
        task.click.assert_not_called();task.ensure_main.assert_not_called()

    def test_config_isolation_restores_nested_task_config_even_on_failure(self):
        from src.task.account.RuntimeTaskConfig import isolated_task_configs
        original={'Items':['original']};task=SimpleNamespace(config=original,default_config={})
        with self.assertRaises(RuntimeError):
            with isolated_task_configs([task]):task.config['Items'].append('changed');raise RuntimeError()
        self.assertIs(task.config,original);self.assertEqual(original,{'Items':['original']})

    def test_login_rechecks_identity_immediately_before_submission(self):
        task=self.task();task._executor=SimpleNamespace(get_task_by_class=lambda cls:None)
        task._detect_current_account_from_login=Mock(return_value='190****0002')
        with patch.object(self.module.MultiAccountConfigTask,'_select_target_account'),self.assertRaises(self.module.WaitFailedException):
            task._login_target_account('1900001')
        task.click.assert_not_called();task.ensure_main.assert_not_called()


class AccountWidgets(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_edit_reorders_tasks_and_saves_normalized_account(self):
        from account_ui import AccountDialog
        dialog=AccountDialog(None,profile());dialog.steps.setCurrentRow(1);dialog.move_step(-1)
        dialog.label.setText('主号');dialog.key.setText('190****0001');dialog.save()
        self.assertEqual(dialog.value['account_key'],'1900001');self.assertEqual(dialog.value['steps'][0]['action'],'weekly')
        dialog.close()

    def test_account_page_persists_order_without_starting_on_open(self):
        from account_ui import AccountsPage
        with tempfile.TemporaryDirectory() as folder:
            callback=Mock();p=Path(folder)/'accounts.json';save_accounts(p,[profile(),profile(2)])
            page=AccountsPage(p,callback);callback.assert_not_called();page.table.selectRow(1);page.move(-1)
            self.assertEqual(load_accounts(p)[0]['id'],profile(2)['id'])
            page.start_button.click();self.assertEqual(callback.call_args.args[0],'multiaccount')
            self.assertEqual(callback.call_args.args[1]['accounts'][0]['id'],profile(2)['id']);page.close()


class InventoryReadback(unittest.TestCase):
    def read(self,task,labels):
        import sys
        sys.path.insert(0,str(ROOT/'ok-wuthering-waves-3.7.8'))
        from manual_launcher.account_inventory import read_saved_accounts
        with patch('src.task.MultiAccountDailyTask.combo_items',return_value=labels):return read_saved_accounts(task)

    def task(self):
        return SimpleNamespace(_login_combo=Mock(return_value=123),screenshot=Mock(),click=Mock(),next_frame=Mock(),
            ocr=Mock(),do_find_account_drop_down=Mock())

    def test_native_list_deduplicates_without_clicking_or_logging_in(self):
        task=self.task();self.assertEqual(self.read(task,['190****0001','190****0001','131****0002']),['190****0001','131****0002'])
        task.click.assert_not_called()

    def test_collapsed_ocr_list_is_opened_once_and_never_submits_login(self):
        task=self.task();task._login_combo.return_value=None
        task.ocr.side_effect=[[SimpleNamespace(name='190****0001')],[SimpleNamespace(name='190****0001'),SimpleNamespace(name='131****0002')]]
        closed=object();task.do_find_account_drop_down.return_value=closed
        self.assertEqual(len(self.read(task,[])),2);task.click.assert_called_once_with(closed,after_sleep=2)

    def test_unrecognized_page_does_not_guess_coordinates(self):
        task=self.task();task._login_combo.return_value=None;task.ocr.return_value=[];task.do_find_account_drop_down.return_value=None
        with self.assertRaises(RuntimeError):self.read(task,[])
        task.click.assert_not_called()


class WorkerAdapter(unittest.TestCase):
    def adapter(self,folder,fail=False):
        # Execute the actual nested adapter, with capture/input and task bodies
        # replaced. This checks the worker boundary, beyond plan orchestration.
        import ast,textwrap,threading
        tree=ast.parse((ROOT/'local_runner.py').read_text(encoding='utf-8'))
        node=next(n for n in ast.walk(tree) if isinstance(n,ast.ClassDef) and n.name=='ObservedMultiAccount')
        outer={'mode':'multiaccount','administrator':True,'source_version':'v3.7.8','errors':[]}
        config={'Which to Farm':'Old','Items':['original']}
        sub=SimpleNamespace(config=config,default_config={},reset_combat_state=Mock(),map_zoomed=True)
        env=dict(result=outer,parent_report=None,child_report_path=None,manual_options={'Accounts':[profile()]},
            args=SimpleNamespace(mode='multiaccount',farm_target='tacet'),report_path=Path(folder)/'report.json',
            runtime=SimpleNamespace(screenshot=SimpleNamespace(screenshot_folder='original-shots')),
            save_lock=threading.RLock(),outputs=[],seen=[])
        class Child:
            default_config={}
            def __init__(self,**kw):self.config={}
            def after_init(self,**kw):pass
            def post_init(self):pass
            def run(self):
                env['seen'].append(deepcopy(self.config));sub.config['Items'].append('runtime')
                if fail:raise RuntimeError('capture failure')
                env['save'](status='PROBE_PASSED',activity_points=10)
        scope=dict(MultiAccountConfigTask=object,WWOneTimeTask=Mock(),
            StartupProbe=Child,ObservedDaily=Child,ObservedWeekly=Child,ObservedTacet=Child,
            ObservedForgery=Child,ObservedSimulation=Child,ObservedEcho=Child,ObservedNightmare=Child,
            datetime=__import__('datetime').datetime,re=__import__('re'))
        from src.task.account.RuntimeTaskConfig import isolated_task_configs,effective_config
        scope.update(isolated_task_configs=isolated_task_configs,effective_config=effective_config)
        source='def build(env):\n'
        for key in ('result','parent_report','child_report_path','manual_options','args','report_path','runtime','save_lock'):
            source+=f'    {key}=env[{key!r}]\n'
        source+='    def save(**kw):\n        result.update(kw)\n        env["outputs"].append((child_report_path,dict(result)))\n    env["save"]=save\n'
        source+=textwrap.indent(ast.unparse(node),'    ')+'\n    return ObservedMultiAccount, lambda:(result,parent_report,child_report_path,manual_options,args)\n'
        exec(compile(source,'<production-account-adapter>','exec'),scope)
        cls,state=scope['build'](env)
        owner=SimpleNamespace(executor=SimpleNamespace(get_all_tasks=lambda:[sub],scene=object()),_app=object(),active_child=None)
        return cls,owner,env,state,sub,config

    def test_each_daily_uses_its_own_target_and_restores_worker_state(self):
        with tempfile.TemporaryDirectory() as folder:
            cls,owner,env,state,sub,original=self.adapter(folder)
            receipt=cls.run_child(owner,profile(),{'action':'daily','options':{'daily_farm':'forgery','index':7}},0)
            self.assertEqual(receipt['status'],'PROBE_PASSED')
            self.assertEqual(env['seen'][0]['Which Forgery Challenge to Farm'],7)
            self.assertEqual(env['seen'][0]['Which to Farm'],'Forgery Challenge')
            self.assertEqual(state()[0]['mode'],'multiaccount');self.assertIsNone(state()[1]);self.assertIsNone(owner.active_child)
            self.assertEqual(env['runtime'].screenshot.screenshot_folder,'original-shots')
            self.assertIs(sub.config,original);self.assertEqual(original['Items'],['original'])
            self.assertEqual(state()[-1].farm_target,'tacet');sub.reset_combat_state.assert_called_once()

    def test_child_failure_still_restores_context_and_provides_failed_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            cls,owner,env,state,sub,original=self.adapter(folder,fail=True)
            receipt=cls.run_child(owner,profile(),{'action':'probe','options':{}},0)
            self.assertEqual(receipt['status'],'FAILED');self.assertIn('capture failure',receipt['errors'][0])
            self.assertEqual(state()[0]['mode'],'multiaccount');self.assertIs(sub.config,original)
            self.assertEqual(env['runtime'].screenshot.screenshot_folder,'original-shots')


if __name__=='__main__':unittest.main()
