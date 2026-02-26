import numpy as np
import os
import curses

from .audio.engine import AudioEngine
from .audio.clock import TransportClock
from .audio.mixer import Mixer
from .instruments.drum_machine import DrumMachine
from .instruments.bass_synth import BassSynth
from .instruments.lead_synth import LeadSynth
from .instruments.pad_synth import PadSynth
from .sequencer.transport import Transport
from .sequencer.pattern import Pattern
from .ai.pattern_gen import PatternGenerator
from .ai.variation import VariationEngine
from .ai.suggestions import SuggestionEngine
from .ai.style_presets import STYLES, STYLE_NAMES
from .io.wav_export import export_wav
from .io.project import save_project, load_project
from .ui.terminal import TerminalUI


class TechnoBoxApp:
    """Main application controller - wires audio, instruments, sequencer, and UI."""

    def __init__(self, sr=48000, block_size=1024):
        self.sr = sr
        self.block_size = block_size

        # Audio engine
        self.engine = AudioEngine(sr, block_size)
        self.engine.render_callback = self._render_block

        # Clock
        self.clock = TransportClock(bpm=130, sr=sr, block_size=block_size)

        # Instruments
        self.drums = DrumMachine(sr)
        self.bass = BassSynth(sr)
        self.lead = LeadSynth(sr)
        self.pad = PadSynth(sr)

        # Mixer
        self.mixer = Mixer(sr)
        self.mixer.init_tracks([
            'kick', 'snare', 'clap', 'closed_hat', 'open_hat',
            'tom_lo', 'tom_hi', 'rimshot', 'bass', 'lead', 'pad'
        ])

        # Sequencer
        self.transport = Transport()

        # AI
        self.current_style = 'detroit'
        self.pattern_gen = PatternGenerator(self.current_style)
        self.variation_engine = VariationEngine()
        self.suggestion_engine = SuggestionEngine()

        # UI
        self.ui = TerminalUI(self)

        # State
        self._last_step = -1
        self._bass_release_countdown = 0
        self._lead_release_countdown = 0
        self._pad_release_countdown = 0

        # Apply initial style and auto-generate a beat
        self._apply_style(self.current_style)
        self.ai_generate()
        self.clock.playing = True
        self.engine.state.playing = True

    def run(self):
        """Start the application."""
        self.engine.start()
        try:
            curses.wrapper(self.ui.run)
        finally:
            self.engine.stop()

    def _render_block(self, block_size):
        """Called by the audio engine render thread. Synthesizes one block of audio."""
        pattern = self.transport.current_pattern

        # Advance clock
        triggers = self.clock.advance(block_size)

        # Process step triggers
        for step_idx, sample_offset in triggers:
            self.engine.state.current_step = step_idx

            step_triggers = pattern.get_triggers_at_step(step_idx)

            for track_name, step in step_triggers.items():
                if track_name in DrumMachine.VOICE_NAMES:
                    self.drums.trigger_voice(track_name, step.velocity)
                elif track_name == 'bass':
                    self.bass.trigger(step.note, step.velocity, step.accent)
                    self._bass_release_countdown = int(self.clock.samples_per_step * 0.8)
                elif track_name == 'lead':
                    self.lead.trigger(step.note, step.velocity)
                    self._lead_release_countdown = int(self.clock.samples_per_step * 0.7)
                elif track_name == 'pad':
                    self.pad.trigger(step.note, step.velocity)
                    self._pad_release_countdown = int(self.clock.samples_per_step * 4)

        # Handle note releases
        self._bass_release_countdown -= block_size
        if self._bass_release_countdown <= 0 and self._bass_release_countdown > -block_size:
            self.bass.release()

        self._lead_release_countdown -= block_size
        if self._lead_release_countdown <= 0 and self._lead_release_countdown > -block_size:
            self.lead.release_all()

        self._pad_release_countdown -= block_size
        if self._pad_release_countdown <= 0 and self._pad_release_countdown > -block_size:
            self.pad.release_all()

        # Render instruments
        drums_out = self.drums.render(block_size)
        bass_out = self.bass.render(block_size)
        lead_out = self.lead.render(block_size)
        pad_out = self.pad.render(block_size)

        # Split drum outputs for per-track mixing
        track_outputs = {
            'drums_stereo': drums_out,
            'bass': bass_out,
            'lead': lead_out,
            'pad': pad_out,
        }

        # Simple mix (drums already stereo panned internally)
        stereo = np.zeros((block_size, 2), dtype=np.float64)
        stereo += drums_out * self.mixer.master.master_volume
        stereo += bass_out * self.mixer.track_volumes.get('bass', 0.8)
        stereo += lead_out * self.mixer.track_volumes.get('lead', 0.8)
        stereo += pad_out * self.mixer.track_volumes.get('pad', 0.8)

        # Master processing
        stereo = self.mixer.master.process(stereo)

        return stereo

    # --- Transport controls ---

    def toggle_play(self):
        self.clock.playing = not self.clock.playing
        if not self.clock.playing:
            self.clock.reset()
            self.bass.release()
            self.lead.release_all()
            self.pad.release_all()
        self.engine.state.playing = self.clock.playing

    def set_bpm(self, bpm):
        self.clock.bpm = max(60, min(200, bpm))
        self.engine.state.bpm = self.clock.bpm
        self.mixer.master.delay.set_tempo_sync(self.clock.bpm)

    # --- AI controls ---

    def ai_generate(self):
        """Generate a new pattern using AI."""
        pattern = self.transport.current_pattern
        gen = self.pattern_gen.generate_full_pattern(pattern.length)

        for track_name, data in gen.items():
            if track_name not in pattern.tracks:
                continue
            track = pattern.tracks[track_name]
            vels = data['velocities']
            notes = data.get('notes', None)
            accents = data.get('accents', None)
            glides = data.get('glides', None)

            for i in range(min(len(vels), track.length)):
                track.steps[i].active = vels[i] > 0
                track.steps[i].velocity = float(vels[i]) if vels[i] > 0 else 0.8
                if notes is not None:
                    track.steps[i].note = int(notes[i])
                if accents is not None:
                    track.steps[i].accent = bool(accents[i])
                if glides is not None:
                    track.steps[i].glide = bool(glides[i])

    def ai_variation(self):
        """Create a variation of the current pattern."""
        pattern = self.transport.current_pattern
        for track_name, track in pattern.tracks.items():
            vels = np.array([s.velocity if s.active else 0.0 for s in track.steps])
            mutated = self.variation_engine.mutate(vels, mutation_rate=0.2)
            for i in range(track.length):
                track.steps[i].active = mutated[i] > 0
                if mutated[i] > 0:
                    track.steps[i].velocity = float(mutated[i])

    def ai_humanize(self):
        """Humanize velocities in current pattern."""
        pattern = self.transport.current_pattern
        for track_name, track in pattern.tracks.items():
            vels = np.array([s.velocity if s.active else 0.0 for s in track.steps])
            humanized = self.variation_engine.humanize(vels, amount=0.08)
            for i in range(track.length):
                if track.steps[i].active:
                    track.steps[i].velocity = float(humanized[i])

    def cycle_style(self):
        """Cycle through available styles."""
        idx = STYLE_NAMES.index(self.current_style)
        idx = (idx + 1) % len(STYLE_NAMES)
        self._apply_style(STYLE_NAMES[idx])

    def _apply_style(self, style_name):
        self.current_style = style_name
        style = STYLES[style_name]
        self.pattern_gen.set_style(style_name)

        self.clock.bpm = style['bpm']
        self.clock.swing = style.get('swing', 0.0)
        self.engine.state.bpm = self.clock.bpm

        # Apply instrument presets
        self.drums.apply_preset(style)
        self.bass.apply_preset(style.get('bass', {}))
        self.lead.apply_preset(style.get('lead', {}))
        self.pad.apply_preset(style.get('pad', {}))

        self.mixer.master.delay.set_tempo_sync(self.clock.bpm)

    def get_suggestions(self):
        pattern = self.transport.current_pattern
        return self.suggestion_engine.analyze_and_suggest(pattern, self.current_style)

    # --- Synth parameter editing ---

    def get_synth_params(self, track_name):
        """Return list of (name, value, min, max) for synth editing."""
        if track_name in ['kick', 'snare', 'clap', 'closed_hat', 'open_hat', 'tom_lo', 'tom_hi', 'rimshot']:
            voice = self.drums.voices.get(track_name)
            if not voice:
                return []
            params = []
            if hasattr(voice, 'pitch'):
                params.append(('Pitch', voice.pitch, 20, 200))
            if hasattr(voice, 'decay'):
                params.append(('Decay', voice.decay, 0.01, 2.0))
            if hasattr(voice, 'drive'):
                params.append(('Drive', voice.drive, 1.0, 5.0))
            if hasattr(voice, 'click'):
                params.append(('Click', voice.click, 0.0, 1.0))
            if hasattr(voice, 'tone'):
                params.append(('Tone', voice.tone, 0.0, 1.0))
            if hasattr(voice, 'snappy'):
                params.append(('Snappy', voice.snappy, 0.0, 1.0))
            return params
        elif track_name == 'bass':
            return [
                ('Cutoff', self.bass.cutoff, 20, 10000),
                ('Resonance', self.bass.resonance, 0, 4),
                ('Env Mod', self.bass.env_mod, 0, 8000),
                ('Drive', self.bass.drive, 1, 5),
                ('Sub Level', self.bass.sub_level, 0, 1),
                ('Glide', self.bass.glide_time, 0, 0.2),
            ]
        elif track_name == 'lead':
            return [
                ('Cutoff', self.lead.cutoff, 20, 10000),
                ('Resonance', self.lead.resonance, 0, 1),
                ('Filter Env', self.lead.filter_env_amt, 0, 8000),
                ('Detune', self.lead.osc2_detune, 0, 1),
                ('Osc Mix', self.lead.osc_mix, 0, 1),
                ('Volume', self.lead.volume, 0, 1),
            ]
        elif track_name == 'pad':
            return [
                ('Cutoff', self.pad.cutoff, 20, 10000),
                ('Resonance', self.pad.resonance, 0, 1),
                ('Detune', self.pad.detune, 0, 0.05),
                ('Width', self.pad.stereo_width, 0, 1),
                ('Volume', self.pad.volume, 0, 1),
            ]
        return []

    def adjust_synth_param(self, track_idx, param_idx, direction):
        """Adjust a synth parameter by direction (-1 or +1)."""
        track_order = [
            'kick', 'snare', 'clap', 'closed_hat', 'open_hat',
            'tom_lo', 'tom_hi', 'rimshot', 'bass', 'lead', 'pad'
        ]
        if track_idx >= len(track_order):
            return
        track_name = track_order[track_idx]
        params = self.get_synth_params(track_name)
        if param_idx >= len(params):
            return

        name, value, min_v, max_v = params[param_idx]
        step = (max_v - min_v) * 0.05  # 5% of range
        new_value = max(min_v, min(max_v, value + direction * step))

        # Apply to the actual instrument
        if track_name in ['kick', 'snare', 'clap', 'closed_hat', 'open_hat', 'tom_lo', 'tom_hi', 'rimshot']:
            voice = self.drums.voices.get(track_name)
            if voice:
                attr_map = {
                    'Pitch': 'pitch', 'Decay': 'decay', 'Drive': 'drive',
                    'Click': 'click', 'Tone': 'tone', 'Snappy': 'snappy',
                }
                attr = attr_map.get(name)
                if attr and hasattr(voice, attr):
                    setattr(voice, attr, new_value)
        elif track_name == 'bass':
            attr_map = {
                'Cutoff': 'cutoff', 'Resonance': 'resonance', 'Env Mod': 'env_mod',
                'Drive': 'drive', 'Sub Level': 'sub_level', 'Glide': 'glide_time',
            }
            attr = attr_map.get(name)
            if attr:
                setattr(self.bass, attr, new_value)
        elif track_name == 'lead':
            attr_map = {
                'Cutoff': 'cutoff', 'Resonance': 'resonance', 'Filter Env': 'filter_env_amt',
                'Detune': 'osc2_detune', 'Osc Mix': 'osc_mix', 'Volume': 'volume',
            }
            attr = attr_map.get(name)
            if attr:
                setattr(self.lead, attr, new_value)
        elif track_name == 'pad':
            attr_map = {
                'Cutoff': 'cutoff', 'Resonance': 'resonance',
                'Detune': 'detune', 'Width': 'stereo_width', 'Volume': 'volume',
            }
            attr = attr_map.get(name)
            if attr:
                setattr(self.pad, attr, new_value)

    # --- File operations ---

    def export_wav(self):
        """Export current pattern as WAV."""
        was_playing = self.clock.playing
        self.clock.playing = True
        self.clock.reset()

        filename = os.path.expanduser(f'~/technobox/exports/beat_{self.current_style}.wav')
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        export_wav(
            self._render_block,
            filename,
            duration_bars=4,
            bpm=self.clock.bpm,
            sr=self.sr,
        )

        self.clock.playing = was_playing
        if not was_playing:
            self.clock.reset()

    def save_project(self):
        filepath = os.path.expanduser('~/technobox/projects/current.json')
        save_project(filepath, self.transport, self.clock, self.current_style)

    def load_project(self):
        filepath = os.path.expanduser('~/technobox/projects/current.json')
        data = load_project(filepath)
        if data:
            self.clock.bpm = data.get('bpm', 130)
            self.clock.swing = data.get('swing', 0.0)
            style = data.get('style', 'detroit')
            if style in STYLE_NAMES:
                self._apply_style(style)
            self.transport.current_pattern_idx = data.get('current_pattern', 0)

            from .sequencer.pattern import Pattern
            for i, pdata in enumerate(data.get('patterns', [])):
                if i < len(self.transport.patterns):
                    self.transport.patterns[i] = Pattern.from_dict(pdata)
