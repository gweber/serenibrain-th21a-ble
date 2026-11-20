# serenibrain-th21a-ble

Read the **SereniBrain TH21A** EEG headband over Bluetooth LE from Python — on Linux, macOS or Windows, without the
vendor app and without any cloud.

The headband streams one EEG channel from the forehead at 250 Hz, plus event markers and the battery voltage. This
library connects, starts the stream and parses the packets. The protocol, and how each part of it was established,
is in [PROTOCOL.md](PROTOCOL.md).

> Unofficial. Not affiliated with SereniBrain or its manufacturer. Not a medical device; nothing here diagnoses or
> treats anything.

## Install

```bash
pip install git+https://github.com/gweber/serenibrain-th21a-ble
```

Needs Python 3.9+ and [bleak](https://github.com/hbldh/bleak). Close the SereniBrain app on your phone first: while
it is connected, the headband is invisible to everything else.

## Command line

```bash
th21a scan                  # find the headband
th21a info                  # model as the headband reports it
th21a check                 # 10 s electrode-contact check
th21a stream --seconds 60 > session.csv   # time,counter,value,marker,battery_mv
th21a analyze session.csv   # artifact labels per 2 s and scale-free features (offline)
```

`th21a check` prints a verdict: **NO CONTACT** (the amplifier input sits at the rail — band off, or a pad missing),
**POOR** / **FAIR** (mains hum — the hydrogel pads are drying out), **NOISY** (broad-band noise without a mains line
standing out: movement or a loose band, so it says nothing about the pads), or **GOOD**. The hum thresholds are raw
counts from one headband; `hum_vs_near` (the mains line against its neighbouring frequencies) is scale-free.

In `th21a stream`, `time` comes from the sample counter, not from when the Bluetooth packet arrived: samples are 4 ms
apart, anchored to the arrival of the first packet. A dropped notification leaves a hole in `time` and `counter`
and is reported on stderr (`gap: 10 samples missing before counter …`), with a summary at the end.

### Analysing a recording

`th21a analyze session.csv` splits the recording into 2-second blocks and labels each one, then computes spectral
features over the clean blocks:

```
blocks       off 1  gap 1  muscle 1  eye 1  clean 36
timeline     one mark per 2 s: o off, g gap, m muscle, e eye, . clean
    0 min    ..........e.........m.........o....g....
clean_blocks       36
rel_delta          0.556
rel_theta          0.199
rel_alpha          0.109
rel_beta           0.136
theta_beta         1.46
alpha_theta        0.55
aperiodic_exponent 1.47
```

(Synthetic 80 s test recording with a blink, a clench, a rail block and a dropped notification planted at
known places; from `tests/test_analysis.py`.)

- **Labels** (after the single-channel artifact approach in [arXiv:2509.26058](https://arxiv.org/abs/2509.26058)):
  *eye* = unusual power at 1–4 Hz (blinks, eye movements), *muscle* = unusual power at 20–100 Hz (forehead, jaw;
  mains left out), *off* = input at the rail, *gap* = a dropped notification. "Unusual" means several times the
  recording's median block, so the labels need no microvolt scale, but the median block has to be clean: start a
  recording with half a minute of sitting still. The thresholds are starting points, not validated on many people.
- **Features** are the ones an unknown gain cannot change: band powers as a share of 1–30 Hz, theta/beta,
  alpha/theta, and the aperiodic (1/f) exponent fitted over 2–30 Hz without the alpha range. They come from the
  averaged spectrum of the clean blocks; with fewer than ~10 clean blocks (20 s) they are too noisy to read.
- `--blocks` prints one CSV line per block (start, label, eye and muscle ratios) for your own plots.

## Python

```python
import asyncio
from th21a import Headband, find

async def main():
    async with Headband(await find()) as band:
        print(await band.info())
        n = 0
        async for packet in band.stream():          # ~25 packets a second, 10 samples each
            for s in packet.samples:
                print(s.index, s.counter, s.value, s.marker)   # index: the counter unwrapped, 0, 1, 2, ...
            n += 1
            if n == 50:
                await band.mark(1)                  # lands in the marker byte of the next sample
            if n == 100:
                break

asyncio.run(main())
```

`band.clock.lost` / `band.clock.gaps` count samples missing from the counter (dropped notifications); `band.errors`
counts packets that did not parse.

The parser alone needs no Bluetooth: `th21a.parse(bytes)` returns an `EEGPacket` or `InfoPacket`.

## Good to know

- **Values are raw ADC counts** (signed 24-bit). The factor to microvolts is not known yet — help welcome.
- **Pads matter.** Dried hydrogel pads give strong 50/60 Hz hum. See *Practical notes* in PROTOCOL.md.
- **A forehead band is not an occipital EEG.** Muscle tension, blinks and band ratios work; the classic
  eyes-closed alpha rise is weak at the forehead.
- **Your EEG is health data.** This library stores nothing; what you record is yours to protect.

## Credits

[hiiambob89/EEG-Adapter-and-Visualizer](https://github.com/hiiambob89/EEG-Adapter-and-Visualizer) found the GATT
layout and the first working start sequence.

## License

MIT
