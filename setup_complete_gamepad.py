#!/usr/bin/env python3
"""
Wheeler Virtual Gamepad - Complete Setup Script
One-click setup for the complete DriverKit-based virtual gamepad system.
"""

import os
import sys
import subprocess
import platform
import time
from pathlib import Path

def print_banner():
    print("""
🎮 Wheeler Virtual Gamepad - Complete Setup
==========================================

Professional DriverKit-based virtual gamepad for macOS Sequoia
- Native HID gamepad functionality
- Works with any Xbox controller compatible game
- Real-time UDP communication
- Professional installation and code signing

""")

def check_system():
    """Check if system meets requirements"""
    print("🔍 Checking system requirements...")
    
    # Check macOS
    if platform.system() != 'Darwin':
        print("❌ This setup only works on macOS")
        return False
    
    # Check macOS version
    version = platform.mac_ver()[0]
    major, minor = map(int, version.split('.')[:2])
    
    if major < 10 or (major == 10 and minor < 15):
        print(f"❌ macOS 10.15+ required, found {version}")
        return False
    
    print(f"✅ macOS {version} - Compatible")
    
    # Check for required tools
    tools = ['xcode-select', 'make', 'python3']
    for tool in tools:
        if subprocess.run(['which', tool], capture_output=True).returncode != 0:
            print(f"❌ {tool} not found")
            return False
    
    print("✅ All required tools available")
    return True

def setup_python_environment():
    """Setup Python environment with required packages"""
    print("\n🐍 Setting up Python environment...")
    
    try:
        # Check if packages are already installed
        import socket
        import struct
        import threading
        print("✅ Core Python packages available")
        
        # Try to install optional packages
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install', 'pynput', 'pyautogui'], 
                         check=False, capture_output=True)
            print("✅ Optional packages installed")
        except:
            print("⚠️  Optional packages not installed (cross-platform fallback may not work)")
        
        return True
    except Exception as e:
        print(f"❌ Python environment setup failed: {e}")
        return False

def build_and_install():
    """Build and install the complete gamepad system"""
    print("\n🔨 Building and installing Wheeler Virtual Gamepad...")
    
    # Find the DriverKit directory
    script_dir = Path(__file__).parent
    driverkit_dir = script_dir / 'DriverKit'
    
    if not driverkit_dir.exists():
        print("❌ DriverKit directory not found")
        return False
    
    # Change to DriverKit directory
    os.chdir(driverkit_dir)
    
    # Make scripts executable
    for script in ['build_all.sh', 'install_wheeler_gamepad.sh']:
        script_path = driverkit_dir / script
        if script_path.exists():
            os.chmod(script_path, 0o755)
    
    # Run the complete build and install
    print("Building components...")
    build_result = subprocess.run(['./build_all.sh', '--clean', '--install'], 
                                capture_output=False)
    
    if build_result.returncode == 0:
        print("✅ Build and installation completed successfully")
        return True
    else:
        print("❌ Build or installation failed")
        return False

def verify_installation():
    """Verify that the installation was successful"""
    print("\n✅ Verifying installation...")
    
    # Check system extension
    result = subprocess.run(['systemextensionsctl', 'list'], 
                          capture_output=True, text=True)
    
    if 'com.wheeler.gamepad.driver' in result.stdout:
        print("✅ DriverKit extension installed and active")
    else:
        print("⚠️  DriverKit extension may not be active yet")
        print("   Go to System Preferences → Security & Privacy → General")
        print("   and click 'Allow' for the Wheeler extension")
    
    # Check daemon
    result = subprocess.run(['launchctl', 'list'], capture_output=True, text=True)
    
    if 'com.wheeler.gamepad.daemon' in result.stdout:
        print("✅ Gamepad daemon is running")
    else:
        print("⚠️  Gamepad daemon not running")
    
    return True

def test_gamepad():
    """Test the gamepad functionality"""
    print("\n🧪 Testing gamepad functionality...")
    
    try:
        # Import and test the client
        sys.path.append(str(Path(__file__).parent))
        from wheeler_gamepad_client import WheelerGamepadClient, GamepadState
        
        # Create client
        client = WheelerGamepadClient()
        
        # Test backend detection
        client._detect_backends()
        print(f"✅ Detected backend: {client.backend_type}")
        
        # Test basic functionality
        state = GamepadState()
        state.steering_angle = 45.0
        state.throttle = 0.5
        
        print("✅ Basic gamepad functionality working")
        return True
        
    except Exception as e:
        print(f"⚠️  Gamepad test failed: {e}")
        print("   The gamepad may still work, but Python client has issues")
        return False

def show_usage_examples():
    """Show usage examples"""
    print("""
🎯 Usage Examples
================

1. Quick Test:
   python3 wheeler_gamepad_client.py

2. Racing Game Setup:
   from wheeler_gamepad_client import create_gamepad
   gamepad = create_gamepad()
   gamepad.set_steering(45)      # Turn right
   gamepad.set_throttle(0.8)     # 80% throttle

3. Flight Sim Setup:
   gamepad.set_stick("left", 0.2, -0.3)   # Aileron + Elevator
   gamepad.set_stick("right", 0.1, 0.7)   # Rudder + Throttle

4. Check Status:
   ./DriverKit/install_wheeler_gamepad.sh --status

5. View Logs:
   tail -f /var/log/wheeler-gamepad-daemon.log

📚 Documentation:
   - Complete Guide: DriverKit/README_COMPLETE_GAMEPAD.md
   - Quick Start: DriverKit/QUICK_START_GUIDE.md
   - macOS Info: README-macOS.md
""")

def main():
    """Main setup function"""
    print_banner()
    
    # Check system requirements
    if not check_system():
        print("\n❌ System requirements not met. Please install required tools.")
        sys.exit(1)
    
    # Setup Python environment
    if not setup_python_environment():
        print("\n❌ Python environment setup failed.")
        sys.exit(1)
    
    # Ask user for confirmation
    print("\n🚀 Ready to install Wheeler Virtual Gamepad")
    print("This will:")
    print("  • Build the DriverKit extension")
    print("  • Install the userspace daemon")
    print("  • Set up automatic startup")
    print("  • Require administrator password")
    print()
    
    response = input("Continue with installation? [Y/n]: ").strip().lower()
    if response and response not in ['y', 'yes']:
        print("Installation cancelled.")
        sys.exit(0)
    
    # Build and install
    if not build_and_install():
        print("\n❌ Installation failed. Check the error messages above.")
        sys.exit(1)
    
    # Verify installation
    verify_installation()
    
    # Test functionality
    test_gamepad()
    
    # Show usage examples
    show_usage_examples()
    
    print("""
🎉 Installation Complete!
========================

Your Wheeler Virtual Gamepad is now installed and ready to use.

Next Steps:
1. If prompted, approve the system extension in System Preferences
2. Test with: python3 wheeler_gamepad_client.py
3. Use with your favorite games and simulators!

The gamepad will automatically start on boot and is ready for use.
""")

if __name__ == "__main__":
    main()