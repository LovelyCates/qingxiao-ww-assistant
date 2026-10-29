"""Local intent planner plus optional, explicitly configured LLM connection.

The model can propose catalog actions only. It never receives a shell tool,
account credentials, screenshots or unrestricted filesystem access.
"""
from __future__ import annotations
import base64
import ctypes
from ctypes import wintypes
import json
import re
from urllib import request, error, parse

from catalog import CATALOG, TOOL_LINKS, PLAN_OPTIONS, planner_catalog
from model import RUNS, atomic_json, make_request, read_json

CONFIG = RUNS / 'assistant-settings.json'
MAX_STEPS = 8

def protect_secret(value: str, decrypt=False) -> str:
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    raw = base64.b64decode(value, validate=True) if decrypt else value.encode('utf-8')
    storage = ctypes.create_string_buffer(raw)
    source = Blob(len(raw), ctypes.cast(storage, ctypes.POINTER(ctypes.c_ubyte)))
    output = Blob()
    crypt = ctypes.windll.crypt32
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    if decrypt:
        ok = function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output))
    else:
        ok = function(ctypes.byref(source), 'MC local assistant', None, None, None, 1, ctypes.byref(output))
    if not ok:
        raise RuntimeError('无法使用 Windows 加密保存密钥，请改用本次会话临时密钥。')
    try:
        result = ctypes.string_at(output.data, output.size)
        return result.decode('utf-8') if decrypt else base64.b64encode(result).decode('ascii')
    finally:
        ctypes.windll.kernel32.LocalFree(output.data)

def load_settings():
    data = read_json(CONFIG, {})
    return dict(enabled=bool(data.get('enabled', False)), base_url=data.get('base_url', 'https://api.openai.com/v1'),
                model=data.get('model', ''), protocol=data.get('protocol', 'responses'),
                auto_execute=bool(data.get('auto_execute', True)), key_saved=bool(data.get('protected_key')))

def save_settings(settings, key=None, remember=True):
    base = validate_endpoint(settings.get('base_url', ''))
    model = str(settings.get('model', '')).strip()
    if len(model) > 200 or '\n' in model:
        raise ValueError('模型名称无效。')
    protocol = settings.get('protocol', 'responses')
    if protocol not in ('responses', 'chat'):
        raise ValueError('请选择支持的接口协议。')
    data = dict(enabled=bool(settings.get('enabled')), base_url=base, model=model, protocol=protocol,
                auto_execute=bool(settings.get('auto_execute', True)))
    old = read_json(CONFIG, {})
    if remember and key:
        data['protected_key'] = protect_secret(key)
    elif remember and key is None and old.get('protected_key'):
        data['protected_key'] = old['protected_key']
    atomic_json(CONFIG, data)

def get_key(session_key=None):
    if session_key:
        return session_key
    encrypted = read_json(CONFIG, {}).get('protected_key')
    return protect_secret(encrypted, decrypt=True) if encrypted else ''

def validate_endpoint(value):
    value = str(value).strip().rstrip('/')
    parts = parse.urlsplit(value)
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ValueError('API 地址不能包含账号、密钥、查询参数或片段。')
    if parts.scheme not in ('https', 'http') or not parts.hostname:
        raise ValueError('请填写有效的 API Base URL。')
    if parts.scheme == 'http' and parts.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('远程 API 请使用 HTTPS；本地模型可使用 localhost HTTP。')
    return value

def validate_plan(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get('reply'), str):
        raise ValueError('助手返回的计划格式无效。')
    steps = plan.get('steps', [])
    if not isinstance(steps, list) or len(steps) > MAX_STEPS:
        raise ValueError('一次最多安排 8 个任务。')
    result = []
    for number, step in enumerate(steps):
        if not isinstance(step, dict) or set(step) - {'action', 'options'}:
            raise ValueError('计划包含无法识别的字段。')
        action = step.get('action')
        options = step.get('options', {})
        if not isinstance(options, dict) or set(options) - {'index', 'material', 'count', 'scope', 'kind', 'duration', 'check_only','daily_farm','main_stat','stamina_limit','target_limit'}:
            raise ValueError('任务参数无效。')
        if action in ('stop', 'status') or action in TOOL_LINKS:
            if options:
                raise ValueError('该操作不接受额外参数。')
        elif action in CATALOG:
            if set(options)-PLAN_OPTIONS[action]:
                raise ValueError('该任务不支持所指定的限制参数，本次没有执行。请核对目标与当前支持的选项。')
            if action=='reconstruct' and 'main_stat' not in options:
                raise ValueError('主属性重构必须明确指定目标主属性，本次没有执行。')
            duration = options.get('duration', 30)
            if type(duration) is not int or not 1 <= duration <= 180:
                raise ValueError('辅助时长应为 1–180 分钟。')
            clean = {k:v for k,v in options.items() if k != 'duration'}
            if action=='multiaccount':
                from accounts import load_accounts
                clean['accounts']=load_accounts(RUNS/'accounts.json')
            make_request(action, **clean)
            if CATALOG[action].continuous and number != len(steps) - 1:
                raise ValueError('持续辅助必须放在队列最后。')
        else:
            raise ValueError('助手提出了未接入的任务，未执行。')
        result.append({'action': action, 'options': options})
    return {'reply': plan['reply'][:3000], 'steps': result}

def offline_plan(text):
    """Conservative fallback; unknown or ambiguous requests remain conversational."""
    text = text.strip()
    if re.search('多账号|全部账号|所有账号',text) and re.search('执行|日常|开始|运行',text):
        try:
            from accounts import load_accounts
            make_request('multiaccount',accounts=load_accounts(RUNS/'accounts.json'))
        except (ValueError,OSError):
            return {'reply':'请先在“多账号”页添加已保存登录状态的账号，并核对各账号任务。','steps':[]}
        return {'reply':'按“多账号”页已保存的顺序执行启用账号；各账号使用自己的任务参数，失败即停。','steps':[{'action':'multiaccount','options':{}}]}
    if re.search(r'怎么|如何|为什么|是什么',text):
        return {'reply':'这是一条用法问题，没有开始游戏任务。可在“自动任务”选择目标，在“游玩与声骸”设置辅助；配置模型后可以直接询问具体用法。','steps':[]}
    if re.search(r'不要停止|别停止|不用停止|不要停下',text):
        return {'reply':'没有停止当前任务。','steps':[]}
    if re.search(r'停止|停下|别刷|取消任务|^(?:不要|别|取消).*(?:拾取|吸收|战斗|跳过|刷|强化|合成)', text):
        return {'reply': '停止当前任务并清空等待队列，保留游戏。', 'steps':[{'action':'stop'}]}
    if re.search(r'签到|抽卡分析|抽卡记录|养成计算|兑换码', text):
        return {'reply':'打开签到与账号工具入口。首次使用需要在工具内自行登录库街区。', 'steps':[{'action':'community'}]}
    if re.search(r'配装|伤害计算|计算伤害|声骸评分', text):
        return {'reply':'打开声骸配装与伤害计算工具。', 'steps':[{'action':'optimizer'}]}
    if re.search(r'刷完|打完|跑完|完成|结束',text) and re.search(r'吗|没|？|\?',text) and re.search(r'[Bb][Oo][Ss][Ss]|首领|拾取|合成|强化|梦魇',text):
        return {'reply':'查看最近任务记录，本次不会重新开始刷取。','steps':[{'action':'status'}]}
    if re.search(r'状态|进度|完成了|做完了|检查', text):
        action = 'weekly' if re.search(r'本周|这周|周常|乐园', text) else 'probe'
        return {'reply':'只读取本周游历值，不进入乐园补做。' if action == 'weekly' else '读取今日活跃度，不消耗体力。', 'steps':[{'action':action,'options':{'check_only':True} if action=='weekly' else {}}]}
    matches = [('reconstruct',r'主属性.*重构|重构.*声骸|修改.*主属性'),('elimination',r'无音消除'),
               ('fasttravel',r'快捷传送|快速旅行辅助'),('quest',r'剧情组合|剧情辅助'),
               ('dialog',r'跳过.*对话|跳剧情|过对话'), ('pickup',r'自动拾取|自动吸收|帮.*捡'),
               ('combat',r'战斗辅助|自动战斗'), ('enhance',r'强化.*声骸|声骸.*强化'),
               ('merge',r'合成.*声骸|声骸.*合成|清理弃置'), ('nightmare',r'梦魇|残象聚落'),
               ('weekly',r'乐园|周常'), ('daily',r'日常|一条龙'), ('echo',r'[Bb][Oo][Ss][Ss]|首领|[4四][Cc费]'), ('tacet',r'无音区'),
               ('forgery',r'凝素'), ('simulation',r'模拟|贝币|经验')]
    found = [action for action, pattern in matches if re.search(pattern, text)]
    if not found:
        return {'reply':'目前为本地指令模式。可以说“检查今天进度”“刷模拟贝币”“打开自动拾取”。配置模型后可进行更自由的对话与多步任务规划。', 'steps':[]}
    if len(found) > 1:
        return {'reply':'这句话包含多个任务。请分别指定目标，或在设置中连接 LLM 来安排多步队列。', 'steps':[]}
    action = found[0]
    options = {}
    if action=='reconstruct':
        from model import MAIN_STATS
        chosen=next((s for s in sorted(MAIN_STATS,key=len,reverse=True) if s in text),None)
        if not chosen:return {'reply':'请明确重构的目标主属性，例如“重构1个声骸为暴击伤害”。本次没有开始。','steps':[]}
        options['main_stat']=chosen
    if action=='echo':options['scope']='boss'
    if CATALOG[action].continuous or action=='elimination':
        duration=re.search(r'(\d+)\s*(?:分钟|min\b)',text,re.I)
        if duration:options['duration']=int(duration.group(1))
    index = re.search(r'(?:第\s*|序号\s*)(\d+)\s*(?:项|个)?', text)
    if index:
        if 'index' not in PLAN_OPTIONS[action]:
            return {'reply':'这项目前不能按列表序号指定目标，本次没有执行。请使用任务页面提供的选项。','steps':[]}
        options['index'] = int(index.group(1))
    count_text=text[:index.start()]+text[index.end():] if index else text
    if action in ('merge','enhance','reconstruct') and re.search(r'[零一二两三四五六七八九十百千万]+\s*(?:次|轮|个|批)',count_text):
        return {'reply':'请用阿拉伯数字明确数量：强化和重构按“个候选”，合成按“批，每批100个”。本次没有执行。','steps':[]}
    if action in ('merge','enhance','reconstruct') and re.search(r'\d+\s*[.．到至~～—-]\s*\d+\s*(?:次|轮|个|批)',count_text):
        return {'reply':'请指定一个整数上限，不能使用小数或范围。本次没有执行。','steps':[]}
    count=re.search(r'(\d+)\s*(次|轮|个|批)',count_text)
    if action == 'merge' and count and count.group(2) != '批':
        return {'reply':'弃置合成按批执行，每批100个。请明确写“合成1批声骸”；不能把个数或次数当作批数。本次没有执行。','steps':[]}
    if action == 'enhance' and count and count.group(2) != '个':
        return {'reply':'批量强化按候选声骸个数执行，每个候选可能强化多个阶段。请写“强化1个声骸”，本次没有执行。','steps':[]}
    if action == 'reconstruct' and count and count.group(2) != '个':
        return {'reply':'主属性重构按候选声骸个数执行。请写“重构1个声骸为暴击伤害”，本次没有执行。','steps':[]}
    if action in ('echo','merge','enhance','reconstruct'):
        if count:options['count']=int(count.group(1))
    elif action in ('tacet','forgery','simulation') and count:
        return {'reply':'当前刷体力会持续到自然体力不足，暂不支持按次数限定。本次没有开始，避免超出你指定的次数。','steps':[]}
    if action == 'simulation':
        options['material'] = 'Weapon EXP' if '武器' in text else 'Resonator EXP' if re.search(r'角色|共鸣者|经验',text) else 'Shell Credit'
    if action == 'forgery' and not index:
        return {'reply':'凝素要刷哪一个目标？请写“凝素第1项”这样的指南序号，避免刷错材料。', 'steps':[]}
    plan = {'reply': f'准备：{CATALOG[action].label}。' + ('这项会消耗材料，请先核对筛选与规则，再手动开始。' if CATALOG[action].spends_materials else ''),
            'steps':[{'action':action, 'options':options}]}
    return validate_plan(plan)

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('API 地址发生重定向，请直接配置最终 HTTPS 地址。')

def llm_plan(text, history=(), snapshot=None, session_key=None):
    settings = load_settings()
    if not settings['enabled']:
        return dict(offline_plan(text), source='local')
    key = get_key(session_key)
    if not key or not settings['model']:
        return dict(reply='尚未配置密钥或模型，请在“设置 → 对话模型”中填写。没有发送网络请求。', steps=[], source='unconfigured')
    catalog = planner_catalog() + [{'action':k,'label':v[0],'description':v[2]} for k,v in TOOL_LINKS.items()]
    system = ('你是鸣潮个人桌面助手。用简洁中文对话，基于目录安排任务。只输出JSON对象：'
              '{"reply":"给用户的回复", "steps":[{"action":"目录ID", "options":{}}]}。'
              '普通聊天、知识问答、目标不清楚时steps为空；不能伪称任务已完成。'
              '不支持的任务请说明。禁止输出代码、命令、路径或额外字段。一次最多8步。'
              '持续辅助只能放最后。停止用stop，查本地状态用status。'
              '参数仅允许index(指南序号整数)、material(Shell Credit/Resonator EXP/Weapon EXP)、count(1-100)、'
              'scope(boss/weekly/nightmare)、kind(all/purification/nest)、duration(辅助或活动分钟1-180)、'
              'check_only(布尔，按目录限定)、daily_farm(tacet/forgery/simulation)、main_stat(游戏主属性名称)、'
              'stamina_limit(整数，所选副本单次体力整数倍，最高240)、target_limit(聚落目标1-100)。'
              '用户只要求查看、检查本周进度时，weekly必须设置check_only=true；明确要求补做周常时才执行。'
              '每项任务只能使用目录allowed_options中的参数。无音、凝素、模拟目前持续刷自然体力，不支持限定次数；用户指定次数时先说明，不得擅自改为全部体力。'
              'merge.count严格表示批数，每批100个；enhance和reconstruct的count表示候选声骸个数。用户指定个数来合成或指定次数来强化、重构时，先澄清，steps必须为空。'
              'reconstruct必须明确main_stat；不要猜测。quest只是手动跑图时的对话、战斗和拾取组合，不自动接取任务、寻路或解谜。'
              '摘要按国服4点日刷新及周一4点周刷新；activity或weekly为null表示本日或本周尚未核实，不能当作0或已完成。'
              '不明确的材料副本必须问清楚。自然体力永不补充。材料消耗任务仍由用户核对后开始。'
              '\n目录：' + json.dumps(catalog, ensure_ascii=False) + '\n本地已核实摘要：' + json.dumps(snapshot or {}, ensure_ascii=False))
    messages = [{'role':'system','content':system}]
    for message in list(history)[-8:]:
        if message.get('role') in ('user','assistant'):
            messages.append({'role':message['role'], 'content':str(message.get('content',''))[:3000]})
    messages.append({'role':'user','content':text[:6000]})
    base = validate_endpoint(settings['base_url'])
    if settings['protocol'] == 'responses':
        payload = {'model':settings['model'], 'input':messages, 'max_output_tokens':1800, 'store':False,
                   'text':{'format':{'type':'json_object'}}}
        endpoint = base + '/responses'
    else:
        payload = {'model':settings['model'], 'messages':messages, 'max_tokens':1800,
                   'response_format':{'type':'json_object'}}
        endpoint = base + '/chat/completions'
    req = request.Request(endpoint, data=json.dumps(payload).encode(), method='POST',
                          headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with request.build_opener(NoRedirect()).open(req, timeout=45) as response:
            raw = response.read(256000)
        data = json.loads(raw)
        if settings['protocol'] == 'responses':
            content = ''.join(c.get('text','') for item in data.get('output',[]) if item.get('type')=='message'
                              for c in item.get('content',[]) if c.get('type')=='output_text')
        else:
            content = data['choices'][0]['message']['content']
        plan = validate_plan(json.loads(content))
        return dict(plan, source='llm', usage=data.get('usage', {}))
    except error.HTTPError as exc:
        raise RuntimeError(f'模型接口返回 HTTP {exc.code}，请检查地址、模型、权限与余额。') from None
    except (error.URLError, TimeoutError):
        raise RuntimeError('模型连接超时或网络不可用，本次没有执行游戏任务。') from None
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise RuntimeError('模型响应不符合任务协议，本次没有执行游戏任务。') from None
