"""Machine-local paths; never include local-config.json in a source release."""
import hashlib
import json
import os
from pathlib import Path
import uuid

ROOT=Path(__file__).resolve().parents[1]

def load_runtime_settings(root=ROOT):
    path=Path(root)/'local-config.json'
    if not path.exists():return {}
    try:values=json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError) as exc:raise ValueError('本机路径配置无法读取，请重新选择游戏启动器。') from exc
    if not isinstance(values,dict) or set(values)-{'game_executable'} or not isinstance(values.get('game_executable',''),str):
        raise ValueError('本机路径配置格式无效。')
    return values

def game_executable(root=ROOT):
    raw=os.environ.get('WW_GAME_EXE') or load_runtime_settings(root).get('game_executable','')
    return Path(raw).expanduser() if raw else None

def save_game_executable(path,root=ROOT):
    path=Path(path).expanduser().resolve()
    if not path.is_file() or path.suffix.lower()!='.exe':raise ValueError('请选择已经安装的游戏启动器 EXE。')
    destination=Path(root)/'local-config.json';temp=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps({'game_executable':str(path)},ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temp,destination)

def panel_instance_key(root=ROOT):
    digest=hashlib.sha256(str(Path(root).resolve()).casefold().encode('utf-8')).hexdigest()[:20]
    return 'MC-Manual-Panel-'+digest

def asset_path(name,fallback):
    folder=ROOT/'manual_launcher/assets';preferred=folder/name
    return preferred if preferred.is_file() else folder/fallback
