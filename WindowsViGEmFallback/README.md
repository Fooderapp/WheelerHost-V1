# ViGEm Fallback (XInput emulation)

This folder documents the fallback solution using ViGEm (via the `vgamepad` Python
package) to emulate Xbox 360 controllers for XInput-only applications.

Existing, working code in this repo:
- `vigem_bridge.py` (core bridge)
- `wheeler_windows_ui.py` (UI + UDP + multi-client ViGEm wrappers) under `HIDGamepadDriver/`
- `requirements-win.txt` (Python deps on Windows)

Usage (Windows):
- Install Python 3.10+ and Visual C++ Redistributable
- `pip install -r requirements-win.txt`
- Run `python vigem_bridge.py` or the Windows UI in `HIDGamepadDriver/wheeler_windows_ui.py`

Notes:
- Keep this as a ready fallback if a native HID path is not acceptable for a given app.
- The new `WindowsCustomHID` driver provides a standard HID Gamepad device; many apps will
  work with HID directly. For XInput-only apps, use this ViGEm-based fallback.

