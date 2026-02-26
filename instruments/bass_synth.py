import numpy as np
from ..synth.oscillators import SawOscillator, SquareOscillator, SineOscillator
from ..synth.filters import MoogLadderFilter
from ..synth.envelopes import ADSREnvelope


class BassSynth:
    """Monophonic bass synth - TB-303 style acid + deep techno bass."""

    def __init__(self, sr=48000):
        self.sr = sr
        self.saw_osc = SawOscillator(sr)
        self.square_osc = SquareOscillator(sr)
        self.sub_osc = SineOscillator(sr)
        self.filter = MoogLadderFilter(sr)
        self.amp_env = ADSREnvelope(0.005, 0.2, 0.0, 0.05, sr)
        self.filter_env = ADSREnvelope(0.005, 0.2, 0.0, 0.1, sr)

        # Parameters
        self.waveform = 'saw'
        self.cutoff = 800.0
        self.resonance = 2.5
        self.env_mod = 3000.0
        self.accent = 0.0
        self.glide_time = 0.0
        self.sub_level = 0.3
        self.drive = 1.5

        self.current_freq = 55.0
        self.target_freq = 55.0
        self._accent_active = False
        self._active = False

    def trigger(self, note, velocity=1.0, accent=False):
        freq = 440.0 * 2 ** ((note - 69) / 12.0)
        self.target_freq = freq
        if self.glide_time <= 0:
            self.current_freq = freq

        vel = min(velocity + (0.3 if accent else 0.0), 1.0)
        self.amp_env.gate_on(vel)
        self.filter_env.gate_on(vel)
        self._accent_active = accent
        self._active = True

    def release(self):
        self.amp_env.gate_off()
        self.filter_env.gate_off()

    def render(self, num_samples):
        if not self._active:
            return np.zeros((num_samples, 2), dtype=np.float64)

        # Glide
        if self.glide_time > 0 and abs(self.current_freq - self.target_freq) > 0.1:
            glide_rate = 1.0 / (self.glide_time * self.sr)
            freq_array = np.zeros(num_samples, dtype=np.float64)
            for i in range(num_samples):
                diff = self.target_freq - self.current_freq
                self.current_freq += diff * glide_rate
                freq_array[i] = self.current_freq
        else:
            self.current_freq = self.target_freq
            freq_array = self.current_freq

        # Main oscillator
        if self.waveform == 'saw':
            osc_out = self.saw_osc.render(num_samples, freq_array)
        else:
            osc_out = self.square_osc.render(num_samples, freq_array)

        # Sub oscillator (one octave down)
        sub_freq = freq_array * 0.5 if isinstance(freq_array, np.ndarray) else freq_array * 0.5
        sub_out = self.sub_osc.render(num_samples, sub_freq)
        signal = osc_out * 0.7 + sub_out * self.sub_level

        # Filter envelope modulation
        env_mod = self.filter_env.render(num_samples)
        accent_boost = 1.5 if self._accent_active else 1.0
        cutoff_mod = self.cutoff + env_mod * self.env_mod * accent_boost
        cutoff_mod = np.clip(cutoff_mod, 20, self.sr * 0.45)

        signal = self.filter.process(signal, cutoff=cutoff_mod, resonance=self.resonance)

        # Amplitude envelope
        amp = self.amp_env.render(num_samples)
        signal *= amp

        # Drive
        if self.drive > 1.0:
            signal = np.tanh(signal * self.drive) / np.tanh(self.drive)

        if not self.amp_env.active:
            self._active = False

        # Mono to stereo (centered)
        stereo = np.zeros((num_samples, 2), dtype=np.float64)
        stereo[:, 0] = signal
        stereo[:, 1] = signal
        return stereo

    def apply_preset(self, preset):
        for k, v in preset.items():
            if hasattr(self, k):
                setattr(self, k, v)
