#!/usr/bin/env python3
"""
Wheeler Host Launcher
Cross-platform launcher script for Wheeler Host virtual gamepad application.
"""

import sys
import os
import platform
import subprocess

def check_dependencies():
    """Check if required dependencies are installed."""
    required_packages = ['PySide6', 'qrcode', 'PIL']
    platform_packages = {
        'darwin': ['pynput'],  # macOS
        'linux': ['pynput', 'evdev'],  # Linux
    }
    
    missing = []
    
    # Check basic requirements
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    # Check platform-specific requirements
    system = platform.system().lower()
    if system in platform_packages:
        for package in platform_packages[system]:
            try:
                __import__(package)
            except ImportError:
                missing.append(package)
    
    return missing

def install_dependencies(packages):
    """Install missing dependencies."""
    print(f"Installing missing dependencies: {', '.join(packages)}")
    
    # Map package names to pip install names
    pip_names = {
        'PIL': 'pillow',
        'PySide6': 'PySide6',
        'qrcode': 'qrcode',
        'pynput': 'pynput',
        'evdev': 'evdev'
    }
    
    pip_packages = [pip_names.get(pkg, pkg) for pkg in packages]
    
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install'] + pip_packages)
        print("Dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Failed to install dependencies: {e}")
        return False

def setup_environment():
    """Set up environment variables for the current platform."""
    system = platform.system().lower()
    
    if system == 'linux':
        # For headless Linux systems, use offscreen rendering
        if 'DISPLAY' not in os.environ:
            os.environ['QT_QPA_PLATFORM'] = 'offscreen'
            print("Set QT_QPA_PLATFORM=offscreen for headless environment")
    
    elif system == 'darwin':  # macOS
        # Set display if not present (for some macOS configurations)
        if 'DISPLAY' not in os.environ:
            os.environ['DISPLAY'] = ':0'
        print("macOS detected - ensure accessibility permissions are granted")
        print("Go to System Preferences → Security & Privacy → Privacy → Accessibility")
        print("Add Terminal.app or Python to the allowed applications list")

def main():
    """Main launcher function."""
    print("Wheeler Host - Cross-Platform Virtual Gamepad")
    print("=" * 50)
    
    # Detect platform
    system = platform.system()
    print(f"Platform: {system}")
    
    # Check dependencies
    print("Checking dependencies...")
    missing = check_dependencies()
    
    if missing:
        print(f"Missing dependencies: {', '.join(missing)}")
        response = input("Install missing dependencies? (y/n): ").lower().strip()
        
        if response in ('y', 'yes'):
            if not install_dependencies(missing):
                print("Failed to install dependencies. Please install manually:")
                print(f"pip install {' '.join(missing)}")
                return 1
        else:
            print("Cannot continue without required dependencies.")
            return 1
    else:
        print("All dependencies are installed.")
    
    # Set up environment
    setup_environment()
    
    # Launch the application
    print("\nStarting Wheeler Host...")
    print("Press Ctrl+C to stop the application")
    print("-" * 50)
    
    try:
        # Import and run the main application
        from wheeler_main import main as wheeler_main
        wheeler_main()
    except KeyboardInterrupt:
        print("\nApplication stopped by user.")
        return 0
    except ImportError as e:
        print(f"Failed to import wheeler_main: {e}")
        print("Make sure you're running this script from the Wheeler Host directory.")
        return 1
    except Exception as e:
        print(f"Application error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())