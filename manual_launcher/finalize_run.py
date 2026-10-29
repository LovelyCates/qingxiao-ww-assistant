"""Finalize a terminated worker's evidence; never controls or launches the game."""
import argparse
from datetime import datetime
import html
import json
from pathlib import Path
from model import ROOT, atomic_json, read_json

TERMINAL={'PROBE_PASSED','READBACK_PASSED','SKIPPED_ALREADY_COMPLETE','ALREADY_WEEKLY_COMPLETE',
          'FARM_PASSED','FARM_READBACK_PASSED','SKIPPED_INSUFFICIENT_STAMINA',
          'EXECUTION_FINISHED','ASSIST_FINISHED','NO_ELIGIBLE_ECHOES','NEEDS_REVIEW','FAILED','CANCELLED','TIMEOUT','NEEDS_ADMIN'}

def finalize(folder,exit_code,timed_out=False):
    folder=Path(folder).resolve()
    folder.relative_to(ROOT/'local-runs')
    if folder.parent!=ROOT/'local-runs':raise ValueError('Unexpected run directory')
    path=folder/'report.json';report=read_json(path,{})
    terminal=report.get('status') in TERMINAL and bool(report.get('ended_at'))
    known_failure=report.get('status') in {'FAILED','CANCELLED','TIMEOUT','NEEDS_ADMIN','NEEDS_REVIEW'}
    if terminal and not timed_out and (exit_code==0 or known_failure):
        return {'Changed':False,'Status':report['status']}
    stamp=datetime.now().astimezone().isoformat()
    old_status=report.get('status')
    report.update(status='TIMEOUT' if timed_out else 'NEEDS_REVIEW' if terminal else 'FAILED',stage='worker_timed_out' if timed_out else 'worker_exit_after_report' if terminal else 'worker_exited_unexpectedly',
                  worker_exit_code=exit_code,worker_last_status=old_status,ended_at=stamp,updated_at=stamp)
    report.setdefault('started_at',stamp)
    report.setdefault('mode',folder.name.split('-')[0])
    errors=list(report.get('errors') or [])
    errors.append('任务超过运行时限，工作进程已停止。' if timed_out else f'工作进程已退出（代码 {exit_code}），没有完整结束报告。请核对最后截图与日志；没有自动重试消耗操作。')
    report['errors']=errors
    recovery=read_json(folder/'window-recovery.json',None)
    if recovery is not None:report['window_recovery']=recovery
    atomic_json(path,report)
    from reporting import write_report_html
    write_report_html(report,path)
    atomic_json(folder/'process-result.json',{'ExitCode':exit_code,'EndedAt':stamp,'TimedOut':timed_out})
    return {'Changed':True,'Status':report['status']}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);parser.add_argument('--exit-code',type=int,required=True);parser.add_argument('--timed-out',action='store_true')
    args=parser.parse_args();print(json.dumps(finalize(args.folder,args.exit_code,args.timed_out)))
