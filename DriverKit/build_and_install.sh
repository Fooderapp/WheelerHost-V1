#!/bin/bash
# build_and_install.sh
# Build and install the Wheeler DriverKit virtual gamepad extension

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR/WheelerGamepadDriver"
BUILD_DIR="$PROJECT_DIR/build"

echo "Wheeler DriverKit Virtual Gamepad - Build and Install Script"
echo "============================================================"

# Check if we're on macOS
if [[ "$(uname)" != "Darwin" ]]; then
    echo "Error: This script must be run on macOS"
    exit 1
fi

# Check if Xcode is installed
if ! command -v xcodebuild &> /dev/null; then
    echo "Error: Xcode command line tools are required"
    echo "Install with: xcode-select --install"
    exit 1
fi

# Check for Apple Developer account setup
echo "Checking for Apple Developer account setup..."
if ! security find-identity -v -p codesigning | grep -q "Developer ID"; then
    echo "Warning: No Developer ID certificate found"
    echo "You'll need to:"
    echo "1. Have an Apple Developer account"
    echo "2. Install your Developer ID certificate in Keychain"
    echo "3. Update the DEVELOPMENT_TEAM in the Xcode project"
fi

# Create build directory
mkdir -p "$BUILD_DIR"

echo "Building Wheeler DriverKit extension..."
cd "$PROJECT_DIR"

# Build the extension
xcodebuild -project WheelerGamepadDriver.xcodeproj \
           -target WheelerGamepadDriver \
           -configuration Release \
           -derivedDataPath "$BUILD_DIR" \
           build

if [ $? -ne 0 ]; then
    echo "Error: Build failed"
    exit 1
fi

echo "Build completed successfully!"

# Find the built extension
DEXT_PATH=$(find "$BUILD_DIR" -name "*.dext" -type d | head -1)
if [ -z "$DEXT_PATH" ]; then
    echo "Error: Could not find built .dext file"
    exit 1
fi

echo "Built extension: $DEXT_PATH"

# Installation
echo ""
echo "Installing Wheeler DriverKit extension..."
echo "This requires administrator privileges."

# Copy to system extensions directory
SYSTEM_EXT_DIR="/Library/SystemExtensions"
INSTALL_DIR="$SYSTEM_EXT_DIR/$(basename "$DEXT_PATH")"

sudo mkdir -p "$SYSTEM_EXT_DIR"
sudo rm -rf "$INSTALL_DIR"
sudo cp -R "$DEXT_PATH" "$SYSTEM_EXT_DIR/"

echo "Extension copied to: $INSTALL_DIR"

# Load the extension
echo "Loading extension..."
sudo systemextensionsctl developer on
sudo systemextensionsctl load "$INSTALL_DIR"

echo ""
echo "Installation completed!"
echo ""
echo "Next steps:"
echo "1. You may need to approve the system extension in System Preferences"
echo "2. Go to System Preferences > Security & Privacy > General"
echo "3. Click 'Allow' for the Wheeler extension if prompted"
echo "4. The extension should now be available for the Wheeler Host application"
echo ""
echo "To uninstall later, run:"
echo "sudo systemextensionsctl uninstall com.wheeler.gamepad.driver"