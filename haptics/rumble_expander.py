import math

class RumbleParams:
    def __init__(self):
        self.smoothTau = 0.015
        self.lowTau = 0.090
        self.highTau = 0.015
        self.outAtkTau = 0.004
        self.outDecTau = 0.030

        self.impactDerivThresh = 5.0
        self.impactGain = 0.65
        self.impactDecayTau = 0.060
        self.impactRefractSec = 0.08

        self.absFreqHz = 12.0
        self.absDepth = 0.85
        self.absGateThresh = 0.10
        self.slipFreqHz = 10.0
        self.slipDepth = 0.75
        self.slipGateThresh = 0.08

        self.engineGain = 0.20
        self.engineTau = 0.200

        self.bodyLowGain = 0.9
        self.bodyHighGain = 0.35
        self.bodyImpactL = 0.45
        self.bodyImpactR = 0.65

        self.trigAbsGain = 1.00
        self.trigSlipGain = 0.90
        self.trigAssistLow = 0.12

        self.highBiasR = 0.70
        self.lowBiasL = 0.70

        self.globalGain = 1.0

def _alpha(dt, tau):
    if tau <= 0.0:
        return 1.0
    a = dt / (tau + dt)
    if a < 0.0: return 0.0
    if a > 1.0: return 1.0
    return a

def _clamp01(x):
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x

class RumbleExpander:
    def __init__(self, params=None):
        self.P = params or RumbleParams()
        self.reset()

    def reset(self):
        self.smL = self.smR = 0.0
        self.low = 0.0
        self.prevLow = 0.0
        self.high = 0.0
        self.highLP = 0.0
        self.hpEnv = 0.0
        self.eng = 0.0
        self.impactEnv = 0.0
        self.impactRefract = 0.0
        self.absPhase = 0.0
        self.slipPhase = 0.0
        self.o_bodyL = self.o_bodyR = self.o_trigL = self.o_trigR = 0.0

    def _smooth_out(self, prev, target, dt):
        aAtk = _alpha(dt, self.P.outAtkTau)
        aDec = _alpha(dt, self.P.outDecTau)
        if target >= prev:
            return prev + aAtk * (target - prev)
        return prev + aDec * (target - prev)

    def process(self, dt, rumbleL, rumbleR, lt=0.0, rt=0.0,
                speed01=0.0, brakePressed=False, throttlePressed=False, isOffroad=False):
        rumbleL = _clamp01(float(rumbleL))
        rumbleR = _clamp01(float(rumbleR))
        lt = _clamp01(float(lt))
        rt = _clamp01(float(rt))
        speed01 = _clamp01(float(speed01))

        # Pre smoothing
        aSm = _alpha(dt, self.P.smoothTau)
        self.smL += aSm * (rumbleL - self.smL)
        self.smR += aSm * (rumbleR - self.smR)

        # Band split
        mixLow = self.P.lowBiasL * self.smL + (1.0 - self.P.lowBiasL) * self.smR
        mixHigh = (1.0 - self.P.highBiasR) * self.smL + self.P.highBiasR * self.smR

        aLow = _alpha(dt, self.P.lowTau)
        aHigh = _alpha(dt, self.P.highTau)

        self.low += aLow * (mixLow - self.low)
        self.highLP += aHigh * (mixHigh - self.highLP)
        hpIn = mixHigh - self.highLP
        self.high += aHigh * (hpIn - self.high)

        # HP energy envelope
        hpAbs = abs(self.high)
        aHpE = _alpha(dt, 0.025)
        self.hpEnv += aHpE * (hpAbs - self.hpEnv)

        # Impacts on low band derivative
        dLow = (self.low - self.prevLow) / max(1e-4, dt)
        self.prevLow = self.low
        self.impactRefract = max(0.0, self.impactRefract - dt)
        if dLow > self.P.impactDerivThresh and self.impactRefract <= 0.0:
            self.impactEnv = min(1.0, self.impactEnv + self.P.impactGain)
            self.impactRefract = self.P.impactRefractSec
        # decay
        self.impactEnv += -_alpha(dt, self.P.impactDecayTau) * self.impactEnv

        # States
        braking = (lt > rt) or bool(brakePressed)
        accel = (rt > lt) or bool(throttlePressed)

        # ABS pulses
        absAmp = 0.0
        if braking and self.hpEnv > self.P.absGateThresh:
            self.absPhase += 2.0 * math.pi * self.P.absFreqHz * dt
            if self.absPhase > 2.0 * math.pi:
                self.absPhase -= 2.0 * math.pi
            s = 0.5 * (math.sin(self.absPhase) + 1.0)
            absAmp = s * self.P.absDepth * (self.hpEnv - self.P.absGateThresh) / (1.0 - self.P.absGateThresh)

        # Slip pulses
        slipAmp = 0.0
        if accel and self.hpEnv > self.P.slipGateThresh:
            self.slipPhase += 2.0 * math.pi * self.P.slipFreqHz * dt
            if self.slipPhase > 2.0 * math.pi:
                self.slipPhase -= 2.0 * math.pi
            s = 0.5 * (math.sin(self.slipPhase) + 1.0)
            slipAmp = s * self.P.slipDepth * (self.hpEnv - self.P.slipGateThresh) / (1.0 - self.P.slipGateThresh)

        # Engine
        aEng = _alpha(dt, self.P.engineTau)
        self.eng += aEng * (self.hpEnv - self.eng)

        # Mix
        bodyL = 0.0; bodyR = 0.0; trigL = 0.0; trigR = 0.0
        bodyL += self.P.bodyLowGain * max(0.0, self.low)
        bodyR += self.P.bodyLowGain * max(0.0, self.low)
        bodyR += self.P.bodyHighGain * self.hpEnv
        bodyL += self.P.bodyHighGain * 0.25 * self.hpEnv
        bodyL += self.P.bodyImpactL * self.impactEnv
        bodyR += self.P.bodyImpactR * self.impactEnv
        bodyR += self.P.engineGain * self.eng

        trigL += self.P.trigAbsGain * absAmp
        trigR += self.P.trigSlipGain * slipAmp
        if braking:
            trigL += self.P.trigAssistLow * self.low
        if accel:
            trigR += self.P.trigAssistLow * self.low

        if isOffroad:
            bodyR += 0.08 * self.hpEnv
            trigR += 0.05 * self.hpEnv

        # Smooth + clamp
        y_bodyL = self._smooth_out(self.o_bodyL, bodyL, dt)
        y_bodyR = self._smooth_out(self.o_bodyR, bodyR, dt)
        y_trigL = self._smooth_out(self.o_trigL, trigL, dt)
        y_trigR = self._smooth_out(self.o_trigR, trigR, dt)
        self.o_bodyL, self.o_bodyR, self.o_trigL, self.o_trigR = y_bodyL, y_bodyR, y_trigL, y_trigR

        g = self.P.globalGain
        y_bodyL = _clamp01(g * y_bodyL)
        y_bodyR = _clamp01(g * y_bodyR)
        y_trigL = _clamp01(g * y_trigL)
        y_trigR = _clamp01(g * y_trigR)

        return {
            "bodyL": y_bodyL,
            "bodyR": y_bodyR,
            "trigL": y_trigL,
            "trigR": y_trigR,
            "impact": _clamp01(self.impactEnv * 1.0),
        }

