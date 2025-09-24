"""
ONNX-based real-time sound event detector for force feedback.
Uses a pre-trained YAMNet ONNX model for audio event classification.
"""
import os
import numpy as np
import onnxruntime as ort

class OnnxAudioEventDetector:
    def __init__(self, model_path=None):
        if model_path is None:
            model_path = os.path.join(os.path.dirname(__file__), '../models/yamnet.onnx')
        self.model_path = os.path.abspath(model_path)
        if not os.path.isfile(self.model_path):
            raise FileNotFoundError(f"ONNX model not found: {self.model_path}")
        self.session = ort.InferenceSession(self.model_path, providers=['CPUExecutionProvider'])
        # YAMNet expects mono 16kHz float32 waveform
        self.input_name = self.session.get_inputs()[0].name
        self.class_map = self._load_class_map()

    def _load_class_map(self):
        # YAMNet class map: expanded for racing/driving haptic feedback
        return {
            # Core vehicle/driving sounds
            8: 'Vehicle', 9: 'Car', 10: 'Engine', 11: 'Motor_vehicle',
            12: 'Motorcycle', 13: 'Bus', 336: 'Car_passing_by',
            
            # Tire/road sounds
            14: 'Skidding', 15: 'Tire_squeal', 19: 'Road_vehicle',
            423: 'Tire_on_gravel', 424: 'Road_surface',
            
            # Impact/crash sounds  
            16: 'Crash', 17: 'Bang', 18: 'Impact', 137: 'Slam',
            138: 'Thump', 139: 'Thud', 376: 'Breaking',
            
            # Environmental
            20: 'Wind', 21: 'Rustling', 22: 'Wind_noise',
            
            # Audio categories
            0: 'Speech', 7: 'Music', 137: 'Noise',
            
            # Additional vehicle-related
            425: 'Acceleration', 426: 'Deceleration', 427: 'Braking',
            428: 'Gear_shift', 429: 'Exhaust', 430: 'Turbo',
            
            # Surface types
            431: 'Gravel', 432: 'Dirt', 433: 'Asphalt', 434: 'Concrete',
            
            # Weather/conditions
            435: 'Rain_on_surface', 436: 'Wet_road', 437: 'Puddle_splash',
        }

    def predict(self, audio_mono_16k: np.ndarray):
        """
        Run ONNX model on a mono 16kHz float32 waveform.
        Returns: (scores, class_ids)
        """
        if audio_mono_16k.dtype != np.float32:
            audio_mono_16k = audio_mono_16k.astype(np.float32)
        # YAMNet expects 1D waveform, not batched
        outputs = self.session.run(None, {self.input_name: audio_mono_16k})
        # YAMNet ONNX output: [frames, classes]
        scores = outputs[0]  # [frames, classes]
        mean_scores = np.mean(scores, axis=0)  # [classes]
        top_ids = np.argsort(mean_scores)[::-1][:5]
        return [(self.class_map.get(i, str(i)), float(mean_scores[i])) for i in top_ids]
