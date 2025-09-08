//
//  WheelerGamepadDriver.cpp
//  Wheeler Virtual Gamepad Driver
//
//  Created by Wheeler Host on 2025-09-08.
//  Copyright © 2025 Wheeler. All rights reserved.
//

#include "WheelerGamepadDriver.h"
#include <DriverKit/IOLib.h>
#include <DriverKit/IOBufferMemoryDescriptor.h>
#include <DriverKit/OSCollections.h>
#include <HIDDriverKit/IOHIDKeys.h>

// HID Report Descriptor for Xbox-style gamepad
const uint8_t WheelerGamepadDriver::kHIDReportDescriptor[] = {
    0x05, 0x01,        // Usage Page (Generic Desktop Ctrls)
    0x09, 0x05,        // Usage (Game Pad)
    0xA1, 0x01,        // Collection (Application)
    0x85, 0x01,        //   Report ID (1)
    
    // Left and Right Sticks
    0x09, 0x01,        //   Usage (Pointer)
    0xA1, 0x00,        //   Collection (Physical)
    0x09, 0x30,        //     Usage (X)
    0x09, 0x31,        //     Usage (Y)
    0x15, 0x00,        //     Logical Minimum (0)
    0x26, 0xFF, 0xFF,  //     Logical Maximum (65535)
    0x35, 0x00,        //     Physical Minimum (0)
    0x46, 0xFF, 0xFF,  //     Physical Maximum (65535)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x02,        //     Report Count (2)
    0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
    0xC0,              //   End Collection
    
    0x09, 0x01,        //   Usage (Pointer)
    0xA1, 0x00,        //   Collection (Physical)
    0x09, 0x33,        //     Usage (Rx)
    0x09, 0x34,        //     Usage (Ry)
    0x15, 0x00,        //     Logical Minimum (0)
    0x26, 0xFF, 0xFF,  //     Logical Maximum (65535)
    0x35, 0x00,        //     Physical Minimum (0)
    0x46, 0xFF, 0xFF,  //     Physical Maximum (65535)
    0x75, 0x10,        //     Report Size (16)
    0x95, 0x02,        //     Report Count (2)
    0x81, 0x02,        //     Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
    0xC0,              //   End Collection
    
    // Triggers
    0x09, 0x32,        //   Usage (Z)
    0x09, 0x35,        //   Usage (Rz)
    0x15, 0x00,        //   Logical Minimum (0)
    0x25, 0xFF,        //   Logical Maximum (255)
    0x35, 0x00,        //   Physical Minimum (0)
    0x45, 0xFF,        //   Physical Maximum (255)
    0x75, 0x08,        //   Report Size (8)
    0x95, 0x02,        //   Report Count (2)
    0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
    
    // Buttons
    0x05, 0x09,        //   Usage Page (Button)
    0x19, 0x01,        //   Usage Minimum (0x01)
    0x29, 0x10,        //   Usage Maximum (0x10)
    0x15, 0x00,        //   Logical Minimum (0)
    0x25, 0x01,        //   Logical Maximum (1)
    0x75, 0x01,        //   Report Size (1)
    0x95, 0x10,        //   Report Count (16)
    0x81, 0x02,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,No Null Position)
    
    // D-pad
    0x05, 0x01,        //   Usage Page (Generic Desktop Ctrls)
    0x09, 0x39,        //   Usage (Hat switch)
    0x15, 0x00,        //   Logical Minimum (0)
    0x25, 0x07,        //   Logical Maximum (7)
    0x35, 0x00,        //   Physical Minimum (0)
    0x46, 0x3B, 0x01,  //   Physical Maximum (315)
    0x65, 0x14,        //   Unit (System: English Rotation, Length: Centimeter)
    0x75, 0x04,        //   Report Size (4)
    0x95, 0x01,        //   Report Count (1)
    0x81, 0x42,        //   Input (Data,Var,Abs,No Wrap,Linear,Preferred State,Null State)
    
    // Padding
    0x75, 0x04,        //   Report Size (4)
    0x95, 0x01,        //   Report Count (1)
    0x81, 0x01,        //   Input (Const,Array,Abs,No Wrap,Linear,Preferred State,No Null Position)
    
    0xC0,              // End Collection
};

const size_t WheelerGamepadDriver::kHIDReportDescriptorSize = sizeof(kHIDReportDescriptor);

// Method dispatch table for user client
const IOUserClientMethodDispatch WheelerGamepadUserClient::sMethods[kWheelerGamepadUserClientMethodCount] = {
    [kWheelerGamepadUserClientMethodUpdateState] = {
        .function = (IOUserClientMethodFunction) &WheelerGamepadUserClient::sUpdateGamepadState,
        .checkCompletionExists = false,
        .checkScalarInputCount = 0,
        .checkStructureInputSize = sizeof(WheelerGamepadDriver::GamepadState),
        .checkScalarOutputCount = 0,
        .checkStructureOutputSize = 0,
    },
    [kWheelerGamepadUserClientMethodGetState] = {
        .function = (IOUserClientMethodFunction) &WheelerGamepadUserClient::sGetGamepadState,
        .checkCompletionExists = false,
        .checkScalarInputCount = 0,
        .checkStructureInputSize = 0,
        .checkScalarOutputCount = 0,
        .checkStructureOutputSize = sizeof(WheelerGamepadDriver::GamepadState),
    },
};

#pragma mark - WheelerGamepadDriver Implementation

bool WheelerGamepadDriver::init()
{
    if (!super::init()) {
        return false;
    }
    
    // Initialize gamepad state to neutral
    memset(&m_gamepadState, 0, sizeof(m_gamepadState));
    m_gamepadState.leftStickX = 0;
    m_gamepadState.leftStickY = 0;
    m_gamepadState.rightStickX = 0;
    m_gamepadState.rightStickY = 0;
    m_gamepadState.leftTrigger = 0;
    m_gamepadState.rightTrigger = 0;
    m_gamepadState.buttons = 0;
    m_gamepadState.dpad = 0;
    
    m_inputReportBuffer = nullptr;
    
    return true;
}

kern_return_t WheelerGamepadDriver::Start(IOService* provider)
{
    kern_return_t ret = super::Start(provider);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    
    // Create input report buffer
    ret = IOBufferMemoryDescriptor::Create(kIOMemoryDirectionInOut, 12, 0, &m_inputReportBuffer);
    if (ret != kIOReturnSuccess) {
        IOLog("WheelerGamepadDriver: Failed to create input report buffer\n");
        return ret;
    }
    
    IOLog("WheelerGamepadDriver: Started successfully\n");
    return kIOReturnSuccess;
}

kern_return_t WheelerGamepadDriver::Stop(IOService* provider)
{
    IOLog("WheelerGamepadDriver: Stopping\n");
    
    if (m_inputReportBuffer) {
        m_inputReportBuffer->release();
        m_inputReportBuffer = nullptr;
    }
    
    return super::Stop(provider);
}

void WheelerGamepadDriver::free()
{
    if (m_inputReportBuffer) {
        m_inputReportBuffer->release();
        m_inputReportBuffer = nullptr;
    }
    
    super::free();
}

OSDictionary* WheelerGamepadDriver::newDeviceDescription()
{
    OSDictionary* description = OSDictionary::withCapacity(10);
    if (!description) {
        return nullptr;
    }
    
    OSNumber* vendorID = OSNumber::withNumber(kVendorID, 16);
    OSNumber* productID = OSNumber::withNumber(kProductID, 16);
    OSNumber* versionNumber = OSNumber::withNumber(kVersionNumber, 16);
    OSNumber* locationID = OSNumber::withNumber(kLocationID, 32);
    OSNumber* primaryUsagePage = OSNumber::withNumber(kHIDPage_GenericDesktop, 32);
    OSNumber* primaryUsage = OSNumber::withNumber(kHIDUsage_GD_GamePad, 32);
    OSString* manufacturer = OSString::withCString("Wheeler");
    OSString* product = OSString::withCString("Wheeler Virtual Gamepad");
    OSString* serialNumber = OSString::withCString("WVG001");
    OSString* transport = OSString::withCString("Virtual");
    
    if (vendorID && productID && versionNumber && locationID && 
        primaryUsagePage && primaryUsage && manufacturer && product && 
        serialNumber && transport) {
        
        description->setObject(kIOHIDVendorIDKey, vendorID);
        description->setObject(kIOHIDProductIDKey, productID);
        description->setObject(kIOHIDVersionNumberKey, versionNumber);
        description->setObject(kIOHIDLocationIDKey, locationID);
        description->setObject(kIOHIDPrimaryUsagePageKey, primaryUsagePage);
        description->setObject(kIOHIDPrimaryUsageKey, primaryUsage);
        description->setObject(kIOHIDManufacturerKey, manufacturer);
        description->setObject(kIOHIDProductKey, product);
        description->setObject(kIOHIDSerialNumberKey, serialNumber);
        description->setObject(kIOHIDTransportKey, transport);
    }
    
    OSSafeReleaseNULL(vendorID);
    OSSafeReleaseNULL(productID);
    OSSafeReleaseNULL(versionNumber);
    OSSafeReleaseNULL(locationID);
    OSSafeReleaseNULL(primaryUsagePage);
    OSSafeReleaseNULL(primaryUsage);
    OSSafeReleaseNULL(manufacturer);
    OSSafeReleaseNULL(product);
    OSSafeReleaseNULL(serialNumber);
    OSSafeReleaseNULL(transport);
    
    return description;
}

OSData* WheelerGamepadDriver::newReportDescriptor()
{
    return OSData::withBytes(kHIDReportDescriptor, kHIDReportDescriptorSize);
}

kern_return_t WheelerGamepadDriver::setReport(IOMemoryDescriptor* report, IOHIDReportType reportType, IOOptionBits options, uint32_t completionTimeout, OSAction* action)
{
    // Handle output reports (e.g., force feedback)
    return kIOReturnSuccess;
}

kern_return_t WheelerGamepadDriver::getReport(IOMemoryDescriptor* report, IOHIDReportType reportType, IOOptionBits options, uint32_t completionTimeout, OSAction* action)
{
    if (reportType == kIOHIDReportTypeInput) {
        return sendInputReport();
    }
    
    return kIOReturnUnsupported;
}

kern_return_t WheelerGamepadDriver::NewUserClient(uint32_t type, IOUserClient** userClient)
{
    WheelerGamepadUserClient* client = OSTypeAlloc(WheelerGamepadUserClient);
    if (!client) {
        return kIOReturnNoMemory;
    }
    
    if (!client->init()) {
        client->release();
        return kIOReturnError;
    }
    
    if (client->attach(this) != true) {
        client->release();
        return kIOReturnError;
    }
    
    if (client->start(this) != kIOReturnSuccess) {
        client->detach(this);
        client->release();
        return kIOReturnError;
    }
    
    *userClient = client;
    return kIOReturnSuccess;
}

kern_return_t WheelerGamepadDriver::updateGamepadState(const void* data, size_t length)
{
    if (length != sizeof(GamepadState)) {
        return kIOReturnBadArgument;
    }
    
    memcpy(&m_gamepadState, data, sizeof(GamepadState));
    
    // Send input report to HID system
    return sendInputReport();
}

kern_return_t WheelerGamepadDriver::sendInputReport()
{
    if (!m_inputReportBuffer) {
        return kIOReturnNotReady;
    }
    
    // Pack gamepad state into HID report format
    struct HIDInputReport {
        uint8_t reportID;
        uint16_t leftStickX;
        uint16_t leftStickY;
        uint16_t rightStickX;
        uint16_t rightStickY;
        uint8_t leftTrigger;
        uint8_t rightTrigger;
        uint16_t buttons;
        uint8_t dpad;
    } __attribute__((packed));
    
    HIDInputReport report;
    report.reportID = 1;
    
    // Convert signed stick values to unsigned (0-65535 range)
    report.leftStickX = (uint16_t)(m_gamepadState.leftStickX + 32768);
    report.leftStickY = (uint16_t)(m_gamepadState.leftStickY + 32768);
    report.rightStickX = (uint16_t)(m_gamepadState.rightStickX + 32768);
    report.rightStickY = (uint16_t)(m_gamepadState.rightStickY + 32768);
    
    report.leftTrigger = m_gamepadState.leftTrigger;
    report.rightTrigger = m_gamepadState.rightTrigger;
    report.buttons = m_gamepadState.buttons;
    report.dpad = m_gamepadState.dpad;
    
    // Write report to buffer
    kern_return_t ret = m_inputReportBuffer->writeBytes(0, &report, sizeof(report));
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    
    // Send the report
    return handleReport(m_inputReportBuffer, kIOHIDReportTypeInput);
}

#pragma mark - WheelerGamepadUserClient Implementation

bool WheelerGamepadUserClient::init()
{
    if (!super::init()) {
        return false;
    }
    
    m_driver = nullptr;
    return true;
}

kern_return_t WheelerGamepadUserClient::Start(IOService* provider)
{
    kern_return_t ret = super::Start(provider);
    if (ret != kIOReturnSuccess) {
        return ret;
    }
    
    m_driver = OSDynamicCast(WheelerGamepadDriver, provider);
    if (!m_driver) {
        return kIOReturnBadArgument;
    }
    
    IOLog("WheelerGamepadUserClient: Started successfully\n");
    return kIOReturnSuccess;
}

kern_return_t WheelerGamepadUserClient::Stop(IOService* provider)
{
    IOLog("WheelerGamepadUserClient: Stopping\n");
    m_driver = nullptr;
    return super::Stop(provider);
}

void WheelerGamepadUserClient::free()
{
    m_driver = nullptr;
    super::free();
}

kern_return_t WheelerGamepadUserClient::ExternalMethod(uint64_t selector, IOUserClientMethodArguments* arguments, const IOUserClientMethodDispatch* dispatch, OSObject* target, void* reference)
{
    if (selector >= kWheelerGamepadUserClientMethodCount) {
        return kIOReturnBadArgument;
    }
    
    return super::ExternalMethod(selector, arguments, &sMethods[selector], this, nullptr);
}

kern_return_t WheelerGamepadUserClient::sUpdateGamepadState(OSObject* target, void* reference, IOUserClientMethodArguments* arguments)
{
    WheelerGamepadUserClient* client = OSDynamicCast(WheelerGamepadUserClient, target);
    if (!client) {
        return kIOReturnBadArgument;
    }
    
    return client->updateGamepadState(arguments);
}

kern_return_t WheelerGamepadUserClient::sGetGamepadState(OSObject* target, void* reference, IOUserClientMethodArguments* arguments)
{
    WheelerGamepadUserClient* client = OSDynamicCast(WheelerGamepadUserClient, target);
    if (!client) {
        return kIOReturnBadArgument;
    }
    
    return client->getGamepadState(arguments);
}

kern_return_t WheelerGamepadUserClient::updateGamepadState(IOUserClientMethodArguments* arguments)
{
    if (!m_driver || !arguments->structureInput || arguments->structureInputSize != sizeof(WheelerGamepadDriver::GamepadState)) {
        return kIOReturnBadArgument;
    }
    
    return m_driver->updateGamepadState(arguments->structureInput, arguments->structureInputSize);
}

kern_return_t WheelerGamepadUserClient::getGamepadState(IOUserClientMethodArguments* arguments)
{
    if (!m_driver || !arguments->structureOutput || arguments->structureOutputSize != sizeof(WheelerGamepadDriver::GamepadState)) {
        return kIOReturnBadArgument;
    }
    
    // Copy current gamepad state to output buffer
    memcpy(arguments->structureOutput, &m_driver->m_gamepadState, sizeof(WheelerGamepadDriver::GamepadState));
    
    return kIOReturnSuccess;
}