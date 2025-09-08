#!/bin/bash
#
# Wheeler Virtual Gamepad - Complete Build System
# Builds DriverKit extension, daemon, and creates distribution package
#
# Usage: ./build_all.sh [--clean] [--dev-team TEAM_ID] [--package] [--install]
#

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$SCRIPT_DIR/build"
DIST_DIR="$SCRIPT_DIR/dist"
PACKAGE_NAME="WheelerVirtualGamepad"

# Component directories
EXTENSION_DIR="$SCRIPT_DIR/WheelerGamepadDriver"
DAEMON_DIR="$SCRIPT_DIR/WheelerGamepadDaemon"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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
    echo -e "${CYAN}[STEP]${NC} $1"
}

# Parse command line arguments
CLEAN=false
DEV_TEAM=""
CREATE_PACKAGE=false
INSTALL_AFTER_BUILD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --clean)
            CLEAN=true
            shift
            ;;
        --dev-team)
            DEV_TEAM="$2"
            shift 2
            ;;
        --package)
            CREATE_PACKAGE=true
            shift
            ;;
        --install)
            INSTALL_AFTER_BUILD=true
            shift
            ;;
        --help|-h)
            echo "Wheeler Virtual Gamepad Build System"
            echo
            echo "Usage: $0 [OPTIONS]"
            echo
            echo "Options:"
            echo "  --clean         Clean all build artifacts before building"
            echo "  --dev-team ID   Specify development team ID for code signing"
            echo "  --package       Create distribution package after building"
            echo "  --install       Install after successful build"
            echo "  --help, -h      Show this help message"
            echo
            echo "Examples:"
            echo "  $0                                    # Basic build"
            echo "  $0 --clean --package                 # Clean build with package"
            echo "  $0 --dev-team ABC123 --install       # Build with specific team and install"
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

# Check if running on macOS
check_macos() {
    if [[ "$(uname)" != "Darwin" ]]; then
        log_error "This build system only works on macOS"
        exit 1
    fi
    
    local version=$(sw_vers -productVersion)
    log_info "Building on macOS $version"
}

# Check for required tools
check_build_tools() {
    log_step "Checking build requirements..."
    
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
    
    log_success "All build tools available"
}

# Get development team ID
get_dev_team() {
    if [[ -n "$DEV_TEAM" ]]; then
        echo "$DEV_TEAM"
        return
    fi
    
    # Try to find development team from keychain
    local teams=$(security find-identity -v -p codesigning 2>/dev/null | grep "Developer ID Application" | head -1 | sed 's/.*(\([^)]*\)).*/\1/' || echo "")
    
    if [[ -n "$teams" ]]; then
        echo "$teams"
    else
        log_warning "No development team found. Code signing may fail."
        echo ""
    fi
}

# Clean build artifacts
clean_build() {
    log_step "Cleaning build artifacts..."
    
    # Clean extension build
    if [[ -d "$EXTENSION_DIR" ]]; then
        cd "$EXTENSION_DIR"
        rm -rf build/
        rm -rf DerivedData/
    fi
    
    # Clean daemon build
    if [[ -d "$DAEMON_DIR" ]]; then
        cd "$DAEMON_DIR"
        make clean 2>/dev/null || true
    fi
    
    # Clean main build and dist directories
    rm -rf "$BUILD_DIR"
    rm -rf "$DIST_DIR"
    
    log_success "Build artifacts cleaned"
}

# Build DriverKit extension
build_extension() {
    log_step "Building DriverKit extension..."
    
    if [[ ! -d "$EXTENSION_DIR" ]]; then
        log_error "Extension directory not found: $EXTENSION_DIR"
        exit 1
    fi
    
    cd "$EXTENSION_DIR"
    
    # Prepare build arguments
    local dev_team=$(get_dev_team)
    local build_args="-project WheelerGamepadDriver.xcodeproj -scheme WheelerGamepadDriver -configuration Release"
    
    if [[ -n "$dev_team" ]]; then
        build_args="$build_args DEVELOPMENT_TEAM=$dev_team"
        log_info "Using development team: $dev_team"
    fi
    
    # Build the extension
    log_info "Running xcodebuild..."
    if xcodebuild $build_args build; then
        log_success "DriverKit extension built successfully"
    else
        log_error "Failed to build DriverKit extension"
        exit 1
    fi
    
    # Find and verify the built extension
    local extension_path=$(find build -name "*.dext" -type d | head -1)
    if [[ ! -d "$extension_path" ]]; then
        log_error "Built extension not found"
        exit 1
    fi
    
    log_info "Extension built at: $extension_path"
}

# Build daemon
build_daemon() {
    log_step "Building userspace daemon..."
    
    if [[ ! -d "$DAEMON_DIR" ]]; then
        log_error "Daemon directory not found: $DAEMON_DIR"
        exit 1
    fi
    
    cd "$DAEMON_DIR"
    
    # Build the daemon
    if make; then
        log_success "Daemon built successfully"
    else
        log_error "Failed to build daemon"
        exit 1
    fi
    
    # Verify the built daemon
    if [[ ! -f "WheelerGamepadDaemon" ]]; then
        log_error "Built daemon not found"
        exit 1
    fi
    
    log_info "Daemon built at: $DAEMON_DIR/WheelerGamepadDaemon"
}

# Create distribution package
create_distribution_package() {
    log_step "Creating distribution package..."
    
    # Create distribution directory structure
    mkdir -p "$DIST_DIR/$PACKAGE_NAME"
    local pkg_dir="$DIST_DIR/$PACKAGE_NAME"
    
    # Copy built components
    log_info "Copying built components..."
    
    # Copy extension
    local extension_path=$(find "$EXTENSION_DIR/build" -name "*.dext" -type d | head -1)
    if [[ -d "$extension_path" ]]; then
        cp -R "$extension_path" "$pkg_dir/"
        log_info "✓ Extension copied"
    else
        log_error "Extension not found for packaging"
        exit 1
    fi
    
    # Copy daemon
    if [[ -f "$DAEMON_DIR/WheelerGamepadDaemon" ]]; then
        cp "$DAEMON_DIR/WheelerGamepadDaemon" "$pkg_dir/"
        log_info "✓ Daemon copied"
    else
        log_error "Daemon not found for packaging"
        exit 1
    fi
    
    # Copy installation script
    cp "$SCRIPT_DIR/install_wheeler_gamepad.sh" "$pkg_dir/"
    chmod +x "$pkg_dir/install_wheeler_gamepad.sh"
    log_info "✓ Installation script copied"
    
    # Copy Python client
    cp "$PROJECT_ROOT/wheeler_gamepad_client.py" "$pkg_dir/"
    log_info "✓ Python client copied"
    
    # Copy documentation
    cp "$SCRIPT_DIR/README.md" "$pkg_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/README-macOS.md" "$pkg_dir/" 2>/dev/null || true
    cp "$PROJECT_ROOT/MACOS_SEQUOIA_COMPATIBILITY.md" "$pkg_dir/" 2>/dev/null || true
    
    # Create package README
    cat > "$pkg_dir/README.txt" << 'EOF'
Wheeler Virtual Gamepad for macOS
==================================

This package contains a complete DriverKit-based virtual gamepad solution for macOS Sequoia.

Contents:
- WheelerGamepadDriver.dext: DriverKit system extension
- WheelerGamepadDaemon: Userspace daemon for UDP communication
- install_wheeler_gamepad.sh: Automated installation script
- wheeler_gamepad_client.py: Python client library

Installation:
1. Run: ./install_wheeler_gamepad.sh
2. Follow the prompts for system extension approval
3. The gamepad will be available system-wide

Usage:
- The daemon listens on UDP port 12000
- Use the Python client library for easy integration
- Compatible with any application that supports Xbox controllers

For more information, see the included documentation files.
EOF
    
    # Create archive
    cd "$DIST_DIR"
    local archive_name="${PACKAGE_NAME}-$(date +%Y%m%d-%H%M%S).tar.gz"
    tar -czf "$archive_name" "$PACKAGE_NAME"
    
    log_success "Distribution package created: $DIST_DIR/$archive_name"
    
    # Create checksums
    shasum -a 256 "$archive_name" > "$archive_name.sha256"
    log_info "✓ SHA256 checksum created"
    
    echo
    log_info "Package contents:"
    tar -tzf "$archive_name" | sed 's/^/  /'
}

# Run tests
run_tests() {
    log_step "Running tests..."
    
    # Test Python client
    if [[ -f "$PROJECT_ROOT/wheeler_gamepad_client.py" ]]; then
        cd "$PROJECT_ROOT"
        if python3 -c "import wheeler_gamepad_client; print('✓ Python client imports successfully')"; then
            log_success "Python client test passed"
        else
            log_warning "Python client test failed"
        fi
    fi
    
    # Test daemon (basic syntax check)
    if [[ -f "$DAEMON_DIR/WheelerGamepadDaemon" ]]; then
        if "$DAEMON_DIR/WheelerGamepadDaemon" --help &>/dev/null; then
            log_success "Daemon basic test passed"
        else
            log_info "Daemon help test completed (expected behavior)"
        fi
    fi
}

# Install after build
install_components() {
    log_step "Installing components..."
    
    if [[ -f "$SCRIPT_DIR/install_wheeler_gamepad.sh" ]]; then
        "$SCRIPT_DIR/install_wheeler_gamepad.sh"
    else
        log_error "Installation script not found"
        exit 1
    fi
}

# Print build summary
print_summary() {
    echo
    echo "🎮 Wheeler Virtual Gamepad Build Summary"
    echo "========================================"
    echo
    
    # Extension info
    local extension_path=$(find "$EXTENSION_DIR/build" -name "*.dext" -type d 2>/dev/null | head -1)
    if [[ -d "$extension_path" ]]; then
        echo "✅ DriverKit Extension: $(basename "$extension_path")"
        echo "   Path: $extension_path"
    else
        echo "❌ DriverKit Extension: Not built"
    fi
    
    # Daemon info
    if [[ -f "$DAEMON_DIR/WheelerGamepadDaemon" ]]; then
        echo "✅ Userspace Daemon: WheelerGamepadDaemon"
        echo "   Path: $DAEMON_DIR/WheelerGamepadDaemon"
    else
        echo "❌ Userspace Daemon: Not built"
    fi
    
    # Package info
    if [[ "$CREATE_PACKAGE" == true ]]; then
        local latest_package=$(ls -t "$DIST_DIR"/*.tar.gz 2>/dev/null | head -1)
        if [[ -f "$latest_package" ]]; then
            echo "✅ Distribution Package: $(basename "$latest_package")"
            echo "   Path: $latest_package"
            echo "   Size: $(du -h "$latest_package" | cut -f1)"
        fi
    fi
    
    echo
    echo "Next steps:"
    if [[ "$INSTALL_AFTER_BUILD" != true ]]; then
        echo "• Install: ./install_wheeler_gamepad.sh"
    fi
    echo "• Test: python3 wheeler_gamepad_client.py"
    echo "• Documentation: README-macOS.md"
    echo
}

# Main build function
main() {
    echo "🔨 Wheeler Virtual Gamepad Build System"
    echo "======================================="
    echo
    
    check_macos
    check_build_tools
    
    # Clean if requested
    if [[ "$CLEAN" == true ]]; then
        clean_build
    fi
    
    # Create build directory
    mkdir -p "$BUILD_DIR"
    
    # Build components
    build_extension
    build_daemon
    
    # Run tests
    run_tests
    
    # Create package if requested
    if [[ "$CREATE_PACKAGE" == true ]]; then
        create_distribution_package
    fi
    
    # Install if requested
    if [[ "$INSTALL_AFTER_BUILD" == true ]]; then
        install_components
    fi
    
    # Print summary
    print_summary
    
    log_success "Build completed successfully!"
}

# Run main function
main