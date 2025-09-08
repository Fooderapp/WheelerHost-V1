# Wheeler Virtual Gamepad - Complete DriverKit Solution

A professional-grade virtual gamepad system for macOS Sequoia using DriverKit technology. This solution provides native HID gamepad functionality that works with any application expecting Xbox-style controller input.

## 🎮 Features

### Core Functionality
- **Native HID Gamepad**: Appears as a real Xbox controller to applications
- **DriverKit Technology**: Uses Apple's modern DriverKit framework for system-level integration
- **UDP Communication**: High-performance UDP protocol for real-time input
- **Cross-Platform Client**: Python client library works on macOS, Windows, and Linux
- **Professional Installation**: Automated installation with proper code signing

### Gamepad Capabilities
- **Analog Sticks**: Left and right analog sticks with full 16-bit precision
- **Triggers**: Left and right analog triggers (0-255 range)
- **Buttons**: 14 standard Xbox buttons (A, B, X, Y, bumpers, etc.)
- **D-Pad**: 8-direction digital pad
- **Force Feedback**: Ready for future force feedback implementation

### Wheeler-Specific Features
- **Steering Wheel Support**: Direct steering angle input (-900° to +900°)
- **Throttle/Brake**: Dedicated throttle and brake inputs
- **Button Mapping**: Flexible button mapping for racing applications
- **Real-time Updates**: Sub-millisecond latency for responsive gaming

## 📋 System Requirements

- **macOS**: 10.15 (Catalina) or later, optimized for macOS Sequoia
- **Xcode**: Command Line Tools or full Xcode installation
- **Apple Developer Account**: Required for code signing (free account works)
- **Python**: 3.7+ for client library
- **Administrator Access**: Required for system extension installation

## 🚀 Quick Start

### 1. Installation

```bash
# Clone or download the Wheeler Host repository
cd WheelerHost-V1/DriverKit

# Run the automated installer
./install_wheeler_gamepad.sh
```

The installer will:
- Build the DriverKit extension and daemon
- Install and activate the system extension
- Set up the background daemon
- Configure automatic startup

### 2. Verification

```bash
# Check installation status
./install_wheeler_gamepad.sh --status

# Test the gamepad
python3 wheeler_gamepad_client.py
```

### 3. Basic Usage

```python
from wheeler_gamepad_client import create_gamepad, GamepadButton

# Connect to the gamepad
gamepad = create_gamepad()

# Set steering angle (racing wheel style)
gamepad.set_steering(45.0)  # 45 degrees right

# Set throttle and brake
gamepad.set_throttle(0.8)   # 80% throttle
gamepad.set_brake(0.0)      # No brake

# Press buttons
gamepad.set_button(GamepadButton.A, True)   # Press A
gamepad.set_button(GamepadButton.A, False)  # Release A

# Disconnect when done
gamepad.disconnect()
```

## 🏗️ Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    macOS Applications                        │
│              (Games, Simulators, etc.)                     │
└─────────────────────┬───────────────────────────────────────┘
                      │ HID Input
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  macOS HID System                           │
└─────────────────────┬───────────────────────────────────────┘
                      │ HID Reports
                      ▼
┌─────────────────────────────────────────────────────────────┐
│            WheelerGamepadDriver.dext                        │
│              (DriverKit Extension)                          │
└─────────────────────┬───────────────────────────────────────┘
                      │ IOKit Communication
                      ▼
┌─────────────────────────────────────────────────────────────┐
│           WheelerGamepadDaemon                              │
│            (Userspace Daemon)                               │
└─────────────────────┬───────────────────────────────────────┘
                      │ UDP Port 12000
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Wheeler Host Application                       │
│               or Python Client                              │
└─────────────────────────────────────────────────────────────┘
```

### Component Details

#### DriverKit Extension (`WheelerGamepadDriver.dext`)
- **Purpose**: System-level HID gamepad driver
- **Technology**: Apple DriverKit framework
- **Location**: `/Library/SystemExtensions/`
- **Privileges**: Kernel-level access for HID functionality
- **Communication**: IOKit user client interface

#### Userspace Daemon (`WheelerGamepadDaemon`)
- **Purpose**: Bridge between UDP input and DriverKit extension
- **Technology**: C++ with IOKit and BSD sockets
- **Location**: `/usr/local/bin/WheelerGamepadDaemon`
- **Startup**: Managed by launchd (automatic startup)
- **Protocol**: Custom UDP packet format

#### Python Client Library (`wheeler_gamepad_client.py`)
- **Purpose**: High-level programming interface
- **Features**: Auto-detection, error handling, continuous mode
- **Compatibility**: Cross-platform (macOS, Windows, Linux)
- **Protocol**: Wheeler UDP packet format

## 🔧 Advanced Configuration

### Custom Development Team

If you have a specific Apple Developer Team ID:

```bash
./install_wheeler_gamepad.sh --dev-team YOUR_TEAM_ID
```

### Manual Build Process

```bash
# Build everything from source
./build_all.sh --clean --package

# Build with specific team ID
./build_all.sh --dev-team YOUR_TEAM_ID --install
```

### Daemon Configuration

The daemon can be configured by editing the launch daemon plist:

```bash
sudo nano /Library/LaunchDaemons/com.wheeler.gamepad.daemon.plist
```

Common configuration options:
- **UDP Port**: Change the listening port (default: 12000)
- **Log Level**: Adjust logging verbosity
- **Auto-restart**: Configure restart behavior

### Debugging

#### Check System Extension Status
```bash
systemextensionsctl list
```

#### Check Daemon Status
```bash
sudo launchctl list | grep wheeler
tail -f /var/log/wheeler-gamepad-daemon.log
```

#### Check System Logs
```bash
log show --predicate 'subsystem contains "Wheeler"' --last 1h
```

## 🎯 Integration Examples

### Racing Game Integration

```python
import time
from wheeler_gamepad_client import create_gamepad

gamepad = create_gamepad()
gamepad.start_continuous_mode(60)  # 60 Hz updates

# Simulate racing input
for i in range(1000):
    # Steering oscillation
    angle = 45 * math.sin(i * 0.1)
    gamepad.set_steering(angle)
    
    # Throttle control
    throttle = min(1.0, i / 500.0)
    gamepad.set_throttle(throttle)
    
    time.sleep(1/60)  # 60 FPS

gamepad.stop_continuous_mode()
gamepad.disconnect()
```

### Flight Simulator Integration

```python
from wheeler_gamepad_client import create_gamepad, GamepadButton

gamepad = create_gamepad()

# Map flight controls
gamepad.set_stick("left", aileron, elevator)    # Primary flight controls
gamepad.set_stick("right", rudder, throttle)    # Rudder and throttle
gamepad.set_button(GamepadButton.A, gear_up)    # Landing gear
gamepad.set_button(GamepadButton.B, flaps)      # Flaps
```

### Custom Application Integration

```python
class CustomGamepadController:
    def __init__(self):
        self.gamepad = create_gamepad()
        self.gamepad.set_feedback_callback(self.handle_feedback)
    
    def handle_feedback(self, left_force, right_force):
        # Handle force feedback from games
        print(f"Force feedback: L={left_force}, R={right_force}")
    
    def send_custom_input(self, data):
        # Convert your custom data to gamepad state
        state = self.convert_to_gamepad_state(data)
        self.gamepad.update_state(state)
```

## 🛠️ Development

### Building from Source

1. **Prerequisites**:
   ```bash
   xcode-select --install
   ```

2. **Clone Repository**:
   ```bash
   git clone https://github.com/Fooderapp/WheelerHost-V1.git
   cd WheelerHost-V1/DriverKit
   ```

3. **Build**:
   ```bash
   ./build_all.sh --clean --package
   ```

### Code Signing

For distribution, you'll need proper code signing:

1. **Get Apple Developer Account**
2. **Create Certificates** in Xcode or Developer Portal
3. **Build with Team ID**:
   ```bash
   ./build_all.sh --dev-team YOUR_TEAM_ID
   ```

### Testing

```bash
# Run comprehensive tests
./build_all.sh --clean --package
python3 wheeler_gamepad_client.py

# Manual testing
./install_wheeler_gamepad.sh --status
systemextensionsctl list | grep Wheeler
```

## 🔒 Security & Privacy

### System Extension Security
- **Code Signing**: All components are properly code signed
- **System Integrity**: Uses Apple's secure DriverKit framework
- **Sandboxing**: DriverKit extensions run in secure sandbox
- **User Approval**: System extension requires explicit user approval

### Network Security
- **Local Only**: UDP communication is localhost-only by default
- **No Internet**: No external network communication
- **Firewall Friendly**: Uses single UDP port (12000)

### Privacy Protection
- **No Data Collection**: No telemetry or usage data collected
- **Local Processing**: All input processing happens locally
- **No Cloud**: No cloud services or external dependencies

## 🚨 Troubleshooting

### Common Issues

#### "System Extension Blocked"
**Solution**: Go to System Preferences → Security & Privacy → General, and click "Allow" for the Wheeler extension.

#### "Developer Cannot Be Verified"
**Solution**: 
1. Right-click the installer script
2. Select "Open" from context menu
3. Click "Open" in the security dialog

#### "Daemon Not Starting"
**Solution**:
```bash
# Check daemon logs
tail -f /var/log/wheeler-gamepad-daemon.log

# Restart daemon manually
sudo launchctl unload /Library/LaunchDaemons/com.wheeler.gamepad.daemon.plist
sudo launchctl load /Library/LaunchDaemons/com.wheeler.gamepad.daemon.plist
```

#### "No Gamepad Detected in Games"
**Solution**:
1. Verify system extension is active: `systemextensionsctl list`
2. Check daemon is running: `sudo launchctl list | grep wheeler`
3. Test with Python client: `python3 wheeler_gamepad_client.py`
4. Restart the game application

### Getting Help

1. **Check Status**: `./install_wheeler_gamepad.sh --status`
2. **View Logs**: `tail -f /var/log/wheeler-gamepad-daemon.log`
3. **System Logs**: `log show --predicate 'subsystem contains "Wheeler"' --last 1h`
4. **GitHub Issues**: Report issues on the project repository

## 📄 License

This project is licensed under the MIT License. See the LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please read the contributing guidelines and submit pull requests for any improvements.

## 📞 Support

For support and questions:
- **GitHub Issues**: Primary support channel
- **Documentation**: Check README files in the repository
- **Community**: Join discussions in the project repository

---

**Wheeler Virtual Gamepad** - Professional virtual gamepad solution for macOS Sequoia