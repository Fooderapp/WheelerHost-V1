#include "Public.h"
#include "HidReportDescriptor.h"

DRIVER_INITIALIZE DriverEntry;

NTSTATUS
DriverEntry(
    _In_ PDRIVER_OBJECT  DriverObject,
    _In_ PUNICODE_STRING RegistryPath
)
{
    WDF_DRIVER_CONFIG config;
    NTSTATUS status;

    WDF_DRIVER_CONFIG_INIT(&config, EvtDriverDeviceAdd);
    config.EvtDriverUnload = NULL;

    WDF_OBJECT_ATTRIBUTES attributes;
    WDF_OBJECT_ATTRIBUTES_INIT(&attributes);
    attributes.EvtCleanupCallback = EvtDriverContextCleanup;

    status = WdfDriverCreate(DriverObject, RegistryPath, &attributes, &config, WDF_NO_HANDLE);
    return status;
}

VOID
EvtDriverContextCleanup(
    _In_ WDFOBJECT DriverObject
)
{
    UNREFERENCED_PARAMETER(DriverObject);
}

static NTSTATUS
CreateDevice(_Inout_ PWDFDEVICE_INIT DeviceInit, _Out_ WDFDEVICE* Device)
{
    NTSTATUS status;

    WdfDeviceInitSetDeviceType(DeviceInit, FILE_DEVICE_KEYBOARD); // generic HID
    WdfDeviceInitSetExclusive(DeviceInit, FALSE);

    // HID minidriver: set characteristics for HID stack
    WdfDeviceInitSetIoType(DeviceInit, WdfDeviceIoDirect);

    WDF_PNPPOWER_EVENT_CALLBACKS pnpCallbacks;
    WDF_PNPPOWER_EVENT_CALLBACKS_INIT(&pnpCallbacks);
    WdfDeviceInitSetPnpPowerEventCallbacks(DeviceInit, &pnpCallbacks);

    WDF_OBJECT_ATTRIBUTES deviceAttributes;
    WDF_OBJECT_ATTRIBUTES_INIT_CONTEXT_TYPE(&deviceAttributes, DEVICE_CONTEXT);

    status = WdfDeviceCreate(&DeviceInit, &deviceAttributes, Device);
    if (!NT_SUCCESS(status)) return status;

    // Register a device interface for our control device
    status = WdfDeviceCreateDeviceInterface(*Device, &GUID_DEVINTERFACE_CustomHIDControl, NULL);
    if (!NT_SUCCESS(status)) return status;

    // Create queues: default for HID internal IOCTLs, and a manual queue for pending reads
    WDF_IO_QUEUE_CONFIG queueConfig;
    WDF_IO_QUEUE_CONFIG_INIT_DEFAULT_QUEUE(&queueConfig, WdfIoQueueDispatchParallel);
    queueConfig.EvtIoInternalDeviceControl = EvtIoInternalDeviceControl;
    status = WdfIoQueueCreate(*Device, &queueConfig, WDF_NO_OBJECT_ATTRIBUTES, NULL);
    if (!NT_SUCCESS(status)) return status;

    // Manual queue for pending IOCTL_HID_READ_REPORT requests
    WDF_IO_QUEUE_CONFIG manualCfg;
    WDF_IO_QUEUE_CONFIG_INIT(&manualCfg, WdfIoQueueDispatchManual);
    status = WdfIoQueueCreate(*Device, &manualCfg, WDF_NO_OBJECT_ATTRIBUTES, &DeviceGetContext(*Device)->ReadReportQueue);
    if (!NT_SUCCESS(status)) return status;

    // Control queue for our custom IOCTL via device interface
    WDF_IO_QUEUE_CONFIG ctrlQueueCfg;
    WDF_IO_QUEUE_CONFIG_INIT(&ctrlQueueCfg, WdfIoQueueDispatchParallel);
    ctrlQueueCfg.EvtIoDeviceControl = EvtIoDeviceControl;
    status = WdfIoQueueCreate(*Device, &ctrlQueueCfg, WDF_NO_OBJECT_ATTRIBUTES, &DeviceGetContext(*Device)->ControlQueue);
    if (!NT_SUCCESS(status)) return status;

    return STATUS_SUCCESS;
}

NTSTATUS
EvtDriverDeviceAdd(
    _In_    WDFDRIVER       Driver,
    _Inout_ PWDFDEVICE_INIT DeviceInit
)
{
    UNREFERENCED_PARAMETER(Driver);
    // Create the WDF device for our virtual HID
    WDFDEVICE device = NULL;
    NTSTATUS status = CreateDevice(DeviceInit, &device);
    return status;
}
