# xinput_bridge_proc.py
# Launches ViGEmBridge.exe and talks over STDIN/STDOUT (no sockets).
import subprocess, threading, json, os, sys, shutil

class XInputBridgeProc:
    def __init__(self, exe_path=None):
        # Resolve bridge exe
        exe = exe_path or self._default_path()
        if not exe or not os.path.isfile(exe):
            raise RuntimeError("ViGEmBridge.exe not found. Pass exe_path or place it next to this script.")
        self._exe = exe
        self._p = None
        self._ffb_cb = None
        self._start()

    def _default_path(self):
        here = os.path.dirname(os.path.abspath(__file__))
        # Try common spots
        candidates = [
            os.path.join(here, "ViGEmBridge.exe"),
            os.path.join(here, "ViGEmBridge", "bin", "Release", "net8.0", "ViGEmBridge.exe"),
            os.path.join(here, "ViGEmBridge", "bin", "Release", "net7.0", "ViGEmBridge.exe"),
            os.path.join(here, "ViGEmBridge", "bin", "Release", "net6.0", "ViGEmBridge.exe"),
        ]
        for p in candidates:
            if os.path.isfile(p): return p
        return None

    def _start(self):
        # Hide console window on Windows
        creationflags = 0
        if os.name == "nt":
            creationflags = 0x08000000  # CREATE_NO_WINDOW

        self._p = subprocess.Popen(
            [self._exe],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            creationflags=creationflags
        )
        self._th = threading.Thread(target=self._read_stdout, daemon=True)
        self._th.start()

    def set_feedback_callback(self, cb):
        """cb(L:float, R:float)"""
        self._ffb_cb = cb

    def _read_stdout(self):
        if not self._p or not self._p.stdout: return
        for line in self._p.stdout:
            line = line.strip()
            if not line or line[0] != '{': continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict) and obj.get("type") == "ffb":
                    L = float(obj.get("rumbleL", 0.0))
                    R = float(obj.get("rumbleR", 0.0))
                    if self._ffb_cb: self._ffb_cb(L, R)
            except Exception:
                pass

    def send_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int):
        if not self._p or not self._p.stdin: return
        pkt = {
            "lx": float(lx),
            "ly": float(ly),
            "rt": int(max(0, min(255, rt))),
            "lt": int(max(0, min(255, lt))),
            "buttons": int(btn_mask) & 0xFFF
        }
        try:
            self._p.stdin.write(json.dumps(pkt) + "\n")
            self._p.stdin.flush()
        except Exception:
            pass

    def close(self):
        try:
            if self._p and self._p.stdin:
                self._p.stdin.close()
        except Exception:
            pass
        try:
            if self._p:
                self._p.terminate()
        except Exception:
            pass
