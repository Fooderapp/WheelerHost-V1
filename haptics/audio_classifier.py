"""
Real-time audio classification for force feedback generation.
Classifies incoming audio into different categories and generates appropriate FFB.
"""
import threading
import time
from typing import Dict, Optional, Callable

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    # Create dummy numpy for graceful fallback
    class DummyNumPy:
        def array(self, *args, **kwargs): return []
        def mean(self, *args, **kwargs): return 0.0
        def sum(self, *args, **kwargs): return 0.0
        def max(self, *args, **kwargs): return 0.0
        def exp(self, *args, **kwargs): return 1.0
        def log(self, *args, **kwargs): return 0.0
        def clip(self, *args, **kwargs): return 0.0
        def maximum(self, *args, **kwargs): return 0.0
        def corrcoef(self, *args, **kwargs): return [[1.0, 1.0], [1.0, 1.0]]
        def isnan(self, *args, **kwargs): return False
    np = DummyNumPy()

class AudioClassifier:
    """
    Lightweight real-time audio classifier for racing game FFB.
    Analyzes frequency spectrum and temporal patterns to classify:
    - Music (steady tonal content)
    - Road/Surface (broadband noise, tire skid)
    - Engine (low frequency harmonics)
    - Impact/Crash (sudden spectral changes)
    
    Gracefully handles missing numpy dependency.
    """
    
    def __init__(self, samplerate: int = 48000):
        self.sr = samplerate
        self._lock = threading.Lock()
        self.available = HAS_NUMPY
        
        if not HAS_NUMPY:
            # Fallback mode - return simple static values
            self._features = {'music': 0.0, 'road': 0.5, 'engine': 0.3, 'impact': 0.0}
            self._gains = {'music': 0.1, 'road': 1.0, 'engine': 0.8, 'impact': 1.5}
            return
        
        # Classification state
        self._prev_spectrum = None
        self._spectrum_history = []
        self._history_size = 5
        
        # Feature accumulators (smoothed)
        self._features = {
            'music': 0.0,
            'road': 0.0, 
            'engine': 0.0,
            'impact': 0.0
        }
        
        # Tunable parameters (improved for better identification)
        self._params = {
            # Music detection (harmonic content) - tighter thresholds
            'music_harmonic_thresh': 0.4,  # Higher threshold for more selective music detection
            'music_stability_thresh': 0.85,  # Require more stability
            
            # Road/surface (broadband noise) - better sensitivity
            'road_freq_min': 200,    # Focus on tire noise range
            'road_freq_max': 3000,   # Extended range for different surfaces
            'road_broadband_thresh': 0.15,  # More sensitive to broadband content
            
            # Engine (low frequency harmonics) - more specific
            'engine_freq_min': 40,   # Lower for deep engine sounds
            'engine_freq_max': 250,  # Focused on engine fundamentals
            'engine_harmonic_thresh': 0.35,  # Higher threshold for better detection
            
            # Impact (sudden spectral flux) - reduced sensitivity for less ticking
            'impact_flux_thresh': 0.08,  # Higher threshold to reduce false positives
            'impact_decay_rate': 0.92,   # Faster decay to reduce sustained ticking
            
            # Smoothing (improved to reduce ticking feel)
            'smooth_attack': 0.05,   # Slower attack for smoother response
            'smooth_decay': 0.15     # Faster decay to prevent sticking
        }
        
        # Category weights/gains (controllable via sliders) - improved defaults
        self._gains = {
            'music': 0.05,     # Very low music FFB to avoid interference
            'road': 1.0,       # Full road effects
            'engine': 0.6,     # Moderate engine vibration  
            'impact': 1.2      # Emphasized but not overwhelming impacts
        }
        
    def set_gain(self, category: str, gain: float):
        """Set gain/intensity for a specific FFB category."""
        with self._lock:
            if category in self._gains:
                self._gains[category] = max(0.0, min(2.0, gain))
    
    def get_gains(self) -> Dict[str, float]:
        """Get current category gains."""
        with self._lock:
            return self._gains.copy()
    
    def classify_spectrum(self, spectrum, freqs) -> Dict[str, float]:
        """
        Classify a frequency spectrum into different categories.
        Returns classification confidence for each category (0-1).
        """
        if not self.available:
            # Fallback mode - return static values
            return self._features.copy()
            
        with self._lock:
            # Music detection - look for harmonic structure and stability
            music_score = self._detect_music(spectrum, freqs)
            
            # Road/surface - broadband noise characteristics
            road_score = self._detect_road(spectrum, freqs)
            
            # Engine - low frequency harmonic content
            engine_score = self._detect_engine(spectrum, freqs)
            
            # Impact - sudden spectral changes
            impact_score = self._detect_impact(spectrum, freqs)
            
            # Smooth the features (improved smoothing to reduce ticking)
            dt = 1.0 / 60.0  # Assume ~60fps updates, but smoother
            for category, new_val in [('music', music_score), ('road', road_score), 
                                    ('engine', engine_score), ('impact', impact_score)]:
                old_val = self._features[category]
                # Use different smoothing for impact to reduce ticking
                if category == 'impact':
                    # Impact gets special treatment - quick attack, fast decay
                    alpha = 0.2 if new_val > old_val else 0.4
                    # Apply decay even when no new impact detected
                    if new_val < 0.01:
                        new_val = old_val * self._params['impact_decay_rate']
                else:
                    alpha = self._params['smooth_attack'] if new_val > old_val else self._params['smooth_decay']
                
                self._features[category] = old_val + alpha * (new_val - old_val)
                # Ensure values stay in valid range
                self._features[category] = max(0.0, min(1.0, self._features[category]))
            
            # Update history
            self._spectrum_history.append(spectrum.copy())
            if len(self._spectrum_history) > self._history_size:
                self._spectrum_history.pop(0)
            
            self._prev_spectrum = spectrum.copy()
            
            return self._features.copy()
    
    def _detect_music(self, spectrum, freqs) -> float:
        """Detect musical content via harmonic analysis and stability."""
        if not self.available:
            return 0.1
        # Harmonic detection in musical range (200-4000 Hz)
        music_mask = (freqs >= 200) & (freqs <= 4000)
        music_spectrum = spectrum[music_mask]
        
        if len(music_spectrum) < 10:
            return 0.0
        
        # Spectral centroid and spread
        music_freqs = freqs[music_mask]
        total_energy = np.sum(music_spectrum)
        if total_energy < 1e-6:
            return 0.0
        
        # Look for peaks (harmonic content)
        peaks = self._find_spectral_peaks(music_spectrum)
        harmonic_ratio = len(peaks) / max(1, len(music_spectrum) // 10)
        
        # Stability check - compare with recent history
        stability = 0.0
        if len(self._spectrum_history) >= 3:
            recent_spectra = self._spectrum_history[-3:]
            stability = self._calculate_stability(music_spectrum, recent_spectra, music_mask)
        
        # Combine harmonic and stability features
        music_score = 0.0
        if harmonic_ratio > self._params['music_harmonic_thresh']:
            music_score += 0.5
        if stability > self._params['music_stability_thresh']:
            music_score += 0.5
            
        return min(1.0, music_score)
    
    def _detect_road(self, spectrum, freqs) -> float:
        """Detect road/surface noise - broadband characteristics."""
        if not self.available:
            return 0.5
        road_mask = (freqs >= self._params['road_freq_min']) & (freqs <= self._params['road_freq_max'])
        road_spectrum = spectrum[road_mask]
        
        if len(road_spectrum) < 5:
            return 0.0
        
        # Measure broadband-ness (inverse of tonality)
        if len(road_spectrum) > 0:
            # Spectral flatness (geometric mean / arithmetic mean)
            gmean = np.exp(np.mean(np.log(np.maximum(road_spectrum, 1e-12))))
            amean = np.mean(road_spectrum)
            flatness = gmean / max(amean, 1e-12)
            
            # Higher flatness = more noise-like = more road-like
            road_score = min(1.0, flatness / self._params['road_broadband_thresh'])
        else:
            road_score = 0.0
            
        return road_score
    
    def _detect_engine(self, spectrum, freqs) -> float:
        """Detect engine sounds - low frequency harmonic content."""
        if not self.available:
            return 0.3
        engine_mask = (freqs >= self._params['engine_freq_min']) & (freqs <= self._params['engine_freq_max'])
        engine_spectrum = spectrum[engine_mask]
        
        if len(engine_spectrum) < 5:
            return 0.0
        
        # Look for harmonic structure in engine frequency range
        peaks = self._find_spectral_peaks(engine_spectrum)
        peak_ratio = len(peaks) / max(1, len(engine_spectrum) // 5)
        
        # Check for typical engine harmonics
        engine_score = 0.0
        if peak_ratio > self._params['engine_harmonic_thresh']:
            # Additional check: look for fundamental around 50-150 Hz
            fund_mask = (freqs >= 50) & (freqs <= 150)
            if np.any(fund_mask):
                fund_energy = np.max(spectrum[fund_mask])
                total_energy = np.sum(engine_spectrum)
                if fund_energy > 0.1 * total_energy:
                    engine_score = min(1.0, peak_ratio)
        
        return engine_score
    
    def _detect_impact(self, spectrum, freqs) -> float:
        """Detect impact/crash sounds - sudden spectral changes."""
        if not self.available:
            return 0.0
        if self._prev_spectrum is None:
            return 0.0
        
        # Calculate spectral flux (difference between consecutive frames)
        if len(spectrum) == len(self._prev_spectrum):
            diff = spectrum - self._prev_spectrum
            # Only positive changes (new energy)
            positive_diff = np.maximum(diff, 0.0)
            flux = np.sum(positive_diff) / len(spectrum)
            
            # Normalize and threshold
            impact_score = min(1.0, flux / self._params['impact_flux_thresh'])
        else:
            impact_score = 0.0
        
        return impact_score
    
    def _find_spectral_peaks(self, spectrum, prominence: float = 0.1) -> list:
        """Find peaks in spectrum (simple peak detection)."""
        if not self.available or not spectrum:
            return []
        if len(spectrum) < 3:
            return []
        
        peaks = []
        threshold = np.max(spectrum) * prominence
        
        for i in range(1, len(spectrum) - 1):
            if (spectrum[i] > spectrum[i-1] and 
                spectrum[i] > spectrum[i+1] and 
                spectrum[i] > threshold):
                peaks.append(i)
        
        return peaks
    
    def _calculate_stability(self, current, history: list, mask) -> float:
        """Calculate spectral stability over time."""
        if not self.available or len(history) == 0:
            return 0.0
        
        correlations = []
        for past_spectrum in history:
            if len(past_spectrum) == len(current):
                past_masked = past_spectrum[mask] if len(past_spectrum) > len(mask) else past_spectrum
                if len(past_masked) == len(current):
                    corr = np.corrcoef(current, past_masked)[0, 1]
                    if not np.isnan(corr):
                        correlations.append(corr)
        
        return np.mean(correlations) if correlations else 0.0
    
    def generate_ffb(self, categories: Dict[str, float]) -> tuple[float, float]:
        """
        Generate force feedback (left, right) based on classified audio categories.
        Returns (left_intensity, right_intensity) in range [0, 1].
        Improved to reduce ticking and provide smoother response.
        """
        with self._lock:
            left_ffb = 0.0
            right_ffb = 0.0
            
            # Road effects - stereo broadband rumble (primary feel)
            road_intensity = categories.get('road', 0.0) * self._gains['road']
            left_ffb += road_intensity * 0.9   # Strong road feel
            right_ffb += road_intensity * 0.9
            
            # Engine - low frequency rumble, balanced stereo
            engine_intensity = categories.get('engine', 0.0) * self._gains['engine']
            left_ffb += engine_intensity * 0.7
            right_ffb += engine_intensity * 0.7
            
            # Impact - sharp but controlled burst (reduced ticking)
            impact_intensity = categories.get('impact', 0.0) * self._gains['impact']
            # Apply additional smoothing to impact to prevent ticking
            smoothed_impact = min(impact_intensity, 0.8)  # Cap impact intensity
            left_ffb += smoothed_impact * 0.8
            right_ffb += smoothed_impact * 0.6
            
            # Music - very minimal, just subtle background
            music_intensity = categories.get('music', 0.0) * self._gains['music']
            left_ffb += music_intensity * 0.1
            right_ffb += music_intensity * 0.1
            
            # Apply gentle saturation curve to prevent harsh clipping
            def soft_saturate(x):
                if x <= 0.7:
                    return x
                else:
                    # Soft compression above 70%
                    excess = x - 0.7
                    return 0.7 + excess * 0.5
            
            left_ffb = soft_saturate(left_ffb)
            right_ffb = soft_saturate(right_ffb)
            
            # Final clamping
            left_ffb = max(0.0, min(1.0, left_ffb))
            right_ffb = max(0.0, min(1.0, right_ffb))
            
            return left_ffb, right_ffb