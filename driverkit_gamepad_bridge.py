#!/usr/bin/env python3
"""
DriverKit Gamepad Bridge for macOS
Communicates with the Wheeler DriverKit virtual gamepad driver.
"""

import os
import sys
import platform
import ctypes
import struct
from ctypes import c_uint32, c_uint16, c_uint8, c_int16, c_void_p, c_size_t, POINTER, Structure

# Only available on macOS
if platform.system() == 'Darwin':
    try:
        # Load IOKit framework
        from ctypes import cdll
        IOKit = cdll.LoadLibrary('/System/Library/Frameworks/IOKit.framework/IOKit')
        CoreFoundation = cdll.LoadLibrary('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        
        # IOKit function prototypes
        IOKit.IOServiceMatching.argtypes = [ctypes.c_char_p]
        IOKit.IOServiceMatching.restype = c_void_p
        
        IOKit.IOServiceGetMatchingService.argtypes = [c_uint32, c_void_p]
        IOKit.IOServiceGetMatchingService.restype = c_uint32
        
        IOKit.IOServiceOpen.argtypes = [c_uint32, c_uint32, c_uint32, POINTER(c_uint32)]
        IOKit.IOServiceOpen.restype = c_uint32
        
        IOKit.IOServiceClose.argtypes = [c_uint32]
        IOKit.IOServiceClose.restype = c_uint32
        
        IOKit.IOConnectCallStructMethod.argtypes = [c_uint32, c_uint32, c_void_p, c_size_t, c_void_p, POINTER(c_size_t)]
        IOKit.IOConnectCallStructMethod.restype = c_uint32
        
        # CoreFoundation function prototypes
        CoreFoundation.CFStringCreateWithCString.argtypes = [c_void_p, ctypes.c_char_p, c_uint32]
        CoreFoundation.CFStringCreateWithCString.restype = c_void_p
        
        CoreFoundation.CFRelease.argtypes = [c_void_p]
        CoreFoundation.CFRelease.restype = None
        
        IOKIT_AVAILABLE = True
    except (OSError, AttributeError) as e:
        print(f"Warning: IOKit not available: {e}")
        IOKIT_AVAILABLE = False
else:
    IOKIT_AVAILABLE = False


class GamepadState(Structure):
    """C structure matching the DriverKit GamepadState."""
    _fields_ = [
        ("leftStickX", c_int16),     # -32768 to 32767
        ("leftStickY", c_int16),     # -32768 to 32767
        ("rightStickX", c_int16),    # -32768 to 32767
        ("rightStickY", c_int16),    # -32768 to 32767
        ("leftTrigger", c_uint8),    # 0 to 255
        ("rightTrigger", c_uint8),   # 0 to 255
        ("buttons", c_uint16),       # Button bitmask
        ("dpad", c_uint8),          # D-pad state (0-8, 0=center)
    ]


class DriverKitGamepadBridge:
    """
    DriverKit-based virtual gamepad bridge for macOS.
    Communicates with the Wheeler DriverKit extension to create a true virtual gamepad.
    """
    
    # IOKit constants
    kIOMasterPortDefault = 0
    kIOReturnSuccess = 0
    kCFStringEncodingUTF8 = 0x08000100
    
    # Method selectors (must match DriverKit extension)
    kWheelerGamepadUserClientMethodUpdateState = 0
    kWheelerGamepadUserClientMethodGetState = 1
    
    def __init__(self):
        """Initialize the DriverKit gamepad bridge."""
        self.platform = platform.system().lower()
        self.service = 0
        self.connection = 0
        self.connected = False
        self.last_state = GamepadState()
        
        print(f"DriverKitGamepadBridge initializing for {self.platform}")
        
        if self.platform == "darwin" and IOKIT_AVAILABLE:
            self._connect_to_driver()
        else:
            print("DriverKit bridge only available on macOS with IOKit")
    
    def _connect_to_driver(self):
        """Connect to the Wheeler DriverKit extension."""
        try:
            # Create matching dictionary for our service
            service_name = b"WheelerGamepadDriver"
            matching_dict = IOKit.IOServiceMatching(service_name)
            if not matching_dict:
                print("Failed to create service matching dictionary")
                return False
            
            # Find the service
            self.service = IOKit.IOServiceGetMatchingService(self.kIOMasterPortDefault, matching_dict)
            if not self.service:
                print("Wheeler DriverKit extension not found. Make sure it's installed and loaded.")
                return False
            
            # Open connection to the service
            connection = c_uint32(0)
            result = IOKit.IOServiceOpen(self.service, 0, 0, ctypes.byref(connection))
            if result != self.kIOReturnSuccess:
                print(f"Failed to open connection to DriverKit extension: {result}")
                return False
            
            self.connection = connection.value
            self.connected = True
            print("Successfully connected to Wheeler DriverKit extension")
            return True
            
        except Exception as e:
            print(f"Error connecting to DriverKit extension: {e}")
            return False
    
    def send_state(self, lx: float, ly: float, rt: int, lt: int, btn_mask: int):
        """
        Send gamepad state to the DriverKit extension.
        
        Args:
            lx: Left stick X (-1.0 to 1.0)
            ly: Left stick Y (-1.0 to 1.0)
            rt: Right trigger (0 to 255)
            lt: Left trigger (0 to 255)
            btn_mask: Button bitmask
        """
        if not self.connected:
            # Fallback to logging if not connected
            print(f"DriverKit Gamepad state: LX={lx:.2f}, LY={ly:.2f}, RT={rt}, LT={lt}, Buttons=0x{btn_mask:03X}")
            return
        
        try:
            # Convert float stick values to int16 range
            state = GamepadState()
            state.leftStickX = int(max(-32768, min(32767, lx * 32767)))
            state.leftStickY = int(max(-32768, min(32767, ly * 32767)))
            state.rightStickX = 0  # Not used in current implementation
            state.rightStickY = 0  # Not used in current implementation
            state.leftTrigger = max(0, min(255, lt))
            state.rightTrigger = max(0, min(255, rt))
            state.buttons = btn_mask & 0xFFFF
            state.dpad = self._buttons_to_dpad(btn_mask)
            
            # Send state to DriverKit extension
            result = IOKit.IOConnectCallStructMethod(
                self.connection,
                self.kWheelerGamepadUserClientMethodUpdateState,
                ctypes.byref(state),
                ctypes.sizeof(state),
                None,
                None
            )
            
            if result != self.kIOReturnSuccess:
                print(f"Failed to send gamepad state to DriverKit extension: {result}")
            
            self.last_state = state
            
        except Exception as e:
            print(f"Error sending gamepad state: {e}")
    
    def _buttons_to_dpad(self, btn_mask: int) -> int:
        """Convert button mask to D-pad value."""
        # Extract D-pad buttons (assuming bits 8-11 are D-pad)
        dpad_up = (btn_mask >> 8) & 1
        dpad_down = (btn_mask >> 9) & 1
        dpad_left = (btn_mask >> 10) & 1
        dpad_right = (btn_mask >> 11) & 1
        
        # Convert to HID D-pad format (0=center, 1=up, 2=up-right, etc.)
        if dpad_up and dpad_right:
            return 2  # Up-Right
        elif dpad_right and dpad_down:
            return 4  # Down-Right
        elif dpad_down and dpad_left:
            return 6  # Down-Left
        elif dpad_left and dpad_up:
            return 8  # Up-Left
        elif dpad_up:
            return 1  # Up
        elif dpad_right:
            return 3  # Right
        elif dpad_down:
            return 5  # Down
        elif dpad_left:
            return 7  # Left
        else:
            return 0  # Center
    
    def get_state(self) -> dict:
        """Get current gamepad state from the DriverKit extension."""
        if not self.connected:
            return {
                'leftStickX': self.last_state.leftStickX,
                'leftStickY': self.last_state.leftStickY,
                'rightStickX': self.last_state.rightStickX,
                'rightStickY': self.last_state.rightStickY,
                'leftTrigger': self.last_state.leftTrigger,
                'rightTrigger': self.last_state.rightTrigger,
                'buttons': self.last_state.buttons,
                'dpad': self.last_state.dpad,
            }
        
        try:
            state = GamepadState()
            output_size = c_size_t(ctypes.sizeof(state))
            
            result = IOKit.IOConnectCallStructMethod(
                self.connection,
                self.kWheelerGamepadUserClientMethodGetState,
                None,
                0,
                ctypes.byref(state),
                ctypes.byref(output_size)
            )
            
            if result == self.kIOReturnSuccess:
                return {
                    'leftStickX': state.leftStickX,
                    'leftStickY': state.leftStickY,
                    'rightStickX': state.rightStickX,
                    'rightStickY': state.rightStickY,
                    'leftTrigger': state.leftTrigger,
                    'rightTrigger': state.rightTrigger,
                    'buttons': state.buttons,
                    'dpad': state.dpad,
                }
            else:
                print(f"Failed to get gamepad state from DriverKit extension: {result}")
                return {}
                
        except Exception as e:
            print(f"Error getting gamepad state: {e}")
            return {}
    
    def set_feedback_callback(self, callback):
        """Set callback for force feedback events (not implemented yet)."""
        # TODO: Implement force feedback support
        pass
    
    def close(self):
        """Close connection to the DriverKit extension."""
        if self.connected and self.connection:
            IOKit.IOServiceClose(self.connection)
            self.connection = 0
            self.connected = False
            print("Disconnected from Wheeler DriverKit extension")
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        self.close()


def test_driverkit_bridge():
    """Test the DriverKit gamepad bridge."""
    print("Testing DriverKit Gamepad Bridge...")
    
    bridge = DriverKitGamepadBridge()
    
    if not bridge.connected:
        print("DriverKit extension not available, testing fallback mode...")
    
    # Test sending various states
    import time
    
    print("Sending test gamepad states...")
    
    # Neutral state
    bridge.send_state(0.0, 0.0, 0, 0, 0)
    time.sleep(0.1)
    
    # Steering left
    bridge.send_state(-0.5, 0.0, 0, 0, 0)
    time.sleep(0.1)
    
    # Steering right
    bridge.send_state(0.5, 0.0, 0, 0, 0)
    time.sleep(0.1)
    
    # Throttle
    bridge.send_state(0.0, 0.0, 200, 0, 0)
    time.sleep(0.1)
    
    # Brake
    bridge.send_state(0.0, 0.0, 0, 200, 0)
    time.sleep(0.1)
    
    # Button A
    bridge.send_state(0.0, 0.0, 0, 0, 1)
    time.sleep(0.1)
    
    # Multiple buttons
    bridge.send_state(0.0, 0.0, 0, 0, 0b1111)
    time.sleep(0.1)
    
    # D-pad up
    bridge.send_state(0.0, 0.0, 0, 0, 0b100000000)  # Bit 8
    time.sleep(0.1)
    
    # Return to neutral
    bridge.send_state(0.0, 0.0, 0, 0, 0)
    
    print("Test completed!")
    
    # Test getting state
    state = bridge.get_state()
    print(f"Current state: {state}")
    
    bridge.close()


if __name__ == "__main__":
    test_driverkit_bridge()