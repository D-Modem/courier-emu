# Courier ADC phase quantization and the 56000 investigation, 31 October 2026

## Retained numerical correction

`C5xCore::codec_line_sample` now linearly interpolates adjacent entries in the
existing 1025-entry phase table instead of rounding the ADC instant to a
single phase. The original 128 taps, Kaiser window, cutoff, FIR delay, line
FIFO, source/codec clocks and sample consumption are unchanged. The table
already includes the upper endpoint, so interpolation requires neither a
new input sample nor a history shift.

At an 8 kHz source / 9.6 kHz ADC, with a 10000-amplitude integer sine input,
the measured SNRs (including amplitude and phase error, no fitting) are:

| Frequency | Nearest-phase lookup | Interpolated kernel |
| ---: | ---: | ---: |
| 1000 Hz | 74.08 dB | 88.03 dB |
| 3000 Hz | 63.95 dB | 94.32 dB |
| 3800 Hz | 61.90 dB | 80.27 dB |
| 3900 Hz | 26.87 dB | 26.87 dB |

The 3900-Hz result distinguishes finite-filter response from phase-table
quantization; this correction does not flatten that response. Tests retain
fixed physical time and delay rather than fitting either away. **75 focused
emulator tests pass**, including ADC retunes, FIFO accounting, prepared-grid
behavior, frame servicing and native CPU/port regressions.

## 56000 remains unqualified

Our server's index 15 at B=37, MD=5 carries exactly 56000 bits/s (x2 Draft
0.33 clauses 10/11/22). The Courier's allowed mask is already **7FFF** and
MD is **5**; a missing capability bit is not the ceiling.

Read-only capture at original Courier 403 **E2EC** retains the adjusted ACC
metric before E2F3's descending threshold search, the allowed mask, margin,
MD, saved indices, MP and all fifteen thresholds. The index-15 threshold is
**4680 (18048)**. In the original reconstruction call, late metrics average
**17775.625** over the last eight retained observations; with interpolation,
**17932.5**, with a maximum retained metric **18023**. Both calls negotiate
index 14, actual **54666/31200**, and deliver **5200/5200 downstream plus
28/28 upstream bytes exactly**.

A longer interpolation call also stays at index 14. Its payload is withheld
until bearer sample **1000000 (125 s)** and still arrives exactly, so it is
not merely an early-bootstrap payload pass. Its last 64 retained metrics range
17253..17376, with adaptive margin changes; the initial improvement must not
be extrapolated into guaranteed index-15 selection.

## Rejected/excluded experiments

- A 256-tap reconstruction improves the independent 3900-Hz tone result to
  **76.03 dB**, but the call negotiates only **52000**. Its additional FIR
  delay also changes the channel, so tone accuracy alone does not justify
  promotion. It remains isolated, not applied to the source tree.
- Rounding the line helper's scaled PCM rather than truncating also stays at
  **54666**. One captured metric reaches **18059**, but it does not lead to
  an observed index-15 MP/completed handoff. This experiment remains isolated.
- AT requests involving `&U0`, `&N38`, `&N39`, and a fixed-rate-clamp command
  are rejected with **ERROR before dialing** in these probe contexts. They
  are not failed 56000 channel measurements or evidence of a hard rate cap.

No threshold, gain, firmware field, rate report or received payload was
patched to manufacture 56000. The remaining work is to identify why the
remaining reconstructed channel/receiver metric does not sustain the index-15
threshold, not to reinterpret the CONNECT label as measured bit rate.

Provenance: `../v90modem/artifacts/x2-56000-20261031/`; `valid/baseline`,
`interpolation`, `long`, `wide`, `round`, and `request` preserve the distinct
outcomes. Numerical probes are `measure_adc.py`. The read-only observer is
`../v90modem/tools/probe_x2_host_courier.py --capture-rate`; unlike the payload
capture mode, it installs a native 64-hit ring at initialization and drains
it at close, without a per-service Python execution hook.
