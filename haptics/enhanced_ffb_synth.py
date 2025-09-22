"""
Enhanced FFB synthesis with audio classification.
Integrates the AudioClassifier with existing FFB generation.
"""
import time
from typing import Dict, Optional
from .ffb_synth import FfbSynthEngine, FfbSynthParams
from .audio_classifier import AudioClassifier

class EnhancedFfbSynth:
    """
    Enhanced FFB synthesizer that combines:
    1. Physics-based steering feel (spring/damper)
    2. Audio-classified force feedback (music, road, engine, impact)
    3. Per-category intensity controls
    """
    
    def __init__(self):
        # Physics-based FFB (existing)
        self.physics_ffb = FfbSynthEngine()
        
        # Audio-based FFB (new)
        self.audio_classifier = AudioClassifier()
        
        # Mixing parameters
        self.mix_params = {
            'physics_weight': 0.7,    # Base steering feel
            'audio_weight': 0.3,      # Audio enhancement
            'total_gain': 1.0,        # Master volume
        }
        
        # Per-category gains (exposed to UI)
        self.category_gains = {
            'music': 0.1,
            'road': 1.0,
            'engine': 0.8,
            'impact': 1.5
        }
        
        # Update classifier gains
        for category, gain in self.category_gains.items():
            self.audio_classifier.set_gain(category, gain)
    
    def set_category_gain(self, category: str, gain: float):
        """Set FFB intensity for a specific audio category (0.0 - 2.0)."""
        gain = max(0.0, min(2.0, gain))
        self.category_gains[category] = gain
        self.audio_classifier.set_gain(category, gain)
    
    def get_category_gains(self) -> Dict[str, float]:
        """Get current category gain settings."""
        return self.category_gains.copy()
    
    def set_mix_params(self, physics_weight: float = None, audio_weight: float = None, total_gain: float = None):
        """Adjust mixing between physics and audio FFB."""
        if physics_weight is not None:
            self.mix_params['physics_weight'] = max(0.0, min(1.0, physics_weight))
        if audio_weight is not None:
            self.mix_params['audio_weight'] = max(0.0, min(1.0, audio_weight))
        if total_gain is not None:
            self.mix_params['total_gain'] = max(0.0, min(2.0, total_gain))
    
    def process_audio_spectrum(self, spectrum, freqs):
        """Process audio spectrum for classification."""
        return self.audio_classifier.classify_spectrum(spectrum, freqs)
    
    def generate_ffb(self, 
                    dt: float,
                    steering_x: float, 
                    steering_dx: float,
                    throttle: float, 
                    brake: float, 
                    lat_g: float,
                    audio_spectrum=None,
                    audio_freqs=None) -> tuple[float, float]:
        """
        Generate combined FFB from physics and audio sources.
        
        Args:
            dt: Time delta
            steering_x: Steering position [-1, 1]
            steering_dx: Steering velocity
            throttle: Throttle input [0, 1]
            brake: Brake input [0, 1]
            lat_g: Lateral G-force
            audio_spectrum: FFT magnitude spectrum (optional)
            audio_freqs: FFT frequency bins (optional)
            
        Returns:
            (left_ffb, right_ffb) in range [0, 1]
        """
        
        # 1. Physics-based FFB (existing steering feel)
        physics_left, physics_right = self.physics_ffb.process(
            dt, steering_x, steering_dx, throttle, brake, lat_g
        )
        
        # 2. Audio-based FFB
        audio_left, audio_right = 0.0, 0.0
        if audio_spectrum is not None and audio_freqs is not None:
            # Classify audio
            try:
                categories = self.audio_classifier.classify_spectrum(audio_spectrum, audio_freqs)
                audio_left, audio_right = self.audio_classifier.generate_ffb(categories)
            except Exception:
                # Fallback if classification fails
                audio_left, audio_right = 0.0, 0.0
        
        # 3. Mix physics and audio FFB
        physics_weight = self.mix_params['physics_weight']
        audio_weight = self.mix_params['audio_weight']
        total_gain = self.mix_params['total_gain']
        
        # Weighted combination
        final_left = (physics_left * physics_weight + audio_left * audio_weight) * total_gain
        final_right = (physics_right * physics_weight + audio_right * audio_weight) * total_gain
        
        # Clamp to valid range
        final_left = max(0.0, min(1.0, final_left))
        final_right = max(0.0, min(1.0, final_right))
        
        return final_left, final_right
    
    def get_classification_debug_info(self) -> Dict[str, float]:
        """Get current audio classification values for debugging/UI."""
        return self.audio_classifier._features.copy()


class AudioFfbProcessor:
    """
    Standalone processor for audio-only FFB generation.
    Can be used when only audio effects are desired.
    """
    
    def __init__(self):
        self.classifier = AudioClassifier()
        self.last_update = time.time()
        
        # Timing control
        self.update_rate_hz = 60.0  # Target update rate
        self.min_update_interval = 1.0 / self.update_rate_hz
        
    def process_audio_frame(self, spectrum, freqs) -> tuple[float, float]:
        """
        Process a single audio frame and generate FFB.
        
        Args:
            spectrum: FFT magnitude spectrum
            freqs: FFT frequency bins
            
        Returns:
            (left_ffb, right_ffb) in range [0, 1]
        """
        current_time = time.time()
        
        # Rate limiting
        if current_time - self.last_update < self.min_update_interval:
            return 0.0, 0.0
        
        self.last_update = current_time
        
        try:
            # Classify audio
            categories = self.classifier.classify_spectrum(spectrum, freqs)
            
            # Generate FFB
            left_ffb, right_ffb = self.classifier.generate_ffb(categories)
            
            return left_ffb, right_ffb
            
        except Exception:
            return 0.0, 0.0
    
    def set_category_gain(self, category: str, gain: float):
        """Set gain for a specific category."""
        self.classifier.set_gain(category, gain)
    
    def get_category_gains(self) -> Dict[str, float]:
        """Get current category gains."""
        return self.classifier.get_gains()