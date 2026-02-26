import numpy as np


class SineOscillator:
    def __init__(self, sr=48000):
        self.sr = sr
        self.phase = 0.0

    def render(self, num_samples, freq):
        if isinstance(freq, (int, float)):
            dt = freq / self.sr
            phases = (self.phase + np.arange(num_samples) * dt) % 1.0
            self.phase = (self.phase + num_samples * dt) % 1.0
            return np.sin(2 * np.pi * phases)
        else:
            out = np.zeros(num_samples, dtype=np.float64)
            for i in range(num_samples):
                out[i] = np.sin(2 * np.pi * self.phase)
                self.phase = (self.phase + freq[i] / self.sr) % 1.0
            return out


class SawOscillator:
    def __init__(self, sr=48000):
        self.sr = sr
        self.phase = 0.0

    def _polyblep(self, t, dt):
        if t < dt:
            t /= dt
            return t + t - t * t - 1.0
        elif t > 1.0 - dt:
            t = (t - 1.0) / dt
            return t * t + t + t + 1.0
        return 0.0

    def render(self, num_samples, freq):
        if isinstance(freq, (int, float)):
            dt = freq / self.sr
            phases = (self.phase + np.arange(num_samples) * dt) % 1.0
            self.phase = (self.phase + num_samples * dt) % 1.0
            out = 2.0 * phases - 1.0
            # Apply polyblep at wrap points
            diffs = np.diff(phases, prepend=phases[0] - dt)
            wraps = diffs < -0.5
            for idx in np.where(wraps)[0]:
                t = phases[idx]
                out[idx] -= self._polyblep(t, dt)
                if idx > 0:
                    out[idx - 1] -= self._polyblep(phases[idx - 1], dt)
            return out
        else:
            out = np.zeros(num_samples, dtype=np.float64)
            for i in range(num_samples):
                dt = freq[i] / self.sr
                out[i] = 2.0 * self.phase - 1.0
                out[i] -= self._polyblep(self.phase, dt)
                self.phase = (self.phase + dt) % 1.0
            return out


class SquareOscillator:
    def __init__(self, sr=48000):
        self.sr = sr
        self.phase = 0.0

    def _polyblep(self, t, dt):
        if t < dt:
            t /= dt
            return t + t - t * t - 1.0
        elif t > 1.0 - dt:
            t = (t - 1.0) / dt
            return t * t + t + t + 1.0
        return 0.0

    def render(self, num_samples, freq, pw=0.5):
        if isinstance(freq, (int, float)):
            dt = freq / self.sr
            phases = (self.phase + np.arange(num_samples) * dt) % 1.0
            self.phase = (self.phase + num_samples * dt) % 1.0
            out = np.where(phases < pw, 1.0, -1.0)
            return out
        else:
            out = np.zeros(num_samples, dtype=np.float64)
            for i in range(num_samples):
                dt = freq[i] / self.sr
                out[i] = 1.0 if self.phase < pw else -1.0
                out[i] += self._polyblep(self.phase, dt)
                out[i] -= self._polyblep((self.phase + 1.0 - pw) % 1.0, dt)
                self.phase = (self.phase + dt) % 1.0
            return out


class TriangleOscillator:
    def __init__(self, sr=48000):
        self.sr = sr
        self.phase = 0.0

    def render(self, num_samples, freq):
        if isinstance(freq, (int, float)):
            dt = freq / self.sr
            phases = (self.phase + np.arange(num_samples) * dt) % 1.0
            self.phase = (self.phase + num_samples * dt) % 1.0
            return 2.0 * np.abs(2.0 * phases - 1.0) - 1.0
        else:
            out = np.zeros(num_samples, dtype=np.float64)
            for i in range(num_samples):
                out[i] = 2.0 * abs(2.0 * self.phase - 1.0) - 1.0
                self.phase = (self.phase + freq[i] / self.sr) % 1.0
            return out


class NoiseOscillator:
    def __init__(self, sr=48000):
        self.sr = sr
        self.rng = np.random.default_rng()
        # Pink noise state (Voss-McCartney)
        self._pink_state = np.zeros(16)
        self._pink_counter = 0

    def render(self, num_samples, color='white'):
        if color == 'white':
            return self.rng.standard_normal(num_samples)
        elif color == 'pink':
            out = np.zeros(num_samples, dtype=np.float64)
            for i in range(num_samples):
                self._pink_counter += 1
                # Update one random row based on trailing zeros
                k = 0
                n = self._pink_counter
                while n > 0 and (n & 1) == 0:
                    k += 1
                    n >>= 1
                if k < len(self._pink_state):
                    self._pink_state[k] = self.rng.standard_normal()
                out[i] = np.sum(self._pink_state) / len(self._pink_state)
            return out
        return self.rng.standard_normal(num_samples)


class SuperSawOscillator:
    def __init__(self, sr=48000, num_voices=7):
        self.sr = sr
        self.voices = [SawOscillator(sr) for _ in range(num_voices)]
        self.detune_ratios = [0.993, 0.996, 0.999, 1.000, 1.001, 1.004, 1.007]
        self.mix_levels = [0.5, 0.7, 0.9, 1.0, 0.9, 0.7, 0.5]
        self._mix_sum = sum(self.mix_levels)

    def render(self, num_samples, freq, detune=0.5):
        out = np.zeros(num_samples, dtype=np.float64)
        for voice, ratio, level in zip(self.voices, self.detune_ratios, self.mix_levels):
            spread = 1.0 + (ratio - 1.0) * detune
            out += voice.render(num_samples, freq * spread) * level
        return out / self._mix_sum
