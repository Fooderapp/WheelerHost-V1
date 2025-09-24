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
        # YAMNet class map: 521 classes, can be found in yamnet_class_map.csv
        # For demo, use a minimal hardcoded map for key FFB categories
        return {
            0: 'Speech',
            7: 'Music',
            8: 'Vehicle',
            9: 'Car',
            10: 'Engine',
            14: 'Skidding',
            15: 'Tire squeal',
            16: 'Crash',
            17: 'Bang',
            18: 'Impact',
            19: 'Road',
            20: 'Wind',
            # ... (expand as needed)
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
