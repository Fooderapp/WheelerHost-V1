"""
AudioProbe: Optional real-time audio capture -> haptics features.

Goals:
- Low-latency (10–20 ms hop) capture of system output when supported
- Extract coarse features: road (broadband), engine (low band), impacts (spectral flux)
- Simple music suppression heuristics to avoid reacting to steady music

Dependencies (optional):
- numpy, sounddevice (PortAudio). If not present or loopback unsupported, probe stays inactive.
"""
from __future__ import annotations

import threading, time
from typing import Optional, Dict

try:
    import numpy as np  # type: ignore
except Exception:
    np = None  # type: ignore

try:
    import sounddevice as sd  # type: ignore
except Exception:
    sd = None  # type: ignore


def list_devices():
    """Return a list of (index, label) devices suitable for input/loopback.
    On Windows WASAPI, prefer devices containing 'loopback'. Includes an 'Auto' option (-1).
    """
    out = [(-1, 'Auto')]
    if sd is None:
        return out
    try:
        devs = sd.query_devices()
        hostapis = sd.query_hostapis()
        for i, d in enumerate(devs):
            max_in = d.get('max_input_channels', 0)
            host = hostapis[d.get('hostapi', 0)].get('name', '')
            name = d.get('name', '')
            label = f"{i}: {name} [{host}]"
            if max_in and max_in > 0:
                out.append((i, label))
            elif 'wasapi' in host.lower() and 'loopback' in name.lower():
                out.append((i, label))
    except Exception:
        pass
    return out


class AudioProbe:
    def __init__(self, samplerate: int = 48000, blocksize: int = 1024, device: int | None = None):
        self.enabled = (np is not None and sd is not None)
        self._sr = int(samplerate)
        self._bs = int(blocksize)
        self._device = device if (isinstance(device, int) and device >= 0) else None
        self._lock = threading.Lock()
        self._features: Dict[str, float] = {"bodyL":0.0, "bodyR":0.0, "impact":0.0}
        # Tunables (thread-safe via _lock). Defaults aimed for general content.
        self._params = {
            "road_gain": 1.0,
            "engine_gain": 1.0,
            "impact_gain": 1.0,
            # Normalization scales (approximate). Higher -> less sensitive
            "road_norm": 0.020,
            "eng_norm":  0.015,
            "imp_norm":  0.010,
            # Music suppression: 0=off, 1=strong
            "music_suppress": 0.6,
            # Suppress when flatness < thresh and flux < gate
            "flat_thresh": 0.25,
            "flux_gate":   0.002,
        }
        self._prev_mag = None
        self._flux_env = 0.0
        self._road_env = 0.0
        self._eng_env = 0.0
        self._last_t = time.time()
        self._stream = None

        if not self.enabled:
            return

        try:
            # Try WASAPI loopback on Windows; default otherwise
            kwargs = { 'dtype':'float32', 'latency':'low', 'samplerate': self._sr, 'channels': 2 }
            if hasattr(sd, 'WasapiSettings'):
                try:
                    # Pick an explicit loopback device if available
                    dev_index = self._device
                    if dev_index is None:
                        try:
                            devs = sd.query_devices()
                            for i, d in enumerate(devs):
                                name = str(d.get('name','')).lower()
                                host = sd.query_hostapis()[d.get('hostapi',0)].get('name','').lower()
                                if 'wasapi' in host and 'loopback' in name and d.get('max_input_channels',0) >= 1:
                                    dev_index = i; break
                        except Exception:
                            dev_index = None
                    ws = sd.WasapiSettings(loopback=True)
                    self._stream = sd.InputStream(callback=self._cb, blocksize=self._bs, extra_settings=ws, device=dev_index, **kwargs)
                except Exception:
                    self._stream = sd.InputStream(callback=self._cb, blocksize=self._bs, **kwargs)
            else:
                self._stream = sd.InputStream(callback=self._cb, blocksize=self._bs, samplerate=self._sr, channels=2, dtype='float32', latency='low')
            self._stream.start()
        except Exception:
            self.enabled = False
            self._stream = None

    def close(self):
        try:
            if self._stream is not None:
                self._stream.stop(); self._stream.close()
        except Exception:
            pass

    def _cb(self, indata, frames, time_info, status):
        try:
            x = np.asarray(indata, dtype=np.float32)
            if x.ndim == 2:
                x = x.mean(axis=1)
            # Hann window
            N = int(len(x))
            if N <= 0: return
            w = np.hanning(N).astype(np.float32)
            xf = np.fft.rfft(x * w)
            mag = np.abs(xf)
            freqs = np.fft.rfftfreq(N, 1.0/self._sr)

            # Bands
            def band(a,b):
                i0 = int(a * N / self._sr)
                i1 = int(b * N / self._sr)
                m = mag[(freqs>=a) & (freqs<=b)]
                return m

            # Spectral flux in 80–250Hz
            m_band = mag[(freqs>=80) & (freqs<=250)]
            flux = 0.0
            if self._prev_mag is not None and len(self._prev_mag)==len(mag):
                d = m_band - self._prev_mag[(freqs>=80) & (freqs<=250)]
                flux = float(np.sum(np.maximum(d, 0.0))) / max(1, len(m_band))
            self._prev_mag = mag.copy()

            # Road broadband envelope 150–800Hz
            road_band = mag[(freqs>=150) & (freqs<=800)]
            road = float(np.mean(road_band)) if road_band.size else 0.0

            # Engine low band 50–200Hz
            eng_band = mag[(freqs>=50) & (freqs<=200)]
            eng = float(np.mean(eng_band)) if eng_band.size else 0.0

            # Music suppression heuristics
            # Tonalness via spectral flatness in 200–900Hz
            music_band = mag[(freqs>=200) & (freqs<=900)]
            flat = 1.0
            if music_band.size:
                gmean = np.exp(np.mean(np.log(np.maximum(music_band, 1e-12))))
                amean = np.mean(music_band)
                flat = float(gmean / max(1e-12, amean))

            # Smooth (attack/decay)
            dt = max(1e-4, time.time() - self._last_t)
            self._last_t = time.time()
            def smooth(prev, target, atk=0.02, dec=0.08):
                a_atk = dt / (atk + dt)
                a_dec = dt / (dec + dt)
                return prev + (a_atk if target>=prev else a_dec) * (target - prev)

            self._flux_env = smooth(self._flux_env, flux, 0.005, 0.060)
            self._road_env = smooth(self._road_env, road, 0.008, 0.050)
            self._eng_env  = smooth(self._eng_env,  eng,  0.040, 0.150)

            # Gate down when likely music (flatness low and flux low)
            with self._lock:
                P = dict(self._params)
            suppress = 1.0
            if flat < P["flat_thresh"] and self._flux_env < P["flux_gate"]:
                # 1 - music_suppress fraction blends toward strong suppression
                s = max(0.0, min(1.0, float(P["music_suppress"])) )
                suppress = 1.0 - (0.65 * s)  # between 1.0 and 0.35

            # Map to outputs 0..1
            # Normalize by configurable scale (depends on device); clamp
            def nz(x, s):
                y = x / s
                return 0.0 if y<0 else (1.0 if y>1.0 else float(y))

            imp = nz(self._flux_env * suppress, P["imp_norm"]) * P["impact_gain"]
            road_o = nz(self._road_env * suppress, P["road_norm"]) * P["road_gain"]
            eng_o  = nz(self._eng_env,  P["eng_norm"]) * P["engine_gain"]

            bodyR = max(road_o, eng_o * 0.5)
            bodyL = max(road_o*0.8, eng_o * 0.3)

            with self._lock:
                self._features = {"bodyL": bodyL, "bodyR": bodyR, "impact": imp}
        except Exception:
            pass

    def get(self) -> Dict[str, float]:
        with self._lock:
            return dict(self._features)

    def set_params(self, **kwargs):
        # Update tunables at runtime (thread-safe)
        with self._lock:
            for k, v in kwargs.items():
                if k in self._params:
                    try:
                        self._params[k] = float(v)
                    except Exception:
                        pass

    def switch_device(self, device_index: int | None):
        """Switch to a different input device (index from list_devices). None/-1 means Auto."""
        if sd is None:
            return False
        if isinstance(device_index, int) and device_index < 0:
            device_index = None
        try:
            if self._stream is not None:
                self._stream.stop(); self._stream.close()
                self._stream = None
            self._device = device_index
            # Recreate stream
            kwargs = { 'dtype':'float32', 'latency':'low', 'samplerate': self._sr, 'channels': 2 }
            if hasattr(sd, 'WasapiSettings'):
                ws = sd.WasapiSettings(loopback=True)
                self._stream = sd.InputStream(callback=self._cb, blocksize=self._bs, extra_settings=ws, device=self._device, **kwargs)
            else:
                self._stream = sd.InputStream(callback=self._cb, blocksize=self._bs, samplerate=self._sr, channels=2, dtype='float32', latency='low', device=self._device)
            self._stream.start()
            self.enabled = True
            return True
        except Exception:
            self.enabled = False
            self._stream = None
            return False
