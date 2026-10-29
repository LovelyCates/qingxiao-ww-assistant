"""Fetch pinned runtime resources directly from upstream; never republish them."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import sys
import time
from urllib import request,parse,error
import uuid

ROOT=Path(__file__).resolve().parents[1]

def download(url,limit):
    for attempt in range(3):
        try:
            with request.urlopen(url,timeout=45) as response:return response.read(limit)
        except (error.URLError,TimeoutError,OSError) as exc:
            if isinstance(exc,error.HTTPError) and exc.code not in (408,429) and exc.code<500:raise
            if attempt==2:raise
            time.sleep(attempt+1)

def resource_path(entry,source):
    relative=PurePosixPath(entry.get('path',''))
    if (relative.is_absolute() or '..' in relative.parts or '\\' in str(relative)
        or not relative.parts or relative.parts[0] not in ('assets','icons','i18n')
        or not re.fullmatch('[a-f0-9]{64}',entry.get('sha256',''))
        or type(entry.get('bytes')) is not int or not 0<entry['bytes']<60*1024*1024):
        raise ValueError('Invalid upstream resource manifest entry')
    path=(Path(source)/str(relative)).resolve();path.relative_to(Path(source).resolve())
    return path

def fetch_one(entry,source,base):
    path=resource_path(entry,source)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']:return 'cached'
        raise ValueError('Existing resource differs; move it aside before retrying: '+entry['path'])
    url=base+parse.quote(entry['path'],safe='/')
    try:data=download(url,entry['bytes']+1)
    except (error.URLError,TimeoutError,OSError) as exc:
        raise RuntimeError('Failed to download '+entry['path']+'; check network and retry. Verified files are retained.') from exc
    if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
        raise ValueError('Upstream resource checksum mismatch: '+entry['path'])
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_bytes(data)
        if path.exists():raise ValueError('Resource appeared during download; not overwritten')
        os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()
    return 'downloaded'

def main():
    manifest=json.loads((ROOT/'upstream-resources.json').read_text(encoding='utf-8'))
    if manifest['repository']!='ok-oldking/ok-wuthering-waves' or manifest['ref']!='v3.7.8':
        raise ValueError('Unexpected upstream repository/ref')
    source=ROOT/'ok-wuthering-waves-3.7.8'
    entries=manifest['files'];paths=[resource_path(entry,source) for entry in entries]
    if len(set(paths))!=len(paths):raise ValueError('Duplicate upstream resource path')
    if '--check' in sys.argv:
        missing=[entry['path'] for entry,path in zip(entries,paths) if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest()!=entry['sha256']]
        print(json.dumps({'verified':len(entries)-len(missing),'missing_or_changed':missing}))
        return 2 if missing else 0
    base='https://raw.githubusercontent.com/'+manifest['repository']+'/'+manifest['ref']+'/'
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(lambda entry:fetch_one(entry,source,base),entries))
    print(json.dumps({'verified':len(results),'downloaded':results.count('downloaded'),'cached':results.count('cached')}))
    return 0

if __name__=='__main__':raise SystemExit(main())
