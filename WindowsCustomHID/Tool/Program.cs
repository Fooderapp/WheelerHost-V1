using System;
using System.ComponentModel;
using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

internal class Program
{
    // Match GUID in driver Public.h
    static Guid InterfaceGuid = new Guid("E5B3B6C1-3F7E-4C6E-8782-5C9B7F2C89B1");

    const uint FILE_ANY_ACCESS = 0;
    const uint FILE_DEVICE_UNKNOWN = 0x00000022;
    const uint METHOD_BUFFERED = 0;
    static uint CTL_CODE(uint devType, uint function, uint method, uint access) =>
        ((devType << 16) | (access << 14) | (function << 2) | method);
    static readonly uint IOCTL_CUSTOMHID_SUBMIT_INPUT = CTL_CODE(FILE_DEVICE_UNKNOWN, 0x800, METHOD_BUFFERED, FILE_ANY_ACCESS);

    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    struct HidInputReport
    {
        public byte ReportId; // 0x01
        [MarshalAs(UnmanagedType.ByValArray, SizeConst = 63)]
        public byte[] Payload;
    }

    static void Main()
    {
        Console.WriteLine("Custom HID Tool: sending sample input frames...");
        var path = FindDevicePath(InterfaceGuid);
        if (path == null)
        {
            Console.Error.WriteLine("Device interface not found. Ensure driver installed.");
            return;
        }
        Console.WriteLine($"Opening {path}");
        using var handle = CreateDeviceHandle(path);
        if (handle == null || handle.IsInvalid)
        {
            Console.Error.WriteLine("Failed to open device.");
            return;
        }

        // Compose a simple input report with ReportId=1 and some bytes
        var report = new HidInputReport { ReportId = 0x01, Payload = new byte[63] };
        // Example: A button pressed (byte 0 = 1), LX centered, etc.
        report.Payload[0] = 0x01;
        report.Payload[1] = 0x80; // LX
        report.Payload[2] = 0x80; // LY
        report.Payload[3] = 0x80; // RX
        report.Payload[4] = 0x80; // RY

        var size = Marshal.SizeOf<HidInputReport>();
        var buffer = new byte[size];
        IntPtr ptr = Marshal.AllocHGlobal(size);
        try
        {
            Marshal.StructureToPtr(report, ptr, false);
            Marshal.Copy(ptr, buffer, 0, size);
        }
        finally { Marshal.FreeHGlobal(ptr); }

        uint bytesReturned = 0;
        if (!DeviceIoControl(handle, IOCTL_CUSTOMHID_SUBMIT_INPUT, buffer, (uint)buffer.Length, null, 0, ref bytesReturned, IntPtr.Zero))
        {
            Console.Error.WriteLine("IOCTL failed: " + new Win32Exception(Marshal.GetLastWin32Error()).Message);
            return;
        }
        Console.WriteLine("Submitted input report. Check joy.cpl or a HID monitor.");
    }

    static SafeFileHandle CreateDeviceHandle(string devicePath)
    {
        var handle = CreateFile(devicePath, FileAccess.ReadWrite,
            FileShare.ReadWrite, IntPtr.Zero, FileMode.Open, 0, IntPtr.Zero);
        if (handle.IsInvalid)
        {
            throw new Win32Exception(Marshal.GetLastWin32Error());
        }
        return handle;
    }

    static string? FindDevicePath(Guid interfaceGuid)
    {
        IntPtr h = SetupDiGetClassDevs(ref interfaceGuid, null, IntPtr.Zero, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
        if (h == (IntPtr)(-1)) return null;
        try
        {
            SP_DEVICE_INTERFACE_DATA did = new SP_DEVICE_INTERFACE_DATA();
            did.cbSize = (uint)Marshal.SizeOf<SP_DEVICE_INTERFACE_DATA>();
            for (uint index = 0; ; index++)
            {
                if (!SetupDiEnumDeviceInterfaces(h, IntPtr.Zero, ref interfaceGuid, index, ref did))
                {
                    int err = Marshal.GetLastWin32Error();
                    if (err == ERROR_NO_MORE_ITEMS) break;
                    continue;
                }
                uint required = 0;
                SetupDiGetDeviceInterfaceDetail(h, ref did, IntPtr.Zero, 0, ref required, IntPtr.Zero);
                IntPtr detailPtr = Marshal.AllocHGlobal((int)required);
                try
                {
                    Marshal.WriteInt32(detailPtr, IntPtr.Size == 8 ? 8 : 6); // cbSize
                    if (SetupDiGetDeviceInterfaceDetail(h, ref did, detailPtr, required, ref required, IntPtr.Zero))
                    {
                        IntPtr pDevicePath = detailPtr + (IntPtr.Size == 8 ? 8 : 4);
                        string devicePath = Marshal.PtrToStringAuto(pDevicePath)!;
                        return devicePath;
                    }
                }
                finally { Marshal.FreeHGlobal(detailPtr); }
            }
        }
        finally { SetupDiDestroyDeviceInfoList(h); }
        return null;
    }

    const int ERROR_NO_MORE_ITEMS = 259;
    const int DIGCF_PRESENT = 0x00000002;
    const int DIGCF_DEVICEINTERFACE = 0x00000010;

    [StructLayout(LayoutKind.Sequential)]
    struct SP_DEVICE_INTERFACE_DATA
    {
        public uint cbSize;
        public Guid InterfaceClassGuid;
        public uint Flags;
        public UIntPtr Reserved;
    }

    [DllImport("setupapi.dll", SetLastError = true)]
    static extern IntPtr SetupDiGetClassDevs(ref Guid ClassGuid, string? Enumerator, IntPtr hwndParent, int Flags);

    [DllImport("setupapi.dll", SetLastError = true)]
    static extern bool SetupDiEnumDeviceInterfaces(IntPtr DeviceInfoSet, IntPtr DeviceInfoData, ref Guid InterfaceClassGuid, uint MemberIndex, ref SP_DEVICE_INTERFACE_DATA DeviceInterfaceData);

    [DllImport("setupapi.dll", SetLastError = true, CharSet = CharSet.Auto)]
    static extern bool SetupDiGetDeviceInterfaceDetail(IntPtr DeviceInfoSet, ref SP_DEVICE_INTERFACE_DATA DeviceInterfaceData, IntPtr DeviceInterfaceDetailData, uint DeviceInterfaceDetailDataSize, ref uint RequiredSize, IntPtr DeviceInfoData);

    [DllImport("setupapi.dll", SetLastError = true)]
    static extern bool SetupDiDestroyDeviceInfoList(IntPtr DeviceInfoSet);

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    static extern SafeFileHandle CreateFile(string lpFileName, [MarshalAs(UnmanagedType.U4)] FileAccess dwDesiredAccess,
        [MarshalAs(UnmanagedType.U4)] FileShare dwShareMode, IntPtr lpSecurityAttributes,
        [MarshalAs(UnmanagedType.U4)] FileMode dwCreationDisposition, int dwFlagsAndAttributes, IntPtr hTemplateFile);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool DeviceIoControl(SafeFileHandle hDevice, uint dwIoControlCode, byte[]? lpInBuffer, uint nInBufferSize,
        byte[]? lpOutBuffer, uint nOutBufferSize, ref uint lpBytesReturned, IntPtr lpOverlapped);
}

