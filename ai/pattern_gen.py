import numpy as np
from .style_presets import STYLES, get_scale_notes


class PatternGenerator:
    """Rule-based + stochastic pattern generation for techno."""

    def __init__(self, style='detroit'):
        self.style_name = style
        self.style = STYLES[style]
        self.rng = np.random.default_rng()
        self.rules = self.style['pattern_rules']

    def set_style(self, style_name):
        if style_name in STYLES:
            self.style_name = style_name
            self.style = STYLES[style_name]
            self.rules = self.style['pattern_rules']

    def generate_kick(self, length=16):
        """Generate kick pattern - foundation of techno."""
        pattern = np.zeros(length, dtype=np.float64)
        density = self.rules.get('kick_density', 0.5)

        # Four-on-the-floor
        for i in range(0, length, 4):
            pattern[i] = 1.0

        # Off-beat additions
        for i in range(length):
            if i % 4 != 0:
                if i % 2 == 0 and self.rng.random() < density * 0.4:
                    pattern[i] = 0.8
                elif i % 2 != 0 and self.rng.random() < density * 0.15:
                    pattern[i] = 0.6

        # Occasional removal for variation
        syncopation = self.rules.get('syncopation', 0.3)
        for i in [4, 12]:
            if self.rng.random() < syncopation * 0.25:
                pattern[i] = 0.0

        return pattern

    def generate_snare(self, length=16):
        """Snare on 2 and 4 (steps 4 and 12) with ghost notes."""
        pattern = np.zeros(length, dtype=np.float64)
        pattern[4] = 0.9
        pattern[12] = 0.9

        density = self.rules.get('syncopation', 0.3)
        for i in range(length):
            if pattern[i] == 0 and self.rng.random() < density * 0.1:
                pattern[i] = 0.3  # ghost note

        return pattern

    def generate_clap(self, length=16):
        """Clap - typically on beats 2 and 4, sometimes replaces snare."""
        pattern = np.zeros(length, dtype=np.float64)
        if self.rng.random() < 0.5:
            pattern[4] = 0.9
            pattern[12] = 0.9
        else:
            pattern[8] = 0.8
        return pattern

    def generate_closed_hat(self, length=16):
        """Closed hi-hat - drives the groove."""
        pattern = np.zeros(length, dtype=np.float64)
        density = self.rules.get('hat_density', 0.7)

        if density > 0.7:
            # Every 16th note
            pattern[:] = 0.6
            for i in range(0, length, 2):
                pattern[i] = 0.9
        elif density > 0.4:
            # Every 8th note
            for i in range(0, length, 2):
                pattern[i] = 0.8
            # Some 16th fills
            for i in range(1, length, 2):
                if self.rng.random() < density * 0.5:
                    pattern[i] = 0.5
        else:
            # Sparse
            for i in range(0, length, 4):
                pattern[i + 2] = 0.7  # offbeat
            for i in range(length):
                if pattern[i] == 0 and self.rng.random() < density * 0.3:
                    pattern[i] = 0.4

        return pattern

    def generate_open_hat(self, length=16):
        """Open hat - accents and variation."""
        pattern = np.zeros(length, dtype=np.float64)
        # Typically on offbeats
        positions = [2, 6, 10, 14]
        for pos in positions:
            if self.rng.random() < 0.35:
                pattern[pos] = 0.7

        return pattern

    def generate_bass(self, length=16, root=36):
        """Generate bass pattern with notes."""
        pattern_vel = np.zeros(length, dtype=np.float64)
        pattern_notes = np.full(length, root, dtype=int)
        pattern_accents = np.zeros(length, dtype=bool)
        pattern_glides = np.zeros(length, dtype=bool)

        scale_range = self.rules.get('bass_octave_range', [36, 48])
        scale_type = self.rules.get('scale', 'minor')
        movement = self.rules.get('bass_movement', 'root_fifth')
        notes = get_scale_notes(root % 12 + 36, scale_type, tuple(scale_range))
        if not notes:
            notes = [root]

        accent_prob = self.rules.get('accent_probability', 0.2)
        glide_prob = self.rules.get('glide_probability', 0.1)

        if movement == '303':
            # 303-style: random notes, accents, glides, rests
            for i in range(length):
                if self.rng.random() < 0.7:  # 70% chance of note
                    pattern_vel[i] = 0.6 + self.rng.random() * 0.4
                    pattern_notes[i] = self.rng.choice(notes)
                    pattern_accents[i] = self.rng.random() < accent_prob
                    pattern_glides[i] = self.rng.random() < glide_prob
        elif movement == 'chromatic':
            # Berlin: heavy on root, chromatic movements
            pattern_vel[0] = 0.9
            pattern_notes[0] = root
            for i in range(1, length):
                if i % 4 == 0:
                    pattern_vel[i] = 0.8
                    pattern_notes[i] = root
                elif self.rng.random() < 0.5:
                    pattern_vel[i] = 0.7
                    pattern_notes[i] = root + self.rng.choice([-1, 0, 1, 2, 5, 7])
        else:
            # root_fifth: classic techno bass
            fifth = root + 7
            for i in range(0, length, 4):
                pattern_vel[i] = 0.9
                pattern_notes[i] = root
            if self.rng.random() < 0.6:
                pattern_vel[8] = 0.8
                pattern_notes[8] = fifth
            # Fill
            for i in range(length):
                if pattern_vel[i] == 0 and self.rng.random() < 0.2:
                    pattern_vel[i] = 0.5
                    pattern_notes[i] = self.rng.choice([root, fifth, root + 12])

        return pattern_vel, pattern_notes, pattern_accents, pattern_glides

    def generate_lead(self, length=16, root=60):
        """Generate lead melody pattern."""
        pattern_vel = np.zeros(length, dtype=np.float64)
        pattern_notes = np.full(length, root, dtype=int)

        scale_type = self.rules.get('scale', 'minor')
        notes = get_scale_notes(root % 12 + 48, scale_type, (48, 84))
        if not notes:
            notes = [root]

        space = self.rules.get('space', 0.3)

        # Generate a simple melodic line
        current_note = self.rng.choice(notes)
        for i in range(length):
            if self.rng.random() > space:
                pattern_vel[i] = 0.5 + self.rng.random() * 0.4
                # Step motion with occasional leaps
                if self.rng.random() < 0.7:
                    # Step
                    idx = notes.index(current_note) if current_note in notes else 0
                    idx += self.rng.choice([-1, 0, 1])
                    idx = max(0, min(len(notes) - 1, idx))
                    current_note = notes[idx]
                else:
                    # Leap
                    current_note = self.rng.choice(notes)
                pattern_notes[i] = current_note

        return pattern_vel, pattern_notes

    def generate_pad(self, length=16, root=60):
        """Generate pad pattern - long sustained chords."""
        pattern_vel = np.zeros(length, dtype=np.float64)
        pattern_notes = np.full(length, root, dtype=int)

        # Pads typically hold for several steps
        scale_type = self.rules.get('scale', 'minor')
        notes = get_scale_notes(root % 12 + 48, scale_type, (48, 72))
        if not notes:
            notes = [root]

        # One or two chord changes per pattern
        changes = self.rng.choice([1, 2], p=[0.6, 0.4])
        if changes == 1:
            pattern_vel[0] = 0.5
            pattern_notes[0] = self.rng.choice(notes)
        else:
            pattern_vel[0] = 0.5
            pattern_notes[0] = self.rng.choice(notes)
            mid = length // 2
            pattern_vel[mid] = 0.5
            pattern_notes[mid] = self.rng.choice(notes)

        return pattern_vel, pattern_notes

    def generate_full_pattern(self, length=16, root_note=36):
        """Generate a complete pattern for all tracks."""
        result = {}

        # Drums
        result['kick'] = {'velocities': self.generate_kick(length)}
        result['snare'] = {'velocities': self.generate_snare(length)}
        result['clap'] = {'velocities': self.generate_clap(length)}
        result['closed_hat'] = {'velocities': self.generate_closed_hat(length)}
        result['open_hat'] = {'velocities': self.generate_open_hat(length)}

        # Occasional toms and rimshot
        tom_pattern = np.zeros(length, dtype=np.float64)
        if self.rng.random() < 0.3:
            for i in range(length):
                if self.rng.random() < 0.1:
                    tom_pattern[i] = 0.6
        result['tom_lo'] = {'velocities': tom_pattern}
        result['tom_hi'] = {'velocities': np.zeros(length, dtype=np.float64)}
        result['rimshot'] = {'velocities': np.zeros(length, dtype=np.float64)}

        # Bass
        bass_vel, bass_notes, bass_acc, bass_glide = self.generate_bass(length, root_note)
        result['bass'] = {
            'velocities': bass_vel,
            'notes': bass_notes,
            'accents': bass_acc,
            'glides': bass_glide,
        }

        # Lead
        lead_vel, lead_notes = self.generate_lead(length, root_note + 24)
        result['lead'] = {'velocities': lead_vel, 'notes': lead_notes}

        # Pad
        pad_vel, pad_notes = self.generate_pad(length, root_note + 24)
        result['pad'] = {'velocities': pad_vel, 'notes': pad_notes}

        return result
