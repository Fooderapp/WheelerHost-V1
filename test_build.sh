#!/bin/bash

# Test build script for Wheeler Gamepad DriverKit extension
# This script tests the build process with your Apple Developer Team ID

set -e

echo "🔨 Testing Wheeler Gamepad DriverKit Build"
echo "=========================================="

# Your Apple Developer Team ID
TEAM_ID="TY24SSPQG3"

echo "📁 Navigating to DriverKit directory..."
cd DriverKit/WheelerGamepadDriver

echo "🔍 Checking Xcode project structure..."
if [ ! -f "WheelerGamepadDriver.xcodeproj/project.pbxproj" ]; then
    echo "❌ ERROR: Xcode project file missing!"
    exit 1
fi

if [ ! -f "WheelerGamepadDriver.xcodeproj/xcshareddata/xcschemes/WheelerGamepadDriver.xcscheme" ]; then
    echo "❌ ERROR: Xcode scheme file missing!"
    exit 1
fi

echo "✅ Xcode project structure looks good"

echo "🏗️  Testing build with your team ID: $TEAM_ID"
echo "Command: xcodebuild -project WheelerGamepadDriver.xcodeproj -scheme WheelerGamepadDriver -configuration Release -allowProvisioningUpdates DEVELOPMENT_TEAM=$TEAM_ID build"

# Test the build command (this will work on macOS with Xcode installed)
if command -v xcodebuild >/dev/null 2>&1; then
    echo "✅ xcodebuild found, attempting build..."
    xcodebuild -project WheelerGamepadDriver.xcodeproj -scheme WheelerGamepadDriver -configuration Release -allowProvisioningUpdates DEVELOPMENT_TEAM=$TEAM_ID build
    echo "🎉 Build completed successfully!"
else
    echo "⚠️  xcodebuild not found (this is expected in non-macOS environments)"
    echo "✅ Project structure is ready for building on macOS"
fi

echo ""
echo "🎮 Wheeler Gamepad DriverKit Extension Ready!"
echo "============================================="
echo "To build on macOS:"
echo "1. Navigate to: DriverKit/WheelerGamepadDriver/"
echo "2. Run: xcodebuild -project WheelerGamepadDriver.xcodeproj -scheme WheelerGamepadDriver -configuration Release -allowProvisioningUpdates DEVELOPMENT_TEAM=TY24SSPQG3 build"
echo "3. Or use the automated installer: ./install_wheeler_gamepad.sh --dev-team TY24SSPQG3"
echo ""
echo "The build will create: WheelerGamepadDriver.dext"
echo "This is your native DriverKit system extension for macOS Sequoia!"