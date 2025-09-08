# Makefile for Wheeler Gamepad Daemon
# macOS DriverKit userspace daemon

CXX = clang++
CXXFLAGS = -std=c++17 -O2 -Wall -Wextra
FRAMEWORKS = -framework IOKit -framework CoreFoundation
TARGET = WheelerGamepadDaemon
SOURCE = WheelerGamepadDaemon.cpp

# Installation paths
INSTALL_DIR = /usr/local/bin
LAUNCHD_DIR = /Library/LaunchDaemons
PLIST_FILE = com.wheeler.gamepad.daemon.plist

.PHONY: all clean install uninstall start stop status

all: $(TARGET)

$(TARGET): $(SOURCE)
	$(CXX) $(CXXFLAGS) $(FRAMEWORKS) -o $(TARGET) $(SOURCE)

clean:
	rm -f $(TARGET)

install: $(TARGET)
	@echo "Installing Wheeler Gamepad Daemon..."
	sudo cp $(TARGET) $(INSTALL_DIR)/
	sudo chmod +x $(INSTALL_DIR)/$(TARGET)
	@echo "Creating launch daemon plist..."
	sudo tee $(LAUNCHD_DIR)/$(PLIST_FILE) > /dev/null << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.wheeler.gamepad.daemon</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/WheelerGamepadDaemon</string>
        <string>--daemon</string>
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
	sudo chmod 644 $(LAUNCHD_DIR)/$(PLIST_FILE)
	@echo "Installation complete. Use 'make start' to start the daemon."

uninstall:
	@echo "Uninstalling Wheeler Gamepad Daemon..."
	sudo launchctl unload $(LAUNCHD_DIR)/$(PLIST_FILE) 2>/dev/null || true
	sudo rm -f $(LAUNCHD_DIR)/$(PLIST_FILE)
	sudo rm -f $(INSTALL_DIR)/$(TARGET)
	@echo "Uninstallation complete."

start:
	@echo "Starting Wheeler Gamepad Daemon..."
	sudo launchctl load $(LAUNCHD_DIR)/$(PLIST_FILE)
	@echo "Daemon started."

stop:
	@echo "Stopping Wheeler Gamepad Daemon..."
	sudo launchctl unload $(LAUNCHD_DIR)/$(PLIST_FILE)
	@echo "Daemon stopped."

status:
	@echo "Wheeler Gamepad Daemon status:"
	@sudo launchctl list | grep com.wheeler.gamepad.daemon || echo "Daemon not running"

test: $(TARGET)
	@echo "Testing daemon (run in foreground)..."
	./$(TARGET)