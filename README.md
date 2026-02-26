# TechnoBox

Make beats on your MacBook. No DAW needed. All sounds synthesized from scratch.

## Quick Start

```bash
pip install sounddevice numpy scipy
cd technobox
python3 beatmaker.py
```

Starts playing instantly. Tap keys to build your beat.

## Beat Maker

```bash
python3 beatmaker.py
```

An interactive step sequencer. The loop plays, you tap keys to toggle steps on/off.

### Controls

| Key | Action |
|-----|--------|
| `a s d f g h j k` | Toggle steps 1-8 |
| `z x c v b n m ,` | Toggle steps 9-16 |
| `TAB` | Next track |
| `SPACE` | Play / Stop |
| `+ / -` | BPM up / down |
| `G` | AI auto-fill current track |
| `C` | Clear current track |
| `UP / DOWN` | Change note (bass/lead tracks) |
| `[ / ]` | Octave down / up |
| `E` | Export as WAV |
| `Q` | Quit |

### 10 Genre Presets

Load a full genre pattern with Shift + number key:

| Key | Genre | BPM | Vibe |
|-----|-------|-----|------|
| `!` (Shift+1) | Detroit Techno | 128 | Deep, rolling, classic |
| `@` (Shift+2) | Berlin Hard Techno | 140 | Industrial, punchy |
| `#` (Shift+3) | Acid Techno | 138 | 303 squelch, hypnotic |
| `$` (Shift+4) | Minimal Techno | 125 | Sparse, groovy |
| `%` (Shift+5) | Afro House | 122 | Polyrhythmic, warm |
| `^` (Shift+6) | Melodic Techno | 124 | Emotional, atmospheric |
| `&` (Shift+7) | UK Garage / 2-Step | 132 | Broken beats, shuffled |
| `*` (Shift+8) | Uplifting Trance | 138 | Euphoric, driving |
| `(` (Shift+9) | Deep House | 122 | Warm, melodic bass |
| `)` (Shift+0) | Fred Again Style | 128 | Emotional, sparse |

Load a preset, then tweak it. Toggle steps on/off, change notes, make it yours.

## Other Modes

### Instant Play
```bash
python3 play.py          # Detroit techno
python3 play.py acid     # Pick a style
```
Press `1-4` to switch styles live. Just vibes.

### Full Track Creator
```bash
python3 create_track.py
```
Builds a complete song with intro, buildup, drop, breakdown, outro. Exports WAV.

```bash
python3 create_track.py --quick --style acid
```
Instant full track export, no questions asked.

## How It Works

Everything is synthesized in real-time using math. No samples, no audio files.

- **Kick drum**: Sine wave + pitch envelope + saturation
- **Snare**: Pitched oscillator + bandpass noise
- **Hi-hat**: 6 detuned square waves (metallic ring) + noise
- **Clap**: Multiple noise bursts + reverb tail
- **Bass**: Saw/square oscillator + lowpass filter + filter envelope
- **Lead**: Dual detuned oscillators + filter + envelope

## Requirements

- macOS (uses CoreAudio)
- Python 3.10+
- `pip install sounddevice numpy scipy`

## Export

Beats export to `~/technobox/exports/`. Each export gets a unique timestamp filename so nothing gets overwritten.

```
~/technobox/exports/beat_acid_20260226_143022.wav
~/technobox/exports/beat_afro_20260226_143105.wav
```
