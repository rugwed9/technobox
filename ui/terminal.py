import curses
import time
from .colors import (
    init_colors, PAIR_HEADER, PAIR_ACTIVE_STEP, PAIR_CURRENT_STEP,
    PAIR_CURSOR, PAIR_MUTED, PAIR_ACCENT, PAIR_METER_LOW, PAIR_METER_MID,
    PAIR_METER_HIGH, PAIR_AI_TIP, PAIR_STATUS, PAIR_TRACK_NAME,
    PAIR_PLAYING, PAIR_HELP, PAIR_INACTIVE,
)
from .widgets import draw_meter, draw_step_grid


class TerminalUI:
    """Curses-based terminal UI for TechnoBox."""

    # Views
    VIEW_SEQUENCER = 'sequencer'
    VIEW_MIXER = 'mixer'
    VIEW_SYNTH = 'synth'
    VIEW_AI = 'ai'
    VIEW_HELP = 'help'

    def __init__(self, app):
        self.app = app
        self.stdscr = None
        self.current_view = self.VIEW_SEQUENCER

        # Cursor state
        self.cursor_track = 0
        self.cursor_step = 0

        # Track order for display
        self.track_order = [
            'kick', 'snare', 'clap', 'closed_hat', 'open_hat',
            'tom_lo', 'tom_hi', 'rimshot', 'bass', 'lead', 'pad'
        ]
        self.track_short_names = {
            'kick': 'KICK', 'snare': 'SNR', 'clap': 'CLAP',
            'closed_hat': 'CHH', 'open_hat': 'OHH',
            'tom_lo': 'TML', 'tom_hi': 'TMH', 'rimshot': 'RIM',
            'bass': 'BASS', 'lead': 'LEAD', 'pad': 'PAD',
        }

        # Synth param editing
        self.synth_param_idx = 0
        self._last_refresh = 0

    def run(self, stdscr):
        self.stdscr = stdscr
        init_colors()
        curses.curs_set(0)
        stdscr.nodelay(True)
        stdscr.timeout(33)  # ~30fps

        while True:
            try:
                key = stdscr.getch()
            except curses.error:
                key = -1

            if key != -1:
                action = self.handle_key(key)
                if action == 'quit':
                    break

            self.draw()

    def handle_key(self, key):
        """Process keyboard input. Returns 'quit' to exit."""
        pattern = self.app.transport.current_pattern

        # Global keys
        if key == ord('q') or key == 17:  # q or Ctrl-Q
            return 'quit'
        elif key == ord(' '):
            self.app.toggle_play()
        elif key == ord('+') or key == ord('='):
            self.app.set_bpm(self.app.clock.bpm + 1)
        elif key == ord('-') or key == ord('_'):
            self.app.set_bpm(self.app.clock.bpm - 1)
        elif key == ord('['):
            self.app.transport.prev_pattern()
        elif key == ord(']'):
            self.app.transport.next_pattern()

        # View switching
        elif key == curses.KEY_F5 or key == ord('1'):
            self.current_view = self.VIEW_SEQUENCER
        elif key == curses.KEY_F6 or key == ord('2'):
            self.current_view = self.VIEW_MIXER
        elif key == curses.KEY_F7 or key == ord('3'):
            self.current_view = self.VIEW_SYNTH
        elif key == curses.KEY_F8 or key == ord('4'):
            self.current_view = self.VIEW_AI
        elif key == ord('?') or key == ord('5'):
            self.current_view = self.VIEW_HELP

        # Sequencer view keys
        elif self.current_view == self.VIEW_SEQUENCER:
            self._handle_sequencer_key(key, pattern)

        # Mixer view keys
        elif self.current_view == self.VIEW_MIXER:
            self._handle_mixer_key(key)

        # Synth view keys
        elif self.current_view == self.VIEW_SYNTH:
            self._handle_synth_key(key)

        # AI view / global AI keys
        if key == ord('g') or key == ord('G'):
            self.app.ai_generate()
        elif key == ord('r') or key == ord('R'):
            self.app.ai_variation()
        elif key == ord('h') or key == ord('H'):
            self.app.ai_humanize()
        elif key == ord('p') or key == ord('P'):
            self.app.cycle_style()
        elif key == 5:  # Ctrl-E
            self.app.export_wav()
        elif key == 19:  # Ctrl-S
            self.app.save_project()
        elif key == 12:  # Ctrl-L
            self.app.load_project()

        return None

    def _handle_sequencer_key(self, key, pattern):
        track_names = self.track_order

        if key == curses.KEY_UP:
            self.cursor_track = max(0, self.cursor_track - 1)
        elif key == curses.KEY_DOWN:
            self.cursor_track = min(len(track_names) - 1, self.cursor_track + 1)
        elif key == curses.KEY_LEFT:
            self.cursor_step = max(0, self.cursor_step - 1)
        elif key == curses.KEY_RIGHT:
            self.cursor_step = min(pattern.length - 1, self.cursor_step + 1)
        elif key == 10 or key == curses.KEY_ENTER:  # Enter
            track_name = track_names[self.cursor_track]
            if track_name in pattern.tracks:
                pattern.tracks[track_name].toggle_step(self.cursor_step)
        elif key == ord('\t') or key == 9:  # Tab
            self.cursor_track = (self.cursor_track + 1) % len(track_names)
        elif key == ord('v'):
            # Decrease velocity
            track_name = track_names[self.cursor_track]
            if track_name in pattern.tracks:
                step = pattern.tracks[track_name].steps[self.cursor_step]
                step.velocity = max(0.1, step.velocity - 0.1)
        elif key == ord('V'):
            # Increase velocity
            track_name = track_names[self.cursor_track]
            if track_name in pattern.tracks:
                step = pattern.tracks[track_name].steps[self.cursor_step]
                step.velocity = min(1.0, step.velocity + 0.1)
        elif key == ord('n'):
            # Decrease note
            track_name = track_names[self.cursor_track]
            if track_name in pattern.tracks:
                step = pattern.tracks[track_name].steps[self.cursor_step]
                step.note = max(0, step.note - 1)
        elif key == ord('N'):
            # Increase note
            track_name = track_names[self.cursor_track]
            if track_name in pattern.tracks:
                step = pattern.tracks[track_name].steps[self.cursor_step]
                step.note = min(127, step.note + 1)
        elif key == ord('a') or key == ord('A'):
            # Toggle accent
            track_name = track_names[self.cursor_track]
            if track_name in pattern.tracks:
                step = pattern.tracks[track_name].steps[self.cursor_step]
                step.accent = not step.accent
        elif key == ord('m') or key == ord('M'):
            # Toggle mute
            track_name = track_names[self.cursor_track]
            if track_name in pattern.tracks:
                pattern.tracks[track_name].muted = not pattern.tracks[track_name].muted
        elif key == ord('s') or key == ord('S'):
            # Toggle solo
            track_name = track_names[self.cursor_track]
            if track_name in pattern.tracks:
                pattern.tracks[track_name].solo = not pattern.tracks[track_name].solo
        elif key == ord('c') or key == ord('C'):
            # Clear track
            track_name = track_names[self.cursor_track]
            if track_name in pattern.tracks:
                pattern.tracks[track_name].clear()

    def _handle_mixer_key(self, key):
        track_name = self.track_order[self.cursor_track]

        if key == curses.KEY_UP:
            self.cursor_track = max(0, self.cursor_track - 1)
        elif key == curses.KEY_DOWN:
            self.cursor_track = min(len(self.track_order) - 1, self.cursor_track + 1)
        elif key == ord('<') or key == ord(','):
            # Volume down
            vol = self.app.mixer.track_volumes.get(track_name, 0.8)
            self.app.mixer.track_volumes[track_name] = max(0.0, vol - 0.05)
        elif key == ord('>') or key == ord('.'):
            # Volume up
            vol = self.app.mixer.track_volumes.get(track_name, 0.8)
            self.app.mixer.track_volumes[track_name] = min(1.0, vol + 0.05)

    def _handle_synth_key(self, key):
        if key == curses.KEY_UP:
            self.synth_param_idx = max(0, self.synth_param_idx - 1)
        elif key == curses.KEY_DOWN:
            self.synth_param_idx += 1
        elif key == curses.KEY_LEFT:
            self.app.adjust_synth_param(self.cursor_track, self.synth_param_idx, -1)
        elif key == curses.KEY_RIGHT:
            self.app.adjust_synth_param(self.cursor_track, self.synth_param_idx, 1)

    def draw(self):
        self.stdscr.erase()
        h, w = self.stdscr.getmaxyx()

        if h < 20 or w < 60:
            self.stdscr.addstr(0, 0, "Terminal too small! Need 60x20 minimum.")
            self.stdscr.refresh()
            return

        self._draw_header(w)

        if self.current_view == self.VIEW_SEQUENCER:
            self._draw_sequencer(h, w)
        elif self.current_view == self.VIEW_MIXER:
            self._draw_mixer(h, w)
        elif self.current_view == self.VIEW_SYNTH:
            self._draw_synth(h, w)
        elif self.current_view == self.VIEW_AI:
            self._draw_ai(h, w)
        elif self.current_view == self.VIEW_HELP:
            self._draw_help(h, w)

        self._draw_status_bar(h, w)
        self.stdscr.refresh()

    def _draw_header(self, w):
        # Title and transport info
        state = self.app.engine.state
        play_str = "PLAYING" if self.app.clock.playing else "STOPPED"
        play_color = curses.color_pair(PAIR_PLAYING) if self.app.clock.playing else curses.color_pair(PAIR_MUTED)

        title = f" TECHNOBOX "
        bpm_str = f" BPM:{self.app.clock.bpm:.0f} "
        pattern_str = f" Pat:{self.app.transport.current_pattern_idx + 1} "
        style_str = f" [{self.app.current_style.upper()}] "
        step_str = f" Step:{self.app.clock.current_step + 1:2d}/16 "

        try:
            self.stdscr.addstr(0, 0, title, curses.color_pair(PAIR_HEADER) | curses.A_BOLD)
            self.stdscr.addstr(0, len(title), play_str, play_color | curses.A_BOLD)
            self.stdscr.addstr(0, len(title) + len(play_str) + 1, bpm_str)
            self.stdscr.addstr(0, len(title) + len(play_str) + len(bpm_str) + 1, pattern_str)
            self.stdscr.addstr(0, len(title) + len(play_str) + len(bpm_str) + len(pattern_str) + 1, style_str,
                              curses.color_pair(PAIR_AI_TIP) | curses.A_BOLD)
            col = len(title) + len(play_str) + len(bpm_str) + len(pattern_str) + len(style_str) + 1
            self.stdscr.addstr(0, col, step_str)

            # CPU and meters
            cpu_str = f" CPU:{state.cpu_load * 100:.0f}%"
            if col + len(step_str) + len(cpu_str) + 2 < w:
                self.stdscr.addstr(0, col + len(step_str) + 1, cpu_str)
        except curses.error:
            pass

        # Separator
        try:
            self.stdscr.addstr(1, 0, '-' * min(w - 1, 100))
        except curses.error:
            pass

    def _draw_sequencer(self, h, w):
        pattern = self.app.transport.current_pattern
        current_step = self.app.clock.current_step if self.app.clock.playing else -1
        start_y = 2

        # Column header (step numbers)
        step_header = "       "
        for i in range(pattern.length):
            if i % 4 == 0:
                step_header += f"{i+1:<2}"
            else:
                step_header += "  "
            if i < pattern.length - 1 and (i + 1) % 4 == 0:
                step_header += " "
        try:
            self.stdscr.addstr(start_y, 0, step_header[:w-1], curses.color_pair(PAIR_HEADER))
        except curses.error:
            pass

        # Draw each track
        for row, track_name in enumerate(self.track_order):
            y = start_y + 1 + row
            if y >= h - 4:
                break

            track = pattern.tracks.get(track_name)
            if not track:
                continue

            # Track name
            short = self.track_short_names.get(track_name, track_name[:4])
            mute_flag = 'M' if track.muted else ' '
            solo_flag = 'S' if track.solo else ' '
            label = f"{short:>4}{mute_flag}{solo_flag}"

            name_color = curses.color_pair(PAIR_MUTED) if track.muted else curses.color_pair(PAIR_TRACK_NAME)
            try:
                self.stdscr.addstr(y, 0, label, name_color)
            except curses.error:
                pass

            # Step grid
            is_selected = (row == self.cursor_track)
            draw_step_grid(self.stdscr, y, 7, track, current_step, self.cursor_step, is_selected)

        # AI suggestions at bottom
        suggestions = self.app.get_suggestions()
        tip_y = min(start_y + len(self.track_order) + 2, h - 4)
        try:
            self.stdscr.addstr(tip_y, 0, '-' * min(w - 1, 100))
        except curses.error:
            pass
        for i, tip in enumerate(suggestions[:2]):
            try:
                self.stdscr.addstr(tip_y + 1 + i, 1, f"AI: {tip}"[:w-2],
                                  curses.color_pair(PAIR_AI_TIP))
            except curses.error:
                pass

    def _draw_mixer(self, h, w):
        start_y = 2
        try:
            self.stdscr.addstr(start_y, 0, " MIXER ", curses.color_pair(PAIR_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        for row, track_name in enumerate(self.track_order):
            y = start_y + 1 + row
            if y >= h - 3:
                break

            vol = self.app.mixer.track_volumes.get(track_name, 0.8)
            short = self.track_short_names.get(track_name, track_name[:4])
            is_selected = (row == self.cursor_track)

            label_color = curses.color_pair(PAIR_CURSOR) if is_selected else curses.color_pair(PAIR_TRACK_NAME)
            try:
                self.stdscr.addstr(y, 0, f" {short:>4} ", label_color)
            except curses.error:
                pass

            draw_meter(self.stdscr, y, 7, vol, width=20, label='')

            vol_str = f" {vol:.0%}"
            try:
                self.stdscr.addstr(y, 29, vol_str)
            except curses.error:
                pass

        # Master
        master_y = start_y + len(self.track_order) + 2
        if master_y < h - 3:
            try:
                self.stdscr.addstr(master_y, 0, " MSTR ", curses.color_pair(PAIR_HEADER) | curses.A_BOLD)
            except curses.error:
                pass
            draw_meter(self.stdscr, master_y, 7, self.app.mixer.master.master_volume, width=20)

    def _draw_synth(self, h, w):
        start_y = 2
        track_name = self.track_order[self.cursor_track]

        try:
            self.stdscr.addstr(start_y, 0, f" SYNTH: {track_name.upper()} ",
                              curses.color_pair(PAIR_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        params = self.app.get_synth_params(track_name)
        for i, (name, value, min_v, max_v) in enumerate(params):
            y = start_y + 1 + i
            if y >= h - 3:
                break
            is_selected = (i == self.synth_param_idx)
            color = curses.color_pair(PAIR_CURSOR) if is_selected else curses.color_pair(PAIR_HELP)
            try:
                self.stdscr.addstr(y, 1, f"{name:>15}: {value:>8.2f}  [{min_v:.1f} - {max_v:.1f}]", color)
            except curses.error:
                pass

    def _draw_ai(self, h, w):
        start_y = 2
        try:
            self.stdscr.addstr(start_y, 0, " AI ASSISTANT ", curses.color_pair(PAIR_HEADER) | curses.A_BOLD)
            self.stdscr.addstr(start_y + 2, 1, f"Current Style: {self.app.current_style.upper()}",
                              curses.color_pair(PAIR_AI_TIP) | curses.A_BOLD)
        except curses.error:
            pass

        suggestions = self.app.get_suggestions()
        for i, tip in enumerate(suggestions):
            y = start_y + 4 + i
            if y >= h - 5:
                break
            try:
                self.stdscr.addstr(y, 2, f"* {tip}"[:w-3], curses.color_pair(PAIR_AI_TIP))
            except curses.error:
                pass

        # AI key shortcuts
        keys_y = start_y + 8
        ai_keys = [
            ("G", "Generate new pattern"),
            ("R", "Random variation"),
            ("H", "Humanize velocities"),
            ("P", "Cycle style preset"),
        ]
        try:
            self.stdscr.addstr(keys_y, 1, "AI Controls:", curses.color_pair(PAIR_HEADER))
        except curses.error:
            pass
        for i, (k, desc) in enumerate(ai_keys):
            y = keys_y + 1 + i
            if y >= h - 3:
                break
            try:
                self.stdscr.addstr(y, 3, f"[{k}] {desc}", curses.color_pair(PAIR_HELP))
            except curses.error:
                pass

    def _draw_help(self, h, w):
        start_y = 2
        help_sections = [
            ("TRANSPORT", [
                ("Space", "Play / Stop"),
                ("+ / -", "BPM up / down"),
                ("[ / ]", "Prev / Next pattern"),
            ]),
            ("NAVIGATION", [
                ("Arrows", "Move cursor"),
                ("Tab", "Next track"),
                ("1-5", "Switch view (Seq/Mix/Syn/AI/Help)"),
            ]),
            ("EDITING", [
                ("Enter", "Toggle step on/off"),
                ("v / V", "Velocity down / up"),
                ("n / N", "Note down / up"),
                ("a / A", "Toggle accent"),
                ("c / C", "Clear track"),
            ]),
            ("MIXER", [
                ("m / M", "Toggle mute"),
                ("s / S", "Toggle solo"),
                ("< / >", "Volume down / up"),
            ]),
            ("AI", [
                ("G", "Generate pattern"),
                ("R", "Random variation"),
                ("H", "Humanize"),
                ("P", "Cycle style"),
            ]),
            ("FILE", [
                ("Ctrl-S", "Save project"),
                ("Ctrl-L", "Load project"),
                ("Ctrl-E", "Export WAV"),
                ("Ctrl-Q / q", "Quit"),
            ]),
        ]

        try:
            self.stdscr.addstr(start_y, 0, " KEYBOARD SHORTCUTS ",
                              curses.color_pair(PAIR_HEADER) | curses.A_BOLD)
        except curses.error:
            pass

        y = start_y + 1
        for section, keys in help_sections:
            if y >= h - 3:
                break
            try:
                self.stdscr.addstr(y, 1, section, curses.color_pair(PAIR_TRACK_NAME) | curses.A_BOLD)
            except curses.error:
                pass
            y += 1
            for key, desc in keys:
                if y >= h - 3:
                    break
                try:
                    self.stdscr.addstr(y, 3, f"{key:>10}  {desc}", curses.color_pair(PAIR_HELP))
                except curses.error:
                    pass
                y += 1
            y += 1

    def _draw_status_bar(self, h, w):
        status = " [1]Seq [2]Mix [3]Syn [4]AI [5]Help | Space:Play G:Generate P:Style q:Quit "
        try:
            self.stdscr.addstr(h - 1, 0, status[:w-1].ljust(w-1),
                              curses.color_pair(PAIR_STATUS))
        except curses.error:
            pass
