import numpy as np


class TransportClock:
    """BPM-driven step sequencer clock with swing support."""

    def __init__(self, bpm=130, sr=48000, block_size=1024, steps_per_beat=4):
        self.bpm = bpm
        self.sr = sr
        self.block_size = block_size
        self.steps_per_beat = steps_per_beat
        self.swing = 0.0  # 0.0 to 0.5
        self.playing = False
        self.sample_pos = 0
        self.pattern_length = 16
        self._last_step = -1

    @property
    def samples_per_step(self):
        samples_per_beat = self.sr * 60.0 / self.bpm
        return samples_per_beat / self.steps_per_beat

    def reset(self):
        self.sample_pos = 0
        self._last_step = -1

    def advance(self, num_samples):
        """Advance clock, return list of (step_index, sample_offset_in_block)."""
        if not self.playing:
            return []

        triggers = []
        sps = self.samples_per_step

        for i in range(num_samples):
            abs_sample = self.sample_pos + i
            raw_step = abs_sample / sps
            step_int = int(raw_step)

            # Apply swing to odd steps
            if step_int % 2 == 0:
                boundary = int(step_int * sps)
            else:
                boundary = int(step_int * sps + self.swing * sps)

            if abs_sample == boundary and step_int != self._last_step:
                step_in_pattern = step_int % self.pattern_length
                triggers.append((step_in_pattern, i))
                self._last_step = step_int

        self.sample_pos += num_samples
        return triggers

    @property
    def current_step(self):
        sps = self.samples_per_step
        if sps <= 0:
            return 0
        step = int(self.sample_pos / sps)
        return step % self.pattern_length
