# Wheeler Virtual Gamepad - Quick Start Guide

🎮 **Get your virtual gamepad running in 5 minutes!**

## ⚡ One-Command Installation

```bash
./install_wheeler_gamepad.sh
```

That's it! The installer handles everything automatically.

## ✅ Verify Installation

```bash
# Check if everything is working
./install_wheeler_gamepad.sh --status

# Test the gamepad
python3 wheeler_gamepad_client.py
```

## 🎯 Basic Usage

### Python Quick Test
```python
from wheeler_gamepad_client import create_gamepad, GamepadButton

# Connect
gamepad = create_gamepad()

# Steer left 45 degrees
gamepad.set_steering(-45)

# Half throttle
gamepad.set_throttle(0.5)

# Press A button
gamepad.set_button(GamepadButton.A, True)

# Done
gamepad.disconnect()
```

### Racing Wheel Style
```python
gamepad = create_gamepad()

# Racing controls
gamepad.set_steering(90)      # Turn right
gamepad.set_throttle(0.8)     # 80% throttle
gamepad.set_brake(0.0)        # No brake

# Gear shift (using buttons)
gamepad.set_button(GamepadButton.RIGHT_BUMPER, True)  # Shift up
```

### Flight Sim Style
```python
gamepad = create_gamepad()

# Flight controls
gamepad.set_stick("left", 0.2, -0.3)   # Aileron + Elevator
gamepad.set_stick("right", 0.1, 0.7)   # Rudder + Throttle
gamepad.set_button(GamepadButton.A, True)  # Landing gear
```

## 🔧 Common Commands

```bash
# Install
./install_wheeler_gamepad.sh

# Check status
./install_wheeler_gamepad.sh --status

# Uninstall
./install_wheeler_gamepad.sh --uninstall

# Build from source
./build_all.sh --clean --package

# View logs
tail -f /var/log/wheeler-gamepad-daemon.log
```

## 🚨 Troubleshooting

### System Extension Blocked?
1. Go to **System Preferences** → **Security & Privacy** → **General**
2. Click **"Allow"** for Wheeler extension
3. Restart: `./install_wheeler_gamepad.sh --status`

### Gamepad Not Detected?
```bash
# Check if daemon is running
sudo launchctl list | grep wheeler

# Restart daemon
sudo launchctl unload /Library/LaunchDaemons/com.wheeler.gamepad.daemon.plist
sudo launchctl load /Library/LaunchDaemons/com.wheeler.gamepad.daemon.plist
```

### Python Import Error?
```bash
# Install required packages
pip3 install pynput pyautogui

# Or use the Wheeler Host requirements
pip3 install -r requirements.txt
```

## 📱 Integration Examples

### With Wheeler Host App
The gamepad automatically works with the Wheeler Host application - no additional setup needed!

### With Racing Games
1. Install the gamepad: `./install_wheeler_gamepad.sh`
2. Start your racing game
3. The game should detect "Wheeler Virtual Gamepad" as an Xbox controller
4. Configure controls in the game's settings

### With Flight Simulators
1. Install the gamepad
2. Use the Python client to send flight control data
3. The simulator sees it as a standard Xbox controller

## 🎮 Button Mapping

| Wheeler Button | Xbox Equivalent | Python Code |
|----------------|-----------------|-------------|
| A | A | `GamepadButton.A` |
| B | B | `GamepadButton.B` |
| X | X | `GamepadButton.X` |
| Y | Y | `GamepadButton.Y` |
| Left Bumper | LB | `GamepadButton.LEFT_BUMPER` |
| Right Bumper | RB | `GamepadButton.RIGHT_BUMPER` |
| Back | Back/Select | `GamepadButton.BACK` |
| Start | Start/Menu | `GamepadButton.START` |

## 📊 Input Ranges

| Input | Range | Notes |
|-------|-------|-------|
| Steering | -900° to +900° | Racing wheel style |
| Throttle | 0.0 to 1.0 | 0 = no throttle, 1 = full |
| Brake | 0.0 to 1.0 | 0 = no brake, 1 = full |
| Analog Sticks | -1.0 to +1.0 | Standard gamepad range |
| Triggers | 0.0 to 1.0 | 0 = not pressed, 1 = fully pressed |

## 🔗 Need More Help?

- **Full Documentation**: `README_COMPLETE_GAMEPAD.md`
- **macOS Compatibility**: `README-macOS.md`
- **GitHub Issues**: Report problems on the repository
- **System Logs**: `log show --predicate 'subsystem contains "Wheeler"' --last 1h`

---

**Happy Gaming! 🎮**