import numpy as np


class VariationEngine:
    """Creates musical variations of existing patterns."""

    def __init__(self):
        self.rng = np.random.default_rng()

    def humanize(self, velocities, amount=0.1):
        """Add human-like velocity variation."""
        result = velocities.copy()
        for i in range(len(result)):
            if result[i] > 0:
                noise = self.rng.normal(0, amount)
                result[i] = max(0.1, min(1.0, result[i] + noise))
        return result

    def generate_fill(self, length=16, density=0.7, voice='snare'):
        """Generate a drum fill for the last bar."""
        fill = np.zeros(length, dtype=np.float64)
        # Fill typically happens in last 4 steps
        fill_start = length - 4
        for i in range(fill_start, length):
            if self.rng.random() < density:
                fill[i] = 0.6 + self.rng.random() * 0.4
        return fill

    def mutate(self, velocities, mutation_rate=0.2):
        """Randomly alter a pattern while keeping the groove feel."""
        result = velocities.copy()
        for i in range(len(result)):
            if self.rng.random() < mutation_rate:
                if result[i] > 0:
                    # Might remove, shift, or add ghost note
                    action = self.rng.choice(['remove', 'ghost', 'keep'])
                    if action == 'remove':
                        result[i] = 0.0
                    elif action == 'ghost':
                        result[i] = 0.3
                else:
                    if self.rng.random() < 0.3:
                        result[i] = 0.4  # Add ghost note
        return result

    def shift(self, velocities, amount=1):
        """Rotate pattern by N steps."""
        return np.roll(velocities, amount)

    def reverse(self, velocities):
        """Reverse a pattern."""
        return velocities[::-1].copy()

    def thin(self, velocities, keep_probability=0.5):
        """Remove random hits to create space."""
        result = velocities.copy()
        for i in range(len(result)):
            if result[i] > 0 and self.rng.random() > keep_probability:
                # Keep strong beats (0, 4, 8, 12)
                if i % 4 != 0:
                    result[i] = 0.0
        return result

    def densify(self, velocities, add_probability=0.3):
        """Add ghost notes to fill gaps."""
        result = velocities.copy()
        for i in range(len(result)):
            if result[i] == 0 and self.rng.random() < add_probability:
                result[i] = 0.3  # ghost note
        return result
