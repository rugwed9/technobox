import json
import os


def save_project(filepath, transport, clock, style_name, mixer_state=None):
    """Save project state to JSON."""
    data = {
        'version': 1,
        'bpm': clock.bpm,
        'swing': clock.swing,
        'style': style_name,
        'current_pattern': transport.current_pattern_idx,
        'patterns': [p.to_dict() for p in transport.patterns],
    }
    if mixer_state:
        data['mixer'] = mixer_state

    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else '.', exist_ok=True)
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    return filepath


def load_project(filepath):
    """Load project state from JSON. Returns dict or None."""
    if not os.path.exists(filepath):
        return None
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data
