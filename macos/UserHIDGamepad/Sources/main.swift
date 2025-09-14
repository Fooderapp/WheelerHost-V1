import Foundation
import Darwin

// Simple HID Gamepad: 16 buttons + 4 axes (LX, LY, RX, RY) in 0..255
// Report (no Report ID): [buttonsLo, buttonsHi, LX, LY, RX, RY] (6 bytes)

typealias IOHIDUserDeviceRef = OpaquePointer
typealias IOReturn = Int32
typealias IOHIDUserDeviceCreateFn = @convention(c) (CFAllocator?, CFDictionary) -> IOHIDUserDeviceRef?
typealias IOHIDUserDeviceHandleReportFn = @convention(c) (IOHIDUserDeviceRef, UnsafePointer<UInt8>, CFIndex) -> IOReturn

final class HIDGamepad {
    private let device: IOHIDUserDeviceRef
    private let handleReport: IOHIDUserDeviceHandleReportFn
    init?() {
        // HID Report Descriptor
        let desc: [UInt8] = [
            0x05, 0x01,       // Usage Page (Generic Desktop)
            0x09, 0x05,       // Usage (Game Pad)
            0xA1, 0x01,       // Collection (Application)

            // 16 buttons
            0x05, 0x09,       //   Usage Page (Button)
            0x19, 0x01,       //   Usage Minimum (1)
            0x29, 0x10,       //   Usage Maximum (16)
            0x15, 0x00,       //   Logical Minimum (0)
            0x25, 0x01,       //   Logical Maximum (1)
            0x95, 0x10,       //   Report Count (16)
            0x75, 0x01,       //   Report Size (1)
            0x81, 0x02,       //   Input (Data,Var,Abs)

            // 4 axes (LX, LY, RX, RY) as 0..255
            0x05, 0x01,       //   Usage Page (Generic Desktop)
            0x15, 0x00,       //   Logical Minimum (0)
            0x26, 0xFF, 0x00, //   Logical Maximum (255)
            0x75, 0x08,       //   Report Size (8)
            0x95, 0x04,       //   Report Count (4)
            0x09, 0x30,       //   Usage (X)
            0x09, 0x31,       //   Usage (Y)
            0x09, 0x33,       //   Usage (Rx)
            0x09, 0x34,       //   Usage (Ry)
            0x81, 0x02,       //   Input (Data,Var,Abs)

            0xC0              // End Collection
        ]

        // Dynamically load IOKit and resolve functions and CFString keys
        guard let hIOKit = dlopen("/System/Library/Frameworks/IOKit.framework/IOKit", RTLD_LAZY) else {
            fputs("Failed to load IOKit framework\n", stderr)
            return nil
        }
        guard let pCreate = dlsym(hIOKit, "IOHIDUserDeviceCreate"),
              let pHandle = dlsym(hIOKit, "IOHIDUserDeviceHandleReport") else {
            fputs("Failed to resolve IOHIDUserDevice symbols\n", stderr)
            return nil
        }
        let create = unsafeBitCast(pCreate, to: IOHIDUserDeviceCreateFn.self)
        self.handleReport = unsafeBitCast(pHandle, to: IOHIDUserDeviceHandleReportFn.self)
        
        func getKey(_ name: String) -> CFString? {
            guard let sym = dlsym(hIOKit, name) else { return nil }
            return unsafeBitCast(sym, to: UnsafePointer<CFString?>.self).pointee
        }
        guard let kReport = getKey("kIOHIDReportDescriptorKey"),
              let kVID = getKey("kIOHIDVendorIDKey"),
              let kPID = getKey("kIOHIDProductIDKey"),
              let kVer = getKey("kIOHIDVersionNumberKey"),
              let kMfr = getKey("kIOHIDManufacturerKey"),
              let kProd = getKey("kIOHIDProductKey"),
              let kSer = getKey("kIOHIDSerialNumberKey"),
              let kTrans = getKey("kIOHIDTransportKey"),
              let kUsagePage = getKey("kIOHIDPrimaryUsagePageKey"),
              let kUsage = getKey("kIOHIDPrimaryUsageKey"),
              let kMaxIn = getKey("kIOHIDMaxInputReportSizeKey"),
              let kMaxOut = getKey("kIOHIDMaxOutputReportSizeKey"),
              let kMaxFeat = getKey("kIOHIDMaxFeatureReportSizeKey") else {
            fputs("Failed to resolve IOHID CFString keys\n", stderr)
            return nil
        }
        
        let props: [CFString: Any] = [
            kVID: 0x1234,
            kPID: 0xABCD,
            kVer: 0x0001,
            kMfr: "Wheeler" as CFString,
            kProd: "Wheeler User HID Gamepad" as CFString,
            kSer: "00000001" as CFString,
            kTrans: "Virtual" as CFString,
            kUsagePage: 0x01,
            kUsage: 0x05,
            kReport: Data(desc) as CFData,
            kMaxIn: 6, kMaxOut: 0, kMaxFeat: 0
        ]

        guard let dev = create(kCFAllocatorDefault, props as CFDictionary) else {
            return nil
        }
        self.device = dev
    }

    func send(buttons: UInt16, lx: UInt8, ly: UInt8, rx: UInt8, ry: UInt8) {
        var report = [UInt8](repeating: 0, count: 6)
        report[0] = UInt8(buttons & 0xFF)
        report[1] = UInt8((buttons >> 8) & 0xFF)
        report[2] = lx
        report[3] = ly
        report[4] = rx
        report[5] = ry
        report.withUnsafeBufferPointer { buf in
            let res = self.handleReport(device, buf.baseAddress!, buf.count)
            if res != 0 { // kIOReturnSuccess == 0
                fputs("IOHIDUserDeviceHandleReport failed: \(res)\n", stderr)
            }
        }
    }
}

func clampFloat(_ x: Double) -> Double { min(1.0, max(-1.0, x)) }
func mapAxis(_ x: Double) -> UInt8 { // [-1,1] -> [0,255]
    let v = (clampFloat(x) * 0.5 + 0.5) * 255.0
    return UInt8(max(0, min(255, Int(v.rounded()))))
}

struct Args {
    var demo = false
    var udpPort: UInt16? = nil
}

func parseArgs() -> Args {
    var out = Args()
    var it = CommandLine.arguments.dropFirst().makeIterator()
    while let a = it.next() {
        switch a {
        case "--demo": out.demo = true
        case "--udp": if let p = it.next(), let v = UInt16(p) { out.udpPort = v }
        default: break
        }
    }
    return out
}

func runDemo(on pad: HIDGamepad) {
    var on = false
    print("Demo: toggling A button every second. Press Ctrl+C to quit.")
    while true {
        on.toggle()
        let buttons: UInt16 = on ? 0x0001 : 0x0000 // A button
        pad.send(buttons: buttons, lx: 128, ly: 128, rx: 128, ry: 128)
        Thread.sleep(forTimeInterval: 1.0)
    }
}

func runUDP(on pad: HIDGamepad, port: UInt16) {
    let sock = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP)
    guard sock >= 0 else { perror("socket"); exit(1) }
    var addr = sockaddr_in()
    addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
    addr.sin_family = sa_family_t(AF_INET)
    addr.sin_port = in_port_t(port).bigEndian
    addr.sin_addr = in_addr(s_addr: in_addr_t(0)) // 0.0.0.0
    var a = addr
    withUnsafePointer(to: &a) { ptr in
        ptr.withMemoryRebound(to: sockaddr.self, capacity: 1) {
            if bind(sock, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) != 0 { perror("bind"); close(sock); exit(1) }
        }
    }
    print("Listening UDP on :\(port). Send JSON: {\"buttons\":int, \"lx\":f, \"ly\":f, \"rx\":f, \"ry\":f}")
    var buf = [UInt8](repeating: 0, count: 2048)
    while true {
        let n = recv(sock, &buf, buf.count, 0)
        if n <= 0 { continue }
        let data = Data(bytes: buf, count: n)
        do {
            if let obj = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                let buttons = (obj["buttons"] as? Int) ?? 0
                let lx = mapAxis((obj["lx"] as? Double) ?? 0)
                let ly = mapAxis((obj["ly"] as? Double) ?? 0)
                let rx = mapAxis((obj["rx"] as? Double) ?? 0)
                let ry = mapAxis((obj["ry"] as? Double) ?? 0)
                pad.send(buttons: UInt16(buttons & 0xFFFF), lx: lx, ly: ly, rx: rx, ry: ry)
            }
        } catch {
            // ignore
        }
    }
}

// Main
let args = parseArgs()
guard let pad = HIDGamepad() else { fatalError("Failed to create IOHIDUserDevice") }
print("Created user-space HID Gamepad (VID:0x1234 PID:0xABCD)")
if let p = args.udpPort {
    runUDP(on: pad, port: p)
} else {
    runDemo(on: pad)
}
