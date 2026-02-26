import curses
from .colors import *


def draw_meter(win, y, x, value, width=10, label=''):
    """Draw a horizontal level meter."""
    filled = int(value * width)
    filled = min(filled, width)

    if label:
        win.addstr(y, x, label[:6].ljust(6), curses.color_pair(PAIR_TRACK_NAME))
        x += 7

    win.addstr(y, x, '[')
    for i in range(width):
        if i < filled:
            if i < width * 0.6:
                color = curses.color_pair(PAIR_METER_LOW)
            elif i < width * 0.85:
                color = curses.color_pair(PAIR_METER_MID)
            else:
                color = curses.color_pair(PAIR_METER_HIGH)
            win.addstr(y, x + 1 + i, '|', color | curses.A_BOLD)
        else:
            win.addstr(y, x + 1 + i, ' ')
    win.addstr(y, x + width + 1, ']')


def draw_fader(win, y, x, value, height=8, label=''):
    """Draw a vertical fader."""
    if label:
        lbl = label[:4].center(4)
        try:
            win.addstr(y + height + 1, x, lbl, curses.color_pair(PAIR_TRACK_NAME))
        except curses.error:
            pass

    filled = int(value * height)
    for i in range(height):
        pos = height - 1 - i
        ch = '|' if i < filled else ':'
        color = curses.color_pair(PAIR_METER_LOW) if i < filled else curses.color_pair(PAIR_INACTIVE)
        try:
            win.addstr(y + pos, x + 1, ch, color)
        except curses.error:
            pass


def draw_step_grid(win, y, x, track, current_step, cursor_step, is_selected_track):
    """Draw a single track's step grid row."""
    for i in range(track.length):
        step = track.steps[i]

        # Determine character and color
        if step.active:
            if step.accent:
                ch = 'A'
                color = curses.color_pair(PAIR_ACCENT) | curses.A_BOLD
            else:
                # Velocity-based display
                v = step.velocity
                if v > 0.7:
                    ch = '#'
                elif v > 0.4:
                    ch = 'o'
                else:
                    ch = '.'
                color = curses.color_pair(PAIR_ACTIVE_STEP) | curses.A_BOLD
        else:
            ch = '-'
            color = curses.color_pair(PAIR_INACTIVE)

        # Highlight current playback step
        if i == current_step:
            color = curses.color_pair(PAIR_CURRENT_STEP) | curses.A_BOLD

        # Highlight cursor position
        if is_selected_track and i == cursor_step:
            color = curses.color_pair(PAIR_CURSOR) | curses.A_BOLD

        # Add beat separators
        if i > 0 and i % 4 == 0:
            try:
                win.addstr(y, x + i * 2 - 1, '|', curses.color_pair(PAIR_INACTIVE))
            except curses.error:
                pass

        try:
            win.addstr(y, x + i * 2, ch, color)
            if i < track.length - 1:
                win.addstr(y, x + i * 2 + 1, ' ')
        except curses.error:
            pass
