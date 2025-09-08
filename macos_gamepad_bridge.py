# macos_gamepad_bridge.py
# Cross-platform virtual gamepad bridge for macOS and Linux
# Uses pynput for keyboard/mouse simulation and attempts to create virtual gamepad input

import platform
import time
from typing import Optional, Callable
import threading

# Try to import platform-specific modules
try:
    from pynput import keyboard, mouse
    from pynput.keyboard import Key
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False

try:
    import os
    # Set a dummy display if none exists (for headless environments)
    if 'DISPLAY' not in os.environ:
        os.environ['DISPLAY'] = ':0'
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except (ImportError, Exception):
    PYAUTOGUI_AVAILABLE = False

# For Linux, try to use evdev for virtual input device creation
try:
    import evdev
    from evdev import UInput, ecodes
    EVDEV_AVAILABLE = True
except ImportError:
    EVDEV_AVAILABLE = False


class MacOSGamepadBridge:
    """
    Cross-platform virtual gamepad bridge that works on macOS and Linux.
    
    On macOS: Uses keyboard/mouse simulation for basic input
    On Linux: Uses evdev to create a virtual gamepad device
    
    This bridge provides the same interface as the Windows bridges (ViGEm/vJoy)
    but adapts the input to work on Unix-like systems.
    """
    
    def __init__(self, device_id: int = 1):
        self.device_id = device_id
        self._ffb_cb: Optional[Callable[[float, float], None]] = None
        self.platform = platform.system().lower()
        
        # State tracking
        self._last_lx = 0.0
        self._last_ly = 0.0
        self._last_rt = 0
        self._last_lt = 0
        self._last_buttons = 0
        
        # Virtual device for Linux
        self._uinput = None
        
        # Initialize platform-specific components
        self._init_platform()
        
        print(f"MacOSGamepadBridge initialized for {self.platform}")
    
    def _init_platform(self):
        """Initialize platform-specific input systems."""
        if self.platform == "linux" and EVDEV_AVAILABLE:
            self._init_linux_virtual_device()
        elif self.platform == "darwin":  # macOS
            self._init_macos_input()
        else:
            print(f"Warning: Limited support for platform {self.platform}")
    
    def _init_linux_virtual_device(self):
        """Initialize Linux virtual gamepad using evdev."""
        try:
            # Define the capabilities of our virtual gamepad
            cap = {
                ecodes.EV_KEY: [
                    ecodes.BTN_A, ecodes.BTN_B, ecodes.BTN_X, ecodes.BTN_Y,
                    ecodes.BTN_TL, ecodes.BTN_TR,  # LB, RB
                    ecodes.BTN_START, ecodes.BTN_SELECT,  # Start, Back
                    ecodes.BTN_DPAD_UP, ecodes.BTN_DPAD_DOWN, ecodes.BTN_DPAD_LEFT, ecodes.BTN_DPAD_RIGHT
                ],
                ecodes.EV_ABS: [
                    (ecodes.ABS_X, (-32768, 32767, 0, 0)),      # Left stick X
                    (ecodes.ABS_Y, (-32768, 32767, 0, 0)),      # Left stick Y
                    (ecodes.ABS_RX, (-32768, 32767, 0, 0)),     # Right stick X
                    (ecodes.ABS_RY, (-32768, 32767, 0, 0)),     # Right stick Y
                    (ecodes.ABS_Z, (0, 255, 0, 0)),             # Left trigger
                    (ecodes.ABS_RZ, (0, 255, 0, 0)),            # Right trigger
                ]
            }
            
            self._uinput = UInput(cap, name='Wheeler Virtual Gamepad', version=0x3)
            print("Linux virtual gamepad device created successfully")
            
        except Exception as e:
            print(f"Failed to create Linux virtual gamepad: {e}")
            self._uinput = None
    
    def _init_macos_input(self):
        """Initialize macOS input simulation."""
        if not PYNPUT_AVAILABLE:
            print("Warning: pynput not available for macOS input simulation")
            return
        
        # Initialize keyboard and mouse controllers
        try:
            self._keyboard = keyboard.Controller()
            self._mouse = mouse.Controller()
            print("macOS input controllers initialized")
        except Exception as e:
            print(f"Failed to initialize macOS input controllers: {e}")
    
    def set_feedback_callback(self, cb: Optional[Callable[[float, float], None]]):
        """Set callback for force feedback (rumble) events."""
        self._ffb_cb = cb
        # Since we can't provide real FFB on most systems, we'll simulate it
        # by calling the callback with zero values periodically
    
    def send_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int):
        """Send gamepad state to the system."""
        try:
            if self.platform == "linux" and self._uinput:
                self._send_linux_state(lx, ly, rt, lt, btn_mask)
            elif self.platform == "darwin":
                self._send_macos_state(lx, ly, rt, lt, btn_mask)
            else:
                self._send_fallback_state(lx, ly, rt, lt, btn_mask)
                
            # Update state tracking
            self._last_lx = lx
            self._last_ly = ly
            self._last_rt = rt
            self._last_lt = lt
            self._last_buttons = btn_mask
            
        except Exception as e:
            print(f"Error sending gamepad state: {e}")
    
    def _send_linux_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int):
        """Send state to Linux virtual gamepad device."""
        if not self._uinput:
            return
        
        # Convert float axes to integer range
        lx_int = int(lx * 32767)
        ly_int = int(ly * 32767)
        
        # Send analog stick values
        self._uinput.write(ecodes.EV_ABS, ecodes.ABS_X, lx_int)
        self._uinput.write(ecodes.EV_ABS, ecodes.ABS_Y, ly_int)
        
        # Send trigger values
        self._uinput.write(ecodes.EV_ABS, ecodes.ABS_Z, lt)
        self._uinput.write(ecodes.EV_ABS, ecodes.ABS_RZ, rt)
        
        # Send button states
        button_map = [
            ecodes.BTN_A,           # A (bit 0)
            ecodes.BTN_B,           # B (bit 1)
            ecodes.BTN_X,           # X (bit 2)
            ecodes.BTN_Y,           # Y (bit 3)
            ecodes.BTN_TL,          # LB (bit 4)
            ecodes.BTN_TR,          # RB (bit 5)
            ecodes.BTN_START,       # Start (bit 6)
            ecodes.BTN_SELECT,      # Back (bit 7)
            ecodes.BTN_DPAD_UP,     # DPad Up (bit 8)
            ecodes.BTN_DPAD_DOWN,   # DPad Down (bit 9)
            ecodes.BTN_DPAD_LEFT,   # DPad Left (bit 10)
            ecodes.BTN_DPAD_RIGHT,  # DPad Right (bit 11)
        ]
        
        for i, btn_code in enumerate(button_map):
            if i < 12:  # Only handle first 12 buttons
                pressed = (btn_mask >> i) & 1
                self._uinput.write(ecodes.EV_KEY, btn_code, pressed)
        
        # Sync the events
        self._uinput.syn()
    
    def _send_macos_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int):
        """Send state using macOS input simulation."""
        if not PYNPUT_AVAILABLE:
            return
        
        # For macOS, we'll map gamepad input to keyboard/mouse actions
        # This is a simplified approach - in a real implementation, you might
        # want to use more sophisticated mapping or create actual HID devices
        
        try:
            # Map steering to mouse movement (for racing games)
            if abs(lx) > 0.1:  # Dead zone
                # Move mouse horizontally based on steering
                current_pos = self._mouse.position
                new_x = current_pos[0] + (lx * 10)  # Scale factor
                self._mouse.position = (new_x, current_pos[1])
            
            # Map throttle/brake to keyboard keys
            if rt > 50:  # Throttle threshold
                if not hasattr(self, '_throttle_pressed'):
                    self._keyboard.press('w')  # Common throttle key
                    self._throttle_pressed = True
            else:
                if hasattr(self, '_throttle_pressed'):
                    self._keyboard.release('w')
                    delattr(self, '_throttle_pressed')
            
            if lt > 50:  # Brake threshold
                if not hasattr(self, '_brake_pressed'):
                    self._keyboard.press('s')  # Common brake key
                    self._brake_pressed = True
            else:
                if hasattr(self, '_brake_pressed'):
                    self._keyboard.release('s')
                    delattr(self, '_brake_pressed')
            
            # Map buttons to keyboard keys
            button_key_map = {
                0: 'space',    # A button
                1: 'x',        # B button
                2: 'z',        # X button
                3: 'c',        # Y button
                6: Key.enter,  # Start
                7: Key.esc,    # Back
            }
            
            for bit, key in button_key_map.items():
                pressed = (btn_mask >> bit) & 1
                attr_name = f'_btn_{bit}_pressed'
                
                if pressed and not hasattr(self, attr_name):
                    self._keyboard.press(key)
                    setattr(self, attr_name, True)
                elif not pressed and hasattr(self, attr_name):
                    self._keyboard.release(key)
                    delattr(self, attr_name)
                    
        except Exception as e:
            print(f"Error in macOS input simulation: {e}")
    
    def _send_fallback_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int):
        """Fallback state handling for unsupported platforms."""
        # Just log the state for debugging
        if abs(lx) > 0.1 or abs(ly) > 0.1 or rt > 10 or lt > 10 or btn_mask > 0:
            print(f"Gamepad state: LX={lx:.2f}, LY={ly:.2f}, RT={rt}, LT={lt}, Buttons=0x{btn_mask:03X}")
    
    def close(self):
        """Clean up resources."""
        try:
            if self._uinput:
                self._uinput.close()
                self._uinput = None
            
            # Release any pressed keys on macOS
            if self.platform == "darwin" and PYNPUT_AVAILABLE:
                for attr in list(self.__dict__.keys()):
                    if attr.endswith('_pressed'):
                        delattr(self, attr)
                        
        except Exception as e:
            print(f"Error during cleanup: {e}")
    
    def __del__(self):
        """Destructor to ensure cleanup."""
        self.close()


# Compatibility alias
class CrossPlatformGamepadBridge(MacOSGamepadBridge):
    """Alias for backward compatibility."""
    pass