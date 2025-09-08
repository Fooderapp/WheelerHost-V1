#!/usr/bin/env python3
"""
Wheeler Gamepad Client
High-level Python interface for the Wheeler Virtual Gamepad system.
Supports both DriverKit (macOS) and cross-platform fallback modes.
"""

import socket
import struct
import time
import threading
import platform
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import IntEnum

class GamepadButton(IntEnum):
    """Xbox-style gamepad button mappings"""
    A = 0x0001
    B = 0x0002
    X = 0x0004
    Y = 0x0008
    LEFT_BUMPER = 0x0010
    RIGHT_BUMPER = 0x0020
    BACK = 0x0040
    START = 0x0080
    LEFT_STICK = 0x0100
    RIGHT_STICK = 0x0200
    DPAD_UP = 0x0400
    DPAD_DOWN = 0x0800
    DPAD_LEFT = 0x1000
    DPAD_RIGHT = 0x2000

@dataclass
class GamepadState:
    """Complete gamepad state"""
    # Analog sticks (-1.0 to 1.0)
    left_stick_x: float = 0.0
    left_stick_y: float = 0.0
    right_stick_x: float = 0.0
    right_stick_y: float = 0.0
    
    # Triggers (0.0 to 1.0)
    left_trigger: float = 0.0
    right_trigger: float = 0.0
    
    # Buttons (bitmask)
    buttons: int = 0
    
    # Wheeler-specific inputs
    steering_angle: float = 0.0  # degrees, -900 to 900
    throttle: float = 0.0        # 0.0 to 1.0
    brake: float = 0.0           # 0.0 to 1.0

class WheelerGamepadClient:
    """
    High-level client for Wheeler Virtual Gamepad system.
    Automatically detects and uses the best available backend.
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 12000):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.state = GamepadState()
        self.feedback_callback: Optional[Callable[[float, float], None]] = None
        
        # Auto-detection results
        self.backend_type = "unknown"
        self.backend_info = {}
        
        # Threading for continuous operation
        self._running = False
        self._update_thread: Optional[threading.Thread] = None
        
    def connect(self) -> bool:
        """
        Connect to the Wheeler gamepad system.
        Automatically detects the best available backend.
        """
        try:
            # Detect available backends
            self._detect_backends()
            
            # Create UDP socket
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(1.0)  # 1 second timeout
            
            # Test connection by sending a neutral state
            test_state = GamepadState()
            if self._send_state(test_state):
                self.connected = True
                print(f"✅ Connected to Wheeler gamepad system ({self.backend_type})")
                return True
            else:
                print("❌ Failed to connect to Wheeler gamepad system")
                return False
                
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the gamepad system"""
        self.stop_continuous_mode()
        
        if self.socket:
            self.socket.close()
            self.socket = None
        
        self.connected = False
        print("🔌 Disconnected from Wheeler gamepad system")
    
    def _detect_backends(self):
        """Detect available gamepad backends"""
        system = platform.system().lower()
        
        if system == "darwin":  # macOS
            # Check for DriverKit daemon
            if self._check_driverkit_daemon():
                self.backend_type = "DriverKit (macOS)"
                self.backend_info = {
                    "type": "driverkit",
                    "platform": "macOS",
                    "features": ["force_feedback", "full_hid", "system_integration"]
                }
                return
            
            # Check for cross-platform bridge
            if self._check_cross_platform_bridge():
                self.backend_type = "Cross-platform (macOS)"
                self.backend_info = {
                    "type": "cross_platform",
                    "platform": "macOS",
                    "features": ["keyboard_mouse_simulation"]
                }
                return
        
        elif system == "windows":
            self.backend_type = "ViGEm/vJoy (Windows)"
            self.backend_info = {
                "type": "vigem_vjoy",
                "platform": "Windows",
                "features": ["force_feedback", "full_hid"]
            }
        
        elif system == "linux":
            self.backend_type = "Cross-platform (Linux)"
            self.backend_info = {
                "type": "cross_platform",
                "platform": "Linux",
                "features": ["evdev", "uinput"]
            }
        
        else:
            self.backend_type = "Unknown"
            self.backend_info = {"type": "unknown", "platform": system}
    
    def _check_driverkit_daemon(self) -> bool:
        """Check if DriverKit daemon is running"""
        try:
            import subprocess
            result = subprocess.run(
                ["launchctl", "list", "com.wheeler.gamepad.daemon"],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except:
            return False
    
    def _check_cross_platform_bridge(self) -> bool:
        """Check if cross-platform bridge is available"""
        try:
            # Try importing the required modules
            import pynput
            return True
        except ImportError:
            return False
    
    def update_state(self, state: GamepadState):
        """Update the gamepad state"""
        self.state = state
        if self.connected:
            self._send_state(state)
    
    def set_steering(self, angle: float):
        """Set steering angle in degrees (-900 to 900)"""
        self.state.steering_angle = max(-900, min(900, angle))
        self.state.left_stick_x = self.state.steering_angle / 900.0
        if self.connected:
            self._send_state(self.state)
    
    def set_throttle(self, value: float):
        """Set throttle (0.0 to 1.0)"""
        self.state.throttle = max(0.0, min(1.0, value))
        self.state.right_trigger = self.state.throttle
        if self.connected:
            self._send_state(self.state)
    
    def set_brake(self, value: float):
        """Set brake (0.0 to 1.0)"""
        self.state.brake = max(0.0, min(1.0, value))
        self.state.left_trigger = self.state.brake
        if self.connected:
            self._send_state(self.state)
    
    def set_button(self, button: GamepadButton, pressed: bool):
        """Set button state"""
        if pressed:
            self.state.buttons |= button
        else:
            self.state.buttons &= ~button
        
        if self.connected:
            self._send_state(self.state)
    
    def set_stick(self, stick: str, x: float, y: float):
        """Set analog stick position (-1.0 to 1.0)"""
        x = max(-1.0, min(1.0, x))
        y = max(-1.0, min(1.0, y))
        
        if stick.lower() == "left":
            self.state.left_stick_x = x
            self.state.left_stick_y = y
        elif stick.lower() == "right":
            self.state.right_stick_x = x
            self.state.right_stick_y = y
        
        if self.connected:
            self._send_state(self.state)
    
    def reset_state(self):
        """Reset gamepad to neutral state"""
        self.state = GamepadState()
        if self.connected:
            self._send_state(self.state)
    
    def start_continuous_mode(self, update_rate: float = 60.0):
        """Start continuous state updates at specified rate (Hz)"""
        if self._running:
            return
        
        self._running = True
        self._update_thread = threading.Thread(
            target=self._continuous_update_loop,
            args=(1.0 / update_rate,),
            daemon=True
        )
        self._update_thread.start()
        print(f"🔄 Started continuous mode at {update_rate} Hz")
    
    def stop_continuous_mode(self):
        """Stop continuous state updates"""
        if not self._running:
            return
        
        self._running = False
        if self._update_thread:
            self._update_thread.join(timeout=1.0)
            self._update_thread = None
        
        print("⏹️ Stopped continuous mode")
    
    def set_feedback_callback(self, callback: Callable[[float, float], None]):
        """Set callback for force feedback (left_force, right_force)"""
        self.feedback_callback = callback
    
    def get_backend_info(self) -> Dict[str, Any]:
        """Get information about the current backend"""
        return {
            "backend_type": self.backend_type,
            "connected": self.connected,
            "host": self.host,
            "port": self.port,
            **self.backend_info
        }
    
    def _send_state(self, state: GamepadState) -> bool:
        """Send gamepad state via UDP"""
        if not self.socket:
            return False
        
        try:
            # Pack state into Wheeler UDP protocol format
            packet = struct.pack(
                "fffIffff",  # 8 floats + 1 uint32
                state.steering_angle,    # Steering angle
                state.throttle,          # Throttle
                state.brake,            # Brake
                state.buttons,          # Button bitmask
                state.left_stick_x,     # Left stick X
                state.left_stick_y,     # Left stick Y
                state.right_stick_x,    # Right stick X
                state.right_stick_y     # Right stick Y
            )
            
            self.socket.sendto(packet, (self.host, self.port))
            return True
            
        except Exception as e:
            print(f"❌ Failed to send state: {e}")
            return False
    
    def _continuous_update_loop(self, interval: float):
        """Continuous update loop for maintaining connection"""
        while self._running:
            if self.connected:
                self._send_state(self.state)
            time.sleep(interval)

# Convenience functions for quick usage
def create_gamepad(host: str = "127.0.0.1", port: int = 12000) -> WheelerGamepadClient:
    """Create and connect a gamepad client"""
    client = WheelerGamepadClient(host, port)
    if client.connect():
        return client
    else:
        raise ConnectionError("Failed to connect to Wheeler gamepad system")

def test_gamepad():
    """Test the gamepad system with a simple demo"""
    print("🎮 Wheeler Gamepad Test")
    print("=" * 40)
    
    try:
        gamepad = create_gamepad()
        print(f"Backend: {gamepad.backend_type}")
        print()
        
        # Test sequence
        print("Testing steering...")
        for angle in [-450, 0, 450, 0]:
            gamepad.set_steering(angle)
            print(f"  Steering: {angle}°")
            time.sleep(0.5)
        
        print("\nTesting throttle/brake...")
        gamepad.set_throttle(1.0)
        print("  Full throttle")
        time.sleep(0.5)
        
        gamepad.set_throttle(0.0)
        gamepad.set_brake(1.0)
        print("  Full brake")
        time.sleep(0.5)
        
        print("\nTesting buttons...")
        for button in [GamepadButton.A, GamepadButton.B, GamepadButton.X, GamepadButton.Y]:
            gamepad.set_button(button, True)
            print(f"  Button {button.name} pressed")
            time.sleep(0.2)
            gamepad.set_button(button, False)
        
        print("\nResetting to neutral...")
        gamepad.reset_state()
        
        print("✅ Test completed successfully!")
        
        gamepad.disconnect()
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_gamepad()