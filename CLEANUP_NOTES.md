Windows + mac cleanup summary (2025-09-10)

Changes made per request:

- Windows: reverted to ViGEm as the only supported bridge
  - Removed experimental KMDF Custom HID driver scaffold under `WindowsCustomHID/`
  - Default Windows flow remains `vigem_bridge.py` (or vJoy fallback if installed)

- macOS: focus on DriverKit solution
  - Removed user-space IOHIDUserDevice test tool under `macos/UserHIDGamepad/`
  - Keep existing DriverKit projects and bridges as primary mac path

- Force feedback passthrough
  - Fixed `vigem_bridge.py` to normalize ViGEmBridge.exe FFB output and call the server callback as `(left,right)` floats in [0,1]

Notes
- If you need the removed code, recover via git history.
- Docs already point Windows to ViGEm and macOS to DriverKit.

