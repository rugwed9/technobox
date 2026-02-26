import numpy as np
import scipy.signal as sig


class MoogLadderFilter:
    """4-pole (24dB/oct) resonant lowpass. Self-oscillates at high resonance."""

    def __init__(self, sr=48000):
        self.sr = sr
        self.s = np.zeros(4)
        self.cutoff = 1000.0
        self.resonance = 0.0

    def process(self, x, cutoff=None, resonance=None):
        n = len(x)
        out = np.zeros(n, dtype=np.float64)

        if cutoff is None:
            cutoff_arr = np.full(n, self.cutoff)
        elif isinstance(cutoff, (int, float)):
            cutoff_arr = np.full(n, float(cutoff))
        else:
            cutoff_arr = cutoff

        if resonance is None:
            res_arr = np.full(n, self.resonance)
        elif isinstance(resonance, (int, float)):
            res_arr = np.full(n, float(resonance))
        else:
            res_arr = resonance

        s0, s1, s2, s3 = self.s

        for i in range(n):
            fc = cutoff_arr[i] / self.sr
            fc = min(fc, 0.45)
            g = np.tan(np.pi * fc)
            G = g / (1.0 + g)

            res = res_arr[i]
            feedback = res * s3
            u = (x[i] - feedback)

            v = np.tanh(u)
            s0 += G * (v - s0)
            s1 += G * (np.tanh(s0) - s1)
            s2 += G * (np.tanh(s1) - s2)
            s3 += G * (np.tanh(s2) - s3)

            out[i] = s3

        self.s = np.array([s0, s1, s2, s3])
        return out

    def reset(self):
        self.s = np.zeros(4)


class StateVariableFilter:
    """Chamberlin SVF - simultaneous LP/BP/HP outputs."""

    def __init__(self, sr=48000):
        self.sr = sr
        self.lp = 0.0
        self.bp = 0.0

    def process(self, x, cutoff, resonance=0.5, mode='low'):
        n = len(x)
        out = np.zeros(n, dtype=np.float64)
        lp, bp = self.lp, self.bp

        if isinstance(cutoff, (int, float)):
            cutoff = np.full(n, float(cutoff))
        if isinstance(resonance, (int, float)):
            resonance = np.full(n, float(resonance))

        for i in range(n):
            f = 2.0 * np.sin(np.pi * min(cutoff[i], self.sr * 0.45) / self.sr)
            q = max(1.0 - resonance[i], 0.01)

            hp = x[i] - lp - q * bp
            bp += f * hp
            lp += f * bp

            if mode == 'low':
                out[i] = lp
            elif mode == 'band':
                out[i] = bp
            elif mode == 'high':
                out[i] = hp
            elif mode == 'notch':
                out[i] = hp + lp

        self.lp, self.bp = lp, bp
        return out

    def reset(self):
        self.lp = 0.0
        self.bp = 0.0


class BiquadChain:
    """scipy.signal wrapper for static filters. Very fast (vectorized C)."""

    def __init__(self, sr=48000):
        self.sr = sr
        self.sos = None
        self.zi = None

    def configure(self, cutoff, filter_type='low', order=4, resonance=0.707):
        try:
            self.sos = sig.butter(order, cutoff, btype=filter_type, fs=self.sr, output='sos')
            self.zi = sig.sosfilt_zi(self.sos) * 0.0
        except Exception:
            self.sos = None
            self.zi = None

    def process(self, x):
        if self.sos is None:
            return x
        y, self.zi = sig.sosfilt(self.sos, x, zi=self.zi)
        return y

    def reset(self):
        if self.sos is not None:
            self.zi = sig.sosfilt_zi(self.sos) * 0.0
