# Wheeler DriverKit Virtual Gamepad

This directory contains a DriverKit-based virtual gamepad driver for macOS that creates a true HID gamepad device, providing superior compatibility compared to keyboard/mouse simulation.

## Overview

The Wheeler DriverKit extension creates a virtual Xbox-style gamepad that appears as a real HID device to macOS and applications. This provides:

- **True gamepad device**: Appears as a real gamepad in System Information and games
- **Full compatibility**: Works with all games that support gamepads
- **Force feedback support**: Framework for implementing haptic feedback (future enhancement)
- **System-level integration**: Proper HID device with standard gamepad descriptors

## Requirements

### Development Requirements
- **macOS 13.0+** (Ventura or later)
- **Xcode 14.0+** with Command Line Tools
- **Apple Developer Account** (required for code signing)
- **Developer ID certificate** installed in Keychain

### Runtime Requirements
- **macOS 13.0+** (Ventura or later)
- **System Integrity Protection (SIP)** may need to be configured for development
- **Administrator privileges** for installation

## Project Structure

```
DriverKit/
├── WheelerGamepadDriver/
│   ├── WheelerGamepadDriver.xcodeproj/    # Xcode project
│   └── WheelerGamepadDriver/              # Source code
│       ├── WheelerGamepadDriver.h         # Header file
│       ├── WheelerGamepadDriver.cpp       # Implementation
│       ├── Info.plist                     # Extension metadata
│       └── WheelerGamepadDriver.entitlements # Required entitlements
├── build_and_install.sh                   # Build and install script
└── README.md                              # This file
```

## Building and Installation

### Step 1: Configure Developer Account

1. **Obtain Apple Developer Account**: Sign up at [developer.apple.com](https://developer.apple.com)

2. **Install Developer Certificate**:
   - Download your Developer ID certificate from the Apple Developer portal
   - Double-click to install in Keychain Access
   - Verify installation: `security find-identity -v -p codesigning`

3. **Update Team ID**:
   - Open `WheelerGamepadDriver.xcodeproj` in Xcode
   - Select the project in the navigator
   - In "Signing & Capabilities", set your Team ID
   - Replace `YOUR_TEAM_ID` in the project settings

### Step 2: Build and Install

Run the automated build and install script:

```bash
cd DriverKit
./build_and_install.sh
```

This script will:
1. Build the DriverKit extension using Xcode
2. Copy the extension to `/Library/SystemExtensions/`
3. Load the extension using `systemextensionsctl`

### Step 3: System Approval

1. **System Extension Approval**:
   - Go to System Preferences → Security & Privacy → General
   - Click "Allow" when prompted for the Wheeler extension
   - You may need to restart after approval

2. **Verify Installation**:
   ```bash
   systemextensionsctl list
   ```
   Look for `com.wheeler.gamepad.driver` in the output

## Usage

Once installed, the DriverKit extension will be automatically used by the Wheeler Host application when running on macOS. The application will log:

```
Using DriverKit bridge for macOS
```

### Testing the Extension

Test the DriverKit bridge directly:

```bash
cd /path/to/WheelerHost-V1
python3 driverkit_gamepad_bridge.py
```

This will test communication with the extension and send sample gamepad states.

### Verifying Gamepad Device

Check that the virtual gamepad appears in System Information:

1. Hold Option and click Apple menu → System Information
2. Navigate to Hardware → USB
3. Look for "Wheeler Virtual Gamepad" device

## Architecture

### DriverKit Extension (`WheelerGamepadDriver`)

The extension consists of two main classes:

1. **`WheelerGamepadDriver`**: Main HID device driver
   - Inherits from `IOHIDDevice`
   - Provides HID report descriptor for Xbox-style gamepad
   - Handles input report generation
   - Manages device properties and metadata

2. **`WheelerGamepadUserClient`**: User-space communication interface
   - Inherits from `IOUserClient`
   - Provides methods for updating gamepad state from user-space
   - Handles communication between Python application and kernel extension

### Python Interface (`driverkit_gamepad_bridge.py`)

The Python bridge communicates with the DriverKit extension using IOKit:

- **IOKit Communication**: Uses `IOConnectCallStructMethod` for sending gamepad state
- **State Management**: Converts Wheeler gamepad format to HID report format
- **Error Handling**: Graceful fallback when extension is not available

### HID Report Descriptor

The extension implements a standard Xbox-style gamepad with:

- **Analog Sticks**: Left stick (X/Y), Right stick (Rx/Ry)
- **Triggers**: Left trigger (Z), Right trigger (Rz)
- **Buttons**: 16 digital buttons (A, B, X, Y, LB, RB, etc.)
- **D-Pad**: 8-direction hat switch

## Troubleshooting

### Build Issues

**"No Developer ID certificate found"**:
- Ensure you have an Apple Developer account
- Download and install your Developer ID certificate
- Update the DEVELOPMENT_TEAM in Xcode project settings

**"Build failed"**:
- Check Xcode version (14.0+ required)
- Verify macOS version (13.0+ required)
- Ensure all entitlements are properly configured

### Installation Issues

**"Operation not permitted"**:
- Run with `sudo` for system extension operations
- Check System Integrity Protection status: `csrutil status`
- For development, you may need to disable some SIP protections

**"Extension not loading"**:
- Check system extension status: `systemextensionsctl list`
- Look for approval prompts in System Preferences
- Check Console.app for system extension logs

### Runtime Issues

**"DriverKit extension not found"**:
- Verify extension is loaded: `systemextensionsctl list`
- Check that the bundle identifier matches: `com.wheeler.gamepad.driver`
- Ensure the extension has been approved in System Preferences

**"Failed to open connection"**:
- Verify the extension is running and approved
- Check that the IOKit service is available
- Look for permission issues in Console.app

## Development Notes

### Debugging

1. **System Logs**: Use Console.app to view system extension logs
2. **IOKit Debugging**: Use `ioreg` to inspect the device tree
3. **HID Testing**: Use tools like "USB Prober" or "IORegistryExplorer"

### Customization

To modify the gamepad characteristics:

1. **HID Descriptor**: Edit `kHIDReportDescriptor` in `WheelerGamepadDriver.cpp`
2. **Device Properties**: Modify `newDeviceDescription()` method
3. **Report Format**: Update `HIDInputReport` structure and `sendInputReport()` method

### Force Feedback

The framework for force feedback is in place but not fully implemented:

1. **Output Reports**: Handle in `setReport()` method
2. **Callback System**: Extend user client interface
3. **Python Integration**: Add force feedback methods to bridge

## Uninstallation

To remove the DriverKit extension:

```bash
# Unload the extension
sudo systemextensionsctl uninstall com.wheeler.gamepad.driver

# Remove files (optional)
sudo rm -rf /Library/SystemExtensions/WheelerGamepadDriver.dext
```

## Security Considerations

- **Code Signing**: Required for all DriverKit extensions
- **Entitlements**: Minimal required entitlements for HID device access
- **System Approval**: User must explicitly approve the extension
- **Sandboxing**: DriverKit extensions run in a restricted environment

## Future Enhancements

1. **Force Feedback**: Implement haptic feedback support
2. **Multiple Devices**: Support for multiple virtual gamepads
3. **Customizable HID**: Runtime-configurable gamepad characteristics
4. **Advanced Features**: Gyroscope, accelerometer simulation
5. **GUI Configuration**: Xcode-based configuration utility

## License

This DriverKit extension is part of the Wheeler Host project and follows the same licensing terms.