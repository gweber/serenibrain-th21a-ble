# TH21A Bluetooth LE protocol

What is known about how the SereniBrain TH21A headband talks over Bluetooth LE, and how each point was established.
Firmware as shipped in 2025; other firmware may differ — verify on your unit.

## Device

- Advertised name: `TH21A_<12 hex digits>` (the Bluetooth address without colons).
- Electrodes: three hydrogel pads on 4 mm snaps across the forehead — Fp1 and Fp2 with the reference at Fpz.
- Chip: Nordic nRF (it exposes Nordic's buttonless DFU service `0000fe59-…`). **Never write to the DFU service**:
  that is the firmware-update path.
- While the phone app is connected, the headband does not advertise. Close the app first.

## GATT

| UUID | Properties | Use |
|---|---|---|
| `8653000a-43e6-47b7-9cb0-5fc21d4ae340` | service | data service |
| `8653000b-43e6-47b7-9cb0-5fc21d4ae340` | notify | packets from the headband |
| `8653000c-43e6-47b7-9cb0-5fc21d4ae340` | write, write without response | commands to the headband |

The default MTU (23) is enough: bleak on Linux received complete 92-byte packets without negotiating a larger MTU.

## Commands

Every command is 8 bytes: ASCII `CTRL`, then two big-endian 16-bit words `group, code`.

| Bytes after `CTRL` | Meaning |
|---|---|
| `00 03 00 05` | get device info (answer: an INFO packet) |
| `00 04 00 01` | self-check |
| `00 03 00 03` | **start** streaming |
| `00 03 00 04` | **stop** streaming |
| `00 04 00 02` | calibrate the gyroscope |
| `00 05 00 nn` | event marker `nn` (1–255) |

No keep-alive is needed: one start command streams until stop or disconnect.

Notes on the evidence: the start sequence was first published by
[hiiambob89/EEG-Adapter-and-Visualizer](https://github.com/hiiambob89/EEG-Adapter-and-Visualizer), which labels
`00 03 00 03` as "stop/reset" and sends `00 05 00 02` every second as a "keep-alive". The vendor app sends
`00 03 00 03` to start acquisition and `00 03 00 04` to stop it, and `00 05 00 nn` is its event-marker call; the
marker interpretation is confirmed on the device (below).

## Packets

All packets start with a 12-byte header:

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | ASCII `DATA` |
| 4 | 2 | type, big-endian: 1 = info, 2 = EEG |
| 6 | 2 | channel count, big-endian (3: EEG, marker and one more — see below) |
| 8 | 4 | payload length, **little-endian** (32 for info, 80 for EEG) |

### Type 1 — info (44 bytes)

Payload starts with the model, ASCII `TH21A`, zero-padded. The rest
(`…01 00 00 00 01 00 00 00 0a 00 00 00 02 00 00 00 18 00 00 00 0c`) is not decoded yet; `0x0a` = 10 samples per
packet and `0x18` = 24 bits per sample would fit.

### Type 2 — EEG (92 bytes, ~25 per second)

Ten samples of 7 bytes, then a 10-byte trailer.

| Offset in sample | Size | Field |
|---|---|---|
| 0 | 3 | EEG value, signed 24-bit little-endian, raw ADC counts |
| 3 | 1 | marker: 0, or the `nn` of a marker command |
| 4 | 1 | unknown (0 in every capture so far) |
| 5 | 2 | sample counter, little-endian, wraps at 65536 |

| Offset in trailer | Size | Field |
|---|---|---|
| 0 | 2 | battery voltage in mV, little-endian (e.g. `68 0f` = 3944) |
| 2 | 8 | not decoded (two values that change from packet to packet, then `00 00`) |

Evidence:
- **Rate**: 35,120 samples in 140.5 s = 250.0 Hz, with no gap in the counter.
- **Marker**: five marker commands (`nn` = 1…5) sent 5 s apart each appeared exactly once in the marker byte, about
  1,300 samples apart. A marker sent every second appeared once per second.
- **One EEG value per sample**: the 24-bit value is the only field that behaves like a signal.
- **It is the amplifier input**: on the head the value sits in range (around 1.3–2.9 × 10⁵ counts, s.d. ~600–3000);
  with the band lying on the table it drifts towards and then sticks at the rail `0x7FFFFF` = 8,388,607.
- **It responds to the body**: clenching the jaw doubles the 20–45 Hz power (muscle activity).

## Not known yet

- **The scale from counts to microvolts.** The vendor converts the integer to a float in a native library; the
  factor has not been recovered. Everything here is in raw counts.
- Whether the two forehead electrodes form one bipolar channel (Fp1 − Fp2) or Fp1 against Fpz.
- The gyroscope data (the vendor app can calibrate it; no gyroscope packet has been seen in a plain stream).
- The rest of the info packet and of the EEG trailer.

## Practical notes

- **Pads**: the hydrogel pads dry out (the vendor says ~3 months at one hour a day, and to keep them in a sealed bag
  when unused). Dried pads show up as strong 50/60 Hz mains hum. A drop of saline and a night in a sealed bag
  restored a year-old set noticeably (hum power down by a factor of ~10). Standard ECG electrodes with a 4 mm snap,
  cut to size, are a cheap substitute — the three must not touch each other.
- **What a forehead band can show**: muscle tension (forehead, jaw), blinks and eye movements, slow/fast band
  ratios. The eyes-closed alpha rise is an occipital effect and is weak or absent at Fp1/Fp2 — not a good test
  of whether the band works.
