"""Label each 2-second block of a recording: off / gap / muscle / eye / clean.

The approach follows the single-channel artifact work in arXiv:2509.26058 (eye artifacts live at low frequencies,
muscle artifacts spread over the high ones), reduced to two band powers and fixed rules so it needs no training data.

The thresholds are relative to the recording itself: a block is "muscle" when its 20-100 Hz power is MUSCLE_FACTOR
times the median block of the same recording, and "eye" likewise for 1-4 Hz. That makes the labels independent of
the unknown counts-to-microvolt scale and of how well the pads conduct, at a price: the median has to be a clean
block, so a recording that is mostly clenched or mostly blinking labels too little. Start a recording with half a
minute of sitting still.
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from . import protocol as p
from .spectrum import WINDOW, band, psd

EYE_BAND = (0.9, 4.0)          # blinks and eye movements at Fp1/Fp2
MUSCLE_BAND = (20.0, 100.0)    # forehead and jaw muscle (EMG); mains and its harmonics are left out
EYE_FACTOR = 5.0               # power ratio to the median block (about 2.2x the amplitude)
MUSCLE_FACTOR = 4.0            # power ratio to the median block (2x the amplitude)
LABELS = ("off", "gap", "muscle", "eye", "clean")


@dataclass
class Block:
    start: int                 # position of the block's first sample in the input
    label: str
    eye: float | None = None       # 1-4 Hz power / the recording's median block
    muscle: float | None = None    # 20-100 Hz power / the recording's median block
    spectrum: tuple[list[float], list[float]] | None = None


def label_blocks(values, index=None, mains: int = 50, size: int = WINDOW) -> list[Block]:
    """Blocks of `size` samples with a label each. `index` (the unwrapped sample numbers, Sample.index) marks blocks
    that span a dropped notification as "gap"; without it, samples are taken as consecutive."""
    out, eye, muscle = [], [], []
    for start in range(0, len(values) - size + 1, size):
        xs = values[start:start + size]
        if sum(1 for x in xs if x >= p.ADC_MAX or x <= p.ADC_MIN) > 0.01 * size:
            out.append(Block(start, "off"))
            continue
        if index is not None and index[start + size - 1] - index[start] != size - 1:
            out.append(Block(start, "gap"))
            continue
        freqs, power = psd(xs)
        b = Block(start, "", spectrum=(freqs, power))
        b.eye, b.muscle = band(freqs, power, *EYE_BAND), band(freqs, power, *MUSCLE_BAND, mains=mains)
        eye.append(b.eye)
        muscle.append(b.muscle)
        out.append(b)
    eye_ref, muscle_ref = (median(eye) or 1e-12, median(muscle) or 1e-12) if eye else (1, 1)
    for b in out:
        if b.label:
            continue
        b.eye, b.muscle = b.eye / eye_ref, b.muscle / muscle_ref
        b.label = "muscle" if b.muscle > MUSCLE_FACTOR else "eye" if b.eye > EYE_FACTOR else "clean"
    return out


def summary(blocks: list[Block]) -> dict[str, int]:
    return {label: sum(1 for b in blocks if b.label == label) for label in LABELS}
