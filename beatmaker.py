#!/usr/bin/env python3
"""
TechnoBox Beat Maker - Tap in YOUR beats.

How it works:
  1. A 16-step loop plays
  2. You pick a track (kick, snare, hat, bass...)
  3. You tap number keys 1-8 to toggle steps ON/OFF while it plays
  4. Layer up tracks one by one
  5. Export your beat as a full track

Keys:
  SPACE      = play/stop
  TAB        = next track
  SHIFT+TAB  = prev track
  1-9,0,q-w  = toggle steps 1-16 (1=step1 ... 0=step10, q=11...w=16 -- WAIT this is confusing)

Actually simpler:
  a s d f  g h j k = toggle steps 1-8
  z x c v  b n m , = toggle steps 9-16

  TAB       = next track
  SHIFT+TAB = prev track
  +/-       = BPM
  SPACE     = play/stop
  G         = AI fill current track
  C         = clear current track
  E         = export WAV
  Q         = quit
"""
import sys
import os
import time
import wave
import tty
import termios
import threading
import numpy as np
import sounddevice as sd

SR = 48000
BLOCK = 2048


# ======================== SYNTH (same compact engine) ========================

class Kick:
    def __init__(self):
        self.phase = 0.0; self.t = 0; self.active = False
        self.pitch=50; self.pitch_amt=200; self.pitch_decay=0.04; self.decay=0.5; self.drive=2.0
    def trigger(self, vel=1.0):
        self.phase=0; self.t=0; self.active=True; self._v=vel
    def render(self, n):
        if not self.active: return np.zeros(n)
        t=(self.t+np.arange(n,dtype=np.float64))/SR; self.t+=n
        freq=self.pitch+self.pitch_amt*np.exp(-t/self.pitch_decay)
        ph=self.phase+np.cumsum(freq/SR); self.phase=ph[-1]
        sig=np.sin(2*np.pi*ph)+np.random.randn(n)*np.exp(-t/0.008)*0.3
        sig=np.tanh(sig*np.exp(-t/self.decay)*self._v*self.drive)
        if np.exp(-t[-1]/self.decay)<0.001: self.active=False
        return sig

class Snare:
    def __init__(self): self.t=0; self.active=False
    def trigger(self, vel=1.0): self.t=0; self.active=True; self._v=vel
    def render(self, n):
        if not self.active: return np.zeros(n)
        t=(self.t+np.arange(n,dtype=np.float64))/SR; self.t+=n
        body=np.sin(2*np.pi*np.cumsum(200*(1+.5*np.exp(-t/.01))/SR))*np.exp(-t/.1)*.4
        noise=np.random.randn(n)*np.exp(-t/.15)*.6
        if t[-1]>.5: self.active=False
        return (body+noise)*self._v

class Clap:
    def __init__(self): self.t=0; self.active=False
    def trigger(self, vel=1.0): self.t=0; self.active=True; self._v=vel
    def render(self, n):
        if not self.active: return np.zeros(n)
        t=(self.t+np.arange(n,dtype=np.float64))/SR; self.t+=n
        noise=np.random.randn(n)
        env=sum(((t>=o)&(t<o+.005)).astype(float)*np.exp(-(t-o)/.002)*.5 for o in [0,.01,.02,.035])
        env+=np.exp(-t/.12)*.3
        if t[-1]>.5: self.active=False
        return noise*env*self._v

class HiHat:
    def __init__(self):
        self.t=0; self.active=False; self._decay=.05
        self.freqs=[205.3,369.6,304.4,522.7,540.0,800.0]
    def trigger(self, vel=1.0, is_open=False):
        self.t=0; self.active=True; self._v=vel; self._decay=.25 if is_open else .05
    def render(self, n):
        if not self.active: return np.zeros(n)
        t=(self.t+np.arange(n,dtype=np.float64))/SR; self.t+=n
        metal=sum(np.sign(np.sin(2*np.pi*f*t)) for f in self.freqs)/len(self.freqs)
        sig=(metal*.6+np.random.randn(n)*.4)*np.exp(-t/self._decay)*self._v*.4
        if t[-1]>self._decay*8: self.active=False
        return sig

class Bass:
    def __init__(self):
        self.phase=0; self.freq=55; self.t=0; self.active=False; self._lp=0
        self.waveform='saw'; self.cutoff=800; self.env_mod=3000; self.drive=1.5
    def trigger(self, note, vel=1.0):
        self.freq=440*2**((note-69)/12); self.phase=0; self.t=0; self.active=True; self._v=vel
    def render(self, n):
        if not self.active: return np.zeros(n)
        t=(self.t+np.arange(n,dtype=np.float64))/SR; self.t+=n
        dt=self.freq/SR; ph=(self.phase+np.arange(n)*dt)%1; self.phase=(self.phase+n*dt)%1
        osc=(2*ph-1) if self.waveform=='saw' else np.where(ph<.5,1,-1)
        sub=np.sin(2*np.pi*(np.arange(n)*dt*.5)%1)*.3
        sig=osc*.7+sub
        fc=np.clip(self.cutoff+np.exp(-t/.15)*self.env_mod,20,SR*.45)
        alpha=1-np.exp(-2*np.pi*fc/SR)
        out=np.zeros(n); lp=self._lp
        for i in range(n): lp+=alpha[i]*(sig[i]-lp); out[i]=lp
        self._lp=lp
        out=np.tanh(out*np.exp(-t/.3)*self._v*self.drive)
        if np.exp(-t[-1]/.3)<.001: self.active=False
        return out

class Lead:
    def __init__(self): self.phase=0; self.freq=440; self.t=0; self.active=False; self._lp=0
    def trigger(self, note, vel=0.6):
        self.freq=440*2**((note-69)/12); self.t=0; self.active=True; self._v=vel; self.phase=0
    def render(self, n):
        if not self.active: return np.zeros(n)
        t=(self.t+np.arange(n,dtype=np.float64))/SR; self.t+=n
        dt=self.freq/SR
        ph1=(self.phase+np.arange(n)*dt)%1; ph2=(self.phase+np.arange(n)*dt*1.005)%1
        self.phase=(self.phase+n*dt)%1
        osc=(2*ph1-1)*.5+(2*ph2-1)*.5
        fc=2000+3000*np.exp(-t/.2); alpha=1-np.exp(-2*np.pi*fc/SR)
        out=np.zeros(n); lp=self._lp
        for i in range(n): lp+=alpha[i]*(osc[i]-lp); out[i]=lp
        self._lp=lp
        out*=np.exp(-t/.4)*self._v
        if np.exp(-t[-1]/.4)<.001: self.active=False
        return out


# ======================== GENRE PRESETS ========================

GENRES = {
    'detroit': {
        'name': 'Detroit Techno', 'bpm': 128,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],   # kick
            [0,0,0,0, .8,0,0,0, 0,0,0,0, .8,0,0,0],       # snare
            [0,0,0,0, .7,0,0,0, 0,0,0,0, .7,0,0,0],       # clap
            [0,0,.7,0, 0,0,.7,0, 0,0,.7,0, 0,0,.7,0],     # ch hat
            [0,0,0,0, 0,0,0,0, 0,0,.6,0, 0,0,0,0],        # oh hat
            [.8,0,0,.7, 0,0,.8,0, .8,0,0,.7, 0,0,0,0],    # bass
            [0]*16,                                          # lead
        ],
        'bass_notes': [36,0,0,36, 0,0,43,0, 36,0,0,36, 0,0,0,0],
        'lead_notes': [0]*16,
        'bass_cfg': {'waveform':'saw','cutoff':600,'env_mod':2500,'drive':1.5},
    },
    'berlin': {
        'name': 'Berlin Hard Techno', 'bpm': 140,
        'patterns': [
            [.9,0,0,0, .9,0,.7,0, .9,0,0,0, .9,0,0,.6],  # kick
            [0,0,0,0, 0,0,0,.7, 0,0,0,0, 0,0,.7,0],       # snare
            [0,0,0,0, .8,0,0,0, 0,0,0,0, .8,0,0,0],       # clap
            [.9,.4,.7,.4, .9,.4,.7,.4, .9,.4,.7,.4, .9,.4,.7,.4], # ch hat
            [0,0,0,0, 0,0,.5,0, 0,0,0,0, 0,0,.5,0],       # oh hat
            [.8,0,.7,0, 0,0,.8,0, .8,0,0,.7, 0,0,.8,0],   # bass
            [0]*16,
        ],
        'bass_notes': [33,0,34,0, 0,0,33,0, 33,0,0,36, 0,0,33,0],
        'lead_notes': [0]*16,
        'bass_cfg': {'waveform':'saw','cutoff':400,'env_mod':4000,'drive':2.5},
    },
    'acid': {
        'name': 'Acid Techno', 'bpm': 138,
        'patterns': [
            [.9,0,0,0, .9,0,0,.7, .9,0,0,0, .9,0,.7,0],  # kick
            [0,0,0,0, .8,0,0,0, 0,0,0,0, .8,0,0,0],       # snare
            [0,0,0,0, 0,0,0,0, .7,0,0,0, 0,0,0,0],        # clap
            [.8,0,.6,0, .8,0,.6,0, .8,0,.6,0, .8,0,.5,.4], # ch hat
            [0,0,0,0, 0,0,0,0, 0,0,.5,0, 0,0,0,0],        # oh hat
            [.8,0,.7,.8, 0,.7,.8,0, .7,.8,0,.7, 0,.8,0,.7],# bass
            [0]*16,
        ],
        'bass_notes': [36,0,39,41, 0,43,36,0, 39,36,0,43, 0,41,0,36],
        'lead_notes': [0]*16,
        'bass_cfg': {'waveform':'square','cutoff':500,'env_mod':5000,'drive':2.0},
    },
    'minimal': {
        'name': 'Minimal Techno', 'bpm': 125,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],    # kick
            [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,.6],        # snare
            [0,0,0,0, .6,0,0,0, 0,0,0,0, 0,0,0,0],        # clap
            [0,0,.5,0, 0,0,.5,0, 0,0,.5,0, 0,.3,.5,0],    # ch hat
            [0]*16,                                          # oh hat
            [.7,0,0,0, 0,0,0,0, .7,0,0,0, 0,0,.6,0],      # bass
            [0,0,.5,0, 0,0,0,0, 0,0,0,0, .5,0,0,0],       # lead
        ],
        'bass_notes': [36,0,0,0, 0,0,0,0, 43,0,0,0, 0,0,36,0],
        'lead_notes': [72,0,75,0, 0,0,0,0, 0,0,0,0, 77,0,0,0],
        'bass_cfg': {'waveform':'saw','cutoff':300,'env_mod':1200,'drive':1.2},
    },
    'afro': {
        'name': 'Afro House', 'bpm': 122,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],    # kick
            [0,0,0,0, .8,0,0,.4, 0,0,0,0, .8,0,.4,0],     # snare (ghost rimshot)
            [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],         # clap
            [0,.6,0,.6, 0,.6,0,.6, 0,.6,0,.6, 0,.6,0,.6],  # ch hat (offbeat)
            [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],         # oh hat
            [.7,0,0,0, 0,0,0,0, .7,0,0,0, 0,0,.6,0],      # bass (minimal)
            [0,0,.5,0, 0,.5,0,0, .5,0,0,.5, 0,0,.5,0],    # lead (conga/perc feel)
        ],
        'bass_notes': [36,0,0,0, 0,0,0,0, 43,0,0,0, 0,0,36,0],
        'lead_notes': [65,0,67,0, 0,65,0,0, 67,0,0,65, 0,0,67,0],
        'bass_cfg': {'waveform':'saw','cutoff':250,'env_mod':800,'drive':1.0},
    },
    'melodic': {
        'name': 'Melodic Techno', 'bpm': 124,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],    # kick
            [0,0,0,0, .7,0,0,0, 0,0,0,0, .7,0,0,0],       # snare
            [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],         # clap
            [.9,.5,.7,.5, .9,.5,.7,.5, .9,.5,.7,.5, .9,.5,.7,.5], # 16th hats
            [0,0,0,0, 0,0,0,0, .5,0,0,0, 0,0,0,0],        # oh hat
            [.7,0,0,0, 0,0,.6,0, .7,0,0,0, 0,.5,0,0],     # bass
            [.5,0,0,.4, 0,0,.5,0, 0,.4,0,0, .5,0,0,.4],   # lead (arp)
        ],
        'bass_notes': [36,0,0,0, 0,0,43,0, 36,0,0,0, 0,41,0,0],
        'lead_notes': [72,0,0,70, 0,0,72,0, 0,75,0,0, 77,0,0,72],
        'bass_cfg': {'waveform':'saw','cutoff':500,'env_mod':2000,'drive':1.3},
    },
    'ukgarage': {
        'name': 'UK Garage / 2-Step', 'bpm': 132,
        'patterns': [
            [.9,0,0,0, 0,0,.8,0, 0,.7,0,0, 0,0,.7,0],    # kick (broken!)
            [0,0,0,0, .8,0,0,0, 0,0,0,0, .8,0,0,0],       # snare
            [0,0,0,0, .6,0,0,0, 0,0,0,0, .6,0,0,0],       # clap
            [0,.7,0,.7, 0,.7,0,.7, 0,.7,0,.7, 0,.7,0,.7],  # ch hat (offbeat)
            [0,0,0,0, 0,0,0,0, 0,0,.5,0, 0,0,0,0],        # oh hat
            [.8,0,0,.6, 0,.5,0,0, .7,0,.5,0, 0,0,.6,0],   # bass (bouncy)
            [0]*16,
        ],
        'bass_notes': [36,0,0,38, 0,41,0,0, 43,0,41,0, 0,0,38,0],
        'lead_notes': [0]*16,
        'bass_cfg': {'waveform':'saw','cutoff':700,'env_mod':2000,'drive':1.3},
    },
    'trance': {
        'name': 'Uplifting Trance', 'bpm': 138,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],    # kick
            [0,0,0,0, .8,0,0,0, 0,0,0,0, .8,0,0,0],       # snare
            [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],         # clap
            [0,.7,0,.7, 0,.7,0,.7, 0,.7,0,.7, 0,.7,0,.7],  # offbeat oh
            [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],         # oh hat
            [0,.8,0,0, 0,.8,0,0, 0,.8,0,0, 0,.8,0,0],     # bass (anti-kick)
            [.5,0,.4,0, .5,0,.6,0, .5,0,.4,0, .6,0,.5,0], # lead (arp)
        ],
        'bass_notes': [36,36,0,0, 0,36,0,0, 0,43,0,0, 0,41,0,0],
        'lead_notes': [72,0,75,0, 72,0,77,0, 75,0,72,0, 77,0,75,0],
        'bass_cfg': {'waveform':'saw','cutoff':600,'env_mod':2500,'drive':1.5},
    },
    'deephouse': {
        'name': 'Deep House', 'bpm': 122,
        'patterns': [
            [.9,0,0,0, .9,0,0,0, .9,0,0,0, .9,0,0,0],    # kick
            [0,0,0,0, .7,0,0,.3, 0,0,0,0, .7,0,0,0],      # snare (ghost on 8)
            [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,0],         # clap
            [.7,0,.6,.5, .7,0,.6,.5, .7,0,.6,.5, .7,0,.6,.5], # ch hat (shuffle)
            [0,.5,0,0, 0,.5,0,0, 0,.5,0,0, 0,.5,0,0],     # oh hat (offbeat)
            [.8,0,0,0, .6,0,0,.5, .7,0,.5,0, 0,0,.6,0],   # bass (melodic)
            [0]*16,
        ],
        'bass_notes': [36,0,0,0, 43,0,0,41, 36,0,48,0, 0,0,43,0],
        'lead_notes': [0]*16,
        'bass_cfg': {'waveform':'saw','cutoff':350,'env_mod':1500,'drive':1.1},
    },
    'fredagain': {
        'name': 'Fred Again / Emotional', 'bpm': 128,
        'patterns': [
            [.7,0,0,0, 0,0,.6,0, 0,.6,0,0, 0,0,0,0],     # kick (sparse, broken)
            [0,0,0,0, .7,0,0,0, 0,0,0,0, .7,0,0,0],       # snare
            [0,0,0,0, .6,0,0,0, 0,0,0,0, .6,0,0,.4],      # clap
            [0,.5,0,.5, 0,.5,0,.5, 0,.5,0,.5, 0,.5,0,.5],  # ch hat (offbeat)
            [0,0,0,0, 0,0,0,0, 0,0,.4,0, 0,0,0,0],        # oh hat
            [.6,0,0,.5, 0,0,0,0, .6,0,0,0, 0,.4,0,0],     # bass (emotional)
            [.4,0,0,0, 0,.4,0,0, 0,0,.5,0, 0,0,0,.4],     # lead (melody)
        ],
        'bass_notes': [36,0,0,39, 0,0,0,0, 43,0,0,0, 0,41,0,0],
        'lead_notes': [72,0,0,0, 0,75,0,0, 0,0,77,0, 0,0,0,72],
        'bass_cfg': {'waveform':'saw','cutoff':500,'env_mod':1800,'drive':1.2},
    },
}

GENRE_KEYS = list(GENRES.keys())


# ======================== BEAT MAKER ========================

TRACK_NAMES = ['KICK', 'SNARE', 'CLAP', 'C.HAT', 'O.HAT', 'BASS', 'LEAD']
TRACK_COLORS = ['\033[91m', '\033[93m', '\033[95m', '\033[96m', '\033[94m', '\033[92m', '\033[97m']
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'

# Step toggle keys: a-k for steps 1-8, z-comma for steps 9-16
STEP_KEYS_TOP = 'asdfghjk'      # steps 1-8
STEP_KEYS_BOT = 'zxcvbnm,'      # steps 9-16

# Bass notes for step input (chromatic from C2)
BASS_NOTES_DEFAULT = [36,36,36,36, 36,36,36,36, 36,36,36,36, 36,36,36,36]
LEAD_NOTES_DEFAULT = [60,60,60,60, 60,60,60,60, 60,60,60,60, 60,60,60,60]

# Note keys for bass/lead
NOTE_MAP = {
    'a': 36, 'w': 37, 's': 38, 'e': 39, 'd': 40, 'f': 41, 't': 42,
    'g': 43, 'y': 44, 'h': 45, 'u': 46, 'j': 47, 'k': 48,
}
# Higher octave for lead
NOTE_MAP_LEAD = {k: v + 24 for k, v in NOTE_MAP.items()}


class BeatMaker:
    def __init__(self):
        self.bpm = 128
        self.patterns = [[0]*16 for _ in range(7)]  # 7 tracks x 16 steps (0=off, >0=velocity)
        self.bass_notes = BASS_NOTES_DEFAULT.copy()
        self.lead_notes = LEAD_NOTES_DEFAULT.copy()
        self.selected_track = 0
        self.playing = True
        self.running = True
        self.step = 0
        self.sample_pos = 0
        self._last_step = -1
        self.mode = 'step'  # 'step' or 'note'
        self.current_genre = 'none'
        self.export_count = 0

        # Instruments
        self.kick = Kick()
        self.snare = Snare()
        self.clap = Clap()
        self.ch_hat = HiHat()
        self.oh_hat = HiHat()
        self.bass = Bass()
        self.lead = Lead()

        # Volumes
        self.volumes = [0.9, 0.6, 0.5, 0.35, 0.3, 0.7, 0.5]

    def load_genre(self, genre_key):
        """Load a genre preset into all tracks."""
        if genre_key not in GENRES:
            return
        g = GENRES[genre_key]
        self.current_genre = genre_key
        self.bpm = g['bpm']
        for i in range(7):
            self.patterns[i] = [float(v) for v in g['patterns'][i]]
        self.bass_notes = list(g['bass_notes'])
        self.lead_notes = list(g['lead_notes'])
        # Apply bass config
        for k, v in g.get('bass_cfg', {}).items():
            if hasattr(self.bass, k):
                setattr(self.bass, k, v)

    @property
    def samples_per_step(self):
        return SR * 60.0 / self.bpm / 4

    def audio_callback(self, outdata, frames, time_info, status):
        if not self.playing:
            outdata.fill(0)
            return
        sps = self.samples_per_step
        for i in range(frames):
            s = int((self.sample_pos + i) / sps)
            if s != self._last_step:
                self._last_step = s
                self.step = s % 16
                p = self.patterns
                st = self.step
                if p[0][st]: self.kick.trigger(p[0][st])
                if p[1][st]: self.snare.trigger(p[1][st])
                if p[2][st]: self.clap.trigger(p[2][st])
                if p[3][st]: self.ch_hat.trigger(p[3][st])
                if p[4][st]: self.oh_hat.trigger(p[4][st], is_open=True)
                if p[5][st]: self.bass.trigger(self.bass_notes[st], p[5][st])
                if p[6][st]: self.lead.trigger(self.lead_notes[st], p[6][st])
        self.sample_pos += frames

        mix = np.zeros(frames, dtype=np.float64)
        mix += self.kick.render(frames) * self.volumes[0]
        mix += self.snare.render(frames) * self.volumes[1]
        mix += self.clap.render(frames) * self.volumes[2]
        mix += self.ch_hat.render(frames) * self.volumes[3]
        mix += self.oh_hat.render(frames) * self.volumes[4]
        mix += self.bass.render(frames) * self.volumes[5]
        mix += self.lead.render(frames) * self.volumes[6]
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

    def ai_fill(self):
        """Auto-generate pattern for current track."""
        rng = np.random.default_rng()
        track = self.selected_track
        if track == 0:  # kick - four on floor
            self.patterns[0] = [0.9,0,0,0, 0.9,0,0,0, 0.9,0,0,0, 0.9,0,0,0]
        elif track == 1:  # snare
            self.patterns[1] = [0,0,0,0, 0.8,0,0,0, 0,0,0,0, 0.8,0,0,0]
        elif track == 2:  # clap
            self.patterns[2] = [0,0,0,0, 0.7,0,0,0, 0,0,0,0, 0.7,0,0,0]
        elif track == 3:  # closed hat
            p = [0.0]*16
            for i in range(16):
                if i % 2 == 0:
                    p[i] = 0.8
                elif rng.random() < 0.4:
                    p[i] = 0.4
            self.patterns[3] = p
        elif track == 4:  # open hat
            p = [0.0]*16
            for i in [2, 6, 10, 14]:
                if rng.random() < 0.4:
                    p[i] = 0.6
            self.patterns[4] = p
        elif track == 5:  # bass
            p = [0.0]*16
            notes = [36, 36, 36, 36, 36, 36, 36, 36, 36, 36, 36, 36, 36, 36, 36, 36]
            scale = [36, 38, 39, 41, 43, 44, 46, 48]
            for i in range(16):
                if rng.random() < 0.5:
                    p[i] = 0.7 + rng.random() * 0.3
                    notes[i] = rng.choice(scale)
            self.patterns[5] = p
            self.bass_notes = notes
        elif track == 6:  # lead
            p = [0.0]*16
            notes = LEAD_NOTES_DEFAULT.copy()
            scale = [60, 62, 63, 65, 67, 68, 70, 72]
            for i in range(16):
                if rng.random() < 0.3:
                    p[i] = 0.6
                    notes[i] = rng.choice(scale)
            self.patterns[6] = p
            self.lead_notes = notes

    def display(self):
        # Clear screen and draw
        lines = []
        lines.append('')
        genre_label = GENRES[self.current_genre]['name'] if self.current_genre in GENRES else 'Custom'
        lines.append(f'  {BOLD}TECHNOBOX BEAT MAKER{RESET}   BPM: {self.bpm}   {"▶ PLAYING" if self.playing else "■ STOPPED"}   [{genre_label}]')
        lines.append(f'  Track: {TRACK_COLORS[self.selected_track]}{BOLD}{TRACK_NAMES[self.selected_track]}{RESET}')
        lines.append('')

        # Step numbers
        nums = '  STEP  '
        for i in range(16):
            if i == 8:
                nums += ' '
            nums += f'{i+1:>2} '
        lines.append(f'{DIM}{nums}{RESET}')

        # Key hints
        keys = '  KEYS  '
        key_labels = list(STEP_KEYS_TOP) + list(STEP_KEYS_BOT)
        for i, k in enumerate(key_labels):
            if i == 8:
                keys += ' '
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
                if i == 8:
                    row += '│'
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
        if self.selected_track == 5:
            note_names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
            nr = '  NOTE  '
            for i in range(16):
                if i == 8: nr += ' '
                if self.patterns[5][i] > 0:
                    n = self.bass_notes[i]
                    nr += f'{note_names[n%12]:>2} '
                else:
                    nr += '   '
            lines.append(f'{DIM}{nr}{RESET}')
        elif self.selected_track == 6:
            note_names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
            nr = '  NOTE  '
            for i in range(16):
                if i == 8: nr += ' '
                if self.patterns[6][i] > 0:
                    n = self.lead_notes[i]
                    nr += f'{note_names[n%12]:>2} '
                else:
                    nr += '   '
            lines.append(f'{DIM}{nr}{RESET}')

        lines.append('')
        lines.append(f'  {DIM}STEP KEYS: a s d f g h j k (1-8)  z x c v b n m , (9-16){RESET}')
        lines.append(f'  {DIM}TAB=next track  SPACE=play/stop  +/-=BPM  G=AI fill  C=clear{RESET}')
        if self.selected_track >= 5:
            lines.append(f'  {DIM}UP/DOWN=change note  [ ]=octave shift{RESET}')
        lines.append(f'  {DIM}GENRES (Shift+Number):{RESET}')
        lines.append(f'  {DIM}!=Detroit @=Berlin #=Acid $=Minimal %=Afro ^=Melodic{RESET}')
        lines.append(f'  {DIM}&=UKGarage *=Trance (=DeepHouse )=FredAgain{RESET}')
        lines.append(f'  {DIM}E=export WAV  Q=quit{RESET}')

        # Move cursor up and redraw
        output = '\033[H'  # home
        output += '\n'.join(lines)
        output += '\n' * 3  # padding
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
        elif ch == '`':  # backtick = prev track
            self.selected_track = (self.selected_track - 1) % 7

        # Transport
        elif ch == ' ':
            self.playing = not self.playing
            if not self.playing:
                self.sample_pos = 0
                self._last_step = -1
        elif ch in ('+', '='):
            self.bpm = min(200, self.bpm + 2)
        elif ch in ('-', '_'):
            self.bpm = max(80, self.bpm - 2)

        # AI
        elif ch in ('G',):  # capital G only for AI
            self.ai_fill()

        # Clear
        elif ch in ('C',):  # capital C only
            self.clear_track()

        # Load genre (0-9 for genres)
        elif ch == '!':  # shift+1
            self.load_genre('detroit')
        elif ch == '@':  # shift+2
            self.load_genre('berlin')
        elif ch == '#':  # shift+3
            self.load_genre('acid')
        elif ch == '$':  # shift+4
            self.load_genre('minimal')
        elif ch == '%':  # shift+5
            self.load_genre('afro')
        elif ch == '^':  # shift+6
            self.load_genre('melodic')
        elif ch == '&':  # shift+7
            self.load_genre('ukgarage')
        elif ch == '*':  # shift+8
            self.load_genre('trance')
        elif ch == '(':  # shift+9
            self.load_genre('deephouse')
        elif ch == ')':  # shift+0
            self.load_genre('fredagain')

        # Note editing for bass/lead
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

        # Note up/down at current step
        elif ch == '\x1b':
            # Escape sequence - read more
            return 'escape'

        # Export
        elif ch in ('E',):
            return 'export'

        # Quit
        elif ch in ('Q', 'q'):
            return 'quit'

        return None

    def export(self):
        """Export beat as WAV with unique filename."""
        import datetime
        ts = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        genre_tag = self.current_genre if self.current_genre != 'none' else 'custom'
        filename = os.path.expanduser(f'~/technobox/exports/beat_{genre_tag}_{ts}.wav')
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        print(f'\n  Exporting 8 bars to {filename}...')

        # Render 8 bars
        bars = 8
        total_steps = 16 * bars
        total_samples = int(total_steps * self.samples_per_step)
        audio = np.zeros(total_samples, dtype=np.float64)

        # Create fresh instruments
        kick=Kick(); snare=Snare(); clap=Clap()
        ch=HiHat(); oh=HiHat(); bass=Bass(); lead=Lead()
        bass.waveform=self.bass.waveform; bass.cutoff=self.bass.cutoff
        bass.env_mod=self.bass.env_mod; bass.drive=self.bass.drive

        pos = 0
        sps = self.samples_per_step
        last_step = -1
        block = 2048

        while pos < total_samples:
            bs = min(block, total_samples - pos)
            for i in range(bs):
                s = int((pos + i) / sps)
                if s != last_step:
                    last_step = s
                    st = s % 16
                    p = self.patterns
                    if p[0][st]: kick.trigger(p[0][st])
                    if p[1][st]: snare.trigger(p[1][st])
                    if p[2][st]: clap.trigger(p[2][st])
                    if p[3][st]: ch.trigger(p[3][st])
                    if p[4][st]: oh.trigger(p[4][st], is_open=True)
                    if p[5][st]: bass.trigger(self.bass_notes[st], p[5][st])
                    if p[6][st]: lead.trigger(self.lead_notes[st], p[6][st])

            mix = np.zeros(bs, dtype=np.float64)
            mix += kick.render(bs)*self.volumes[0]
            mix += snare.render(bs)*self.volumes[1]
            mix += clap.render(bs)*self.volumes[2]
            mix += ch.render(bs)*self.volumes[3]
            mix += oh.render(bs)*self.volumes[4]
            mix += bass.render(bs)*self.volumes[5]
            mix += lead.render(bs)*self.volumes[6]
            mix = np.tanh(mix * 0.85)
            audio[pos:pos+bs] = mix
            pos += bs

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

        size = os.path.getsize(filename) / 1024 / 1024
        print(f'  Done! {size:.1f} MB')
        print(f'  Play it: open {filename}')
        time.sleep(2)

    def run(self):
        # Clear screen
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

                # Non-blocking read with timeout
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
            sys.stdout.write('\033[?25h')  # show cursor
            print('\n  Bye!\n')


if __name__ == '__main__':
    maker = BeatMaker()
    maker.run()
