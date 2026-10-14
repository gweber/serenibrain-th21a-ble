"""th21a scan | info | stream | check -- see README.md."""
from __future__ import annotations

import argparse
import asyncio
import math
import sys
import time

from . import protocol as p


def goertzel_power(xs, freq, rate=p.SAMPLING_RATE):
    """Power of one frequency in a block of samples (no numpy needed)."""
    k = 2 * math.cos(2 * math.pi * freq / rate)
    s1 = s2 = 0.0
    mean = sum(xs) / len(xs)
    for x in xs:
        s1, s2 = (x - mean) + k * s1 - s2, s1
    return (s1 * s1 + s2 * s2 - k * s1 * s2) / len(xs) ** 2


def contact_report(xs, mains=50):
    """A rough electrode-contact check on a few seconds of samples.

    The hum thresholds (RMS, raw counts) come from one headband: dried-out pads gave ~1100, re-moistened ones 750-800,
    and soaking them overnight cut the hum power by a further factor of ~6. Treat them as a guide, not a spec."""
    sat = sum(1 for x in xs if x >= p.ADC_MAX or x <= p.ADC_MIN) / len(xs)
    mean = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mean) ** 2 for x in xs) / len(xs))
    hum = math.sqrt(2 * goertzel_power(xs, mains))
    near = sum(math.sqrt(2 * goertzel_power(xs, f)) for f in (mains - 6, mains - 4, mains + 4, mains + 6)) / 4
    if sat > 0.01:
        verdict = "NO CONTACT: the input sits at the rail (band off the head, or a pad missing)"
    elif hum > 1000:
        verdict = "POOR: strong mains hum -- moisten or replace the hydrogel pads, tighten the band"
    elif hum > 400:
        verdict = "FAIR: noticeable mains hum -- usable with a notch filter; fresher pads help"
    else:
        verdict = "GOOD"
    return {"saturated": round(sat, 3), "sd_counts": round(sd), "hum_rms_counts": round(hum), "hum_vs_near": round(hum / max(near, 1e-9)),
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
        print("time,counter,value,marker,battery_mv")
        end = time.time() + args.seconds if args.seconds else None
        async for pkt in band.stream():
            t = time.time()
            for s in pkt.samples:
                print("%.3f,%d,%d,%d,%d" % (t, s.counter, s.value, s.marker, pkt.battery_mv))
            if end and t > end:
                break


async def check(args):
    from .client import Headband
    async with Headband(await _device(args)) as band:
        xs, end = [], time.time() + args.seconds
        async for pkt in band.stream():
            xs += [s.value for s in pkt.samples]
            if time.time() > end:
                break
    for k, v in contact_report(xs[250:] or xs, args.mains).items():     # the first second settles
        print("%-12s %s" % (k, v))


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
    args = ap.parse_args(argv)
    try:
        asyncio.run(args.fn(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
