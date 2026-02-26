import numpy as np
from ..synth.oscillators import SawOscillator, SquareOscillator, TriangleOscillator, SuperSawOscillator
from ..synth.filters import StateVariableFilter
from ..synth.envelopes import ADSREnvelope


class LeadVoice:
    """Single voice for the lead synth."""

    def __init__(self, sr=48000):
        self.sr = sr
        self.osc1 = SawOscillator(sr)
        self.osc2 = SquareOscillator(sr)
        self.filter = StateVariableFilter(sr)
        self.amp_env = ADSREnvelope(0.01, 0.2, 0.6, 0.3, sr)
        self.filter_env = ADSREnvelope(0.01, 0.3, 0.2, 0.2, sr)
        self.note = 0
        self.freq = 440.0
        self.active = False

    def note_on(self, note, velocity=1.0):
        self.note = note
        self.freq = 440.0 * 2 ** ((note - 69) / 12.0)
        self.amp_env.gate_on(velocity)
        self.filter_env.gate_on(velocity)
        self.active = True

    def note_off(self):
        self.amp_env.gate_off()
        self.filter_env.gate_off()

    def render(self, num_samples, osc1_type, osc2_type, osc2_detune, osc_mix,
               filter_type, cutoff, resonance, filter_env_amt):
        if not self.active:
            return np.zeros(num_samples, dtype=np.float64)

        # Oscillator 1
        osc1_out = self.osc1.render(num_samples, self.freq)

        # Oscillator 2 (detuned)
        detune_ratio = 2 ** (osc2_detune / 12.0)
        osc2_out = self.osc2.render(num_samples, self.freq * detune_ratio)

        signal = osc1_out * (1.0 - osc_mix) + osc2_out * osc_mix

        # Filter with envelope
        f_env = self.filter_env.render(num_samples)
        cutoff_mod = cutoff + f_env * filter_env_amt
        cutoff_mod = np.clip(cutoff_mod, 20, self.sr * 0.45)

        signal = self.filter.process(signal, cutoff_mod, resonance, mode=filter_type)

        # Amplitude envelope
        amp = self.amp_env.render(num_samples)
        signal *= amp

        if not self.amp_env.active:
            self.active = False

        return signal


class LeadSynth:
    """Polyphonic lead synthesizer with dual oscillators and filter."""

    MAX_VOICES = 8

    def __init__(self, sr=48000):
        self.sr = sr
        self.voices = [LeadVoice(sr) for _ in range(self.MAX_VOICES)]

        # Global params
        self.osc1_type = 'saw'
        self.osc2_type = 'square'
        self.osc2_detune = 0.05  # semitones
        self.osc_mix = 0.5
        self.filter_type = 'low'
        self.cutoff = 3000.0
        self.resonance = 0.3
        self.filter_env_amt = 2000.0
        self.volume = 0.6

        # LFO
        self.lfo_rate = 2.0
        self.lfo_depth_filter = 0.0
        self.lfo_phase = 0.0

        self._active = False

    def trigger(self, note, velocity=1.0):
        # Find free voice or steal oldest
        voice = None
        for v in self.voices:
            if not v.active:
                voice = v
                break
        if voice is None:
            voice = self.voices[0]  # steal

        voice.note_on(note, velocity)
        self._active = True

    def release_note(self, note):
        for v in self.voices:
            if v.active and v.note == note:
                v.note_off()
                break

    def release_all(self):
        for v in self.voices:
            if v.active:
                v.note_off()

    def render(self, num_samples):
        # LFO
        lfo_samples = np.arange(num_samples) / self.sr
        lfo = np.sin(2 * np.pi * self.lfo_rate * (self.lfo_phase + lfo_samples))
        self.lfo_phase = (self.lfo_phase + num_samples / self.sr * self.lfo_rate) % 1.0

        cutoff_with_lfo = self.cutoff + lfo * self.lfo_depth_filter

        mono = np.zeros(num_samples, dtype=np.float64)
        any_active = False
        for voice in self.voices:
            if voice.active:
                any_active = True
                mono += voice.render(
                    num_samples,
                    self.osc1_type, self.osc2_type,
                    self.osc2_detune, self.osc_mix,
                    self.filter_type, cutoff_with_lfo,
                    self.resonance, self.filter_env_amt
                )

        self._active = any_active
        mono *= self.volume

        stereo = np.zeros((num_samples, 2), dtype=np.float64)
        stereo[:, 0] = mono
        stereo[:, 1] = mono
        return stereo

    def apply_preset(self, preset):
        for k, v in preset.items():
            if hasattr(self, k):
                setattr(self, k, v)
