import numpy as np
import json


class Step:
    """Single step in a pattern."""
    __slots__ = ['active', 'velocity', 'note', 'accent', 'glide']

    def __init__(self, active=False, velocity=0.8, note=36, accent=False, glide=False):
        self.active = active
        self.velocity = velocity
        self.note = note
        self.accent = accent
        self.glide = glide

    def to_dict(self):
        return {
            'active': self.active,
            'velocity': self.velocity,
            'note': self.note,
            'accent': self.accent,
            'glide': self.glide,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


class Track:
    """A single track (instrument lane) with step data."""

    def __init__(self, name, length=16, default_note=36):
        self.name = name
        self.length = length
        self.default_note = default_note
        self.steps = [Step(note=default_note) for _ in range(length)]
        self.muted = False
        self.solo = False
        self.volume = 0.8
        self.pan = 0.0

    def toggle_step(self, step_idx):
        if 0 <= step_idx < self.length:
            self.steps[step_idx].active = not self.steps[step_idx].active

    def set_step(self, step_idx, active=None, velocity=None, note=None, accent=None, glide=None):
        if 0 <= step_idx < self.length:
            s = self.steps[step_idx]
            if active is not None:
                s.active = active
            if velocity is not None:
                s.velocity = max(0.0, min(1.0, velocity))
            if note is not None:
                s.note = max(0, min(127, note))
            if accent is not None:
                s.accent = accent
            if glide is not None:
                s.glide = glide

    def clear(self):
        for s in self.steps:
            s.active = False
            s.velocity = 0.8
            s.accent = False
            s.glide = False

    def set_from_array(self, velocities):
        """Set pattern from a velocity array (0 = off, >0 = on with that velocity)."""
        for i, v in enumerate(velocities):
            if i < self.length:
                self.steps[i].active = v > 0
                self.steps[i].velocity = v if v > 0 else 0.8

    def to_dict(self):
        return {
            'name': self.name,
            'length': self.length,
            'default_note': self.default_note,
            'muted': self.muted,
            'volume': self.volume,
            'pan': self.pan,
            'steps': [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d):
        t = cls(d['name'], d['length'], d.get('default_note', 36))
        t.muted = d.get('muted', False)
        t.volume = d.get('volume', 0.8)
        t.pan = d.get('pan', 0.0)
        t.steps = [Step.from_dict(s) for s in d['steps']]
        return t


class Pattern:
    """A complete pattern with multiple tracks."""

    # Default track setup for techno
    DRUM_TRACKS = ['kick', 'snare', 'clap', 'closed_hat', 'open_hat', 'tom_lo', 'tom_hi', 'rimshot']
    SYNTH_TRACKS = ['bass', 'lead', 'pad']

    def __init__(self, name='Pattern 1', length=16):
        self.name = name
        self.length = length
        self.tracks = {}

        # Create drum tracks
        for drum in self.DRUM_TRACKS:
            self.tracks[drum] = Track(drum, length, default_note=36)

        # Create synth tracks with different default notes
        self.tracks['bass'] = Track('bass', length, default_note=36)  # C2
        self.tracks['lead'] = Track('lead', length, default_note=60)  # C4
        self.tracks['pad'] = Track('pad', length, default_note=60)    # C4

    def get_triggers_at_step(self, step_idx):
        """Get all active triggers at a given step. Returns dict of track_name -> Step."""
        triggers = {}
        has_solo = any(t.solo for t in self.tracks.values())

        for name, track in self.tracks.items():
            if track.muted:
                continue
            if has_solo and not track.solo:
                continue
            if 0 <= step_idx < track.length:
                step = track.steps[step_idx]
                if step.active:
                    triggers[name] = step
        return triggers

    @property
    def track_names(self):
        return list(self.tracks.keys())

    def to_dict(self):
        return {
            'name': self.name,
            'length': self.length,
            'tracks': {k: v.to_dict() for k, v in self.tracks.items()},
        }

    @classmethod
    def from_dict(cls, d):
        p = cls.__new__(cls)
        p.name = d['name']
        p.length = d['length']
        p.tracks = {k: Track.from_dict(v) for k, v in d['tracks'].items()}
        return p

    def to_json(self):
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_json(cls, s):
        return cls.from_dict(json.loads(s))
