import numpy as np
from ..synth.oscillators import SawOscillator, TriangleOscillator
from ..synth.filters import StateVariableFilter
from ..synth.envelopes import ADSREnvelope


class PadVoice:
    def __init__(self, sr=48000):
        self.sr = sr
        self.osc1 = SawOscillator(sr)
        self.osc2 = SawOscillator(sr)
        self.osc3 = TriangleOscillator(sr)
        self.filter = StateVariableFilter(sr)
        self.amp_env = ADSREnvelope(0.5, 0.3, 0.7, 1.0, sr)
        self.note = 0
        self.freq = 440.0
        self.active = False

    def note_on(self, note, velocity=0.6):
        self.note = note
        self.freq = 440.0 * 2 ** ((note - 69) / 12.0)
        self.amp_env.gate_on(velocity)
        self.active = True

    def note_off(self):
        self.amp_env.gate_off()

    def render(self, num_samples, detune, cutoff, resonance):
        if not self.active:
            return np.zeros(num_samples, dtype=np.float64)

        # 3 detuned oscillators for thick pad sound
        o1 = self.osc1.render(num_samples, self.freq)
        o2 = self.osc2.render(num_samples, self.freq * (1.0 + detune))
        o3 = self.osc3.render(num_samples, self.freq * (1.0 - detune * 0.5))

        signal = (o1 + o2 + o3) / 3.0

        # Gentle lowpass
        signal = self.filter.process(signal, cutoff, resonance, mode='low')

        # Slow envelope
        amp = self.amp_env.render(num_samples)
        signal *= amp

        if not self.amp_env.active:
            self.active = False

        return signal


class PadSynth:
    """Ambient pad synthesizer with slow attack and chorus-like detune."""

    MAX_VOICES = 6

    def __init__(self, sr=48000):
        self.sr = sr
        self.voices = [PadVoice(sr) for _ in range(self.MAX_VOICES)]

        self.detune = 0.008
        self.cutoff = 2000.0
        self.resonance = 0.2
        self.volume = 0.4
        self.stereo_width = 0.5
        self._active = False

        # Chorus LFO
        self.chorus_rate = 0.3
        self.chorus_depth = 0.003
        self.chorus_phase = 0.0

    def trigger(self, note, velocity=0.6):
        voice = None
        for v in self.voices:
            if not v.active:
                voice = v
                break
        if voice is None:
            voice = self.voices[0]
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
        # Chorus modulation on detune
        lfo = np.sin(2 * np.pi * self.chorus_rate *
                     (self.chorus_phase + np.arange(num_samples) / self.sr))
        self.chorus_phase = (self.chorus_phase + num_samples / self.sr * self.chorus_rate) % 1.0
        mod_detune = self.detune + lfo.mean() * self.chorus_depth

        mono = np.zeros(num_samples, dtype=np.float64)
        any_active = False
        for voice in self.voices:
            if voice.active:
                any_active = True
                mono += voice.render(num_samples, mod_detune, self.cutoff, self.resonance)

        self._active = any_active
        mono *= self.volume

        # Stereo spread
        stereo = np.zeros((num_samples, 2), dtype=np.float64)
        stereo[:, 0] = mono * (1.0 + self.stereo_width * 0.3)
        stereo[:, 1] = mono * (1.0 - self.stereo_width * 0.3)
        return stereo

    def apply_preset(self, preset):
        for k, v in preset.items():
            if hasattr(self, k):
                setattr(self, k, v)
