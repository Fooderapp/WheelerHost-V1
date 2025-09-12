// HID Report Descriptor for a Gamepad-like device
#pragma once

// Vendor and product IDs (development)
#define CUSTOMHID_VID 0x1234
#define CUSTOMHID_PID 0xABCD
#define CUSTOMHID_VERSION 0x0001

// 64-byte input report with Report ID 1
// 64-byte output report with Report ID 2
// 64-byte feature report with Report ID 3
static const UCHAR g_HidReportDescriptor[] = {
    0x05, 0x01,       // Usage Page (Generic Desktop)
    0x09, 0x05,       // Usage (Game Pad)
    0xA1, 0x01,       // Collection (Application)

    // Report ID 1 - Input
    0x85, 0x01,       //   Report ID (1)
    // Axes: LX, LY, RX, RY (logical -32768..32767)
    0x15, 0x00,       //   Logical Min (0)
    0x26, 0xFF, 0x00, //   Logical Max (255) [byte payload]
    0x75, 0x08,       //   Report Size (8)
    0x95, 0x40,       //   Report Count (64)
    0x09, 0x01,       //   Usage (Pointer)
    0x81, 0x02,       //   Input (Data,Var,Abs)

    // Report ID 2 - Output
    0x85, 0x02,       //   Report ID (2)
    0x75, 0x08,       //   Report Size (8)
    0x95, 0x40,       //   Report Count (64)
    0x09, 0x02,       //   Usage (2)
    0x91, 0x02,       //   Output (Data,Var,Abs)

    // Report ID 3 - Feature
    0x85, 0x03,       //   Report ID (3)
    0x75, 0x08,       //   Report Size (8)
    0x95, 0x40,       //   Report Count (64)
    0x09, 0x03,       //   Usage (3)
    0xB1, 0x02,       //   Feature (Data,Var,Abs)

    0xC0              // End Collection
};

typedef struct _HID_INPUT_REPORT
{
    UCHAR ReportId; // 0x01
    UCHAR Payload[63];
} HID_INPUT_REPORT, *PHID_INPUT_REPORT;

typedef struct _HID_OUTPUT_REPORT
{
    UCHAR ReportId; // 0x02
    UCHAR Payload[63];
} HID_OUTPUT_REPORT, *PHID_OUTPUT_REPORT;

typedef struct _HID_FEATURE_REPORT
{
    UCHAR ReportId; // 0x03
    UCHAR Payload[63];
} HID_FEATURE_REPORT, *PHID_FEATURE_REPORT;

