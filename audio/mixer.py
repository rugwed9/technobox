import numpy as np
from ..synth.effects import StereoDelay, PlateReverb, Distortion, Compressor
from ..synth.filters import BiquadChain


class MasterBus:
    """Master bus processing: HP filter -> compression -> soft limiting."""

    def __init__(self, sr=48000):
        self.sr = sr
        self.hp_filter = BiquadChain(sr)
        self.hp_filter.configure(30, 'high', order=2)

        self.delay = StereoDelay(sr)
        self.reverb = PlateReverb(sr)
        self.distortion = Distortion(sr)
        self.compressor = Compressor(sr)
        self.compressor.threshold = -6.0
        self.compressor.ratio = 3.0

        self.master_volume = 0.8

    def process(self, stereo):
        # HP to remove rumble
        for ch in range(2):
            stereo[:, ch] = self.hp_filter.process(stereo[:, ch])

        # Effects chain
        stereo = self.distortion.process(stereo)
        stereo = self.delay.process(stereo)
        stereo = self.reverb.process(stereo)
        stereo = self.compressor.process(stereo)

        # Master volume
        stereo *= self.master_volume

        # Soft limiter
        stereo = np.tanh(stereo * 0.95) / 0.95

        return stereo


class Mixer:
    """Mixes instrument outputs with volume/pan/mute/solo."""

    def __init__(self, sr=48000):
        self.sr = sr
        self.master = MasterBus(sr)

        # Per-track settings (set dynamically)
        self.track_volumes = {}
        self.track_pans = {}
        self.track_mutes = {}
        self.track_solos = {}

    def init_tracks(self, track_names):
        for name in track_names:
            self.track_volumes.setdefault(name, 0.8)
            self.track_pans.setdefault(name, 0.0)
            self.track_mutes.setdefault(name, False)
            self.track_solos.setdefault(name, False)

    def mix(self, track_outputs, block_size):
        """Mix dict of track_name -> stereo array into master stereo output."""
        stereo = np.zeros((block_size, 2), dtype=np.float64)
        has_solo = any(self.track_solos.values())

        for name, audio in track_outputs.items():
            if self.track_mutes.get(name, False):
                continue
            if has_solo and not self.track_solos.get(name, False):
                continue

            vol = self.track_volumes.get(name, 0.8)
            pan = self.track_pans.get(name, 0.0)

            if audio.ndim == 1:
                # Mono to stereo
                angle = (pan + 1.0) * np.pi / 4.0
                stereo[:, 0] += audio * np.cos(angle) * vol
                stereo[:, 1] += audio * np.sin(angle) * vol
            else:
                stereo += audio * vol

        # Master processing
        stereo = self.master.process(stereo)
        return stereo
