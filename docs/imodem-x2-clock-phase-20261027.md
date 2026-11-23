# x2 clock-phase and interrupt-source controls — 2026-10-27

## Scope

Follow-up to [first non-idle full-bank capture](imodem-x2-first-full-bank-20261027.md).
The objective is to distinguish steady clock drift, transport discontinuity,
and CPU interrupt servicing before the first damaged downstream record.

**Production defaults have not changed.** The new code is passive, opt-in
telemetry. The existing `COURIER_ROM_XF_INT0=1` experiment changes both the
frame interrupt source and polling from 1024 to 64 instructions, and disables
the native worker-poll fast path. Its successes must not be attributed to the
source alone without the separate controls.
No firmware, oscillator/CPI ratio, bank capacity, idle token, payload check,
or traffic acceptance criterion was changed.

## Configurable periodic cadence follow-up

[Frame cadence controls](frame-cadence.md) now provide an opt-in live
codec-derived periodic interval, configurable samples per frame, fractional
phase, and explicit fixed-rate overrides in both Python and the native worker.
The original 1024-instruction polling and native-worker eligibility remain
unchanged. Initial adaptive-periodic x2 gates fail, so the feature is **not**
the default and is not a substitute for the successful actual-XF experiment.

## New observations

With `--analog-trace-link-errors`, `rom_link_errors.clock_timeline` contains up
to 8192 non-draining snapshots. Each snapshot records CPU instructions, DSP
instructions/cycles, XF falling edges, codec primary frames/period, raw PCM
samples queued/consumed/pending, codec output samples, CPU interrupt entry
counts, observed EOIs, PA6, CPU PC/flags, and a reset epoch. The one-time input
cushion is included in queued samples. The raw PCM accounting invariant is:

```
line_input_queued - line_input_consumed == line_input_pending
```

Snapshots are made at observed INT0 entries, at most once per 60000 CPU
instructions (about 18 ms on this board), except on a DSP reset/replacement.
A reset-generation counter separates epochs even if a reset occurs before
the next sparse snapshot or before any DSP cycle has elapsed. There is no
new clock, callback, queue, retry, or execution advance. The diagnostic ring
is independent of the much shorter first-full-bank event ring. The first
pending-error event additionally retains its most recent 256 clock snapshots.

These are simultaneous **observations**, not a reconstruction of physical
ASIC time. CPU device time and DSP catch-up work can be offset within a service
chunk. EOI observations are not precise EOI writes. Counts include boot and
training; compare deltas within a steady-state epoch, not absolute totals.

Read-only analysis:

```sh
PYTHONPATH=. .venv/bin/python tools/analyze_clock_trajectory.py \
  artifacts/imodem-x2-clock-trajectory20-repeat-20261027-154842/analog-result.json \
  --start-cpu 140000000 --before-first-error
```

The analyzer refuses counter rewinds within a segment and inconsistent raw
PCM accounting, and never computes deltas across reset epochs or codec
period changes. `--start-cpu` selects steady operation; a codec period alone
does not imply the modem has completed training.

## Default-source failure: neither accumulated cycle drift nor PCM loss

`artifacts/imodem-x2-clock-trajectory20-repeat-20261027-154842` is a fresh
unchanged 20-second wall-clock call, CONNECT 53333/x2, traffic FAIL. First
pending rejection: analog CPU instruction 178465791, line frame 2547.
Analog BLER 63 in the final diagnostic snapshot.

The 633 snapshots from CPU 140055551 through 178438143, before that error,
show:

| Measurement | Result |
|---|---:|
| DSP cycles per CPU instruction | 11.8599999708 (configured 11.86) |
| Relative cycle-debt range | -2 to +88.56 DSP cycles |
| XF falling edges per DSP second | 3199.9667 |
| CPU frame IRQ entries per DSP second | 2391.8263 |
| Raw line samples consumed per DSP second | 8000.0053 |
| Raw line FIFO range | 47–217 samples |

There is no progressive CPU/DSP cycle debt or raw PCM FIFO growth before
this rejection. The DSP's steady XF cadence and the synthetic CPU interrupt
cadence differ substantially. In the successful V.34 control, the codec
period is 5600 DSP cycles (7200 Hz) and XF/CPU frame service both run at
2400.00069/s. In x2, the codec period is 4200 cycles (9600 Hz) and XF runs at
3200/s, while the default synthetic IRQ cadence stays near 2400/s. This
links the discrepancy to the codec/frame cadence rather than accumulated
CPU/DSP oscillator debt. That observation is not, by itself, proof of the
physical board's undocumented interrupt wiring.

A second fresh default-source 20-second call,
`imodem-x2-clock-trajectory20-20261027-154751`, also failed (CONNECT 49333,
final analog BLER 52), with the same qualitative phase/cadence relationship.

Removing wall-clock pacing alone also failed:
`imodem-x2-clock-isolation-offline60-20261027-154040`, CONNECT 53333/x2,
7 complete downstream records, first analog error CPU 178449407/frame 2546,
final analog BLER 340. Wall-clock removal is not a cure for the default source.

### Exact downstream transport comparison

The archived `verify_downstream_transport.py` under the offline 60-second
XF artifact compares decoded/scaled `imodem-tx.g711` with `analog-rx.wav`.
It uses **one constant sample offset**, not an aligning resampler. It finds
one 2048-sample anchor, then checks every overlapping sample after the initial
2 seconds of DS0. Gain is taken from the saved bridge status.

For the failed default-source repeat, the fixed offset is 200399 samples.
All 271601 samples checked through the traffic-health boundary match exactly.
The 8674 mismatches in the *complete* final-file overlap start much later,
at source sample 331281, after the measured window (which ends by source
sample 287601). Those final-file mismatches are retained in the report, not
silently discarded. Thus there is no transport sample insertion/deletion or
waveform corruption in the checked prefix leading through the failed window.

This tests the DS0-to-analog-line transport, not every internal ADC/filter or
undocumented ASIC rule. The PCM accounting separately observes the ADC queue.

## Existing XF experiment: sustained downstream success

All calls below use original ROM, original six banks, S39=8, original 512-byte
records/checks/gap/trailing-silence rules. The experiment is the existing
`COURIER_ROM_XF_INT0=1` source/polling switch, not a new functional patch.

| Artifact | Mode | Gate | Down/up complete records | Analog/upstream BLER |
|---|---|---|---:|---:|
| `imodem-x2-clock-xf-control20-20261027-155041` | wall-clock 20 s | FAIL (long gaps) | 93 / 15 | 0 / 0 |
| `imodem-x2-clock-xf-offline20-20261027-155301` | offline 20 s | PASS | 137 / 27 | 0 / 1 |
| `imodem-x2-clock-xf-offline60-20261027-180406` | offline 60 s | PASS | 470 / 84 | 0 / 0 |
| `imodem-x2-clock-xf-wallclock60-20261027-181000` | wall-clock 60 s | PASS | 389 / 71 | 0 / 0 |
| `imodem-x2-clock-controls-20261027-181500/x2-xf64-wallclock60-repeat` | wall-clock 60 s | PASS | 392 / 71 | 1 post-window / 0 |

The first four calls negotiated analog CONNECT 52000/x2; the final repeat
negotiated **CONNECT 53333/x2**. This is a passed 60-second 53333 traffic gate,
not repeatable full-rate qualification or a default-source fix. All five had
no qualifying non-idle full-bank capture. The 20-second offline run's result was recovered after the tool
invocation timed out; its supervisor exit status was not recorded and is not
inferred from the traffic gate. The bounded 60-second supervisors recorded
exit 0, with no timeout.

In the offline 60-second pass, steady DSP XF edges and CPU INT0 entries both
run at 3200.00096/s; line consumption is 8000.00240/s. Raw input FIFO occupancy
stays within 52–214 samples. The full checked transport overlap has **zero
mismatches in 626961 samples** at the same fixed 200399-sample offset. There
are 575601 exact matching samples through traffic health.

The wall-clock 60-second pass has maximum completed-record gaps of 40 and
34 100-ms ticks, and both directions receive at tick 599. Its traffic-health
native peak wall-clock lag is 412180571 DSP cycles (~10.22 s). A large owed
wall target therefore does not, alone, establish corruption or a failed gate.
The earlier wall-clock 20-second experiment had 74-/93-tick gaps and failed;
XF mode is not yet repeatably qualified simply because these 60-second calls
passed. The fresh wall-clock repeat also passes with 40-/34-tick maximum
gaps, last receives at ticks 598/597. Its one analog rejection is post-window:
line frame 5263 versus traffic-health line frame 4999. There were no reported
measured-window rejections in either direction.

The wall-clock captures have extra idle codewords during training/diagnostics,
so a single raw-DSP-to-line offset does **not** match their entire files.
Those mismatches are retained in their transport verification JSON. For the
first wall-clock 60-second pass, the last mismatch through traffic health is
source sample 36400, well before the measured traffic begins. A conservative
window starting one 100-ms tick before the earliest endpoint's recorded start
matches exactly: **486400 samples, zero mismatches**. The 53333 repeat likewise
matches **485440 samples, zero mismatches** across its conservative measured
window. Do not confuse pre-CONNECT idle insertions or post-window clear-down
with a measured-window transport discontinuity.

## Source, polling, and native-worker controls

`artifacts/imodem-x2-clock-controls-20261027-181500/supervise.py` runs sequential,
bounded controls, saving commands/environments/results and heartbeat:

1. Offline x2, periodic source, 64-instruction polling (isolate polling).
2. Offline x2, XF source, default 1024-instruction polling (isolate source).
3. Unchanged fixed-14400 V.34 wall-clock gate with the XF experiment.
4. Repeat unchanged x2 wall-clock 60-second gate with the XF experiment.

The two source/polling controls use archived diagnostic-only `sitecustomize.py`
modules to set the existing timer/service constants in both processes. They
must not be mistaken for unchanged-default controls. No source-tree timing
constants were edited to perform them. Both exited 1 with NO CARRIER rather
than CONNECT (periodic64 in 218.66 s, XF1024 in 246.94 s); neither provides a
steady-state connected comparison. A failed handshake is not evidence that
the connected-output fault has been isolated.

The V.34 XF64 gate **passes**, CONNECT 14400/V34/LAPM, 46 downstream/28 upstream
records, maximum completed-record gaps 5/8 ticks, and last receives at ticks
197/199. Its final 16 analog BLERs and non-idle full-bank capture occur after
the window: first rejection line frame 4267 versus traffic-health line frame
3999. There are no reported measured-window rejections. This is not a claim
that all final diagnostic counters are clean.

An additional independent control,
`imodem-x2-periodic-no-native-worker20-20261027-182500`, disables only the native
worker while retaining default periodic IRQs and 1024-instruction polling,
without wall-clock pacing. It CONNECTs at 53333/x2 and **fails**, 7 downstream
records, last at tick 113, final analog BLER 67, qualifying non-idle full-bank
capture. Thus simply disabling the native fast worker does not fix the fault.
Its pre-error clock samples still show 3200.08 XF edges versus 2390.17 CPU
frame IRQs per DSP second, flat CPU/DSP cycle debt, and bounded PCM occupancy.

`imodem-x2-periodic64-no-native-worker20-20261027-183000` adds a finer-polling,
native-worker-disabled periodic-source control, making the source-only
comparison to the successful XF64 mode explicit. Its archived supervisor
waits until the wall-clock repeat finishes to avoid adding probe load there.
It also exits 1 with NO CARRIER (214.89 s), so it does not supply the desired
connected source-only comparison. None of these no-CONNECT pilots should be
counted as measured-window corruption or as qualification of a source change.

A separate cadence-only pilot,
`imodem-x2-connected-cadence-control20-20261027-183500`, was explicitly
**invalidated and stopped**: its archived hook looks for `/x2/` at the initial
online-mode transition, which happens at the word `CONNECT`, before the suffix
exists. Therefore the intended cadence adjustment cannot run. Its validation
JSON records the exclusion; do not use this pilot as evidence for or against
an adaptive periodic-cadence correction.

The demonstrated mitigation is the existing XF64 mode with S39=8. Its two
fresh wall-clock 60-second passes (one at 53333) and V.34 measured-window pass
are a substantial improvement over the default-source failures. Production
source/polling defaults remain unchanged: isolate the remaining source/latency
coupling before promoting a timing change, and repeat full-rate qualification
before claiming universal x2 reliability.

## Subsequent controls and native-execution caveat

[Coupled-clock and finer-recognition controls](imodem-x2-coupled-clocks-20261027.md)
retain later failed repetitions as well as a fresh passing 52000/60-second
call. They do not support promoting the XF profile as universally reliable.

The later ROM-backed result now exposes actual `native_worker_polls`. The
current bridge's audio-only/non-codec-direct eligibility guard prevents the
native fast worker from taking these services; a completed control requesting
native XF explicitly reported zero native polls. Historical labels such as
"no-native-worker" describe requested settings, not verified native execution
in the comparison arm. Those controls therefore cannot establish a native
versus Python causal difference. Preserve their training/corruption results,
but do not treat the requested selector as proof that execution changed.
