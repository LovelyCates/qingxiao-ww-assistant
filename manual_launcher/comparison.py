"""Evidence-scoped comparison of the personal APP with the pinned official release."""
from datetime import datetime
import html
import json
from pathlib import Path
from catalog import CATALOG
from model import ROOT,RUNS,atomic_json,read_json

VERSION='v3.7.13'
SOURCE='https://github.com/ok-oldking/ok-wuthering-waves/releases/tag/'+VERSION

def comparison_rows():
    # Integration is deliberately separate from live acceptance.
    return [
        ('日常一条龙','内置；可选刷取目标及附加任务','已接入；现可选择无音区／凝素／模拟','未满→满整轮复测仍待验收'),
        ('无音区／凝素／模拟','内置副本刷取','已接入；增加自然体力上限控件','三类均有战斗和体力核验证据'),
        ('Boss声骸','普通／周本／特殊梦魇；多项战斗参数','已接入分类、序号、轮数','有实际战斗与拾取记录；更多Boss组合待验证'),
        ('梦魇／残象聚落','内置目标队列','已接入；增加目标数量上限控件','净化与聚落已有实跑记录'),
        ('乐园周常','内置周常流程','已接入；完成时跳过、支持只检查','有完整历史执行及6000读数证据'),
        ('批量强化','双爆和有效词条规则、成功后暂停','已接入；数量上限、预检与材料设置核对','单候选培养至+15、按规则弃置已验证'),
        ('弃置融合','按100个完整批次融合','已接入；显式批次上限与弃置筛选核对','一批实际融合通过；独立库存账未核验'),
        ('主属性重构','内置游戏内数据重构','本轮新增；目标选择、预检、候选上限、确认与提交记录','接口和模拟流程验证；材料实跑待验收'),
        ('无音消除','3.7.13支持前置→终局冲分','本轮移植正式版；页面预检、运行时限、分关记录','算法与流程检查；活动实跑待验收'),
        ('自动战斗','自动锁敌、解放、治疗切换','已接入；本轮开放辅助参数','已验证真实战斗；新开关待组合实跑'),
        ('自动拾取','名单设置、交互识别','已接入；本轮开放白名单和黑名单','有真实拾取记录及误交互回归'),
        ('跳对话／NPC飞讯','跳过和确认页面处理','已接入，补充实际动作回执','NPC飞讯与真实图片链路已验证'),
        ('快捷传送','识别地图中的快速旅行按钮','本轮新增限时辅助入口','模拟流程验证；真实地图动作待验收'),
        ('剧情组合','各辅助可同时启用','本轮新增可选组合：对话／战斗／拾取／传送','组合循环验证；不包含任务寻路和解谜'),
        ('高级Boss参数','Boss模板、等级、等待时间、拾取方式、解放与治疗开关','当前开放分类／序号／轮数；其余沿用脚本配置，未逐项开放','参数界面尚未完全对齐'),
        ('角色与热键设置','角色命座／打法开关、战斗热键设置','沿用本机已有配置，个人APP尚无完整编辑页','未标记为已完成'),
        ('日常附加任务','完成后可附加周常、聚落、弃置融合和Boss','日常内不自动附加；需在APP队列单独安排','材料项仍逐次确认；队列不等同原生附加设置'),
        ('启动登录／鼠标恢复','内置底层辅助','复用；首次登录验证由本人处理','已有启动和恢复验证'),
        ('多账号','普通轮换及各账号独立配置','已接入；按用户要求暂缓，不继续测试','账号1检查通过；整轮未完成'),
        ('队伍代码／创意工坊','队伍代码管理、搜索、导入导出','尚未接入个人APP界面','保留为后续差异，不标记已支持'),
        ('框架与更新','ok-script 2.0.20；官方更新渠道','运行源3.7.8加选取修复；框架2.0.13','本轮只移植兼容功能，未整体升级框架'),
        ('运行体验','官方任务与参数界面','个人界面、自然语言、任务队列、结果回查和截图','已有UI／协议／恢复测试'),
        ('定时执行','部分任务支持计划运行','保持纯手动，不增加定时或开机触发','当前三个权限任务均无触发器'),
        ('任意主线／支线全自动','本次正式版任务目录未提供通用任务寻路／解谜','未实现通用自动接取、寻路和解谜','辅助跳剧情不能等同全自动过主线'),
    ]

def comparison_data():
    return dict(updated_at=datetime.now().astimezone().isoformat(),official_version=VERSION,official_release=SOURCE,
        app_actions=len(CATALOG),production_source='3.7.8 + selected local/upstream adaptations',
        rows=[dict(feature=r[0],official=r[1],app=r[2],evidence=r[3]) for r in comparison_rows()])

def render_comparison():
    esc=lambda x:html.escape(str(x))
    data=comparison_data()
    rows=''.join('<tr>'+''.join('<td>'+esc(value)+'</td>' for value in row)+'</tr>' for row in comparison_rows())
    return '<html><meta charset="utf-8"><style>body{font:14px/1.7 "Microsoft YaHei UI",sans-serif;color:#234d43;background:#f0f6f4}table{border-collapse:collapse;width:100%}td,th{padding:12px;border:1px solid #d3e3db;text-align:left;vertical-align:top}th{background:#e4efe9}a{color:#247d70}</style><h2>当前 APP 与 OK-WW 功能对照</h2><p>官方基准：<a href="'+SOURCE+'">'+VERSION+'</a> · APP '+str(len(CATALOG))+'项入口。接入状态与实测证据分开列示。</p><table><tr><th>功能</th><th>官方 OK-WW</th><th>当前 APP</th><th>验证范围</th></tr>'+rows+'</table><p>核对时间：'+esc(data['updated_at'])+'</p></html>'

if __name__=='__main__':
    output=RUNS/'app-comparison-20261030';output.mkdir(exist_ok=True)
    atomic_json(output/'comparison.json',comparison_data())
    (output/'comparison.html').write_text(render_comparison(),encoding='utf-8')
    print(json.dumps({'official_version':VERSION,'app_actions':len(CATALOG),'rows':len(comparison_rows())}))
