# First non-idle output-bank exhaustion, 2026-10-27

## Result: better localization, not an x2 timing fix

The observer now freezes a native execution-order timeline at the first
**non-FF00 output attempt with all six receive banks occupied**, rather than
waiting for a later CPU CRC rejection. A repeat 20-second x2 call and a
60-second x2 call both reproduce this condition. Replaying their captured
status transitions, output holding words, CPU byte reads and acknowledgments
finds **no internal handshake mismatch** in either bounded snapshot.

This narrows the [previous IRQ/lane investigation](imodem-x2-irq-lanes-20261027.md):
CPU service really is late relative to DSP publication in the modeled run;
the captured CPU reads are not simply ignoring a bank that the model says is
free or reading a different word from the one published. It does **not** prove
that the undocumented ASIC's interrupt, acknowledgment or latching rules are
modeled correctly. No scheduling or handshake behavior has been changed.

One 20-second call passes at 52000; its repeat fails at 48000, and the 60-second
52000 call fails. **Repeatable sustained x2 and the 53333 qualification remain
open.** Firmware, S39=8, finite bank capacity, clock ratios, default polling,
payloads and traffic gates are unchanged.

## What was added

- `native/c5x_core.h`, `native/c5x_core.cpp`: an optional shared diagnostic
  recorder for DSP PA6/data-bank bus accesses. DSP/CPU execution and the
  existing bus-event histories are unchanged. The recorder is data-only and
  shared-owned; closing either processor cannot leave a callback into freed
  host memory.
- `native/c5x_capi.cpp`, `courier_emu/dsp.py`: a second, bounded combined
  timeline, separate from the legacy 2048-row recent ring and full lane
  capture. It retains up to 2048 events through the trigger and 256 afterward.
  Reads do not drain it. The rolling context continues after the frozen
  snapshot fills; later full reads never replace the first trigger.
- `courier_emu/machine.py`, `courier_emu/rom_link_errors.py`: arm at CONNECT
  only under `--analog-trace-link-errors`. Verify the original DSP output
  routine while the core is live. Cache the verification before final result
  construction, which happens after the DSP closes. Reset/rebuild/re-arm
  starts a new diagnostic epoch; old signature verification cannot certify
  another epoch.
- `tools/analyze_output_exhaustion.py`: read-only replay of receive-bank free
  bits, status polarity, holding words, byte halves and CPU ACK gaps. It
  reports sampled inconsistencies, never repairs a guest frame or changes
  traffic qualification. Signature/epoch and ordering checks fail closed.

The final snapshot is at `rom_link_errors.output_exhaustion` in
`analog-result.json`, and under `analog.rom_link_errors` in `result.json`.
Early rejection snapshots also include the capture available at that instant;
the final report can have more post-trigger events than an early snapshot.

### Trigger qualification

Arming at CONNECT alone is insufficient. The unfiltered pilot captured six
idle **FF00** publications, then a full PA6 read in the common LAMM helper.
That is not evidence that a data octet was lost.

The retained 403 trigger requires:

1. Original `8320..832B` output-path signature verified at CONNECT.
2. Full PA6 read (`value & 3F00 == 0`) in helper **80E8**.
3. DSP stack return **8327**: the delayed CALL at 8323, after its two delay
   slots, rather than an input/mailbox caller of the same helper.
4. Pending output cell **0320 != FF00**. This excludes idle flag tokens,
   not all possible control tokens. For example, FE00 can still qualify.

A kind-11 row retains the pending word immediately before the trigger. The
explicit `trigger_index` identifies the qualifying read; earlier full reads
in the preceding context need not qualify. `full_status_reads` counts all full
PA6 reads after arming, including idle/input reads, not lost octets.

New combined event kinds are 8 = DSP read, 9 = DSP write, 10 = CPU status read,
11 = filtered DSP data-cell observation. Kinds 1..7 retain their previous
meaning. Legacy recent/capture event streams are unchanged.

**Do not interpolate CPU time onto DSP rows.** Their CPU timestamp is zero
(unknown). Native execution order is exact, but a DSP catch-up batch can
represent earlier elapsed CPU work. Adjacent CPU observations are not physical
time bounds. EOI kinds 5/7 remain observations, not exact EOI write times.

## Fresh calls

All traffic uses 512-byte ASCII payloads. Counts are upstream/downstream
complete records **inside the requested window**, not final-drain counts.
The x2 ceiling is the unchanged &N36, not an assertion of negotiated 53333.

| Artifact suffix, 20261027 | Window | Initial analog CONNECT | U / D | D largest gap including trailing silence | Final analog BLER | Gate |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| `first-data-full-150619` | 20 s | 52000/x2 | 13 / 12 | 1.6 s | 0 | PASS |
| `first-data-full-repeat-150822` | 20 s | 48000/x2 | 11 / 8 | 8.2 s | 40 | FAIL |
| `first-data-full-60s-150912` | 60 s | 52000/x2 | 41 / 8 | 48.1 s | 260 | FAIL |
| `v34-first-data-full-regression-151044` | 20 s | 14400/V34 | 13 / 12 | 1.7 s | 3, post-window | PASS |

The first three directory names have prefix `imodem-x2-`; the last has prefix
`imodem-`. The passing x2 call has no qualifying output-exhaustion snapshot,
despite 1525 total full PA6 reads. This is correlation in bounded calls, not a
claim that no snapshot guarantees reliability. The repeat also retains **one
upstream traffic rejection/BLER**; S39=8 is not universally upstream-error-free.

The V.34 control uses the previous fixed-14400, &K0 settings and passes the
unchanged traffic gate. Its first analog rejection is at line frame **4349**,
after the saved traffic-health boundary at line frame **4078**. Post-window
ATI6 prints BLER 0; final memory BLER is 3. Its late FE00 trigger and final
counter must not be attributed to the measured traffic window or silently
reported as a universally zero-BLER call.

### First blocked non-idle words

- **Repeat20:** at DSP instruction **1046602345**, cycle **1206374344**, PA6
  is **0003**, pending output word **00CE**. The next qualifying attempt has
  **0020**, also with PA6=0003. The next CPU frame ISR reads status FF and
  then drains/ACKs all six banks. Last-ACK to next-ACK gap across the trigger:
  **5120 CPU instructions**, about **1.51 ms** at the identified timebase.
- **60 seconds:** DSP instruction **1414707902**, cycle **1683369604**, PA6
  **001C**, pending word **00A0**; the next attempt has **0050**. The next
  frame ISR drains all six banks. The ACK gap is **2023 instructions**, about
  **0.595 ms**. Three immediately preceding publications include two FF00
  tokens and 0001, so idle/boundary traffic consumes the same finite slots as
  data. It must not be dropped or acknowledged by the observer to make room.

Both replays have zero sampled free-bit/status discrepancies, zero changing
holding-word/byte-half discrepancies and zero writes into a known occupied
output bank. They retain intervening IRQ/EOI observations. The original
8320..8334 path returns without publishing when the selected free bit is clear;
the snapshots preserve pending words at that decision, not repaired data.
These new first-trigger snapshots alone do not independently establish valid
pre-HDLC FCS for each blocked word; the earlier valid-input boundary remains
separate evidence.

## Replay and tests

```sh
PYTHONPATH=. .venv/bin/python tools/analyze_output_exhaustion.py \
  artifacts/imodem-x2-first-data-full-repeat-20261027-150822/analog-result.json

PYTHONPATH=. .venv/bin/python tools/analyze_output_exhaustion.py \
  artifacts/imodem-x2-first-data-full-60s-20261027-150912/analog-result.json
```

Commands, environment, bounded run statuses and original outputs are retained
in each directory. No COURIER_* experimental override was set; PYTHONPATH=.
was explicit. No finer-polling, XF-source or larger-FIFO control was retained.

Focused regressions cover bounded pre/post context, opt-in/arming behavior,
idle and wrong-caller rejection, non-draining reads, unchanged legacy capture,
unchanged core execution/bus history with observation on/off, lifetime safety,
rebuild epochs, post-close reporting and offline mismatch detection.
The two failing live captures are also replayed by optional artifact tests.
**212 focused tests pass** (one combined selection, 23.37 seconds), and
`git diff --check` is clean. No full-suite pass is claimed.

Excluded pilots are retained:

- `imodem-x2-first-full-bank-20261027-145705`: missing PYTHONPATH; no call.
- `imodem-x2-first-full-bank-20261027-145730`: final diagnostic attempted to
  inspect the already-closed DSP. No valid result/gate claim. Fixed by caching
  signature verification live; a regression exercises post-close reporting.
- `imodem-x2-first-full-bank-20261027-150101`: valid unfiltered 48000/x2
  pilot, traffic FAIL, final analog BLER 48. Its first trigger is idle FF00,
  motivating the retained filter. It is not a lost-data trigger.

## Duration versus record/byte-count controls

Following the observation that a short success followed by a longer failure
could be harness-driven, two additional 60-second controls tested whether the
failure follows record count, transferred bytes, or elapsed connected time:

| Control | Initial analog CONNECT | Complete D records / bytes | Partial next record | Last complete D record after CONNECT |
| --- | --- | ---: | ---: | ---: |
| Baseline512, `first-data-full-60s-150912` | 52000/x2 | 8 / 4248 | 361 bytes | 11.9 s |
| Payload256, `duration-control-256-152721` | 52000/x2 | 16 / 4400 | 274 bytes | 11.6 s |
| Payload512, first sends held 3 s, `duration-delay3-153046` | 52000/x2 | 6 / 3186 | 227 bytes | 11.8 s |

All paths are under `artifacts/imodem-x2-` and include date `20261027-` before
the timestamp. All three gates fail, all three retain a qualifying output-bank
exhaustion snapshot, and replay finds the sampled handshake internally
consistent. Final analog BLERs in the new controls are 251 and 234; the delayed
control also has one upstream traffic rejection/BLER. No zero-error claim is
made for these calls.

The delayed control's saved `delay-control.py` wraps only
`AnalogTraffic.next_record`, withholding new DTE records for 30 100-ms ticks
after both original CONNECTs. Both directions are delayed. It does not move
the measured window start, change modem code or clocks, inject received data,
or alter acceptance. Its first complete record gap is 4.5 s, below the existing
five-second limit. Production traffic code was not changed; `command.json`
explicitly names the diagnostic wrapper, and `control.json` describes it.

This small set argues **against a fixed record-count or hard byte-capacity
cutoff**, and makes an elapsed-connected-time-dependent transition a stronger
working hypothesis: delaying source traffic reduces bytes delivered before
the stall without moving the last complete record about three seconds later.
It does not yet identify a timer or prove a universal 12-second boundary;
repeat controls and finer event/state tracing at that boundary remain needed.
The earlier passing20 call itself crossed 12 seconds and 4 KiB, so a hard
unconditional timeout is not established either.

There is also a traffic-driver amplification to distinguish from the initial
fault: `Traffic.next_record` intentionally permits one outstanding record per
direction. Baseline512 sends nine records, receives eight plus a prefix of
nine, and withholds ten waiting for nine to complete. The opposite direction
continues, the call stays active, and the saved PCM health remains clean. This
means prolonged complete-record silence alone is not proof that the emulator
stopped executing. It does **not** explain away the first incomplete record
or the captured full-bank output attempts.

## Clock-phase follow-up

The subsequent [clock-phase/source controls](imodem-x2-clock-phase-20261027.md)
find no progressive CPU/DSP cycle debt or checked transport discontinuity before
a fresh rejection, but measure approximately 3200 DSP XF edges versus 2392
synthetic CPU frame IRQ entries per second. The existing XF/finer-polling
experiment then passes fresh offline and wall-clock 60-second gates at 52000,
plus a fresh wall-clock 60-second repeat at 53333, without bank exhaustion.
The V.34 measured-window regression also passes. Source-only/polling-only
controls do not complete CONNECT and therefore do not isolate the connected
fault. Production defaults remain unchanged; repeatable full-rate qualification
and a justified hardware-model correction are still distinct from these passes.

## Remaining boundary

The captured model is internally consistent, but CPU service opportunities
still arrive after finite-bank exhaustion. Next distinguish the **actual EOI
write/interrupt-recognition boundary and CPU/DSP catch-up interleaving** from
physical ASIC interrupt/latching behavior. Do not replace the finite banks,
invent retries, discard idle tokens, modify firmware or weaken trailing-gap
criteria. Require repeatable 20-/60-second duplex success and a true 53333
qualification before calling x2 reliable.
