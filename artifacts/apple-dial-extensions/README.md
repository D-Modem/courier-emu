# Separate extension attempts: 6311 and 6312

**Later result:** [reset/hang-up continuity is fixed](../apple-reset-continuity/README.md).
A new 6311 attempt returns cleanly with `NO CARRIER`, zero active gaps/overflows,
and verified hook release. The captures below retain the earlier failures.

These are **two separate calls**, correcting the earlier interpretation as
`63116312`. The optimized 403 worker sent `ATX1S7=20DT6311`, released the line,
and then sent `ATX1S7=20DT6312`. Independent USB readbacks verify on-hook after
each attempt, including before the second call.

| Extension | Decoded codec TX DTMF | Successful off-hook PCM | Native polls | Result |
|---|---|---:|---:|---|
| 6311 | `6311` | 29.943 s | 78,990 | No CONNECT/final response; local underrun at reset |
| 6312 | `6312` | 29.943 s | 78,992 | No CONNECT/final response; local underrun at reset |

Unlike the earlier last-generation-only capture, these traces retain PCM
across **every DSP generation**. Goertzel decoding of the original firmware's
transmitted waveform independently recovers the requested four digits in each
case. This capture is at the Courier codec boundary, before the Apple's hardware
rate converter and output gain; it is not a far-end acknowledgement of digits.

Both workers finish with a local hardware stream failure at DSP teardown/reset,
not a clean Hayes result from the called modem. The helper reports active output
gaps and releases the line. Neither result should be described as confirmed
remote no-answer/busy. No CONNECT or sustained modem answer tone is established.
RX contains strong/clipped low-frequency audio; nominal-frequency measurements
in `audio-analysis.json` are not a validated call-progress classifier.

Each extension directory contains:

- `summary.json`, `report.json`: invocation, result and native execution counts.
- `hardware.log`: actual final underrun counter and hook-release confirmation.
  The report's socket counters precede the failure and can still show zero.
- `final-line-status.*`: independent post-call USB status (hook bit clear).
- `codec-tx.s16`, `codec-rx.s16`: signed PCM16 little-endian, with variable rates.
- `codec-frames.jsonl`: rate, hook state, wall timestamp and sample offsets for
  every codec exchange. RX is after rate conversion/DC blocking; TX is before
  hardware gain. Respect the rate metadata; these are not fixed-8-kHz files.
- `audio-analysis.json`: independently decoded DTMF plus RX frequency-bin checks.

`run_attempt.py` reproduces one explicit attempt to 6311 or 6312 (no redial loop);
`trace_worker.py` records the codec boundary without supplying any received
audio, digits or carrier result to the guest. The runner now also accepts 6313,
`--carrier-wait`, configurable frame/instruction/time budgets and `--diagnostics`
for once-per-second read-only DSP snapshots. It stops five seconds after a real
serial CONNECT by default (`--stop-after-connect 0` disables that limit).

`--post-dial-gain` is an **explicit diagnostic experiment**, not a production
default: it changes host TX gain once firmware command `0017` starts negotiation,
after the firmware-generated digits. New frame metadata records the applied
`tx_gain`; raw TX remains before that gain. See
[negotiation results](../apple-negotiation-6313/README.md). The wrapper does not
patch guest memory, consume peripheral registers, inject DSP messages or invent
carrier. Invalid/non-finite gains and nonpositive call budgets are rejected.

New captures also retain `codec-hardware-{tx,rx}.s16` and
`codec-hardware-frames.jsonl`: TX is the actual post-resampler/post-gain helper
submission, RX is raw helper input before DC blocking. These remain attempted
submissions, not proof of DAC playback. Codec-side events now specify `rx_rate`
independently when RX stays on the fixed hardware clock. `--rx-grid codec` is
an opt-in diagnostic control restoring the original preconverted RX; see
[audio-path audit](../apple-adc-grid/README.md).
