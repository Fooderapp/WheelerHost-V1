# dk_bridge_proc.py
# Launches a local DriverKit bridge (WheelerDKBridge) and talks over STDIN/STDOUT JSON.
# This mirrors xinput_bridge_proc.py so udp_server.py can remain mostly unchanged.

import os, json, subprocess, threading

class DKBridgeProc:
    def __init__(self, exe_path=None):
        exe = exe_path or os.environ.get("DK_BRIDGE_EXE") or self._default_path()
        if not exe or not os.path.isfile(exe):
            raise RuntimeError("WheelerDKBridge executable not found. Build the mac helper and set DK_BRIDGE_EXE or pass exe_path.")
        self._exe = exe
        self._p = None
        self._ffb_cb = None
        self._start()

    def _default_path(self):
        # Common product locations; adjust as needed
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.abspath(os.path.join(here, os.pardir))
        cands = [
            # Xcode new default when using custom build dir
            os.path.join(root, "WheelerHost-mac", "build", "Release", "WheelerDKBridge"),
            os.path.join(root, "WheelerHost-mac", "build", "Debug", "WheelerDKBridge"),
            # Legacy DerivedData-style within project
            os.path.join(root, "WheelerHost-mac", "Build", "Products", "Release", "WheelerDKBridge"),
            os.path.join(root, "WheelerHost-mac", "Build", "Products", "Debug", "WheelerDKBridge"),
        ]
        for p in cands:
            if os.path.isfile(p):
                return p
        return None

    def _start(self):
        self._p = subprocess.Popen(
            [self._exe],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # surface helper diagnostics
            text=True,
            bufsize=1,
        )
        self._th = threading.Thread(target=self._read_stdout, daemon=True)
        self._th.start()

    def set_feedback_callback(self, cb):
        self._ffb_cb = cb

    def _read_stdout(self):
        if not self._p or not self._p.stdout: return
        for line in self._p.stdout:
            line = line.strip()
            if not line:
                continue
            # Handle both JSON messages and plain text
            if line.startswith('{'):
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and obj.get("type") == "ffb":
                        L = float(obj.get("rumbleL", 0.0))
                        R = float(obj.get("rumbleR", 0.0))
                        if self._ffb_cb:
                            self._ffb_cb(L, R)
                    elif isinstance(obj, dict) and obj.get("type") in ("info","warn","error"):
                        # Bubble up helper status messages
                        note = obj.get("note", "")
                        msg_type = obj.get("type", "info")
                        print(f"[dkbridge] {msg_type.upper()}: {note}")
                        
                        # Log important status changes
                        if "GameController" in note:
                            print(f"[dkbridge] Using GameController fallback - virtual gamepad should be visible in System Preferences")
                        elif "DriverKit user client connected" in note:
                            print(f"[dkbridge] DriverKit connection successful - using native HID device")
                except Exception as e:
                    print(f"[dkbridge] JSON parse error: {e}")
            else:
                # Handle non-JSON output (debugging info, etc.)
                print(f"[dkbridge] {line}")

    def send_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int, hat: int = 8):
        if not self._p or not self._p.stdin: return
        pkt = {
            "lx": float(max(-1.0, min(1.0, lx))),
            "ly": float(max(-1.0, min(1.0, ly))),
            "rt": int(max(0, min(255, rt))),
            "lt": int(max(0, min(255, lt))),
            "buttons": int(btn_mask) & 0xFFF,
            "hat": int(max(0, min(8, hat)))
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
