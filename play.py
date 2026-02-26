#!/usr/bin/env python3
"""
TechnoBox - Just play a beat. No UI, no BS.
Usage: python3 play.py [style]
Styles: detroit, berlin, acid, minimal
"""
import sys
import time
import threading
import numpy as np
import sounddevice as sd

SR = 48000
BLOCK = 2048


# ============ FAST SYNTH ENGINE (vectorized, no slow loops) ============

class Kick:
    def __init__(self):
        self.phase = 0.0
        self.env = 0.0
        self.click_env = 0.0
        self.t = 0
        self.active = False
        self.pitch = 50.0
        self.pitch_amt = 200.0
        self.pitch_decay = 0.04
        self.decay = 0.6
        self.drive = 2.0

    def trigger(self, vel=1.0):
        self.phase = 0.0
        self.t = 0
        self.env = vel
        self.click_env = vel
        self.active = True

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n
        freq = self.pitch + self.pitch_amt * np.exp(-t / self.pitch_decay)
        phase = self.phase + np.cumsum(freq / SR)
        self.phase = phase[-1]
        body = np.sin(2 * np.pi * phase)
        amp = np.exp(-t / self.decay)
        click = np.random.randn(n) * np.exp(-t / 0.008) * 0.3
        sig = (body + click) * amp
        sig = np.tanh(sig * self.drive)
        if amp[-1] < 0.001:
            self.active = False
        return sig


class Snare:
    def __init__(self):
        self.t = 0
        self.active = False
        self.vel = 0.0

    def trigger(self, vel=1.0):
        self.t = 0
        self.vel = vel
        self.active = True

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n
        freq = 200 * (1 + 0.5 * np.exp(-t / 0.01))
        body = np.sin(2 * np.pi * np.cumsum(freq / SR)) * np.exp(-t / 0.1) * 0.4
        noise = np.random.randn(n) * np.exp(-t / 0.15) * 0.6
        sig = (body + noise) * self.vel
        if np.exp(-t[-1] / 0.15) < 0.001:
            self.active = False
        return sig


class HiHat:
    def __init__(self):
        self.t = 0
        self.active = False
        self.vel = 0.0
        self.decay = 0.05
        self.freqs = [205.3, 369.6, 304.4, 522.7, 540.0, 800.0]

    def trigger(self, vel=1.0, open_hat=False):
        self.t = 0
        self.vel = vel
        self.decay = 0.25 if open_hat else 0.05
        self.active = True

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n
        metal = np.zeros(n)
        for f in self.freqs:
            metal += np.sign(np.sin(2 * np.pi * f * t))
        metal /= len(self.freqs)
        noise = np.random.randn(n)
        sig = (metal * 0.6 + noise * 0.4) * np.exp(-t / self.decay) * self.vel * 0.4
        if np.exp(-t[-1] / self.decay) < 0.001:
            self.active = False
        return sig


class Clap:
    def __init__(self):
        self.t = 0
        self.active = False
        self.vel = 0.0

    def trigger(self, vel=1.0):
        self.t = 0
        self.vel = vel
        self.active = True

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n
        noise = np.random.randn(n)
        bursts = np.zeros(n)
        for offset in [0, 0.01, 0.02, 0.035]:
            mask = (t >= offset) & (t < offset + 0.005)
            bursts += mask * np.exp(-(t - offset) / 0.002) * 0.5
        tail = np.exp(-t / 0.12) * 0.3
        sig = noise * (bursts + tail) * self.vel
        if np.exp(-t[-1] / 0.12) < 0.001:
            self.active = False
        return sig


class Bass:
    def __init__(self):
        self.phase = 0.0
        self.freq = 55.0
        self.target_freq = 55.0
        self.t = 0
        self.active = False
        self.vel = 0.0
        self.cutoff = 800.0
        self.resonance = 2.5
        self.env_mod = 3000.0
        self.drive = 1.5
        self.waveform = 'saw'
        # Simple filter state
        self._lp = 0.0

    def trigger(self, note, vel=1.0):
        self.target_freq = 440.0 * 2 ** ((note - 69) / 12.0)
        self.freq = self.target_freq
        self.phase = 0.0
        self.t = 0
        self.vel = vel
        self.active = True

    def release(self):
        pass  # decay handles it

    def render(self, n):
        if not self.active:
            return np.zeros(n)
        t = (self.t + np.arange(n, dtype=np.float64)) / SR
        self.t += n

        # Oscillator
        dt = self.freq / SR
        phases = (self.phase + np.arange(n) * dt) % 1.0
        self.phase = (self.phase + n * dt) % 1.0
        if self.waveform == 'saw':
            osc = 2.0 * phases - 1.0
        else:
            osc = np.where(phases < 0.5, 1.0, -1.0)

        # Sub
        sub_phases = (np.arange(n) * dt * 0.5) % 1.0
        sub = np.sin(2 * np.pi * sub_phases) * 0.3

        sig = osc * 0.7 + sub

        # Simple filter envelope (vectorized one-pole LPF)
        env = np.exp(-t / 0.15)
        fc = self.cutoff + env * self.env_mod
        fc = np.clip(fc, 20, SR * 0.45)
        # One-pole lowpass (fast, vectorized-ish)
        alpha = 1.0 - np.exp(-2.0 * np.pi * fc / SR)
        out = np.zeros(n)
        lp = self._lp
        for i in range(n):
            lp += alpha[i] * (sig[i] - lp)
            out[i] = lp
        self._lp = lp

        # Amp envelope
        amp = np.exp(-t / 0.3) * self.vel
        out *= amp

        # Drive
        out = np.tanh(out * self.drive)

        if amp[-1] < 0.001:
            self.active = False
        return out


# ============ PATTERN + STYLES ============

STYLES = {
    'detroit': {
        'bpm': 128, 'swing': 0.0,
        'kick_pattern':    [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0],
        'snare_pattern':   [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0],
        'hat_pattern':     [0,0,1,0, 0,0,1,0, 0,0,1,0, 0,0,1,0],
        'hat_vel':         [0,0,.7,0, 0,0,.7,0, 0,0,.7,0, 0,0,.7,0],
        'clap_pattern':    [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0],
        'bass_pattern':    [1,0,0,1, 0,0,1,0, 1,0,0,1, 0,0,0,0],
        'bass_notes':      [36,0,0,36, 0,0,43,0, 36,0,0,36, 0,0,0,0],
        'bass': {'cutoff': 600, 'resonance': 2.0, 'env_mod': 2500, 'drive': 1.5, 'waveform': 'saw'},
        'kick': {'pitch': 50, 'decay': 0.5, 'drive': 2.0, 'pitch_amt': 180},
    },
    'berlin': {
        'bpm': 140, 'swing': 0.0,
        'kick_pattern':    [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0],
        'snare_pattern':   [0,0,0,0, 0,0,0,1, 0,0,0,0, 0,0,1,0],
        'hat_pattern':     [1,1,1,1, 1,1,1,1, 1,1,1,1, 1,1,1,1],
        'hat_vel':         [.9,.4,.7,.4, .9,.4,.7,.4, .9,.4,.7,.4, .9,.4,.7,.4],
        'clap_pattern':    [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0],
        'bass_pattern':    [1,0,1,0, 0,0,1,0, 1,0,0,1, 0,0,1,0],
        'bass_notes':      [33,0,34,0, 0,0,33,0, 33,0,0,36, 0,0,33,0],
        'bass': {'cutoff': 400, 'resonance': 3.0, 'env_mod': 4000, 'drive': 2.5, 'waveform': 'saw'},
        'kick': {'pitch': 45, 'decay': 0.4, 'drive': 3.5, 'pitch_amt': 250},
    },
    'acid': {
        'bpm': 138, 'swing': 0.05,
        'kick_pattern':    [1,0,0,0, 1,0,0,1, 1,0,0,0, 1,0,1,0],
        'snare_pattern':   [0,0,0,0, 1,0,0,0, 0,0,0,0, 1,0,0,0],
        'hat_pattern':     [1,0,1,0, 1,0,1,0, 1,0,1,0, 1,0,1,1],
        'hat_vel':         [.8,0,.6,0, .8,0,.6,0, .8,0,.6,0, .8,0,.5,.4],
        'clap_pattern':    [0,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,0,0],
        'bass_pattern':    [1,0,1,1, 0,1,1,0, 1,1,0,1, 0,1,0,1],
        'bass_notes':      [36,0,39,41, 0,43,36,0, 39,36,0,43, 0,41,0,36],
        'bass': {'cutoff': 500, 'resonance': 3.8, 'env_mod': 5000, 'drive': 2.0, 'waveform': 'square'},
        'kick': {'pitch': 52, 'decay': 0.45, 'drive': 2.0, 'pitch_amt': 200},
    },
    'minimal': {
        'bpm': 125, 'swing': 0.12,
        'kick_pattern':    [1,0,0,0, 1,0,0,0, 1,0,0,0, 1,0,0,0],
        'snare_pattern':   [0,0,0,0, 0,0,0,0, 0,0,0,0, 0,0,0,1],
        'hat_pattern':     [0,0,1,0, 0,0,1,0, 0,0,1,0, 0,1,1,0],
        'hat_vel':         [0,0,.5,0, 0,0,.5,0, 0,0,.5,0, 0,.3,.5,0],
        'clap_pattern':    [0,0,0,0, 1,0,0,0, 0,0,0,0, 0,0,0,0],
        'bass_pattern':    [1,0,0,0, 0,0,0,0, 1,0,0,0, 0,0,1,0],
        'bass_notes':      [36,0,0,0, 0,0,0,0, 43,0,0,0, 0,0,36,0],
        'bass': {'cutoff': 300, 'resonance': 1.0, 'env_mod': 1200, 'drive': 1.2, 'waveform': 'saw'},
        'kick': {'pitch': 55, 'decay': 0.6, 'drive': 1.5, 'pitch_amt': 150},
    },
}


class BeatPlayer:
    def __init__(self, style='detroit'):
        self.style_name = style
        self.style = STYLES[style]
        self.bpm = self.style['bpm']
        self.step = 0
        self.sample_pos = 0

        # Instruments
        self.kick = Kick()
        self.snare = Snare()
        self.hat = HiHat()
        self.hat_open = HiHat()
        self.clap = Clap()
        self.bass = Bass()

        # Apply style
        for k, v in self.style.get('kick', {}).items():
            setattr(self.kick, k, v)
        for k, v in self.style.get('bass', {}).items():
            setattr(self.bass, k, v)

        self.running = True
        self._last_step = -1

    @property
    def samples_per_step(self):
        return SR * 60.0 / self.bpm / 4  # 16th notes

    def render(self, outdata, frames, time_info, status):
        out = np.zeros(frames, dtype=np.float64)
        sps = self.samples_per_step
        swing = self.style.get('swing', 0.0)

        # Check for step triggers within this block
        for i in range(frames):
            abs_pos = self.sample_pos + i
            step_float = abs_pos / sps
            step_int = int(step_float)

            # Swing: delay odd steps
            if step_int % 2 == 1:
                boundary = int(step_int * sps + swing * sps)
            else:
                boundary = int(step_int * sps)

            if abs_pos == boundary and step_int != self._last_step:
                self._last_step = step_int
                s = step_int % 16

                # Trigger instruments
                if self.style['kick_pattern'][s]:
                    self.kick.trigger(0.9)
                if self.style['snare_pattern'][s]:
                    self.snare.trigger(0.8)
                if self.style['hat_pattern'][s]:
                    vel = self.style['hat_vel'][s] if self.style['hat_vel'][s] > 0 else 0.7
                    self.hat.trigger(vel)
                if self.style['clap_pattern'][s]:
                    self.clap.trigger(0.8)
                if self.style['bass_pattern'][s]:
                    note = self.style['bass_notes'][s]
                    if note > 0:
                        self.bass.trigger(note, 0.8)

        self.sample_pos += frames

        # Render all
        mix = np.zeros(frames, dtype=np.float64)
        mix += self.kick.render(frames) * 0.9
        mix += self.snare.render(frames) * 0.6
        mix += self.hat.render(frames) * 0.35
        mix += self.clap.render(frames) * 0.5
        mix += self.bass.render(frames) * 0.7

        # Simple master: soft clip
        mix = np.tanh(mix * 0.8)

        # Stereo
        outdata[:, 0] = mix.astype(np.float32)
        outdata[:, 1] = mix.astype(np.float32)

    def play(self):
        style_display = {
            'detroit': 'DETROIT TECHNO  |  128 BPM  |  Deep & Rolling',
            'berlin':  'BERLIN TECHNO   |  140 BPM  |  Hard & Industrial',
            'acid':    'ACID TECHNO     |  138 BPM  |  303 Squelch',
            'minimal': 'MINIMAL TECHNO  |  125 BPM  |  Hypnotic & Sparse',
        }

        print()
        print("  ========================================")
        print("  ████████ ███████  ██████ ██   ██ ███   ██  ██████  ██████   ██████  ██   ██")
        print("     ██    ██      ██      ██   ██ ████  ██ ██    ██ ██   ██ ██    ██  ██ ██ ")
        print("     ██    █████   ██      ███████ ██ ██ ██ ██    ██ ██████  ██    ██   ███  ")
        print("     ██    ██      ██      ██   ██ ██  ████ ██    ██ ██   ██ ██    ██  ██ ██ ")
        print("     ██    ███████  ██████ ██   ██ ██   ███  ██████  ██████   ██████  ██   ██")
        print("  ========================================")
        print()
        print(f"  >> {style_display.get(self.style_name, self.style_name)}")
        print()
        print("  Controls:")
        print("    1 = Detroit  |  2 = Berlin  |  3 = Acid  |  4 = Minimal")
        print("    + = BPM up   |  - = BPM down")
        print("    q = Quit")
        print()
        print("  PLAYING... ", end='', flush=True)

        stream = sd.OutputStream(
            samplerate=SR,
            blocksize=BLOCK,
            channels=2,
            dtype='float32',
            callback=self.render,
            latency='low',
        )

        with stream:
            try:
                while self.running:
                    # Show step indicator
                    step = self._last_step % 16
                    bar = ''
                    for i in range(16):
                        if i % 4 == 0 and i > 0:
                            bar += '|'
                        if i == step:
                            bar += 'X'
                        elif self.style['kick_pattern'][i]:
                            bar += 'o'
                        else:
                            bar += '-'
                    bpm_str = f" BPM:{self.bpm}"
                    print(f"\r  [{bar}]{bpm_str} ", end='', flush=True)
                    time.sleep(0.05)
            except KeyboardInterrupt:
                pass

        print("\n\n  Stopped.")


def main():
    style = 'detroit'
    if len(sys.argv) > 1:
        s = sys.argv[1].lower()
        if s in STYLES:
            style = s
        else:
            print(f"Unknown style '{s}'. Options: detroit, berlin, acid, minimal")
            sys.exit(1)

    player = BeatPlayer(style)

    # Keyboard input thread
    def input_loop():
        import tty
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while player.running:
                ch = sys.stdin.read(1)
                if ch == 'q' or ch == 'Q':
                    player.running = False
                elif ch == '1':
                    switch_style(player, 'detroit')
                elif ch == '2':
                    switch_style(player, 'berlin')
                elif ch == '3':
                    switch_style(player, 'acid')
                elif ch == '4':
                    switch_style(player, 'minimal')
                elif ch == '+' or ch == '=':
                    player.bpm = min(200, player.bpm + 2)
                elif ch == '-' or ch == '_':
                    player.bpm = max(80, player.bpm - 2)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

    def switch_style(player, new_style):
        player.style_name = new_style
        player.style = STYLES[new_style]
        player.bpm = player.style['bpm']
        for k, v in player.style.get('kick', {}).items():
            setattr(player.kick, k, v)
        for k, v in player.style.get('bass', {}).items():
            setattr(player.bass, k, v)

    t = threading.Thread(target=input_loop, daemon=True)
    t.start()
    player.play()


if __name__ == '__main__':
    main()
