# 6313: V.8 / V.34 negotiation after filter preflight

**No CONNECT yet.** Longer waiting and a diagnostic data-level reduction do not
resolve negotiation. No PBX/gateway settings or guest firmware were changed.
The new analyser and observer do not supply synthetic audio/carrier events.

## Results

| Attempt | Host output gain | Outcome |
|---|---|---|
| `../apple-training-underrun/prewarmed/6313` | unity | ANSWERED, 25 billed seconds; V.8 and CRC-valid INFO0 both ways; clean NO CARRIER, no active sample loss |
| `long-wait/6313` | unity, S7=60 | ANSWERED, 62 billed seconds; no received V.8 menu/overlays; fallback; clean NO CARRIER after 82.97 seconds off-hook PCM, no active sample loss |
| `data-quarter/call/6313` | unity digits, 0.25 after native command 0017; S7=60 | ANSWERED, 40 billed seconds; V.8 and CRC-valid INFO0 both ways; repeated setup, then local 55-sample underrun at 44.91 seconds off-hook PCM |

The long call's `486 Busy Here` is **not the INVITE outcome**: it immediately
follows a later OPTIONS probe. The initial INVITE receives 200 OK and ACK.
`long-wait-cdr.csv` confirms ANSWERED (`1792631642.2123`), correcting an initial
reading of the uncorrelated SIP summary. CDR timestamps are UTC; SIP timestamps
are PBX local NZDT (+13). The quarter-data call is `1792632332.2126`; see
`data-quarter/cdr.csv` and `channels-during-call.txt`.

## Independently decoded signal evidence

`tools/analyze_apple_call.py` follows the capture's exact per-frame rates and
produces separate 8-kHz WAVs plus a JSON timeline without opening hardware.
Times are captured sample time, not exact physical latency. TX applies recorded
host gain (older traces assume unity); RX is post DC/rate conversion. The final
failed TX block is an attempted submission, not proof of playback.

In **both** the original prewarmed call and the quarter-data call:

- Local V.21 channel 1 CM repeats `e0 c1 65 13 10 27 0a 0d`.
- Peer V.21 channel 2 JM repeats `e0 c1 45 13 10 2a 0d`.
- A 17-bit CRC-valid INFO0 body `11111111100001000` is independently recovered
  on local TX at 1200 Hz **and on RX at 2400 Hz**.
- On the quarter-data capture these occur in search windows TX 11.5–12.0 s,
  RX 12.0–12.5 s. On the original prewarmed capture: TX 13.5–14.0 s,
  RX 14.0–14.5 s. Search windows are not exact frame boundaries.

The peer's 2400-Hz component coexists with a stronger 1800-Hz component. A
single-dominant-FFT-bin classifier misses its INFO0. The analyser therefore
searches DPSK sync/CRC independently of the largest spectral peak. Tests include
valid INFO0 under a stronger interfering 1800-Hz tone and a silence control.
This establishes valid INFO0 reaching the recorded receive boundary, **not**
that the guest successfully qualifies it or completes phase 2.

The long unity-gain call differs: the captured peer sends ~5.4 seconds of answer
tone, no decoded JM, then fallback signals; the local modem eventually holds
1800 Hz. More S7 time alone does not recover that negotiation.

## Passive RTP capture and levels

`data-quarter/media.pcap` records four G.711 streams on Asterisk's Ethernet
interface; `rtp/` retains raw payloads, packet timestamps, WAVs and summaries.
Extraction uses sibling `tools/eicon_rtp_pcap_check.py`. Decoded CM/JM bytes agree
with the native codec recordings. Measured in decoded G.711 units:

- Local CM at diagnostic 0.25 data gain: **RMS 1547.6, -20.16 dBm0**.
- Peer JM: **RMS 3902.8, -12.13 dBm0**.

The CM is routable/decodable at that level, but attenuation does **not** remove
the repeated V.34 setup. These are bearer-domain measurements, not calibration
of Apple DAC voltage or AC01 dBm. Production gain defaults remain unchanged.

No RTP sequence/timestamp discontinuities are present in the four **locally
captured** streams. Caller-side interarrival nevertheless reaches **90.52 ms**;
peer-side maximum is 29.42 ms. Asterisk's during-call stats also report **15
lost packets / 2%** on the 6313 transmit leg, presumably from remote RTCP.
Thus this is not evidence of lossless end-to-end delivery; network/jitter and
remote playout still need investigation.

## Remaining stream/receive boundaries

The late quarter-data failure is **not** the original cold-filter stall:

- All known filters are prepared; `live_filter_misses` is empty.
- The 7200 → transient 8641.234462 → 9600 Hz transition succeeds.
- Helper stderr subsequently reports **55 active output gap samples**, verified
  hook release and worker exit 1. No reset-silence exception or larger buffer
  was used. Python's gap counter remains zero because the helper closed before
  replying; `hardware.log` is authoritative.
- Read-only DSP snapshots show `rx_empty_frames` increasing **143 → 188** around
  the retune and then remaining 188. This separate internal ADC boundary should
  be investigated alongside mixed-rate queuing; it is not a USB overflow count
  and is not yet a demonstrated cause of the negotiation failure.

Next useful work is correlating actual DSP detector input/qualification with
these valid INFO0 samples, checking retune input-queue timing and profiling the
late service deadline failure. No event, memory or negotiation-success patches
have been applied.

## Reproduce the diagnostic experiment

```sh
.venv/bin/python artifacts/apple-dial-extensions/run_attempt.py 6313 \
  --output artifacts/NEW-DIRECTORY --carrier-wait 60 --frames 6000 \
  --instructions 600000000 --timeout 150 --diagnostics --post-dial-gain 0.25

# numpy is available in the sibling v90modem venv:
../v90modem/.venv/bin/python tools/analyze_apple_call.py \
  artifacts/NEW-DIRECTORY/6313
```

`--post-dial-gain` is opt-in, modifies host analogue output scaling only after
native firmware command 0017, and leaves the earlier firmware-generated digits
at the requested initial gain. Default runner behavior is unchanged. Optional
stop-after-CONNECT watches actual serial CONNECT (default five seconds later),
not DSP tags or SIP answer. The regression selection with NumPy available passes
**101 tests in 21.61 s**; the three new offline-analysis tests pass independently.
