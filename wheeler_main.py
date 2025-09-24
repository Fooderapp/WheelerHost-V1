
# wheeler_main.py
# Resizable main window + overlay + UDP server (single-client lock).
# Hotkeys: F9 toggle overlay, F11 reset overlay.

import sys, os, json
# Make sure this script's directory is importable when launched from another CWD (Windows double-click/run)
try:
    _HERE = os.path.dirname(__file__)
    if _HERE and _HERE not in sys.path:
        sys.path.insert(0, _HERE)
except Exception:
    pass
from PySide6 import QtWidgets, QtGui, QtCore
from PySide6.QtCore import Qt

from udp_server import UDPServer, LOG
from overlay import Overlay
try:
    from haptics.audio_probe import list_devices as list_audio_devices
except Exception:
    list_audio_devices = None

# --------- QR Pane (shows QR for udp://IP:PORT but caption is IP:PORT only) ----------
import io, socket, qrcode
from PIL import Image

def list_ipv4():
    ips = []
    hostname = socket.gethostname()
    try:
        for info in socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP):
            addr = info[4][0]
            if "." in addr and not addr.startswith("127.") and addr not in ips:
                ips.append(addr)
    except Exception:
        pass
    # Fallback to localhost resolve
    for host in ["localhost"]:
        try:
            addr = socket.gethostbyname(host)
            if "." in addr and not addr.startswith("127.") and addr not in ips:
                ips.append(addr)
        except Exception:
            pass
    return ips or ["127.0.0.1"]

class QRPane(QtWidgets.QScrollArea):
    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self.port = port
        self.setWidgetResizable(True)
        self._inner = QtWidgets.QWidget()
        self.setWidget(self._inner)
        self.hbox = QtWidgets.QHBoxLayout(self._inner)
        self.hbox.setContentsMargins(8,8,8,8)
        self.hbox.setSpacing(12)
        self.refresh()

    def refresh(self):
        while (item := self.hbox.takeAt(0)) is not None:
            w = item.widget()
            if w: w.deleteLater()
        for ip in list_ipv4():
            url = f"udp://{ip}:{self.port}"
            qr_img = qrcode.make(url)
            if hasattr(qr_img, "get_image"): qr_img = qr_img.get_image()
            qr_img = qr_img.convert("RGB")
            buf = io.BytesIO(); qr_img.save(buf, format="PNG")
            pix = QtGui.QPixmap(); pix.loadFromData(buf.getvalue(), "PNG")
            panel = QtWidgets.QFrame(); panel.setFrameShape(QtWidgets.QFrame.NoFrame)
            v = QtWidgets.QVBoxLayout(panel); v.setContentsMargins(10,10,10,10); v.setSpacing(8)
            lblImg = QtWidgets.QLabel(); lblImg.setPixmap(pix); lblImg.setAlignment(Qt.AlignCenter)
            # Caption is IP:PORT only (no udp://)
            lblTxt = QtWidgets.QLabel(f"{ip}:{self.port}"); lblTxt.setAlignment(Qt.AlignCenter)
            lblTxt.setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.addWidget(lblImg); v.addWidget(lblTxt)
            self.hbox.addWidget(panel)
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.hbox.addWidget(spacer)

# --------- Main Window ----------
class MainWindow(QtWidgets.QWidget):
    def _generate_haptic_patterns(self, events):
        """
        Map ONNX events to rich haptic patterns for phone telemetry, with prioritization and force mute.
        Returns a dict with keys: impact, trigL, trigR, audInt, audHz, audLowInt, audLowHz, audHighInt, audHighHz, rumbleL, rumbleR
        """
        # Prioritization: 1. Impact 2. Road/Skid 3. Engine 4. Music
        priorities = [
            ('impact', ['impact', 'crash', 'bang', 'hit']),
            ('road', ['road', 'dirt', 'surface', 'gravel', 'skid', 'tire', 'squeal', 'brake']),
            ('engine', ['engine', 'motor', 'car', 'vehicle']),
            ('music', ['music', 'song', 'melody'])
        ]
        # ... rest of function ...

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Wheeler — Windows (Single Client + Overlay)")
        self.resize(1180, 800)
        self.setMinimumSize(900, 600)
        self._size_grip = QtWidgets.QSizeGrip(self)
        self._size_grip.setFixedSize(16, 16)

        # Server and overlays
        self.server = UDPServer(port=8765)
        self.server.telemetry.connect(self.onTelemetry)
        self.server.buttons.connect(self.onButtons)
        self.server.tuning.connect(self.onRemoteTuning)
        self.server.clients_changed.connect(self.onClientsChanged)
        self.overlays = []
        app = QtWidgets.QApplication.instance()
        try:
            for s in app.screens():
                self.overlays.append(Overlay(screen=s))
        except Exception:
            self.overlays.append(Overlay())

        # Top bar
        top = QtWidgets.QHBoxLayout()
        self.lblLan = QtWidgets.QLabel(f"{list_ipv4()[0]}:8765")
        self.btnStart = QtWidgets.QPushButton("STOP"); self.btnStart.clicked.connect(self.toggleServer)
        self.chkEditOverlay = QtWidgets.QCheckBox("Edit overlay (clickable)"); self.chkEditOverlay.setChecked(False)
        self.chkFreezeSteer = QtWidgets.QCheckBox("Freeze steering (debug)")
        self.cmbPad = QtWidgets.QComboBox(); self.cmbPad.addItems(["X360", "DS4"]); self.cmbPad.setCurrentIndex(0)
        self.lblFfbSrc = QtWidgets.QLabel("FFB: –")
        top.addWidget(self.lblLan); top.addStretch(1)
        top.addWidget(QtWidgets.QLabel("Pad:")); top.addWidget(self.cmbPad); top.addSpacing(8)
        top.addWidget(self.lblFfbSrc); top.addSpacing(8)
        top.addWidget(self.chkFreezeSteer); top.addWidget(self.chkEditOverlay); top.addWidget(self.btnStart)

        # Main layout
        grid = QtWidgets.QGridLayout(self)
        grid.setContentsMargins(16, 12, 16, 12)
        grid.setHorizontalSpacing(18); grid.setVerticalSpacing(12)
        grid.addLayout(top, 0, 0, 1, 2)
        self.leftCol = QtWidgets.QVBoxLayout(); self.rightCol = QtWidgets.QVBoxLayout()
        grid.addLayout(self.leftCol, 1, 0, 1, 1); grid.addLayout(self.rightCol, 1, 1, 1, 1)

        # Left: QR + Inputs
        self.qrPane = QRPane(8765); self.leftCol.addWidget(self.qrPane, 3)
        labInputs = QtWidgets.QLabel("INPUTS (last)"); self.leftCol.addWidget(labInputs)
        inGrid = QtWidgets.QGridLayout(); inGrid.setHorizontalSpacing(16); inGrid.setVerticalSpacing(8)
        self.lblSteerVal = QtWidgets.QLabel("0.00"); self.lblSteerVal.setAlignment(Qt.AlignRight)
        self.prSteer = QtWidgets.QProgressBar(); self.prSteer.setRange(0, 1000); self.prSteer.setTextVisible(False)
        self.lblThrVal = QtWidgets.QLabel("0%"); self.lblThrVal.setAlignment(Qt.AlignRight)
        self.prThrottle = QtWidgets.QProgressBar(); self.prThrottle.setRange(0, 1000); self.prThrottle.setFormat("Throttle %p%")
        self.lblBrkVal = QtWidgets.QLabel("0%"); self.lblBrkVal.setAlignment(Qt.AlignRight)
        self.prBrake = QtWidgets.QProgressBar(); self.prBrake.setRange(0, 1000); self.prBrake.setFormat("Brake %p%")
        inGrid.addWidget(QtWidgets.QLabel("STEERING"), 0, 0); inGrid.addWidget(self.lblSteerVal, 0, 1)
        inGrid.addWidget(self.prSteer, 1, 0, 1, 2)
        inGrid.addWidget(QtWidgets.QLabel("THROTTLE"), 2, 0); inGrid.addWidget(self.lblThrVal, 2, 1)
        inGrid.addWidget(self.prThrottle, 3, 0, 1, 2)
        inGrid.addWidget(QtWidgets.QLabel("BRAKE"), 4, 0); inGrid.addWidget(self.lblBrkVal, 4, 1)
        inGrid.addWidget(self.prBrake, 5, 0, 1, 2)
        self.leftCol.addLayout(inGrid)

        # ONNX visualization labels
        self.lblOnnxEvent = QtWidgets.QLabel("ONNX Event: –")
        self.lblOnnxHaptic = QtWidgets.QLabel("Haptic: –")
        self.lblAudioLevel = QtWidgets.QLabel("Audio Level: –")
        self.leftCol.addWidget(self.lblOnnxEvent)
        self.leftCol.addWidget(self.lblOnnxHaptic)
        self.leftCol.addWidget(self.lblAudioLevel)

        # Right: Overlay group
        boxOverlay = QtWidgets.QGroupBox("Overlay")
        gl = QtWidgets.QGridLayout(boxOverlay)
        self.chkBar = QtWidgets.QCheckBox("Show bottom bar"); self.chkBar.setChecked(True)
        self.chkSides = QtWidgets.QCheckBox("Show side G-force blur"); self.chkSides.setChecked(False)
        gl.addWidget(self.chkBar, 0, 0, 1, 2); gl.addWidget(self.chkSides, 1, 0, 1, 2)
        gl.addWidget(QtWidgets.QLabel("Scale (1..3)"), 2, 0)
        self.spinScale = QtWidgets.QDoubleSpinBox(); self.spinScale.setRange(1.0, 3.0); self.spinScale.setSingleStep(0.05); self.spinScale.setValue(1.7)
        gl.addWidget(self.spinScale, 2, 1)
        gl.addWidget(QtWidgets.QLabel("Blur amount (0..2)"), 3, 0)
        self.spinBlur = QtWidgets.QDoubleSpinBox(); self.spinBlur.setRange(0.0, 2.0); self.spinBlur.setSingleStep(0.05); self.spinBlur.setValue(0.70)
        gl.addWidget(self.spinBlur, 3, 1)
        gl.addWidget(QtWidgets.QLabel("Curve gamma (0.2..4)"), 4, 0)
        self.spinGamma = QtWidgets.QDoubleSpinBox(); self.spinGamma.setRange(0.2, 4.0); self.spinGamma.setSingleStep(0.05); self.spinGamma.setValue(0.80)
        gl.addWidget(self.spinGamma, 4, 1)
        gl.addWidget(QtWidgets.QLabel("Opacity (0..1.5)"), 5, 0)
        self.spinAlpha = QtWidgets.QDoubleSpinBox(); self.spinAlpha.setRange(0.0, 1.5); self.spinAlpha.setSingleStep(0.05); self.spinAlpha.setValue(0.60)
        gl.addWidget(self.spinAlpha, 5, 1)
        self.btnResetOverlay = QtWidgets.QPushButton("Reset overlay"); gl.addWidget(self.btnResetOverlay, 6, 0, 1, 2)
        self.rightCol.addWidget(boxOverlay)

        # Right: Audio Haptics group
        boxAudio = QtWidgets.QGroupBox("Audio Haptics")
        ga = QtWidgets.QGridLayout(boxAudio); ga.setHorizontalSpacing(12); ga.setVerticalSpacing(6)
        self.cmbAudio = QtWidgets.QComboBox(); self.cmbAudio.setMinimumWidth(260)
        devs = []
        if list_audio_devices is not None:
            try:
                devs = list_audio_devices()
            except Exception:
                devs = []
        if not devs:
            devs = [(-1, 'Auto')]
        for idx, label in devs:
            self.cmbAudio.addItem(str(label), idx)
        ga.addWidget(QtWidgets.QLabel("Audio device"), 0, 0); ga.addWidget(self.cmbAudio, 0, 1)
        self.lblAudioStatus = QtWidgets.QLabel("Audio: Inactive"); ga.addWidget(self.lblAudioStatus, 0, 2)
        self.chkOnnxFfb = QtWidgets.QCheckBox("Use ONNX/YAMNet FFB"); self.chkOnnxFfb.setChecked(True)
        ga.addWidget(self.chkOnnxFfb, 0, 3)
        self.sldRoad = QtWidgets.QSlider(Qt.Horizontal); self.sldRoad.setRange(0, 200); self.sldRoad.setValue(100)
        self.sldEng  = QtWidgets.QSlider(Qt.Horizontal); self.sldEng.setRange(0, 200);  self.sldEng.setValue(100)
        self.sldImp  = QtWidgets.QSlider(Qt.Horizontal); self.sldImp.setRange(0, 200);  self.sldImp.setValue(100)
        self.sldMusic = QtWidgets.QSlider(Qt.Horizontal); self.sldMusic.setRange(0, 100); self.sldMusic.setValue(60)
        self.sldIntensity = QtWidgets.QSlider(Qt.Horizontal); self.sldIntensity.setRange(0, 200); self.sldIntensity.setValue(100)
        self.sldGateOn  = QtWidgets.QSlider(Qt.Horizontal); self.sldGateOn.setRange(0, 50);  self.sldGateOn.setValue(12)
        self.sldGateOff = QtWidgets.QSlider(Qt.Horizontal); self.sldGateOff.setRange(0, 50); self.sldGateOff.setValue(5)
        self.sldGateHold= QtWidgets.QSlider(Qt.Horizontal); self.sldGateHold.setRange(100, 1500); self.sldGateHold.setValue(600)
        ga.addWidget(QtWidgets.QLabel("Road gain"), 1, 0); ga.addWidget(self.sldRoad, 1, 1)
        ga.addWidget(QtWidgets.QLabel("Engine gain"), 2, 0); ga.addWidget(self.sldEng,  2, 1)
        ga.addWidget(QtWidgets.QLabel("Impact gain"), 3, 0); ga.addWidget(self.sldImp,  3, 1)
        ga.addWidget(QtWidgets.QLabel("Music suppression"), 4, 0); ga.addWidget(self.sldMusic, 4, 1)
        ga.addWidget(QtWidgets.QLabel("Gate ON thr"), 5, 0); ga.addWidget(self.sldGateOn,  5, 1)
        ga.addWidget(QtWidgets.QLabel("Gate OFF thr"), 6, 0); ga.addWidget(self.sldGateOff, 6, 1)
        ga.addWidget(QtWidgets.QLabel("Gate hold (ms)"), 7, 0); ga.addWidget(self.sldGateHold, 7, 1)
        ga.addWidget(QtWidgets.QLabel("Intensity"), 8, 0); ga.addWidget(self.sldIntensity, 8, 1)
        self.rightCol.addWidget(boxAudio)

        # ONNX FFB state and detector
        self.use_onnx_ffb = False
        self.onnx_detector = None
        self.audio_probe = None
        self.chkOnnxFfb.toggled.connect(self._toggle_onnx_ffb)

        # Clients and Log
        labClients = QtWidgets.QLabel("Client"); self.rightCol.addWidget(labClients)
        self.lstClients = QtWidgets.QListWidget(); self.rightCol.addWidget(self.lstClients, 1)
        labLog = QtWidgets.QLabel("Log"); self.rightCol.addWidget(labLog)
        self.txtLog = QtWidgets.QPlainTextEdit(); self.txtLog.setReadOnly(True); self.rightCol.addWidget(self.txtLog, 1)
        LOG.line.connect(self._appendLog)

        # Overlay wiring
        self.chkBar.toggled.connect(lambda on: self._for_each_overlay(lambda o: o.set_show_bar(on)))
        self.chkSides.toggled.connect(lambda on: self._for_each_overlay(lambda o: o.set_show_sides(on)))
        self.spinScale.valueChanged.connect(lambda v: self._for_each_overlay(lambda o: o.set_scale(v)))
        self.spinBlur.valueChanged.connect(lambda v: self._for_each_overlay(lambda o: o.set_blur_amount(v)))
        self.spinGamma.valueChanged.connect(lambda v: self._for_each_overlay(lambda o: o.set_curve_gamma(v)))
        self.spinAlpha.valueChanged.connect(lambda v: self._for_each_overlay(lambda o: o.set_alpha_strength(v)))
        self.btnResetOverlay.clicked.connect(lambda: self._for_each_overlay(lambda o: o.reset_all()))
        self.chkEditOverlay.toggled.connect(lambda on: self._for_each_overlay(lambda o: o.set_input_enabled(on)))

        # Server wiring
        self.chkFreezeSteer.toggled.connect(self.server.set_freeze_steering)
        self.cmbPad.currentTextChanged.connect(lambda s: self.server.set_pad_target(s.lower()))
        self.cmbAudio.currentIndexChanged.connect(lambda _: self.server.set_audio_device(self.cmbAudio.currentData()))
        self.sldRoad.valueChanged.connect(lambda v: self.server.set_audio_road_gain(v/100.0))
        self.sldEng.valueChanged.connect(lambda v: self.server.set_audio_engine_gain(v/100.0))
        self.sldImp.valueChanged.connect(lambda v: self.server.set_audio_impact_gain(v/100.0))
        self.sldMusic.valueChanged.connect(lambda v: self.server.set_audio_music_suppress(v/100.0))
        self.sldGateOn.valueChanged.connect(lambda v: self.server.set_audio_gate_on(v/100.0))
        self.sldGateOff.valueChanged.connect(lambda v: self.server.set_audio_gate_off(v/100.0))
        self.sldGateHold.valueChanged.connect(lambda v: self.server.set_audio_gate_hold(int(v)))
        self.sldIntensity.valueChanged.connect(lambda v: self.server.set_audio_intensity(v/100.0))
        try:
            self.server.audio_status_changed.connect(lambda s: self.lblAudioStatus.setText(f"Audio: {s}"))
        except Exception:
            pass

        # Hotkeys
        s1 = QtGui.QShortcut(QtGui.QKeySequence("F9"), self); s1.activated.connect(self._toggleOverlayVisible)
        s2 = QtGui.QShortcut(QtGui.QKeySequence("F11"), self); s2.activated.connect(self._resetOverlay)

        # Size grip in corner
        grid.addWidget(self._size_grip, 2, 1, alignment=Qt.AlignRight | Qt.AlignBottom)

        # Start server
        self._running = False
        self.toggleServer()

        # Initialize ONNX if default ON
        if self.chkOnnxFfb.isChecked():
            self._toggle_onnx_ffb(True)

    # ----- ONNX/classic FFB toggle handler -----
    def _toggle_onnx_ffb(self, checked):
        self.use_onnx_ffb = checked
        if checked:
            try:
                from haptics.onnx_audio_event_detector import OnnxAudioEventDetector
                from haptics.audio_probe import AudioProbe
                self.onnx_detector = OnnxAudioEventDetector()
                self.audio_probe = AudioProbe(device=self.cmbAudio.currentData())
                self.lblFfbSrc.setText("FFB: ONNX")
                self.lblAudioStatus.setText("Audio: ONNX active")
            except Exception as e:
                self.lblAudioStatus.setText(f"Audio: ONNX error: {e}")
                self.onnx_detector = None
                self.audio_probe = None
        else:
            self.onnx_detector = None
            self.audio_probe = None
            self.lblAudioStatus.setText("Audio: Inactive")
            self.lblFfbSrc.setText("FFB: AUDIO")

    # ----- server toggle -----
    def toggleServer(self):
        running = self._running
        if not running:
            self.server.start()
            self.btnStart.setText("STOP")
            self.qrPane.refresh()
            self.lblLan.setText(f"{list_ipv4()[0]}:8765")
        else:
            self.server.stop()
            self.btnStart.setText("START")
        self._running = not running

    # ----- log -----
    def _appendLog(self, s: str):
        self.txtLog.moveCursor(QtGui.QTextCursor.End)
        self.txtLog.insertPlainText(s)
        self.txtLog.moveCursor(QtGui.QTextCursor.End)

    # ----- overlay edit state: enable mouse while main window is visible -----
    # Remove implicit overlay mouse grabbing; controlled via the checkbox now
    def showEvent(self, e):
        super().showEvent(e)
    def hideEvent(self, e):
        super().hideEvent(e)
    def changeEvent(self, e):
        super().changeEvent(e)

    # ----- hotkeys -----
    def _toggleOverlayVisible(self):
        any_vis = any(o.isVisible() for o in self.overlays)
        new_vis = not any_vis
        self._for_each_overlay(lambda o: o.set_overlay_visible(new_vis))

    def _resetOverlay(self):
        self._for_each_overlay(lambda o: o.reset_all())

    # ----- slots from server -----
    def onTelemetry(self, x, throttle, brake, latG, seq_any, rumbleL, rumbleR, src):
        steer_bar = int((x * 0.5 + 0.5) * 1000)
        self.prSteer.setValue(max(0, min(1000, steer_bar)))
        self.lblSteerVal.setText(f"{x:+.2f}")
        self.prThrottle.setValue(int(max(0.0, min(1.0, throttle)) * 1000))
        self.prBrake.setValue(int(max(0.0, min(1.0, brake)) * 1000))
        self.lblThrVal.setText(f"{int(throttle*100):d}%")
        self.lblBrkVal.setText(f"{int(brake*100):d}%")
        # Feed overlay
        self._for_each_overlay(lambda o: o.set_telemetry(x, latG))

        # ONNX FFB path - rich haptic pattern generation from sound events
        if getattr(self, 'use_onnx_ffb', False) and self.onnx_detector and self.audio_probe:
            try:
                audio = self.audio_probe.get_onnx_audio()
                if audio is not None:
                    # Show audio level (RMS) without numpy
                    if audio is not None and len(audio) > 0:
                        # audio is expected to be a sequence of floats
                        s = 0.0
                        for v in audio:
                            s += v * v
                        rms = (s / len(audio)) ** 0.5
                    else:
                        rms = 0.0
                    self.lblAudioLevel.setText(f"Audio Level: {rms:.3f}")
                    events = self.onnx_detector.predict(audio)
                    # Generate rich haptic patterns based on sound events
                    haptic_patterns = self._generate_haptic_patterns(events)
                    # Visualize ONNX event and haptic output
                    if events:
                        top_event = max(events, key=lambda e: e[1])
                        self.lblOnnxEvent.setText(f"ONNX Event: {top_event[0]} ({top_event[1]:.2f})")
                    else:
                        self.lblOnnxEvent.setText("ONNX Event: –")
                    if haptic_patterns:
                        self._send_onnx_haptics(haptic_patterns)
                        haptic_str = ', '.join(f"{k}:{v:.2f}" for k,v in haptic_patterns.items() if v > 0.05)
                        self.lblOnnxHaptic.setText(f"Haptic: {haptic_str}")
                        active_events = [name for name, conf in events if conf > 0.1]
                        self.lblFfbSrc.setText(f"FFB: ONNX ({len(active_events)} events: {', '.join(active_events[:2])})")
                    else:
                        self.lblFfbSrc.setText("FFB: ONNX (no events)")
                        self.lblOnnxHaptic.setText("Haptic: –")
                else:
                    self.lblAudioLevel.setText("Audio Level: –")
            except Exception as e:
                self.lblAudioStatus.setText(f"ONNX error: {e}")
                self.lblOnnxEvent.setText("ONNX Event: error")
                self.lblOnnxHaptic.setText("Haptic: –")
                self.lblAudioLevel.setText("Audio Level: error")
        else:
            # FFB source label (classic path)
            try:
                s = str(src).lower() if isinstance(src, (str, bytes)) else ""
                if   s == "real":  self.lblFfbSrc.setText("FFB: REAL")
                elif s == "audio": self.lblFfbSrc.setText("FFB: AUDIO")
                elif s == "synth": self.lblFfbSrc.setText("FFB: SYNTH")
                else:               self.lblFfbSrc.setText("FFB: NONE")
            except Exception:
                pass

    def onButtons(self, btns: dict):
        pass

    def onRemoteTuning(self, changed: dict):
        pass

    def onClientsChanged(self, items):
        self.lstClients.clear()
        self.lstClients.addItems(items)

    # ----- ONNX haptic pattern generation -----
    def _generate_haptic_patterns(self, events):
        """Generate rich haptic patterns based on ONNX sound event detection."""
        import time, math
        
        patterns = {
            'rumbleL': 0.0, 'rumbleR': 0.0,
            'impact': 0.0,
            'trigL': 0.0, 'trigR': 0.0,
            'audInt': 0.0, 'audHz': 120.0,
            'audLowInt': 0.0, 'audLowHz': 60.0,
            'audHighInt': 0.0, 'audHighHz': 200.0,
        }
        
        # Current time for pattern generation
        t = time.time()
        
        for name, confidence in events:
            if confidence < 0.08:  # Skip weak predictions
                continue
                
            name_lower = name.lower()
            
            # Engine sounds - Low frequency rumble
            if any(keyword in name_lower for keyword in ['engine', 'motor', 'car', 'vehicle']):
                patterns['rumbleL'] += confidence * 0.7
                patterns['audLowInt'] += confidence * 0.8
                patterns['audLowHz'] = 45.0 + confidence * 30.0  # 45-75 Hz
            
            # Skidding/Tire squeal - High frequency, fast pulses
            elif any(keyword in name_lower for keyword in ['skid', 'squeal', 'tire', 'brake']):
                # Fast pulsing pattern for skid
                pulse = (math.sin(t * 40) + 1) * 0.5  # 20Hz pulse
                patterns['rumbleR'] += confidence * pulse * 0.9
                patterns['audHighInt'] += confidence * 0.9
                patterns['audHighHz'] = 180.0 + confidence * 50.0  # 180-230 Hz
                patterns['trigR'] += confidence * 0.6
            
            # Road/Surface noise - Textured, medium frequency
            elif any(keyword in name_lower for keyword in ['road', 'surface', 'gravel', 'dirt']):
                # Textured pattern for road surface
                texture = (math.sin(t * 15) * 0.3 + math.sin(t * 23) * 0.2 + 0.5) * 0.5
                patterns['rumbleL'] += confidence * texture * 0.6
                patterns['rumbleR'] += confidence * texture * 0.4
                patterns['audInt'] += confidence * 0.7
                patterns['audHz'] = 90.0 + confidence * 40.0  # 90-130 Hz
            
            # Impact/Crash - Strong hit-like feedback
            elif any(keyword in name_lower for keyword in ['crash', 'bang', 'impact', 'hit']):
                patterns['impact'] += confidence * 1.0
                patterns['trigL'] += confidence * 0.8
                patterns['trigR'] += confidence * 0.8
                patterns['rumbleL'] += confidence * 0.9
                patterns['rumbleR'] += confidence * 0.9
                patterns['audInt'] += confidence * 1.0
                patterns['audHz'] = 150.0  # Sharp impact frequency
            
            # Wind - Subtle high frequency
            elif any(keyword in name_lower for keyword in ['wind', 'air']):
                patterns['audHighInt'] += confidence * 0.4
                patterns['audHighHz'] = 160.0 + confidence * 80.0  # 160-240 Hz
                patterns['rumbleR'] += confidence * 0.3
        
        # Clamp all values to valid ranges
        for key in patterns:
            if 'Hz' in key:
                patterns[key] = max(20.0, min(300.0, patterns[key]))
            else:
                patterns[key] = max(0.0, min(1.0, patterns[key]))
        
        return patterns if any(v > 0.05 for k, v in patterns.items() if 'Hz' not in k) else None
    
    def _send_onnx_haptics(self, patterns):
        """Send ONNX-generated haptic patterns to the phone via UDP server override."""
        import time
        
        # Override FFB values in server to inject ONNX haptics
        self.server._ffbL = patterns['rumbleL']
        self.server._ffbR = patterns['rumbleR']
        self.server._ffb_ms = int(time.time() * 1000)  # Mark as fresh FFB
        
        # Store patterns for potential future use in server modifications
        if not hasattr(self.server, '_onnx_patterns'):
            self.server._onnx_patterns = {}
        self.server._onnx_patterns.update(patterns)

    # ----- helper -----
    def _for_each_overlay(self, fn):
        try:
            for o in getattr(self, 'overlays', []):
                try:
                    fn(o)
                except Exception:
                    pass
        except Exception:
            pass

# ---------- main ----------
def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow(); w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
