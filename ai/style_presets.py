STYLES = {
    'detroit': {
        'name': 'Detroit / Classic Techno',
        'bpm': 128,
        'swing': 0.0,
        'kick': {'pitch': 50, 'decay': 0.5, 'drive': 1.5, 'click': 0.4, 'pitch_env_amt': 180},
        'hat': {'decay': 0.04, 'tone': 0.6},
        'snare': {'body_freq': 200, 'snappy': 0.6},
        'bass': {
            'waveform': 'saw', 'cutoff': 600, 'resonance': 1.5,
            'env_mod': 2000, 'sub_level': 0.4, 'drive': 1.5,
        },
        'lead': {
            'cutoff': 4000, 'resonance': 0.3, 'filter_env_amt': 1500,
            'osc2_detune': 0.08, 'osc_mix': 0.5,
        },
        'pad': {'cutoff': 2000, 'resonance': 0.2, 'detune': 0.008},
        'pattern_rules': {
            'kick_density': 0.6,
            'hat_density': 0.7,
            'syncopation': 0.3,
            'bass_octave_range': [36, 48],
            'scale': 'minor',
            'bass_movement': 'root_fifth',
        },
    },
    'berlin': {
        'name': 'Berlin / Hard Techno',
        'bpm': 140,
        'swing': 0.0,
        'kick': {'pitch': 45, 'decay': 0.4, 'drive': 3.0, 'click': 0.6, 'pitch_env_amt': 250},
        'hat': {'decay': 0.03, 'tone': 0.8},
        'snare': {'body_freq': 180, 'snappy': 0.7},
        'bass': {
            'waveform': 'saw', 'cutoff': 400, 'resonance': 2.5,
            'env_mod': 4000, 'sub_level': 0.2, 'drive': 2.5,
        },
        'lead': {
            'cutoff': 2000, 'resonance': 0.5, 'filter_env_amt': 3000,
            'osc2_detune': 0.15, 'osc_mix': 0.6,
        },
        'pad': {'cutoff': 1500, 'resonance': 0.3, 'detune': 0.01},
        'pattern_rules': {
            'kick_density': 0.3,
            'hat_density': 0.9,
            'syncopation': 0.2,
            'bass_octave_range': [24, 36],
            'scale': 'minor',
            'bass_movement': 'chromatic',
        },
    },
    'acid': {
        'name': 'Acid Techno',
        'bpm': 138,
        'swing': 0.1,
        'kick': {'pitch': 52, 'decay': 0.45, 'drive': 2.0, 'click': 0.3, 'pitch_env_amt': 200},
        'hat': {'decay': 0.04, 'tone': 0.5},
        'snare': {'body_freq': 210, 'snappy': 0.5},
        'bass': {
            'waveform': 'square', 'cutoff': 500, 'resonance': 3.5,
            'env_mod': 5000, 'sub_level': 0.1, 'drive': 2.0,
            'glide_time': 0.05,
        },
        'lead': {
            'cutoff': 3000, 'resonance': 0.6, 'filter_env_amt': 4000,
            'osc2_detune': 0.05, 'osc_mix': 0.3,
        },
        'pad': {'cutoff': 2500, 'resonance': 0.15, 'detune': 0.006},
        'pattern_rules': {
            'kick_density': 0.5,
            'hat_density': 0.6,
            'syncopation': 0.5,
            'accent_probability': 0.3,
            'glide_probability': 0.2,
            'bass_octave_range': [36, 60],
            'scale': 'minor',
            'bass_movement': '303',
        },
    },
    'minimal': {
        'name': 'Minimal Techno',
        'bpm': 125,
        'swing': 0.15,
        'kick': {'pitch': 55, 'decay': 0.6, 'drive': 1.2, 'click': 0.2, 'pitch_env_amt': 150},
        'hat': {'decay': 0.06, 'tone': 0.4},
        'snare': {'body_freq': 190, 'snappy': 0.4},
        'bass': {
            'waveform': 'saw', 'cutoff': 300, 'resonance': 0.5,
            'env_mod': 800, 'sub_level': 0.5, 'drive': 1.0,
        },
        'lead': {
            'cutoff': 5000, 'resonance': 0.2, 'filter_env_amt': 1000,
            'osc2_detune': 0.03, 'osc_mix': 0.4,
        },
        'pad': {'cutoff': 3000, 'resonance': 0.1, 'detune': 0.005},
        'pattern_rules': {
            'kick_density': 0.4,
            'hat_density': 0.5,
            'syncopation': 0.6,
            'space': 0.7,
            'bass_octave_range': [36, 48],
            'scale': 'minor',
            'bass_movement': 'root_fifth',
        },
    },
}

STYLE_NAMES = list(STYLES.keys())

# Scale definitions (semitone offsets from root)
SCALES = {
    'minor': [0, 2, 3, 5, 7, 8, 10],
    'major': [0, 2, 4, 5, 7, 9, 11],
    'dorian': [0, 2, 3, 5, 7, 9, 10],
    'phrygian': [0, 1, 3, 5, 7, 8, 10],
    'chromatic': list(range(12)),
}


def get_scale_notes(root=36, scale='minor', octave_range=(36, 60)):
    """Get all MIDI notes in a scale within the given range."""
    intervals = SCALES.get(scale, SCALES['minor'])
    notes = []
    for octave in range(-2, 8):
        for interval in intervals:
            note = root + octave * 12 + interval
            if octave_range[0] <= note <= octave_range[1]:
                notes.append(note)
    return sorted(set(notes))
