#!/usr/bin/env python3
"""
TechnoBox Track Creator - Build full tracks like a producer.

Creates complete songs with:
  - Song structure (intro, buildup, drop, breakdown, outro)
  - Energy automation (filter sweeps, volume builds, fx)
  - Multiple pattern variations per section
  - Full WAV export (3-5 minutes)

Usage:
  python3 create_track.py              # interactive mode
  python3 create_track.py --quick      # auto-generate a full track
  python3 create_track.py --style acid # pick a style
"""
import sys
import os
import time
import wave
import threading
import numpy as np
import sounddevice as sd

SR = 48000
BLOCK = 2048


# ======================== SYNTH VOICES ========================

class Kick:
    def __init__(self, pitch=50, pitch_amt=200, pitch_decay=0.04, decay=0.5, drive=2.0):
        self.pitch = pitch
        self.pitch_amt = pitch_amt
        self.pitch_decay = pitch_decay
        self.decay = decay
        self.drive = drive
        self.phase = 0.0
        self.t = 0
        self.active = False

    def trigger(self, vel=1.0):
        self.phase = 0.0
        self.t = 0
        self.active = True
        self._vel = vel

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n
        freq = self.pitch + self.pitch_amt * np.exp(-t / self.pitch_decay)
        phase = self.phase + np.cumsum(freq / SR)
        self.phase = phase[-1]
        body = np.sin(2 * np.pi * phase)
        amp = np.exp(-t / self.decay) * self._vel
        click = np.random.randn(n) * np.exp(-t / 0.008) * 0.3
        sig = np.tanh((body + click) * amp * self.drive)
        if amp[-1] < 0.001:
            self.active = False
        return sig


class Snare:
    def __init__(self):
        self.t = 0
        self.active = False

    def trigger(self, vel=1.0):
        self.t = 0
        self.active = True
        self._vel = vel

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n
        freq = 200 * (1 + 0.5 * np.exp(-t / 0.01))
        body = np.sin(2 * np.pi * np.cumsum(freq / SR)) * np.exp(-t / 0.1) * 0.4
        noise = np.random.randn(n) * np.exp(-t / 0.15) * 0.6
        sig = (body + noise) * self._vel
        if t[-1] > 0.5:
            self.active = False
        return sig


class Clap:
    def __init__(self):
        self.t = 0
        self.active = False

    def trigger(self, vel=1.0):
        self.t = 0
        self.active = True
        self._vel = vel

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n
        noise = np.random.randn(n)
        env = np.zeros(n)
        for off in [0.0, 0.01, 0.02, 0.035]:
            mask = (t >= off) & (t < off + 0.005)
            env += mask * np.exp(-(t - off) / 0.002) * 0.5
        env += np.exp(-t / 0.12) * 0.3
        sig = noise * env * self._vel
        if t[-1] > 0.5:
            self.active = False
        return sig


class HiHat:
    def __init__(self):
        self.t = 0
        self.active = False
        self.freqs = [205.3, 369.6, 304.4, 522.7, 540.0, 800.0]
        self._decay = 0.05

    def trigger(self, vel=1.0, is_open=False):
        self.t = 0
        self.active = True
        self._vel = vel
        self._decay = 0.25 if is_open else 0.05

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n
        metal = sum(np.sign(np.sin(2 * np.pi * f * t)) for f in self.freqs) / len(self.freqs)
        noise = np.random.randn(n)
        sig = (metal * 0.6 + noise * 0.4) * np.exp(-t / self._decay) * self._vel * 0.4
        if t[-1] > self._decay * 8:
            self.active = False
        return sig


class Bass:
    def __init__(self, waveform='saw', cutoff=800, resonance=2.5, env_mod=3000, drive=1.5):
        self.waveform = waveform
        self.cutoff = cutoff
        self.resonance = resonance
        self.env_mod = env_mod
        self.drive = drive
        self.phase = 0.0
        self.freq = 55.0
        self.t = 0
        self.active = False
        self._lp = 0.0

    def trigger(self, note, vel=1.0):
        self.freq = 440.0 * 2 ** ((note - 69) / 12.0)
        self.phase = 0.0
        self.t = 0
        self.active = True
        self._vel = vel

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n
        dt = self.freq / SR
        phases = (self.phase + np.arange(n) * dt) % 1.0
        self.phase = (self.phase + n * dt) % 1.0
        if self.waveform == 'saw':
            osc = 2.0 * phases - 1.0
        else:
            osc = np.where(phases < 0.5, 1.0, -1.0)
        sub = np.sin(2 * np.pi * (np.arange(n) * dt * 0.5) % 1.0) * 0.3
        sig = osc * 0.7 + sub
        env = np.exp(-t / 0.15)
        fc = self.cutoff + env * self.env_mod
        fc = np.clip(fc, 20, SR * 0.45)
        alpha = 1.0 - np.exp(-2.0 * np.pi * fc / SR)
        out = np.zeros(n)
        lp = self._lp
        for i in range(n):
            lp += alpha[i] * (sig[i] - lp)
            out[i] = lp
        self._lp = lp
        amp = np.exp(-t / 0.3) * self._vel
        out = np.tanh(out * amp * self.drive)
        if amp[-1] < 0.001:
            self.active = False
        return out


class Pad:
    def __init__(self):
        self.phases = [0.0, 0.0, 0.0]
        self.freq = 220.0
        self.amp = 0.0
        self.target_amp = 0.0
        self.active = False

    def trigger(self, note, vel=0.4):
        self.freq = 440.0 * 2 ** ((note - 69) / 12.0)
        self.target_amp = vel
        self.active = True

    def release(self):
        self.target_amp = 0.0

    def render(self, n):
        if not self.active and self.amp < 0.001:
            return np.zeros(n)
        out = np.zeros(n)
        detunes = [1.0, 1.005, 0.995]
        for j, det in enumerate(detunes):
            f = self.freq * det
            dt = f / SR
            ph = (self.phases[j] + np.arange(n) * dt) % 1.0
            self.phases[j] = (self.phases[j] + n * dt) % 1.0
            out += (2.0 * ph - 1.0) / 3.0  # saw
        # Slow amplitude smoothing
        amp_arr = np.zeros(n)
        a = self.amp
        rate = 0.0001  # slow fade
        for i in range(n):
            a += (self.target_amp - a) * rate
            amp_arr[i] = a
        self.amp = a
        if self.amp < 0.001 and self.target_amp == 0:
            self.active = False
        # Simple lowpass
        fc = 1500.0
        alpha_val = 1.0 - np.exp(-2.0 * np.pi * fc / SR)
        lp = 0.0
        filtered = np.zeros(n)
        for i in range(n):
            lp += alpha_val * (out[i] - lp)
            filtered[i] = lp
        return filtered * amp_arr


class Lead:
    def __init__(self):
        self.phase = 0.0
        self.freq = 440.0
        self.t = 0
        self.active = False
        self._lp = 0.0

    def trigger(self, note, vel=0.6):
        self.freq = 440.0 * 2 ** ((note - 69) / 12.0)
        self.t = 0
        self.active = True
        self._vel = vel
        self.phase = 0.0

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n
        dt = self.freq / SR
        ph1 = (self.phase + np.arange(n) * dt) % 1.0
        ph2 = (self.phase + np.arange(n) * dt * 1.005) % 1.0
        self.phase = (self.phase + n * dt) % 1.0
        osc = (2.0 * ph1 - 1.0) * 0.5 + (2.0 * ph2 - 1.0) * 0.5
        amp = np.exp(-t / 0.4) * self._vel
        # Filter
        fc = 2000 + 3000 * np.exp(-t / 0.2)
        alpha = 1.0 - np.exp(-2.0 * np.pi * fc / SR)
        out = np.zeros(n)
        lp = self._lp
        for i in range(n):
            lp += alpha[i] * (osc[i] - lp)
            out[i] = lp
        self._lp = lp
        out *= amp
        if amp[-1] < 0.001:
            self.active = False
        return out


# ======================== DELAY / REVERB ========================

class Delay:
    def __init__(self, time_sec=0.375, feedback=0.4, mix=0.25):
        self.buf = np.zeros(int(time_sec * SR))
        self.pos = 0
        self.feedback = feedback
        self.mix = mix

    def process(self, x):
        out = np.zeros(len(x))
        for i in range(len(x)):
            delayed = self.buf[self.pos]
            self.buf[self.pos] = x[i] + delayed * self.feedback
            self.pos = (self.pos + 1) % len(self.buf)
            out[i] = x[i] + delayed * self.mix
        return out


class SimpleReverb:
    def __init__(self, mix=0.15):
        delays_ms = [29.7, 37.1, 41.1, 43.7]
        self.delays = [int(d / 1000 * SR) for d in delays_ms]
        self.bufs = [np.zeros(d + 1) for d in self.delays]
        self.positions = [0] * len(self.delays)
        self.feedback = 0.8
        self.mix = mix

    def process(self, x):
        out = np.zeros(len(x))
        for i in range(len(x)):
            s = 0.0
            for c in range(len(self.delays)):
                rp = (self.positions[c] - self.delays[c]) % len(self.bufs[c])
                delayed = self.bufs[c][rp]
                self.bufs[c][self.positions[c] % len(self.bufs[c])] = x[i] + delayed * self.feedback
                self.positions[c] += 1
                s += delayed
            out[i] = s / len(self.delays)
        return x * (1 - self.mix) + out * self.mix


# ======================== SONG SECTIONS ========================

# Each section defines: which instruments play, volume levels, pattern variations, fx

def make_section(name, bars, kick_pat, snare_pat, clap_pat, hat_pat, hat_vel, oh_pat,
                 bass_pat, bass_notes, lead_pat=None, lead_notes=None, pad_note=None,
                 kick_vol=0.9, snare_vol=0.6, clap_vol=0.5, hat_vol=0.35,
                 bass_vol=0.7, lead_vol=0.0, pad_vol=0.0,
                 delay_mix=0.0, reverb_mix=0.1, filter_sweep=None, energy=0.5):
    return {
        'name': name, 'bars': bars,
        'kick': kick_pat, 'snare': snare_pat, 'clap': clap_pat,
        'hat': hat_pat, 'hat_vel': hat_vel, 'oh': oh_pat,
        'bass': bass_pat, 'bass_notes': bass_notes,
        'lead': lead_pat or [0]*16, 'lead_notes': lead_notes or [0]*16,
        'pad_note': pad_note,
        'kick_vol': kick_vol, 'snare_vol': snare_vol, 'clap_vol': clap_vol,
        'hat_vol': hat_vol, 'bass_vol': bass_vol, 'lead_vol': lead_vol,
        'pad_vol': pad_vol,
        'delay_mix': delay_mix, 'reverb_mix': reverb_mix,
        'filter_sweep': filter_sweep, 'energy': energy,
    }


# ---------- SONG TEMPLATES ----------

def detroit_track():
    """Full Detroit techno track ~ 3.5 min"""
    _k4 = [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0]
    _sn  = [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0]
    _cl  = [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0]
    _hc  = [0,0,1,0, 0,0,1,0, 0,0,1,0, 0,0,1,0]
    _hv  = [0,0,.7,0, 0,0,.7,0, 0,0,.7,0, 0,0,.7,0]
    _h16 = [1,1,1,1, 1,1,1,1, 1,1,1,1, 1,1,1,1]
    _hv16= [.9,.4,.7,.4, .9,.4,.7,.4, .9,.4,.7,.4, .9,.4,.7,.4]
    _oh  = [0,0,0,0, 0,0,0,0, 0,0,1,0, 0,0,0,0]
    _b1  = [1,0,0,1, 0,0,1,0, 1,0,0,1, 0,0,0,0]
    _bn1 = [36,0,0,36, 0,0,43,0, 36,0,0,36, 0,0,0,0]
    _b2  = [1,0,1,0, 0,0,1,0, 1,0,0,1, 0,1,0,0]
    _bn2 = [36,0,43,0, 0,0,36,0, 36,0,0,43, 0,36,0,0]
    _ld  = [1,0,0,0, 0,0,1,0, 0,0,1,0, 0,0,0,0]
    _ln  = [72,0,0,0, 0,0,75,0, 0,0,72,0, 0,0,0,0]
    z16 = [0]*16

    return {
        'name': 'Detroit Dreams',
        'bpm': 128,
        'style': 'detroit',
        'kick_cfg': {'pitch': 50, 'pitch_amt': 180, 'decay': 0.5, 'drive': 2.0},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 600, 'resonance': 2.0, 'env_mod': 2500, 'drive': 1.5},
        'sections': [
            # INTRO: just kick + hat building (8 bars)
            make_section('INTRO', 4, _k4, z16, z16, _hc, _hv, z16, z16, z16,
                         pad_note=60, pad_vol=0.2, reverb_mix=0.3, hat_vol=0.2, energy=0.2),
            make_section('INTRO+', 4, _k4, z16, z16, _hc, _hv, z16, _b1, _bn1,
                         pad_note=60, pad_vol=0.25, bass_vol=0.3, reverb_mix=0.25, energy=0.3),

            # BUILDUP: adding elements (8 bars)
            make_section('BUILD', 4, _k4, z16, _cl, _h16, _hv16, z16, _b1, _bn1,
                         bass_vol=0.5, hat_vol=0.3, reverb_mix=0.2, energy=0.5,
                         filter_sweep='open'),
            make_section('BUILD+', 4, _k4, _sn, _cl, _h16, _hv16, _oh, _b2, _bn2,
                         bass_vol=0.6, hat_vol=0.35, delay_mix=0.15, energy=0.7,
                         filter_sweep='open'),

            # DROP 1: full energy (8 bars)
            make_section('DROP', 8, _k4, _sn, _cl, _h16, _hv16, _oh, _b2, _bn2,
                         _ld, _ln, pad_note=60,
                         bass_vol=0.75, lead_vol=0.4, pad_vol=0.15,
                         delay_mix=0.2, reverb_mix=0.15, energy=1.0),

            # BREAKDOWN: strip it back (4 bars)
            make_section('BREAK', 4, z16, z16, z16, _hc, _hv, z16, z16, z16,
                         pad_note=63, pad_vol=0.4, hat_vol=0.2,
                         reverb_mix=0.4, delay_mix=0.3, energy=0.2),

            # BUILDUP 2 (4 bars)
            make_section('BUILD2', 4, _k4, z16, z16, _h16, _hv16, z16, _b1, _bn1,
                         bass_vol=0.5, hat_vol=0.3, energy=0.6, filter_sweep='open'),

            # DROP 2: full energy with variation (8 bars)
            make_section('DROP2', 8, _k4, _sn, _cl, _h16, _hv16, _oh, _b2, _bn2,
                         _ld, _ln, pad_note=60,
                         bass_vol=0.8, lead_vol=0.45, pad_vol=0.15,
                         delay_mix=0.2, reverb_mix=0.15, energy=1.0),

            # OUTRO: winding down (8 bars)
            make_section('OUTRO', 4, _k4, z16, z16, _hc, _hv, z16, _b1, _bn1,
                         bass_vol=0.4, hat_vol=0.25, reverb_mix=0.3, energy=0.4),
            make_section('OUTRO-', 4, _k4, z16, z16, z16, z16, z16, z16, z16,
                         pad_note=60, pad_vol=0.3, reverb_mix=0.4, kick_vol=0.5, energy=0.1),
        ]
    }


def berlin_track():
    """Hard Berlin techno track"""
    _k4 = [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0]
    _ks = [1,0,0,0, 1,0,1,0, 1,0,0,0, 1,0,0,1]
    _sn = [0,0,0,0, 0,0,0,1, 0,0,0,0, 0,0,1,0]
    _cl = [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0]
    _h16= [1,1,1,1, 1,1,1,1, 1,1,1,1, 1,1,1,1]
    _hv = [.9,.4,.7,.4, .9,.4,.7,.4, .9,.4,.7,.4, .9,.4,.7,.4]
    _oh = [0,0,0,0, 0,0,1,0, 0,0,0,0, 0,0,1,0]
    _b1 = [1,0,1,0, 0,0,1,0, 1,0,0,1, 0,0,1,0]
    _bn1= [33,0,34,0, 0,0,33,0, 33,0,0,36, 0,0,33,0]
    _b2 = [1,0,1,1, 0,1,1,0, 1,0,1,0, 0,1,1,0]
    _bn2= [33,0,34,36, 0,33,34,0, 33,0,36,0, 0,34,33,0]
    z16 = [0]*16

    return {
        'name': 'Berlin Warehouse',
        'bpm': 140,
        'style': 'berlin',
        'kick_cfg': {'pitch': 45, 'pitch_amt': 250, 'decay': 0.4, 'drive': 3.5},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 400, 'resonance': 3.0, 'env_mod': 4000, 'drive': 2.5},
        'sections': [
            make_section('INTRO', 4, _k4, z16, z16, z16, z16, z16, z16, z16,
                         kick_vol=0.7, reverb_mix=0.3, energy=0.2),
            make_section('BUILD', 4, _k4, z16, z16, _h16, _hv, z16, _b1, _bn1,
                         bass_vol=0.4, hat_vol=0.25, energy=0.4, filter_sweep='open'),
            make_section('BUILD+', 4, _ks, _sn, z16, _h16, _hv, _oh, _b1, _bn1,
                         bass_vol=0.6, hat_vol=0.35, energy=0.7, filter_sweep='open'),
            make_section('DROP', 8, _ks, _sn, _cl, _h16, _hv, _oh, _b2, _bn2,
                         bass_vol=0.8, hat_vol=0.4, delay_mix=0.15, energy=1.0),
            make_section('BREAK', 4, z16, z16, z16, z16, z16, z16, z16, z16,
                         pad_note=58, pad_vol=0.35, reverb_mix=0.5, energy=0.1),
            make_section('BUILD3', 4, _k4, z16, z16, _h16, _hv, z16, _b1, _bn1,
                         bass_vol=0.5, energy=0.6, filter_sweep='open'),
            make_section('DROP2', 8, _ks, _sn, _cl, _h16, _hv, _oh, _b2, _bn2,
                         bass_vol=0.85, hat_vol=0.4, delay_mix=0.15, energy=1.0),
            make_section('OUTRO', 4, _k4, z16, z16, _h16, _hv, z16, z16, z16,
                         hat_vol=0.2, reverb_mix=0.35, energy=0.3),
            make_section('OUTRO-', 4, _k4, z16, z16, z16, z16, z16, z16, z16,
                         kick_vol=0.5, reverb_mix=0.4, energy=0.1),
        ]
    }


def acid_track():
    """Acid techno track with 303 squelch"""
    _k4 = [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0]
    _ks = [1,0,0,0, 1,0,0,1, 1,0,0,0, 1,0,1,0]
    _sn = [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0]
    _cl = [0,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0]
    _h8 = [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,0]
    _hv8= [.8,0,.6,0, .8,0,.6,0, .8,0,.6,0, .8,0,.6,0]
    _h16= [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,1]
    _hv16=[.8,0,.6,0, .8,0,.6,0, .8,0,.6,0, .8,0,.5,.4]
    _oh = [0,0,0,0, 0,0,0,0, 0,0,1,0, 0,0,0,0]
    _b1 = [1,0,1,1, 0,1,1,0, 1,1,0,1, 0,1,0,1]
    _bn1= [36,0,39,41, 0,43,36,0, 39,36,0,43, 0,41,0,36]
    _b2 = [1,1,0,1, 1,0,1,0, 1,0,1,1, 0,1,1,0]
    _bn2= [36,39,0,43, 41,0,36,0, 39,0,41,43, 0,36,39,0]
    _ld = [1,0,0,0, 0,0,1,0, 0,1,0,0, 0,0,0,1]
    _ln = [72,0,0,0, 0,0,75,0, 0,77,0,0, 0,0,0,72]
    z16 = [0]*16

    return {
        'name': 'Acid Dreams',
        'bpm': 138,
        'style': 'acid',
        'kick_cfg': {'pitch': 52, 'pitch_amt': 200, 'decay': 0.45, 'drive': 2.0},
        'bass_cfg': {'waveform': 'square', 'cutoff': 500, 'resonance': 3.8, 'env_mod': 5000, 'drive': 2.0},
        'sections': [
            make_section('INTRO', 4, z16, z16, z16, _h8, _hv8, z16, _b1, _bn1,
                         bass_vol=0.4, hat_vol=0.2, reverb_mix=0.3, energy=0.2),
            make_section('INTRO+', 4, _k4, z16, z16, _h8, _hv8, z16, _b1, _bn1,
                         bass_vol=0.55, hat_vol=0.25, energy=0.4),
            make_section('BUILD', 4, _k4, z16, z16, _h16, _hv16, z16, _b1, _bn1,
                         bass_vol=0.65, hat_vol=0.3, energy=0.6, filter_sweep='open'),
            make_section('DROP', 8, _ks, _sn, _cl, _h16, _hv16, _oh, _b2, _bn2,
                         _ld, _ln, bass_vol=0.8, lead_vol=0.35, hat_vol=0.35,
                         delay_mix=0.2, energy=1.0),
            make_section('BREAK', 4, z16, z16, z16, z16, z16, z16, _b1, _bn1,
                         bass_vol=0.4, pad_note=63, pad_vol=0.3,
                         reverb_mix=0.45, delay_mix=0.3, energy=0.15),
            make_section('BUILD2', 4, _k4, z16, z16, _h16, _hv16, z16, _b1, _bn1,
                         bass_vol=0.6, energy=0.6, filter_sweep='open'),
            make_section('DROP2', 8, _ks, _sn, _cl, _h16, _hv16, _oh, _b2, _bn2,
                         _ld, _ln, bass_vol=0.85, lead_vol=0.4, hat_vol=0.35,
                         delay_mix=0.2, energy=1.0),
            make_section('OUTRO', 4, _k4, z16, z16, _h8, _hv8, z16, _b1, _bn1,
                         bass_vol=0.4, reverb_mix=0.3, energy=0.3),
            make_section('END', 4, z16, z16, z16, z16, z16, z16, _b1, _bn1,
                         bass_vol=0.25, reverb_mix=0.5, delay_mix=0.3, energy=0.1),
        ]
    }


def minimal_track():
    """Minimal techno track - hypnotic and sparse"""
    _k4 = [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0]
    _sn = [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,1]
    _cl = [0,0,0,0, 1,0,0,0, 0,0,0,0, 0,0,0,0]
    _h1 = [0,0,1,0, 0,0,1,0, 0,0,1,0, 0,0,1,0]
    _hv1= [0,0,.5,0, 0,0,.5,0, 0,0,.5,0, 0,0,.5,0]
    _h2 = [0,0,1,0, 0,0,1,0, 0,0,1,0, 0,1,1,0]
    _hv2= [0,0,.5,0, 0,0,.5,0, 0,0,.5,0, 0,.3,.5,0]
    _oh = [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0]
    _b1 = [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,1,0]
    _bn1= [36,0,0,0, 0,0,0,0, 43,0,0,0, 0,0,36,0]
    _ld = [0,0,1,0, 0,0,0,0, 0,0,0,0, 1,0,0,0]
    _ln = [72,0,75,0, 0,0,0,0, 0,0,0,0, 77,0,0,0]
    z16 = [0]*16

    return {
        'name': 'Minimal Hypnosis',
        'bpm': 125,
        'style': 'minimal',
        'kick_cfg': {'pitch': 55, 'pitch_amt': 150, 'decay': 0.6, 'drive': 1.5},
        'bass_cfg': {'waveform': 'saw', 'cutoff': 300, 'resonance': 1.0, 'env_mod': 1200, 'drive': 1.2},
        'sections': [
            make_section('INTRO', 4, _k4, z16, z16, z16, z16, z16, z16, z16,
                         kick_vol=0.6, pad_note=60, pad_vol=0.25, reverb_mix=0.4, energy=0.1),
            make_section('BUILD', 4, _k4, z16, z16, _h1, _hv1, z16, _b1, _bn1,
                         bass_vol=0.35, hat_vol=0.2, pad_note=60, pad_vol=0.2, energy=0.3),
            make_section('BUILD+', 4, _k4, _sn, z16, _h2, _hv2, z16, _b1, _bn1,
                         bass_vol=0.5, hat_vol=0.25, energy=0.5),
            make_section('DROP', 8, _k4, _sn, _cl, _h2, _hv2, z16, _b1, _bn1,
                         _ld, _ln, bass_vol=0.6, lead_vol=0.3, hat_vol=0.3,
                         delay_mix=0.25, reverb_mix=0.2, energy=0.8),
            make_section('BREAK', 4, z16, z16, z16, z16, z16, z16, z16, z16,
                         pad_note=63, pad_vol=0.4, reverb_mix=0.5, energy=0.1),
            make_section('DROP2', 8, _k4, _sn, _cl, _h2, _hv2, z16, _b1, _bn1,
                         _ld, _ln, bass_vol=0.65, lead_vol=0.35, hat_vol=0.3,
                         delay_mix=0.25, reverb_mix=0.2, energy=0.8),
            make_section('OUTRO', 8, _k4, z16, z16, _h1, _hv1, z16, z16, z16,
                         hat_vol=0.15, pad_note=60, pad_vol=0.3, reverb_mix=0.4, energy=0.15),
        ]
    }


TRACKS = {
    'detroit': detroit_track,
    'berlin': berlin_track,
    'acid': acid_track,
    'minimal': minimal_track,
}


# ======================== RENDERER ========================

class TrackRenderer:
    def __init__(self, track_data):
        self.data = track_data
        self.bpm = track_data['bpm']
        self.sr = SR

        # Build instruments
        self.kick = Kick(**track_data['kick_cfg'])
        self.snare = Snare()
        self.clap = Clap()
        self.hat = HiHat()
        self.hat_open = HiHat()
        self.bass = Bass(**track_data['bass_cfg'])
        self.lead = Lead()
        self.pad = Pad()

        self.delay = Delay(time_sec=60.0 / self.bpm * 0.75, feedback=0.35, mix=0.0)
        self.reverb = SimpleReverb(mix=0.15)

        self.sample_pos = 0
        self._last_step = -1

    @property
    def samples_per_step(self):
        return self.sr * 60.0 / self.bpm / 4

    @property
    def total_bars(self):
        return sum(s['bars'] for s in self.data['sections'])

    @property
    def total_seconds(self):
        return self.total_bars * 4 * 60.0 / self.bpm

    def get_section_at_bar(self, bar):
        """Return the section active at the given bar number."""
        cumulative = 0
        for section in self.data['sections']:
            if bar < cumulative + section['bars']:
                return section, bar - cumulative
            cumulative += section['bars']
        return self.data['sections'][-1], 0

    def render_block(self, n):
        sps = self.samples_per_step

        for i in range(n):
            abs_pos = self.sample_pos + i
            step_int = int(abs_pos / sps)

            if step_int != self._last_step:
                self._last_step = step_int
                s = step_int % 16
                bar = step_int // 16
                section, _ = self.get_section_at_bar(bar)

                # Update FX
                self.delay.mix = section['delay_mix']
                self.reverb.mix = section['reverb_mix']

                # Trigger instruments
                if section['kick'][s]:
                    self.kick.trigger(section['kick_vol'])
                if section['snare'][s]:
                    self.snare.trigger(section['snare_vol'])
                if section['clap'][s]:
                    self.clap.trigger(section['clap_vol'])
                if section['hat'][s]:
                    vel = section['hat_vel'][s] if section['hat_vel'][s] > 0 else 0.7
                    self.hat.trigger(vel * section['hat_vol'] / 0.35)
                if section['oh'][s]:
                    self.hat_open.trigger(0.6, is_open=True)
                if section['bass'][s]:
                    note = section['bass_notes'][s]
                    if note > 0:
                        self.bass.trigger(note, section['bass_vol'])
                if section['lead'][s] and section['lead_vol'] > 0:
                    note = section['lead_notes'][s]
                    if note > 0:
                        self.lead.trigger(note, section['lead_vol'])
                if s == 0 and section.get('pad_note') and section['pad_vol'] > 0:
                    self.pad.trigger(section['pad_note'], section['pad_vol'])

        self.sample_pos += n

        # Render
        mix = np.zeros(n, dtype=np.float64)
        mix += self.kick.render(n) * 0.9
        mix += self.snare.render(n) * 0.6
        mix += self.clap.render(n) * 0.5
        mix += self.hat.render(n) * 0.35
        mix += self.hat_open.render(n) * 0.3
        mix += self.bass.render(n) * 0.7
        mix += self.lead.render(n) * 0.5
        mix += self.pad.render(n) * 0.5

        # FX
        mix = self.delay.process(mix)
        mix = self.reverb.process(mix)

        # Soft clip
        mix = np.tanh(mix * 0.85)
        return mix

    def render_full(self, progress_callback=None):
        """Render the entire track to a numpy array."""
        total_samples = int(self.total_seconds * self.sr)
        audio = np.zeros(total_samples, dtype=np.float64)
        block = 2048
        pos = 0
        while pos < total_samples:
            bs = min(block, total_samples - pos)
            audio[pos:pos+bs] = self.render_block(bs)
            pos += bs
            if progress_callback and pos % (block * 20) == 0:
                progress_callback(pos / total_samples)
        return audio

    def play_realtime(self):
        """Play track through speakers in real-time."""
        self.sample_pos = 0
        self._last_step = -1
        running = [True]

        def callback(outdata, frames, time_info, status):
            if not running[0]:
                outdata.fill(0)
                return
            total = int(self.total_seconds * self.sr)
            if self.sample_pos >= total:
                running[0] = False
                outdata.fill(0)
                return
            mix = self.render_block(frames)
            outdata[:, 0] = mix.astype(np.float32)
            outdata[:, 1] = mix.astype(np.float32)

        stream = sd.OutputStream(
            samplerate=self.sr, blocksize=BLOCK, channels=2,
            dtype='float32', callback=callback, latency='low',
        )

        total_bars = self.total_bars
        sps = self.samples_per_step

        with stream:
            while running[0]:
                bar = int(self.sample_pos / sps / 16)
                step = self._last_step % 16 if self._last_step >= 0 else 0
                section, _ = self.get_section_at_bar(min(bar, total_bars - 1))
                elapsed = self.sample_pos / self.sr
                total_sec = self.total_seconds

                # Display
                grid = ''
                for i in range(16):
                    if i % 4 == 0 and i > 0:
                        grid += '|'
                    grid += 'X' if i == step else '-'
                pct = elapsed / total_sec * 100

                mins = int(elapsed) // 60
                secs = int(elapsed) % 60
                t_mins = int(total_sec) // 60
                t_secs = int(total_sec) % 60

                print(f"\r  [{grid}] {section['name']:>8s}  "
                      f"{mins}:{secs:02d}/{t_mins}:{t_secs:02d}  "
                      f"{pct:5.1f}%  Bar {bar+1}/{total_bars} ", end='', flush=True)
                time.sleep(0.04)

        print(f"\r  {'':80}")
        print("  Track finished!")


def save_wav(audio, filename, sr=SR):
    """Save mono audio to stereo WAV."""
    os.makedirs(os.path.dirname(filename) or '.', exist_ok=True)
    peak = np.abs(audio).max()
    if peak > 0:
        audio = audio / peak * 0.92
    stereo = np.column_stack([audio, audio])
    data = (stereo * 32767).astype(np.int16)
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())


# ======================== MAIN ========================

def show_menu():
    print()
    print("  ========================================")
    print("  TECHNOBOX TRACK CREATOR")
    print("  ========================================")
    print()
    print("  Choose a track style:")
    print()
    print("    1) Detroit Techno  - 128 BPM - Deep & rolling")
    print("    2) Berlin Techno   - 140 BPM - Hard & industrial")
    print("    3) Acid Techno     - 138 BPM - 303 squelch")
    print("    4) Minimal Techno  - 125 BPM - Hypnotic & sparse")
    print()
    print("  What do you want to do?")
    print()
    print("    p) Preview (play through speakers)")
    print("    e) Export to WAV file")
    print("    b) Both (preview then export)")
    print("    q) Quit")
    print()


def main():
    # Handle --quick flag
    quick = '--quick' in sys.argv
    style_arg = None
    for arg in sys.argv[1:]:
        if arg.startswith('--style'):
            if '=' in arg:
                style_arg = arg.split('=')[1]
        elif arg in TRACKS and arg != '--quick':
            style_arg = arg

    if quick:
        style = style_arg or 'detroit'
        if style not in TRACKS:
            style = 'detroit'
        track_data = TRACKS[style]()
        renderer = TrackRenderer(track_data)
        filename = os.path.expanduser(f'~/technobox/exports/{track_data["name"].replace(" ", "_").lower()}.wav')
        print(f"\n  Generating: {track_data['name']} ({track_data['bpm']} BPM)")
        print(f"  Duration: {renderer.total_seconds:.0f}s ({renderer.total_bars} bars)")
        print(f"  Sections: {' > '.join(s['name'] for s in track_data['sections'])}")
        print(f"\n  Rendering...", end='', flush=True)

        def progress(pct):
            bars = int(pct * 30)
            print(f"\r  Rendering [{'#' * bars}{'-' * (30-bars)}] {pct*100:.0f}%", end='', flush=True)

        audio = renderer.render_full(progress)
        save_wav(audio, filename)
        print(f"\r  Rendering [{'#'*30}] 100%  ")
        print(f"\n  Saved: {filename}")
        print(f"  Size: {os.path.getsize(filename) / 1024 / 1024:.1f} MB")
        return

    # Interactive mode
    show_menu()

    style = 'detroit'
    action = 'b'

    try:
        choice = input("  Style [1-4]: ").strip()
        style = {'1': 'detroit', '2': 'berlin', '3': 'acid', '4': 'minimal'}.get(choice, 'detroit')

        action = input("  Action [p/e/b]: ").strip().lower()
        if action not in ('p', 'e', 'b'):
            action = 'b'
    except (KeyboardInterrupt, EOFError):
        print("\n  Bye!")
        return

    track_data = TRACKS[style]()
    renderer = TrackRenderer(track_data)

    print(f"\n  Track: {track_data['name']}")
    print(f"  BPM: {track_data['bpm']}")
    print(f"  Duration: {renderer.total_seconds:.0f}s ({renderer.total_bars} bars)")
    print(f"  Structure: {' > '.join(s['name'] for s in track_data['sections'])}")
    print()

    if action in ('p', 'b'):
        print("  Playing... (Ctrl-C to skip)\n")
        try:
            renderer.play_realtime()
        except KeyboardInterrupt:
            print("\n  Skipped playback.")

    if action in ('e', 'b'):
        # Re-render for clean export
        renderer2 = TrackRenderer(track_data)
        filename = os.path.expanduser(f'~/technobox/exports/{track_data["name"].replace(" ", "_").lower()}.wav')

        print(f"\n  Exporting...", end='', flush=True)

        def progress(pct):
            bars = int(pct * 30)
            print(f"\r  Exporting [{'#' * bars}{'-' * (30-bars)}] {pct*100:.0f}%", end='', flush=True)

        audio = renderer2.render_full(progress)
        save_wav(audio, filename)
        print(f"\r  Exporting [{'#'*30}] 100%  ")
        print(f"\n  Saved: {filename}")
        print(f"  Size: {os.path.getsize(filename) / 1024 / 1024:.1f} MB")
        print(f"\n  Open with: open {filename}")

    print()


if __name__ == '__main__':
    main()
