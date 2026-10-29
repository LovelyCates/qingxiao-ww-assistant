"""Local manual-launcher protocol. No game or UI side effects on import."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import uuid
import math
try:
    from .catalog import CATALOG
except ImportError:
    from catalog import CATALOG

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / 'local-runs'
JOBS = {key:(job.label, job.mode, job.task) for key,job in CATALOG.items()}
MATERIALS = {'贝币': 'Shell Credit', '共鸣者经验': 'Resonator EXP', '武器经验': 'Weapon EXP'}
STATES = {'NO_ELIGIBLE_ECHOES': '没有可处理的声骸', 'PROBE_PASSED': '检测完成', 'READBACK_PASSED': '完成并通过核验',
          'ASSIST_FINISHED': '游玩辅助已结束',
          'SKIPPED_ALREADY_COMPLETE': '今日已完成，已跳过', 'ALREADY_WEEKLY_COMPLETE': '本周已完成，已跳过',
          'FARM_PASSED': '刷取完成', 'FARM_READBACK_PASSED': '体力核验完成',
          'SKIPPED_INSUFFICIENT_STAMINA': '自然体力不足，未刷取', 'EXECUTION_FINISHED': '执行结束',
          'NEEDS_REVIEW': '执行结束，请查看结果', 'FAILED': '运行中断，请查看日志',
          'CANCELLED': '已停止', 'TIMEOUT': '运行超时，已停止', 'NEEDS_ADMIN': '权限入口不可用'}
STAGES = {'bootstrap': '正在初始化', 'initializing_ok_ww': '正在加载工具', 'starting_task': '正在连接游戏',
          'waiting_for_game_main': '等待进入角色主界面', 'reading_daily_activity': '读取日常活跃度',
          'checking_before_daily': '检查是否需要补日常', 'executing_real_daily': '执行日常任务',
          'reading_back_daily': '核对日常结果', 'checking_weekly_progress': '检查本周游历值',
          'executing_real_weekly': '执行乐园周常', 'checking_natural_stamina': '检查自然体力',
          'healing_before_farm': '传送回血', 'healing_at_known_location': '切换回血地点',
          'entering_farm': '进入目标副本／自动战斗', 'claiming_reward': '领取奖励', 'farming': '继续刷取',
          'executing_echo': '自动刷取 Boss 声骸', 'executing_nightmare': '执行梦魇／聚落刷取'}
STAGES.update({'echo_combat':'Boss战斗进行中','echo_pickup':'战斗后寻找声骸'})
STAGES.update({'checking_echo_page':'正在检查当前声骸页，不消耗材料', 'echo_page_checked':'声骸页检查结束，未消耗材料',
               'checking_merge_page':'正在检查数据融合筛选，不消耗材料', 'merge_page_checked':'数据融合筛选检查结束，未消耗材料'})
STAGES['window_recovery_needed']='窗口恢复异常，已停止任务并交由外层恢复'
STAGES.update(account_preflight='核对本轮账号计划',account_tasks='按账号顺序执行任务',accounts_finished='多账号任务结束')
STAGES.update(reconstructing='按目标主属性重构',reconstruct_submitting='提交重构并等待回执',
    reconstruct_checked='候选页面检查完成，未消耗材料',reconstruct_interrupted='重构已停止，请核对回执',reconstruct_finished='主属性重构执行结束',
    executing_event='无音消除活动进行中',event_checked='活动页面检查完成，未开始挑战',event_finished='本轮活动执行结束')
STAGES.update({'enhance_interrupted':'培养已停止，请核对当前声骸', 'merge_interrupted':'合成已停止，请核对背包',
               'assist_deadline_exceeded':'辅助内部调用超时，已释放按键并停止'})
STAGES.update({'probe_finished': '检测结束，已返回角色主界面', 'daily_finished': '日常任务结束',
               'assisting_play':'游玩辅助运行中', 'assist_finished':'辅助时长已到',
               'merging_discarded_echoes':'合成已弃置声骸', 'merge_finished':'弃置合成结束',
               'enhancing_echoes':'按规则培养声骸', 'enhance_finished':'声骸培养结束',
               'daily_already_complete': '今日活跃已满，未重复刷取', 'weekly_finished': '周常检查／执行结束',
               'farm_finished': '刷取结束，已核对剩余体力', 'echo_finished': 'Boss 声骸任务结束',
               'nightmare_finished': '梦魇／聚落任务结束', 'stopped_by_user': '已停止当前脚本'})


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def normalize_enhance_rules(value=None):
    defaults = {'require_double_crit':True, 'valid_stats':['暴击','暴击伤害','攻击百分比'],
                'minimum_valid':3, 'crit_score':13.8, 'first_crit':6.9,
                'require_valid_before_crit':False, 'require_first_valid':False}
    if value is not None and (not isinstance(value, dict) or
            set(value) not in (set(defaults), set(defaults)-{'require_valid_before_crit','require_first_valid'})):
        raise ValueError('强化规则字段不完整或包含未知选项')
    rules = {**defaults, **(value or {})}
    allowed_stats = {'暴击','暴击伤害','攻击百分比','生命百分比','防御百分比','攻击','生命','防御',
                     '共鸣效率','普攻伤害加成','重击伤害加成','共鸣解放伤害加成','共鸣技能伤害加成'}
    if any(type(rules[k]) is not bool for k in ('require_double_crit','require_valid_before_crit','require_first_valid')):
        raise ValueError('强化开关必须为布尔值')
    if type(rules['minimum_valid']) is not int or not 1 <= rules['minimum_valid'] <= 5:
        raise ValueError('有效词条数量应为1至5')
    stats = rules['valid_stats']
    if (not isinstance(stats,list) or not stats or any(not isinstance(s,str) for s in stats)
            or not set(stats) <= allowed_stats or len(set(stats)) != len(stats)):
        raise ValueError('有效词条无效或重复')
    if rules['minimum_valid'] > len(stats):
        raise ValueError('要求的有效词条数量多于已选词条种类')
    if any(type(rules[k]) not in (int,float) or not math.isfinite(rules[k]) or not 0 <= rules[k] <= 50
           for k in ('crit_score','first_crit')):
        raise ValueError('双爆分值应为0至50之间的有限数值')
    rules['valid_stats'] = list(stats)
    return rules


def enhancement_summary(rules):
    rules = normalize_enhance_rules(rules)
    return ('要求双爆：'+('是' if rules['require_double_crit'] else '否')+
            '\n有效词条：'+'、'.join(rules['valid_stats'])+f'；至少{rules["minimum_valid"]}条'+
            f'\n双爆齐全时分值至少{rules["crit_score"]}；首条暴击/爆伤折算至少{rules["first_crit"]}'+
            '\n首条必须有效：'+('是' if rules['require_first_valid'] else '否')+
            '；首条暴击/爆伤出现前必须全有效：'+('是' if rules['require_valid_before_crit'] else '否'))


MAIN_STATS=('攻击','暴击伤害','暴击','生命','防御','共鸣效率','冷凝伤害加成','热熔伤害加成','导电伤害加成','气动伤害加成','衍射伤害加成','湮灭伤害加成')


def normalize_helper_options(value=None):
    defaults=dict(auto_target=True,use_liberation=True,switch_healer=True,
        quest_dialog=True,quest_combat=True,quest_pickup=True,quest_fasttravel=False,
        pickup_whitelist=['吸收'],pickup_blacklist=['领取奖励','离开副本'])
    if value is not None and (not isinstance(value,dict) or set(value)-set(defaults)):
        raise ValueError('辅助设置包含未知选项。')
    settings={**defaults,**(value or {})}
    for key in set(defaults)-{'pickup_whitelist','pickup_blacklist'}:
        if type(settings[key]) is not bool:raise ValueError('辅助开关必须是布尔值。')
    for key in ('pickup_whitelist','pickup_blacklist'):
        items=settings[key]
        if (not isinstance(items,list) or len(items)>20 or any(not isinstance(s,str) or not s.strip()
                or len(s)>40 or any(ord(c)<32 for c in s) for s in items)):
            raise ValueError('拾取名单每项应为1至40个可见字符，最多20项。')
        settings[key]=list(dict.fromkeys(s.strip() for s in items))
    return settings


def make_request(action, *, index=1, material='Shell Credit', count=5, scope='boss', kind='all',
                 duration=30, background='background', confirmed_materials=False, enhance_rules=None, check_only=False,
                 stamina_limit=None, target_limit=None, validation_scene=None, accounts=None,
                 main_stat=None,daily_farm=None,helper_options=None):
    if action not in JOBS:
        raise ValueError('Unknown action')
    if main_stat is not None and (action!='reconstruct' or main_stat not in MAIN_STATS):raise ValueError('目标主属性无效。')
    if action=='reconstruct':main_stat=main_stat or '攻击'
    if daily_farm is not None and (action!='daily' or daily_farm not in ('tacet','forgery','simulation')):
        raise ValueError('日常刷取类型无效。')
    if helper_options is not None and action not in ('pickup','dialog','combat','fasttravel','quest'):
        raise ValueError('辅助设置不能用于此任务。')
    helpers=normalize_helper_options(helper_options)
    if action=='quest' and not any(helpers[k] for k in ('quest_dialog','quest_combat','quest_pickup','quest_fasttravel')):
        raise ValueError('剧情组合辅助请至少启用一项。')
    if action=='multiaccount':
        try:
            from .accounts import normalize_accounts
        except ImportError:
            from accounts import normalize_accounts
        accounts=normalize_accounts(accounts,require_enabled=True)
    elif accounts is not None:
        raise ValueError('账号计划只能用于多账号任务。')
    scenes={'pickup':('pickup_echo',),'combat':('combat_boss','combat_tacet'),'dialog':('dialog_phone',),
            'enhance':('echo_inventory','echo_current_resume'),'multiaccount':('account_inventory',)}
    if validation_scene is not None and validation_scene not in scenes.get(action,()):
        raise ValueError('该验证场景与辅助任务不匹配')
    if validation_scene=='echo_current_resume' and count!=1:
        raise ValueError('当前声骸恢复仅允许一个候选')
    if validation_scene=='echo_current_resume' and check_only:
        raise ValueError('中断培养恢复使用专用核对，不支持普通背包预检')
    if target_limit is not None and (action!='nightmare' or type(target_limit) is not int or not 1<=target_limit<=100):
        raise ValueError('聚落目标上限须为1至100之间的整数')
    if stamina_limit is not None:
        cost=60 if action=='tacet' else 40
        if action not in ('tacet','forgery','simulation') or type(stamina_limit) is not int or not cost <= stamina_limit <= 240 or stamina_limit%cost:
            raise ValueError('体力上限须为所选副本单次消耗的整数倍，且不超过240')
    if type(check_only) is not bool or (check_only and action not in ('weekly','enhance','merge','reconstruct','elimination')):
        raise ValueError('此任务不支持只检查；可用于周常、强化、融合、重构和无音消除。')
    maximum = {'tacet': 21, 'forgery': 20}.get(action, {'boss': 20, 'weekly': 9, 'nightmare': 10}.get(scope, 0))
    if action=='daily' and daily_farm:maximum={'tacet':21,'forgery':20,'simulation':1}[daily_farm]
    if type(index) is not int or not 1 <= index <= max(maximum, 1):
        raise ValueError('Target index out of range')
    if material not in MATERIALS.values() or scope not in ('boss', 'weekly', 'nightmare'):
        raise ValueError('Invalid selection')
    if type(count) is not int or not 1 <= count <= 100 or kind not in ('all', 'purification', 'nest'):
        raise ValueError('Invalid farming limit')
    if type(duration) is not int or not 1 <= duration <= 180 or background not in ('foreground','background','hidden'):
        raise ValueError('Invalid runtime options')
    rules = normalize_enhance_rules(enhance_rules)
    if type(confirmed_materials) is not bool:
        raise ValueError('Material confirmation must be a boolean')
    if action in ('pickup','dialog','combat','fasttravel','quest','elimination','reconstruct'):
        background = 'foreground'
    if action=='multiaccount':background='foreground'
    request = dict(Version=1, RequestId=str(uuid.uuid4()), Action=action,
                CreatedAt=datetime.now(timezone.utc).isoformat(), Index=index,
                Material=material, Count=count, Scope=scope, Kind=kind,
                Duration=duration, Background=background, ConfirmedMaterials=bool(confirmed_materials), EnhanceRules=rules, CheckOnly=check_only)
    if stamina_limit is not None:request['StaminaLimit']=stamina_limit
    if target_limit is not None:request['TargetLimit']=target_limit
    if validation_scene is not None:request['ValidationScene']=validation_scene
    if accounts is not None:request['Accounts']=accounts
    if main_stat is not None:request['MainStat']=main_stat
    if daily_farm is not None:request['DailyFarm']=daily_farm
    if action in ('pickup','dialog','combat','fasttravel','quest'):request['HelperOptions']=helpers
    return request
