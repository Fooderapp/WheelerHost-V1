# Wheeler Host - Cross-Platform Audio Solutions

## Audio Level Issues Resolved ✅

### Problem Summary:
- **macOS**: No audio level display due to lack of system audio loopback
- **Windows**: "numpy not found" errors even with requirements.txt

### Solutions Implemented:

#### 1. **macOS Solution: Test Audio Generator**
- When real audio capture fails, Wheeler automatically falls back to a synthetic audio generator
- Generates realistic engine, impact, road, and music patterns for ONNX testing
- You'll see: `Audio: ONNX (Test Generator)` in the UI
- Console shows: `🎵 Test audio: impact for 0.3s` etc.

#### 2. **Windows Solution: Pure Python RMS + Numpy Fallback**
- RMS calculation now works without numpy dependency 
- If numpy is available, uses optimized version
- If numpy missing, falls back to pure Python calculation
- No more import errors

#### 3. **Cross-Platform Error Handling**
- Better error messages showing exactly what's working/failing
- Audio level meter shows meaningful status:
  - `Audio Level: 0.234` (working)
  - `Audio Level: no data` (probe not capturing)
  - `Audio Level: probe disabled` (sounddevice/loopback unavailable)

### Testing the Solutions:

#### On macOS:
1. Run Wheeler - you should see test audio generator activate automatically
2. Audio Level meter will show changing values as synthetic patterns play
3. ONNX Event labels will show detected events from test patterns
4. Console shows which patterns are playing: engine/impact/road/music/silence

#### On Windows:
1. Install requirements: `pip install -r requirements.txt`
2. Real audio capture via WASAPI loopback should work
3. If numpy issues persist, Wheeler will use pure Python fallbacks
4. Audio Level meter shows real game audio levels

### For Real Audio Capture on macOS:
To capture actual game audio on macOS (instead of test generator):
1. Install BlackHole virtual audio driver: `brew install blackhole-2ch`
2. Configure Audio MIDI Setup to route game audio through BlackHole
3. Select BlackHole device in Wheeler's audio device dropdown
4. Wheeler will then capture real game audio for ONNX processing

### ONNX Detection Priority (as requested):
1. **Impact** (highest priority) - Collisions, crashes, hits
2. **Road/Skid** - Tire friction, surface noise  
3. **Engine** - Motor sounds, RPM changes
4. **Music** (lowest priority) - Background music (often suppressed)

The system generates rich haptic patterns beyond simple rumble L/R, including multi-channel effects that vary by event type and intensity.