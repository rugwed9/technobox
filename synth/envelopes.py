import numpy as np


class ADSREnvelope:
    IDLE, ATTACK, DECAY, SUSTAIN, RELEASE = range(5)

    def __init__(self, attack=0.01, decay=0.1, sustain=0.7, release=0.3, sr=48000):
        self.attack = max(attack, 0.001)
        self.decay = max(decay, 0.001)
        self.sustain = sustain
        self.release = max(release, 0.001)
        self.sr = sr
        self.state = self.IDLE
        self.level = 0.0
        self.target = 0.0
        self._attack_rate = 0.0
        self._decay_rate = 0.0
        self._release_coeff = 0.0

    def gate_on(self, velocity=1.0):
        self.state = self.ATTACK
        self.target = velocity
        self._attack_rate = 1.0 / (self.attack * self.sr)
        self._decay_rate = 1.0 / (self.decay * self.sr)
        self._release_coeff = np.exp(-1.0 / (self.release * self.sr))

    def gate_off(self):
        if self.state != self.IDLE:
            self.state = self.RELEASE

    def render(self, num_samples):
        out = np.zeros(num_samples, dtype=np.float64)
        for i in range(num_samples):
            if self.state == self.ATTACK:
                self.level += self._attack_rate * self.target
                if self.level >= self.target:
                    self.level = self.target
                    self.state = self.DECAY
            elif self.state == self.DECAY:
                self.level -= self._decay_rate * (self.target - self.sustain * self.target)
                if self.level <= self.sustain * self.target:
                    self.level = self.sustain * self.target
                    self.state = self.SUSTAIN
            elif self.state == self.SUSTAIN:
                pass
            elif self.state == self.RELEASE:
                self.level *= self._release_coeff
                if self.level < 0.0001:
                    self.level = 0.0
                    self.state = self.IDLE
            out[i] = self.level
        return out

    @property
    def active(self):
        return self.state != self.IDLE


class ExponentialDecay:
    def __init__(self, decay_time=0.5, sr=48000):
        self.sr = sr
        self.decay_time = decay_time
        self.decay_rate = np.exp(-1.0 / (max(decay_time, 0.001) * sr))
        self.level = 0.0
        self.active = False

    def trigger(self, velocity=1.0):
        self.level = velocity
        self.active = True

    def set_decay(self, decay_time):
        self.decay_time = decay_time
        self.decay_rate = np.exp(-1.0 / (max(decay_time, 0.001) * self.sr))

    def render(self, num_samples):
        if not self.active:
            return np.zeros(num_samples, dtype=np.float64)
        rates = self.decay_rate ** np.arange(num_samples)
        out = self.level * rates
        self.level = out[-1]
        if self.level < 0.0001:
            self.active = False
            self.level = 0.0
        return out


class PitchEnvelope:
    def __init__(self, start_freq=200, end_freq=50, decay_time=0.05, sr=48000):
        self.start = start_freq
        self.end = end_freq
        self.decay_time = max(decay_time, 0.001)
        self.sr = sr
        self.sample_pos = 0
        self.active = False

    def trigger(self):
        self.active = True
        self.sample_pos = 0

    def render(self, num_samples):
        if not self.active:
            return np.full(num_samples, self.end, dtype=np.float64)
        t = (self.sample_pos + np.arange(num_samples)) / self.sr
        self.sample_pos += num_samples
        freq = self.end + (self.start - self.end) * np.exp(-t / self.decay_time)
        return freq
