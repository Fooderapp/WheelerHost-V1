//
//  WheelerGamepadDaemon.cpp
//  Wheeler Virtual Gamepad Daemon
//
//  Created by Wheeler Host on 2025-09-08.
//  Copyright © 2025 Wheeler. All rights reserved.
//

#include <iostream>
#include <thread>
#include <chrono>
#include <atomic>
#include <signal.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <syslog.h>
#include <IOKit/IOKitLib.h>
#include <CoreFoundation/CoreFoundation.h>

// Wheeler Gamepad Driver constants
#define kWheelerGamepadDriverClassName "WheelerGamepadDriver"
#define kWheelerGamepadUserClientMethodSetState 0
#define kWheelerGamepadUserClientMethodGetState 1

// Gamepad state structure (must match driver)
struct GamepadState {
    int16_t leftStickX;      // -32768 to 32767
    int16_t leftStickY;      // -32768 to 32767
    int16_t rightStickX;     // -32768 to 32767
    int16_t rightStickY;     // -32768 to 32767
    uint8_t leftTrigger;     // 0 to 255
    uint8_t rightTrigger;    // 0 to 255
    uint16_t buttons;        // Bitmask of button states
    uint8_t dpad;           // D-pad state (0-8, 0=center)
};

// UDP packet structure for Wheeler protocol
struct WheelerUDPPacket {
    float steerAngle;        // Steering angle in degrees
    float throttle;          // Throttle 0.0 to 1.0
    float brake;            // Brake 0.0 to 1.0
    uint32_t buttons;       // Button bitmask
    float leftStickX;       // Left stick X (-1.0 to 1.0)
    float leftStickY;       // Left stick Y (-1.0 to 1.0)
    float rightStickX;      // Right stick X (-1.0 to 1.0)
    float rightStickY;      // Right stick Y (-1.0 to 1.0)
};

class WheelerGamepadDaemon {
private:
    std::atomic<bool> m_running{false};
    io_service_t m_service{0};
    io_connect_t m_connection{0};
    int m_udpSocket{-1};
    struct sockaddr_in m_serverAddr{};
    GamepadState m_currentState{};
    
    // Configuration
    static constexpr int UDP_PORT = 12000;
    static constexpr int MAX_STEER_ANGLE = 900; // degrees
    
public:
    WheelerGamepadDaemon() = default;
    ~WheelerGamepadDaemon() { cleanup(); }
    
    bool initialize() {
        // Open syslog
        openlog("WheelerGamepadDaemon", LOG_PID | LOG_CONS, LOG_DAEMON);
        syslog(LOG_INFO, "Wheeler Gamepad Daemon starting...");
        
        // Find and connect to the DriverKit extension
        if (!connectToDriver()) {
            syslog(LOG_ERR, "Failed to connect to Wheeler gamepad driver");
            return false;
        }
        
        // Setup UDP server
        if (!setupUDPServer()) {
            syslog(LOG_ERR, "Failed to setup UDP server");
            return false;
        }
        
        syslog(LOG_INFO, "Wheeler Gamepad Daemon initialized successfully");
        return true;
    }
    
    void run() {
        m_running = true;
        syslog(LOG_INFO, "Wheeler Gamepad Daemon running on UDP port %d", UDP_PORT);
        
        while (m_running) {
            processUDPMessages();
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        
        syslog(LOG_INFO, "Wheeler Gamepad Daemon stopped");
    }
    
    void stop() {
        m_running = false;
    }
    
private:
    bool connectToDriver() {
        // Create matching dictionary for our driver
        CFMutableDictionaryRef matchingDict = IOServiceMatching(kWheelerGamepadDriverClassName);
        if (!matchingDict) {
            syslog(LOG_ERR, "Failed to create matching dictionary");
            return false;
        }
        
        // Find the service
        m_service = IOServiceGetMatchingService(kIOMasterPortDefault, matchingDict);
        if (m_service == 0) {
            syslog(LOG_ERR, "Wheeler gamepad driver not found. Is the DriverKit extension loaded?");
            return false;
        }
        
        // Open connection to the service
        kern_return_t ret = IOServiceOpen(m_service, mach_task_self(), 0, &m_connection);
        if (ret != KERN_SUCCESS) {
            syslog(LOG_ERR, "Failed to open connection to driver: 0x%x", ret);
            IOObjectRelease(m_service);
            m_service = 0;
            return false;
        }
        
        syslog(LOG_INFO, "Connected to Wheeler gamepad driver");
        return true;
    }
    
    bool setupUDPServer() {
        // Create UDP socket
        m_udpSocket = socket(AF_INET, SOCK_DGRAM, 0);
        if (m_udpSocket < 0) {
            syslog(LOG_ERR, "Failed to create UDP socket");
            return false;
        }
        
        // Set socket options
        int opt = 1;
        if (setsockopt(m_udpSocket, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt)) < 0) {
            syslog(LOG_WARNING, "Failed to set SO_REUSEADDR");
        }
        
        // Bind to port
        memset(&m_serverAddr, 0, sizeof(m_serverAddr));
        m_serverAddr.sin_family = AF_INET;
        m_serverAddr.sin_addr.s_addr = INADDR_ANY;
        m_serverAddr.sin_port = htons(UDP_PORT);
        
        if (bind(m_udpSocket, (struct sockaddr*)&m_serverAddr, sizeof(m_serverAddr)) < 0) {
            syslog(LOG_ERR, "Failed to bind UDP socket to port %d", UDP_PORT);
            close(m_udpSocket);
            m_udpSocket = -1;
            return false;
        }
        
        syslog(LOG_INFO, "UDP server listening on port %d", UDP_PORT);
        return true;
    }
    
    void processUDPMessages() {
        WheelerUDPPacket packet;
        struct sockaddr_in clientAddr;
        socklen_t clientLen = sizeof(clientAddr);
        
        // Set socket to non-blocking
        fd_set readfds;
        FD_ZERO(&readfds);
        FD_SET(m_udpSocket, &readfds);
        
        struct timeval timeout;
        timeout.tv_sec = 0;
        timeout.tv_usec = 1000; // 1ms timeout
        
        int result = select(m_udpSocket + 1, &readfds, nullptr, nullptr, &timeout);
        if (result <= 0) {
            return; // No data or error
        }
        
        ssize_t bytesReceived = recvfrom(m_udpSocket, &packet, sizeof(packet), 0,
                                        (struct sockaddr*)&clientAddr, &clientLen);
        
        if (bytesReceived == sizeof(packet)) {
            updateGamepadState(packet);
            sendStateToDriver();
        }
    }
    
    void updateGamepadState(const WheelerUDPPacket& packet) {
        // Convert Wheeler protocol to gamepad state
        
        // Steering -> Left stick X
        float normalizedSteer = packet.steerAngle / MAX_STEER_ANGLE;
        normalizedSteer = std::max(-1.0f, std::min(1.0f, normalizedSteer));
        m_currentState.leftStickX = (int16_t)(normalizedSteer * 32767);
        
        // Throttle/Brake -> Right trigger/Left trigger
        m_currentState.rightTrigger = (uint8_t)(packet.throttle * 255);
        m_currentState.leftTrigger = (uint8_t)(packet.brake * 255);
        
        // Direct stick mappings
        m_currentState.leftStickY = (int16_t)(packet.leftStickY * 32767);
        m_currentState.rightStickX = (int16_t)(packet.rightStickX * 32767);
        m_currentState.rightStickY = (int16_t)(packet.rightStickY * 32767);
        
        // Button mapping
        m_currentState.buttons = (uint16_t)(packet.buttons & 0xFFFF);
        
        // D-pad (extract from buttons if needed)
        m_currentState.dpad = 0; // Center by default
    }
    
    void sendStateToDriver() {
        if (m_connection == 0) {
            return;
        }
        
        size_t outputSize = 0;
        kern_return_t ret = IOConnectCallStructMethod(
            m_connection,
            kWheelerGamepadUserClientMethodSetState,
            &m_currentState,
            sizeof(m_currentState),
            nullptr,
            &outputSize
        );
        
        if (ret != KERN_SUCCESS) {
            static int errorCount = 0;
            if (++errorCount % 1000 == 0) { // Log every 1000th error to avoid spam
                syslog(LOG_WARNING, "Failed to send state to driver: 0x%x (count: %d)", ret, errorCount);
            }
        }
    }
    
    void cleanup() {
        if (m_udpSocket >= 0) {
            close(m_udpSocket);
            m_udpSocket = -1;
        }
        
        if (m_connection != 0) {
            IOServiceClose(m_connection);
            m_connection = 0;
        }
        
        if (m_service != 0) {
            IOObjectRelease(m_service);
            m_service = 0;
        }
        
        closelog();
    }
};

// Global daemon instance for signal handling
WheelerGamepadDaemon* g_daemon = nullptr;

void signalHandler(int signal) {
    syslog(LOG_INFO, "Received signal %d, shutting down...", signal);
    if (g_daemon) {
        g_daemon->stop();
    }
}

int main(int argc, char* argv[]) {
    // Check if running as daemon
    bool daemonMode = false;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-d") == 0 || strcmp(argv[i], "--daemon") == 0) {
            daemonMode = true;
            break;
        }
    }
    
    // Daemonize if requested
    if (daemonMode) {
        pid_t pid = fork();
        if (pid < 0) {
            std::cerr << "Fork failed" << std::endl;
            return 1;
        }
        if (pid > 0) {
            return 0; // Parent exits
        }
        
        // Child continues
        setsid();
        chdir("/");
        close(STDIN_FILENO);
        close(STDOUT_FILENO);
        close(STDERR_FILENO);
    }
    
    // Setup signal handlers
    signal(SIGINT, signalHandler);
    signal(SIGTERM, signalHandler);
    signal(SIGHUP, signalHandler);
    
    // Create and run daemon
    WheelerGamepadDaemon daemon;
    g_daemon = &daemon;
    
    if (!daemon.initialize()) {
        std::cerr << "Failed to initialize Wheeler Gamepad Daemon" << std::endl;
        return 1;
    }
    
    daemon.run();
    
    return 0;
}