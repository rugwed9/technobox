import curses

# Color pair IDs
PAIR_DEFAULT = 0
PAIR_HEADER = 1
PAIR_ACTIVE_STEP = 2
PAIR_CURRENT_STEP = 3
PAIR_CURSOR = 4
PAIR_MUTED = 5
PAIR_ACCENT = 6
PAIR_METER_LOW = 7
PAIR_METER_MID = 8
PAIR_METER_HIGH = 9
PAIR_AI_TIP = 10
PAIR_STATUS = 11
PAIR_TRACK_NAME = 12
PAIR_PLAYING = 13
PAIR_HELP = 14
PAIR_INACTIVE = 15


def init_colors():
    curses.start_color()
    curses.use_default_colors()

    curses.init_pair(PAIR_HEADER, curses.COLOR_CYAN, -1)
    curses.init_pair(PAIR_ACTIVE_STEP, curses.COLOR_GREEN, -1)
    curses.init_pair(PAIR_CURRENT_STEP, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(PAIR_CURSOR, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(PAIR_MUTED, curses.COLOR_RED, -1)
    curses.init_pair(PAIR_ACCENT, curses.COLOR_YELLOW, -1)
    curses.init_pair(PAIR_METER_LOW, curses.COLOR_GREEN, -1)
    curses.init_pair(PAIR_METER_MID, curses.COLOR_YELLOW, -1)
    curses.init_pair(PAIR_METER_HIGH, curses.COLOR_RED, -1)
    curses.init_pair(PAIR_AI_TIP, curses.COLOR_MAGENTA, -1)
    curses.init_pair(PAIR_STATUS, curses.COLOR_WHITE, curses.COLOR_BLUE)
    curses.init_pair(PAIR_TRACK_NAME, curses.COLOR_CYAN, -1)
    curses.init_pair(PAIR_PLAYING, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(PAIR_HELP, curses.COLOR_WHITE, -1)
    curses.init_pair(PAIR_INACTIVE, curses.COLOR_WHITE, -1)
