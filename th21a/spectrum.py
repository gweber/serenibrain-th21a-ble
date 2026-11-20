"""Power spectra in plain Python (no numpy): a radix-2 FFT over Hann-windowed blocks."""
from __future__ import annotations

import cmath
import math

from . import protocol as p

WINDOW = 512                 # samples per block: 2.048 s at 250 Hz, 0.49 Hz per bin


def fft(xs: list[complex]) -> list[complex]:
    """Iterative radix-2 FFT; len(xs) must be a power of two."""
    n = len(xs)
    out = list(xs)
    j = 0
    for i in range(1, n):                      # bit-reversal permutation
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            out[i], out[j] = out[j], out[i]
    size = 2
    while size <= n:
        step = cmath.exp(-2j * math.pi / size)
        for start in range(0, n, size):
            w = 1
            for k in range(size // 2):
                a, b = out[start + k], out[start + k + size // 2] * w
                out[start + k], out[start + k + size // 2] = a + b, a - b
                w *= step
        size *= 2
    return out


def psd(xs, rate: float = p.SAMPLING_RATE) -> tuple[list[float], list[float]]:
    """(frequencies, power) of one block, mean removed, Hann window. Power is in counts^2 per bin, so only ratios
    between bins and blocks are meaningful while the counts-to-microvolt scale is unknown."""
    n = len(xs)
    if n & (n - 1):
        raise ValueError("block length must be a power of two")
    mean = sum(xs) / n
    win = [0.5 - 0.5 * math.cos(2 * math.pi * i / n) for i in range(n)]
    spec = fft([(x - mean) * w for x, w in zip(xs, win)])
    norm = sum(w * w for w in win)
    freqs = [k * rate / n for k in range(n // 2 + 1)]
    power = [abs(spec[k]) ** 2 / norm for k in range(n // 2 + 1)]
    return freqs, power


def band(freqs, power, lo: float, hi: float, mains: int | None = None) -> float:
    """Summed power in [lo, hi) Hz, leaving out +-3 Hz around the mains frequency and its harmonics."""
    total = 0.0
    for f, pw in zip(freqs, power):
        if lo <= f < hi and not (mains and min(abs(f - h) for h in range(mains, 126 + mains, mains)) <= 3):
            total += pw
    return total


def blocks(xs, size: int = WINDOW):
    """Consecutive non-overlapping blocks of `size` samples (the remainder is dropped)."""
    return [xs[i:i + size] for i in range(0, len(xs) - size + 1, size)]
