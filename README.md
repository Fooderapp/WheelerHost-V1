Wheeler Python Host

Cross‑platform host that accepts telemetry over UDP from the phone, shows a UI/overlay, and forwards inputs to a local gamepad bridge (DriverKit on macOS or ViGEm/vJoy on Windows). Default UDP port: `8765`.

Quick Start (macOS)
- Prereqs: Python 3.10+ and Xcode command line tools.
- Build the mac helper binary `WheelerDKBridge` in Xcode:
  - Open `WheelerHost-mac/WheelerMacHost.xcodeproj`.
  - Select target `WheelerDKBridge` (Swift console app) and build `Debug` (or `Release`).
  - Approve and activate the DriverKit extension via the Setup app if prompted (you already did this).
- Ensure the Python host can find `WheelerDKBridge`:
  - Default search paths (first match wins):
    - `WheelerHost-mac/Build/Products/Release/WheelerDKBridge`
    - `WheelerHost-mac/Build/Products/Debug/WheelerDKBridge`
  - If your build ends up under `WheelerHost-mac/build/Debug/…`, set an env var:
    - `export DK_BRIDGE_EXE="../WheelerHost-mac/build/Debug/WheelerDKBridge"`
- Install Python deps and run:
  - `cd WheelerHost-V1`
  - `bash ./run_mac.sh`
- In the UI, the top‑left shows your LAN `IP:8765` and displays QR codes. Point the phone app to that endpoint.

Quick Start (Windows)
- Prereqs: Python 3.10+, Visual C++ Runtime.
- Preferred bridge: ViGEm
  - Build or obtain `ViGEmBridge.exe` (the small console bridge in this repo). Place it next to `wheeler_main.py` or under `ViGEmBridge\bin\Release\net8.0\`.
  - Alternatively, install vJoy + `pyvjoy` for a DirectInput fallback (no force feedback backchannel).
- Install Python deps and run:
  - `cd WheelerHost-V1`
  - `run_win.bat`

Phone ↔ Host Protocol
- Phone sends JSON packets with `sig:"WHEEL1"`, axes, buttons, and a `seq` counter.
- Host replies with JSON including `ack`, `rumbleL/R` (real game FFB if available), and `center`.

Controls & Debug
- Overlay: F9 toggles visibility, F11 resets layout (Windows global hotkeys; on macOS use the main UI buttons).
- UI checkboxes let you toggle passthrough‑only rumble, hybrid synth, and other debug behaviors.
- Logs stream in the right‑side pane; real force feedback events log as they arrive from the game.

Troubleshooting
- No gamepad movement in game:
  - macOS: Confirm the DriverKit dext shows as “activated enabled” in `systemextensionsctl list` and run the Setup app once if needed. Ensure `DK_BRIDGE_EXE` points to the built `WheelerDKBridge`.
  - Windows: Ensure `ViGEmBridge.exe` is present. If missing, install vJoy and `pip install pyvjoy` for fallback.
- Phone can’t connect: Verify the host IP and that nothing else is bound to UDP `:8765`.

