# I-modem live timing correction and completed V.90 holds

**Later UART correction:** [clean holds and repeated ATI6 output](imodem-v90-uart-starvation-fix-20261025.md)
now completes both 60-second holds plus ten ATI6 queries per call with zero
full-session TX rebuffers or RX loss. The results and remaining-output limit
below describe the earlier 18:35 build, not the latest qualification.

Follow-up to [the instrumented failure analysis](imodem-v90-failure-analysis-20261025.md).
The identified IRQ13 watchdog failure now has a scheduler correction, not just
an identified firmware branch. The watchdog itself and the modem firmware
remain unchanged. Live native polling remains **opt-in**.

## Defects and corrections

### 1. Native DSP target used the wrong clock rate

Python's I-modem digital PCM target runs at **40.32 MHz**, but native live-poll
extrapolation used a hardcoded **20.16 MHz**. Native execution consequently
fell behind between Python anchor refreshes, which jumped the target forward.

`native/c5x_capi.cpp` now derives the rate from the configured DSP/CPU ratio
and supervisor instruction rate. It retains the wall target and does not
throw away DSP cycles or network octets. A regression starts a core at
30 million cycles against a one-second wall anchor: the correct clock owes
cycles, whereas the former half-rate calculation incorrectly considers it
ahead.

**Fixing that constant alone was insufficient.** Two intermediate tests
connected, but probes still caught watchdog writes during ATI6 output.
Those tests are retained rather than counted as proof of a watchdog fix.

### 2. CPU pacing depended on whether polls could be elided

Serial output and dirty devices force Python service. Previously they also
bypassed the native supervisor pacing gate. An old absolute pacing anchor
could additionally bank a large instruction deficit during host delays and
then permit a supervisor sprint.

The timing probe caught approximately 50 mailbox service entries in a
10-ms interval, at roughly twice the normal supervisor retirement rate,
while the PIT remained wall-clock paced. That trips the firmware's
50-entry watchdog. The failure is not explained by dirty RTP alone.

CPU pacing now applies to **both native and fallback service**, independently
of poll elision. If CPU pacing falls more than one millisecond behind, its
anchor rebases rather than banking an unlimited catch-up sprint. Ahead-of-time
CPU execution sleeps in bounded, at-most-one-millisecond windows. This changes
only the CPU pacing anchor: the DSP target, PCM queues, timer expiries, PIC
priority, and firmware watchdog are not reset or suppressed.

### 3. An independent DSP needs a scheduler-turn allowance

Once CPU pacing was corrected, strict DSP advancement proportional to retired
CPU work could starve outgoing audio when host execution slowed down. One
intermediate 6312 call had clean RX, no watchdog abort, a 217-ms TX gap, and
then an incoming PBX BYE. It reached modulation completion and entered the
error-control path, but never CONNECT. This was distinct from the original
watchdog failure.

A **genuine scheduler turn** in paced live mode may now recover up to **one
DS0 frame (5,040 DSP cycles)**. Port-driven cycles already spent since the
previous turn count against the extra allowance. Repeating service at the
same instruction count grants nothing extra. The absolute wall target remains
an upper bound.

Individual port accesses retain their retired-instruction budget and the
existing holding-word read protections. A zero-quantum **port write is not a
scheduler turn**: the distinction is explicit in `_advance_dsp`, the Python
native wrapper, and the separate `courier_imodemio_advance_turn_serve` entry
point. Neither increasing the allowance on every port read nor removing the
firmware's interrupt watchdog is part of this fix.

### 4. Shared absolute stamps must use the same clock domain

A regression also exposed a macOS-specific defect: Python's
`time.monotonic_ns()` uses `CLOCK_UPTIME_RAW` there, whereas the C++ helper uses
`clock_gettime(CLOCK_MONOTONIC)`. Their absolute epochs differ. Linux does not
have this particular mismatch, so it is not the explanation for the Linux
failure.

`poll_state.native_monotonic_ns()` explicitly uses `CLOCK_MONOTONIC` for
shared polling and CPU-pacing anchors on both sides. Ordinary elapsed-time
measurements remain separate. No `PollState` layout change was required by
this follow-up.

## Hardware evidence: exact final build

Both calls used the same full-rate saved profile, 200-ms receive/transmit
reserves, account 2903, and `COURIER_LIVE_POLL_ELISION=1` in CT 127. The tested
library is `/root/courier-emu/.build/libcourier_c5x-live-final.so`, built with
Clang 19 from the updated sources. Use matching updated Python sources.

| Destination | CONNECT | Completed host-wall hold | Sample-counted hold | ATI6 rates |
|---|---|---:|---:|---|
| 6312 | 49333/ARQ/V90/LAPM | 60.000220 s | 60.000250 s | 12000/49333 |
| 6313 | 48000/ARQ/V90/LAPM | 60.000558 s | 60.000625 s | 14400/48000 |

For **both calls, through the entire hold**:

- readable MULTITECH login banner;
- zero missing RX playout samples, sequence gaps, timestamp jumps or late packets;
- **zero TX rebuffers**, maximum TX packet gap 24.73/25.58 ms respectively;
- no observed IRQ13 watchdog write;
- ATI6 subsequently reports Online/LAPM and zero block resends, retrains,
  BLERs, link timeouts or NAKs;
- zero native torn data words or busy-bank writes in the final reports.

The instrumented final 6313 call has maximum IRQ-entry counts of **25** in
snapshots at CONNECT, hold completion and escape completion, and **30** in
the ATI6 snapshot; the watchdog threshold is 50. These are bounded ring-buffer
snapshots, not a claim to have stored every IRQ from the full call. Passive
abort probes cover the entire call and record no watchdog hit.

Before the exact final API cleanup, the frame-allowance candidate also made
three consecutive connections: a five-second 50666/V90 hold and 60-second
49333/V90 holds on both ports. Thus the final two holds are supported by
candidate repeats, but do not represent a controlled long-run success-rate
study. An earlier distinct XID timeout is not retroactively proven to share
the watchdog cause merely because it did not recur in these repeats.

## Qualification boundary of the earlier build

**ATI6 output after each final hold still causes one TX rebuffer**: maximum
full-session gaps are 188.42 ms (6312) and 215.93 ms (6313). Observer media
snapshots prove these begin only after sending ATI6, not during training,
the 60-second hold, or the guarded escape. Both calls remain Online and are
ended deliberately with ATH. This diagnostic-output starvation is a remaining
limitation, not a clean full-session timing result and not something to hide
inside a passing hold.

These tests submit no login credentials or application test payload. ATI6
counts only 51 received octets. They demonstrate modulation/LAPM startup and
stable idle/banner holds, **not sustained binary throughput**. ATI6's displayed
31-second duration remains the previously verified firmware half-scale
accounting; it is not the actual duration of these holds.

## Regression and archived evidence

**96 targeted regressions pass**, including digital clock extrapolation,
CPU pacing with elision disabled, fallback pacing/rebasing, scheduler-turn
allowance accounting, repeated-turn protection, holding-word reads in paced
and ordinary modes, receive-before-DSP ordering, native ports/PICs, media
playout, pair keepalive, DTE handoff, and firmware accounting.

Private evidence under `.artifact-archives/`:

- `imodem-v90-irq-timing-20261025-175703/`: pre-fix IRQ timing ring.
- `imodem-v90-live4032-{trace,hold}-20261025-180143/`: clock-rate-only tests;
  connected, but watchdog still fires during diagnostics.
- `imodem-v90-paced-{trace,hold6312,hold6313}-20261025-181135/`: CPU pacing
  correction; clean watchdog trace, plus the independent TX-starvation failure.
- `imodem-v90-frame-{trace,hold6312,hold6313}-20261025-182404/`: candidate
  frame-allowance successes. The enclosing local batch command timed out
  during the third call, but its bounded remote observer completed normally;
  that call's packet capture is partial, so use its report/audio/observer for
  completed-hold evidence rather than asserting a full capture.
- `imodem-v90-final-{6312,6313}-20261025-183529/`: exact final build, complete
  bounded captures, observer media snapshots, transcripts and recordings.
- `imodem-v90-final-verification-20261025/verification.json`: asserted hold
  checks, sample counts, counters, source/report/library hashes. The remote
  `poll_state.py` differs from local only by a blank line; its AST is identical.

The account/destination idle checks ran before each call. No PBX, ATA or
answering-modem settings were changed. All calls and scoped captures have
ended; sibling calls were left alone.
