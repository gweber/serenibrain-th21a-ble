"""Spectral features that do not depend on the unknown counts-to-microvolt scale.

A gain factor multiplies every bin of the power spectrum by the same number. Relative band powers, band ratios and
the slope of the spectrum on log-log axes (the aperiodic or 1/f exponent, cf. arXiv:2001.09424) are unchanged by it,
so they can be compared between sessions and, with care, between headbands before the scale is known.

Only blocks labelled "clean" by quality.label_blocks() are used, and their spectra are averaged first: the spectrum of
a single 2 s block is too noisy for a fit (the exponent scatters by about +-0.3), 20 clean blocks (40 s) bring it to a
few hundredths on synthetic 1/f noise. Read the features only with clean_blocks of 10 or more.

At the forehead even clean blocks carry some eye activity in the delta band and some muscle in beta: read those two
with that in mind.
"""
from __future__ import annotations

import math

from .quality import Block
from .spectrum import band

BANDS = {"delta": (1.0, 4.0), "theta": (4.0, 8.0), "alpha": (8.0, 13.0), "beta": (13.0, 30.0)}
FIT_RANGE = (2.0, 30.0)        # the aperiodic fit; above 30 Hz forehead muscle flattens the spectrum
PEAK_SKIP = (7.0, 14.0)        # left out of the fit so an alpha peak does not bend the line


def mean_spectrum(blocks: list[Block]) -> tuple[list[float], list[float]] | None:
    """The average spectrum of the clean blocks (Welch's method with non-overlapping blocks), or None."""
    spectra = [b.spectrum for b in blocks if b.label == "clean" and b.spectrum]
    if not spectra:
        return None
    freqs = spectra[0][0]
    return freqs, [sum(s[1][k] for s in spectra) / len(spectra) for k in range(len(freqs))]


def aperiodic_exponent(freqs, power, lo: float = FIT_RANGE[0], hi: float = FIT_RANGE[1], skip=PEAK_SKIP) -> float:
    """The exponent chi of power ~ 1/f^chi: minus the least-squares slope of log10(power) over log10(f)."""
    pts = [(math.log10(f), math.log10(pw)) for f, pw in zip(freqs, power)
           if lo <= f <= hi and not skip[0] <= f <= skip[1] and pw > 0]
    if len(pts) < 3:
        raise ValueError("too few bins for a fit")
    mx = sum(x for x, _ in pts) / len(pts)
    my = sum(y for _, y in pts) / len(pts)
    slope = sum((x - mx) * (y - my) for x, y in pts) / sum((x - mx) ** 2 for x, _ in pts)
    return -slope


def features(blocks: list[Block]) -> dict[str, float] | None:
    """Relative band powers (share of 1-30 Hz), theta/beta and alpha/theta, and the aperiodic exponent, over the
    clean blocks; None if there are none."""
    spec = mean_spectrum(blocks)
    if spec is None:
        return None
    freqs, power = spec
    total = band(freqs, power, 1.0, 30.0)
    out = {"clean_blocks": sum(1 for b in blocks if b.label == "clean")}
    bp = {name: band(freqs, power, lo, hi) for name, (lo, hi) in BANDS.items()}
    out.update({f"rel_{name}": round(v / total, 3) for name, v in bp.items()})
    out["theta_beta"] = round(bp["theta"] / bp["beta"], 2)
    out["alpha_theta"] = round(bp["alpha"] / bp["theta"], 2)
    out["aperiodic_exponent"] = round(aperiodic_exponent(freqs, power), 2)
    return out
