"""Single allowlist for buttons, queues and natural-language planning."""
from dataclasses import dataclass

@dataclass(frozen=True)
class Job:
    label: str
    mode: str
    task: str
    description: str
    category: str = '日常与刷取'
    spends_materials: bool = False
    continuous: bool = False

CATALOG = {
    'probe': Job('检查今日进度', 'probe', 'MC-Auto-probe', '读取活跃度并返回主界面，不刷副本。'),
    'daily': Job('日常一条龙', 'daily', 'MC-Auto-daily', '先检查活跃度，未满再补日常；不连带执行周常。'),
    'tacet': Job('无音区刷取', 'farm', 'MC-Auto-daily', '按指南序号刷声骸，只用自然体力。'),
    'forgery': Job('凝素领域', 'farm', 'MC-Auto-daily', '刷武器与技能材料，只用自然体力。'),
    'simulation': Job('模拟领域', 'farm', 'MC-Auto-daily', '贝币、共鸣者经验或武器经验。'),
    'weekly': Job('乐园周常', 'weekly', 'MC-Auto-weekly', '读取周度游历，6000已满就跳过。'),
    'echo': Job('Boss 声骸', 'echo', 'MC-Auto-daily', '按次数刷声骸，不领取耗体力奖励。'),
    'nightmare': Job('梦魇／残象聚落', 'nightmare', 'MC-Auto-daily', '按地图解锁情况刷取。'),
    'multiaccount': Job('多账号任务', 'multiaccount', 'MC-Auto-daily', '按账号顺序执行各自任务；失败即停，结果按账号保存。','多账号'),
    'pickup': Job('自动拾取', 'assist', 'MC-Auto-daily', '自己跑图，辅助拾取与吸收；可随时停止。', '游玩辅助', continuous=True),
    'dialog': Job('自动跳过对话', 'assist', 'MC-Auto-daily', '辅助跳过可跳过的对话，不自动规划任务路线。', '游玩辅助', continuous=True),
    'combat': Job('战斗与拾取辅助', 'assist', 'MC-Auto-daily', '手动跑图，遇敌自动战斗并拾取。', '游玩辅助', continuous=True),
    'fasttravel': Job('快捷传送辅助', 'assist', 'MC-Auto-daily', '在地图中识别并点击快速旅行；需手动选择目标。','游玩辅助',continuous=True),
    'quest': Job('剧情组合辅助', 'assist', 'MC-Auto-daily', '手动跑任务路线，组合跳对话、战斗和拾取；不自动寻路或解谜。','游玩辅助',continuous=True),
    'enhance': Job('批量强化声骸', 'enhance', 'MC-Auto-daily', '先在背包筛选候选声骸，再按词条规则培养；消耗材料。', '声骸管理', spends_materials=True),
    'merge': Job('弃置声骸合成', 'merge', 'MC-Auto-daily', '仅合成已标记弃置的声骸，每批100个；不自动挑选并标记弃置。', '声骸管理', spends_materials=True),
    'reconstruct': Job('声骸主属性重构', 'mainstat', 'MC-Auto-daily', '先筛选0级候选，按目标主属性使用游戏内数据重构；消耗重构材料。','声骸管理',spends_materials=True),
    'elimination': Job('无音消除活动', 'event', 'MC-Auto-daily', '从活动页面开始，完成前置并挑战终局；按设定时限停止。','活动'),
}
TOOL_LINKS = {
    'community': ('签到与账号工具', 'https://github.com/leck995/WutheringWavesTool', '库街区签到、抽卡分析、养成计算；使用独立开源工具。'),
    'optimizer': ('配装与伤害计算', 'https://www.wutheringtools.com/', '在浏览器使用声骸配装优化与伤害计算。'),
    'wiki': ('清宵与鸣潮资料', 'https://wiki.biligame.com/wutheringwaves/', '角色、声骸与养成资料查询。'),
}
PLAN_OPTIONS={'multiaccount':set(),'probe':set(),'daily':{'daily_farm','index','material'},'weekly':{'check_only'},'tacet':{'index','stamina_limit'},'forgery':{'index','stamina_limit'},
              'simulation':{'material','stamina_limit'},'echo':{'index','count','scope'},'nightmare':{'kind','target_limit'},
              'pickup':{'duration'},'dialog':{'duration'},'combat':{'duration'},'fasttravel':{'duration'},'quest':{'duration'},
              'enhance':{'count'},'merge':{'count'},'reconstruct':{'count','main_stat','check_only'},'elimination':{'duration','check_only'}}

def planner_catalog():
    return [{'action': key, 'label': j.label, 'description': j.description,
             'count_unit': '批，每批100个已弃置声骸' if key=='merge' else '候选声骸个数，每个可能培养多个阶段' if key=='enhance' else '候选声骸个数' if key=='reconstruct' else '轮' if key=='echo' else None,
             'spends_materials': j.spends_materials, 'continuous': j.continuous,'allowed_options':sorted(PLAN_OPTIONS[key])}
            for key, j in CATALOG.items()]
