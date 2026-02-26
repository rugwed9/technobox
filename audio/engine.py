import threading
import time
import numpy as np
import sounddevice as sd


class RingBuffer:
    """Lock-free single-producer single-consumer ring buffer."""

    def __init__(self, capacity):
        self.capacity = capacity
        self.buffer = np.zeros(capacity, dtype=np.float32)
        self.write_pos = 0
        self.read_pos = 0

    @property
    def read_available(self):
        return self.write_pos - self.read_pos

    @property
    def write_available(self):
        return self.capacity - self.read_available

    def write(self, data):
        n = len(data)
        if n > self.write_available:
            return False
        pos = self.write_pos % self.capacity
        if pos + n <= self.capacity:
            self.buffer[pos:pos + n] = data
        else:
            split = self.capacity - pos
            self.buffer[pos:] = data[:split]
            self.buffer[:n - split] = data[split:]
        self.write_pos += n
        return True

    def read(self, n):
        if n > self.read_available:
            return None
        pos = self.read_pos % self.capacity
        if pos + n <= self.capacity:
            data = self.buffer[pos:pos + n].copy()
        else:
            split = self.capacity - pos
            data = np.concatenate([self.buffer[pos:], self.buffer[:n - split]])
        self.read_pos += n
        return data


class AudioState:
    """Shared state from render thread to UI. Written atomically."""

    def __init__(self):
        self.current_step = 0
        self.peak_l = 0.0
        self.peak_r = 0.0
        self.cpu_load = 0.0
        self.playing = False
        self.bpm = 130.0


class AudioEngine:
    """Core audio engine with render thread and sounddevice output."""

    def __init__(self, sample_rate=48000, block_size=1024):
        self.sr = sample_rate
        self.block_size = block_size
        self.channels = 2

        # Ring buffer: 8 blocks ahead
        buf_size = 8 * block_size * self.channels
        self.ring_buffer = RingBuffer(buf_size)

        self.state = AudioState()
        self._running = False
        self._render_thread = None
        self.stream = None

        # These get set by the app
        self.render_callback = None  # function(block_size) -> np.array(block_size, 2)

    def start(self):
        self._running = True
        self._render_thread = threading.Thread(target=self._render_loop, daemon=True)
        self._render_thread.start()
        self.stream = sd.OutputStream(
            samplerate=self.sr,
            blocksize=self.block_size,
            channels=self.channels,
            dtype='float32',
            callback=self._audio_callback,
            latency='low',
        )
        self.stream.start()

    def stop(self):
        self._running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None
        if self._render_thread:
            self._render_thread.join(timeout=2.0)
            self._render_thread = None

    def _audio_callback(self, outdata, frames, time_info, status):
        needed = frames * self.channels
        if self.ring_buffer.read_available >= needed:
            data = self.ring_buffer.read(needed)
            outdata[:] = data.reshape(frames, self.channels)
        else:
            outdata.fill(0)

    def _render_loop(self):
        while self._running:
            needed = self.block_size * self.channels
            if self.ring_buffer.write_available >= needed:
                t0 = time.perf_counter()
                if self.render_callback:
                    block = self.render_callback(self.block_size)
                else:
                    block = np.zeros((self.block_size, 2), dtype=np.float64)

                # Update peaks
                self.state.peak_l = float(np.abs(block[:, 0]).max())
                self.state.peak_r = float(np.abs(block[:, 1]).max())

                # Write to ring buffer as interleaved float32
                interleaved = block.astype(np.float32).ravel()
                self.ring_buffer.write(interleaved)

                dt = time.perf_counter() - t0
                budget = self.block_size / self.sr
                self.state.cpu_load = dt / budget
            else:
                time.sleep(0.001)
