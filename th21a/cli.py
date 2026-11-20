"""th21a scan | info | stream | check | analyze -- see README.md."""
from __future__ import annotations

import argparse
import asyncio
import csv
import math
import sys
import time

from . import protocol as p
from .timing import SampleClock, sample_time


def goertzel_power(xs, freq, rate=p.SAMPLING_RATE):
    """Power of one frequency in a block of samples (no numpy needed)."""
    k = 2 * math.cos(2 * math.pi * freq / rate)
    s1 = s2 = 0.0
    mean = sum(xs) / len(xs)
    for x in xs:
        s1, s2 = (x - mean) + k * s1 - s2, s1
    return (s1 * s1 + s2 * s2 - k * s1 * s2) / len(xs) ** 2


LINE_RATIO = 3   # the mains bin must be this many times its neighbours (amplitude) to count as hum


def contact_report(xs, mains=50):
    """A rough electrode-contact check on a few seconds of samples.

    The hum thresholds (RMS, raw counts) come from one headband: dried-out pads gave ~1100, re-moistened ones 750-800,
    and soaking them overnight cut the hum power by a further factor of ~6. Treat them as a guide, not a spec.

    `hum_vs_near` (the mains line against the bins 4-6 Hz beside it) does not depend on the unknown counts-to-microvolt
    scale. A pad problem shows up as a narrow line; if the mains bin is no higher than its neighbours, the energy there
    is broad-band (movement, a loose band) and says nothing about the pads, so POOR/FAIR need the line to stand out."""
    sat = sum(1 for x in xs if x >= p.ADC_MAX or x <= p.ADC_MIN) / len(xs)
    mean = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))
    hum = math.sqrt(2 * goertzel_power(xs, mains))
    near = sum(math.sqrt(2 * goertzel_power(xs, f)) for f in (mains - 6, mains - 4, mains + 4, mains + 6)) / 4
    ratio = hum / max(near, 1e-9)
    if sat > 0.01:
        verdict = "NO CONTACT: the input sits at the rail (band off the head, or a pad missing)"
    elif hum > 400 and ratio < LINE_RATIO:
        verdict = "NOISY: broad-band noise, not mains hum -- keep still and check the band's fit, then check again"
    elif hum > 1000:
        verdict = "POOR: strong mains hum -- moisten or replace the hydrogel pads, tighten the band"
    elif hum > 400:
        verdict = "FAIR: noticeable mains hum -- usable with a notch filter; fresher pads help"
    else:
        verdict = "GOOD"
    return {"saturated": round(sat, 3), "sd_counts": round(sd), "hum_rms_counts": round(hum), "hum_vs_near": round(ratio, 1),
            "verdict": verdict}


async def _device(args):
    from .client import find
    if args.address:
        return args.address
    d = await find()
    if d is None:
        sys.exit("no TH21A found -- switch it on, close the phone app, come closer")
    print("found %s (%s)" % (d.name, d.address), file=sys.stderr)
    return d


async def scan(args):
    from .client import find
    d = await find(args.seconds)
    print("%s %s" % (d.name, d.address) if d else "none found")


async def info(args):
    from .client import Headband
    async with Headband(await _device(args)) as band:
        pkt = await band.info()
        print(pkt.model if pkt else "no answer", pkt.payload.hex() if pkt else "")


async def stream(args):
    from .client import Headband
    async with Headband(await _device(args)) as band:
        # time comes from the sample counter (evenly spaced at 250 Hz), anchored to when the first packet arrived;
        # arrival times would give 10 equal stamps per notification and BLE jitter.
        print("time,counter,value,marker,battery_mv")
        end = time.time() + args.seconds if args.seconds else None
        t0, lost = None, 0
        async for pkt in band.stream():
            t = time.time()
            if t0 is None:
                t0 = t - pkt.samples[-1].index / p.SAMPLING_RATE
            if band.clock.lost > lost:
                print("gap: %d samples missing before counter %d" % (band.clock.lost - lost, pkt.samples[0].counter),
                      file=sys.stderr)
                lost = band.clock.lost
            for s in pkt.samples:
                print("%.4f,%d,%d,%d,%d" % (sample_time(s.index, t0), s.counter, s.value, s.marker, pkt.battery_mv))
            if end and t > end:
                break
        _summary(band)


def _summary(band):
    c = band.clock
    if c.lost or c.glitches or band.errors:
        print("%d samples lost in %d gaps, %d repeated/out-of-order, %d bad packets"
              % (c.lost, c.gaps, c.glitches, band.errors), file=sys.stderr)


async def check(args):
    from .client import Headband
    async with Headband(await _device(args)) as band:
        xs, end = [], time.time() + args.seconds
        async for pkt in band.stream():
            xs += [s.value for s in pkt.samples]
            if time.time() > end:
                break
        _summary(band)
    for k, v in contact_report(xs[250:] or xs, args.mains).items():     # the first second settles
        print("%-12s %s" % (k, v))


MARKS = {"off": "o", "gap": "g", "muscle": "m", "eye": "e", "clean": "."}


def load_csv(path):
    """Values and unwrapped sample numbers from a `th21a stream` CSV."""
    clock, values, index = SampleClock(), [], []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            values.append(int(row["value"]))
            index.append(clock.feed(int(row["counter"])))
    return values, index


def analyze(args):
    """Block labels and scale-free features of a recorded session (offline, no Bluetooth)."""
    from .features import features
    from .quality import label_blocks, summary
    values, index = load_csv(args.csv)
    blocks = label_blocks(values, index, mains=args.mains)
    if not blocks:
        sys.exit("too short: a block is 512 samples (2 s)")
    if args.blocks:
        print("start_s,label,eye,muscle")
        for b in blocks:
            print("%.2f,%s,%s,%s" % (index[b.start] / p.SAMPLING_RATE, b.label,
                                     "" if b.eye is None else round(b.eye, 2), "" if b.muscle is None else round(b.muscle, 2)))
        return
    print("blocks       %s" % "  ".join("%s %d" % kv for kv in summary(blocks).items()))
    marks = "".join(MARKS[b.label] for b in blocks)
    print("timeline     one mark per 2 s: %s" % ", ".join("%s %s" % (m, k) for k, m in MARKS.items()))
    for i in range(0, len(marks), 60):          # 60 marks = 2 minutes per line
        print("  %3d min    %s" % (i // 30, marks[i:i + 60]))
    feats = features(blocks)
    if feats is None:
        print("features     none: no clean block")
    for k, v in (feats or {}).items():
        print("%-18s %s" % (k, v))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="th21a", description=__doc__)
    ap.add_argument("--address", help="Bluetooth address (default: the first TH21A found)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("--seconds", type=float, default=20); s.set_defaults(fn=scan)
    sub.add_parser("info").set_defaults(fn=info)
    s = sub.add_parser("stream", help="CSV to stdout"); s.add_argument("--seconds", type=float, default=0); s.set_defaults(fn=stream)
    s = sub.add_parser("check", help="electrode contact check")
    s.add_argument("--seconds", type=float, default=10); s.add_argument("--mains", type=int, default=50, choices=(50, 60))
    s.set_defaults(fn=check)
    s = sub.add_parser("analyze", help="artifact labels and scale-free features of a recorded CSV")
    s.add_argument("csv"); s.add_argument("--mains", type=int, default=50, choices=(50, 60))
    s.add_argument("--blocks", action="store_true", help="one CSV line per 2 s block instead of the summary")
    s.set_defaults(fn=analyze)
    args = ap.parse_args(argv)
    if args.fn is analyze:
        return analyze(args)
    try:
        asyncio.run(args.fn(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
