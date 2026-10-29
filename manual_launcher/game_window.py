"""Task-local presentation policy for the game window selected by OK-WW.

Never sends gameplay input. DWM hiding is experimental until real capture and
readback pass; any failure is reported, and the window is restored on cleanup.
"""
import ctypes
from ctypes import wintypes
import threading
import time
import json

def foreground_window():
    user32=ctypes.windll.user32;user32.GetForegroundWindow.restype=wintypes.HWND
    return user32.GetForegroundWindow()

def prepare_existing_game():
    """Restore only a minimized Unreal window owned by the official game binary.

    OK-WW can't discover a usable capture surface while its bounds are minimized.
    Restore without activation before device discovery, preserving single-instance.
    """
    import psutil
    import win32con
    import win32gui
    import win32process
    game_pids={p.info['pid'] for p in psutil.process_iter(['pid','name'])
               if (p.info['name'] or '').casefold()=='client-win64-shipping.exe'}
    restored=[]
    def visit(hwnd,_):
        if win32gui.GetClassName(hwnd)!='UnrealWindow':return
        _,pid=win32process.GetWindowThreadProcessId(hwnd)
        if pid in game_pids and win32gui.IsIconic(hwnd):
            win32gui.ShowWindow(hwnd,win32con.SW_SHOWNOACTIVATE)
            restored.append(hwnd)
    win32gui.EnumWindows(visit,None)
    if restored:time.sleep(0.8)
    return restored

class GameWindowPolicy:
    def __init__(self,runtime,mode,save,command_file=None,request_id=None,return_hwnd=None):
        self.runtime=runtime;self.mode=mode;self.save=save;self.hwnd=0
        self.hidden=False;self.hide_backend=None;self.original_style=None;self.manual_reveal=False;self.stopped=threading.Event();self.lock=threading.RLock()
        self.user32=ctypes.windll.user32;self.dwm=ctypes.windll.dwmapi
        self.user32.GetForegroundWindow.restype=wintypes.HWND
        self.user32.SetForegroundWindow.argtypes=[wintypes.HWND]
        self.user32.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int];self.user32.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        self.user32.SetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int,ctypes.c_ssize_t];self.user32.SetWindowLongPtrW.restype=ctypes.c_ssize_t
        self.user32.SetLayeredWindowAttributes.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_ubyte,wintypes.DWORD]
        self.user32.IsWindow.argtypes=[wintypes.HWND];self.user32.IsIconic.argtypes=[wintypes.HWND]
        self.user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        self.user32.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
        self.user32.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        self.dwm.DwmSetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
        self.dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
        self.return_hwnd=return_hwnd or self.user32.GetForegroundWindow();self.last_foreground=self.return_hwnd
        self.command_file=command_file;self.request_id=request_id;self.last_command=None
        self.lease_file=command_file.with_name('window-lease.json') if command_file else None
        self.thread=threading.Thread(target=self.run,name='MCGamePresentation',daemon=True)
    def start(self):
        if self.mode!='foreground':self.thread.start()
    def return_focus(self):
        # Only undo the game's own activation. Do not take focus away from a
        # different application the user opened during worker initialization.
        if self.user32.GetForegroundWindow()!=self.hwnd:return
        if self.return_hwnd and self.return_hwnd!=self.hwnd and self.user32.IsWindow(self.return_hwnd):
            self.user32.SetForegroundWindow(self.return_hwnd)
    def cloak(self,enabled):
        if enabled and self.hidden:return 0,True
        if not enabled and not self.hidden:return 0,False
        if not enabled and self.hide_backend=='layered':
            alpha_restored=self.user32.SetLayeredWindowAttributes(self.hwnd,0,255,2)
            self.user32.SetWindowLongPtrW(self.hwnd,-20,self.original_style)
            if not alpha_restored or self.user32.GetWindowLongPtrW(self.hwnd,-20)!=self.original_style:
                raise RuntimeError('Game window restoration could not be verified; recovery lease remains active')
            self.hidden=False;self.write_lease(False);return 0,False
        flag=wintypes.BOOL(enabled)
        code=self.dwm.DwmSetWindowAttribute(self.hwnd,13,ctypes.byref(flag),ctypes.sizeof(flag))
        state=wintypes.DWORD()
        read=self.dwm.DwmGetWindowAttribute(self.hwnd,14,ctypes.byref(state),ctypes.sizeof(state))
        self.hidden=code==0 and read==0 and bool(state.value)
        if self.hidden:self.hide_backend='dwm'
        if enabled and not self.hidden:
            if self.original_style is None:self.original_style=self.user32.GetWindowLongPtrW(self.hwnd,-20)
            self.user32.SetWindowLongPtrW(self.hwnd,-20,self.original_style|0x00080000|0x00000020)
            if self.user32.SetLayeredWindowAttributes(self.hwnd,0,1,2):
                self.hidden=True;self.hide_backend='layered'
            else:
                self.user32.SetWindowLongPtrW(self.hwnd,-20,self.original_style)
        self.write_lease(self.hidden)
        return code,self.hidden
    def write_lease(self,active):
        if not self.lease_file:return
        from model import atomic_json
        pid=wintypes.DWORD();self.user32.GetWindowThreadProcessId(self.hwnd,ctypes.byref(pid))
        atomic_json(self.lease_file,{'Active':bool(active),'Hwnd':self.hwnd,'GamePid':pid.value,
                                   'Backend':self.hide_backend,'OriginalStyle':self.original_style,
                                   'RequestId':self.request_id})
    def run(self):
        try:self._run_loop()
        except Exception as exc:
            try:self.save(window_policy_error=str(exc),window_mode_effective='needs_recovery')
            finally:
                if self.command_file:
                    from model import atomic_json
                    atomic_json(self.command_file.with_name('stop-request.json'),
                                {'RequestId':self.request_id,'Stop':True,'Reason':'window_policy_error'})
                self.stopped.set()
    def _run_loop(self):
        while not self.stopped.wait(0.5):
            window=getattr(self.runtime.device_manager,'hwnd',None)
            if window is None:window=getattr(self.runtime.device_manager,'hwnd_window',None)
            hwnd=getattr(window,'hwnd',0)
            if not hwnd or not self.user32.IsWindow(hwnd):continue
            with self.lock:
                if not self.hwnd:
                    if self.mode=='hidden' and getattr(self.runtime.task_executor,'current_task',None) is None:
                        continue
                    self.hwnd=hwnd
                    # Keep the game rendering in its normal screen bounds, beneath
                    # other applications. No minimize while an active task captures.
                    if self.user32.IsIconic(hwnd):self.user32.ShowWindow(hwnd,4)
                    self.user32.SetWindowPos(hwnd,1,0,0,0,0,0x0010|0x0001|0x0002)
                    self.return_focus()
                    if self.mode=='hidden':
                        code,hidden=self.cloak(True)
                        self.save(window_mode_requested=self.mode,window_mode_effective=(self.hide_backend+'_hidden') if hidden else 'background',window_hide_hresult=code,
                                  window_hidden_has_foreground=self.user32.GetForegroundWindow()==hwnd)
                    else:self.save(window_mode_requested=self.mode,window_mode_effective='background')
                    self.last_foreground=self.user32.GetForegroundWindow()
                    continue
                foreground=self.user32.GetForegroundWindow()
                if foreground==self.hwnd and self.last_foreground!=self.hwnd:
                    if self.hidden:self.cloak(False)
                    self.manual_reveal=True
                    self.save(window_manually_revealed=True,window_mode_effective='user_visible',window_reveal_reason='foreground_activated')
                self.last_foreground=foreground
                self.process_command()
    def process_command(self):
        if not self.command_file:return
        try:command=json.loads(self.command_file.read_text(encoding='utf-8-sig'))
        except (OSError,ValueError):return
        if command.get('RequestId')!=self.request_id or command.get('Id')==self.last_command:return
        if command.get('Action') not in ('show','hide'):return
        self.last_command=command.get('Id')
        if command['Action']=='show':
            if self.hidden:self.cloak(False)
            self.user32.ShowWindow(self.hwnd,9)
            self.user32.SetForegroundWindow(self.hwnd)
            self.manual_reveal=True
            self.save(window_manually_revealed=True,window_mode_effective='user_visible',window_command_ack=self.last_command,window_reveal_reason='assistant_button')
        else:
            self.manual_reveal=False
            self.user32.SetWindowPos(self.hwnd,1,0,0,0,0,0x0010|0x0001|0x0002)
            if self.mode=='hidden':self.cloak(True)
            self.save(window_mode_effective=(self.hide_backend+'_hidden') if self.hidden else 'background',window_command_ack=self.last_command)
    def finish(self):
        self.stopped.set()
        if self.thread.is_alive():self.thread.join(timeout=1.5)
        with self.lock:
            if self.hwnd and self.user32.IsWindow(self.hwnd):
                if self.hidden:self.cloak(False)
                if self.mode!='foreground' and not self.manual_reveal:
                    self.user32.ShowWindow(self.hwnd,6)
                    self.save(game_minimized_after_task=bool(self.user32.IsIconic(self.hwnd)))
