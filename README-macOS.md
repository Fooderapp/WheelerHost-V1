# Wheeler Host - macOS Sequoia Compatibility

This document describes the macOS Sequoia compatibility changes made to the Wheeler Host virtual gamepad application.

## Overview

Wheeler Host is a virtual gamepad application that receives input from a mobile phone via UDP and creates virtual gamepad input on the host system. The original version was Windows-only, using ViGEmBridge and vJoy. This update adds cross-platform support for macOS Sequoia and Linux.

## Platform Support

### Windows (Original)
- **ViGEmBridge**: Primary option for XInput gamepad emulation (Xbox 360/Xbox One controllers)
- **vJoy**: Fallback option for DirectInput gamepad emulation
- **Force Feedback**: Full support via ViGEmBridge

### macOS Sequoia (New)
- **Cross-Platform Bridge**: Uses pynput for keyboard/mouse input simulation
- **Input Mapping**: Gamepad input is mapped to keyboard keys and mouse movement
- **Force Feedback**: Simulated (no actual haptic feedback)

### Linux (New)
- **evdev Virtual Device**: Creates actual virtual gamepad using Linux input subsystem
- **Cross-Platform Bridge**: Fallback to keyboard/mouse simulation if evdev unavailable
- **Force Feedback**: Limited support

## Installation

### Prerequisites

#### All Platforms
```bash
pip install PySide6 qrcode pillow
```

#### macOS/Linux Additional Dependencies
```bash
pip install pynput pyautogui evdev
```

#### macOS Specific
On macOS, you may need to grant accessibility permissions to the terminal or Python application to allow input simulation.

1. Go to System Preferences → Security & Privacy → Privacy → Accessibility
2. Add Terminal.app or your Python executable to the list of allowed applications

## Usage

### Starting the Application

The application automatically detects the platform and uses the appropriate virtual gamepad bridge:

```bash
python3 wheeler_main.py
```

### Platform Detection

The application will log which bridge is being used:
- Windows: `ViGEmBridge-X360` or `vJoy`
- macOS: `CrossPlatform-Darwin`
- Linux: `CrossPlatform-Linux`

### Input Mapping (macOS)

When using the cross-platform bridge on macOS, gamepad input is mapped as follows:

| Gamepad Input | macOS Action |
|---------------|--------------|
| Left Stick X (Steering) | Mouse horizontal movement |
| Right Trigger (Throttle) | 'W' key |
| Left Trigger (Brake) | 'S' key |
| A Button | Spacebar |
| B Button | 'X' key |
| X Button | 'Z' key |
| Y Button | 'C' key |
| Start Button | Enter key |
| Back Button | Escape key |

### Input Mapping (Linux with evdev)

On Linux with evdev support, a true virtual gamepad device is created that appears as a standard game controller to applications.

## Technical Details

### Architecture Changes

1. **New Bridge System**: Added `MacOSGamepadBridge` class that provides the same interface as the Windows bridges
2. **Platform Detection**: Updated `UDPServer._init_bridge()` to detect the platform and select the appropriate bridge
3. **Graceful Fallback**: If the preferred bridge fails, the system falls back to alternatives

### File Changes

- `macos_gamepad_bridge.py`: New cross-platform virtual gamepad bridge
- `udp_server.py`: Updated bridge selection logic
- `test_bridge.py`: Test script for the new bridge

### Bridge Interface

All bridges implement the same interface:
```python
class GamepadBridge:
    def set_feedback_callback(self, callback):
        """Set callback for force feedback events"""
        
    def send_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int):
        """Send gamepad state to the system"""
        
    def close(self):
        """Clean up resources"""
```

## Limitations

### macOS Limitations
- No true gamepad device creation (uses keyboard/mouse simulation)
- Limited force feedback (no haptic feedback)
- Requires accessibility permissions
- Input mapping is fixed (not customizable through UI)

### Linux Limitations
- Requires `/dev/uinput` access for virtual gamepad creation
- May require running with elevated privileges in some configurations
- Force feedback support varies by system

## Troubleshooting

### macOS Issues

**"Permission denied" errors**:
- Grant accessibility permissions as described in Installation section

**Input not working in games**:
- The cross-platform bridge uses keyboard/mouse simulation, not true gamepad input
- Some games may not respond to keyboard input when expecting gamepad input

### Linux Issues

**"uinput module not loaded" error**:
```bash
sudo modprobe uinput
```

**Permission denied accessing /dev/uinput**:
```bash
sudo chmod 666 /dev/uinput
```
Or add your user to the `input` group:
```bash
sudo usermod -a -G input $USER
```

### General Issues

**Application won't start**:
- Ensure all dependencies are installed
- Check that PySide6 is properly installed
- On headless systems, set `QT_QPA_PLATFORM=offscreen`

## Development Notes

### Adding New Platforms

To add support for additional platforms:

1. Create a new bridge class implementing the standard interface
2. Add platform detection logic to `UDPServer._init_bridge()`
3. Import the new bridge class in `udp_server.py`

### Testing

Use the provided test script to verify bridge functionality:
```bash
python3 test_bridge.py
```

## Compatibility

- **Python**: 3.8+
- **macOS**: Tested on Sequoia (15.0+), should work on earlier versions
- **Linux**: Tested on Ubuntu/Debian, should work on most distributions
- **Windows**: Maintains full compatibility with original functionality

## Future Improvements

- Customizable input mapping for macOS
- Better force feedback simulation
- Support for additional gamepad types
- GUI configuration for cross-platform settings
- Native HID device creation on macOS