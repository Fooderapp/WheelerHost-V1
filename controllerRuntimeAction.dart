// Automatic FlutterFlow imports
import '/backend/backend.dart';
import '/backend/schema/structs/index.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/custom_code/actions/index.dart'; // Imports other custom actions
import '/flutter_flow/custom_functions.dart'; // Imports custom functions
import 'package:flutter/material.dart';
// Begin custom action code
// DO NOT REMOVE OR MODIFY THE CODE ABOVE!

// FlutterFlow custom action
// File: lib/custom_code/actions/controller_runtime_action.dart
//
// UDP client + sensors + CoreHaptics ticks (NO throttle masking)

import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/services.dart';
import 'package:dchs_motion_sensors/dchs_motion_sensors.dart';

Future<dynamic> controllerRuntimeAction(
  String command,
  String? url,
  double? value,
  String? buttonName,
  bool? buttonPressed,
  double? tiltlock,
  double? deadzone,
) async {
  final ctrl = _UdpController.I;
  try {
    switch (command) {
      case 'start':
        final u = (url ?? '').trim();
        if (!u.startsWith('udp://')) {
          throw Exception('URL must look like udp://<ip>:<port>');
        }
        if (tiltlock != null) ctrl.tiltLockDeg = tiltlock;
        if (deadzone != null) ctrl.tiltDead = deadzone;
        await ctrl.start(u);
        break;

      case 'stop':
        await ctrl.stop();
        break;

      case 'background':
        await ctrl.background();
        break;

      case 'destroy':
        await ctrl.destroy();
        break;

      case 'setThrottle':
        // keep axis for PC, but DO NOT vibrate on throttle
        ctrl.throttle = _toUnit(value);
        ctrl._maybeSendNow(force: true);
        break;

      case 'setBrake':
        ctrl.brake = _toUnit(value);
        ctrl._maybeSendNow(force: true);
        break;

      case 'setButton':
        ctrl.setButton(buttonName ?? '', buttonPressed ?? false);
        break;

      case 'getState':
        // fallthrough
        break;

      case 'ffbTest':
        // Built-in phone-side haptic test.
        // On iOS: ask native to run the pattern, else run Dart fallback.
        if (Platform.isIOS) {
          try { await _Haptics._ios.invokeMethod('ffbTest'); } catch (_) {}
        } else {
          final base = ((value ?? 0.4)).clamp(0.0, 1.0);
          final t0 = DateTime.now().millisecondsSinceEpoch;
          Timer.periodic(const Duration(milliseconds: 16), (t) {
            final now = DateTime.now().millisecondsSinceEpoch;
            final dt = (now - t0) / 1000.0;
            if (dt > 2.5) {
              t.cancel();
              _Haptics.stopContinuous();
              _Haptics.stop();
              return;
            }
            final energy = (base + 0.25 * math.sin(dt * 2 * math.pi)).clamp(0.0, 1.0);
            final L = (0.5 * energy).clamp(0.0, 1.0);
            final R = (0.8 * energy).clamp(0.0, 1.0);
            final bedStrength = (0.20 + 0.60 * math.pow(energy, 0.85)).toDouble().clamp(0.18, 0.95);
            final bedSharp = (0.35 + 0.45 * (0.5 * R + 0.2 * L)).clamp(0.30, 0.90);
            final bedHz = (12.0 + 18.0 * math.pow(energy, 0.85)).toDouble().clamp(12.0, 26.0);
            _Haptics.bedTick(strength: bedStrength, sharpness: bedSharp, maxHz: bedHz);
            if ((now ~/ 180) % 2 == 0 && energy > 0.35) {
              _Haptics.doubleTick(a1: 0.55 + 0.35 * energy, s1: 0.55, a2: 0.65 + 0.35 * energy, s2: 0.85, gapMs: 34);
            }
          });
        }
        break;

      default:
        throw Exception('Unknown command: $command');
    }
  } catch (e) {
    final snap = ctrl._snapshotJson();
    snap['error'] = e.toString();
    return snap;
  }

  return ctrl._snapshotJson();
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
double _clamp01(double v) => v < 0.0 ? 0.0 : (v > 1.0 ? 1.0 : v);
double _clamp1(double v) => v < -1.0 ? -1.0 : (v > 1.0 ? 1.0 : v);
double _toUnit(double? v) {
  var x = (v ?? 0.0).toDouble();
  if (x > 1.0) {
    if (x <= 100.0) {
      x = x / 100.0;
    } else if (x <= 255.0) {
      x = x / 255.0;
    } else {
      x = 1.0;
    }
  }
  if (x < 0.0) x = 0.0;
  if (x > 1.0) x = 1.0;
  return x;
}

// ─── Haptics: transient ticks only ────────────────────────────────────────────
class _Haptics {
  static const _ios = MethodChannel('core_haptics');
  static bool _iosKnown = false;
  static bool _iosOK = false;
  static int _lastTickMs = 0;
  static int _lastContMs = 0;
  static int _lastBedMs = 0;
  static bool _contOn = false;

  static Future<void> _probeIOS() async {
    if (_iosKnown) return;
    _iosKnown = true;
    try {
      final sup = await _ios.invokeMethod('supported');
      _iosOK = sup == true;
    } catch (_) {
      _iosOK = false;
    }
  }

  static Future<void> tick({
    required double strength,
    required double sharpness,
    double maxHz = 24.0,
  }) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    final minDelta = (1000.0 / maxHz).floor();
    if (now - _lastTickMs < minDelta) return;
    _lastTickMs = now;

    if (Platform.isIOS) {
      await _probeIOS();
      if (_iosOK) {
        try {
          await _ios.invokeMethod('tick', {
            'strength': strength.clamp(0.0, 1.0),
            'sharpness': sharpness.clamp(0.0, 1.0),
          });
          return;
        } catch (_) {}
      }
    }
    // Fallback (Android / old iOS)
    try {
      await HapticFeedback.vibrate();
    } catch (_) {}
  }

  // Separate limiter for bed pulses to avoid starving when spikes occur.
  static Future<void> bedTick({
    required double strength,
    required double sharpness,
    double maxHz = 20.0,
  }) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    final minDelta = (1000.0 / maxHz).floor();
    if (now - _lastBedMs < minDelta) return;
    _lastBedMs = now;

    if (Platform.isIOS) {
      await _probeIOS();
      if (_iosOK) {
        try {
          await _ios.invokeMethod('tick', {
            'strength': strength.clamp(0.0, 1.0),
            'sharpness': sharpness.clamp(0.0, 1.0),
          });
          return;
        } catch (_) {}
      }
    }
    try {
      await HapticFeedback.vibrate();
    } catch (_) {}
  }

  static Future<void> doubleTick({
    double a1 = 0.45,
    double s1 = 0.65,
    double a2 = 0.85,
    double s2 = 0.85,
    int gapMs = 36,
  }) async {
    await tick(strength: a1, sharpness: s1, maxHz: 60);
    Timer(Duration(milliseconds: gapMs < 28 ? 28 : gapMs), () {
      tick(strength: a2, sharpness: s2, maxHz: 60);
    });
  }

  static Future<void> tripleBurst({
    double a1 = 0.85,
    double s1 = 0.85,
    double a2 = 0.65,
    double s2 = 0.60,
    double a3 = 0.50,
    double s3 = 0.45,
    int gap1Ms = 28,
    int gap2Ms = 22,
  }) async {
    await tick(strength: a1, sharpness: s1, maxHz: 60);
    Timer(Duration(milliseconds: gap1Ms < 18 ? 18 : gap1Ms), () {
      tick(strength: a2, sharpness: s2, maxHz: 60);
      Timer(Duration(milliseconds: gap2Ms < 18 ? 18 : gap2Ms), () {
        tick(strength: a3, sharpness: s3, maxHz: 60);
      });
    });
  }

  static Future<void> stop() async {
    _lastTickMs = 0;
    if (Platform.isIOS) {
      try {
        await _ios.invokeMethod('steerHapticsStop');
        await _ios.invokeMethod('stop');
      } catch (_) {}
    }
  }

  static Future<void> updateContinuous({
    required double intensity,
    required double sharpness,
    double maxHz = 60.0,
  }) async {
    final now = DateTime.now().millisecondsSinceEpoch;
    final minDelta = (1000.0 / maxHz).floor();
    if (now - _lastContMs < minDelta) return;
    _lastContMs = now;
    intensity = intensity.clamp(0.0, 1.0);
    sharpness = sharpness.clamp(0.0, 1.0);

    if (Platform.isIOS) {
      await _probeIOS();
      if (_iosOK) {
        try {
          if (!_contOn) {
            await _ios.invokeMethod('startContinuous', {
              'intensity': intensity,
              'sharpness': sharpness,
            });
            _contOn = true;
          } else {
            await _ios.invokeMethod('updateContinuous', {
              'intensity': intensity,
              'sharpness': sharpness,
            });
          }
          return;
        } catch (_) {
          // fall through to Android/no-op
        }
      }
    }
    // Android / fallback: no continuous engine, ignore but keep compatibility
  }

  static Future<void> stopContinuous() async {
    _lastContMs = 0;
    if (!_contOn) return;
    _contOn = false;
    if (Platform.isIOS) {
      try {
        await _ios.invokeMethod('stopContinuous');
      } catch (_) {}
    }
  }
}

// ─── Controller ───────────────────────────────────────────────────────────────
class _UdpController with WidgetsBindingObserver {
  static final _UdpController I = _UdpController._();
  _UdpController._();

  // UDP
  RawDatagramSocket? _sock;
  InternetAddress? _dstAddr;
  int _dstPort = 0;
  int _seq = 0;

  // Loop
  Timer? _tick; // 60 Hz
  bool _running = false;
  bool _foreground = true;

  // Sensors
  StreamSubscription? _accSub;
  StreamSubscription? _screenSub;

  // Screen parity
  double _screenDeg = 0.0;
  int? _lockedParity;
  int _parityStableSince = 0;
  int _currentParity() => (_screenDeg == 270.0) ? -1 : 1;

  // Gravity LPF
  double _gY = 0.0, _gZ = 0.0;
  // Higher alpha → more immediate response (less lag)
  static const double _gAlpha = 0.35;

  // Lateral accel EMA (kept if you want to use later)
  double _emaLat = 0.0;
  static const double _accAlpha = 0.2;

  // State
  double steeringX = 0.0;
  double throttle = 0.0;
  double brake = 0.0;

  // Buttons
  bool btnA = false,
      btnB = false,
      btnX = false,
      btnY = false,
      btnLB = false,
      btnRB = false,
      btnStart = false,
      btnBack = false,
      dpadUp = false,
      dpadDown = false,
      dpadLeft = false,
      dpadRight = false,
      btnHandbrake = false;

  // D-Pad → Left Stick (DIRT menu: Y inverted)
  double _lsX = 0.0, _lsY = 0.0;

  final Map<String, int> _btnLatchUntil = {};
  static const int _btnLatchFrames = 3;

  // Game feedback (from Python)
  int? fbAckSeq;
  double fbRumbleL = 0.0;
  double fbRumbleR = 0.0;
  int fbLastRxMs = 0;
  // Expanded feedback (optional fields from Python expander)
  double fbTrigL = 0.0; // ABS gate [0..1]
  double fbTrigR = 0.0; // Slip gate [0..1]
  double fbImpact = 0.0; // Impact strength [0..1]
  // Local rate limiters for expanded channels
  int _lastAbsTickMs = 0;
  int _lastSlipTickMs = 0;
  int _lastImpactMs = 0;

  // EMAs
  double _emaL = 0.0, _emaR = 0.0;
  static const double _emaA = 0.25;

  // Center double-click gate
  int _lastCenterMs = 0;

  // Tuning for steering ramp
  static const double _dead = 0.06;

  // Tilt params
  double tiltLockDeg = 70.0;
  double tiltDead = 0.05;
  static const double _tiltExpo = 0.22;
  static const double _gainLeft = 1.00;
  static const double _gainRight = 1.00;

  // timing
  int _lastStepMs = 0;

  // Network pacing
  // Allow up to ~60 Hz network sends when needed
  static const int _MIN_SEND_MS = 16;
  static const int _MAX_SILENCE_MS = 90;
  int _lastSendMs = 0;
  double _lastSentSteer = 0.0,
      _lastSentThr = 0.0,
      _lastSentBrk = 0.0,
      _lastSentLsX = 0.0,
      _lastSentLsY = 0.0;
  bool _lastBtnA = false,
      _lastBtnB = false,
      _lastBtnX = false,
      _lastBtnY = false,
      _lastBtnLB = false,
      _lastBtnRB = false,
      _lastBtnStart = false,
      _lastBtnBack = false,
      _lastDpadUp = false,
      _lastDpadDown = false,
      _lastDpadLeft = false,
      _lastDpadRight = false,
      _lastHB = false;

  bool get connected => _sock != null && _running;

  // Lifecycle
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (!_running) return;
    if (state == AppLifecycleState.resumed) {
      _foreground = true;
    } else {
      _foreground = false;
      background();
    }
  }

  Future<void> start(String udpUrl) async {
    await stop();

    WidgetsBinding.instance.addObserver(this);
    _foreground = true;

    // Parse & resolve
    late final Uri u;
    try {
      u = Uri.parse(udpUrl);
      if (u.scheme != 'udp' || u.host.isEmpty || u.port == 0) {
        throw Exception('Bad udp URL');
      }
    } catch (_) {
      throw Exception('Bad UDP url. Use udp://<ip>:<port>');
    }

    InternetAddress? addr = InternetAddress.tryParse(u.host);
    if (addr == null) {
      final list = await InternetAddress.lookup(u.host);
      addr = list.firstWhere((a) => a.type == InternetAddressType.IPv4,
          orElse: () => list.first);
    }
    _dstAddr = addr;
    _dstPort = u.port;

    // Bind
    _sock = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
    _sock!.broadcastEnabled = false;

    // Listen feedback (from Python: rumbleL/rumbleR)
    _sock!.listen((event) {
      if (event == RawSocketEvent.read) {
        final dg = _sock!.receive();
        if (dg == null) return;
        try {
          final s = utf8.decode(dg.data);
          if (s.isEmpty || s.codeUnitAt(0) != 123) return; // '{'
          final obj = jsonDecode(s);
          if (obj is Map) {
            if (obj['type'] == 'finetune') return;
            fbAckSeq = (obj['ack'] as num?)?.toInt() ?? fbAckSeq;
            fbRumbleL = (obj['rumbleL'] as num?)?.toDouble() ?? fbRumbleL;
            fbRumbleR = (obj['rumbleR'] as num?)?.toDouble() ?? fbRumbleR;
            // Optional expanded channels
            final trigL = (obj['trigL'] as num?)?.toDouble();
            final trigR = (obj['trigR'] as num?)?.toDouble();
            final impact = (obj['impact'] as num?)?.toDouble();
            if (trigL != null) fbTrigL = trigL.clamp(0.0, 1.0);
            if (trigR != null) fbTrigR = trigR.clamp(0.0, 1.0);
            if (impact != null) fbImpact = impact.clamp(0.0, 1.0);
            fbLastRxMs = DateTime.now().millisecondsSinceEpoch;

            // EMAs
            _emaL = _emaA * fbRumbleL + (1 - _emaA) * _emaL;
            _emaR = _emaA * fbRumbleR + (1 - _emaA) * _emaR;
          }
        } catch (_) {}
      }
    });

    // Sensors @ 60Hz
    final us60 = Duration.microsecondsPerSecond ~/ 60;
    motionSensors.accelerometerUpdateInterval = us60;
    _lockedParity = _currentParity();
    _parityStableSince = DateTime.now().millisecondsSinceEpoch;
    _accSub = motionSensors.accelerometer.listen(_onAccel);
    _screenSub = motionSensors.screenOrientation.listen(_onScreen);

    // Local loop
    _lastStepMs = DateTime.now().millisecondsSinceEpoch;
    _tick = Timer.periodic(const Duration(milliseconds: 16), (_) => _step());
    _running = true;

    // Bootstrap heartbeats for 1.5s
    final t0 = DateTime.now().millisecondsSinceEpoch;
    Timer.periodic(const Duration(milliseconds: 150), (t) {
      if (!_running) return t.cancel();
      final now = DateTime.now().millisecondsSinceEpoch;
      if (now - t0 > 1500) return t.cancel();
      _sendNow(force: true);
    });

    _sendNow(force: true);
  }

  Future<void> background() async {
    if (_sock == null || _dstAddr == null) return;
    try {
      _sock!.send(utf8.encode(jsonEncode({"type": "inbackground"})), _dstAddr!,
          _dstPort);
    } catch (_) {}
    await _Haptics.stopContinuous();
    await _Haptics.stop();
  }

  Future<void> destroy() async {
    if (_sock == null || _dstAddr == null) return;
    try {
      _sock!.send(
          utf8.encode(jsonEncode({"type": "disconnect"})), _dstAddr!, _dstPort);
    } catch (_) {}
    await stop();
  }

  Future<void> stop() async {
    try {
      if (_sock != null && _dstAddr != null) {
        _sock!.send(utf8.encode(jsonEncode({"type": "inbackground"})),
            _dstAddr!, _dstPort);
      }
    } catch (_) {}

    _running = false;

    await _accSub?.cancel();
    _accSub = null;
    await _screenSub?.cancel();
    _screenSub = null;
    _tick?.cancel();
    _tick = null;

    try {
      _sock?.close();
    } catch (_) {}
    _sock = null;

    await _Haptics.stop();
    await _Haptics.stopContinuous();

    steeringX = throttle = brake = 0.0;
    btnA = btnB = btnX = btnY = btnLB = btnRB =
        btnStart = btnBack = dpadUp = dpadDown = dpadLeft = dpadRight = false;
    btnHandbrake = false;
    _lsX = _lsY = 0.0;

    fbRumbleL = fbRumbleR = 0.0;
    fbLastRxMs = 0;

    _seq = 0;
    _lastSendMs = 0;

    WidgetsBinding.instance.removeObserver(this);
  }

  void _onAccel(AccelerometerEvent a) {
    _gY = _gAlpha * a.y + (1 - _gAlpha) * _gY;
    _gZ = _gAlpha * a.z + (1 - _gAlpha) * _gZ;
    _emaLat = _accAlpha * a.y + (1 - _accAlpha) * _emaLat;
  }

  void _onScreen(ScreenOrientationEvent e) {
    final now = DateTime.now().millisecondsSinceEpoch;
    final newParity = (e.angle ?? 0.0) == 270.0 ? -1 : 1;
    if (newParity != _lockedParity) {
      if (_parityStableSince == 0) _parityStableSince = now;
      if (now - _parityStableSince > 600) {
        _lockedParity = newParity;
        _parityStableSince = 0;
      }
    } else {
      _parityStableSince = 0;
    }
    _screenDeg = e.angle ?? 0.0;
  }

  void setButton(String name, bool pressed) {
    switch (name.trim()) {
      case 'A':
        btnA = pressed;
        break;
      case 'B':
        btnB = pressed;
        break;
      case 'X':
        btnX = pressed;
        break;
      case 'Y':
        btnY = pressed;
        break;
      case 'LB':
        btnLB = pressed;
        break;
      case 'RB':
        btnRB = pressed;
        break;
      case 'Start':
        btnStart = pressed;
        break;
      case 'Back':
        btnBack = pressed;
        break;
      case 'DPadUp':
        dpadUp = pressed;
        break;
      case 'DPadDown':
        dpadDown = pressed;
        break;
      case 'DPadLeft':
        dpadLeft = pressed;
        break;
      case 'DPadRight':
        dpadRight = pressed;
        break;
      case 'HB':
        btnHandbrake = pressed;
        break;
      default:
        return;
    }

    // DIRT 5: LS Y inverted (Up = -1)
    _lsX = (dpadLeft ? -1.0 : 0.0) + (dpadRight ? 1.0 : 0.0);
    _lsX = _lsX.clamp(-1.0, 1.0);
    _lsY = ((dpadUp ? -1.0 : 0.0) + (dpadDown ? 1.0 : 0.0)).clamp(-1.0, 1.0);

    final now = DateTime.now().millisecondsSinceEpoch;
    _btnLatchUntil[name] = now + (_btnLatchFrames * 16);
    _maybeSendNow(force: true);
  }

  void _centerDoubleClickGate(double prev, double cur) {
    // Disabled per request: avoid any center tick
    return;
  }

  void _step() {
    if (!_foreground) return;

    final now = DateTime.now().millisecondsSinceEpoch;
    _lastStepMs = now;

    final parity = (_lockedParity ?? 1);
    double tilt = math.atan2(_gY, _gZ); // roll
    if (tilt.abs() < tiltDead) tilt = 0.0;

    final lockRad = tiltLockDeg * math.pi / 180.0;
    double x = (tilt / lockRad).clamp(-1.0, 1.0);

    if (_tiltExpo > 0) {
      final s = x.sign, a = x.abs();
      x = s * ((1 - _tiltExpo) * a + _tiltExpo * (a * a * a));
    }

    x = (parity == -1 ? -x : x);
    x = x < 0 ? x * _gainLeft : x * _gainRight;

    final prev = steeringX;
    steeringX = _clamp1(x);

    // Game FFB bed + spikes, and steering-based ticks
    _driveHaptics();
    _driveSteeringHaptics();
    _maybeSendNow();
  }

  // Game FFB → phone haptics (bed pulses + spike pairs)
  void _driveHaptics() {
    // Game FFB mapping (rumble → ticks)
    final now = DateTime.now().millisecondsSinceEpoch;
    if (fbLastRxMs == 0 || (now - fbLastRxMs) > 500) {
      _Haptics.stopContinuous();
      return;
    }

    double L = fbRumbleL.clamp(0.0, 1.0);
    double R = fbRumbleR.clamp(0.0, 1.0);

    // Pseudo-"bed" using transient ticks instead of continuous player.
    // This avoids CoreHaptics continuous issues on some devices/OS.
    final energy = (0.6 * L + 0.8 * R).clamp(0.0, 1.0);
    final bedStrength = (0.15 + 0.55 * math.pow(energy, 0.85))
        .toDouble()
        .clamp(0.15, 0.85);
    final bedSharp = (0.30 + 0.45 * (0.5 * R + 0.2 * L)).clamp(0.25, 0.85);
    final bedHz = (12.0 + 18.0 * math.pow(energy, 0.85))
        .toDouble()
        .clamp(12.0, 24.0);
    if (energy > 0.02) {
      // Ensure any prior continuous bed is off
      _Haptics.stopContinuous();
      _Haptics.bedTick(strength: bedStrength, sharpness: bedSharp, maxHz: bedHz);
    } else {
      _Haptics.stopContinuous();
    }

    // Spike detection v. EMAs (impacts/ABS etc.)
    final spikeL = (L - _emaL) > 0.10;
    final spikeR = (R - _emaR) > 0.10;
    _emaL = _emaA * L + (1 - _emaA) * _emaL;
    _emaR = _emaA * R + (1 - _emaA) * _emaR;

    if (spikeL && !spikeR) {
      // LEFT: strong→soft pair
      final a1 = (0.45 + 0.45 * L).clamp(0.35, 0.95);
      final a2 = (0.22 + 0.40 * L).clamp(0.18, 0.75);
      _Haptics.doubleTick(a1: a1, s1: 0.45, a2: a2, s2: 0.35, gapMs: 36);
      return;
    }
    if (spikeR && !spikeL) {
      // RIGHT: soft→strong pair
      final a1 = (0.28 + 0.35 * R).clamp(0.22, 0.70);
      final a2 = (0.50 + 0.50 * R).clamp(0.40, 1.00);
      _Haptics.doubleTick(a1: a1, s1: 0.65, a2: a2, s2: 0.85, gapMs: 34);
      return;
    }

    // Expanded channels from Python expander
    final now2 = DateTime.now().millisecondsSinceEpoch;
    // ABS pulses on left trigger gate
    if (fbTrigL > 0.05) {
      final absHz = (8.0 + 8.0 * fbTrigL).clamp(8.0, 16.0);
      final minDelta = (1000.0 / absHz).floor();
      if (now2 - _lastAbsTickMs >= minDelta) {
        final a = (0.28 + 0.55 * fbTrigL).clamp(0.22, 0.95);
        _Haptics.tick(strength: a, sharpness: 0.50, maxHz: 60);
        _lastAbsTickMs = now2;
      }
    }
    // Slip pulses on right trigger gate
    if (fbTrigR > 0.05) {
      final slipHz = (7.0 + 10.0 * fbTrigR).clamp(7.0, 17.0);
      final minDelta = (1000.0 / slipHz).floor();
      if (now2 - _lastSlipTickMs >= minDelta) {
        final a = (0.26 + 0.60 * fbTrigR).clamp(0.22, 1.00);
        _Haptics.tick(strength: a, sharpness: 0.65, maxHz: 60);
        _lastSlipTickMs = now2;
      }
    }
    // Strong impact burst when signaled
    if (fbImpact > 0.08 && (now2 - _lastImpactMs) > 90) {
      final a1 = (0.70 + 0.30 * fbImpact).clamp(0.70, 1.00);
      final a2 = (0.45 + 0.35 * fbImpact).clamp(0.40, 0.90);
      final a3 = (0.35 + 0.30 * fbImpact).clamp(0.30, 0.80);
      _Haptics.tripleBurst(a1: a1, s1: 0.85, a2: a2, s2: 0.60, a3: a3, s3: 0.45, gap1Ms: 30, gap2Ms: 22);
      _lastImpactMs = now2;
    }
  }

  // Steering position → periodic transient ticks on iOS.
  // Center = no vibration. Towards sides = higher tick rate and intensity.
  void _driveSteeringHaptics() {
    // iOS native scheduler handles rate limiting and curve mapping.
    if (Platform.isIOS) {
      try {
        _Haptics._ios.invokeMethod('steerHapticsUpdate', {
          'pos': steeringX,
          // Optional tuning exposed here if needed later:
          // 'deadzone': 0.10,
          // 'curve': 3.2,
        });
      } catch (_) {}
    } else {
      // Android/fallback: light manual ticks at edges using Dart limiter
      final ax = steeringX.abs();
      const dead = 0.16; // match iOS deadzone
      if (ax <= dead) return;
      final m = ((ax - dead) / (1.0 - dead)).clamp(0.0, 1.0);
      final curved = math.pow(m, 3.2).toDouble(); // cubic-ish
      final rate = (4.0 + 20.0 * curved).clamp(0.0, 24.0);
      final intensity = (0.06 + 0.72 * curved).clamp(0.06, 1.0);
      final sharp = (0.35 + 0.35 * curved).clamp(0.35, 0.8);
      if (rate <= 0.0) return;
      _Haptics.tick(strength: intensity, sharpness: sharp, maxHz: rate);
    }
  }

  void _maybeSendNow({bool force = false}) {
    final now = DateTime.now().millisecondsSinceEpoch;
    if (!force && (now - _lastSendMs) > _MAX_SILENCE_MS) {
      _sendNow(force: true);
      return;
    }

    final btnChanged = (btnA != _lastBtnA) ||
        (btnB != _lastBtnB) ||
        (btnX != _lastBtnX) ||
        (btnY != _lastBtnY) ||
        (btnLB != _lastBtnLB) ||
        (btnRB != _lastBtnRB) ||
        (btnStart != _lastBtnStart) ||
        (btnBack != _lastBtnBack) ||
        (dpadUp != _lastDpadUp) ||
        (dpadDown != _lastDpadDown) ||
        (dpadLeft != _lastDpadLeft) ||
        (dpadRight != _lastDpadRight) ||
        (btnHandbrake != _lastHB);

    if (force || btnChanged) {
      _sendNow(force: true);
      return;
    }

    final steerDelta = (steeringX - _lastSentSteer).abs();
    final thrDelta = (throttle - _lastSentThr).abs();
    final brkDelta = (brake - _lastSentBrk).abs();
    final lsxDelta = (_lsX - _lastSentLsX).abs();
    final lsyDelta = (_lsY - _lastSentLsY).abs();

    final bigChange = steerDelta > 0.006 ||
        thrDelta > 0.02 ||
        brkDelta > 0.02 ||
        lsxDelta > 0.02 ||
        lsyDelta > 0.02;

    if (!bigChange && (now - _lastSendMs) < _MIN_SEND_MS) return;
    _sendNow(force: false);
  }

  void _sendNow({bool force = false}) {
    if (!_running || _sock == null || _dstAddr == null) return;
    final now = DateTime.now().millisecondsSinceEpoch;

    bool _latched(String key, bool state) =>
        state || ((_btnLatchUntil[key] ?? 0) > now);

    final payload = {
      "sig": "WHEEL1",
      "seq": _seq++,
      "t": now,
      "axis": {
        "steering_x": steeringX,
        "throttle": _clamp01(throttle),
        "brake": _clamp01(brake),
        "latG": _emaLat,
        "ls_x": _lsX,
        "ls_y": _lsY, // Up = -1 (DIRT)
      },
      "buttons": {
        "A": _latched('A', btnA),
        "B": _latched('B', btnB),
        "X": _latched('X', btnX),
        "Y": _latched('Y', btnY),
        "LB": _latched('LB', btnLB),
        "RB": _latched('RB', btnRB),
        "Start": _latched('Start', btnStart),
        "Back": _latched('Back', btnBack),
        "HB": _latched('HB', btnHandbrake),
        "DPadUp": _latched('DPadUp', dpadUp),
        "DPadDown": _latched('DPadDown', dpadDown),
        "DPadLeft": _latched('DPadLeft', dpadLeft),
        "DPadRight": _latched('DPadRight', dpadRight),
      },
      "meta": {
        "device": "flutter_mobile",
        "screen_deg": _screenDeg,
        if (force) "hello": true,
        "tiltLockDeg": tiltLockDeg,
        "tiltDead": tiltDead
      }
    };

    try {
      final bytes = utf8.encode(jsonEncode(payload));
      _sock!.send(bytes, _dstAddr!, _dstPort);

      _lastSendMs = now;
      _lastSentSteer = steeringX;
      _lastSentThr = throttle;
      _lastSentBrk = brake;
      _lastSentLsX = _lsX;
      _lastSentLsY = _lsY;

      _lastBtnA = btnA;
      _lastBtnB = btnB;
      _lastBtnX = btnX;
      _lastBtnY = btnY;
      _lastBtnLB = btnLB;
      _lastBtnRB = btnRB;
      _lastBtnStart = btnStart;
      _lastBtnBack = btnBack;
      _lastDpadUp = dpadUp;
      _lastDpadDown = dpadDown;
      _lastDpadLeft = dpadLeft;
      _lastDpadRight = dpadRight;
      _lastHB = btnHandbrake;
    } catch (_) {}
  }

  Map<String, dynamic> _snapshotJson() => {
        "connected": connected,
        "transport": "udp",
        "dest": {"ip": _dstAddr?.address, "port": _dstPort},
        "seq": _seq,
        "time": DateTime.now().millisecondsSinceEpoch,
        "axis": {
          "steering_x": steeringX,
          "throttle": throttle,
          "brake": brake,
          "latG": _emaLat,
          "ls_x": _lsX,
          "ls_y": _lsY,
        },
        "buttons": {
          "A": btnA,
          "B": btnB,
          "X": btnX,
          "Y": btnY,
          "LB": btnLB,
          "RB": btnRB,
          "Start": btnStart,
          "Back": btnBack,
          "HB": btnHandbrake,
          "DPadUp": dpadUp,
          "DPadDown": dpadDown,
          "DPadLeft": dpadLeft,
          "DPadRight": dpadRight,
        },
        "params": {"tiltLockDeg": tiltLockDeg, "tiltDead": tiltDead},
        "feedback": {
          "rumbleL": fbRumbleL,
          "rumbleR": fbRumbleR,
          "lastRxMs": fbLastRxMs,
        }
      };
}
