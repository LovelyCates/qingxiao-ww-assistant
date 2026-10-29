"""Local saved-account plans. No passwords, network access or game imports."""
from copy import deepcopy
import hashlib
import json
import re
import uuid
try:
    from .model import atomic_json
except ImportError:
    from model import atomic_json

TASKS = {'probe':'检查进度','daily':'日常一条龙','weekly':'乐园周常',
         'tacet':'无音区','forgery':'凝素领域','simulation':'模拟训练',
         'echo':'Boss 声骸','nightmare':'梦魇／聚落'}
STEP_OPTIONS = {'probe':set(),'weekly':set(),
    'daily':{'index','material','daily_farm'},'tacet':{'index','stamina_limit'},
    'forgery':{'index','stamina_limit'},'simulation':{'material','stamina_limit'},
    'echo':{'index','count','scope'},'nightmare':{'kind','target_limit'}}


def account_key(text):
    if not isinstance(text,str):raise ValueError('账号标识必须是文本。')
    key=text.strip().replace('*','').casefold()
    if not re.fullmatch(r'[a-z0-9@._+\-]{3,80}',key):
        raise ValueError('请填写游戏已保存账号列表中的手机号或邮箱显示文本；不要填写密码。')
    return key


def normalize_step(step):
    if not isinstance(step,dict) or set(step)-{'action','options'}:
        raise ValueError('任务步骤格式无效。')
    action=step.get('action');options=step.get('options',{})
    if action not in TASKS or not isinstance(options,dict) or set(options)-STEP_OPTIONS[action]:
        raise ValueError('多账号仅支持目录内的常规任务及对应参数。')
    options=deepcopy(options)
    if action=='daily':
        farm=options.get('daily_farm','tacet')
        if farm not in ('tacet','forgery','simulation'):raise ValueError('日常刷取类型无效。')
        # Validate the selected target against the actual domain, not against
        # the generic daily action's index range.
        target=farm;checked={k:v for k,v in options.items() if k!='daily_farm'}
    else:target=action;checked=options
    try:
        from .model import make_request
    except ImportError:
        from model import make_request
    make_request(target,**checked)
    return {'action':action,'options':options}


def normalize_accounts(accounts, *, require_enabled=False):
    if not isinstance(accounts,list) or len(accounts)>10:raise ValueError('最多配置10个账号。')
    result=[];seen=set();ids=set()
    for value in accounts:
        if not isinstance(value,dict) or set(value)!={'id','label','account_key','enabled','steps'}:
            raise ValueError('账号配置字段不完整或包含未知字段；不保存登录凭据。')
        row=deepcopy(value);row['account_key']=account_key(row['account_key'])
        if row['account_key'] in seen:raise ValueError('账号显示标识重复，无法可靠区分，请检查登录列表。')
        seen.add(row['account_key'])
        try:
            if str(uuid.UUID(row['id']))!=row['id']:raise ValueError()
        except (ValueError,TypeError,AttributeError):raise ValueError('账号配置标识无效。') from None
        if row['id'] in ids:raise ValueError('账号配置ID重复。')
        ids.add(row['id'])
        if (not isinstance(row['label'],str) or not row['label'].strip() or len(row['label'])>40
                or any(ord(c)<32 for c in row['label'])):raise ValueError('账号备注应为1至40个可见字符。')
        row['label']=row['label'].strip()
        if type(row['enabled']) is not bool:raise ValueError('启用状态必须为布尔值。')
        if not isinstance(row['steps'],list) or len(row['steps'])>8:raise ValueError('每个账号最多安排8项任务。')
        row['steps']=[normalize_step(step) for step in row['steps']]
        result.append(row)
    if require_enabled and not any(row['enabled'] for row in result):raise ValueError('请先添加并启用至少一个已保存登录状态的账号。')
    return result


def fingerprint(profile):
    return hashlib.sha256(json.dumps(profile,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def load_accounts(path):
    path=__import__('pathlib').Path(path)
    if not path.exists():return []
    document=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(document,dict) or document.get('version')!=1:raise ValueError('账号配置版本无效。')
    return normalize_accounts(document.get('accounts'))


def save_accounts(path,accounts):
    atomic_json(path,{'version':1,'accounts':normalize_accounts(accounts)})


def retry_accounts(accounts,report):
    """Keep exact task parameters; skip steps already acknowledged as complete."""
    accounts=normalize_accounts(accounts,require_enabled=True)
    results={r['id']:r for r in report.get('account_results',[]) if isinstance(r,dict) and 'id' in r}
    remaining=[]
    for profile in accounts:
        if not profile['enabled']:continue
        old=results.get(profile['id'],{})
        active_path=report.get('active_step_report')
        if active_path and report.get('current_account_id')==profile['id']:
            try:
                from .model import ROOT,read_json
            except ImportError:
                from model import ROOT,read_json
            from pathlib import Path
            path=Path(active_path).resolve()
            path.relative_to(ROOT/'local-runs')
            child=read_json(path,{})
            if child.get('pending_claim'):raise ValueError('中断步骤存在未核实的领奖操作，请先查看截图。')
            # A worker can end after a child receipt but before the parent
            # acknowledges it. Do not repeat a potentially consuming step.
            if child.get('status') not in ('FAILED','CANCELLED','TIMEOUT','NEEDS_REVIEW'):
                raise ValueError('中断步骤回执尚未合并，请先核对账号步骤报告，再安排剩余任务。')
        if old and old.get('fingerprint')!=fingerprint(profile):raise ValueError('原运行账号参数不匹配，不能按旧结果重试。')
        if old.get('status')=='completed':continue
        if old.get('pending_claim'):raise ValueError('上次存在未核实体力领奖，请先查看该账号截图与报告。')
        completed=old.get('completed_steps',0)
        if type(completed) is not int or not 0<=completed<=len(profile['steps']):raise ValueError('原运行步骤进度无效。')
        profile['steps']=profile['steps'][completed:]
        remaining.append(profile)
    if not remaining:raise ValueError('这轮启用账号均已完成，无需重试。')
    return remaining


def execute_accounts(accounts,prepare,login,run_step,publish,check_stop=lambda:None):
    """Single-threaded orchestration; failures never advance to another account."""
    plan=[r for r in normalize_accounts(accounts,require_enabled=True) if r['enabled']]
    rows=[dict(id=p['id'],label=p['label'],fingerprint=fingerprint(p),status='pending',
               completed_steps=0,steps=[]) for p in plan]
    publish(deepcopy(rows),None)
    check_stop();prepare()
    for profile,row in zip(plan,rows):
        try:
            check_stop();row['status']='logging_in';publish(deepcopy(rows),row['label'])
            login(profile['account_key'])
            row['status']='running';publish(deepcopy(rows),row['label'])
            for step in profile['steps']:
                check_stop();receipt=run_step(profile,step,len(row['steps']))
                row['steps'].append(receipt)
                row['pending_claim']=receipt.get('pending_claim')
                if receipt.get('status') not in {'PROBE_PASSED','READBACK_PASSED','SKIPPED_ALREADY_COMPLETE',
                    'ALREADY_WEEKLY_COMPLETE','FARM_PASSED','SKIPPED_INSUFFICIENT_STAMINA',
                    'EXECUTION_FINISHED','NO_ELIGIBLE_ECHOES'} or receipt.get('errors'):
                    check_stop()
                    raise RuntimeError('账号任务未通过核验，已停止整轮；请查看该步骤报告。')
                row['completed_steps']+=1;publish(deepcopy(rows),row['label'])
                check_stop()
            row['status']='completed';publish(deepcopy(rows),row['label'])
        except BaseException as exc:
            row['status']='cancelled' if type(exc).__name__=='TaskDisabledException' else 'failed'
            row['error']=str(exc)[:700];publish(deepcopy(rows),row['label']);raise
    return rows
