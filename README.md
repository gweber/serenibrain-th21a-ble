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
```

`th21a check` prints a verdict: **NO CONTACT** (the amplifier input sits at the rail — band off, or a pad missing),
**POOR** / **FAIR** (mains hum — the hydrogel pads are drying out), or **GOOD**.

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
                print(s.counter, s.value, s.marker)
            n += 1
            if n == 50:
                await band.mark(1)                  # lands in the marker byte of the next sample
            if n == 100:
                break

asyncio.run(main())
```

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
