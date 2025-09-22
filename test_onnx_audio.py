import numpy as np
import sounddevice as sd
from haptics.onnx_audio_event_detector import OnnxAudioEventDetector

detector = OnnxAudioEventDetector()

def audio_callback(indata, frames, time, status):
    # Convert stereo to mono and resample to 16kHz if needed
    mono = indata.mean(axis=1)
    # If your device is not 16kHz, resample here (not shown for brevity)
    if len(mono) >= 16000:
        chunk = mono[:16000]
        events = detector.predict(chunk)
        print("Top events:", events)

# Start stream (16kHz mono, 1 second buffer)
with sd.InputStream(channels=1, samplerate=16000, callback=audio_callback, blocksize=16000):
    print("Listening for sound events (Ctrl+C to stop)...")
    import time
    while True:
        time.sleep(1)