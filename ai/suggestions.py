import numpy as np


class SuggestionEngine:
    """Context-aware suggestions for improving patterns."""

    def __init__(self):
        self.rng = np.random.default_rng()
        self.suggestions = []

    def analyze_and_suggest(self, pattern, style_name):
        """Analyze current pattern and generate suggestions."""
        self.suggestions = []

        # Check kick pattern
        kick_track = pattern.tracks.get('kick')
        if kick_track:
            active_count = sum(1 for s in kick_track.steps if s.active)
            if active_count == 0:
                self.suggestions.append("Press G to auto-generate a pattern")
            elif active_count < 4:
                self.suggestions.append("Try adding kicks on beats 1,2,3,4 (steps 0,4,8,12)")
            elif active_count > 12:
                self.suggestions.append("Pattern is very busy - try removing some kicks for breathing room")

        # Check hat pattern
        hat_track = pattern.tracks.get('closed_hat')
        if hat_track:
            active_count = sum(1 for s in hat_track.steps if s.active)
            if active_count == 0 and kick_track and sum(1 for s in kick_track.steps if s.active) > 0:
                self.suggestions.append("Add hi-hats to drive the groove (Tab to hat track, Enter to add)")

        # Check bass
        bass_track = pattern.tracks.get('bass')
        if bass_track:
            active_count = sum(1 for s in bass_track.steps if s.active)
            if active_count == 0:
                self.suggestions.append("Add a bassline - try notes on beats with the kick")

        # Style-specific tips
        style_tips = {
            'detroit': [
                "Classic Detroit uses deep, rolling basslines with minimal hi-hat variation",
                "Try open hats on the offbeats for classic Detroit feel",
            ],
            'berlin': [
                "Berlin techno: crank up the kick drive for that industrial punch",
                "Try faster BPM (138-145) for authentic Berlin sound",
            ],
            'acid': [
                "Acid: increase bass resonance and add accents (A key) for squelch",
                "Add glides between bass notes for classic 303 sound",
                "Random patterns work great for acid - try pressing G",
            ],
            'minimal': [
                "Less is more - try removing hits instead of adding them",
                "Increase swing for a hypnotic minimal groove",
            ],
        }

        tips = style_tips.get(style_name, [])
        if tips:
            self.suggestions.append(self.rng.choice(tips))

        # General tips
        general = [
            "Use H to humanize velocities for a more organic feel",
            "Use R to create a random variation of current pattern",
            "Ctrl+E to export your beat as a WAV file",
            "Use [ and ] to switch between 8 pattern slots",
        ]
        if not self.suggestions:
            self.suggestions.append(self.rng.choice(general))

        return self.suggestions[:3]  # Max 3 suggestions
