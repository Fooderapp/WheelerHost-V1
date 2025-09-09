//
//  WheelerGamepadDriver.h
//  Wheeler Virtual Gamepad Driver
//
//  Created by Wheeler Host on 2025-09-08.
//  Copyright © 2025 Wheeler. All rights reserved.
//

#ifndef WheelerGamepadDriver_h
#define WheelerGamepadDriver_h

#include <Availability.h>
#include <DriverKit/IOService.h>
#include <DriverKit/IOUserClient.h>
#include <HIDDriverKit/IOHIDDevice.h>
#include <HIDDriverKit/IOHIDDeviceKeys.h>

// Forward declarations
class IOBufferMemoryDescriptor;
class IOMemoryDescriptor;

// Wheeler Gamepad Driver Class
class WheelerGamepadDriver : public IOHIDDevice
{
public:
    virtual bool init() override;
    virtual kern_return_t Start(IOService* provider) override;
    virtual kern_return_t Stop(IOService* provider) override;
    virtual void free() override;
    
    // HID Device methods
    virtual OSDictionary* newDeviceDescription() override;
    virtual OSData* newReportDescriptor() override;
    virtual kern_return_t setReport(IOMemoryDescriptor* report, IOHIDReportType reportType, IOOptionBits options, uint32_t completionTimeout, OSAction* action) override;
    virtual kern_return_t getReport(IOMemoryDescriptor* report, IOHIDReportType reportType, IOOptionBits options, uint32_t completionTimeout, OSAction* action) override;
    
    // User client communication
    virtual kern_return_t NewUserClient(uint32_t type, IOUserClient** userClient) override;
    
    // Custom methods for gamepad state
    virtual kern_return_t updateGamepadState(const void* data, size_t length);
    virtual kern_return_t sendInputReport();
    
private:
    // Gamepad state structure
    struct GamepadState {
        int16_t leftStickX;     // -32768 to 32767
        int16_t leftStickY;     // -32768 to 32767
        int16_t rightStickX;    // -32768 to 32767
        int16_t rightStickY;    // -32768 to 32767
        uint8_t leftTrigger;    // 0 to 255
        uint8_t rightTrigger;   // 0 to 255
        uint16_t buttons;       // Button bitmask
        uint8_t dpad;          // D-pad state (0-8, 0=center)
    } __attribute__((packed));
    
    GamepadState m_gamepadState;
    IOBufferMemoryDescriptor* m_inputReportBuffer;
    
    // HID Report Descriptor for Xbox-style gamepad
    static const uint8_t kHIDReportDescriptor[];
    static const size_t kHIDReportDescriptorSize;
    
    // Device properties
    static constexpr uint16_t kVendorID = 0x1234;
    static constexpr uint16_t kProductID = 0x5678;
    static constexpr uint16_t kVersionNumber = 0x0100;
    static constexpr uint32_t kLocationID = 0x12345678;
};

// User Client Class for communication with userspace
class WheelerGamepadUserClient : public IOUserClient
{
public:
    virtual bool init() override;
    virtual kern_return_t Start(IOService* provider) override;
    virtual kern_return_t Stop(IOService* provider) override;
    virtual void free() override;
    
    // External methods callable from userspace
    virtual kern_return_t ExternalMethod(uint64_t selector, IOUserClientMethodArguments* arguments, const IOUserClientMethodDispatch* dispatch, OSObject* target, void* reference) override;
    
private:
    WheelerGamepadDriver* m_driver;
    
    // Method selectors
    enum {
        kWheelerGamepadUserClientMethodUpdateState = 0,
        kWheelerGamepadUserClientMethodGetState = 1,
        kWheelerGamepadUserClientMethodCount
    };
    
    // External method implementations
    static kern_return_t sUpdateGamepadState(OSObject* target, void* reference, IOUserClientMethodArguments* arguments);
    static kern_return_t sGetGamepadState(OSObject* target, void* reference, IOUserClientMethodArguments* arguments);
    
    kern_return_t updateGamepadState(IOUserClientMethodArguments* arguments);
    kern_return_t getGamepadState(IOUserClientMethodArguments* arguments);
    
    // Method dispatch table
    static const IOUserClientMethodDispatch sMethods[kWheelerGamepadUserClientMethodCount];
};

#endif /* WheelerGamepadDriver_h */