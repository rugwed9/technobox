#!/usr/bin/env python3
"""
TechnoBox Beat Maker v3 - Full creative toolkit.

10 instruments, sound presets, vocal chops, chord stabs, percussion,
mute/solo, swing, sidechain, delay. No genres - just tools to create.

Controls:
  a s d f g h j k     = toggle steps 1-8
  z x c v b n m ,     = toggle steps 9-16
  TAB / `              = next / prev track
  SPACE                = play / stop
  + / -                = BPM up / down
  LEFT / RIGHT         = change sound preset for instrument
  UP / DOWN            = change note (melodic) or track (drums)
  [ / ]                = octave down / up
  G                    = AI auto-fill track
  C                    = clear track
  R                    = randomize / humanize
  < / >                = shift pattern left / right
  S                    = cycle swing (0 > 10 > 20 > 30 > 0)
  M                    = mute / unmute track
  O                    = solo / unsolo track
  E                    = export WAV
  Q                    = quit
"""
import sys
import os
import time
import wave
import tty
import termios
import datetime
import numpy as np
import sounddevice as sd

SR = 48000
BLOCK = 2048


# ======================== SYNTH ENGINE ========================

class Kick:
    def __init__(self):
        self.phase = 0.0; self.t = 0; self.active = False
        self.pitch = 50; self.pitch_amt = 200; self.pitch_decay = 0.04
        self.decay = 0.5; self.drive = 2.0; self.click = 0.3

    def trigger(self, vel=1.0):
        self.phase = 0; self.t = 0; self.active = True; self._v = vel

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        freq = self.pitch + self.pitch_amt * np.exp(-t / self.pitch_decay)
        ph = self.phase + np.cumsum(freq / SR); self.phase = ph[-1]
        sig = np.sin(2 * np.pi * ph)
        sig += np.random.randn(n) * np.exp(-t / 0.005) * self.click
        sig = np.tanh(sig * np.exp(-t / self.decay) * self._v * self.drive)
        if np.exp(-t[-1] / self.decay) < 0.001: self.active = False
        return sig


class Snare:
    def __init__(self):
        self.t = 0; self.active = False
        self.pitch = 200; self.tone = 0.4; self.decay = 0.15; self.snappy = 0.5

    def trigger(self, vel=1.0):
        self.t = 0; self.active = True; self._v = vel

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        body = np.sin(2 * np.pi * np.cumsum(self.pitch * (1 + 0.5 * np.exp(-t / 0.01)) / SR))
        body *= np.exp(-t / (self.decay * 0.7))
        noise = np.random.randn(n) * np.exp(-t / (self.decay * (0.4 + self.snappy * 0.6)))
        sig = body * self.tone + noise * (0.6 + (1 - self.tone) * 0.4)
        if t[-1] > self.decay * 5: self.active = False
        return sig * self._v


class Clap:
    def __init__(self):
        self.t = 0; self.active = False
        self.decay = 0.12; self.spread = 0.015

    def trigger(self, vel=1.0):
        self.t = 0; self.active = True; self._v = vel

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        noise = np.random.randn(n)
        offsets = [0, self.spread * 0.7, self.spread * 1.3, self.spread * 2.3]
        env = sum(((t >= o) & (t < o + 0.005)).astype(float) * np.exp(-(t - o) / 0.002) * 0.5
                  for o in offsets)
        env += np.exp(-t / self.decay) * 0.3
        if t[-1] > self.decay * 5: self.active = False
        return noise * env * self._v


class HiHat:
    def __init__(self):
        self.t = 0; self.active = False; self._decay = 0.05
        self.tone = 0.5
        self.freqs = [205.3, 369.6, 304.4, 522.7, 540.0, 800.0]

    def trigger(self, vel=1.0, is_open=False):
        self.t = 0; self.active = True; self._v = vel
        self._decay = 0.25 if is_open else max(0.02, 0.03 + self.tone * 0.04)

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        metal = sum(np.sign(np.sin(2 * np.pi * f * t)) for f in self.freqs) / len(self.freqs)
        metal_amt = 0.3 + (1 - self.tone) * 0.5
        noise_amt = 0.3 + self.tone * 0.4
        sig = (metal * metal_amt + np.random.randn(n) * noise_amt)
        sig *= np.exp(-t / self._decay) * self._v * 0.4
        if t[-1] > self._decay * 8: self.active = False
        return sig


class Perc:
    """Versatile percussion: shaker, tamb, conga, rim, cowbell."""
    SOUNDS = ['shaker', 'tamb', 'conga', 'rim', 'cowbell']

    def __init__(self):
        self.t = 0; self.active = False; self.sound_idx = 0

    def trigger(self, vel=1.0):
        self.t = 0; self.active = True; self._v = vel

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        s = self.SOUNDS[self.sound_idx % len(self.SOUNDS)]
        if s == 'shaker':
            sig = np.random.randn(n) * np.exp(-t / 0.03) * 0.4
        elif s == 'tamb':
            ring = np.sin(2 * np.pi * 5500 * t) * 0.3 + np.sin(2 * np.pi * 8200 * t) * 0.2
            sig = (ring + np.random.randn(n) * 0.5) * np.exp(-t / 0.07) * 0.35
        elif s == 'conga':
            freq = 200 * (1 + 2 * np.exp(-t / 0.01))
            sig = np.sin(2 * np.pi * np.cumsum(freq / SR)) * np.exp(-t / 0.15) * 0.5
            sig += np.random.randn(n) * np.exp(-t / 0.02) * 0.15
        elif s == 'rim':
            sig = np.sin(2 * np.pi * 800 * t) * np.exp(-t / 0.03) * 0.5
            sig += np.random.randn(n) * np.exp(-t / 0.005) * 0.4
        elif s == 'cowbell':
            sig = (np.sign(np.sin(2 * np.pi * 545 * t)) + np.sign(np.sin(2 * np.pi * 815 * t)))
            sig = sig * 0.25 * np.exp(-t / 0.1)
        else:
            sig = np.zeros(n)
        cutoffs = {'shaker': 0.2, 'tamb': 0.4, 'conga': 0.8, 'rim': 0.15, 'cowbell': 0.5}
        if t[-1] > cutoffs.get(s, 0.5): self.active = False
        return sig * self._v


class Bass:
    def __init__(self):
        self.phase = 0; self.freq = 55; self.t = 0; self.active = False; self._lp = 0
        self.waveform = 'saw'; self.cutoff = 800; self.env_mod = 3000
        self.drive = 1.5; self.decay = 0.3

    def trigger(self, note, vel=1.0):
        self.freq = 440 * 2 ** ((note - 69) / 12)
        self.phase = 0; self.t = 0; self.active = True; self._v = vel

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        dt = self.freq / SR
        ph = (self.phase + np.arange(n) * dt) % 1; self.phase = (self.phase + n * dt) % 1
        osc = np.where(ph < 0.5, 1.0, -1.0) if self.waveform == 'square' else (2 * ph - 1)
        sub = np.sin(2 * np.pi * (np.arange(n) * dt * 0.5) % 1) * 0.3
        sig = osc * 0.7 + sub
        fc = np.clip(self.cutoff + np.exp(-t / 0.15) * self.env_mod, 20, SR * 0.45)
        alpha = 1 - np.exp(-2 * np.pi * fc / SR)
        out = np.zeros(n); lp = self._lp
        for i in range(n): lp += alpha[i] * (sig[i] - lp); out[i] = lp
        self._lp = lp
        out = np.tanh(out * np.exp(-t / self.decay) * self._v * self.drive)
        if np.exp(-t[-1] / self.decay) < 0.001: self.active = False
        return out


class Lead:
    def __init__(self):
        self.phase = 0; self.freq = 440; self.t = 0; self.active = False; self._lp = 0
        self.detune = 1.005; self.decay = 0.4

    def trigger(self, note, vel=0.6):
        self.freq = 440 * 2 ** ((note - 69) / 12)
        self.t = 0; self.active = True; self._v = vel; self.phase = 0

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        dt = self.freq / SR
        ph1 = (self.phase + np.arange(n) * dt) % 1
        ph2 = (self.phase + np.arange(n) * dt * self.detune) % 1
        self.phase = (self.phase + n * dt) % 1
        osc = (2 * ph1 - 1) * 0.5 + (2 * ph2 - 1) * 0.5
        fc = 2000 + 3000 * np.exp(-t / 0.2)
        alpha = 1 - np.exp(-2 * np.pi * fc / SR)
        out = np.zeros(n); lp = self._lp
        for i in range(n): lp += alpha[i] * (osc[i] - lp); out[i] = lp
        self._lp = lp
        out *= np.exp(-t / self.decay) * self._v
        if np.exp(-t[-1] / self.decay) < 0.001: self.active = False
        return out


class VocalChop:
    """Formant synthesis vocal chop - creates vowel sounds like 'ah', 'ee', 'oh'."""
    VOWELS = [
        ('ah', [(730, 90), (1090, 110), (2440, 170)]),
        ('ee', [(270, 60), (2290, 200), (3010, 300)]),
        ('oh', [(570, 80), (840, 100), (2410, 170)]),
        ('oo', [(300, 70), (870, 100), (2240, 170)]),
        ('eh', [(530, 60), (1840, 150), (2480, 200)]),
    ]

    def __init__(self):
        self.t = 0; self.active = False; self.pitch = 220
        self.vowel_idx = 0; self.decay = 0.2
        self._harmonics = []

    def trigger(self, note, vel=1.0):
        self.pitch = 440 * 2 ** ((note - 69) / 12)
        self.t = 0; self.active = True; self._v = vel
        # Precompute harmonic amplitudes shaped by formant curve
        _, formants = self.VOWELS[self.vowel_idx % len(self.VOWELS)]
        self._harmonics = []
        for h in range(1, 30):
            freq = self.pitch * h
            if freq > 16000: break
            amp = sum(np.exp(-((freq - fc) ** 2) / (2 * (bw * 1.5) ** 2)) for fc, bw in formants)
            if amp > 0.01:
                self._harmonics.append((freq, amp / (h ** 0.5)))

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        sig = np.zeros(n)
        for freq, amp in self._harmonics:
            sig += np.sin(2 * np.pi * freq * t) * amp
        # Add breathiness
        sig = sig * 0.7 + np.random.randn(n) * 0.12
        sig *= np.exp(-t / self.decay) * self._v * 0.5
        if t[-1] > self.decay * 5: self.active = False
        return sig


class ChordStab:
    """Chord stab synth - plays multiple notes with filter sweep."""
    CHORD_TYPES = [
        ('minor', [0, 3, 7]),
        ('major', [0, 4, 7]),
        ('min7', [0, 3, 7, 10]),
        ('maj7', [0, 4, 7, 11]),
        ('sus4', [0, 5, 7]),
    ]

    def __init__(self):
        self.t = 0; self.active = False; self.chord_idx = 0
        self.phases = [0.0] * 4; self._lp = 0.0
        self.cutoff = 3000; self.decay = 0.25; self.root = 60

    def trigger(self, root, vel=1.0):
        self.root = root
        self.t = 0; self.active = True; self._v = vel
        self.phases = [0.0] * 4; self._lp = 0.0

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        _, intervals = self.CHORD_TYPES[self.chord_idx % len(self.CHORD_TYPES)]
        sig = np.zeros(n)
        for i, iv in enumerate(intervals):
            freq = 440 * 2 ** ((self.root + iv - 69) / 12)
            dt = freq / SR
            ph = (self.phases[i] + np.arange(n) * dt) % 1
            self.phases[i] = float((self.phases[i] + n * dt) % 1)
            sig += (2 * ph - 1) / len(intervals)
        fc = np.clip(self.cutoff * np.exp(-t / 0.08) + 200, 100, SR * 0.45)
        alpha = 1 - np.exp(-2 * np.pi * fc / SR)
        out = np.zeros(n); lp = self._lp
        for i in range(n): lp += alpha[i] * (sig[i] - lp); out[i] = lp
        self._lp = lp
        out *= np.exp(-t / self.decay) * self._v * 0.6
        if t[-1] > self.decay * 5: self.active = False
        return out


# ======================== EFFECTS ========================

class Sidechain:
    def __init__(self):
        self.env = 0.0; self.amount = 0.5; self.release = 0.15
        self._last_curve = None

    def trigger(self):
        self.env = 1.0

    def compute(self, n):
        if n == 0 or self.env < 0.001:
            self._last_curve = None; return
        coeff = np.exp(-1.0 / (self.release * SR))
        env_curve = self.env * (coeff ** np.arange(n))
        self.env = float(env_curve[-1])
        self._last_curve = 1.0 - env_curve * self.amount

    def apply(self, block):
        if self._last_curve is None: return block
        return block * self._last_curve


class SimpleDelay:
    def __init__(self):
        self.buf = np.zeros(SR * 2); self.write_pos = 0
        self.delay_samples = int(SR * 0.375)
        self.feedback = 0.3; self.mix = 0.15

    def set_tempo(self, bpm):
        self.delay_samples = max(1, int(SR * 60.0 / bpm * 0.75))

    def process(self, block):
        n = len(block)
        if n == 0 or self.mix < 0.01: return block
        buf_len = len(self.buf)
        rs = (self.write_pos - self.delay_samples) % buf_len
        if rs + n <= buf_len:
            delayed = self.buf[rs:rs + n].copy()
        else:
            p1 = buf_len - rs
            delayed = np.concatenate([self.buf[rs:], self.buf[:n - p1]])
        wd = block + delayed * self.feedback
        if self.write_pos + n <= buf_len:
            self.buf[self.write_pos:self.write_pos + n] = wd
        else:
            p1 = buf_len - self.write_pos
            self.buf[self.write_pos:] = wd[:p1]
            self.buf[:n - p1] = wd[p1:]
        self.write_pos = (self.write_pos + n) % buf_len
        return block + delayed * self.mix


# ======================== SOUND PRESETS ========================

KICK_PRESETS = [
    {'name': 'Deep', 'pitch': 48, 'pitch_amt': 160, 'pitch_decay': 0.05, 'decay': 0.6, 'drive': 1.8, 'click': 0.2},
    {'name': 'Hard', 'pitch': 55, 'pitch_amt': 250, 'pitch_decay': 0.03, 'decay': 0.35, 'drive': 3.5, 'click': 0.8},
    {'name': '808', 'pitch': 40, 'pitch_amt': 200, 'pitch_decay': 0.06, 'decay': 0.8, 'drive': 1.5, 'click': 0.1},
    {'name': 'Tight', 'pitch': 60, 'pitch_amt': 120, 'pitch_decay': 0.02, 'decay': 0.25, 'drive': 1.3, 'click': 0.5},
    {'name': 'Punchy', 'pitch': 52, 'pitch_amt': 220, 'pitch_decay': 0.03, 'decay': 0.4, 'drive': 2.5, 'click': 0.5},
    {'name': 'Sub', 'pitch': 42, 'pitch_amt': 180, 'pitch_decay': 0.05, 'decay': 0.7, 'drive': 1.3, 'click': 0.15},
]
SNARE_PRESETS = [
    {'name': 'Tight', 'pitch': 200, 'tone': 0.4, 'decay': 0.12, 'snappy': 0.5},
    {'name': 'Fat', 'pitch': 170, 'tone': 0.3, 'decay': 0.2, 'snappy': 0.6},
    {'name': 'Noisy', 'pitch': 180, 'tone': 0.15, 'decay': 0.15, 'snappy': 0.9},
    {'name': 'Tonal', 'pitch': 250, 'tone': 0.7, 'decay': 0.1, 'snappy': 0.2},
    {'name': 'Long', 'pitch': 190, 'tone': 0.35, 'decay': 0.25, 'snappy': 0.4},
]
CLAP_PRESETS = [
    {'name': 'Tight', 'decay': 0.08, 'spread': 0.01},
    {'name': 'Wide', 'decay': 0.15, 'spread': 0.02},
    {'name': 'Big', 'decay': 0.22, 'spread': 0.025},
]
HAT_PRESETS = [
    {'name': 'Bright', 'tone': 0.2},
    {'name': 'Medium', 'tone': 0.5},
    {'name': 'Dark', 'tone': 0.8},
    {'name': 'Crisp', 'tone': 0.1},
]
BASS_PRESETS = [
    {'name': 'Deep', 'waveform': 'saw', 'cutoff': 400, 'env_mod': 2000, 'drive': 1.3, 'decay': 0.35},
    {'name': 'Acid', 'waveform': 'square', 'cutoff': 500, 'env_mod': 6000, 'drive': 2.5, 'decay': 0.25},
    {'name': 'Sub', 'waveform': 'saw', 'cutoff': 200, 'env_mod': 800, 'drive': 1.0, 'decay': 0.4},
    {'name': 'Pluck', 'waveform': 'saw', 'cutoff': 800, 'env_mod': 4000, 'drive': 1.5, 'decay': 0.15},
    {'name': 'Growl', 'waveform': 'square', 'cutoff': 350, 'env_mod': 3500, 'drive': 3.0, 'decay': 0.3},
]
LEAD_PRESETS = [
    {'name': 'Sharp', 'detune': 1.005, 'decay': 0.35},
    {'name': 'Soft', 'detune': 1.002, 'decay': 0.5},
    {'name': 'Wide', 'detune': 1.01, 'decay': 0.4},
    {'name': 'Pluck', 'detune': 1.003, 'decay': 0.15},
]
VOX_PRESETS = [
    {'name': 'ah', 'vowel_idx': 0, 'decay': 0.2},
    {'name': 'ee', 'vowel_idx': 1, 'decay': 0.2},
    {'name': 'oh', 'vowel_idx': 2, 'decay': 0.2},
    {'name': 'oo', 'vowel_idx': 3, 'decay': 0.25},
    {'name': 'eh', 'vowel_idx': 4, 'decay': 0.2},
]
STAB_PRESETS = [
    {'name': 'minor', 'chord_idx': 0, 'cutoff': 3000, 'decay': 0.25},
    {'name': 'major', 'chord_idx': 1, 'cutoff': 3000, 'decay': 0.25},
    {'name': 'min7', 'chord_idx': 2, 'cutoff': 2500, 'decay': 0.3},
    {'name': 'maj7', 'chord_idx': 3, 'cutoff': 3500, 'decay': 0.3},
    {'name': 'sus4', 'chord_idx': 4, 'cutoff': 2800, 'decay': 0.2},
]

ALL_PRESETS = [
    KICK_PRESETS, SNARE_PRESETS, CLAP_PRESETS, HAT_PRESETS, HAT_PRESETS,
    [{'name': s} for s in Perc.SOUNDS],
    BASS_PRESETS, LEAD_PRESETS, VOX_PRESETS, STAB_PRESETS,
]

# Hidden genre presets (Shift+number still works)
GENRES = {
    'detroit': {
        'name': 'Detroit Techno', 'bpm': 128, 'swing': 0.0,
        'kick_cfg': {'pitch': 50, 'pitch_amt': 180, 'pitch_decay': 0.04, 'decay': 0.5, 'drive': 2.0, 'click': 0.3},
        'snare_cfg': {'pitch': 200, 'tone': 0.4, 'decay': 0.15, 'snappy': 0.5},
        'hat_cfg': {'tone': 0.5}, 'clap_cfg': {'decay': 0.12, 'spread': 0.015},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 600, 'env_mod': 2500, 'drive': 1.5, 'decay': 0.3},
        'volumes': [0.9, 0.6, 0.5, 0.35, 0.3, 0.0, 0.7, 0.5, 0.0, 0.0],
        'delay_mix': 0.15, 'sidechain_amt': 0.5,
        'patterns': [
            [.9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0],
            [0, 0, 0, 0, .8, 0, 0, 0, 0, 0, 0, 0, .8, 0, 0, 0],
            [0, 0, 0, 0, .7, 0, 0, 0, 0, 0, 0, 0, .7, 0, 0, 0],
            [0, 0, .7, 0, 0, 0, .7, 0, 0, 0, .7, 0, 0, 0, .7, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .6, 0, 0, 0, 0, 0],
            [0]*16, [.8,0,0,.7, 0,0,.8,0, .8,0,0,.7, 0,0,0,0], [0]*16, [0]*16, [0]*16,
        ],
        'bass_notes': [36,0,0,36, 0,0,43,0, 36,0,0,36, 0,0,0,0],
        'lead_notes': [0]*16, 'vox_notes': [60]*16, 'stab_notes': [60]*16,
    },
    'berlin': {
        'name': 'Berlin Hard Techno', 'bpm': 140, 'swing': 0.0,
        'kick_cfg': {'pitch': 55, 'pitch_amt': 250, 'pitch_decay': 0.03, 'decay': 0.35, 'drive': 3.5, 'click': 0.8},
        'snare_cfg': {'pitch': 180, 'tone': 0.2, 'decay': 0.12, 'snappy': 0.8},
        'hat_cfg': {'tone': 0.2}, 'clap_cfg': {'decay': 0.1, 'spread': 0.01},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 400, 'env_mod': 4000, 'drive': 2.8, 'decay': 0.25},
        'volumes': [0.95, 0.65, 0.6, 0.4, 0.35, 0.0, 0.75, 0.4, 0.0, 0.0],
        'delay_mix': 0.08, 'sidechain_amt': 0.7,
        'patterns': [
            [.9,0,0,0, .9,0,.7,0, .9,0,0,0, .9,0,0,.6],
            [0,0,0,0, 0,0,0,.7, 0,0,0,0, 0,0,.7,0],
            [0,0,0,0, .8,0,0,0, 0,0,0,0, .8,0,0,0],
            [.9,.4,.7,.4, .9,.4,.7,.4, .9,.4,.7,.4, .9,.4,.7,.4],
            [0,0,0,0, 0,0,.5,0, 0,0,0,0, 0,0,.5,0],
            [0]*16, [.8,0,.7,0, 0,0,.8,0, .8,0,0,.7, 0,0,.8,0], [0]*16, [0]*16, [0]*16,
        ],
        'bass_notes': [33,0,34,0, 0,0,33,0, 33,0,0,36, 0,0,33,0],
        'lead_notes': [0]*16, 'vox_notes': [60]*16, 'stab_notes': [60]*16,
    },
    'acid': {
        'name': 'Acid Techno', 'bpm': 138, 'swing': 0.05,
        'kick_cfg': {'pitch': 50, 'pitch_amt': 200, 'pitch_decay': 0.04, 'decay': 0.45, 'drive': 2.5, 'click': 0.4},
        'snare_cfg': {'pitch': 200, 'tone': 0.4, 'decay': 0.15, 'snappy': 0.5},
        'hat_cfg': {'tone': 0.4}, 'clap_cfg': {'decay': 0.12, 'spread': 0.015},
        'bass_cfg': {'waveform': 'square', 'cutoff': 500, 'env_mod': 6000, 'drive': 2.5, 'decay': 0.25},
        'volumes': [0.85, 0.55, 0.5, 0.35, 0.3, 0.0, 0.85, 0.4, 0.0, 0.0],
        'delay_mix': 0.22, 'sidechain_amt': 0.5,
        'patterns': [
            [.9,0,0,0, .9,0,0,.7, .9,0,0,0, .9,0,.7,0],
            [0,0,0,0, .8,0,0,0, 0,0,0,0, .8,0,0,0],
            [0,0,0,0, 0,0,0,0, .7,0,0,0, 0,0,0,0],
            [.8,0,.6,0, .8,0,.6,0, .8,0,.6,0, .8,0,.5,.4],
            [0,0,0,0, 0,0,0,0, 0,0,.5,0, 0,0,0,0],
            [0]*16, [.8,0,.7,.8, 0,.7,.8,0, .7,.8,0,.7, 0,.8,0,.7], [0]*16, [0]*16, [0]*16,
        ],
        'bass_notes': [36,0,39,41, 0,43,36,0, 39,36,0,43, 0,41,0,36],
        'lead_notes': [0]*16, 'vox_notes': [60]*16, 'stab_notes': [60]*16,
    },
    'minimal': {
        'name': 'Minimal Techno', 'bpm': 125, 'swing': 0.1,
        'kick_cfg': {'pitch': 65, 'pitch_amt': 100, 'pitch_decay': 0.02, 'decay': 0.25, 'drive': 1.3, 'click': 0.6},
        'snare_cfg': {'pitch': 220, 'tone': 0.6, 'decay': 0.08, 'snappy': 0.3},
        'hat_cfg': {'tone': 0.7}, 'clap_cfg': {'decay': 0.08, 'spread': 0.01},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 300, 'env_mod': 1200, 'drive': 1.2, 'decay': 0.25},
        'volumes': [0.8, 0.45, 0.4, 0.3, 0.25, 0.3, 0.6, 0.45, 0.0, 0.0],
        'delay_mix': 0.25, 'sidechain_amt': 0.3,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],
            [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,.6],
            [0,0,0,0, .6,0,0,0, 0,0,0,0, 0,0,0,0],
            [0,0,.5,0, 0,0,.5,0, 0,0,.5,0, 0,.3,.5,0],
            [0]*16,
            [0,0,0,0, 0,.4,0,0, 0,0,0,0, 0,0,.4,0],
            [.7,0,0,0, 0,0,0,0, .7,0,0,0, 0,0,.6,0],
            [0,0,.5,0, 0,0,0,0, 0,0,0,0, .5,0,0,0],
            [0]*16, [0]*16,
        ],
        'bass_notes': [36,0,0,0, 0,0,0,0, 43,0,0,0, 0,0,36,0],
        'lead_notes': [72,0,75,0, 0,0,0,0, 0,0,0,0, 77,0,0,0],
        'vox_notes': [60]*16, 'stab_notes': [60]*16,
        'perc_sound': 3,
    },
    'afro': {
        'name': 'Afro House', 'bpm': 122, 'swing': 0.22,
        'kick_cfg': {'pitch': 45, 'pitch_amt': 150, 'pitch_decay': 0.05, 'decay': 0.6, 'drive': 1.5, 'click': 0.15},
        'snare_cfg': {'pitch': 240, 'tone': 0.5, 'decay': 0.1, 'snappy': 0.4},
        'hat_cfg': {'tone': 0.6}, 'clap_cfg': {'decay': 0.1, 'spread': 0.012},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 250, 'env_mod': 800, 'drive': 1.0, 'decay': 0.35},
        'volumes': [0.85, 0.5, 0.4, 0.4, 0.3, 0.4, 0.65, 0.5, 0.35, 0.0],
        'delay_mix': 0.15, 'sidechain_amt': 0.35,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],
            [0,0,0,0, .8,0,0,.4, 0,0,0,0, .8,0,.4,0],
            [0]*16,
            [0,.6,0,.6, 0,.6,0,.6, 0,.6,0,.6, 0,.6,0,.6],
            [0]*16,
            [0,.5,0,0, 0,.5,0,0, 0,.5,0,0, 0,.5,0,0],
            [.7,0,0,0, 0,0,0,0, .7,0,0,0, 0,0,.6,0],
            [0,0,.5,0, 0,.5,0,0, .5,0,0,.5, 0,0,.5,0],
            [0,0,0,0, .5,0,0,0, 0,0,0,0, .5,0,0,0],
            [0]*16,
        ],
        'bass_notes': [36,0,0,0, 0,0,0,0, 43,0,0,0, 0,0,36,0],
        'lead_notes': [65,0,67,0, 0,65,0,0, 67,0,0,65, 0,0,67,0],
        'vox_notes': [65,0,0,0, 67,0,0,0, 0,0,0,0, 65,0,0,0],
        'stab_notes': [60]*16,
        'perc_sound': 0, 'vox_vowel': 0,
    },
    'melodic': {
        'name': 'Melodic Techno', 'bpm': 124, 'swing': 0.0,
        'kick_cfg': {'pitch': 52, 'pitch_amt': 170, 'pitch_decay': 0.04, 'decay': 0.4, 'drive': 1.8, 'click': 0.25},
        'snare_cfg': {'pitch': 200, 'tone': 0.5, 'decay': 0.18, 'snappy': 0.4},
        'hat_cfg': {'tone': 0.35}, 'clap_cfg': {'decay': 0.15, 'spread': 0.02},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 500, 'env_mod': 2000, 'drive': 1.3, 'decay': 0.3},
        'volumes': [0.85, 0.55, 0.45, 0.35, 0.3, 0.0, 0.65, 0.55, 0.0, 0.35],
        'delay_mix': 0.22, 'sidechain_amt': 0.45,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],
            [0,0,0,0, .7,0,0,0, 0,0,0,0, .7,0,0,0],
            [0]*16,
            [.9,.5,.7,.5, .9,.5,.7,.5, .9,.5,.7,.5, .9,.5,.7,.5],
            [0,0,0,0, 0,0,0,0, .5,0,0,0, 0,0,0,0],
            [0]*16,
            [.7,0,0,0, 0,0,.6,0, .7,0,0,0, 0,.5,0,0],
            [.5,0,0,.4, 0,0,.5,0, 0,.4,0,0, .5,0,0,.4],
            [0]*16,
            [.5,0,0,0, 0,0,0,0, .5,0,0,0, 0,0,.4,0],
        ],
        'bass_notes': [36,0,0,0, 0,0,43,0, 36,0,0,0, 0,41,0,0],
        'lead_notes': [72,0,0,70, 0,0,72,0, 0,75,0,0, 77,0,0,72],
        'vox_notes': [60]*16,
        'stab_notes': [60,0,0,0, 0,0,0,0, 63,0,0,0, 0,0,58,0],
        'stab_chord': 0,
    },
    'ukgarage': {
        'name': 'UK Garage / 2-Step', 'bpm': 132, 'swing': 0.25,
        'kick_cfg': {'pitch': 42, 'pitch_amt': 200, 'pitch_decay': 0.06, 'decay': 0.55, 'drive': 1.8, 'click': 0.15},
        'snare_cfg': {'pitch': 190, 'tone': 0.3, 'decay': 0.13, 'snappy': 0.6},
        'hat_cfg': {'tone': 0.4}, 'clap_cfg': {'decay': 0.1, 'spread': 0.012},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 700, 'env_mod': 2000, 'drive': 1.3, 'decay': 0.2},
        'volumes': [0.9, 0.6, 0.5, 0.4, 0.3, 0.35, 0.8, 0.0, 0.4, 0.45],
        'delay_mix': 0.1, 'sidechain_amt': 0.4,
        'patterns': [
            [.9,0,0,0, 0,0,.8,0, 0,.7,0,0, 0,0,.7,0],
            [0,0,0,0, .8,0,0,0, 0,0,0,0, .8,0,0,0],
            [0,0,0,0, .6,0,0,0, 0,0,0,0, .6,0,0,0],
            [0,.7,0,.7, 0,.7,0,.7, 0,.7,0,.7, 0,.7,0,.7],
            [0,0,0,0, 0,0,0,0, 0,0,.5,0, 0,0,0,0],
            [0,.4,0,0, 0,.4,0,0, 0,.4,0,0, 0,.4,0,0],
            [.8,0,0,.6, 0,.5,0,0, .7,0,.5,0, 0,0,.6,0],
            [0]*16,
            [.5,0,0,0, 0,0,.4,0, 0,0,0,0, .5,0,0,0],
            [.6,0,0,0, 0,0,0,0, .6,0,0,0, 0,0,.5,0],
        ],
        'bass_notes': [36,0,0,38, 0,41,0,0, 43,0,41,0, 0,0,38,0],
        'lead_notes': [0]*16,
        'vox_notes': [67,0,0,0, 0,0,65,0, 0,0,0,0, 67,0,0,0],
        'stab_notes': [60,0,0,0, 0,0,0,0, 63,0,0,0, 0,0,58,0],
        'perc_sound': 0, 'vox_vowel': 0, 'stab_chord': 2,
    },
    'trance': {
        'name': 'Uplifting Trance', 'bpm': 138, 'swing': 0.0,
        'kick_cfg': {'pitch': 50, 'pitch_amt': 220, 'pitch_decay': 0.035, 'decay': 0.5, 'drive': 2.2, 'click': 0.5},
        'snare_cfg': {'pitch': 200, 'tone': 0.3, 'decay': 0.2, 'snappy': 0.7},
        'hat_cfg': {'tone': 0.3}, 'clap_cfg': {'decay': 0.15, 'spread': 0.018},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 600, 'env_mod': 2500, 'drive': 1.5, 'decay': 0.2},
        'volumes': [0.9, 0.6, 0.5, 0.4, 0.35, 0.0, 0.7, 0.6, 0.0, 0.0],
        'delay_mix': 0.25, 'sidechain_amt': 0.6,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],
            [0,0,0,0, .8,0,0,0, 0,0,0,0, .8,0,0,0],
            [0]*16,
            [0,.7,0,.7, 0,.7,0,.7, 0,.7,0,.7, 0,.7,0,.7],
            [0]*16, [0]*16,
            [0,.8,0,0, 0,.8,0,0, 0,.8,0,0, 0,.8,0,0],
            [.5,0,.4,0, .5,0,.6,0, .5,0,.4,0, .6,0,.5,0],
            [0]*16, [0]*16,
        ],
        'bass_notes': [36,36,0,0, 0,36,0,0, 0,43,0,0, 0,41,0,0],
        'lead_notes': [72,0,75,0, 72,0,77,0, 75,0,72,0, 77,0,75,0],
        'vox_notes': [60]*16, 'stab_notes': [60]*16,
    },
    'deephouse': {
        'name': 'Deep House', 'bpm': 122, 'swing': 0.15,
        'kick_cfg': {'pitch': 48, 'pitch_amt': 160, 'pitch_decay': 0.05, 'decay': 0.55, 'drive': 1.5, 'click': 0.15},
        'snare_cfg': {'pitch': 210, 'tone': 0.5, 'decay': 0.12, 'snappy': 0.4},
        'hat_cfg': {'tone': 0.55}, 'clap_cfg': {'decay': 0.1, 'spread': 0.013},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 350, 'env_mod': 1500, 'drive': 1.1, 'decay': 0.35},
        'volumes': [0.85, 0.5, 0.4, 0.35, 0.35, 0.3, 0.75, 0.0, 0.0, 0.35],
        'delay_mix': 0.18, 'sidechain_amt': 0.35,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],
            [0,0,0,0, .7,0,0,.3, 0,0,0,0, .7,0,0,0],
            [0]*16,
            [.7,0,.6,.5, .7,0,.6,.5, .7,0,.6,.5, .7,0,.6,.5],
            [0,.5,0,0, 0,.5,0,0, 0,.5,0,0, 0,.5,0,0],
            [0,0,.4,0, 0,0,.4,0, 0,0,.4,0, 0,0,.4,0],
            [.8,0,0,0, .6,0,0,.5, .7,0,.5,0, 0,0,.6,0],
            [0]*16, [0]*16,
            [.5,0,0,0, 0,0,0,0, .5,0,0,0, 0,0,0,0],
        ],
        'bass_notes': [36,0,0,0, 43,0,0,41, 36,0,48,0, 0,0,43,0],
        'lead_notes': [0]*16, 'vox_notes': [60]*16,
        'stab_notes': [60,0,0,0, 0,0,0,0, 63,0,0,0, 0,0,0,0],
        'perc_sound': 0, 'stab_chord': 0,
    },
    'fredagain': {
        'name': 'Fred Again / Emotional', 'bpm': 128, 'swing': 0.1,
        'kick_cfg': {'pitch': 55, 'pitch_amt': 120, 'pitch_decay': 0.03, 'decay': 0.3, 'drive': 1.5, 'click': 0.25},
        'snare_cfg': {'pitch': 200, 'tone': 0.4, 'decay': 0.16, 'snappy': 0.5},
        'hat_cfg': {'tone': 0.6}, 'clap_cfg': {'decay': 0.13, 'spread': 0.015},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 500, 'env_mod': 1800, 'drive': 1.2, 'decay': 0.3},
        'volumes': [0.7, 0.55, 0.5, 0.35, 0.3, 0.0, 0.6, 0.55, 0.45, 0.0],
        'delay_mix': 0.2, 'sidechain_amt': 0.3,
        'patterns': [
            [.7,0,0,0, 0,0,.6,0, 0,.6,0,0, 0,0,0,0],
            [0,0,0,0, .7,0,0,0, 0,0,0,0, .7,0,0,0],
            [0,0,0,0, .6,0,0,0, 0,0,0,0, .6,0,0,.4],
            [0,.5,0,.5, 0,.5,0,.5, 0,.5,0,.5, 0,.5,0,.5],
            [0,0,0,0, 0,0,0,0, 0,0,.4,0, 0,0,0,0],
            [0]*16,
            [.6,0,0,.5, 0,0,0,0, .6,0,0,0, 0,.4,0,0],
            [.4,0,0,0, 0,.4,0,0, 0,0,.5,0, 0,0,0,.4],
            [.5,0,0,0, 0,0,.4,0, 0,.4,0,0, 0,0,0,.4],
            [0]*16,
        ],
        'bass_notes': [36,0,0,39, 0,0,0,0, 43,0,0,0, 0,41,0,0],
        'lead_notes': [72,0,0,0, 0,75,0,0, 0,0,77,0, 0,0,0,72],
        'vox_notes': [67,0,0,0, 0,0,65,0, 0,63,0,0, 0,0,0,65],
        'stab_notes': [60]*16,
        'vox_vowel': 0,
    },
}


# ======================== UI CONSTANTS ========================

TRACK_NAMES = ['KICK', 'SNARE', 'CLAP', 'C.HAT', 'O.HAT', 'PERC', 'BASS', 'LEAD', 'VOX', 'STAB']
TRACK_COLORS = [
    '\033[91m', '\033[93m', '\033[95m', '\033[96m', '\033[94m',
    '\033[33m', '\033[92m', '\033[97m', '\033[35m', '\033[36m',
]
RST = '\033[0m'; BLD = '\033[1m'; DIM = '\033[2m'
STEP_KEYS_TOP = 'asdfghjk'
STEP_KEYS_BOT = 'zxcvbnm,'
MELODIC_TRACKS = {6, 7, 8, 9}  # bass, lead, vox, stab


# ======================== BEAT MAKER ========================

class BeatMaker:
    def __init__(self):
        self.bpm = 128
        self.swing = 0.0
        self.patterns = [[0] * 16 for _ in range(10)]
        self.bass_notes = [36] * 16
        self.lead_notes = [60] * 16
        self.vox_notes = [60] * 16
        self.stab_notes = [60] * 16
        self.selected_track = 0
        self.playing = True
        self.running = True
        self.step = 0
        self.sample_pos = 0
        self._last_step = -1
        self.export_count = 0
        self.status_msg = ''
        self.status_time = 0

        # Sound variant indices
        self.variants = [0] * 10

        # Mute / Solo
        self.mutes = [False] * 10
        self.solo = -1  # -1 = no solo

        # Instruments
        self.kick = Kick()
        self.snare = Snare()
        self.clap = Clap()
        self.ch_hat = HiHat()
        self.oh_hat = HiHat()
        self.perc = Perc()
        self.bass = Bass()
        self.lead = Lead()
        self.vox = VocalChop()
        self.stab = ChordStab()
        self._instruments = [
            self.kick, self.snare, self.clap, self.ch_hat, self.oh_hat,
            self.perc, self.bass, self.lead, self.vox, self.stab,
        ]

        # Volumes
        self.volumes = [0.9, 0.6, 0.5, 0.35, 0.3, 0.35, 0.7, 0.5, 0.4, 0.4]

        # Effects
        self.sidechain = Sidechain()
        self.delay = SimpleDelay()
        self.delay.set_tempo(self.bpm)

    def _apply_variant(self, track, idx):
        """Apply a sound preset to an instrument."""
        presets = ALL_PRESETS[track]
        idx = idx % len(presets)
        self.variants[track] = idx
        p = presets[idx]
        inst = self._instruments[track]
        for k, v in p.items():
            if k != 'name' and hasattr(inst, k):
                setattr(inst, k, v)
        # Special cases
        if track == 5:  # PERC
            self.perc.sound_idx = idx
        elif track == 8:  # VOX
            self.vox.vowel_idx = p.get('vowel_idx', idx)
        elif track == 9:  # STAB
            self.stab.chord_idx = p.get('chord_idx', idx)
        self.status_msg = f'{TRACK_NAMES[track]}: {p["name"]}'
        self.status_time = time.time()

    def _get_variant_name(self, track):
        presets = ALL_PRESETS[track]
        return presets[self.variants[track] % len(presets)]['name']

    def _get_notes(self, track):
        if track == 6: return self.bass_notes
        if track == 7: return self.lead_notes
        if track == 8: return self.vox_notes
        if track == 9: return self.stab_notes
        return None

    def load_genre(self, genre_key):
        if genre_key not in GENRES: return
        g = GENRES[genre_key]
        self.bpm = g['bpm']; self.swing = g.get('swing', 0.0)
        for i in range(10):
            self.patterns[i] = [float(v) for v in g['patterns'][i]]
        self.bass_notes = list(g['bass_notes'])
        self.lead_notes = list(g['lead_notes'])
        self.vox_notes = list(g.get('vox_notes', [60] * 16))
        self.stab_notes = list(g.get('stab_notes', [60] * 16))
        for k, v in g.get('kick_cfg', {}).items():
            if hasattr(self.kick, k): setattr(self.kick, k, v)
        for k, v in g.get('snare_cfg', {}).items():
            if hasattr(self.snare, k): setattr(self.snare, k, v)
        for k, v in g.get('clap_cfg', {}).items():
            if hasattr(self.clap, k): setattr(self.clap, k, v)
        for k, v in g.get('hat_cfg', {}).items():
            if hasattr(self.ch_hat, k): setattr(self.ch_hat, k, v)
            if hasattr(self.oh_hat, k): setattr(self.oh_hat, k, v)
        for k, v in g.get('bass_cfg', {}).items():
            if hasattr(self.bass, k): setattr(self.bass, k, v)
        if 'perc_sound' in g: self.perc.sound_idx = g['perc_sound']
        if 'vox_vowel' in g: self.vox.vowel_idx = g['vox_vowel']
        if 'stab_chord' in g: self.stab.chord_idx = g['stab_chord']
        if 'volumes' in g: self.volumes = list(g['volumes'])
        self.delay.mix = g.get('delay_mix', 0.15)
        self.delay.set_tempo(self.bpm)
        self.sidechain.amount = g.get('sidechain_amt', 0.5)
        self.mutes = [False] * 10; self.solo = -1
        self.status_msg = f'Loaded {g["name"]}'
        self.status_time = time.time()

    @property
    def samples_per_step(self):
        return SR * 60.0 / self.bpm / 4

    def _get_swung_step(self, sample_pos):
        sps = self.samples_per_step
        pair_dur = sps * 2
        bar_pos = sample_pos % (16 * sps)
        pair_idx = int(bar_pos / pair_dur)
        within = bar_pos - pair_idx * pair_dur
        threshold = sps * (1.0 + self.swing)
        return pair_idx * 2 if within < threshold else pair_idx * 2 + 1

    def audio_callback(self, outdata, frames, time_info, status):
        if not self.playing:
            outdata.fill(0); return

        kick_hit = False
        for i in range(frames):
            s = self._get_swung_step(self.sample_pos + i)
            if s != self._last_step:
                self._last_step = s
                self.step = s % 16
                p = self.patterns; st = self.step
                if p[0][st]: self.kick.trigger(p[0][st]); kick_hit = True
                if p[1][st]: self.snare.trigger(p[1][st])
                if p[2][st]: self.clap.trigger(p[2][st])
                if p[3][st]: self.ch_hat.trigger(p[3][st])
                if p[4][st]: self.oh_hat.trigger(p[4][st], is_open=True)
                if p[5][st]: self.perc.trigger(p[5][st])
                if p[6][st]: self.bass.trigger(self.bass_notes[st], p[6][st])
                if p[7][st]: self.lead.trigger(self.lead_notes[st], p[7][st])
                if p[8][st]: self.vox.trigger(self.vox_notes[st], p[8][st])
                if p[9][st]: self.stab.trigger(self.stab_notes[st], p[9][st])
        self.sample_pos += frames

        # Only trigger sidechain if kick is audible
        if kick_hit and not self.mutes[0] and (self.solo < 0 or self.solo == 0):
            self.sidechain.trigger()

        # Render all instruments
        outs = [inst.render(frames) * self.volumes[i] for i, inst in enumerate(self._instruments)]

        # Sidechain on bass, lead, vox, stab
        self.sidechain.compute(frames)
        for i in (6, 7, 8, 9):
            outs[i] = self.sidechain.apply(outs[i])

        # Mute / Solo
        mix = np.zeros(frames, dtype=np.float64)
        for i, out in enumerate(outs):
            if self.mutes[i]: continue
            if self.solo >= 0 and i != self.solo: continue
            mix += out

        mix = self.delay.process(mix)
        mix = np.tanh(mix * 0.8)
        outdata[:, 0] = mix.astype(np.float32)
        outdata[:, 1] = mix.astype(np.float32)

    def toggle_step(self, step_idx):
        t = self.selected_track
        if self.patterns[t][step_idx] > 0:
            self.patterns[t][step_idx] = 0
        else:
            self.patterns[t][step_idx] = 0.8

    def clear_track(self):
        self.patterns[self.selected_track] = [0] * 16
        self.status_msg = f'Cleared {TRACK_NAMES[self.selected_track]}'
        self.status_time = time.time()

    def humanize(self):
        t = self.selected_track
        rng = np.random.default_rng()
        for i in range(16):
            if self.patterns[t][i] > 0:
                v = self.patterns[t][i] + rng.normal(0, 0.1)
                self.patterns[t][i] = float(np.clip(v, 0.2, 1.0))
        self.status_msg = f'Humanized {TRACK_NAMES[t]}'
        self.status_time = time.time()

    def shift_pattern(self, direction):
        t = self.selected_track
        p = self.patterns[t]
        if direction > 0:
            self.patterns[t] = [p[-1]] + p[:-1]
        else:
            self.patterns[t] = p[1:] + [p[0]]
        # Also shift notes for melodic tracks
        notes = self._get_notes(t)
        if notes:
            if direction > 0:
                notes[:] = [notes[-1]] + notes[:-1]
            else:
                notes[:] = notes[1:] + [notes[0]]
        self.status_msg = f'Shifted {TRACK_NAMES[t]} {"→" if direction > 0 else "←"}'
        self.status_time = time.time()

    def ai_fill(self):
        rng = np.random.default_rng()
        t = self.selected_track
        if t == 0:
            self.patterns[0] = [0.9,0,0,0, 0.9,0,0,0, 0.9,0,0,0, 0.9,0,0,0]
        elif t == 1:
            self.patterns[1] = [0,0,0,0, 0.8,0,0,0, 0,0,0,0, 0.8,0,0,0]
        elif t == 2:
            self.patterns[2] = [0,0,0,0, 0.7,0,0,0, 0,0,0,0, 0.7,0,0,0]
        elif t == 3:
            p = [0.0]*16
            for i in range(16):
                if i % 2 == 0: p[i] = 0.8
                elif rng.random() < 0.4: p[i] = 0.4
            self.patterns[3] = p
        elif t == 4:
            p = [0.0]*16
            for i in [2, 6, 10, 14]:
                if rng.random() < 0.4: p[i] = 0.6
            self.patterns[4] = p
        elif t == 5:
            p = [0.0]*16
            styles = [[0,.5,0,0]*4, [.5,0,.5,0]*4, [0,0,.5,0]*4]
            self.patterns[5] = list(rng.choice(styles))
        elif t == 6:
            p = [0.0]*16; notes = [36]*16
            scale = [36, 38, 39, 41, 43, 44, 46, 48]
            for i in range(16):
                if rng.random() < 0.5:
                    p[i] = 0.7 + rng.random()*0.3
                    notes[i] = int(rng.choice(scale))
            self.patterns[6] = p; self.bass_notes = notes
        elif t == 7:
            p = [0.0]*16; notes = [60]*16
            scale = [60, 62, 63, 65, 67, 68, 70, 72]
            for i in range(16):
                if rng.random() < 0.3:
                    p[i] = 0.6; notes[i] = int(rng.choice(scale))
            self.patterns[7] = p; self.lead_notes = notes
        elif t == 8:
            p = [0.0]*16; notes = [60]*16
            scale = [60, 63, 65, 67, 70, 72]
            for i in range(16):
                if rng.random() < 0.2:
                    p[i] = 0.6; notes[i] = int(rng.choice(scale))
            self.patterns[8] = p; self.vox_notes = notes
        elif t == 9:
            p = [0.0]*16; notes = [60]*16
            roots = [55, 58, 60, 63, 65]
            positions = [0, 4, 8, 12]
            for pos in positions:
                if rng.random() < 0.6:
                    p[pos] = 0.6; notes[pos] = int(rng.choice(roots))
            self.patterns[9] = p; self.stab_notes = notes
        self.status_msg = f'AI filled {TRACK_NAMES[t]}'
        self.status_time = time.time()

    def display(self):
        lines = []
        lines.append('')
        play = '\033[92m▶ PLAYING\033[0m' if self.playing else '\033[91m■ STOPPED\033[0m'
        lines.append(f'  {BLD}TECHNOBOX{RST}  BPM:{self.bpm}  {play}  Swing:{int(self.swing*100)}%')

        # Track info with variant name
        t = self.selected_track
        color = TRACK_COLORS[t]
        vname = self._get_variant_name(t)
        mute_str = ' \033[91mMUTED\033[0m' if self.mutes[t] else ''
        solo_str = ' \033[93mSOLO\033[0m' if self.solo == t else ''
        lines.append(f'  Track: {color}{BLD}{TRACK_NAMES[t]}{RST} [{vname}]{mute_str}{solo_str}  {DIM}← → change sound{RST}')
        lines.append('')

        # Step numbers
        nums = '  STEP '
        for i in range(16):
            if i == 8: nums += ' '
            nums += f'{i+1:>2} '
        lines.append(f'{DIM}{nums}{RST}')

        # Key hints
        keys = '  KEYS '
        for i, k in enumerate(list(STEP_KEYS_TOP) + list(STEP_KEYS_BOT)):
            if i == 8: keys += ' '
            keys += f' {k} '
        lines.append(f'{DIM}{keys}{RST}')
        lines.append(f'  {"─" * 58}')

        # Tracks
        for tr in range(10):
            c = TRACK_COLORS[tr]
            sel = '▸' if tr == self.selected_track else ' '
            name = f'{TRACK_NAMES[tr]:>5}'
            muted = self.mutes[tr] or (self.solo >= 0 and self.solo != tr)
            row = f'  {sel}{c}{BLD}{name}{RST} '
            for i in range(16):
                if i == 8: row += '│'
                v = self.patterns[tr][i]
                if muted:
                    row += f'{DIM} {"·" if v > 0 else "-"} {RST}'
                elif i == self.step and self.playing:
                    row += f'\033[7m{c}{" ■" if v > 0 else "  "} {RST}'
                elif v > 0:
                    sym = '■' if v > 0.7 else ('□' if v > 0.4 else '·')
                    row += f'{c} {sym} {RST}'
                else:
                    row += f'{DIM} - {RST}'
            # Show M/S indicators
            if self.mutes[tr]: row += f' {DIM}M{RST}'
            elif self.solo == tr: row += f' \033[93mS{RST}'
            lines.append(row)

        lines.append(f'  {"─" * 58}')

        # Note display for melodic tracks
        if t in MELODIC_TRACKS:
            note_names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
            notes = self._get_notes(t)
            pats = self.patterns[t]
            nr = '  NOTE '
            for i in range(16):
                if i == 8: nr += ' '
                if pats[i] > 0 and notes:
                    nr += f'{note_names[notes[i]%12]:>2} '
                else:
                    nr += '   '
            lines.append(f'{DIM}{nr}{RST}')

        lines.append('')
        lines.append(f'  {DIM}STEPS: a s d f g h j k | z x c v b n m ,{RST}')
        lines.append(f'  {DIM}TAB=track ←→=sound ↑↓=note/track []=octave{RST}')
        lines.append(f'  {DIM}G=fill C=clear R=random </>=shift S=swing M=mute O=solo{RST}')
        lines.append(f'  {DIM}E=export(#{self.export_count})  Q=quit{RST}')

        if self.status_msg and time.time() - self.status_time < 3:
            lines.append(f'  \033[93m{self.status_msg}{RST}')
        else:
            lines.append('')

        sys.stdout.write('\033[H' + '\n'.join(lines) + '\n' * 2)
        sys.stdout.flush()

    def handle_key(self, ch):
        if ch in STEP_KEYS_TOP:
            self.toggle_step(STEP_KEYS_TOP.index(ch))
        elif ch in STEP_KEYS_BOT:
            self.toggle_step(STEP_KEYS_BOT.index(ch) + 8)
        elif ch == '\t':
            self.selected_track = (self.selected_track + 1) % 10
        elif ch == '`':
            self.selected_track = (self.selected_track - 1) % 10
        elif ch == ' ':
            self.playing = not self.playing
            if not self.playing: self.sample_pos = 0; self._last_step = -1
        elif ch in ('+', '='):
            self.bpm = min(200, self.bpm + 2); self.delay.set_tempo(self.bpm)
        elif ch in ('-', '_'):
            self.bpm = max(80, self.bpm - 2); self.delay.set_tempo(self.bpm)
        elif ch == 'G': self.ai_fill()
        elif ch == 'C': self.clear_track()
        elif ch == 'R': self.humanize()
        elif ch == 'S':
            swings = [0.0, 0.10, 0.20, 0.30]
            cur = min(swings, key=lambda x: abs(x - self.swing))
            idx = (swings.index(cur) + 1) % len(swings)
            self.swing = swings[idx]
            self.status_msg = f'Swing: {int(self.swing*100)}%'
            self.status_time = time.time()
        elif ch == 'M':
            t = self.selected_track
            self.mutes[t] = not self.mutes[t]
            self.status_msg = f'{TRACK_NAMES[t]} {"muted" if self.mutes[t] else "unmuted"}'
            self.status_time = time.time()
        elif ch == 'O':
            t = self.selected_track
            self.solo = -1 if self.solo == t else t
            self.status_msg = f'{TRACK_NAMES[t]} {"soloed" if self.solo == t else "unsolo"}'
            self.status_time = time.time()
        elif ch == '<':
            self.shift_pattern(-1)
        elif ch == '>':
            self.shift_pattern(1)
        elif ch == '[':
            notes = self._get_notes(self.selected_track)
            if notes: notes[:] = [max(24, n - 12) for n in notes]
        elif ch == ']':
            notes = self._get_notes(self.selected_track)
            if notes: notes[:] = [min(96, n + 12) for n in notes]
        # Hidden genre hotkeys
        elif ch == '!': self.load_genre('detroit')
        elif ch == '@': self.load_genre('berlin')
        elif ch == '#': self.load_genre('acid')
        elif ch == '$': self.load_genre('minimal')
        elif ch == '%': self.load_genre('afro')
        elif ch == '^': self.load_genre('melodic')
        elif ch == '&': self.load_genre('ukgarage')
        elif ch == '*': self.load_genre('trance')
        elif ch == '(': self.load_genre('deephouse')
        elif ch == ')': self.load_genre('fredagain')
        elif ch == 'E': return 'export'
        elif ch in ('Q', 'q'): return 'quit'
        return None

    def _handle_arrow(self, direction):
        """Handle arrow keys: direction is 'up','down','left','right'."""
        t = self.selected_track
        if direction == 'up':
            if t in MELODIC_TRACKS:
                notes = self._get_notes(t)
                if notes: notes[self.step] = min(96, notes[self.step] + 1)
            else:
                self.selected_track = max(0, t - 1)
        elif direction == 'down':
            if t in MELODIC_TRACKS:
                notes = self._get_notes(t)
                if notes: notes[self.step] = max(24, notes[self.step] - 1)
            else:
                self.selected_track = min(9, t + 1)
        elif direction == 'left':
            presets = ALL_PRESETS[t]
            self._apply_variant(t, (self.variants[t] - 1) % len(presets))
        elif direction == 'right':
            presets = ALL_PRESETS[t]
            self._apply_variant(t, (self.variants[t] + 1) % len(presets))

    def export(self):
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        filename = os.path.expanduser(f'~/technobox/exports/beat_{ts}.wav')
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        self.status_msg = 'Exporting 8 bars...'; self.status_time = time.time()
        self.display()

        bars = 8
        sps = self.samples_per_step
        total = int(16 * bars * sps)
        audio = np.zeros(total, dtype=np.float64)

        # Fresh instruments with same configs
        insts = [Kick(), Snare(), Clap(), HiHat(), HiHat(), Perc(), Bass(), Lead(), VocalChop(), ChordStab()]
        src = self._instruments
        for attr in ('pitch','pitch_amt','pitch_decay','decay','drive','click'):
            if hasattr(src[0], attr): setattr(insts[0], attr, getattr(src[0], attr))
        for attr in ('pitch','tone','decay','snappy'):
            if hasattr(src[1], attr): setattr(insts[1], attr, getattr(src[1], attr))
        for attr in ('decay','spread'):
            setattr(insts[2], attr, getattr(src[2], attr))
        insts[3].tone = self.ch_hat.tone; insts[4].tone = self.oh_hat.tone
        insts[5].sound_idx = self.perc.sound_idx
        for attr in ('waveform','cutoff','env_mod','drive','decay'):
            setattr(insts[6], attr, getattr(src[6], attr))
        for attr in ('detune','decay'):
            setattr(insts[7], attr, getattr(src[7], attr))
        insts[8].vowel_idx = self.vox.vowel_idx; insts[8].decay = self.vox.decay
        insts[9].chord_idx = self.stab.chord_idx; insts[9].cutoff = self.stab.cutoff; insts[9].decay = self.stab.decay

        sc = Sidechain(); sc.amount = self.sidechain.amount; sc.release = self.sidechain.release
        dl = SimpleDelay(); dl.mix = self.delay.mix; dl.feedback = self.delay.feedback; dl.set_tempo(self.bpm)

        pos = 0; last_step = -1; block = 2048
        note_arrays = [None,None,None,None,None,None, self.bass_notes, self.lead_notes, self.vox_notes, self.stab_notes]

        while pos < total:
            bs = min(block, total - pos)
            kick_hit = False
            for i in range(bs):
                sp = pos + i
                pair_dur = sps * 2
                bar_pos = sp % (16 * sps)
                pi = int(bar_pos / pair_dur)
                within = bar_pos - pi * pair_dur
                s = pi * 2 if within < sps * (1.0 + self.swing) else pi * 2 + 1
                if s != last_step:
                    last_step = s; st = s % 16
                    if self.patterns[0][st]: insts[0].trigger(self.patterns[0][st]); kick_hit = True
                    if self.patterns[1][st]: insts[1].trigger(self.patterns[1][st])
                    if self.patterns[2][st]: insts[2].trigger(self.patterns[2][st])
                    if self.patterns[3][st]: insts[3].trigger(self.patterns[3][st])
                    if self.patterns[4][st]: insts[4].trigger(self.patterns[4][st], is_open=True)
                    if self.patterns[5][st]: insts[5].trigger(self.patterns[5][st])
                    if self.patterns[6][st]: insts[6].trigger(self.bass_notes[st], self.patterns[6][st])
                    if self.patterns[7][st]: insts[7].trigger(self.lead_notes[st], self.patterns[7][st])
                    if self.patterns[8][st]: insts[8].trigger(self.vox_notes[st], self.patterns[8][st])
                    if self.patterns[9][st]: insts[9].trigger(self.stab_notes[st], self.patterns[9][st])

            if kick_hit: sc.trigger()
            outs = [inst.render(bs) * self.volumes[i] for i, inst in enumerate(insts)]
            sc.compute(bs)
            for i in (6,7,8,9): outs[i] = sc.apply(outs[i])
            mix = sum(outs[i] for i in range(10) if not self.mutes[i] and (self.solo < 0 or self.solo == i))
            mix = dl.process(mix)
            mix = np.tanh(mix * 0.8)
            audio[pos:pos+bs] = mix
            pos += bs

        peak = np.abs(audio).max()
        if peak > 0: audio = audio / peak * 0.92
        stereo = np.column_stack([audio, audio])
        data = (stereo * 32767).astype(np.int16)
        with wave.open(filename, 'w') as wf:
            wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(SR)
            wf.writeframes(data.tobytes())

        self.export_count += 1
        size = os.path.getsize(filename) / 1024 / 1024
        self.status_msg = f'Export #{self.export_count}: {os.path.basename(filename)} ({size:.1f}MB)'
        self.status_time = time.time()

    def run(self):
        sys.stdout.write('\033[2J\033[H'); sys.stdout.flush()
        stream = sd.OutputStream(samplerate=SR, blocksize=BLOCK, channels=2,
                                 dtype='float32', callback=self.audio_callback, latency='low')
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            stream.start()
            while self.running:
                self.display()
                import select
                if select.select([sys.stdin], [], [], 0.04)[0]:
                    ch = sys.stdin.read(1)
                    if ch == '\x1b':
                        if select.select([sys.stdin], [], [], 0.01)[0]:
                            ch2 = sys.stdin.read(1)
                            if ch2 == '[':
                                ch3 = sys.stdin.read(1)
                                if ch3 == 'A': self._handle_arrow('up')
                                elif ch3 == 'B': self._handle_arrow('down')
                                elif ch3 == 'C': self._handle_arrow('right')
                                elif ch3 == 'D': self._handle_arrow('left')
                                elif ch3 == 'Z': self.selected_track = (self.selected_track - 1) % 10
                        continue
                    result = self.handle_key(ch)
                    if result == 'quit': self.running = False
                    elif result == 'export': self.export()
            stream.stop()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            sys.stdout.write('\033[?25h')
            print('\n  Bye!\n')


if __name__ == '__main__':
    BeatMaker().run()
