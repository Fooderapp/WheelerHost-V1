import Foundation
import AVFoundation

// Simple macOS audio helper: taps default input (or a named device like BlackHole) and prints JSON features

struct AudioFeatures: Codable {
    let bodyL: Double
    let bodyR: Double
    let impact: Double
    let device: String
}

final class AudioCapture {
    let engine = AVAudioEngine()
    var lastFlush = Date().timeIntervalSince1970
    var emaFast: Double = 0
    var emaSlow: Double = 0
    var roadEnv: Double = 0
    var engEnv: Double = 0
    var prevSlow: Double = 0
    var impactEnv: Double = 0
    var deviceName: String = "(default)"

    func start(deviceHint: String?) throws {
        // On macOS, AVAudioSession is unavailable; AVAudioEngine taps default input.
        // For system output capture, the user must set a loopback device (e.g., BlackHole) as input.
        if let hint = deviceHint, !hint.isEmpty {
            self.deviceName = hint
        } else {
            self.deviceName = "Default Input"
        }

        let input = engine.inputNode
        let fmt = input.inputFormat(forBus: 0)
        input.installTap(onBus: 0, bufferSize: 1024, format: fmt) { buf, when in
            let ch = Int(fmt.channelCount)
            guard let ptr = buf.floatChannelData else { return }
            let frames = Int(buf.frameLength)
            if frames <= 0 || ch <= 0 { return }
            for i in 0..<frames {
                var acc: Float = 0
                for c in 0..<ch { acc += ptr[c][i] }
                let mono = Double(acc) / Double(ch)
                let a = abs(mono)
                // Envelopes
                let atkFast = 0.2, decFast = 0.2
                let atkSlow = 0.02, decSlow = 0.02
                let atkRoad = 0.12, decRoad = 0.08
                let atkEng  = 0.04, decEng  = 0.12
                let atkImp  = 0.25, decImp  = 0.10

                self.emaFast += (a >= self.emaFast ? atkFast : decFast) * (a - self.emaFast)
                self.emaSlow += (a >= self.emaSlow ? atkSlow : decSlow) * (a - self.emaSlow)
                let hf = max(0.0, self.emaFast - self.emaSlow)
                self.roadEnv += ((hf >= self.roadEnv) ? atkRoad : decRoad) * (hf - self.roadEnv)
                self.engEnv  += ((self.emaSlow >= self.engEnv) ? atkEng : decEng) * (self.emaSlow - self.engEnv)
                let dSlow = max(0.0, self.emaSlow - self.prevSlow)
                self.impactEnv += ((dSlow >= self.impactEnv) ? atkImp : decImp) * (dSlow - self.impactEnv)
                self.prevSlow = self.emaSlow
            }

            let now = Date().timeIntervalSince1970
            if now - self.lastFlush >= 0.016 {
                self.lastFlush = now
                let road = min(1.0, max(0.0, self.roadEnv / 0.02))
                let eng  = min(1.0, max(0.0, self.engEnv / 0.015))
                let imp  = min(1.0, max(0.0, self.impactEnv / 0.01))
                let bodyR = max(road, 0.5 * eng)
                let bodyL = max(0.8 * road, 0.3 * eng)
                let obj = AudioFeatures(bodyL: bodyL, bodyR: bodyR, impact: imp, device: self.deviceName)
                if let data = try? JSONEncoder().encode(obj) {
                    if let line = String(data: data, encoding: .utf8) { print(line) }
                    fflush(stdout)
                }
            }
        }
        try engine.start()
        // Print started status
        let started = ["status":"started", "device": self.deviceName] as [String : Any]
        if let data = try? JSONSerialization.data(withJSONObject: started), let line = String(data: data, encoding: .utf8) { print(line); fflush(stdout) }
    }
}

let hint = CommandLine.arguments.dropFirst().joined(separator: " ")
let cap = AudioCapture()
do {
    try cap.start(deviceHint: hint)
    RunLoop.main.run()
} catch {
    let err = ["status":"error","message":"\(error.localizedDescription)"]
    if let data = try? JSONSerialization.data(withJSONObject: err), let line = String(data: data, encoding: .utf8) { print(line); fflush(stdout) }
}
