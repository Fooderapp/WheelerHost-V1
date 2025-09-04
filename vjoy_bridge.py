# vjoy_bridge.py
# Simple bridge using vJoy (DirectInput) instead of ViGEm (XInput).
# Requires: vJoy driver installed and a Device ID=1 enabled with X,Y,Z,RZ axes and >=12 buttons.
# pip install pyvjoy

from typing import Optional

try:
    import pyvjoy  # type: ignore
except Exception as e:  # pragma: no cover
    pyvjoy = None  # type: ignore


class VJoyBridge:
    """Drop-in replacement exposing send_state(lx,ly,rt,lt,btn_mask) and set_feedback_callback.

    Notes:
    - vJoy provides no rumble feedback; set_feedback_callback() is accepted but never called.
    - Axes mapping: LX->X, LY->Y (inverted already at caller), RT->Z, LT->RZ.
    - Buttons mapping: bits 0..11 map to buttons 1..12.
    - POV: derive from D-Pad bits if a single direction is pressed, else neutral.
    """

    def __init__(self, device_id: int = 1):
        if pyvjoy is None:
            raise RuntimeError(
                "pyvjoy not available. Install vJoy driver and `pip install pyvjoy`."
            )
        try:
            self.j = pyvjoy.VJoyDevice(int(device_id))
        except Exception as e:  # pragma: no cover
            raise RuntimeError(f"Failed to open vJoy device {device_id}: {e}")
        self._ffb_cb = None

        # Precompute ranges
        self._AX_MIN = 1
        self._AX_MAX = 0x8000  # 32768

    def set_feedback_callback(self, cb):
        # vJoy can’t deliver FFB to us; accept to keep interface compatibility
        self._ffb_cb = cb

    # Helpers
    def _to_axis_centered(self, v: float) -> int:
        # v: -1..1 -> 1..32768
        v = float(max(-1.0, min(1.0, v)))
        # Map -1..1 to 0..1 then scale to 1..32768
        u = (v + 1.0) * 0.5
        out = int(self._AX_MIN + round(u * (self._AX_MAX - self._AX_MIN)))
        if out < self._AX_MIN: out = self._AX_MIN
        if out > self._AX_MAX: out = self._AX_MAX
        return out

    def _to_axis_trigger(self, v: int) -> int:
        # v: 0..255 -> 1..32768
        v = int(max(0, min(255, v)))
        u = v / 255.0
        out = int(self._AX_MIN + round(u * (self._AX_MAX - self._AX_MIN)))
        if out < self._AX_MIN: out = self._AX_MIN
        if out > self._AX_MAX: out = self._AX_MAX
        return out

    def _to_pov(self, mask: int) -> int:
        # vJoy POV in 1/100th deg: 0=Up, 9000=Right, 18000=Down, 27000=Left, 0xFFFFFFFF=neutral
        up = (mask & (1 << 8)) != 0
        down = (mask & (1 << 9)) != 0
        left = (mask & (1 << 10)) != 0
        right = (mask & (1 << 11)) != 0
        # Only handle cardinal singles; diagonals -> prefer horizontal then vertical deterministically
        if up and not (left or right or down):
            return 0
        if right and not (up or down or left):
            return 9000
        if down and not (left or right or up):
            return 18000
        if left and not (up or down or right):
            return 27000
        # Simple diagonal resolution
        if up and right:
            return 4500
        if right and down:
            return 13500
        if down and left:
            return 22500
        if left and up:
            return 31500
        return 0xFFFFFFFF

    def send_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int):
        try:
            # Axes
            self.j.set_axis(pyvjoy.HID_USAGE_X,  self._to_axis_centered(float(lx)))
            self.j.set_axis(pyvjoy.HID_USAGE_Y,  self._to_axis_centered(float(ly)))
            self.j.set_axis(pyvjoy.HID_USAGE_Z,  self._to_axis_trigger(int(rt)))
            self.j.set_axis(pyvjoy.HID_USAGE_RZ, self._to_axis_trigger(int(lt)))

            # Buttons 1..12 from bits 0..11
            mask = int(btn_mask) & 0xFFF
            for i in range(12):
                on = (mask >> i) & 1
                # vJoy buttons are 1-indexed
                self.j.set_button(i + 1, 1 if on else 0)

            # POV from D-Pad bits
            pov_val = self._to_pov(mask)
            try:
                self.j.set_cont_pov(pov_val, 1)  # POV #1
            except Exception:
                # Some vJoy builds expose only discrete POV, ignore
                pass
        except Exception:
            # Swallow exceptions to match ViGEm bridge behavior (non-fatal)
            pass

    def close(self):
        # Nothing to close for pyvjoy; leave device alive
        pass

