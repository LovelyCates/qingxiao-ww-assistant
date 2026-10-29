"""Bounded result indexing and incremental log tailing, without game imports."""
from pathlib import Path
from datetime import datetime,timedelta
import time
from model import RUNS, read_json

SUCCESS = {'PROBE_PASSED','READBACK_PASSED','SKIPPED_ALREADY_COMPLETE','ALREADY_WEEKLY_COMPLETE',
           'FARM_PASSED','FARM_READBACK_PASSED','SKIPPED_INSUFFICIENT_STAMINA','EXECUTION_FINISHED','ASSIST_FINISHED','NO_ELIGIBLE_ECHOES'}

class RunHistory:
    def __init__(self):
        self.cache = {}
        self.last_scan = 0
        self.records = []

    def refresh(self, force=False):
        if not force and time.monotonic() - self.last_scan < 5:
            return self.records
        self.last_scan = time.monotonic()
        seen = set()
        for path in RUNS.glob('*/report.json'):
            try:
                stat = path.stat()
                signature = (stat.st_mtime_ns,stat.st_size)
                seen.add(path)
                if path not in self.cache or self.cache[path][0] != signature:
                    report = read_json(path, {})
                    if report:
                        self.cache[path] = (signature,dict(report,_path=str(path),_run=path.parent.name))
            except OSError:
                continue
        self.cache = {p:v for p,v in self.cache.items() if p in seen}
        self.records = sorted((v[1] for v in self.cache.values()),key=lambda r:r.get('started_at',''),reverse=True)[:250]
        for record in self.records:
            record.pop('_verified_stamina_spent',None)
            record.pop('_verification_note',None)
        verification=read_json(RUNS/'verified-farm-consumption.json',{})
        if verification.get('consumption_verified'):
            source=verification.get('source_report')
            for record in self.records:
                if record['_path']==source:
                    record['_verified_stamina_spent']=verification.get('stamina_spent')
                    record['_verification_note']='原运行报错，后续截图与读数已核验消耗。'
        return self.records

    def summary(self):
        records = self.refresh()
        completed = [r for r in records if r.get('ended_at')]
        now=datetime.now().astimezone()
        def periods(value):
            try:
                stamp=datetime.fromisoformat(value)
                if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=now.tzinfo)
                day=(stamp.astimezone(now.tzinfo)-timedelta(hours=4)).date()
                return day,day-timedelta(days=day.weekday())
            except (ValueError,TypeError):return None,None
        day,week=periods(now.isoformat())
        activity_record=next((r for r in records if r.get('activity_points') is not None and r.get('status') in SUCCESS
                             and periods(r.get('updated_at') or r.get('ended_at'))[0]==day),{})
        weekly_record=next((r for r in records if r.get('weekly_progress_points') is not None and r.get('status') in SUCCESS
                           and periods(r.get('updated_at') or r.get('ended_at'))[1]==week),{})
        # A batch can leave a different account logged in, even after failure.
        # Keep child readings scoped to their account rather than showing an
        # earlier single-account reading as the current account's progress.
        switched_at=max((r.get('started_at','') for r in records if r.get('mode')=='multiaccount'),default='')
        if activity_record.get('started_at','')<switched_at:activity_record={}
        if weekly_record.get('started_at','')<switched_at:weekly_record={}
        spent = sum((r.get('_verified_stamina_spent') if r.get('_verified_stamina_spent') is not None else r.get('stamina_spent') or 0)
                    for r in completed if r.get('status')=='FARM_PASSED' or r.get('_verified_stamina_spent') is not None)
        return {'runs':len(completed),'successes':sum(r.get('status') in SUCCESS for r in completed),
                'activity':activity_record.get('activity_points'),'weekly':weekly_record.get('weekly_progress_points'),
                'activity_observed_at':activity_record.get('updated_at') or activity_record.get('ended_at'),
                'weekly_observed_at':weekly_record.get('updated_at') or weekly_record.get('ended_at'),
                'server_day':str(day),'server_week':str(week),'verified_stamina_spent':spent,
                'recent_tasks':[{key:r[key] for key in ('mode','status','ended_at','echo_count','assist_action') if key in r}
                                for r in completed[:6]]}

    def screenshots(self, record, limit=10):
        folder = Path(record['_path']).parent / 'screenshots'
        return sorted(folder.rglob('*.png'),key=lambda p:(p.stat().st_mtime_ns,p.as_posix()),reverse=True)[:limit]

class IncrementalTail:
    def __init__(self, limit=24000):
        self.limit = limit
        self.offsets = {}
        self.texts = {}
    def read(self, folder):
        changed = False
        for name in ('stdout.log','stderr.log'):
            path = Path(folder) / name
            try:
                size = path.stat().st_size
                offset = self.offsets.get(path,0)
                if size == offset:
                    continue
                if size < offset or size-offset > self.limit:
                    offset = max(0,size-self.limit)
                    self.texts[path] = ''
                with path.open('rb') as stream:
                    stream.seek(offset)
                    chunk = stream.read(self.limit)
                    self.offsets[path] = stream.tell()
                self.texts[path] = (self.texts.get(path,'') + chunk.decode('utf-8',errors='replace'))[-self.limit:]
                changed = True
            except OSError:
                continue
        content = '\n'.join(self.texts.get(Path(folder)/name,'') for name in ('stdout.log','stderr.log'))
        return content, changed
