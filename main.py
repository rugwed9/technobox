#!/usr/bin/env python3
"""
TechnoBox - Pure MacBook Techno Beat Production System

A complete techno music production system running in the terminal.
All sounds are synthesized procedurally - no samples needed.

Usage:
    python3 -m technobox

Controls:
    Space       Play / Stop
    + / -       BPM up / down
    Arrows      Navigate step grid
    Enter       Toggle step on/off
    Tab         Next track
    G           AI Generate pattern
    P           Cycle style (Detroit/Berlin/Acid/Minimal)
    H           Humanize velocities
    R           Random variation
    Ctrl-E      Export WAV
    Ctrl-S      Save project
    q           Quit
"""

from .app import TechnoBoxApp


def main():
    app = TechnoBoxApp()
    app.run()


if __name__ == '__main__':
    main()
