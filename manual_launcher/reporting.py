"""Readable local report pages; raw evidence stays available below the summary."""
from datetime import datetime
import html
import json
import os
from pathlib import Path
from urllib.parse import quote
try:
    from .model import ROOT,STATES,STAGES,read_json
    from .runtime_settings import asset_path
except ImportError:
    from model import ROOT,STATES,STAGES,read_json
    from runtime_settings import asset_path

VERIFICATION=ROOT/'local-runs/verified-farm-consumption.json'
def esc(value):return html.escape(str(value),quote=True)
def elapsed(report):
    try:
        start=datetime.fromisoformat(report['started_at']);end=datetime.fromisoformat(report.get('ended_at') or report['updated_at'])
        seconds=max(0,round((end-start).total_seconds()))
        return f'{seconds//60}分{seconds%60:02d}秒'
    except (KeyError,TypeError,ValueError):return '尚未记录'

def render_report(report,path):
    path=Path(path);status=report.get('status','STARTING');failure=status in ('FAILED','TIMEOUT','NEEDS_ADMIN','NEEDS_REVIEW')
    title={'probe':'今日进度检查','daily':'日常一条龙','weekly':'乐园周常','farm':'自然体力刷取','echo':'Boss声骸',
           'nightmare':'梦魇／残象聚落','assist':'游玩辅助','merge':'弃置声骸合成','enhance':'声骸培养','multiaccount':'多账号任务','mainstat':'声骸主属性重构','event':'无音消除活动'}.get(report.get('mode'),'本次任务')
    state=STATES.get(status,'运行中' if status=='STARTING' else status)
    cards=[('任务结果',state),('运行时长',elapsed(report))]
    if report.get('account_results') is not None:
        rows=report['account_results'];cards.append(('账号完成',f'{sum(r.get("status")=="completed" for r in rows)} / {len(rows)}'))
    if report.get('selected_echo_level') is not None:cards.append(('当前声骸等级','+'+str(report['selected_echo_level'])))
    if report.get('merge_selected_materials') is not None:cards.append(('预检选中材料',str(report['merge_selected_materials'])+' / 100'))
    if report.get('activity_points') is not None:cards.append(('活跃度',str(report['activity_points'])+' / 100'))
    if report.get('weekly_progress_points') is not None:cards.append(('周游历',str(report['weekly_progress_points'])+' / 6000'))
    if report.get('echo_count') is not None:cards.append(('声骸拾取读数',str(report['echo_count'])))
    if report.get('assist_elapsed_seconds') is not None:cards.append(('辅助运行',str(report['assist_elapsed_seconds'])+' 秒'))
    for key,label in (('enhance_selected','培养候选'),('enhance_success','合格锁定'),('enhance_rejected','不合格弃置'),
                      ('merge_batches','已完成合成批数'),('pickup_interactions','拾取交互次数'),('combat_sessions','战斗处理次数'),('dialog_actions','对话操作次数'),
                      ('travel_actions','快捷传送次数'),('reconstruct_completed','完成重构数量'),('event_stages','本轮完成关卡'),('event_reward_claims','活动领奖动作')):
        if report.get(key) is not None:cards.append((label,report[key]))
    spent=None;spent_note=''
    verification=read_json(VERIFICATION,{})
    if verification.get('consumption_verified') and str(verification.get('source_report','')).casefold()==str(path).casefold():
        spent=verification.get('stamina_spent');spent_note='原运行异常，后续截图回查核实；原始状态保留。'
    elif status in ('FARM_PASSED','FARM_READBACK_PASSED') and report.get('stamina_spent') is not None:
        spent=report['stamina_spent']
    if spent is not None:cards.append(('已核实体力消耗',str(spent)))
    elif report.get('pending_claim') or report.get('mode')=='farm':cards.append(('体力消耗','待核对'))
    notes=[]
    if report.get('check_only') and report.get('discard_filter_verified'):notes.append('已核对只筛选弃置声骸。本次预检只选择材料，没有提交融合。')
    if report.get('detection_only'):notes.append('本次只检测，没有进入补做或刷取。')
    if report.get('window_hidden_has_foreground') is False:notes.append('隐藏时焦点已交还原窗口，游戏未占用前台。')
    if report.get('game_minimized_after_task'):notes.append('任务结束后，游戏已恢复窗口样式并收回任务栏。')
    if report.get('material_consumption_independently_verified') is False:notes.append('材料消耗未独立核实，请核对背包与截图。')
    if report.get('pending_claim'):notes.append('记录了尚未完成核验的领奖操作，请先查截图，不要直接重复领取。')
    if report.get('pending_reconstruct'):notes.append('重构提交尚无完整回执，请先核对截图，不要直接重试消耗材料。')
    if report.get('main_attribute_independently_verified') is False:notes.append('已记录游戏重构结果弹窗，未独立核验主属性与材料库存。')
    if report.get('event_end_reason')=='time_limit':notes.append('达到本轮运行时限，进度保留；这不表示活动已经全部完成。')
    if spent_note:notes.append(spent_note)
    folder=path.parent
    log_prefix='../../../' if report.get('account_scoped') else ''
    screenshot_root=folder/'screenshots'
    images=sorted(screenshot_root.rglob('*.png'),key=lambda p:(p.stat().st_mtime_ns,p.as_posix()))[-12:]
    figures=''.join('<a href="screenshots/'+quote(p.relative_to(screenshot_root).as_posix(),safe='/')+'"><img loading="lazy" src="screenshots/'+quote(p.relative_to(screenshot_root).as_posix(),safe='/')+'" alt="'+esc(p.stem)+'"><span>'+esc(p.stem)+'</span></a>' for p in images)
    asset=quote(os.path.relpath(asset_path('qingxiao-icon.png','app-icon.png'),folder).replace('\\','/'),safe='/')
    card_html=''.join('<div class="card"><small>'+esc(label)+'</small><strong>'+esc(value)+'</strong></div>' for label,value in cards)
    errors=list(report.get('errors') or []);recovered=report.get('recovered_log_errors') or []
    if report.get('stop_reason') and report['stop_reason'] not in errors:errors.append(report['stop_reason'])
    for key in ('window_policy_error','window_cleanup_error'):
        if report.get(key) and report[key] not in errors:errors.append(report[key])
    issues=('<section class="warning"><h2>需要核对</h2><ul>'+''.join('<li>'+esc(x)+'</li>' for x in errors)+'</ul></section>') if errors else ''
    if recovered:issues+='<details><summary>已恢复提示 · 原始日志保留</summary><ul>'+''.join('<li>'+esc(x)+'</li>' for x in recovered)+'</ul></details>'
    if report.get('account_results'):
        states={'pending':'等待','logging_in':'切换账号','running':'执行中','completed':'完成','failed':'失败','cancelled':'已停止'}
        items=[]
        for row in report['account_results']:
            links=[]
            for step in row.get('steps',[]):
                target=Path(step.get('report',''))
                try:relative=target.resolve().relative_to(folder.resolve()).with_suffix('.html').as_posix()
                except ValueError:continue
                links.append('<a href="'+quote(relative,safe='/')+'">'+esc(step.get('action','任务'))+'：'+esc(STATES.get(step.get('status'),step.get('status','未知')))+'</a>')
            items.append('<tr><td>'+esc(row['label'])+'</td><td>'+esc(states.get(row['status'],row['status']))+'</td><td>'+str(row.get('completed_steps',0))+'</td><td>'+'<br>'.join(links)+'</td></tr>')
        issues+='<section><h2>各账号结果</h2><table><tr><th>账号备注</th><th>状态</th><th>已完成步骤</th><th>步骤报告</th></tr>'+''.join(items)+'</table></section>'
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'''+esc(title)+''' · 清宵助手</title>
<style>body{margin:0;background:#f0f6f4;color:#163f42;font:15px/1.8 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1160px;margin:auto;padding:34px 24px 70px}header{display:flex;gap:20px;align-items:center;margin-bottom:24px}header img{width:76px;height:76px;border-radius:18px}h1{font:34px KaiTi,serif;margin:0}h2{font-size:21px}p{margin:7px 0}.muted,small{color:#688580}.badge{display:inline-block;background:#e1efe9;color:#247d70;border-radius:16px;padding:4px 13px}.bad{background:#f5e3df;color:#9b504b}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px}.card,section,details{background:white;border:1px solid #d6e6df;border-radius:18px;padding:18px 22px}.card strong{display:block;font-size:22px;margin-top:8px}.warning{background:#fff4e0;border-color:#ead4ab}section,details{margin:20px 0}summary{cursor:pointer}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.7 Consolas,monospace}a{color:#247d70}.images{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}.images img{width:100%;border-radius:12px}.images span{display:block;font-size:12px;overflow-wrap:anywhere}.images a{text-decoration:none}.links{display:flex;gap:20px;flex-wrap:wrap}</style><main>
<header><img src="'''+asset+'''" alt="清宵个人版图标"><div><p class="muted">鸣潮 · 本机任务记录</p><h1>'''+esc(title)+'''</h1><p><span class="badge '''+('bad' if failure else '')+'">'+esc(state)+'''</span></p></div></header>
<div class="cards">'''+card_html+'''</div><section><p>阶段：'''+esc(STAGES.get(report.get('stage'),report.get('stage','尚未记录')))+'''</p><p class="muted">开始：'''+esc(report.get('started_at','尚未记录'))+'''</p>'''+''.join('<p>'+esc(x)+'</p>' for x in notes)+'''</section>'''+issues+'''
<h2>本次截图</h2><p class="muted">点击查看原图；最多展示最近12张，完整截图保存在本次运行文件夹。</p><div class="images">'''+(figures or '<p>本次暂无截图。</p>')+'''</div>
<details><summary>原始运行数据</summary><pre>'''+esc(json.dumps(report,ensure_ascii=False,indent=2))+'''</pre></details><p class="links"><a href="report.json">原始JSON</a><a href="stdout.log">运行日志</a><a href="stderr.log">错误日志</a><a href="../qingxiao-upgrade-acceptance.html">整体验收进度</a></p><p class="muted">状态未完成时不能据此宣称成功。进度与拾取为画面识别读数，不代表独立核实全部奖励到账。</p></main></html>'''
    if log_prefix:
        page=page.replace('href="stdout.log"','href="'+log_prefix+'stdout.log"').replace('href="stderr.log"','href="'+log_prefix+'stderr.log"')
    return page

def write_report_html(report,path):
    path=Path(path)
    path.with_suffix('.html').write_text(render_report(report,path),encoding='utf-8')
