# x2: coupled virtual clocks and independent IRQ recognition controls

## Status

This adds useful opt-in controls, **not a repeatable full-rate x2 fix**.
Legacy periodic frame routing and independent wall-clock operation remain the
probe defaults. Firmware, six data banks, CPU/DSP clock ratios, traffic records,
and acceptance thresholds are unchanged.

## The two clock topologies

The existing live I-modem path independently advances PIT/RTOS peripheral time
against wall time and gives the DSP a bounded wall target. CPU pacing is a
third participant. Under host scheduling delays those domains can separate:
`imodem-qualified-xf-profile-20261027/x2-60` ended with PIT time 117.3976396 s
and executed DSP time 106.5625566 s. This is a measured discrepancy, not proof
that it causes every x2 error.

The pair probe now accepts:

```sh
# Append to the original call/traffic command; keep its other settings.
--wallclock --clock-mode coupled --analog-frame-source dsp-xf
```

For a **virtual, backpressured pair**, coupled mode derives CPU, DSP, PIT/RTOS,
and stopped-highway fallback progress from executed instruction time. It still
wall-paces the CPU in Python and in native polling, including turns where
native device elision is unavailable. A delayed host therefore pauses the
virtual machine together, rather than advancing protocol timers ahead of
unexecuted modem work. Existing instruction/DSP debt and PCM are retained;
there is no invented FIFO, replay of old IRQs, or suppression of idle samples.

`BearerLineLink(..., instruction_clocked=True)` is the capability that selects
this topology; its API default is false. Real SIP/external-clock peers retain
the old independent live clock. `--clock-mode independent` explicitly selects
the old pair topology. Without `--wallclock`, either mode remains unpaced.

Coupled virtual timing is **not a guarantee of real-time external DS0 service**:
if the host cannot execute the emulation quickly enough, guest time runs slower
than wall time. Payload/continuity qualification and host real-time performance
are separate claims.

## Frame routing and recognition

`--analog-frame-source dsp-xf` selects actual falling edges, not a CONNECT-rate
table. The per-machine XF profile defaults to cooperative service and 64
instructions between ordinary IRQ checks. It no longer changes a module-wide
poll constant. Fixed `--analog-frame-hz` still overrides XF routing.

Two independent controls permit valid scheduling comparisons:

- `--analog-interrupt-poll-instructions N`: ordinary timer/UART polling.
- `--analog-frame-irq-poll-instructions N`: XF recognition interval (default 64).

Their CLI/worker/API equivalents omit `analog-`. A smaller XF interval does
not fabricate more DSP edges or change the general IRQ interval. IF,
in-service/EOI, vector/stack feasibility, one pending/coalesced request, and
DSP reset generations still govern delivery. Smaller intervals can be costly.

Native worker XF dispatch is implemented and unit-tested, including entry
between ordinary timer polls and actual EOI observations. Explicit
`COURIER_WORKER_POLL=1` requests it, but does **not** prove it ran. Results now
expose `dsp_bridge.line.native_worker_polls` for ROM-backed audio too. The
current bridge's audio-only/non-codec-direct guard prevents native fast-clock
eligibility on these calls; the 16-instruction control's completed V.34 call
reported **zero native worker polls**. Artifact names containing `native` are
requested configurations, not evidence of native execution. Those controls
must not be used to infer a native-versus-Python causal difference.

## Retained controls

Artifacts preserve command, relevant environment, logs, heartbeat, and bounded
supervisor status. Never rerun a supervisor in place over retained results.
All counts below are complete records; gaps use the unchanged 100-ms traffic
frame units. Final error counts must be checked against event timestamps when
classifying measured-window versus clear-down errors.

### Independent clocks, cooperative XF/64

`artifacts/imodem-qualified-xf-profile-20261027/` is an **attempted**
qualification, despite its directory name:

| Call | Gate | CONNECT | Down/up records | Largest down/up gaps |
|---|---|---:|---:|---:|
| x2-20 | PASS | 52000 | see result | within limits |
| x2-60 | FAIL | 53333 | 357 / 66 | 59 / 35 |
| x2-60-repeat | FAIL | 52000 | 163 / 33 | 209 / 206 |
| v34-20 | incomplete within bound | — | — | — |

The first 60-second call had zero endpoint errors and no qualifying exhaustion
trigger, yet failed the maximum-gap gate. Its measured downstream PCM matched
exactly at one fixed offset; a pause must not simply be called transport loss.

### Coupled clocks, cooperative XF/64

`artifacts/imodem-coupled-xf-20261027/`:

| Call | Gate | CONNECT | Down/up records | Largest down/up gaps |
|---|---|---:|---:|---:|
| x2-20 | PASS | 52000 | 116 / 23 | 39 / 34 |
| x2-60 | PASS | 52000 | 471 / 84 | 13 / 16 |
| x2-60-repeat | FAIL | 52000 | 431 / 82 | 59 / 32 |
| v34-20 | PASS | 14400 | see result | within limits |

The passing x2 calls had zero endpoint errors and no qualifying exhaustion
trigger. The failed repeat still received through ticks 599/596, but exceeded
the gap threshold and recorded one analogue BLER during the window (first
pending error at line frame 4193, health end at 4961), plus a qualifying
full-bank observation. That observation is not itself a byte-loss count.

PIT minus executed DSP time remained approximately 0.148621 s across the x2
calls, the initial CPU/DSP epoch offset rather than accumulating relative
clock debt. This demonstrates coherent accounting, **not complete reliability**.

The unchanged fixed-offset transport checker found **zero mismatches** across
all compared x2 downstream samples: 627761 samples in the passing 60-second
call, including 482560 in its measured window, and 628561 in the failed repeat,
including 483360 in its window. Offset was 200399 samples, with no realignment.
The V.34 checker attempt had an invalid anchor and zero measured-window
coverage; its transport comparison is explicitly excluded, not called a pass.

### Rejected timer-only clamp

`artifacts/imodem-coherent-native-xf-20261027/` retains a candidate that capped
PIT/RTOS time at executed DSP time while CPU execution remained independent.
The coarse x2 control timed out; the finer control failed trailing continuity
(last receive ticks 506/517 despite zero endpoint errors), while V.34 passed.
**The clamp was reverted.** Source snapshots and disabled candidate tests are
archived under `rejected-clock/`; they are not production code or current tests.

### Finer recognition controls

`artifacts/imodem-coupled-native-xf16-20261027/` requested native XF/16 with
coupled clocks and ordinary polling still 64. Both x2 calls exceeded the
220-second host bound before completing; they are **not completed 60-second
qualification calls**. V.34 passed, but reported zero native worker polls.
The tighter cooperative callback interval was expensive; no native performance
or reliability conclusion follows from this selector.

`artifacts/imodem-coupled-xf32-20261027/` completed cooperative XF/32 controls:

| Call | Gate | CONNECT | Down/up records | Largest down/up gaps |
|---|---|---:|---:|---:|
| x2-60 | PASS | 52000 | 448 / 85 | 40 / 13 |
| x2-60-repeat | FAIL | 52000 | 429 / 82 | 59 / 33 |
| v34-20 | PASS | 14400 | 46 / 28 | 5 / 8 |

The passing x2 call had one upstream rejection. The failed repeat had zero
endpoint errors and no qualifying exhaustion trigger, yet the same 59-tick
recovery pause. Receiving continued through ticks 599/595. Finer recognition
is not by itself a repeatable correction.

`artifacts/imodem-coupled-xf16-full-20261027/` allowed 420 host seconds to
complete the expensive cooperative XF/16 pilot. Its first 60-second call
completed and failed: 429/83 records, last ticks 599/597, gaps 59/33, zero
endpoint errors and no qualifying exhaustion trigger. Remaining follow-ups
were then cancelled; the partial repeat is excluded and the 20-second job
was not run. This is further evidence against attributing the recovery pause
solely to the 64-instruction recognition bound. No defaults were promoted.

## Validation and remaining work

Focused validation covers virtual/external clock separation, CPU pacing even
without native elision, no host-delay-generated PCM in coupled mode, ordinary
idle generation with guest progress, 100-Hz PIT guest time, per-machine polling,
CLI forwarding, actual XF opcodes, coalescing, reset epochs, IF/EOI, and native
interrupt stack layout. See `tests/test_virtual_pair_clock.py`,
`tests/test_frame_source_profile.py`, and `tests/test_native_xf_frame_irq.py`.

Final focused validation: **191 tests passed in 13.34 seconds**;
`git diff --check` was clean. This was not a full-suite run. No probes remain
running; completed, timed-out, and intentionally stopped controls are retained.

The remaining tasks are to identify the recovery pause and occasional output
failure without confusing clock coherence, configured routing, actual native
execution, and physical ASIC wiring. In particular, the same pause survived
coherent clocks and 64/32/16 recognition, including runs without endpoint errors
or a qualifying full-bank trigger. The control/flow path around that pause is a
more useful next isolation point than another frequency-only change. No new
default should be promoted from a single passing 60-second call, and the new
topology has not yet demonstrated repeatable 53333 qualification.
