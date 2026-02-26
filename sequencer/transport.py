from .pattern import Pattern


class Transport:
    """Transport controller - manages playback, pattern selection, arrangement."""

    def __init__(self):
        self.patterns = [Pattern(f'Pattern {i+1}') for i in range(8)]
        self.current_pattern_idx = 0
        self.playing = False
        self.recording = False

        # Arrangement mode
        self.arrangement_mode = False
        self.arrangement = []  # list of pattern indices
        self.arrangement_pos = 0

    @property
    def current_pattern(self):
        return self.patterns[self.current_pattern_idx]

    def play(self):
        self.playing = True

    def stop(self):
        self.playing = False

    def toggle_play(self):
        self.playing = not self.playing
        return self.playing

    def select_pattern(self, idx):
        if 0 <= idx < len(self.patterns):
            self.current_pattern_idx = idx

    def next_pattern(self):
        self.current_pattern_idx = (self.current_pattern_idx + 1) % len(self.patterns)

    def prev_pattern(self):
        self.current_pattern_idx = (self.current_pattern_idx - 1) % len(self.patterns)

    def copy_pattern(self, src_idx, dst_idx):
        if 0 <= src_idx < len(self.patterns) and 0 <= dst_idx < len(self.patterns):
            import json
            data = self.patterns[src_idx].to_dict()
            data['name'] = f'Pattern {dst_idx + 1}'
            self.patterns[dst_idx] = Pattern.from_dict(data)

    def get_next_arrangement_pattern(self):
        """Called when a pattern finishes in arrangement mode."""
        if not self.arrangement_mode or not self.arrangement:
            return self.current_pattern_idx
        self.arrangement_pos = (self.arrangement_pos + 1) % len(self.arrangement)
        idx = self.arrangement[self.arrangement_pos]
        self.current_pattern_idx = idx
        return idx
