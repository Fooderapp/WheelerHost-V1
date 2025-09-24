"""
TestAudioGenerator: Generate synthetic audio for testing ONNX detection when real audio capture isn't available.

This is useful on macOS where system audio loopback requires additional software,
or for testing specific audio patterns.
"""
import math
import time
import threading
from typing import Optional, List
import random

try:
    import numpy as np
except ImportError:
    np = None


class TestAudioGenerator:
    """Generate synthetic audio patterns for testing ONNX detection."""
    
    def __init__(self, samplerate: int = 16000):
        self.sr = samplerate
        self.buffer_size = samplerate  # 1 second
        self.enabled = True
        
        # Create buffer (with or without numpy)
        if np is not None:
            self.buffer = np.zeros(self.buffer_size, dtype=np.float32)
        else:
            self.buffer = [0.0] * self.buffer_size
        
        self.pos = 0
        self.lock = threading.Lock()
        self.running = False
        self.thread = None
        
        # Test patterns
        self.patterns = {
            'engine': {'freq': 120, 'amplitude': 0.3, 'duration': 2.0},
            'impact': {'freq': 800, 'amplitude': 0.8, 'duration': 0.2},
            'road': {'freq': 300, 'amplitude': 0.4, 'duration': 1.5},
            'music': {'freq': 440, 'amplitude': 0.2, 'duration': 3.0},
            'silence': {'freq': 0, 'amplitude': 0.0, 'duration': 1.0}
        }
        
        self.current_pattern = 'silence'
        self.pattern_start_time = time.time()
        self.pattern_duration = 1.0
    
    def start(self):
        """Start generating test audio patterns."""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._generate_loop, daemon=True)
        self.thread.start()
        print("✓ Test audio generator started")
    
    def stop(self):
        """Stop generating audio."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=1.0)
        print("✓ Test audio generator stopped")
    
    def _generate_loop(self):
        """Main generation loop."""
        last_time = time.time()
        samples_per_update = self.sr // 50  # ~20ms updates
        
        while self.running:
            current_time = time.time()
            dt = current_time - last_time
            
            if dt >= 0.02:  # 20ms updates
                self._generate_samples(samples_per_update)
                self._update_pattern()
                last_time = current_time
            
            time.sleep(0.01)
    
    def _update_pattern(self):
        """Switch between different test patterns."""
        elapsed = time.time() - self.pattern_start_time
        
        if elapsed >= self.pattern_duration:
            # Choose next pattern
            pattern_names = list(self.patterns.keys())
            weights = [0.1, 0.3, 0.2, 0.1, 0.3]  # Favor impact and road, some silence
            self.current_pattern = random.choices(pattern_names, weights=weights)[0]
            
            self.pattern_start_time = time.time()
            pattern_info = self.patterns[self.current_pattern]
            self.pattern_duration = pattern_info['duration'] + random.uniform(-0.5, 0.5)
            
            print(f"🎵 Test audio: {self.current_pattern} for {self.pattern_duration:.1f}s")
    
    def _generate_samples(self, num_samples: int):
        """Generate audio samples for current pattern."""
        pattern_info = self.patterns[self.current_pattern]
        freq = pattern_info['freq']
        amp = pattern_info['amplitude']
        
        with self.lock:
            for i in range(num_samples):
                if freq > 0:
                    # Generate sine wave with some noise
                    t = (self.pos + i) / self.sr
                    sample = amp * (
                        math.sin(2 * math.pi * freq * t) +
                        0.2 * math.sin(2 * math.pi * freq * 2.1 * t) +  # Harmonic
                        0.1 * random.uniform(-1, 1)  # Noise
                    )
                else:
                    sample = 0.0
                
                # Write to buffer
                buf_idx = (self.pos + i) % self.buffer_size
                if np is not None:
                    self.buffer[buf_idx] = sample
                else:
                    self.buffer[buf_idx] = sample
            
            self.pos = (self.pos + num_samples) % self.buffer_size
    
    def get_onnx_audio(self, length: int = 16000) -> Optional[List[float]]:
        """Get recent audio samples for ONNX (same interface as AudioProbe)."""
        if not self.enabled:
            return None
        
        if length > self.buffer_size:
            length = self.buffer_size
        
        with self.lock:
            if np is not None:
                # Numpy version
                if self.pos >= length:
                    return self.buffer[self.pos-length:self.pos].tolist()
                else:
                    part1 = self.buffer[self.pos-length:].tolist()
                    part2 = self.buffer[:self.pos].tolist()
                    return part1 + part2
            else:
                # Pure Python version
                result = []
                for i in range(length):
                    idx = (self.pos - length + i) % self.buffer_size
                    result.append(self.buffer[idx])
                return result
    
    def close(self):
        """Clean up resources."""
        self.stop()


# Test the generator
if __name__ == "__main__":
    gen = TestAudioGenerator()
    gen.start()
    
    try:
        for _ in range(10):
            audio = gen.get_onnx_audio(1000)
            if audio:
                rms = (sum(x*x for x in audio) / len(audio)) ** 0.5
                print(f"Generated {len(audio)} samples, RMS: {rms:.3f}")
            time.sleep(1)
    finally:
        gen.stop()