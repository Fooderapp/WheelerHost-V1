# xinput_bridge_proc.py
# Launches ViGEmBridge.exe and talks over STDIN/STDOUT (no sockets).
import subprocess, threading, json, os, sys, shutil

class XInputBridgeProc:
    def __init__(self, exe_path=None, target: str = "x360"):
        # Resolve bridge exe
        exe = exe_path or self._default_path()
        if not exe or not os.path.isfile(exe):
            raise RuntimeError("ViGEmBridge.exe not found. Pass exe_path or place it next to this script.")
        self._exe = exe
        self._p = None
        self._ffb_cb = None
        self._target = (target or "x360").lower().strip()
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
        # Send target selection as control message if not default
        try:
            if self._p and self._p.stdin and self._target in ("x360","ds4"):
                self._p.stdin.write(json.dumps({"type":"target","value": self._target}) + "\n")
                self._p.stdin.flush()
        except Exception:
            pass

    def set_target(self, target: str):
        t = (target or "").strip().lower()
        if t not in ("x360", "ds4"):
            return
        self._target = t
        try:
            if self._p and self._p.stdin:
                self._p.stdin.write(json.dumps({"type":"target","value": t}) + "\n")
                self._p.stdin.flush()
        except Exception:
            pass

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
                    def _val(keys, default=0.0):
                        for k in keys:
                            if k in obj:
                                try:
                                    return float(obj.get(k, default))
                                except Exception:
                                    pass
                        return float(default)

                    # Try a variety of known keys from possible bridges
                    L = _val(["rumbleL","leftMotor","rumble_left","L","l"])  # main left motor
                    R = _val(["rumbleR","rightMotor","rumble_right","R","r"]) # main right motor
                    LT = _val(["rumbleLT","leftTrigger","lt"])                 # impulse trigger left
                    RT = _val(["rumbleRT","rightTrigger","rt"])                # impulse trigger right

                    # Normalize to 0..1 if large (e.g., 0..65535)
                    def _norm(x):
                        x = float(x)
                        if x < 0: x = 0.0
                        # Heuristic normalization for typical ranges
                        if x > 1.0:
                            if x <= 255.0:
                                x = x / 255.0
                            else:
                                x = x / 65535.0
                        if x > 1.0: x = 1.0
                        return x

                    L = _norm(L); R = _norm(R); LT = _norm(LT); RT = _norm(RT)

                    # If main motors are zero but triggers are active, map triggers into channels
                    if L <= 0.0 and R <= 0.0 and (LT > 0.0 or RT > 0.0):
                        # Bias triggers to the right/high channel by default
                        L = max(L, LT * 0.5)
                        R = max(R, RT * 0.8)
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
