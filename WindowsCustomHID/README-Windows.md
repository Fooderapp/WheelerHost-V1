Windows Virtual HID Gamepad (KMDF)

This adds a Windows KMDF virtual HID Gamepad driver and a simple user-mode tool.
It presents a standard HID Gamepad (Generic Desktop → Game Pad) with Xbox-like
layout for DirectInput/Raw HID consumers. For XInput-only apps, use ViGEm fallback.

Folders

- HIDDriver/   KMDF virtual HID miniport (INF + source + VS project)
- Tool/        C# console tool to send input frames to the driver

Requirements

- Windows 10 or newer, x64
- Visual Studio 2022
- Windows Driver Kit (WDK) for VS 2022
- Test signing enabled during development: run admin cmd then reboot
  bcdedit /set testsigning on

Build & Install

1) Open HIDDriver/CustomHID.sln in Visual Studio (WDK installed).
2) Build Release x64.
3) Install driver via INF: right-click CustomHID.inf → Install, or
   pnputil /add-driver CustomHID.inf /install
4) Device appears under Human Interface Devices as "Custom HID Gamepad".

Usage

- Run the Tool project to send gamepad states. The tool opens the driver's
  control device and issues IOCTLs to submit input reports; the driver then
  forwards those as HID Input reports to the HID stack.

VID/PID

- Development VID/PID used: 0x1234 / 0xABCD
- Update in CustomHID.inf and HIDAttributes in the driver if you want custom IDs.

Notes

- This implements HID, not XInput; for Xbox-controller emulation in XInput-only
  apps, continue using the existing ViGEm-based solution.

