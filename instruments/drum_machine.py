import numpy as np
from ..synth.envelopes import ExponentialDecay, PitchEnvelope
from ..synth.filters import BiquadChain


class TechnoKick:
    def __init__(self, sr=48000):
        self.sr = sr
        self.phase = 0.0
        self.amp_env = ExponentialDecay(0.6, sr)
        self.click_env = ExponentialDecay(0.008, sr)
        self.sample_pos = 0

        # Tunable
        self.pitch = 50.0
        self.pitch_env_amt = 200.0
        self.pitch_decay = 0.04
        self.decay = 0.6
        self.drive = 2.0
        self.click = 0.5

    def trigger(self, velocity=1.0):
        self.phase = 0.0
        self.sample_pos = 0
        self.amp_env = ExponentialDecay(self.decay, self.sr)
        self.amp_env.trigger(velocity)
        self.click_env = ExponentialDecay(0.008, self.sr)
        self.click_env.trigger(velocity)

    def render(self, num_samples):
        if not self.amp_env.active:
            return np.zeros(num_samples, dtype=np.float64)

        t = (self.sample_pos + np.arange(num_samples, dtype=np.float64)) / self.sr
        self.sample_pos += num_samples

        # Pitch envelope
        freq = self.pitch + self.pitch_env_amt * np.exp(-t / self.pitch_decay)
        phase_inc = freq / self.sr
        phases = self.phase + np.cumsum(phase_inc)
        self.phase = phases[-1] % (2 * np.pi)

        # Body sine
        body = np.sin(2 * np.pi * phases)

        # Click transient
        click_noise = np.random.randn(num_samples) * self.click_env.render(num_samples) * self.click

        signal = body * 0.8 + click_noise * 0.2
        signal *= self.amp_env.render(num_samples)

        # Saturation
        if self.drive > 1.0:
            signal = np.tanh(signal * self.drive) / np.tanh(self.drive)

        return signal


class Snare:
    def __init__(self, sr=48000):
        self.sr = sr
        self.body_env = ExponentialDecay(0.1, sr)
        self.noise_env = ExponentialDecay(0.15, sr)
        self.body_freq = 200.0
        self.body_phase = 0.0
        self.snappy = 0.6
        self.noise_filter = BiquadChain(sr)
        self.noise_filter.configure([1000, 8000], 'band', order=2)
        self.sample_pos = 0

    def trigger(self, velocity=1.0):
        self.body_env = ExponentialDecay(0.1, self.sr)
        self.noise_env = ExponentialDecay(0.15, self.sr)
        self.body_env.trigger(velocity)
        self.noise_env.trigger(velocity)
        self.body_phase = 0.0
        self.sample_pos = 0

    def render(self, num_samples):
        if not self.body_env.active and not self.noise_env.active:
            return np.zeros(num_samples, dtype=np.float64)

        t = (self.sample_pos + np.arange(num_samples, dtype=np.float64)) / self.sr
        self.sample_pos += num_samples

        # Body with pitch drop
        freq = self.body_freq * (1.0 + 0.5 * np.exp(-t / 0.01))
        phase_inc = np.cumsum(freq / self.sr)
        body = np.sin(2 * np.pi * (self.body_phase + phase_inc))
        self.body_phase = (self.body_phase + phase_inc[-1]) % 1.0
        body *= self.body_env.render(num_samples) * (1.0 - self.snappy)

        # Noise
        noise = np.random.randn(num_samples)
        noise = self.noise_filter.process(noise)
        noise *= self.noise_env.render(num_samples) * self.snappy

        return body + noise


class Clap:
    def __init__(self, sr=48000):
        self.sr = sr
        self.tail_env = ExponentialDecay(0.15, sr)
        self.bp_filter = BiquadChain(sr)
        self.bp_filter.configure([800, 3500], 'band', order=2)
        self.burst_offsets = [0, 0.01, 0.02, 0.035]
        self._burst_samples = []
        self.phase = 0

    def trigger(self, velocity=1.0):
        self.tail_env = ExponentialDecay(0.15, self.sr)
        self.tail_env.trigger(velocity)
        self._burst_samples = [int(t * self.sr) for t in self.burst_offsets]
        self.phase = 0

    def render(self, num_samples):
        if not self.tail_env.active:
            return np.zeros(num_samples, dtype=np.float64)

        noise = np.random.randn(num_samples)
        signal = np.zeros(num_samples, dtype=np.float64)

        for offset in self._burst_samples:
            if self.phase <= offset < self.phase + num_samples:
                local = offset - self.phase
                burst_len = min(int(0.005 * self.sr), num_samples - local)
                env = np.exp(-np.arange(burst_len) / (0.002 * self.sr))
                signal[local:local + burst_len] += noise[local:local + burst_len] * env * 0.5

        signal += noise * self.tail_env.render(num_samples) * 0.3
        signal = self.bp_filter.process(signal)
        self.phase += num_samples
        return signal


class HiHat:
    def __init__(self, sr=48000):
        self.sr = sr
        self.env = ExponentialDecay(0.05, sr)
        self.ring_freqs = [205.3, 369.6, 304.4, 522.7, 540.0, 800.0]
        self.ring_phases = np.zeros(6)
        self.hp_filter = BiquadChain(sr)
        self.hp_filter.configure(7000, 'high', order=4)
        self.decay = 0.05
        self.tone = 0.6

    def trigger(self, velocity=1.0, open_hat=False):
        decay = 0.3 if open_hat else self.decay
        self.env = ExponentialDecay(decay, self.sr)
        self.env.trigger(velocity)

    def render(self, num_samples):
        if not self.env.active:
            return np.zeros(num_samples, dtype=np.float64)

        # Metallic ring: 6 detuned square waves
        ring = np.zeros(num_samples, dtype=np.float64)
        for j, freq in enumerate(self.ring_freqs):
            dt = freq / self.sr
            phases = (self.ring_phases[j] + np.arange(num_samples) * dt) % 1.0
            self.ring_phases[j] = phases[-1]
            ring += np.sign(np.sin(2 * np.pi * phases))
        ring /= len(self.ring_freqs)

        noise = np.random.randn(num_samples)
        signal = ring * self.tone + noise * (1.0 - self.tone)
        signal = self.hp_filter.process(signal)
        signal *= self.env.render(num_samples)
        return signal


class Tom:
    def __init__(self, sr=48000, freq=80):
        self.sr = sr
        self.base_freq = freq
        self.phase = 0.0
        self.amp_env = ExponentialDecay(0.3, sr)
        self.sample_pos = 0

    def trigger(self, velocity=1.0):
        self.phase = 0.0
        self.sample_pos = 0
        self.amp_env = ExponentialDecay(0.3, self.sr)
        self.amp_env.trigger(velocity)

    def render(self, num_samples):
        if not self.amp_env.active:
            return np.zeros(num_samples, dtype=np.float64)

        t = (self.sample_pos + np.arange(num_samples, dtype=np.float64)) / self.sr
        self.sample_pos += num_samples
        freq = self.base_freq * (1.0 + 1.5 * np.exp(-t / 0.03))
        phase_inc = np.cumsum(freq / self.sr)
        signal = np.sin(2 * np.pi * (self.phase + phase_inc))
        self.phase = (self.phase + phase_inc[-1]) % 1.0
        signal *= self.amp_env.render(num_samples)
        return signal


class Rimshot:
    def __init__(self, sr=48000):
        self.sr = sr
        self.env = ExponentialDecay(0.03, sr)
        self.phase = 0.0
        self.sample_pos = 0

    def trigger(self, velocity=1.0):
        self.phase = 0.0
        self.sample_pos = 0
        self.env = ExponentialDecay(0.03, self.sr)
        self.env.trigger(velocity)

    def render(self, num_samples):
        if not self.env.active:
            return np.zeros(num_samples, dtype=np.float64)

        t = (self.sample_pos + np.arange(num_samples, dtype=np.float64)) / self.sr
        self.sample_pos += num_samples

        # Pitched component + noise
        freq = 800 * (1.0 + 2.0 * np.exp(-t / 0.005))
        phase_inc = np.cumsum(freq / self.sr)
        tone = np.sin(2 * np.pi * (self.phase + phase_inc)) * 0.6
        self.phase = (self.phase + phase_inc[-1]) % 1.0
        noise = np.random.randn(num_samples) * 0.4
        signal = (tone + noise) * self.env.render(num_samples)
        return signal


class DrumMachine:
    """8-voice drum machine with per-voice synthesis."""

    VOICE_NAMES = ['kick', 'snare', 'clap', 'closed_hat', 'open_hat', 'tom_lo', 'tom_hi', 'rimshot']

    def __init__(self, sr=48000):
        self.sr = sr
        self.voices = {
            'kick': TechnoKick(sr),
            'snare': Snare(sr),
            'clap': Clap(sr),
            'closed_hat': HiHat(sr),
            'open_hat': HiHat(sr),
            'tom_lo': Tom(sr, freq=80),
            'tom_hi': Tom(sr, freq=120),
            'rimshot': Rimshot(sr),
        }
        self.levels = {k: 0.8 for k in self.voices}
        # Stereo pan positions (-1 left, 0 center, 1 right)
        self.pans = {
            'kick': 0.0, 'snare': 0.0, 'clap': 0.1,
            'closed_hat': 0.3, 'open_hat': -0.3,
            'tom_lo': -0.2, 'tom_hi': 0.2, 'rimshot': 0.15,
        }
        self.muted = {k: False for k in self.voices}

    def trigger_voice(self, voice_name, velocity=1.0, **kwargs):
        if voice_name in self.voices and not self.muted[voice_name]:
            if voice_name == 'open_hat':
                self.voices[voice_name].trigger(velocity, open_hat=True)
            else:
                self.voices[voice_name].trigger(velocity)

    def render(self, num_samples):
        """Render all voices into stereo output (num_samples, 2)."""
        stereo = np.zeros((num_samples, 2), dtype=np.float64)
        for name, voice in self.voices.items():
            if self.muted[name]:
                continue
            mono = voice.render(num_samples) * self.levels.get(name, 0.8)
            pan = self.pans.get(name, 0.0)
            # Constant power panning
            angle = (pan + 1.0) * np.pi / 4.0
            stereo[:, 0] += mono * np.cos(angle)
            stereo[:, 1] += mono * np.sin(angle)
        return stereo

    def apply_preset(self, preset):
        """Apply a drum preset dict to voice parameters."""
        if 'kick' in preset:
            kick = self.voices['kick']
            for k, v in preset['kick'].items():
                if hasattr(kick, k):
                    setattr(kick, k, v)
        if 'hat' in preset:
            for hat_name in ['closed_hat', 'open_hat']:
                hat = self.voices[hat_name]
                for k, v in preset['hat'].items():
                    if hasattr(hat, k):
                        setattr(hat, k, v)
        if 'snare' in preset:
            snare = self.voices['snare']
            for k, v in preset['snare'].items():
                if hasattr(snare, k):
                    setattr(snare, k, v)
