vJoy Bridge (ViGEm Alternative)

If ViGEmBus is unavailable, you can use vJoy + pyvjoy to emulate a DirectInput gamepad. Many games accept DirectInput or you can pair vJoy with x360ce to present an XInput pad.

Install

- Install vJoy driver and create Device ID 1 with axes X, Y, Z, RZ and at least 12 buttons.
- Python deps: `pip install pyvjoy PySide6 PySide6-Addons qrcode pillow`

Run

- Launch the Windows host (`wheeler_main.py` or `wheeler_windows_ui.py`). The server will try ViGEm first; if not found, it falls back to vJoy automatically.

Notes

- vJoy does not provide force feedback back to the app, so the phone will receive synthesized rumble based on telemetry when there’s no real FFB.
- To get XInput in games that require it, use x360ce to map the vJoy device to an emulated Xbox 360 controller per-game.

