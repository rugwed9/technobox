import numpy as np
import wave
import struct
import os


def export_wav(render_func, filename, duration_bars=4, bpm=130, sr=48000, bit_depth=16):
    """Render the current pattern to a WAV file.

    Args:
        render_func: function(block_size) -> np.array(block_size, 2)
        filename: output file path
        duration_bars: number of bars (patterns) to render
        bpm: tempo
        sr: sample rate
        bit_depth: 16 or 24
    """
    beats_per_bar = 4
    total_beats = beats_per_bar * duration_bars
    total_seconds = total_beats * 60.0 / bpm
    total_samples = int(total_seconds * sr)

    block_size = 1024
    all_audio = []

    rendered = 0
    while rendered < total_samples:
        remaining = total_samples - rendered
        bs = min(block_size, remaining)
        block = render_func(bs)
        if block.shape[0] < bs:
            block = np.pad(block, ((0, bs - block.shape[0]), (0, 0)))
        all_audio.append(block)
        rendered += bs

    audio = np.concatenate(all_audio, axis=0)

    # Normalize to prevent clipping
    peak = np.abs(audio).max()
    if peak > 0:
        audio = audio / peak * 0.95

    # Ensure directory exists
    os.makedirs(os.path.dirname(filename) if os.path.dirname(filename) else '.', exist_ok=True)

    # Write WAV
    with wave.open(filename, 'w') as wf:
        wf.setnchannels(2)
        if bit_depth == 24:
            wf.setsampwidth(3)
        else:
            wf.setsampwidth(2)
        wf.setframerate(sr)

        if bit_depth == 16:
            data = (audio * 32767).astype(np.int16)
            wf.writeframes(data.tobytes())
        elif bit_depth == 24:
            # 24-bit encoding
            scaled = (audio * 8388607).astype(np.int32)
            frames = bytearray()
            for frame in scaled.flatten():
                b = frame.to_bytes(4, byteorder='little', signed=True)
                frames.extend(b[:3])
            wf.writeframes(bytes(frames))

    return filename
