# xinput_bridge.py
# Local UDP bridge to ViGEmBridge.exe on Windows.
# Sends inputs to 127.0.0.1:27700 and listens for FFB on 127.0.0.1:27701.

import socket, json, threading

class XInputBridge:
    def __init__(self, send_port=27700, recv_port=27701):
        self._send_ep = ("127.0.0.1", int(send_port))
        self._recv_port = int(recv_port)
        self._sock_send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self._sock_recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock_recv.bind(("127.0.0.1", self._recv_port))
        self._sock_recv.settimeout(0.2)

        self._ffb_cb = None
        self._stop = threading.Event()
        self._th = threading.Thread(target=self._recv_loop, daemon=True)
        self._th.start()

    def set_feedback_callback(self, cb):
        """cb(L:float, R:float)"""
        self._ffb_cb = cb

    def _recv_loop(self):
        while not self._stop.is_set():
            try:
                data, _ = self._sock_recv.recvfrom(2048)
            except socket.timeout:
                continue
            except Exception:
                break
            try:
                s = data.decode("utf-8", "ignore")
                if not s or s[0] != "{": continue
                obj = json.loads(s)
                if isinstance(obj, dict) and obj.get("type") == "ffb":
                    def _val(keys, default=0.0):
                        for k in keys:
                            if k in obj:
                                try:
                                    return float(obj.get(k, default))
                                except Exception:
                                    pass
                        return float(default)
                    L = _val(["rumbleL","leftMotor","rumble_left","L","l"])  # main left
                    R = _val(["rumbleR","rightMotor","rumble_right","R","r"]) # main right
                    LT = _val(["rumbleLT","leftTrigger","lt"])                 # trigger left
                    RT = _val(["rumbleRT","rightTrigger","rt"])                # trigger right
                    def _norm(x):
                        x = float(x)
                        if x < 0: x = 0.0
                        if x > 1.0:
                            if x <= 255.0: x = x / 255.0
                            else: x = x / 65535.0
                        if x > 1.0: x = 1.0
                        return x
                    L = _norm(L); R = _norm(R); LT = _norm(LT); RT = _norm(RT)
                    if L <= 0.0 and R <= 0.0 and (LT > 0.0 or RT > 0.0):
                        L = max(L, LT * 0.5)
                        R = max(R, RT * 0.8)
                    if self._ffb_cb: self._ffb_cb(L, R)
            except Exception:
                pass

    def send_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int):
        """
        lx, ly: -1..1
        rt, lt: 0..255
        btn_mask: bit 0:A 1:B 2:X 3:Y 4:LB 5:RB 6:Start 7:Back 8:Up 9:Down 10:Left 11:Right
        """
        pkt = {
            "lx": float(lx),
            "ly": float(ly),
            "rt": int(max(0, min(255, rt))),
            "lt": int(max(0, min(255, lt))),
            "buttons": int(btn_mask) & 0xFFF
        }
        try:
            self._sock_send.sendto(json.dumps(pkt).encode("utf-8"), self._send_ep)
        except Exception:
            pass

    def close(self):
        self._stop.set()
        try: self._sock_recv.close()
        except Exception: pass
        try: self._sock_send.close()
        except Exception: pass
