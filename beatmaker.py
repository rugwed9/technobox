#!/usr/bin/env python3
"""
TechnoBox Beat Maker v2 - Every genre sounds DIFFERENT.

Major upgrade: per-genre kick/snare/hat/clap sound shaping, swing, sidechain,
tempo-synced delay. Each genre is its own sonic world.

Keys:
  a s d f g h j k = toggle steps 1-8
  z x c v b n m , = toggle steps 9-16
  TAB       = next track
  `         = prev track
  +/-       = BPM
  SPACE     = play/stop
  G         = AI fill current track
  C         = clear current track
  UP/DOWN   = change note (bass/lead) or change track
  [ / ]     = octave shift (bass/lead)
  E         = export WAV (multiple exports OK!)
  Q         = quit

Genres (Shift+Number):
  ! Detroit  @ Berlin  # Acid  $ Minimal  % Afro
  ^ Melodic  & UKGarage  * Trance  ( DeepHouse  ) FredAgain
"""
import sys
import os
import time
import wave
import tty
import termios
import threading
import datetime
import numpy as np
import sounddevice as sd

SR = 48000
BLOCK = 2048


# ======================== SYNTH ENGINE ========================

class Kick:
    """Configurable kick drum. pitch/decay/drive/click change character dramatically."""
    def __init__(self):
        self.phase = 0.0; self.t = 0; self.active = False
        # Tunable params - genres set these differently
        self.pitch = 50         # base freq (Hz) - lower=subby, higher=clicky
        self.pitch_amt = 200    # pitch sweep range - more=punchier attack
        self.pitch_decay = 0.04 # pitch sweep speed - shorter=snappier
        self.decay = 0.5        # amplitude decay - longer=boomy
        self.drive = 2.0        # saturation amount - more=harder
        self.click = 0.3        # transient click noise - more=attacky

    def trigger(self, vel=1.0):
        self.phase = 0; self.t = 0; self.active = True; self._v = vel

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        # Pitch sweep: high -> low
        freq = self.pitch + self.pitch_amt * np.exp(-t / self.pitch_decay)
        ph = self.phase + np.cumsum(freq / SR); self.phase = ph[-1]
        # Core sine body
        sig = np.sin(2 * np.pi * ph)
        # Click transient (noise burst)
        sig += np.random.randn(n) * np.exp(-t / 0.005) * self.click
        # Drive + amplitude envelope
        sig = np.tanh(sig * np.exp(-t / self.decay) * self._v * self.drive)
        if np.exp(-t[-1] / self.decay) < 0.001: self.active = False
        return sig


class Snare:
    """Configurable snare. pitch/tone/snappy control body vs noise balance."""
    def __init__(self):
        self.t = 0; self.active = False
        self.pitch = 200    # body frequency
        self.tone = 0.4     # 0=all noise, 1=more body
        self.decay = 0.15   # overall decay time
        self.snappy = 0.5   # noise tightness (0=loose, 1=tight crisp)

    def trigger(self, vel=1.0):
        self.t = 0; self.active = True; self._v = vel

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        # Pitched body
        body = np.sin(2 * np.pi * np.cumsum(self.pitch * (1 + 0.5 * np.exp(-t / 0.01)) / SR))
        body *= np.exp(-t / (self.decay * 0.7))
        # Noise component
        noise_decay = self.decay * (0.4 + self.snappy * 0.6)
        noise = np.random.randn(n) * np.exp(-t / noise_decay)
        # Mix body and noise
        sig = body * self.tone + noise * (0.6 + (1 - self.tone) * 0.4)
        if t[-1] > self.decay * 5: self.active = False
        return sig * self._v


class Clap:
    """Configurable clap. spread controls multi-burst timing, decay controls tail."""
    def __init__(self):
        self.t = 0; self.active = False
        self.decay = 0.12   # tail decay
        self.spread = 0.015 # timing spread of multi-burst

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
    """Configurable hi-hat. tone controls bright(0) vs dark(1), affects character."""
    def __init__(self):
        self.t = 0; self.active = False; self._decay = 0.05
        self.tone = 0.5  # 0=bright/metallic, 1=dark/soft
        self.freqs = [205.3, 369.6, 304.4, 522.7, 540.0, 800.0]

    def trigger(self, vel=1.0, is_open=False):
        self.t = 0; self.active = True; self._v = vel
        if is_open:
            self._decay = 0.25
        else:
            self._decay = max(0.02, 0.03 + self.tone * 0.04)

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        # Metallic ring from detuned square waves
        metal = sum(np.sign(np.sin(2 * np.pi * f * t)) for f in self.freqs) / len(self.freqs)
        # Mix metal vs noise based on tone
        metal_amt = 0.3 + (1 - self.tone) * 0.5  # bright = more metal
        noise_amt = 0.3 + self.tone * 0.4         # dark = more noise
        sig = (metal * metal_amt + np.random.randn(n) * noise_amt)
        sig *= np.exp(-t / self._decay) * self._v * 0.4
        if t[-1] > self._decay * 8: self.active = False
        return sig


class Bass:
    """Bass synth with filter envelope. waveform/cutoff/env_mod/drive shape the tone."""
    def __init__(self):
        self.phase = 0; self.freq = 55; self.t = 0; self.active = False; self._lp = 0
        self.waveform = 'saw'; self.cutoff = 800; self.env_mod = 3000; self.drive = 1.5
        self.decay = 0.3  # amplitude decay

    def trigger(self, note, vel=1.0):
        self.freq = 440 * 2 ** ((note - 69) / 12)
        self.phase = 0; self.t = 0; self.active = True; self._v = vel

    def render(self, n):
        if not self.active: return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR; self.t += n
        dt = self.freq / SR
        ph = (self.phase + np.arange(n) * dt) % 1; self.phase = (self.phase + n * dt) % 1
        # Oscillator
        if self.waveform == 'square':
            osc = np.where(ph < 0.5, 1.0, -1.0)
        else:
            osc = 2 * ph - 1
        # Sub oscillator
        sub = np.sin(2 * np.pi * (np.arange(n) * dt * 0.5) % 1) * 0.3
        sig = osc * 0.7 + sub
        # One-pole lowpass filter with envelope
        fc = np.clip(self.cutoff + np.exp(-t / 0.15) * self.env_mod, 20, SR * 0.45)
        alpha = 1 - np.exp(-2 * np.pi * fc / SR)
        out = np.zeros(n); lp = self._lp
        for i in range(n):
            lp += alpha[i] * (sig[i] - lp); out[i] = lp
        self._lp = lp
        out = np.tanh(out * np.exp(-t / self.decay) * self._v * self.drive)
        if np.exp(-t[-1] / self.decay) < 0.001: self.active = False
        return out


class Lead:
    """Dual-oscillator lead with filter."""
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
        # Filter
        fc = 2000 + 3000 * np.exp(-t / 0.2)
        alpha = 1 - np.exp(-2 * np.pi * fc / SR)
        out = np.zeros(n); lp = self._lp
        for i in range(n):
            lp += alpha[i] * (osc[i] - lp); out[i] = lp
        self._lp = lp
        out *= np.exp(-t / self.decay) * self._v
        if np.exp(-t[-1] / self.decay) < 0.001: self.active = False
        return out


# ======================== EFFECTS ========================

class Sidechain:
    """Ducks bass/lead when kick hits. Makes the mix pump and breathe."""
    def __init__(self):
        self.env = 0.0
        self.amount = 0.5     # 0=no duck, 1=full duck
        self.release = 0.15   # release time in seconds
        self._last_curve = None  # cached for applying to multiple tracks

    def trigger(self):
        self.env = 1.0

    def compute(self, n):
        """Compute the ducking curve for this block. Call once, apply to many."""
        if n == 0 or self.env < 0.001:
            self._last_curve = None
            return
        coeff = np.exp(-1.0 / (self.release * SR))
        env_curve = self.env * (coeff ** np.arange(n))
        self.env = float(env_curve[-1])
        self._last_curve = 1.0 - env_curve * self.amount

    def apply(self, block):
        """Apply the pre-computed ducking curve to a signal."""
        if self._last_curve is None:
            return block
        return block * self._last_curve


class SimpleDelay:
    """Tempo-synced delay. Adds space and depth."""
    def __init__(self, sr=SR):
        self.sr = sr
        self.buf = np.zeros(sr * 2)  # 2 sec max
        self.write_pos = 0
        self.delay_samples = int(sr * 0.375)
        self.feedback = 0.3
        self.mix = 0.15

    def set_tempo(self, bpm):
        """Sync delay to dotted eighth note."""
        self.delay_samples = int(self.sr * 60.0 / bpm * 0.75)

    def process(self, block):
        n = len(block)
        if n == 0 or self.mix < 0.01:
            return block
        buf_len = len(self.buf)
        # Read delayed samples
        read_start = (self.write_pos - self.delay_samples) % buf_len
        if read_start + n <= buf_len:
            delayed = self.buf[read_start:read_start + n].copy()
        else:
            part1 = buf_len - read_start
            delayed = np.concatenate([self.buf[read_start:], self.buf[:n - part1]])
        # Write input + feedback
        write_data = block + delayed * self.feedback
        if self.write_pos + n <= buf_len:
            self.buf[self.write_pos:self.write_pos + n] = write_data
        else:
            part1 = buf_len - self.write_pos
            self.buf[self.write_pos:] = write_data[:part1]
            self.buf[:n - part1] = write_data[part1:]
        self.write_pos = (self.write_pos + n) % buf_len
        return block + delayed * self.mix


# ======================== GENRE PRESETS ========================
# Each genre configures EVERY instrument differently for distinct sonic character.

GENRES = {
    'detroit': {
        'name': 'Detroit Techno', 'bpm': 128, 'swing': 0.0,
        'kick_cfg': {'pitch': 50, 'pitch_amt': 180, 'pitch_decay': 0.04, 'decay': 0.5, 'drive': 2.0, 'click': 0.3},
        'snare_cfg': {'pitch': 200, 'tone': 0.4, 'decay': 0.15, 'snappy': 0.5},
        'hat_cfg': {'tone': 0.5},
        'clap_cfg': {'decay': 0.12, 'spread': 0.015},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 600, 'env_mod': 2500, 'drive': 1.5, 'decay': 0.3},
        'volumes': [0.9, 0.6, 0.5, 0.35, 0.3, 0.7, 0.5],
        'delay_mix': 0.15, 'sidechain_amt': 0.5,
        'patterns': [
            [.9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0],     # kick
            [0, 0, 0, 0, .8, 0, 0, 0, 0, 0, 0, 0, .8, 0, 0, 0],         # snare
            [0, 0, 0, 0, .7, 0, 0, 0, 0, 0, 0, 0, .7, 0, 0, 0],         # clap
            [0, 0, .7, 0, 0, 0, .7, 0, 0, 0, .7, 0, 0, 0, .7, 0],       # ch hat
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .6, 0, 0, 0, 0, 0],          # oh hat
            [.8, 0, 0, .7, 0, 0, .8, 0, .8, 0, 0, .7, 0, 0, 0, 0],      # bass
            [0] * 16,                                                       # lead
        ],
        'bass_notes': [36, 0, 0, 36, 0, 0, 43, 0, 36, 0, 0, 36, 0, 0, 0, 0],
        'lead_notes': [0] * 16,
    },
    'berlin': {
        'name': 'Berlin Hard Techno', 'bpm': 140, 'swing': 0.0,
        'kick_cfg': {'pitch': 55, 'pitch_amt': 250, 'pitch_decay': 0.03, 'decay': 0.35, 'drive': 3.5, 'click': 0.8},
        'snare_cfg': {'pitch': 180, 'tone': 0.2, 'decay': 0.12, 'snappy': 0.8},
        'hat_cfg': {'tone': 0.2},  # bright, metallic
        'clap_cfg': {'decay': 0.1, 'spread': 0.01},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 400, 'env_mod': 4000, 'drive': 2.8, 'decay': 0.25},
        'volumes': [0.95, 0.65, 0.6, 0.4, 0.35, 0.75, 0.4],
        'delay_mix': 0.08, 'sidechain_amt': 0.7,
        'patterns': [
            [.9, 0, 0, 0, .9, 0, .7, 0, .9, 0, 0, 0, .9, 0, 0, .6],    # kick (extra hits)
            [0, 0, 0, 0, 0, 0, 0, .7, 0, 0, 0, 0, 0, 0, .7, 0],         # snare
            [0, 0, 0, 0, .8, 0, 0, 0, 0, 0, 0, 0, .8, 0, 0, 0],         # clap
            [.9, .4, .7, .4, .9, .4, .7, .4, .9, .4, .7, .4, .9, .4, .7, .4],  # ch hat (relentless)
            [0, 0, 0, 0, 0, 0, .5, 0, 0, 0, 0, 0, 0, 0, .5, 0],         # oh hat
            [.8, 0, .7, 0, 0, 0, .8, 0, .8, 0, 0, .7, 0, 0, .8, 0],     # bass
            [0] * 16,
        ],
        'bass_notes': [33, 0, 34, 0, 0, 0, 33, 0, 33, 0, 0, 36, 0, 0, 33, 0],
        'lead_notes': [0] * 16,
    },
    'acid': {
        'name': 'Acid Techno', 'bpm': 138, 'swing': 0.05,
        'kick_cfg': {'pitch': 50, 'pitch_amt': 200, 'pitch_decay': 0.04, 'decay': 0.45, 'drive': 2.5, 'click': 0.4},
        'snare_cfg': {'pitch': 200, 'tone': 0.4, 'decay': 0.15, 'snappy': 0.5},
        'hat_cfg': {'tone': 0.4},
        'clap_cfg': {'decay': 0.12, 'spread': 0.015},
        'bass_cfg': {'waveform': 'square', 'cutoff': 500, 'env_mod': 6000, 'drive': 2.5, 'decay': 0.25},  # big filter sweep!
        'volumes': [0.85, 0.55, 0.5, 0.35, 0.3, 0.85, 0.4],
        'delay_mix': 0.22, 'sidechain_amt': 0.5,
        'patterns': [
            [.9, 0, 0, 0, .9, 0, 0, .7, .9, 0, 0, 0, .9, 0, .7, 0],    # kick
            [0, 0, 0, 0, .8, 0, 0, 0, 0, 0, 0, 0, .8, 0, 0, 0],         # snare
            [0, 0, 0, 0, 0, 0, 0, 0, .7, 0, 0, 0, 0, 0, 0, 0],          # clap
            [.8, 0, .6, 0, .8, 0, .6, 0, .8, 0, .6, 0, .8, 0, .5, .4],  # ch hat
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .5, 0, 0, 0, 0, 0],          # oh hat
            [.8, 0, .7, .8, 0, .7, .8, 0, .7, .8, 0, .7, 0, .8, 0, .7], # bass (busy 303)
            [0] * 16,
        ],
        'bass_notes': [36, 0, 39, 41, 0, 43, 36, 0, 39, 36, 0, 43, 0, 41, 0, 36],
        'lead_notes': [0] * 16,
    },
    'minimal': {
        'name': 'Minimal Techno', 'bpm': 125, 'swing': 0.1,
        'kick_cfg': {'pitch': 65, 'pitch_amt': 100, 'pitch_decay': 0.02, 'decay': 0.25, 'drive': 1.3, 'click': 0.6},
        'snare_cfg': {'pitch': 220, 'tone': 0.6, 'decay': 0.08, 'snappy': 0.3},
        'hat_cfg': {'tone': 0.7},  # dark, soft
        'clap_cfg': {'decay': 0.08, 'spread': 0.01},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 300, 'env_mod': 1200, 'drive': 1.2, 'decay': 0.25},
        'volumes': [0.8, 0.45, 0.4, 0.3, 0.25, 0.6, 0.45],
        'delay_mix': 0.25, 'sidechain_amt': 0.3,
        'patterns': [
            [.9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0],      # kick
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .6],          # snare (just one ghost)
            [0, 0, 0, 0, .6, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],          # clap
            [0, 0, .5, 0, 0, 0, .5, 0, 0, 0, .5, 0, 0, .3, .5, 0],      # ch hat
            [0] * 16,
            [.7, 0, 0, 0, 0, 0, 0, 0, .7, 0, 0, 0, 0, 0, .6, 0],        # bass
            [0, 0, .5, 0, 0, 0, 0, 0, 0, 0, 0, 0, .5, 0, 0, 0],         # lead
        ],
        'bass_notes': [36, 0, 0, 0, 0, 0, 0, 0, 43, 0, 0, 0, 0, 0, 36, 0],
        'lead_notes': [72, 0, 75, 0, 0, 0, 0, 0, 0, 0, 0, 0, 77, 0, 0, 0],
    },
    'afro': {
        'name': 'Afro House', 'bpm': 122, 'swing': 0.22,  # heavy swing!
        'kick_cfg': {'pitch': 45, 'pitch_amt': 150, 'pitch_decay': 0.05, 'decay': 0.6, 'drive': 1.5, 'click': 0.15},
        'snare_cfg': {'pitch': 240, 'tone': 0.5, 'decay': 0.1, 'snappy': 0.4},
        'hat_cfg': {'tone': 0.6},
        'clap_cfg': {'decay': 0.1, 'spread': 0.012},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 250, 'env_mod': 800, 'drive': 1.0, 'decay': 0.35},
        'volumes': [0.85, 0.5, 0.4, 0.4, 0.3, 0.65, 0.5],
        'delay_mix': 0.15, 'sidechain_amt': 0.35,
        'patterns': [
            [.9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0],      # kick
            [0, 0, 0, 0, .8, 0, 0, .4, 0, 0, 0, 0, .8, 0, .4, 0],       # snare (ghost rimshot)
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],           # clap
            [0, .6, 0, .6, 0, .6, 0, .6, 0, .6, 0, .6, 0, .6, 0, .6],   # ch hat (offbeat)
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],           # oh hat
            [.7, 0, 0, 0, 0, 0, 0, 0, .7, 0, 0, 0, 0, 0, .6, 0],        # bass
            [0, 0, .5, 0, 0, .5, 0, 0, .5, 0, 0, .5, 0, 0, .5, 0],      # lead (perc feel)
        ],
        'bass_notes': [36, 0, 0, 0, 0, 0, 0, 0, 43, 0, 0, 0, 0, 0, 36, 0],
        'lead_notes': [65, 0, 67, 0, 0, 65, 0, 0, 67, 0, 0, 65, 0, 0, 67, 0],
    },
    'melodic': {
        'name': 'Melodic Techno', 'bpm': 124, 'swing': 0.0,
        'kick_cfg': {'pitch': 52, 'pitch_amt': 170, 'pitch_decay': 0.04, 'decay': 0.4, 'drive': 1.8, 'click': 0.25},
        'snare_cfg': {'pitch': 200, 'tone': 0.5, 'decay': 0.18, 'snappy': 0.4},
        'hat_cfg': {'tone': 0.35},  # bright, shimmery
        'clap_cfg': {'decay': 0.15, 'spread': 0.02},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 500, 'env_mod': 2000, 'drive': 1.3, 'decay': 0.3},
        'volumes': [0.85, 0.55, 0.45, 0.35, 0.3, 0.65, 0.55],
        'delay_mix': 0.22, 'sidechain_amt': 0.45,
        'patterns': [
            [.9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0],      # kick
            [0, 0, 0, 0, .7, 0, 0, 0, 0, 0, 0, 0, .7, 0, 0, 0],         # snare
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],           # clap
            [.9, .5, .7, .5, .9, .5, .7, .5, .9, .5, .7, .5, .9, .5, .7, .5],  # 16th hats
            [0, 0, 0, 0, 0, 0, 0, 0, .5, 0, 0, 0, 0, 0, 0, 0],          # oh hat
            [.7, 0, 0, 0, 0, 0, .6, 0, .7, 0, 0, 0, 0, .5, 0, 0],       # bass
            [.5, 0, 0, .4, 0, 0, .5, 0, 0, .4, 0, 0, .5, 0, 0, .4],     # lead (arp)
        ],
        'bass_notes': [36, 0, 0, 0, 0, 0, 43, 0, 36, 0, 0, 0, 0, 41, 0, 0],
        'lead_notes': [72, 0, 0, 70, 0, 0, 72, 0, 0, 75, 0, 0, 77, 0, 0, 72],
    },
    'ukgarage': {
        'name': 'UK Garage / 2-Step', 'bpm': 132, 'swing': 0.25,  # heavy 2-step shuffle
        'kick_cfg': {'pitch': 42, 'pitch_amt': 200, 'pitch_decay': 0.06, 'decay': 0.55, 'drive': 1.8, 'click': 0.15},
        'snare_cfg': {'pitch': 190, 'tone': 0.3, 'decay': 0.13, 'snappy': 0.6},
        'hat_cfg': {'tone': 0.4},
        'clap_cfg': {'decay': 0.1, 'spread': 0.012},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 700, 'env_mod': 2000, 'drive': 1.3, 'decay': 0.2},
        'volumes': [0.9, 0.6, 0.5, 0.4, 0.3, 0.8, 0.4],
        'delay_mix': 0.1, 'sidechain_amt': 0.4,
        'patterns': [
            [.9, 0, 0, 0, 0, 0, .8, 0, 0, .7, 0, 0, 0, 0, .7, 0],      # kick (broken!)
            [0, 0, 0, 0, .8, 0, 0, 0, 0, 0, 0, 0, .8, 0, 0, 0],         # snare
            [0, 0, 0, 0, .6, 0, 0, 0, 0, 0, 0, 0, .6, 0, 0, 0],         # clap
            [0, .7, 0, .7, 0, .7, 0, .7, 0, .7, 0, .7, 0, .7, 0, .7],   # ch hat (offbeat)
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .5, 0, 0, 0, 0, 0],          # oh hat
            [.8, 0, 0, .6, 0, .5, 0, 0, .7, 0, .5, 0, 0, 0, .6, 0],     # bass (bouncy)
            [0] * 16,
        ],
        'bass_notes': [36, 0, 0, 38, 0, 41, 0, 0, 43, 0, 41, 0, 0, 0, 38, 0],
        'lead_notes': [0] * 16,
    },
    'trance': {
        'name': 'Uplifting Trance', 'bpm': 138, 'swing': 0.0,
        'kick_cfg': {'pitch': 50, 'pitch_amt': 220, 'pitch_decay': 0.035, 'decay': 0.5, 'drive': 2.2, 'click': 0.5},
        'snare_cfg': {'pitch': 200, 'tone': 0.3, 'decay': 0.2, 'snappy': 0.7},
        'hat_cfg': {'tone': 0.3},  # bright, driving
        'clap_cfg': {'decay': 0.15, 'spread': 0.018},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 600, 'env_mod': 2500, 'drive': 1.5, 'decay': 0.2},
        'volumes': [0.9, 0.6, 0.5, 0.4, 0.35, 0.7, 0.6],
        'delay_mix': 0.25, 'sidechain_amt': 0.6,
        'patterns': [
            [.9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0],      # kick
            [0, 0, 0, 0, .8, 0, 0, 0, 0, 0, 0, 0, .8, 0, 0, 0],         # snare
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],           # clap
            [0, .7, 0, .7, 0, .7, 0, .7, 0, .7, 0, .7, 0, .7, 0, .7],   # offbeat hats
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],           # oh hat
            [0, .8, 0, 0, 0, .8, 0, 0, 0, .8, 0, 0, 0, .8, 0, 0],       # bass (offbeat pump)
            [.5, 0, .4, 0, .5, 0, .6, 0, .5, 0, .4, 0, .6, 0, .5, 0],   # lead (arp)
        ],
        'bass_notes': [36, 36, 0, 0, 0, 36, 0, 0, 0, 43, 0, 0, 0, 41, 0, 0],
        'lead_notes': [72, 0, 75, 0, 72, 0, 77, 0, 75, 0, 72, 0, 77, 0, 75, 0],
    },
    'deephouse': {
        'name': 'Deep House', 'bpm': 122, 'swing': 0.15,
        'kick_cfg': {'pitch': 48, 'pitch_amt': 160, 'pitch_decay': 0.05, 'decay': 0.55, 'drive': 1.5, 'click': 0.15},
        'snare_cfg': {'pitch': 210, 'tone': 0.5, 'decay': 0.12, 'snappy': 0.4},
        'hat_cfg': {'tone': 0.55},  # warm
        'clap_cfg': {'decay': 0.1, 'spread': 0.013},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 350, 'env_mod': 1500, 'drive': 1.1, 'decay': 0.35},
        'volumes': [0.85, 0.5, 0.4, 0.35, 0.35, 0.75, 0.4],
        'delay_mix': 0.18, 'sidechain_amt': 0.35,
        'patterns': [
            [.9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0, .9, 0, 0, 0],      # kick
            [0, 0, 0, 0, .7, 0, 0, .3, 0, 0, 0, 0, .7, 0, 0, 0],        # snare (ghost on 8)
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],           # clap
            [.7, 0, .6, .5, .7, 0, .6, .5, .7, 0, .6, .5, .7, 0, .6, .5],  # ch hat (shuffle)
            [0, .5, 0, 0, 0, .5, 0, 0, 0, .5, 0, 0, 0, .5, 0, 0],       # oh hat (offbeat)
            [.8, 0, 0, 0, .6, 0, 0, .5, .7, 0, .5, 0, 0, 0, .6, 0],     # bass (melodic)
            [0] * 16,
        ],
        'bass_notes': [36, 0, 0, 0, 43, 0, 0, 41, 36, 0, 48, 0, 0, 0, 43, 0],
        'lead_notes': [0] * 16,
    },
    'fredagain': {
        'name': 'Fred Again / Emotional', 'bpm': 128, 'swing': 0.1,
        'kick_cfg': {'pitch': 55, 'pitch_amt': 120, 'pitch_decay': 0.03, 'decay': 0.3, 'drive': 1.5, 'click': 0.25},
        'snare_cfg': {'pitch': 200, 'tone': 0.4, 'decay': 0.16, 'snappy': 0.5},
        'hat_cfg': {'tone': 0.6},  # soft
        'clap_cfg': {'decay': 0.13, 'spread': 0.015},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 500, 'env_mod': 1800, 'drive': 1.2, 'decay': 0.3},
        'volumes': [0.7, 0.55, 0.5, 0.35, 0.3, 0.6, 0.55],
        'delay_mix': 0.2, 'sidechain_amt': 0.3,
        'patterns': [
            [.7, 0, 0, 0, 0, 0, .6, 0, 0, .6, 0, 0, 0, 0, 0, 0],       # kick (sparse, broken)
            [0, 0, 0, 0, .7, 0, 0, 0, 0, 0, 0, 0, .7, 0, 0, 0],         # snare
            [0, 0, 0, 0, .6, 0, 0, 0, 0, 0, 0, 0, .6, 0, 0, .4],        # clap
            [0, .5, 0, .5, 0, .5, 0, .5, 0, .5, 0, .5, 0, .5, 0, .5],   # ch hat (offbeat)
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, .4, 0, 0, 0, 0, 0],          # oh hat
            [.6, 0, 0, .5, 0, 0, 0, 0, .6, 0, 0, 0, 0, .4, 0, 0],       # bass
            [.4, 0, 0, 0, 0, .4, 0, 0, 0, 0, .5, 0, 0, 0, 0, .4],       # lead
        ],
        'bass_notes': [36, 0, 0, 39, 0, 0, 0, 0, 43, 0, 0, 0, 0, 41, 0, 0],
        'lead_notes': [72, 0, 0, 0, 0, 75, 0, 0, 0, 0, 77, 0, 0, 0, 0, 72],
    },
}

GENRE_KEYS = list(GENRES.keys())


# ======================== BEAT MAKER ========================

TRACK_NAMES = ['KICK', 'SNARE', 'CLAP', 'C.HAT', 'O.HAT', 'BASS', 'LEAD']
TRACK_COLORS = ['\033[91m', '\033[93m', '\033[95m', '\033[96m', '\033[94m', '\033[92m', '\033[97m']
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'

STEP_KEYS_TOP = 'asdfghjk'      # steps 1-8
STEP_KEYS_BOT = 'zxcvbnm,'      # steps 9-16

BASS_NOTES_DEFAULT = [36] * 16
LEAD_NOTES_DEFAULT = [60] * 16


class BeatMaker:
    def __init__(self):
        self.bpm = 128
        self.swing = 0.0  # 0=straight, 0.25=heavy shuffle
        self.patterns = [[0] * 16 for _ in range(7)]
        self.bass_notes = BASS_NOTES_DEFAULT.copy()
        self.lead_notes = LEAD_NOTES_DEFAULT.copy()
        self.selected_track = 0
        self.playing = True
        self.running = True
        self.step = 0
        self.sample_pos = 0
        self._last_step = -1
        self.current_genre = 'none'
        self.export_count = 0
        self.status_msg = ''
        self.status_time = 0

        # Instruments
        self.kick = Kick()
        self.snare = Snare()
        self.clap = Clap()
        self.ch_hat = HiHat()
        self.oh_hat = HiHat()
        self.bass = Bass()
        self.lead = Lead()

        # Volumes (per-track)
        self.volumes = [0.9, 0.6, 0.5, 0.35, 0.3, 0.7, 0.5]

        # Effects
        self.sidechain = Sidechain()
        self.delay = SimpleDelay()
        self.delay.set_tempo(self.bpm)

    def load_genre(self, genre_key):
        """Load a genre preset - applies ALL instrument configs for distinct sound."""
        if genre_key not in GENRES:
            return
        g = GENRES[genre_key]
        self.current_genre = genre_key
        self.bpm = g['bpm']
        self.swing = g.get('swing', 0.0)

        # Load patterns
        for i in range(7):
            self.patterns[i] = [float(v) for v in g['patterns'][i]]
        self.bass_notes = list(g['bass_notes'])
        self.lead_notes = list(g['lead_notes'])

        # Apply KICK config - this is what makes genres sound different!
        for k, v in g.get('kick_cfg', {}).items():
            if hasattr(self.kick, k):
                setattr(self.kick, k, v)

        # Apply SNARE config
        for k, v in g.get('snare_cfg', {}).items():
            if hasattr(self.snare, k):
                setattr(self.snare, k, v)

        # Apply CLAP config
        for k, v in g.get('clap_cfg', {}).items():
            if hasattr(self.clap, k):
                setattr(self.clap, k, v)

        # Apply HI-HAT config (both closed and open)
        for k, v in g.get('hat_cfg', {}).items():
            if hasattr(self.ch_hat, k):
                setattr(self.ch_hat, k, v)
            if hasattr(self.oh_hat, k):
                setattr(self.oh_hat, k, v)

        # Apply BASS config
        for k, v in g.get('bass_cfg', {}).items():
            if hasattr(self.bass, k):
                setattr(self.bass, k, v)

        # Apply VOLUMES
        if 'volumes' in g:
            self.volumes = list(g['volumes'])

        # Apply EFFECTS
        self.delay.mix = g.get('delay_mix', 0.15)
        self.delay.set_tempo(self.bpm)
        self.sidechain.amount = g.get('sidechain_amt', 0.5)

        self.status_msg = f'Loaded {g["name"]}'
        self.status_time = time.time()

    @property
    def samples_per_step(self):
        return SR * 60.0 / self.bpm / 4

    def _get_swung_step(self, sample_pos):
        """Calculate which step we're on, accounting for swing.
        Swing delays odd-numbered steps (the 'ands')."""
        sps = self.samples_per_step
        pair_duration = sps * 2  # duration of an even+odd step pair

        # Which pair are we in?
        bar_pos = sample_pos % (16 * sps)  # position within bar
        pair_idx = int(bar_pos / pair_duration)
        within_pair = bar_pos - pair_idx * pair_duration

        # Where does the odd step start? (shifted by swing)
        odd_threshold = sps * (1.0 + self.swing)

        if within_pair < odd_threshold:
            return pair_idx * 2       # even step
        else:
            return pair_idx * 2 + 1   # odd step (swung late)

    def audio_callback(self, outdata, frames, time_info, status):
        if not self.playing:
            outdata.fill(0)
            return

        sps = self.samples_per_step
        kick_triggered = False

        for i in range(frames):
            s = self._get_swung_step(self.sample_pos + i)
            if s != self._last_step:
                self._last_step = s
                self.step = s % 16
                p = self.patterns
                st = self.step
                if p[0][st]:
                    self.kick.trigger(p[0][st])
                    kick_triggered = True
                if p[1][st]: self.snare.trigger(p[1][st])
                if p[2][st]: self.clap.trigger(p[2][st])
                if p[3][st]: self.ch_hat.trigger(p[3][st])
                if p[4][st]: self.oh_hat.trigger(p[4][st], is_open=True)
                if p[5][st]: self.bass.trigger(self.bass_notes[st], p[5][st])
                if p[6][st]: self.lead.trigger(self.lead_notes[st], p[6][st])
        self.sample_pos += frames

        # Trigger sidechain on kick
        if kick_triggered:
            self.sidechain.trigger()

        # Render instruments
        kick_out = self.kick.render(frames) * self.volumes[0]
        snare_out = self.snare.render(frames) * self.volumes[1]
        clap_out = self.clap.render(frames) * self.volumes[2]
        ch_out = self.ch_hat.render(frames) * self.volumes[3]
        oh_out = self.oh_hat.render(frames) * self.volumes[4]
        bass_out = self.bass.render(frames) * self.volumes[5]
        lead_out = self.lead.render(frames) * self.volumes[6]

        # Apply sidechain ducking to bass and lead (pump effect)
        self.sidechain.compute(frames)
        bass_out = self.sidechain.apply(bass_out)
        lead_out = self.sidechain.apply(lead_out)

        # Mix
        mix = kick_out + snare_out + clap_out + ch_out + oh_out + bass_out + lead_out

        # Apply delay
        mix = self.delay.process(mix)

        # Final limiter
        mix = np.tanh(mix * 0.85)

        outdata[:, 0] = mix.astype(np.float32)
        outdata[:, 1] = mix.astype(np.float32)

    def toggle_step(self, step_idx):
        track = self.selected_track
        if self.patterns[track][step_idx] > 0:
            self.patterns[track][step_idx] = 0
        else:
            self.patterns[track][step_idx] = 0.8

    def clear_track(self):
        self.patterns[self.selected_track] = [0] * 16
        self.status_msg = f'Cleared {TRACK_NAMES[self.selected_track]}'
        self.status_time = time.time()

    def ai_fill(self):
        """Auto-generate pattern for current track."""
        rng = np.random.default_rng()
        track = self.selected_track
        if track == 0:  # kick - four on floor
            self.patterns[0] = [0.9, 0, 0, 0, 0.9, 0, 0, 0, 0.9, 0, 0, 0, 0.9, 0, 0, 0]
        elif track == 1:  # snare
            self.patterns[1] = [0, 0, 0, 0, 0.8, 0, 0, 0, 0, 0, 0, 0, 0.8, 0, 0, 0]
        elif track == 2:  # clap
            self.patterns[2] = [0, 0, 0, 0, 0.7, 0, 0, 0, 0, 0, 0, 0, 0.7, 0, 0, 0]
        elif track == 3:  # closed hat
            p = [0.0] * 16
            for i in range(16):
                if i % 2 == 0:
                    p[i] = 0.8
                elif rng.random() < 0.4:
                    p[i] = 0.4
            self.patterns[3] = p
        elif track == 4:  # open hat
            p = [0.0] * 16
            for i in [2, 6, 10, 14]:
                if rng.random() < 0.4:
                    p[i] = 0.6
            self.patterns[4] = p
        elif track == 5:  # bass
            p = [0.0] * 16
            notes = [36] * 16
            scale = [36, 38, 39, 41, 43, 44, 46, 48]
            for i in range(16):
                if rng.random() < 0.5:
                    p[i] = 0.7 + rng.random() * 0.3
                    notes[i] = int(rng.choice(scale))
            self.patterns[5] = p
            self.bass_notes = notes
        elif track == 6:  # lead
            p = [0.0] * 16
            notes = LEAD_NOTES_DEFAULT.copy()
            scale = [60, 62, 63, 65, 67, 68, 70, 72]
            for i in range(16):
                if rng.random() < 0.3:
                    p[i] = 0.6
                    notes[i] = int(rng.choice(scale))
            self.patterns[6] = p
            self.lead_notes = notes
        self.status_msg = f'AI filled {TRACK_NAMES[track]}'
        self.status_time = time.time()

    def display(self):
        lines = []
        lines.append('')
        genre_label = GENRES[self.current_genre]['name'] if self.current_genre in GENRES else 'Custom'
        play_status = '\033[92m▶ PLAYING\033[0m' if self.playing else '\033[91m■ STOPPED\033[0m'
        lines.append(f'  {BOLD}TECHNOBOX BEAT MAKER{RESET}   BPM: {self.bpm}   {play_status}   [{genre_label}]')

        # Show swing if active
        extras = []
        if self.swing > 0.01:
            extras.append(f'Swing:{int(self.swing*100)}%')
        if self.sidechain.amount > 0.01:
            extras.append(f'SC:{int(self.sidechain.amount*100)}%')
        if self.delay.mix > 0.01:
            extras.append(f'Delay:{int(self.delay.mix*100)}%')
        if extras:
            lines.append(f'  {DIM}{" | ".join(extras)}{RESET}')

        lines.append(f'  Track: {TRACK_COLORS[self.selected_track]}{BOLD}{TRACK_NAMES[self.selected_track]}{RESET}')
        lines.append('')

        # Step numbers
        nums = '  STEP  '
        for i in range(16):
            if i == 8: nums += ' '
            nums += f'{i+1:>2} '
        lines.append(f'{DIM}{nums}{RESET}')

        # Key hints
        keys = '  KEYS  '
        key_labels = list(STEP_KEYS_TOP) + list(STEP_KEYS_BOT)
        for i, k in enumerate(key_labels):
            if i == 8: keys += ' '
            keys += f' {k} '
        lines.append(f'{DIM}{keys}{RESET}')
        lines.append(f'  {"─" * 58}')

        # Each track
        for t in range(7):
            color = TRACK_COLORS[t]
            selected = '▸' if t == self.selected_track else ' '
            name = f'{TRACK_NAMES[t]:>5}'
            row = f'  {selected}{color}{BOLD}{name}{RESET} '

            for i in range(16):
                if i == 8: row += '│'
                v = self.patterns[t][i]
                if i == self.step and self.playing:
                    if v > 0:
                        row += f'\033[7m{color} ■ {RESET}'
                    else:
                        row += f'\033[7m   {RESET}'
                elif v > 0:
                    if v > 0.7:
                        row += f'{color} ■ {RESET}'
                    elif v > 0.4:
                        row += f'{color} □ {RESET}'
                    else:
                        row += f'{color} · {RESET}'
                else:
                    row += f'{DIM} - {RESET}'
            lines.append(row)

        lines.append(f'  {"─" * 58}')

        # Bass/lead note display
        if self.selected_track in (5, 6):
            note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            notes = self.bass_notes if self.selected_track == 5 else self.lead_notes
            pats = self.patterns[self.selected_track]
            nr = '  NOTE  '
            for i in range(16):
                if i == 8: nr += ' '
                if pats[i] > 0:
                    n = notes[i]
                    nr += f'{note_names[n%12]:>2} '
                else:
                    nr += '   '
            lines.append(f'{DIM}{nr}{RESET}')

        lines.append('')
        lines.append(f'  {DIM}STEP KEYS: a s d f g h j k (1-8)  z x c v b n m , (9-16){RESET}')
        lines.append(f'  {DIM}TAB=next track  SPACE=play/stop  +/-=BPM  G=AI fill  C=clear{RESET}')
        if self.selected_track >= 5:
            lines.append(f'  {DIM}UP/DOWN=change note  [ ]=octave shift{RESET}')
        lines.append(f'  {DIM}GENRES: !=Detroit @=Berlin #=Acid $=Minimal %=Afro{RESET}')
        lines.append(f'  {DIM}        ^=Melodic &=UKGarage *=Trance (=DeepHouse )=FredAgain{RESET}')
        lines.append(f'  {DIM}E=export WAV (#{self.export_count})  Q=quit{RESET}')

        # Status message (fades after 3 seconds)
        if self.status_msg and time.time() - self.status_time < 3:
            lines.append(f'  \033[93m{self.status_msg}{RESET}')
        else:
            lines.append('')

        output = '\033[H'
        output += '\n'.join(lines)
        output += '\n' * 3
        sys.stdout.write(output)
        sys.stdout.flush()

    def handle_key(self, ch):
        # Step toggles
        if ch in STEP_KEYS_TOP:
            idx = STEP_KEYS_TOP.index(ch)
            self.toggle_step(idx)
        elif ch in STEP_KEYS_BOT:
            idx = STEP_KEYS_BOT.index(ch) + 8
            self.toggle_step(idx)

        # Track select
        elif ch == '\t':
            self.selected_track = (self.selected_track + 1) % 7
        elif ch == '`':
            self.selected_track = (self.selected_track - 1) % 7

        # Transport
        elif ch == ' ':
            self.playing = not self.playing
            if not self.playing:
                self.sample_pos = 0
                self._last_step = -1
        elif ch in ('+', '='):
            self.bpm = min(200, self.bpm + 2)
            self.delay.set_tempo(self.bpm)
        elif ch in ('-', '_'):
            self.bpm = max(80, self.bpm - 2)
            self.delay.set_tempo(self.bpm)

        # AI fill
        elif ch == 'G':
            self.ai_fill()

        # Clear
        elif ch == 'C':
            self.clear_track()

        # Genre presets
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

        # Octave shift for bass/lead
        elif ch == '[':
            if self.selected_track == 5:
                self.bass_notes = [max(24, n - 12) for n in self.bass_notes]
            elif self.selected_track == 6:
                self.lead_notes = [max(36, n - 12) for n in self.lead_notes]
        elif ch == ']':
            if self.selected_track == 5:
                self.bass_notes = [min(60, n + 12) for n in self.bass_notes]
            elif self.selected_track == 6:
                self.lead_notes = [min(84, n + 12) for n in self.lead_notes]

        # Export
        elif ch == 'E':
            return 'export'

        # Quit
        elif ch in ('Q', 'q'):
            return 'quit'

        return None

    def export(self):
        """Export beat as WAV. Each export gets a unique timestamp filename."""
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        genre_tag = self.current_genre if self.current_genre != 'none' else 'custom'
        filename = os.path.expanduser(f'~/technobox/exports/beat_{genre_tag}_{ts}.wav')
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        self.status_msg = 'Exporting 8 bars...'
        self.status_time = time.time()
        self.display()

        # Render 8 bars offline
        bars = 8
        total_steps = 16 * bars
        sps = self.samples_per_step
        total_samples = int(total_steps * sps)
        audio = np.zeros(total_samples, dtype=np.float64)

        # Create fresh instruments with same configs
        kick = Kick()
        for attr in ('pitch', 'pitch_amt', 'pitch_decay', 'decay', 'drive', 'click'):
            setattr(kick, attr, getattr(self.kick, attr))
        snare = Snare()
        for attr in ('pitch', 'tone', 'decay', 'snappy'):
            setattr(snare, attr, getattr(self.snare, attr))
        clap = Clap()
        for attr in ('decay', 'spread'):
            setattr(clap, attr, getattr(self.clap, attr))
        ch = HiHat()
        ch.tone = self.ch_hat.tone
        oh = HiHat()
        oh.tone = self.oh_hat.tone
        bass = Bass()
        for attr in ('waveform', 'cutoff', 'env_mod', 'drive', 'decay'):
            setattr(bass, attr, getattr(self.bass, attr))
        lead = Lead()
        lead.detune = self.lead.detune
        lead.decay = self.lead.decay

        # Fresh effects for export
        sc = Sidechain()
        sc.amount = self.sidechain.amount
        sc.release = self.sidechain.release
        delay = SimpleDelay()
        delay.mix = self.delay.mix
        delay.feedback = self.delay.feedback
        delay.set_tempo(self.bpm)

        pos = 0
        last_step = -1
        block = 2048

        while pos < total_samples:
            bs = min(block, total_samples - pos)
            kick_hit = False

            # Step triggers with swing
            for i in range(bs):
                sample = pos + i
                pair_duration = sps * 2
                bar_pos = sample % (16 * sps)
                pair_idx = int(bar_pos / pair_duration)
                within_pair = bar_pos - pair_idx * pair_duration
                odd_threshold = sps * (1.0 + self.swing)
                if within_pair < odd_threshold:
                    s = pair_idx * 2
                else:
                    s = pair_idx * 2 + 1

                if s != last_step:
                    last_step = s
                    st = s % 16
                    p = self.patterns
                    if p[0][st]: kick.trigger(p[0][st]); kick_hit = True
                    if p[1][st]: snare.trigger(p[1][st])
                    if p[2][st]: clap.trigger(p[2][st])
                    if p[3][st]: ch.trigger(p[3][st])
                    if p[4][st]: oh.trigger(p[4][st], is_open=True)
                    if p[5][st]: bass.trigger(self.bass_notes[st], p[5][st])
                    if p[6][st]: lead.trigger(self.lead_notes[st], p[6][st])

            if kick_hit:
                sc.trigger()

            # Render + effects
            kick_out = kick.render(bs) * self.volumes[0]
            snare_out = snare.render(bs) * self.volumes[1]
            clap_out = clap.render(bs) * self.volumes[2]
            ch_out = ch.render(bs) * self.volumes[3]
            oh_out = oh.render(bs) * self.volumes[4]
            bass_out = bass.render(bs) * self.volumes[5]
            lead_out = lead.render(bs) * self.volumes[6]

            sc.compute(bs)
            bass_out = sc.apply(bass_out)
            lead_out = sc.apply(lead_out)

            mix = kick_out + snare_out + clap_out + ch_out + oh_out + bass_out + lead_out
            mix = delay.process(mix)
            mix = np.tanh(mix * 0.85)
            audio[pos:pos + bs] = mix
            pos += bs

        # Normalize
        peak = np.abs(audio).max()
        if peak > 0:
            audio = audio / peak * 0.92
        stereo = np.column_stack([audio, audio])
        data = (stereo * 32767).astype(np.int16)
        with wave.open(filename, 'w') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(SR)
            wf.writeframes(data.tobytes())

        self.export_count += 1
        size = os.path.getsize(filename) / 1024 / 1024
        short_name = os.path.basename(filename)
        self.status_msg = f'Exported #{self.export_count}: {short_name} ({size:.1f}MB)'
        self.status_time = time.time()

    def run(self):
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.flush()

        stream = sd.OutputStream(
            samplerate=SR, blocksize=BLOCK, channels=2,
            dtype='float32', callback=self.audio_callback, latency='low',
        )

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)

        try:
            tty.setcbreak(fd)
            stream.start()

            while self.running:
                self.display()

                import select
                if select.select([sys.stdin], [], [], 0.04)[0]:
                    ch = sys.stdin.read(1)

                    # Handle arrow keys (escape sequences)
                    if ch == '\x1b':
                        if select.select([sys.stdin], [], [], 0.01)[0]:
                            ch2 = sys.stdin.read(1)
                            if ch2 == '[':
                                ch3 = sys.stdin.read(1)
                                if ch3 == 'A':  # up arrow
                                    if self.selected_track == 5:
                                        s = self.step
                                        self.bass_notes[s] = min(60, self.bass_notes[s] + 1)
                                    elif self.selected_track == 6:
                                        s = self.step
                                        self.lead_notes[s] = min(84, self.lead_notes[s] + 1)
                                    else:
                                        self.selected_track = max(0, self.selected_track - 1)
                                elif ch3 == 'B':  # down arrow
                                    if self.selected_track == 5:
                                        s = self.step
                                        self.bass_notes[s] = max(24, self.bass_notes[s] - 1)
                                    elif self.selected_track == 6:
                                        s = self.step
                                        self.lead_notes[s] = max(36, self.lead_notes[s] - 1)
                                    else:
                                        self.selected_track = min(6, self.selected_track + 1)
                                elif ch3 == 'Z':  # shift+tab
                                    self.selected_track = (self.selected_track - 1) % 7
                        continue

                    result = self.handle_key(ch)
                    if result == 'quit':
                        self.running = False
                    elif result == 'export':
                        self.export()

            stream.stop()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            sys.stdout.write('\033[?25h')
            print('\n  Bye!\n')


if __name__ == '__main__':
    maker = BeatMaker()
    maker.run()
