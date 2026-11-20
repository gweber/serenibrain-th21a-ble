import cmath
import math
import random

import pytest

from th21a import cli
from th21a import protocol as p
from th21a.features import aperiodic_exponent, features
from th21a.quality import label_blocks, summary
from th21a.spectrum import WINDOW, band, fft, psd


def pink_block(rng, chi, n=WINDOW, level=20000.0, alpha=0.0):
    """One block of noise with power ~ 1/f^chi (random phases), optionally with a 10 Hz peak."""
    spec = [0j] * n
    for k in range(1, n // 2):
        f = k * p.SAMPLING_RATE / n
        amp = level * f ** (-chi / 2) * (1 + alpha * math.exp(-((f - 10) / 1.2) ** 2))
        spec[k] = amp * cmath.exp(2j * math.pi * rng.random())
        spec[n - k] = spec[k].conjugate()
    return [170000 + (v.conjugate() / n).real for v in fft([s.conjugate() for s in spec])]


def recording(rng, blocks=40, chi=1.5):
    return [x for _ in range(blocks) for x in pink_block(rng, chi)]


def test_fft_matches_a_plain_dft():
    rng = random.Random(0)
    xs = [complex(rng.gauss(0, 1), 0) for _ in range(64)]
    dft = [sum(x * cmath.exp(-2j * math.pi * k * i / 64) for i, x in enumerate(xs)) for k in range(64)]
    assert max(abs(a - b) for a, b in zip(fft(xs), dft)) < 1e-9


def test_psd_puts_a_tone_in_its_bin_and_band_leaves_out_mains():
    xs = [1000 * math.sin(2 * math.pi * 50 * i / 250) for i in range(WINDOW)]
    freqs, power = psd(xs)
    assert abs(freqs[power.index(max(power))] - 50) < 0.5
    assert band(freqs, power, 20, 100, mains=50) < 1e-4 * band(freqs, power, 20, 100)   # leakage beyond +-3 Hz only


@pytest.mark.parametrize("chi", [1.0, 1.5, 2.0])
def test_aperiodic_exponent_recovers_the_slope_over_averaged_blocks(chi):
    rng = random.Random(1)
    feats = features(label_blocks(recording(rng, 20, chi)))
    assert feats["aperiodic_exponent"] == pytest.approx(chi, abs=0.05)
    # one block alone is a noisy periodogram (sd ~0.3 over seeds): only the average is worth reading
    assert aperiodic_exponent(*psd(pink_block(rng, chi))) == pytest.approx(chi, abs=0.8)


def test_features_do_not_depend_on_the_gain():
    rng = random.Random(2)
    xs = [x - 170000 for x in recording(rng, 10)]
    a = features(label_blocks(xs))
    b = features(label_blocks([x * 37.5 for x in xs]))
    assert a == b and a["clean_blocks"] == 10


def test_alpha_peak_shows_in_band_powers_not_in_the_exponent():
    rng = random.Random(3)
    flat = features(label_blocks([x for _ in range(8) for x in pink_block(rng, 1.5)]))
    peak = features(label_blocks([x for _ in range(8) for x in pink_block(rng, 1.5, alpha=3.0)]))
    assert peak["rel_alpha"] > 2 * flat["rel_alpha"] and peak["alpha_theta"] > 2 * flat["alpha_theta"]
    assert peak["aperiodic_exponent"] == pytest.approx(flat["aperiodic_exponent"], abs=0.2)


def plant(xs, index):
    """A blink in block 10, a jaw clench in block 20, the rail in block 30, a dropped notification in block 35."""
    rng = random.Random(9)
    b = 10 * WINDOW + 200
    for i in range(-60, 60):                     # 0.5 s bump, ~10x the background amplitude
        xs[b + i] += 150000 * math.exp(-(i / 25) ** 2)
    b = 20 * WINDOW
    for i in range(WINDOW):                      # broad-band burst, stronger at high frequencies
        xs[b + i] += rng.gauss(0, 6000) - (rng.gauss(0, 6000) if i % 2 else 0)
    for i in range(30 * WINDOW, 30 * WINDOW + 50):
        xs[i] = p.ADC_MAX
    for i in range(35 * WINDOW + 100, len(index)):
        index[i] += 10


def test_labels_find_what_was_planted_and_nothing_else():
    rng = random.Random(4)
    xs = recording(rng)
    index = list(range(len(xs)))
    plant(xs, index)
    blocks = label_blocks(xs, index)
    labels = {i: b.label for i, b in enumerate(blocks) if b.label != "clean"}
    assert labels == {10: "eye", 20: "muscle", 30: "off", 35: "gap"}
    assert summary(blocks) == {"off": 1, "gap": 1, "muscle": 1, "eye": 1, "clean": 36}


def test_analyze_reads_a_stream_csv(tmp_path, capsys):
    rng = random.Random(5)
    xs = recording(rng, 20)
    index = list(range(len(xs)))
    xs[10 * WINDOW:10 * WINDOW + 100] = [p.ADC_MAX] * 100
    path = tmp_path / "session.csv"
    with open(path, "w") as f:
        f.write("time,counter,value,marker,battery_mv\n")
        for n, (i, x) in enumerate(zip(index, xs)):
            if 15 * WINDOW + 50 <= n < 15 * WINDOW + 60:
                continue                          # one notification lost
            f.write("%.4f,%d,%d,0,3900\n" % (i / 250, (i + 65000) % 65536, x))
    cli.main(["analyze", str(path)])
    out = capsys.readouterr().out
    assert "off 1  gap 1  muscle 0  eye 0  clean 17" in out
    assert "    0 min    ..........o....g...\n" in out
    assert "aperiodic_exponent" in out
