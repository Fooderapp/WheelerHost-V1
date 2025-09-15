"""
MemoryScan: Optional per-game memory readers (Windows-only).

Goal: Provide simple signals like speed01, absGate, slipGate, impactBoost
without blocking the main loop. Uses a polling thread with low overhead.

Requires: psutil (for process lookup). Optionally ctypes WinAPI (standard).

Profiles: provide a dict of process name -> addresses/scales. This module ships
with an empty example; user can add real addresses in a JSON later.
"""
from __future__ import annotations

import threading, time, platform
from typing import Optional, Dict

try:
    import psutil  # type: ignore
except Exception:
    psutil = None  # type: ignore

if platform.system().lower() == 'windows':
    import ctypes
    from ctypes import wintypes
else:
    ctypes = None


class MemoryScanManager:
    def __init__(self, profile: Optional[Dict]=None, poll_hz: float = 30.0):
        self.enabled = (platform.system().lower() == 'windows' and psutil is not None and ctypes is not None)
        self._prof = profile or {}
        self._lock = threading.Lock()
        self._vals: Dict[str, float] = { 'speed01':0.0, 'absGate':0.0, 'slipGate':0.0, 'impact':0.0 }
        self._stop = threading.Event()
        self._th: Optional[threading.Thread] = None
        self._poll_dt = 1.0 / max(5.0, min(120.0, float(poll_hz)))
        if self.enabled and self._prof:
            self._th = threading.Thread(target=self._run, daemon=True)
            self._th.start()

    def close(self):
        self._stop.set()

    def get(self) -> Dict[str,float]:
        with self._lock:
            return dict(self._vals)

    # ---- internals ----
    def _find_proc(self, name_substr: str):
        try:
            for p in psutil.process_iter(['name']):
                n = (p.info.get('name') or '').lower()
                if name_substr in n:
                    return p
        except Exception:
            return None
        return None

    def _read_float(self, handle, addr) -> Optional[float]:
        try:
            buf = ctypes.create_string_buffer(4)
            nread = wintypes.SIZE_T()
            if ctypes.windll.kernel32.ReadProcessMemory(handle, ctypes.c_void_p(addr), buf, 4, ctypes.byref(nread)):
                if nread.value == 4:
                    return ctypes.c_float.from_buffer_copy(buf).value
        except Exception:
            return None
        return None

    def _run(self):
        prof = self._prof
        proc_sub = str(prof.get('process','')).lower()
        if not proc_sub:
            return
        PROCESS_VM_READ = 0x0010
        PROCESS_QUERY_INFORMATION = 0x0400
        handle = None
        pid = None
        try:
            while not self._stop.is_set():
                if handle is None:
                    p = self._find_proc(proc_sub)
                    if p is not None:
                        try:
                            pid = p.pid
                            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_INFORMATION, False, pid)
                        except Exception:
                            handle = None
                vals = {'speed01':0.0,'absGate':0.0,'slipGate':0.0,'impact':0.0}
                if handle:
                    try:
                        # Example addresses, to be customized per game/profile
                        a_speed = prof.get('addr_speed')
                        a_abs   = prof.get('addr_abs')
                        a_slip  = prof.get('addr_slip')
                        a_imp   = prof.get('addr_impact')
                        if isinstance(a_speed, int):
                            v = self._read_float(handle, a_speed)
                            if v is not None:
                                vals['speed01'] = max(0.0, min(1.0, v / max(1e-3, float(prof.get('speed_norm', 80.0)))))
                        if isinstance(a_abs, int):
                            v = self._read_float(handle, a_abs)
                            if v is not None:
                                vals['absGate'] = 1.0 if v > float(prof.get('abs_thresh', 0.5)) else 0.0
                        if isinstance(a_slip, int):
                            v = self._read_float(handle, a_slip)
                            if v is not None:
                                vals['slipGate'] = 1.0 if v > float(prof.get('slip_thresh', 0.5)) else 0.0
                        if isinstance(a_imp, int):
                            v = self._read_float(handle, a_imp)
                            if v is not None:
                                vals['impact'] = max(0.0, min(1.0, v))
                    except Exception:
                        pass
                with self._lock:
                    self._vals = vals
                time.sleep(self._poll_dt)
        finally:
            try:
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
            except Exception:
                pass

