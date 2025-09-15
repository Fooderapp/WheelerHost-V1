import math

class FfbSynthParams:
    def __init__(self):
        # Spring stiffness at standstill and additional with speed/throttle
        self.k_base = 0.8     # N·m per unit steer
        self.k_thr  = 0.6     # extra stiffness when accelerating (proxy for speed)
        # Damper (against angular velocity)
        self.c_damp = 0.35    # N·m per unit/sec
        # Coulomb friction around center (adds resistance near zero)
        self.mu_fric = 0.18   # N·m
        # Output scaling to 0..1 rumble channels
        self.out_gain = 0.9
        # Soft clip to avoid sudden saturations
        self.soft_clip = 0.8

class FfbSynthEngine:
    """Simple spring+damper+friction synthesizer.

    Inputs:
      - x: steering position in [-1,1]
      - dx: time derivative of x (1/sec)
      - throttle, brake: 0..1
      - latG: lateral acceleration (unused here, but available for future heuristics)

    Output:
      - L, R rumble in 0..1 (balanced by torque sign)
    """
    def __init__(self, params: FfbSynthParams | None = None):
        self.P = params or FfbSynthParams()

    def process(self, dt: float, x: float, dx: float, throttle: float, brake: float, latG: float):
        x = max(-1.0, min(1.0, float(x)))
        throttle = max(0.0, min(1.0, float(throttle)))
        brake = max(0.0, min(1.0, float(brake)))
        dt = max(1e-4, min(0.050, float(dt)))

        # Stiffness scales with acceleration proxy (throttle). Could be replaced by true speed.
        K = self.P.k_base + self.P.k_thr * throttle
        C = self.P.c_damp
        mu = self.P.mu_fric

        # Spring + damper + coulomb friction
        torque = -K * x - C * dx
        if abs(x) > 1e-4:
            torque += -mu * (1.0 if x > 0.0 else -1.0)

        # Map torque to rumble
        # Use magnitude for overall strength; bias channels by sign so it "leans".
        mag = abs(torque)
        # soft clip
        sc = self.P.soft_clip
        if sc > 0.0:
            mag = (mag / (mag + sc)) if mag >= 0.0 else -(mag / (abs(mag) + sc))
            mag = abs(mag)
        y = max(0.0, min(1.0, mag * self.P.out_gain))

        if torque >= 0:
            L = y * 0.65
            R = y
        else:
            L = y
            R = y * 0.65
        return float(max(0.0, min(1.0, L))), float(max(0.0, min(1.0, R)))

