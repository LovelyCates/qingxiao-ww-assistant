"""Summarize an existing farm/readback pair; performs no game actions."""
from pathlib import Path
import html
import json
from local_runner import reconcile_stamina

root = Path(__file__).resolve().parent
runs = root / 'local-runs'
pointer = json.loads((runs / 'latest-farm.json').read_text(encoding='utf-8-sig'))
report_path = Path(pointer['Report']).resolve()
report_path.relative_to(runs.resolve())
readback = json.loads(report_path.read_text(encoding='utf-8-sig'))
if readback.get('stage') != 'farm_readback_finished':
    raise RuntimeError('The most recent run did not finish its readback.')
source_path = Path(readback['source_report']).resolve()
source_path.relative_to(runs.resolve())
source = json.loads(source_path.read_text(encoding='utf-8-sig'))
cost = 60 if source['farming_target'] == 'tacet' else 40
accounting = reconcile_stamina(source['stamina_before'], readback['stamina_after'], source['stamina_budget'], cost)
if not accounting['consumption_verified']:
    raise RuntimeError('Consumption accounting did not pass; original reports were left untouched.')
claim_images = sorted((source_path.parent / 'screenshots').glob('*before-reward-claim_original.png'))
readback_images = sorted((report_path.parent / 'screenshots').glob('*reconciled-after-stamina_original.png'))
reward_images = sorted((source_path.parent / 'screenshots').glob('*natural-stamina-unreadable_original.png'))
if not claim_images or not readback_images or not reward_images:
    raise RuntimeError('Missing evidence screenshots; did not generate a verified summary.')
summary = dict(status='CONSUMPTION_VERIFIED_AFTER_READBACK', observed_at=readback['ended_at'],
               farming_target=source['farming_target'], stamina_before=source['stamina_before'],
               stamina_after_at_readback=readback['stamina_after'], **accounting,
               refill_allowed=False, stored_stamina_allowed=False,
               returned_to_game_main=readback['game_main_observed'],
               original_execution_status=source['status'], readback_execution_status=readback['status'],
               source_report=str(source_path), readback_report=str(report_path),
               screenshots=[str(claim_images[-1]), str(reward_images[-1]), str(readback_images[-1])],
               limitation='Original run reported an OCR error after claiming rewards; follow-up readback verified consumption. Inventory contents were not separately audited.')
summary_path = report_path.parent / 'final-summary.json'
summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
figures = ''.join('<figure><img src="' + html.escape(Path(p).relative_to(runs).as_posix(), quote=True) + '"></figure>' for p in summary['screenshots'])
target_name = {'tacet': '无音区列表第1项', 'simulation': '模拟领域（贝币）', 'forgery': '凝素领域列表第1项'}[summary['farming_target']]
page = ('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>鸣潮刷取结果：已消耗{summary["stamina_spent"]}点体力</title>'
        '<style>body{font:16px/1.8 system-ui;max-width:900px;margin:36px auto;padding:20px;background:#f2f6f4;color:#17362e}h1{font-size:30px}article{background:white;padding:24px;border-radius:14px}img{max-width:100%;height:auto}figure{margin:20px 0}a{color:#006956}</style>'
        f'<article><h1>本轮刷取已完成</h1><p>已按配置完成{target_name}刷取并领取奖励，实际消耗 <strong>{summary["stamina_spent"]} 点自然体力</strong>。</p>'
        f'<p>领取前 {summary["stamina_before"]} → 复查时 {summary["stamina_after_at_readback"]}。净减少 {summary["net_stamina_decrease"]} 点，按奖励费用核算回查期间自然恢复了 {summary["natural_regeneration_inferred"]} 点；未补充体力、未使用备用体力。</p>'
        '<p>原执行在领奖后的体力识别处报错并停止；后续读取指南体力，完成消耗核验。原始失败记录保留，不代表整套日常／周常或定时已经验收。</p>'
        '<p><a href="' + html.escape(source_path.parent.name, quote=True) + '/report.html">原执行报告</a> · <a href="' + html.escape(report_path.parent.name, quote=True) + '/report.html">回查报告</a></p>'
        + figures + '</article></html>')
# This summary lives at the runs root, so the evidence paths remain relative.
(runs / 'latest-farm-summary.html').write_text(page, encoding='utf-8')
(runs / 'verified-farm-consumption.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(dict(summary=str(runs / 'latest-farm-summary.html'), stamina_spent=accounting['stamina_spent'], stamina_after=readback['stamina_after']), ensure_ascii=False))
