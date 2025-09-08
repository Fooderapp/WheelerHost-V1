#!/bin/bash
#
# Wheeler Virtual Gamepad Installation Script
# Installs DriverKit extension and userspace daemon for macOS Sequoia
#
# Usage: ./install_wheeler_gamepad.sh [--uninstall] [--dev-team TEAM_ID]
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTENSION_NAME="WheelerGamepadDriver"
DAEMON_NAME="WheelerGamepadDaemon"
BUNDLE_ID="com.wheeler.gamepad.driver"
DAEMON_BUNDLE_ID="com.wheeler.gamepad.daemon"

# Paths
EXTENSION_DIR="$SCRIPT_DIR/WheelerGamepadDriver"
DAEMON_DIR="$SCRIPT_DIR/WheelerGamepadDaemon"
BUILD_DIR="$SCRIPT_DIR/build"
SYSTEM_EXTENSIONS_DIR="/Library/SystemExtensions"
DAEMON_INSTALL_DIR="/usr/local/bin"
LAUNCHD_DIR="/Library/LaunchDaemons"

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

# Check if running on macOS
check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        log_error "This script only works on macOS"
        exit 1
    fi
    
    # Check macOS version (requires 10.15+ for DriverKit)
    local version=$(sw_vers -productVersion)
    local major=$(echo $version | cut -d. -f1)
    local minor=$(echo $version | cut -d. -f2)
    
    if [[ $major -lt 10 ]] || [[ $major -eq 10 && $minor -lt 15 ]]; then
        log_error "macOS 10.15 (Catalina) or later is required for DriverKit"
        exit 1
    fi
    
    log_info "Running on macOS $version"
}

# Check for required tools
check_requirements() {
    log_info "Checking requirements..."
    
    # Check for Xcode command line tools
    if ! xcode-select -p &> /dev/null; then
        log_error "Xcode command line tools not found. Install with: xcode-select --install"
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
    
    log_success "All requirements met"
}

# Get development team ID
get_dev_team() {
    if [[ -n "$DEV_TEAM" ]]; then
        echo "$DEV_TEAM"
        return
    fi
    
    # Try to find development team from keychain
    local teams=$(security find-identity -v -p codesigning | grep "Developer ID Application" | head -1 | sed 's/.*(\([^)]*\)).*/\1/')
    
    if [[ -n "$teams" ]]; then
        echo "$teams"
    else
        log_warning "No development team found. You may need to specify --dev-team TEAM_ID"
        echo ""
    fi
}

# Build DriverKit extension
build_extension() {
    log_info "Building DriverKit extension..."
    
    if [[ ! -d "$EXTENSION_DIR" ]]; then
        log_error "Extension directory not found: $EXTENSION_DIR"
        exit 1
    fi
    
    cd "$EXTENSION_DIR"
    
    # Clean previous builds
    rm -rf build/
    
    # Build the extension
    local dev_team=$(get_dev_team)
    local build_args="-project WheelerGamepadDriver.xcodeproj -scheme WheelerGamepadDriver -configuration Release -allowProvisioningUpdates"
    
    if [[ -n "$dev_team" ]]; then
        build_args="$build_args DEVELOPMENT_TEAM=$dev_team"
    fi
    
    xcodebuild $build_args build
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to build DriverKit extension"
        exit 1
    fi
    
    log_success "DriverKit extension built successfully"
}

# Build daemon
build_daemon() {
    log_info "Building userspace daemon..."
    
    if [[ ! -d "$DAEMON_DIR" ]]; then
        log_error "Daemon directory not found: $DAEMON_DIR"
        exit 1
    fi
    
    cd "$DAEMON_DIR"
    make clean
    make
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to build daemon"
        exit 1
    fi
    
    log_success "Daemon built successfully"
}

# Install DriverKit extension
install_extension() {
    log_info "Installing DriverKit extension..."
    
    # Find the built extension
    local extension_path=$(find "$EXTENSION_DIR/build" -name "*.dext" -type d | head -1)
    
    if [[ ! -d "$extension_path" ]]; then
        log_error "Built extension not found. Did the build succeed?"
        exit 1
    fi
    
    log_info "Found extension at: $extension_path"
    
    # Copy to system extensions directory (requires admin)
    sudo mkdir -p "$SYSTEM_EXTENSIONS_DIR"
    sudo cp -R "$extension_path" "$SYSTEM_EXTENSIONS_DIR/"
    
    # Activate the extension
    log_info "Activating system extension (this may take a moment)..."
    sudo systemextensionsctl install "$extension_path"
    
    # Wait for activation
    log_info "Waiting for extension to activate..."
    local timeout=30
    local count=0
    
    while [[ $count -lt $timeout ]]; do
        if systemextensionsctl list | grep -q "$BUNDLE_ID"; then
            log_success "Extension activated successfully"
            return 0
        fi
        sleep 1
        ((count++))
    done
    
    log_warning "Extension activation may still be in progress. Check with: systemextensionsctl list"
}

# Install daemon
install_daemon() {
    log_info "Installing daemon..."
    
    cd "$DAEMON_DIR"
    make install
    
    if [[ $? -ne 0 ]]; then
        log_error "Failed to install daemon"
        exit 1
    fi
    
    log_success "Daemon installed successfully"
}

# Start services
start_services() {
    log_info "Starting services..."
    
    cd "$DAEMON_DIR"
    make start
    
    # Give it a moment to start
    sleep 2
    
    # Check if daemon is running
    if make status | grep -q "com.wheeler.gamepad.daemon"; then
        log_success "Daemon started successfully"
    else
        log_warning "Daemon may not have started properly. Check logs with: tail -f /var/log/wheeler-gamepad-daemon.log"
    fi
}

# Uninstall everything
uninstall() {
    log_info "Uninstalling Wheeler Virtual Gamepad..."
    
    # Stop and remove daemon
    if [[ -d "$DAEMON_DIR" ]]; then
        cd "$DAEMON_DIR"
        make uninstall 2>/dev/null || true
    fi
    
    # Remove system extension
    local extension_path="$SYSTEM_EXTENSIONS_DIR/$EXTENSION_NAME.dext"
    if [[ -d "$extension_path" ]]; then
        log_info "Removing system extension..."
        sudo systemextensionsctl uninstall "$BUNDLE_ID" || true
        sudo rm -rf "$extension_path"
    fi
    
    # Clean up any remaining files
    sudo rm -f "$DAEMON_INSTALL_DIR/$DAEMON_NAME"
    sudo rm -f "$LAUNCHD_DIR/com.wheeler.gamepad.daemon.plist"
    
    log_success "Uninstallation complete"
}

# Show status
show_status() {
    log_info "Wheeler Virtual Gamepad Status:"
    
    echo
    echo "System Extension:"
    if systemextensionsctl list | grep -q "$BUNDLE_ID"; then
        echo "  ✅ Installed and active"
    else
        echo "  ❌ Not installed or not active"
    fi
    
    echo
    echo "Daemon:"
    if launchctl list | grep -q "com.wheeler.gamepad.daemon"; then
        echo "  ✅ Running"
    else
        echo "  ❌ Not running"
    fi
    
    echo
    echo "Log files:"
    echo "  Daemon: /var/log/wheeler-gamepad-daemon.log"
    echo "  System: /var/log/system.log (search for 'Wheeler')"
}

# Main installation function
install() {
    log_info "Installing Wheeler Virtual Gamepad for macOS..."
    
    check_macos
    check_requirements
    
    # Create build directory
    mkdir -p "$BUILD_DIR"
    
    # Build components
    build_extension
    build_daemon
    
    # Install components
    install_extension
    install_daemon
    
    # Start services
    start_services
    
    echo
    log_success "Installation complete!"
    echo
    echo "The Wheeler Virtual Gamepad is now installed and running."
    echo "It will automatically start on boot."
    echo
    echo "To check status: $0 --status"
    echo "To uninstall: $0 --uninstall"
    echo
    echo "The gamepad daemon is listening on UDP port 12000."
    echo "You can now use the Wheeler Host application to send gamepad input."
}

# Parse command line arguments
UNINSTALL=false
DEV_TEAM=""
SHOW_STATUS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --uninstall)
            UNINSTALL=true
            shift
            ;;
        --dev-team)
            DEV_TEAM="$2"
            shift 2
            ;;
        --status)
            SHOW_STATUS=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo
            echo "Options:"
            echo "  --uninstall     Uninstall Wheeler Virtual Gamepad"
            echo "  --dev-team ID   Specify development team ID for code signing"
            echo "  --status        Show installation status"
            echo "  --help, -h      Show this help message"
            echo
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Main execution
if [[ "$UNINSTALL" == true ]]; then
    uninstall
elif [[ "$SHOW_STATUS" == true ]]; then
    show_status
else
    install
fi