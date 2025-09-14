User-space HID Gamepad for macOS (Sequoia-compatible)

This tool creates a virtual HID Gamepad entirely in user-space using IOHIDUserDevice.
No DriverKit or special entitlements are required, so it works on macOS Sequoia
for testing and development.

Features
- Appears as a standard Gamepad (Generic Desktop → Game Pad)
- 16 buttons + 4 analog axes (LX, LY, RX, RY; 0..255)
- Demo mode toggles a button so you can verify in games/`Game Controllers` panel
- Optional UDP listener to drive inputs from another app/device

Build
- Requires Xcode command line tools
- From this folder:
  swift build -c release

Run
- Demo mode (toggles A button every second):
  .build/release/UserHIDGamepad --demo

- UDP mode (listen on 12000 for JSON):
  .build/release/UserHIDGamepad --udp 12000

  JSON format (example):
  {"buttons": 1, "lx": 0.0, "ly": 0.0, "rx": 0.0, "ry": 0.0}
  - buttons: 16-bit bitmask (LSB bit = A)
  - lx, ly, rx, ry: floats in [-1.0, 1.0]

Notes
- This is HID-only (not XInput). Most macOS games and apps recognize HID gamepads.
- Use alongside the Windows ViGEm fallback for XInput-specific testing.

