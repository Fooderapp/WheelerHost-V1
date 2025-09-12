#pragma once

#include <ntddk.h>
#include <wdf.h>
#include <hidport.h>

#define IOCTL_CUSTOMHID_SUBMIT_INPUT CTL_CODE(FILE_DEVICE_UNKNOWN, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS)

// {E5B3B6C1-3F7E-4C6E-8782-5C9B7F2C89B1}
DEFINE_GUID(GUID_DEVINTERFACE_CustomHIDControl,
    0xe5b3b6c1, 0x3f7e, 0x4c6e, 0x87, 0x82, 0x5c, 0x9b, 0x7f, 0x2c, 0x89, 0xb1);

// Device context
typedef struct _DEVICE_CONTEXT {
    WDFQUEUE ReadReportQueue; // Manual queue for pending IOCTL_HID_READ_REPORT
    WDFQUEUE ControlQueue;    // For our custom IOCTLs (device interface)
} DEVICE_CONTEXT, *PDEVICE_CONTEXT;

WDF_DECLARE_CONTEXT_TYPE_WITH_NAME(DEVICE_CONTEXT, DeviceGetContext)

EVT_WDF_DRIVER_DEVICE_ADD     EvtDriverDeviceAdd;
EVT_WDF_OBJECT_CONTEXT_CLEANUP EvtDriverContextCleanup;

EVT_WDF_IO_QUEUE_IO_INTERNAL_DEVICE_CONTROL EvtIoInternalDeviceControl;
EVT_WDF_IO_QUEUE_IO_DEVICE_CONTROL          EvtIoDeviceControl;

NTSTATUS HidGetDeviceDescriptor(_In_ WDFREQUEST Request);
NTSTATUS HidGetReportDescriptor(_In_ WDFREQUEST Request);
NTSTATUS HidGetAttributes(_In_ WDFREQUEST Request);
NTSTATUS HidReadReportEnqueue(_In_ WDFREQUEST Request);
NTSTATUS HidWriteReport(_In_ WDFREQUEST Request);
NTSTATUS HidGetSetFeature(_In_ WDFREQUEST Request, _In_ BOOLEAN Set);
