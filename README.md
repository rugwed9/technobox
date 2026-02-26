# TechnoBox

Make beats on your MacBook. No DAW needed. All sounds synthesized from scratch.

Two versions: **Terminal** (Python) and **Browser** (HTML/Web Audio). Zero samples, pure synthesis.

---

## Browser Version — KODA BEATS

Open `koda-beats.html` in any browser. Click anywhere to start. No install needed.

### What it does
- 5 DJ scene presets: Solomun, Anyma, Fred Again, Charlotte de Witte, HUGEL
- 8 instrument loops, 9 one-shot triggers, 10 hold-to-activate effects
- XY pad for live filter/delay/reverb/wobble control (like a Kaoss Pad)
- 16-step sequencer grid with per-track volume
- Spectrum analyzer + waveform visualizer
- Vocal synthesis engine with formant-based chops
- Pre-wired FX chain (no clicks/pops): reverb, delay, echo out, gate, flanger, phaser, crush, pump

### Controls
| Row | Keys | Action |
|-----|------|--------|
| Loops | `Q W E R T Y U I` | Toggle kick, hat, snare, open hat, bass, lead, perc, vox |
| Triggers | `A S D F G H J K L` | Riser, drop, snare roll, phrase, stutter, chord, scatter, brake, impact |
| Effects | `Z X C V B N M , . /` | Lowpass, hipass, crush, reverb, delay, echo out, gate, flanger, pump, phaser |
| Scenes | `1 2 3 4 5` | Solomun, Anyma, Fred Again, Charlotte, HUGEL |
| XY Pad | `TAB` | Cycle mode: Filter / Delay / Reverb / Wobble |
| Transport | `SPACE` tap tempo, `UP/DOWN` BPM, `ESC` panic |
| Presets | `6-9` load, `SHIFT+6-9` save |
| Guide | `?` | Full keyboard reference |

---

## Terminal Version — Beat Maker

```bash
pip install sounddevice numpy scipy
python3 beatmaker.py
```

Starts playing instantly. Tap keys to build your beat.

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

Load with Shift + number key:

| Key | Genre | BPM |
|-----|-------|-----|
| `!` (Shift+1) | Detroit Techno | 128 |
| `@` (Shift+2) | Berlin Hard Techno | 140 |
| `#` (Shift+3) | Acid Techno | 138 |
| `$` (Shift+4) | Minimal Techno | 125 |
| `%` (Shift+5) | Afro House | 122 |
| `^` (Shift+6) | Melodic Techno | 124 |
| `&` (Shift+7) | UK Garage / 2-Step | 132 |
| `*` (Shift+8) | Uplifting Trance | 138 |
| `(` (Shift+9) | Deep House | 122 |
| `)` (Shift+0) | Fred Again Style | 128 |

---

## Other Modes

### Instant Play
```bash
python3 play.py          # Detroit techno
python3 play.py acid     # Pick a style
```

### Full Track Creator
```bash
python3 create_track.py                    # Interactive
python3 create_track.py --quick --style acid  # Instant export
```

---

## How It Works

Everything is synthesized in real-time using math. No samples, no audio files.

- **Kick**: Sine wave + pitch envelope (sweep down) + sub layer + click transient + tanh saturation
- **Snare**: Triangle body + bandpass noise + multi-tap clap layer + distortion snap
- **Hi-hat**: 6 detuned square waves (metallic ring) + filtered noise
- **Clap**: Multiple noise bursts with timing spread
- **Bass**: Saw/sine + resonant lowpass filter + filter envelope + sub oscillator + portamento (acid mode)
- **Lead**: Triple detuned sawtooth oscillators + filter + envelope
- **Vocals** (browser): 5-formant synthesis, pre-rendered syllable buffers, bandpass + compression chain

## Requirements

**Terminal version:**
- macOS (CoreAudio) / Linux (ALSA/PulseAudio)
- Python 3.10+
- `pip install sounddevice numpy scipy`

**Browser version:**
- Any modern browser (Chrome, Safari, Firefox, Edge)
- No install needed

## Export

Terminal beats export to `~/technobox/exports/` with timestamped filenames.
