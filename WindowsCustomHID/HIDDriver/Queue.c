#include "Public.h"
#include "HidReportDescriptor.h"

static const HID_DESCRIPTOR g_HidDescriptor = {
    sizeof(HID_DESCRIPTOR), // bLength
    HID_HID_DESCRIPTOR_TYPE,// bDescriptorType (0x21)
    HID_REVISION,           // bcdHID
    0x00,                   // bCountry
    0x01,                   // bNumDescriptors
    {
        HID_REPORT_DESCRIPTOR_TYPE, // bReportType (0x22)
        sizeof(g_HidReportDescriptor) // wReportLength
    }
};

NTSTATUS HidGetDeviceDescriptor(_In_ WDFREQUEST Request)
{
    NTSTATUS status = STATUS_SUCCESS;
    PHID_DESCRIPTOR outBuf = NULL;
    size_t outLen = 0;
    status = WdfRequestRetrieveOutputBuffer(Request, sizeof(HID_DESCRIPTOR), (PVOID*)&outBuf, &outLen);
    if (!NT_SUCCESS(status)) goto done;
    if (outLen < sizeof(g_HidDescriptor)) { status = STATUS_BUFFER_TOO_SMALL; goto done; }
    RtlCopyMemory(outBuf, &g_HidDescriptor, sizeof(g_HidDescriptor));
    WdfRequestSetInformation(Request, sizeof(g_HidDescriptor));
done:
    WdfRequestComplete(Request, status);
    return status;
}

NTSTATUS HidGetReportDescriptor(_In_ WDFREQUEST Request)
{
    NTSTATUS status = STATUS_SUCCESS;
    PVOID outBuf = NULL;
    size_t outLen = 0;
    status = WdfRequestRetrieveOutputBuffer(Request, sizeof(g_HidReportDescriptor), &outBuf, &outLen);
    if (!NT_SUCCESS(status)) goto done;
    if (outLen < sizeof(g_HidReportDescriptor)) { status = STATUS_BUFFER_TOO_SMALL; goto done; }
    RtlCopyMemory(outBuf, g_HidReportDescriptor, sizeof(g_HidReportDescriptor));
    WdfRequestSetInformation(Request, sizeof(g_HidReportDescriptor));
done:
    WdfRequestComplete(Request, status);
    return status;
}

NTSTATUS HidGetAttributes(_In_ WDFREQUEST Request)
{
    NTSTATUS status = STATUS_SUCCESS;
    PHID_DEVICE_ATTRIBUTES attrs;
    size_t bufLen = 0;
    status = WdfRequestRetrieveOutputBuffer(Request, sizeof(HID_DEVICE_ATTRIBUTES), (PVOID*)&attrs, &bufLen);
    if (!NT_SUCCESS(status)) goto done;
    RtlZeroMemory(attrs, sizeof(HID_DEVICE_ATTRIBUTES));
    attrs->Size = sizeof(HID_DEVICE_ATTRIBUTES);
    attrs->VendorID = CUSTOMHID_VID;
    attrs->ProductID = CUSTOMHID_PID;
    attrs->VersionNumber = CUSTOMHID_VERSION;
    WdfRequestSetInformation(Request, sizeof(HID_DEVICE_ATTRIBUTES));
done:
    WdfRequestComplete(Request, status);
    return status;
}

NTSTATUS HidWriteReport(_In_ WDFREQUEST Request)
{
    // Accept and ignore for now
    size_t len = 0;
    NTSTATUS status = WdfRequestRetrieveInputBuffer(Request, 1, NULL, &len);
    if (NT_SUCCESS(status)) {
        WdfRequestSetInformation(Request, len);
    }
    WdfRequestComplete(Request, status);
    return status;
}

NTSTATUS HidGetSetFeature(_In_ WDFREQUEST Request, _In_ BOOLEAN Set)
{
    UNREFERENCED_PARAMETER(Set);
    NTSTATUS status = STATUS_SUCCESS;
    size_t inLen = 0, outLen = 0;
    (void)WdfRequestRetrieveInputBuffer(Request, 1, NULL, &inLen);
    (void)WdfRequestRetrieveOutputBuffer(Request, 1, NULL, &outLen);
    WdfRequestSetInformation(Request, Set ? inLen : outLen);
    WdfRequestComplete(Request, status);
    return status;
}

static VOID CompleteOneReadWithBuffer(WDFDEVICE Device, PVOID Buffer, size_t Length)
{
    PDEVICE_CONTEXT ctx = DeviceGetContext(Device);
    WDFREQUEST req;
    NTSTATUS status = WdfIoQueueRetrieveNextRequest(ctx->ReadReportQueue, &req);
    if (!NT_SUCCESS(status)) return;
    WDFMEMORY mem;
    status = WdfRequestRetrieveOutputMemory(req, &mem);
    if (NT_SUCCESS(status)) {
        (void)WdfMemoryCopyFromBuffer(mem, 0, Buffer, Length);
        WdfRequestSetInformation(req, Length);
    }
    WdfRequestComplete(req, status);
}

NTSTATUS HidReadReportEnqueue(_In_ WDFREQUEST Request)
{
    // Forward/pending by leaving it in the ReadReportQueue
    WdfRequestForwardToIoQueue(Request, DeviceGetContext(WdfIoQueueGetDevice(WdfRequestGetIoQueue(Request)))->ReadReportQueue);
    return STATUS_PENDING;
}

VOID EvtIoInternalDeviceControl(
    _In_ WDFQUEUE   Queue,
    _In_ WDFREQUEST Request
)
{
    WDFDEVICE device = WdfIoQueueGetDevice(Queue);
    PIO_STACK_LOCATION stack = WdfRequestWdmGetIrp(Request)->Tail.Overlay.CurrentStackLocation;
    ULONG code = stack->Parameters.DeviceIoControl.IoControlCode;

    switch (code) {
    case IOCTL_HID_GET_DEVICE_DESCRIPTOR:
        HidGetDeviceDescriptor(Request);
        break;
    case IOCTL_HID_GET_REPORT_DESCRIPTOR:
        HidGetReportDescriptor(Request);
        break;
    case IOCTL_HID_GET_DEVICE_ATTRIBUTES:
        HidGetAttributes(Request);
        break;
    case IOCTL_HID_READ_REPORT:
        // Queue pending read until user-mode submits input
        WdfRequestForwardToIoQueue(Request, DeviceGetContext(device)->ReadReportQueue);
        break;
    case IOCTL_HID_WRITE_REPORT:
        HidWriteReport(Request);
        break;
    case IOCTL_HID_GET_FEATURE:
        HidGetSetFeature(Request, FALSE);
        break;
    case IOCTL_HID_SET_FEATURE:
        HidGetSetFeature(Request, TRUE);
        break;
    default:
        WdfRequestComplete(Request, STATUS_NOT_SUPPORTED);
        break;
    }
}

VOID EvtIoDeviceControl(
    _In_ WDFQUEUE   Queue,
    _In_ WDFREQUEST Request,
    _In_ size_t     OutputBufferLength,
    _In_ size_t     InputBufferLength,
    _In_ ULONG      IoControlCode
)
{
    UNREFERENCED_PARAMETER(OutputBufferLength);
    UNREFERENCED_PARAMETER(InputBufferLength);

    WDFDEVICE device = WdfIoQueueGetDevice(Queue);
    NTSTATUS status = STATUS_SUCCESS;

    if (IoControlCode == IOCTL_CUSTOMHID_SUBMIT_INPUT) {
        // Input buffer must contain HID_INPUT_REPORT (64 bytes)
        PHID_INPUT_REPORT inReport = NULL;
        size_t len = 0;
        status = WdfRequestRetrieveInputBuffer(Request, sizeof(HID_INPUT_REPORT), (PVOID*)&inReport, &len);
        if (NT_SUCCESS(status) && len >= sizeof(HID_INPUT_REPORT) && inReport->ReportId == 0x01) {
            CompleteOneReadWithBuffer(device, inReport, sizeof(HID_INPUT_REPORT));
            WdfRequestSetInformation(Request, sizeof(HID_INPUT_REPORT));
        } else {
            status = STATUS_INVALID_PARAMETER;
        }
        WdfRequestComplete(Request, status);
        return;
    }

    WdfRequestComplete(Request, STATUS_INVALID_DEVICE_REQUEST);
}
