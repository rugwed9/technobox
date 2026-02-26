import numpy as np
from .filters import BiquadChain


class StereoDelay:
    """Tempo-synced stereo ping-pong delay."""

    def __init__(self, sr=48000, max_delay_sec=2.0):
        self.sr = sr
        max_samples = int(max_delay_sec * sr)
        self.buffer_l = np.zeros(max_samples, dtype=np.float64)
        self.buffer_r = np.zeros(max_samples, dtype=np.float64)
        self.write_pos = 0
        self.max_samples = max_samples

        self.delay_l = int(0.375 * sr)
        self.delay_r = int(0.5 * sr)
        self.feedback = 0.4
        self.mix = 0.3
        self.enabled = True

        self.lp_filter = BiquadChain(sr)
        self.lp_filter.configure(6000, 'low', order=2)

    def set_tempo_sync(self, bpm):
        beat_sec = 60.0 / bpm
        self.delay_l = int(beat_sec * 0.75 * self.sr)  # dotted eighth
        self.delay_r = int(beat_sec * self.sr)           # quarter

    def process(self, stereo):
        if not self.enabled:
            return stereo
        n = stereo.shape[0]
        out = stereo.copy()

        for i in range(n):
            read_l = (self.write_pos - self.delay_l) % self.max_samples
            read_r = (self.write_pos - self.delay_r) % self.max_samples
            delayed_l = self.buffer_l[read_l]
            delayed_r = self.buffer_r[read_r]

            wp = self.write_pos % self.max_samples
            self.buffer_l[wp] = stereo[i, 0] + delayed_r * self.feedback
            self.buffer_r[wp] = stereo[i, 1] + delayed_l * self.feedback

            out[i, 0] += delayed_l * self.mix
            out[i, 1] += delayed_r * self.mix
            self.write_pos += 1

        return out


class PlateReverb:
    """Schroeder/Moorer plate reverb tuned for techno."""

    def __init__(self, sr=48000):
        self.sr = sr
        comb_delays_ms = [29.7, 37.1, 41.1, 43.7, 47.3, 53.0, 59.3, 67.1]
        self.comb_delays = [int(d / 1000 * sr) for d in comb_delays_ms]
        self.comb_buffers = [np.zeros(d + 1, dtype=np.float64) for d in self.comb_delays]
        self.comb_positions = [0] * len(self.comb_delays)
        self.comb_feedback = 0.84

        allpass_delays_ms = [5.0, 1.7, 3.3, 7.3]
        self.ap_delays = [int(d / 1000 * sr) for d in allpass_delays_ms]
        self.ap_buffers = [np.zeros(d + 1, dtype=np.float64) for d in self.ap_delays]
        self.ap_positions = [0] * len(self.ap_delays)
        self.ap_gain = 0.7

        self.mix = 0.2
        self.damping = 0.3
        self.lp_state = [0.0] * len(self.comb_delays)
        self.enabled = True

    def process_mono(self, x):
        if not self.enabled:
            return x
        n = len(x)
        out = np.zeros(n, dtype=np.float64)

        for i in range(n):
            comb_sum = 0.0
            for c in range(len(self.comb_delays)):
                buf = self.comb_buffers[c]
                pos = self.comb_positions[c]
                delay = self.comb_delays[c]
                read_pos = (pos - delay) % len(buf)
                delayed = buf[read_pos]
                self.lp_state[c] = delayed * (1 - self.damping) + self.lp_state[c] * self.damping
                buf[pos % len(buf)] = x[i] + self.lp_state[c] * self.comb_feedback
                self.comb_positions[c] = pos + 1
                comb_sum += delayed
            comb_sum /= len(self.comb_delays)

            signal = comb_sum
            for a in range(len(self.ap_delays)):
                buf = self.ap_buffers[a]
                pos = self.ap_positions[a]
                delay = self.ap_delays[a]
                read_pos = (pos - delay) % len(buf)
                delayed = buf[read_pos]
                output = -signal * self.ap_gain + delayed
                buf[pos % len(buf)] = signal + delayed * self.ap_gain
                self.ap_positions[a] = pos + 1
                signal = output
            out[i] = signal

        return x * (1 - self.mix) + out * self.mix

    def process(self, stereo):
        if not self.enabled:
            return stereo
        mid = (stereo[:, 0] + stereo[:, 1]) * 0.5
        reverbed = self.process_mono(mid)
        out = stereo.copy()
        out[:, 0] += (reverbed - mid) * self.mix
        out[:, 1] += (reverbed - mid) * self.mix
        return out


class Distortion:
    """Multiple distortion modes for techno textures."""

    def __init__(self, sr=48000):
        self.sr = sr
        self.mode = 'tanh'
        self.drive = 2.0
        self.mix = 1.0
        self.enabled = False
        self.lp_filter = BiquadChain(sr)
        self.lp_filter.configure(8000, 'low', order=2)

    def process(self, stereo):
        if not self.enabled:
            return stereo
        out = stereo.copy()
        for ch in range(2):
            dry = stereo[:, ch]
            driven = dry * self.drive

            if self.mode == 'tanh':
                wet = np.tanh(driven)
            elif self.mode == 'hard_clip':
                wet = np.clip(driven, -1, 1)
            elif self.mode == 'fold':
                wet = driven.copy()
                for _ in range(3):
                    wet = np.where(wet > 1, 2 - wet, wet)
                    wet = np.where(wet < -1, -2 - wet, wet)
            elif self.mode == 'bitcrush':
                bits = max(1, int(16 - self.drive * 3))
                levels = 2 ** bits
                wet = np.round(driven * levels) / levels
            else:
                wet = np.tanh(driven)

            wet = self.lp_filter.process(wet)
            out[:, ch] = dry * (1 - self.mix) + wet * self.mix
        return out


class Compressor:
    """Feed-forward compressor with sidechain support."""

    def __init__(self, sr=48000):
        self.sr = sr
        self.threshold = -12.0
        self.ratio = 4.0
        self.attack = 0.003
        self.release = 0.1
        self.makeup = 0.0
        self.envelope = 0.0
        self.enabled = True

    def process_mono(self, x, sidechain=None):
        if not self.enabled:
            return x
        if sidechain is None:
            sidechain = x
        n = len(x)
        out = np.zeros(n, dtype=np.float64)
        env = self.envelope

        attack_coef = np.exp(-1.0 / (self.attack * self.sr))
        release_coef = np.exp(-1.0 / (self.release * self.sr))
        thresh_lin = 10 ** (self.threshold / 20)
        makeup_lin = 10 ** (self.makeup / 20)

        for i in range(n):
            level = abs(sidechain[i])
            if level > env:
                env = attack_coef * env + (1 - attack_coef) * level
            else:
                env = release_coef * env + (1 - release_coef) * level

            if env > thresh_lin and env > 1e-10:
                gain_db = self.threshold + (20 * np.log10(env) - self.threshold) / self.ratio
                gain = 10 ** (gain_db / 20) / env
            else:
                gain = 1.0
            out[i] = x[i] * gain * makeup_lin

        self.envelope = env
        return out

    def process(self, stereo):
        if not self.enabled:
            return stereo
        mid = (stereo[:, 0] + stereo[:, 1]) * 0.5
        compressed = self.process_mono(mid)
        gain = np.where(np.abs(mid) > 1e-10, compressed / mid, 1.0)
        out = stereo.copy()
        out[:, 0] *= gain
        out[:, 1] *= gain
        return out
