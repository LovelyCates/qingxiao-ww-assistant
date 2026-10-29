"""Recover only this game's presentation after an abnormal worker exit."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def recover(path):
    path=Path(path).resolve();path.relative_to(ROOT/'local-runs')
    if path.name!='window-lease.json':raise ValueError('Unexpected presentation lease')
    lease=json.loads(path.read_text(encoding='utf-8-sig'))
    if not lease.get('Active'):return {'Recovered':False,'Reason':'already_released'}
    hwnd=lease['Hwnd'];user32=ctypes.windll.user32
    user32.IsWindow.argtypes=[wintypes.HWND]
    user32.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
    user32.IsIconic.argtypes=[wintypes.HWND]
    user32.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int]
    user32.GetWindowLongPtrW.restype=ctypes.c_ssize_t
    if not user32.IsWindow(hwnd):return {'Recovered':False,'Reason':'game_window_closed'}
    name=ctypes.create_unicode_buffer(256);user32.GetClassNameW(hwnd,name,256)
    pid=wintypes.DWORD();user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    if name.value!='UnrealWindow' or pid.value!=lease.get('GamePid'):raise ValueError('Game window identity changed')
    if lease.get('Backend')=='layered':
        user32.SetLayeredWindowAttributes.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_ubyte,wintypes.DWORD]
        user32.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t]
        user32.SetLayeredWindowAttributes(hwnd,0,255,2)
        user32.SetWindowLongPtrW(hwnd,-20,lease['OriginalStyle'])
        if user32.GetWindowLongPtrW(hwnd,-20)!=lease['OriginalStyle']:
            raise RuntimeError('Game presentation style recovery failed')
    elif lease.get('Backend')=='dwm':
        flag=wintypes.BOOL(False);dwm=ctypes.windll.dwmapi
        dwm.DwmSetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
        if dwm.DwmSetWindowAttribute(hwnd,13,ctypes.byref(flag),ctypes.sizeof(flag))!=0:
            raise RuntimeError('Game cloak recovery failed')
    user32.ShowWindow(hwnd,6)
    minimized=bool(user32.IsIconic(hwnd))
    if not minimized:raise RuntimeError('Game recovery did not reach the taskbar')
    lease.update(Active=False,RecoveredAfterWorkerExit=True)
    path.write_text(json.dumps(lease,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'Recovered':True,'GamePid':pid.value,'OriginalStyleRestored':True,'Minimized':minimized}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('lease',type=Path);args=parser.parse_args()
    print(json.dumps(recover(args.lease)))
