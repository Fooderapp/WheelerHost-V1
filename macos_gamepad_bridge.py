"""
MacOSGamepadBridge

Lightweight cross-platform bridge for macOS using keyboard/mouse simulation.
This is a fallback when DriverKit is unavailable. It is NOT a real gamepad.

Requirements (macOS):
- pip install pynput pyautogui
- Grant Accessibility permission to Terminal/Python in System Settings

Interface compatible with ViGEm/vJoy bridges used by udp_server.py.
"""

from __future__ import annotations

import time
from typing import Optional
import platform
from ctypes import util, cdll, c_void_p, c_bool, c_uint16, c_uint32

try:
    from pynput import keyboard, mouse
except Exception as e:  # pragma: no cover
    keyboard = None  # type: ignore
    mouse = None     # type: ignore
    _IMPORT_ERR = e
else:
    _IMPORT_ERR = None


class MacOSGamepadBridge:
    def __init__(self):
        if keyboard is None or mouse is None:
            raise RuntimeError("Cross-platform bridge not available: install pynput and grant Accessibility permissions")

        self._kb = keyboard.Controller()
        self._mouse = mouse.Controller()
        self._ffb_cb = None

        # State to avoid key spam
        self._down = {
            'w': False, 's': False,
            'a': False, 'd': False,
            'space': False, 'x': False, 'z': False, 'c': False,
            'q': False, 'e': False,
            'enter': False, 'esc': False,
        }

        # Config
        self._thresh = 0.15          # trigger threshold (W/S)
        
        # A/D push‑rate steering (keyboard pulsing)
        self._steer_deadband = 0.12   # ignore tiny lx wiggles
        self._tap_min_hz = 3.0        # gentle steer tap rate at threshold
        self._tap_max_hz = 15.0       # fully steered constant tap rate (A)
        self._tap_hold_ms = 22        # how long each tap is held down

        # Internal tap scheduling state
        now_ms = int(time.time() * 1000)
        self._last_tap_ms = {'a': now_ms, 'd': now_ms}
        self._tap_release_ms = {'a': 0, 'd': 0}

        # Generic pulse scheduling for face/shoulder buttons (NOT W/S; W/S should be true holds)
        self._pulse_keys = ['space','x','z','c','q','e','enter','esc']
        self._pulse_last_ms = {k: now_ms for k in self._pulse_keys}
        self._pulse_release_ms = {k: 0 for k in self._pulse_keys}
        self._pulse_hz_ws = 15.0     # throttle/brake pulse frequency
        self._pulse_hz_btn = 12.0    # other buttons pulse frequency
        self._pulse_hold_ms = 24     # pulse down time

        # macOS CGEvent fallback for better app compatibility (e.g., GeForce NOW)
        self._use_cgevent = (platform.system() == 'Darwin')
        self._cg = None
        self._cf = None
        self._cg_source = None
        if self._use_cgevent:
            try:
                app_svc = util.find_library('ApplicationServices') or util.find_library('CoreGraphics')
                core_found = util.find_library('CoreFoundation')
                if app_svc:
                    self._cg = cdll.LoadLibrary(app_svc)
                if core_found:
                    self._cf = cdll.LoadLibrary(core_found)
                # Configure function signatures and create a shared source
                if self._cg is not None:
                    # CGEventSourceCreate
                    self._cg.CGEventSourceCreate.restype = c_void_p
                    self._cg.CGEventSourceCreate.argtypes = [c_uint32]
                    # kCGEventSourceStateCombinedSessionState = 1
                    self._cg_source = self._cg.CGEventSourceCreate(c_uint32(1))
                    # CGEventCreateKeyboardEvent
                    self._cg.CGEventCreateKeyboardEvent.restype = c_void_p
                    self._cg.CGEventCreateKeyboardEvent.argtypes = [c_void_p, c_uint16, c_bool]
                    # CGEventPost
                    self._cg.CGEventPost.restype = None
                    self._cg.CGEventPost.argtypes = [c_uint32, c_void_p]
                if self._cf is not None:
                    self._cf.CFRelease.restype = None
                    self._cf.CFRelease.argtypes = [c_void_p]
            except Exception:
                self._cg = None; self._cf = None

    def set_feedback_callback(self, cb):
        # No real FFB on this bridge; keep for API compatibility
        self._ffb_cb = cb

    # Map VX360 order (A,B,X,Y,LB,RB,Start,Back, DPadUp, DPadDown, DPadLeft, DPadRight)
    def _key_for_button_index(self, idx: int) -> Optional[str]:
        mapping = {
            0: 'space',  # A
            1: 'x',      # B
            2: 'z',      # X
            3: 'c',      # Y
            4: 'q',      # LB
            5: 'e',      # RB
            6: 'enter',  # Start
            7: 'esc',    # Back
        }
        return mapping.get(idx)

    def _press(self, keyname: str):
        if self._down.get(keyname, False):
            return
        self._down[keyname] = True
        # Post via pynput
        k = self._to_key(keyname)
        if k is not None:
            try:
                self._kb.press(k)
            except Exception:
                pass
        # Post via CGEvent (more compatible with some apps)
        self._cg_post(keyname, True)

    def _release(self, keyname: str):
        if not self._down.get(keyname, False):
            return
        self._down[keyname] = False
        # Release via pynput
        k = self._to_key(keyname)
        if k is not None:
            try:
                self._kb.release(k)
            except Exception:
                pass
        # Release via CGEvent
        self._cg_post(keyname, False)

    def _to_key(self, keyname: str):
        Key = keyboard.Key
        if keyname == 'space': return Key.space
        if keyname == 'enter': return Key.enter
        if keyname == 'esc':   return Key.esc
        # single letters
        if len(keyname) == 1:
            return keyname
        return None

    def _vk_for_key(self, keyname: str) -> Optional[int]:
        # US keyboard layout virtual keycodes
        mapping = {
            'a': 0, 's': 1, 'd': 2, 'q': 12, 'w': 13, 'e': 14,
            'z': 6, 'x': 7, 'c': 8,
            'space': 49, 'enter': 36, 'esc': 53,
        }
        return mapping.get(keyname)

    def _cg_post(self, keyname: str, down: bool):
        if not self._use_cgevent or self._cg is None:
            return
        try:
            vk = self._vk_for_key(keyname)
            if vk is None:
                return
            source = self._cg_source if self._cg_source else c_void_p(0)
            evt = self._cg.CGEventCreateKeyboardEvent(source, c_uint16(vk), c_bool(bool(down)))
            if evt:
                # 0 = kCGHIDEventTap
                self._cg.CGEventPost(c_uint32(0), evt)
                if self._cf is not None:
                    self._cf.CFRelease(evt)
        except Exception:
            pass

    def send_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int):
        now_ms = int(time.time() * 1000)

        # --- Steering: A/D push‑rate taps ---
        try:
            lx_clamped = max(-1.0, min(1.0, float(lx)))
            mag = abs(lx_clamped)
            target = None
            if mag > self._steer_deadband:
                target = 'd' if lx_clamped > 0 else 'a'
            if target is not None:
                frac = (mag - self._steer_deadband) / max(1e-6, (1.0 - self._steer_deadband))
                frac = max(0.0, min(1.0, frac))
                hz = self._tap_min_hz + frac * (self._tap_max_hz - self._tap_min_hz)
                period_ms = 1000.0 / max(1e-3, hz)
                if self._tap_release_ms[target] == 0 and (now_ms - self._last_tap_ms[target]) >= period_ms:
                    self._press(target)
                    self._tap_release_ms[target] = now_ms + self._tap_hold_ms
                    self._last_tap_ms[target] = now_ms
            # Timed releases for both keys
            for k in ('a','d'):
                rel = self._tap_release_ms[k]
                if rel and now_ms >= rel:
                    self._release(k)
                    self._tap_release_ms[k] = 0
        except Exception:
            pass

        # --- Triggers: hold W/S while active (constant press) ---
        try:
            rt_on = int(rt) > 0
            lt_on = int(lt) > 0
            if rt_on: self._press('w')
            else:     self._release('w')
            if lt_on: self._press('s')
            else:     self._release('s')
        except Exception:
            pass

        # --- Face/shoulder buttons: pulse while active ---
        try:
            for i in range(8):
                on = (btn_mask & (1 << i)) != 0
                keyname = self._key_for_button_index(i)
                if not keyname:
                    continue
                if on:
                    self._schedule_pulse(keyname, now_ms, self._pulse_hz_btn, self._pulse_hold_ms)
                else:
                    self._cancel_pulse(keyname)
            # Release any pulses due (includes W/S)
            self._tick_pulse_releases(now_ms)
        except Exception:
            pass

    # Optional setters for tests/tuning
    def set_ad_pushrate(self, deadband: Optional[float] = None, min_hz: Optional[float] = None, max_hz: Optional[float] = None, hold_ms: Optional[int] = None):
        try:
            if deadband is not None:
                self._steer_deadband = max(0.0, min(0.5, float(deadband)))
        except Exception:
            pass
        try:
            if min_hz is not None:
                self._tap_min_hz = max(0.1, float(min_hz))
        except Exception:
            pass
        try:
            if max_hz is not None:
                self._tap_max_hz = max(self._tap_min_hz, float(max_hz))
        except Exception:
            pass
        try:
            if hold_ms is not None:
                self._tap_hold_ms = max(1, int(hold_ms))
        except Exception:
            pass

        

    def close(self):  # best effort: release keys
        for k in list(self._down.keys()):
            self._release(k)
        time.sleep(0.002)

    # ----- pulse helpers -----
    def _schedule_pulse(self, key: str, now_ms: int, hz: float, hold_ms: int):
        if key not in self._pulse_last_ms:
            return
        if self._pulse_release_ms.get(key, 0) == 0:
            period = 1000.0 / max(0.1, hz)
            if (now_ms - self._pulse_last_ms[key]) >= period:
                self._press(key)
                self._pulse_release_ms[key] = now_ms + int(hold_ms)
                self._pulse_last_ms[key] = now_ms

    def _cancel_pulse(self, key: str):
        try:
            if self._pulse_release_ms.get(key, 0) != 0:
                # ensure release happens soon
                self._pulse_release_ms[key] = 1
            else:
                self._release(key)
        except Exception:
            pass

    def _tick_pulse_releases(self, now_ms: int):
        try:
            for k in self._pulse_keys:
                rel = self._pulse_release_ms.get(k, 0)
                if rel and now_ms >= rel:
                    self._release(k)
                    self._pulse_release_ms[k] = 0
        except Exception:
            pass
