#!/bin/bash

# Wheeler Virtual Gamepad Installer - Manual Code Signing Version
# This version uses manual code signing to avoid Xcode account issues

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

log_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTENSION_DIR="$SCRIPT_DIR/WheelerGamepadDriver"
DAEMON_DIR="$SCRIPT_DIR/WheelerGamepadDaemon"
BUILD_DIR="$SCRIPT_DIR/build"
INSTALL_DIR="/Library/SystemExtensions"
DAEMON_INSTALL_DIR="/usr/local/bin"

# Default values
DEV_TEAM=""
CLEAN_BUILD=false
VERBOSE=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dev-team)
            DEV_TEAM="$2"
            shift 2
            ;;
        --clean)
            CLEAN_BUILD=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --dev-team TEAM_ID    Apple Developer Team ID (required)"
            echo "  --clean               Clean build directories before building"
            echo "  --verbose             Enable verbose output"
            echo "  --help                Show this help message"
            echo ""
            echo "Example:"
            echo "  $0 --dev-team TY24SSPQG3 --clean"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate required parameters
if [[ -z "$DEV_TEAM" ]]; then
    log_error "Development team ID is required. Use --dev-team TEAM_ID"
    exit 1
fi

log_info "Installing Wheeler Virtual Gamepad for macOS..."
log_info "Running on macOS $(sw_vers -productVersion)"

# Check system requirements
check_requirements() {
    log_step "Checking requirements..."
    
    # Check macOS version
    local version=$(sw_vers -productVersion | cut -d. -f1)
    if [[ $version -lt 10 ]]; then
        log_error "macOS 10.15 or later required"
        exit 1
    fi
    
    # Check for Xcode command line tools
    if ! xcode-select -p &> /dev/null; then
        log_error "Xcode command line tools not found. Install with: xcode-select --install"
        exit 1
    fi
    
    # Check for xcodebuild
    if ! command -v xcodebuild &> /dev/null; then
        log_error "xcodebuild not found. Please install Xcode."
        exit 1
    fi
    
    # Check for make
    if ! command -v make &> /dev/null; then
        log_error "make not found. Please install build tools."
        exit 1
    fi
    
    # Check for codesign
    if ! command -v codesign &> /dev/null; then
        log_error "codesign not found. Please install Xcode."
        exit 1
    fi
    
    # Check for systemextensionsctl
    if ! command -v systemextensionsctl &> /dev/null; then
        log_error "systemextensionsctl not found. This requires macOS 10.15+"
        exit 1
    fi
    
    # Verify development certificates
    local cert_count=$(security find-identity -v -p codesigning | grep "Apple Development.*($DEV_TEAM)" | wc -l)
    if [[ $cert_count -eq 0 ]]; then
        log_error "No Apple Development certificates found for team $DEV_TEAM"
        log_error "Please ensure your certificates are installed in Keychain Access"
        exit 1
    fi
    
    log_success "All requirements met"
}

# Find the best certificate for signing
find_signing_identity() {
    local identity=$(security find-identity -v -p codesigning | grep "Apple Development.*($DEV_TEAM)" | head -1 | awk '{print $2}')
    if [[ -z "$identity" ]]; then
        log_error "Could not find signing identity for team $DEV_TEAM"
        exit 1
    fi
    echo "$identity"
}

# Build DriverKit extension with manual signing
build_extension() {
    log_step "Building DriverKit extension..."
    
    if [[ ! -d "$EXTENSION_DIR" ]]; then
        log_error "Extension directory not found: $EXTENSION_DIR"
        exit 1
    fi
    
    cd "$EXTENSION_DIR"
    
    # Clean previous builds if requested
    if [[ "$CLEAN_BUILD" == "true" ]]; then
        rm -rf build/
        log_info "Cleaned previous build"
    fi
    
    # Build without automatic signing first
    local build_args="-project WheelerGamepadDriver.xcodeproj -scheme WheelerGamepadDriver -configuration Release"
    build_args="$build_args CODE_SIGN_STYLE=Manual"
    build_args="$build_args CODE_SIGN_IDENTITY="
    build_args="$build_args DEVELOPMENT_TEAM=$DEV_TEAM"
    
    if [[ "$VERBOSE" == "true" ]]; then
        xcodebuild $build_args build
    else
        xcodebuild $build_args build > /dev/null 2>&1
    fi
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to build DriverKit extension"
        exit 1
    fi
    
    # Find the built extension
    local extension_path=$(find build -name "*.dext" -type d | head -1)
    if [[ ! -d "$extension_path" ]]; then
        log_error "Built extension not found"
        exit 1
    fi
    
    # Manual code signing
    log_info "Manually signing DriverKit extension..."
    local signing_identity=$(find_signing_identity)
    
    codesign --force --sign "$signing_identity" \
             --entitlements "WheelerGamepadDriver/WheelerGamepadDriver.entitlements" \
             --timestamp \
             --options runtime \
             "$extension_path"
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to sign DriverKit extension"
        exit 1
    fi
    
    # Verify signature
    codesign --verify --verbose "$extension_path"
    if [[ $? -ne 0 ]]; then
        log_error "Extension signature verification failed"
        exit 1
    fi
    
    log_success "DriverKit extension built and signed successfully"
    echo "Extension path: $extension_path"
}

# Build daemon
build_daemon() {
    log_step "Building userspace daemon..."
    
    if [[ ! -d "$DAEMON_DIR" ]]; then
        log_error "Daemon directory not found: $DAEMON_DIR"
        exit 1
    fi
    
    cd "$DAEMON_DIR"
    
    if [[ "$CLEAN_BUILD" == "true" ]]; then
        make clean > /dev/null 2>&1
    fi
    
    if [[ "$VERBOSE" == "true" ]]; then
        make
    else
        make > /dev/null 2>&1
    fi
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to build daemon"
        exit 1
    fi
    
    # Sign the daemon
    log_info "Signing userspace daemon..."
    local signing_identity=$(find_signing_identity)
    
    codesign --force --sign "$signing_identity" \
             --timestamp \
             --options runtime \
             "WheelerGamepadDaemon"
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to sign daemon"
        exit 1
    fi
    
    log_success "Userspace daemon built and signed successfully"
}

# Install system extension
install_extension() {
    log_step "Installing system extension..."
    
    cd "$EXTENSION_DIR"
    local extension_path=$(find build -name "*.dext" -type d | head -1)
    
    if [[ ! -d "$extension_path" ]]; then
        log_error "Extension not found for installation"
        exit 1
    fi
    
    # Copy extension to system location
    sudo mkdir -p "$INSTALL_DIR"
    sudo cp -R "$extension_path" "$INSTALL_DIR/"
    
    local extension_name=$(basename "$extension_path")
    local installed_path="$INSTALL_DIR/$extension_name"
    
    # Set proper permissions
    sudo chown -R root:wheel "$installed_path"
    sudo chmod -R 755 "$installed_path"
    
    log_success "System extension installed to: $installed_path"
    
    # Activate the extension
    log_info "Activating system extension..."
    log_warning "You may need to approve the system extension in System Preferences > Security & Privacy"
    
    systemextensionsctl developer on
    systemextensionsctl install "$installed_path"
    
    log_success "System extension activation requested"
}

# Install daemon
install_daemon() {
    log_step "Installing userspace daemon..."
    
    cd "$DAEMON_DIR"
    
    if [[ ! -f "WheelerGamepadDaemon" ]]; then
        log_error "Daemon executable not found"
        exit 1
    fi
    
    # Install daemon
    sudo cp "WheelerGamepadDaemon" "$DAEMON_INSTALL_DIR/"
    sudo chmod +x "$DAEMON_INSTALL_DIR/WheelerGamepadDaemon"
    
    log_success "Userspace daemon installed to: $DAEMON_INSTALL_DIR/WheelerGamepadDaemon"
    
    # Create launch daemon plist
    local plist_path="/Library/LaunchDaemons/com.wheeler.gamepad.daemon.plist"
    sudo tee "$plist_path" > /dev/null << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.wheeler.gamepad.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>$DAEMON_INSTALL_DIR/WheelerGamepadDaemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/wheeler-gamepad-daemon.log</string>
    <key>StandardErrorPath</key>
    <string>/var/log/wheeler-gamepad-daemon.log</string>
</dict>
</plist>
EOF
    
    # Load the daemon
    sudo launchctl load "$plist_path"
    
    log_success "Daemon service installed and started"
}

# Main installation process
main() {
    check_requirements
    build_extension
    build_daemon
    install_extension
    install_daemon
    
    log_success "Wheeler Virtual Gamepad installation completed!"
    echo ""
    echo "Next steps:"
    echo "1. Go to System Preferences > Security & Privacy > General"
    echo "2. Click 'Allow' for the Wheeler Gamepad system extension"
    echo "3. Test the gamepad using: python3 wheeler_gamepad_client.py"
    echo ""
    echo "The daemon is now running and will start automatically on boot."
}

# Run main function
main "$@"