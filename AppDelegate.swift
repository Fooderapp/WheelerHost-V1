import UIKit
import Flutter
import CoreHaptics


@UIApplicationMain
class AppDelegate: FlutterAppDelegate {
  private let channelName = "core_haptics"
  private var engine: CHHapticEngine?
  private var supportsHaptics = false
  private var lastSend = CACurrentMediaTime()
  private let maxRateHz: Double = 30.0 // iOS warning says ~32Hz limit → stay under
  private var engineStarted = false
  
  // Steering-based tick scheduler
  private var steerTimer: Timer?
  private var steerLastTick = CACurrentMediaTime()
  private var steerPos: Float = 0.0
  private var steerActive = false
  private var steerDeadzone: Float = 0.16
  private var steerCurve: Float = 3.2 // cubic-ish (ease-in)
  private var steerMaxRateHz: Double = 22.0 // smoother; leave headroom
  private var steerIntensity: Float = 0.0
  private var steerSharpness: Float = 0.6
  private var steerCenterIdleSince = CACurrentMediaTime()
  private let steerAutoStopIdleSec: Double = 1.0
  // Continuous support
  private var contPlayer: CHHapticAdvancedPatternPlayer?
  private var contTimer: Timer?
  private var contLastUpdate = CACurrentMediaTime()
  private let contMaxRateHz: Double = 60.0
  private let contPatternDur: TimeInterval = 10.0 // restarted before end to avoid auto-stop

  // Configuration
  private var solution: String = "vigem" // Default solution

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {

    // Load configuration
    loadConfiguration()

    // Select HID solution
    if solution == "vigem" {
      // Use ViGEm solution
      print("Using ViGEm solution")
    } else if solution == "custom" {
      // Use custom HID solution
      print("Using custom HID solution")
      // TODO: Implement custom HID solution
    } else {
      print("Invalid solution in configuration. Using ViGEm solution.")
    }

    if #available(iOS 13.0, *) {
      supportsHaptics = CHHapticEngine.capabilitiesForHardware().supportsHaptics
    } else {
      supportsHaptics = false
    }

    if supportsHaptics {
      setupEngine()
    }

    let controller : FlutterViewController = window?.rootViewController as! FlutterViewController
    let ch = FlutterMethodChannel(name: channelName, binaryMessenger: controller.binaryMessenger)

    ch.setMethodCallHandler { [weak self] call, result in
      guard let self = self else { return }
      DispatchQueue.main.async {
        switch call.method {
          case "supported":
            result(self.supportsHaptics)

        case "tick":
          guard self.supportsHaptics else { result(nil); return }
          let args = (call.arguments as? [String: Any]) ?? [:]
          let strength = Float((args["strength"] as? Double ?? 0.5).clamp01())
          let sharp = Float((args["sharpness"] as? Double ?? 0.6).clamp01())
          self.tick(strength: strength, sharpness: sharp)
          result(nil)

        case "startContinuous":
          guard self.supportsHaptics else { result(nil); return }
          let args = (call.arguments as? [String: Any]) ?? [:]
          let intensity = Float((args["intensity"] as? Double ?? 0.2).clamp01())
          let sharp = Float((args["sharpness"] as? Double ?? 0.5).clamp01())
          self.startContinuous(intensity: intensity, sharpness: sharp)
          result(nil)

        case "updateContinuous":
          guard self.supportsHaptics else { result(nil); return }
          let args = (call.arguments as? [String: Any]) ?? [:]
          let intensity = Float((args["intensity"] as? Double ?? 0.2).clamp01())
          let sharp = Float((args["sharpness"] as? Double ?? 0.5).clamp01())
          self.updateContinuous(intensity: intensity, sharpness: sharp)
          result(nil)

        case "stopContinuous":
          self.stopContinuous()
          result(nil)

        case "stop":
          self.stop()
          result(nil)

          case "ffbTest":
            self.runFFBTest()
            result(nil)

          case "steerHapticsUpdate":
            let args = (call.arguments as? [String: Any]) ?? [:]
            let pos = Float((args["pos"] as? Double ?? 0.0))
            if let dz = args["deadzone"] as? Double { self.steerDeadzone = Float(max(0.0, min(0.45, dz))) }
            if let cv = args["curve"] as? Double { self.steerCurve = Float(max(1.0, min(6.0, cv))) }
            self.onSteerUpdate(pos: pos)
            result(nil)

          case "steerHapticsStop":
            self.stopSteerHaptics()
            result(nil)

        default:
          result(FlutterMethodNotImplemented)
        }
      }
    }

    GeneratedPluginRegistrant.register(with: self)
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  private func loadConfiguration() {
    if let url = Bundle.main.url(forResource: "gamepad_config", withExtension: "json") {
      do {
        let data = try Data(contentsOf: url)
        if let json = try JSONSerialization.jsonObject(with: data, options: []) as? [String: Any] {
          solution = json["solution"] as? String ?? "vigem"
          print("Loaded solution: \(solution)")
        }
      } catch {
        print("Error loading configuration: \(error)")
      }
    }
  }

  private func setupEngine() {
    guard #available(iOS 13.0, *) else { return }
    do {
      let e = try CHHapticEngine()
      e.isAutoShutdownEnabled = true
      // Prefer haptics-only; avoid any audio rendering
      if #available(iOS 13.0, *) {
        e.playsHapticsOnly = true
      }
      e.stoppedHandler = { [weak self] _ in
        self?.engineStarted = false
        self?.teardownContinuous()
      }
      e.resetHandler = { [weak self] in
        guard let self = self else { return }
        self.engineStarted = false
        try? self.engine?.start()
        self.engineStarted = true
        // After reset, drop the old player; will re-create on demand
        self.teardownContinuous()
      }
      engine = e
      try? engine?.start()
      engineStarted = true
    } catch {
      print("Haptics: engine init error: \(error)")
      engine = nil
      engineStarted = false
    }
  }

  // MARK: - Steering tick haptics
  private func onSteerUpdate(pos: Float) {
    steerPos = max(-1.0, min(1.0, pos))
    let absPos = fabsf(steerPos)
    let now = CACurrentMediaTime()
    let params = computeSteerParams(absPos: absPos)
    steerActive = params.active
    steerIntensity = params.intensity
    steerSharpness = params.sharpness
    steerMaxRateHz = params.rateHz
    if !steerActive {
      // Track idle duration to auto-stop timer if centered
      steerCenterIdleSince = now
    }
    ensureSteerTimer()
  }

  private func computeSteerParams(absPos: Float) -> (active: Bool, rateHz: Double, intensity: Float, sharpness: Float) {
    // Deadzone: no ticks near center
    let dz = max(0.0, min(0.45, steerDeadzone))
    if absPos <= dz {
      return (false, 0.0, 0.0, 0.0)
    }
    // Normalize outside deadzone → [0,1]
    let m = max(0.0, min(1.0, (absPos - dz) / max(0.0001, 1.0 - dz)))
    // Ease-in curve (cubic-ish)
    let curved = powf(m, steerCurve)
    // Map to rate with clear perceptual change (≈4→24 Hz)
    let rate = 4.0 + Double(curved) * 20.0
    // Softer base and lower floor for less "click"
    let intensity = max(0.06, min(1.0, 0.06 + 0.72 * curved))
    let sharp = max(0.35, min(0.8, 0.35 + 0.35 * curved))
    return (true, rate, intensity, sharp)
  }

  private func ensureSteerTimer() {
    // If no activity and timer exists, consider stopping it
    if !steerActive {
      if let t = steerTimer {
        let now = CACurrentMediaTime()
        if now - steerCenterIdleSince >= steerAutoStopIdleSec {
          t.invalidate()
          steerTimer = nil
        }
      }
      return
    }
    if steerTimer == nil {
      // Polling timer to schedule transients based on target rate
      steerTimer = Timer.scheduledTimer(withTimeInterval: 1.0/120.0, repeats: true, block: { [weak self] _ in
        self?.steerTimerTick()
      })
    }
  }

  private func steerTimerTick() {
    guard supportsHaptics else { return }
    if steerMaxRateHz <= 0.0 { return }
    let now = CACurrentMediaTime()
    let interval = 1.0 / steerMaxRateHz
    if now - steerLastTick >= interval {
      steerLastTick = now
      steerBurst(strength: steerIntensity, sharpness: steerSharpness)
    }
  }

  // Smoother than transient: short continuous micro-burst (≈18–32 ms)
  private func steerBurst(strength: Float, sharpness: Float) {
    guard #available(iOS 13.0, *), supportsHaptics else { return }
    ensureEngine()
    let dur: TimeInterval = 0.018 + 0.015 * TimeInterval(min(1.0, max(0.0, Double(strength))))
    let pI = CHHapticEventParameter(parameterID: .hapticIntensity, value: strength)
    let pS = CHHapticEventParameter(parameterID: .hapticSharpness, value: sharpness)
    let ev = CHHapticEvent(eventType: .hapticContinuous, parameters: [pI, pS], relativeTime: 0, duration: dur)
    do {
      let pattern = try CHHapticPattern(events: [ev], parameters: [])
      let player = try engine?.makePlayer(with: pattern)
      try player?.start(atTime: 0)
    } catch {
      // swallow on failure
    }
  }

  private func stopSteerHaptics() {
    steerTimer?.invalidate()
    steerTimer = nil
    steerActive = false
  }

  private func ensureEngine() {
    guard #available(iOS 13.0, *), supportsHaptics else { return }
    if engine == nil { setupEngine() }
    if engineStarted == false {
      do { try engine?.start(); engineStarted = true } catch { }
    }
  }

  /// Single transient “tick” (no continuous players)
  private func tick(strength: Float, sharpness: Float) {
    guard #available(iOS 13.0, *), supportsHaptics else { return }

    // Simple rate limit
    let now = CACurrentMediaTime()
    if now - lastSend < (1.0 / maxRateHz) { return }
    lastSend = now

    ensureEngine()

    let pI = CHHapticEventParameter(parameterID: .hapticIntensity, value: strength)
    let pS = CHHapticEventParameter(parameterID: .hapticSharpness, value: sharpness)
    let ev = CHHapticEvent(eventType: .hapticTransient, parameters: [pI, pS], relativeTime: 0)

    do {
      let pattern = try CHHapticPattern(events: [ev], parameters: [])
      let player = try engine?.makePlayer(with: pattern)
      try player?.start(atTime: 0)
    } catch {
      // If the engine glitched, try to recover once
      engineStarted = false
      try? engine?.start()
      engineStarted = true
      do {
        let pattern = try CHHapticPattern(events: [ev], parameters: [])
        let player = try engine?.makePlayer(with: pattern)
        try player?.start(atTime: 0)
      } catch {
        // swallow; stay silent if OS refuses
      }
    }
  }

  // MARK: - Continuous haptics
  private func ensureContinuousPlayer(intensity: Float, sharpness: Float) {
    guard #available(iOS 13.0, *), supportsHaptics else { return }
    ensureEngine()
    if contPlayer == nil {
      do {
        let pI = CHHapticEventParameter(parameterID: .hapticIntensity, value: intensity)
        let pS = CHHapticEventParameter(parameterID: .hapticSharpness, value: sharpness)
        let ev = CHHapticEvent(eventType: .hapticContinuous, parameters: [pI, pS], relativeTime: 0, duration: contPatternDur)
        let pattern = try CHHapticPattern(events: [ev], parameters: [])
        contPlayer = try engine?.makeAdvancedPlayer(with: pattern)
      } catch {
        contPlayer = nil
      }
    }
  }

  private func startContinuous(intensity: Float, sharpness: Float) {
    guard #available(iOS 13.0, *), supportsHaptics else { return }
    ensureContinuousPlayer(intensity: intensity, sharpness: sharpness)
    do {
      // Start or restart
      try contPlayer?.stop(atTime: 0)
      try contPlayer?.start(atTime: 0)
      // Initial params
      try sendContinuousParams(intensity: intensity, sharpness: sharpness)
      scheduleContinuousRefresh()
    } catch {
      teardownContinuous()
    }
  }

  private func updateContinuous(intensity: Float, sharpness: Float) {
    guard #available(iOS 13.0, *), supportsHaptics else { return }
    let now = CACurrentMediaTime()
    if now - contLastUpdate < (1.0 / contMaxRateHz) { return }
    contLastUpdate = now
    if contPlayer == nil {
      startContinuous(intensity: intensity, sharpness: sharpness)
      return
    }
    do {
      try sendContinuousParams(intensity: intensity, sharpness: sharpness)
    } catch {
      // Attempt to recover once
      startContinuous(intensity: intensity, sharpness: sharpness)
    }
  }

  private func sendContinuousParams(intensity: Float, sharpness: Float) throws {
    guard #available(iOS 13.0, *) else { return }
    let pI = CHHapticDynamicParameter(parameterID: .hapticIntensityControl, value: intensity, relativeTime: 0)
    let pS = CHHapticDynamicParameter(parameterID: .hapticSharpnessControl, value: sharpness, relativeTime: 0)
    try contPlayer?.sendParameters([pI, pS], atTime: 0)
  }

  private func scheduleContinuousRefresh() {
    contTimer?.invalidate()
    // Restart the pattern before its duration ends to avoid auto-stop glitches
    contTimer = Timer.scheduledTimer(withTimeInterval: contPatternDur * 0.9, repeats: true, block: { [weak self] _ in
      guard let self = self else { return }
      if !self.engineStarted { return }
      do {
        try self.contPlayer?.stop(atTime: 0)
        try self.contPlayer?.start(atTime: 0)
      } catch {
        self.teardownContinuous()
      }
    })
  }

  private func stopContinuous() {
    guard #available(iOS 13.0, *) else { return }
    contTimer?.invalidate()
    contTimer = nil
    do { try contPlayer?.stop(atTime: 0) } catch { }
  }

  private func teardownContinuous() {
    contTimer?.invalidate()
    contTimer = nil
    contPlayer = nil
  }

  private func stop() {
    if #available(iOS 13.0, *) {
      stopContinuous()
      stopSteerHaptics()
      return
    }
  }

  // MARK: - App lifecycle
  override func applicationDidEnterBackground(_ application: UIApplication) {
    stopContinuous()
    stopSteerHaptics()
    if #available(iOS 13.0, *) {
      do { try engine?.stop(); engineStarted = false } catch { }
    }
  }

  override func applicationDidBecomeActive(_ application: UIApplication) {
    ensureEngine()
  }

  // MARK: - Test patterns
  private func runFFBTest() {
    guard #available(iOS 13.0, *), supportsHaptics else { return }
    ensureEngine()
    // 2.2s: modulated bed (ticks at ~20Hz) + a couple of spikes
    let total: Double = 2.2
    let step: Double = 0.05 // 20 Hz
    var t: Double = 0.0
    while t <= total {
      DispatchQueue.main.asyncAfter(deadline: .now() + t) { [weak self] in
        guard let self = self else { return }
        let phase = Float(sin((t/total) * 2.0 * .pi) * 0.25 + 0.45)
        let strength = max(0.18, min(0.95, phase))
        let sharp = Float(0.45)
        self.tick(strength: strength, sharpness: sharp)
      }
      t += step
    }
    // Two impact pairs for emphasis
    DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) { [weak self] in
      self?.tick(strength: 0.75, sharpness: 0.85)
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.03) {
        self?.tick(strength: 0.55, sharpness: 0.45)
      }
    }
    DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) { [weak self] in
      self?.tick(strength: 0.55, sharpness: 0.65)
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.03) {
        self?.tick(strength: 0.90, sharpness: 0.85)
      }
    }
  }
}

fileprivate extension Double {
  func clamp01() -> Double { max(0.0, min(1.0, self)) }
}
