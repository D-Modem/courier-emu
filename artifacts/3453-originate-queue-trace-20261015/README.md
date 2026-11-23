# Originate transition: requested by firmware, dropped by its software ring

Offline, unchanged B/C firmware. No hardware access, flash writes, settings
save, forced DSP commands, callback patches, carrier or CONNECT. All published
fields are explicitly selected call diagnostics; arbitrary SI/stack/memory
contents from the temporary raw reports are excluded.

**The previously missing transition is now explained. Negotiation is not yet
working. The corrected quiet-line regression has zero setup drops; the
live peer path is now blocked by later DSP download failures.**

## Decompilation and executed branch

The expanded [line-control disassembly](../3453-line-control-decomp-20261014/line-control.asm)
contains these original supervisor routines:

* 635A1..6360D: configure originate, select command, enter call wait.
* 638AD: return the OR condition of RAM 1C06 bit 02, 0912 bit 01, 0A12 bit 01
  through ZF. These were all zero in the measured run.
* 6405B: special/extended originate commands; the zero condition skips command
  0010, taking 64066 -> 640B4. This skip is an intentional firmware choice,
  not evidence of a missing driver prerequisite.
* 640B8: fallback selection. The measured path reaches 640C2 and requests
  command 0017 with the mode word at 02C2 (5040).
* DSP dispatch table 131B maps command 0017 to **1DE4**, the original originate
  setup. Command 0014 maps to answer setup 1F64; 0015 maps to monitor setup 20E9.

The critical transport routine is 67D5F, approximately:

```c
save_flags();
disable_interrupts();
used = write_pointer_02de - read_pointer_02dc;
if (borrow) used += 0x30;
if (used > 0x2a) {
    restore_flags();
    return;                 // no command queued, no automatic retry
}
enqueue_word(0xff00);
enqueue_word(tag_ax);
enqueue_word(data_bx);
restore_flags();
```

The helper 67D33 implements individual word insertion and ring wrap. The
pseudocode above is explanatory, not replacement firmware and not a proposed
fix to the guest's bounds checks.

## Before: exact first divergence

`bc-origin-branch` executes the expected control branches. `bc-queue-drop`
then watches the queue-occupancy comparison at 67D6F, rejection at 67D89,
and command-0017 selection at 640C2.

On B, at CPU instruction 2,992,832:

* The guest reaches 640C2.
* It calls its own enqueue routine with **AX=0017, BX=5040**.
* The measured queue occupancy is **CX=002E** (46 bytes).
* The guest takes its rejection path, **67D89**.
* The native DSP never receives command 0017 and remains RX=2127, TX=1173,
  state callback 006D=0.

This disproves the earlier hypothesis that the supervisor was waiting for a
missing tone report before deciding to originate. It had already decided.
Status 0809 qualification was downstream monitoring, not the missing request.
Other setup commands were also rejected during the compressed burst.

## Emulator change and controls

`CourierMachine._clocked_3453_call()` limits the correction to a verified 3453
profile, DSP-paced ticks, a finished resident bootstrap, and an actually
asserted guest hook relay. In that state, fast-delay hooks no longer:

* write the timer byte at 0152 to manufacture completion of a timer wait;
* shorten the calibrated CX delay loop to one iteration.

It also preserves **queue-drain waits with timer deadlines** at B/C
59CC3/59CEC/59D12 (canonical C addresses 59CD9/59D02/59D28). These are the
remaining setup-drop cause, not just elapsed-time helpers:

```c
deadline = (timer_014e - 2 + 200) % 200;
while (timer_014e != deadline && read_02dc != write_02de) {
    // Original guest loop; board interrupts service the queued words.
}
```

The old hook wrote `timer_014e = deadline`, immediately taking the timeout exit
without waiting for the queue. Simply preserving the other two waits recovered
command 0017 but still lost setup words. Preserving this condition recovers all
six 0050 setup words with **zero** queue rejections in the quiet-line regression.

The original guest code and board service perform the waits. The emulator
neither enlarges the ring nor inserts/retries a missing command. Startup
acceleration remains as before: disabling every timer wait immediately after
bootstrap prevented the initial firmware setup from completing (24-million
instruction control, no AT replies), so this is deliberately a call-time fix,
not a claim of complete reset-clock fidelity.

`bc-call-queue-fixed` is an intermediate control preserving timer waits only:
B really delivers **0017:5040**, produces native transmit PCM with peak
**10471**, then returns **NO CARRIER**. A's received line peak remains zero,
so this is **not** proof of bidirectional PCM on the wire or a connection.
Eleven other B setup commands still take the rejection path.

`bc-all-delays` is a second intermediate control: timer and busy-loop waits
preserved, but queue-drain timeout shortcuts not yet corrected. This live peer
control exposes a later transport failure:

```
3453C overlay did not acknowledge at 1278, PC=1133
```

The diagnostic 1278 is the **pre-interrupt BMAR**, not a verified payload
destination. PC 1133 belongs to the resident idle/wait helper. The workers do
not produce a complete paired JSON result on this exception. No later carrier
or successful transfer is inferred. The quiet-line regression using the
current implementation independently verifies genuine delivery of command
0017 and all six 0050 setup words, with **zero** queue rejections.

`bc-drain-fixed` is the final live control, preserving all three kinds of wait:
40 million instructions and 100 requested frames. It reaches later download
failures on both sides: A reports an overlay mismatch at FFFE; B reports no
acknowledgment with pre-interrupt BMAR=124C and PC=1133. The run aborts without
a complete paired result. This is not a successful call, and the existing
transport verification was neither bypassed nor weakened. These failures need
request/transfer/reset-epoch tracing before changing the loader.

## Reproduction

Use the private, unchanged assembled B/C image as `$PRIVATE_BC_FLASH`. Baseline
commands common to the peer controls:

```
./courier link "$PRIVATE_BC_FLASH" --with-dsp --line-audio-only \
  --tick-source dsp --a-at 'AT&N1&U1' --a-at 'AT&L1' \
  --b-at 'AT&N1&U1' --b-at 'AT&L1' --summary
```

The before controls used 9/10 million instructions and 12/15 requested frames;
add `--trace-pc 0x67d6f=queue-used --trace-pc 0x67d89=queue-drop
--trace-pc 0x640c2=orig-command17`. The corrected controls used 30 million
instructions, 70 requested frames, and WAV recording under temporary paths.
Each used a distinct `--socket` path. Retain raw reports privately; the
standard PC trace can include arbitrary data at SI.

Validation: **22 tests passed**, covering call-delay gating, real firmware
originate-command delivery, zero queue rejections and all six setup words with
public captures/erased synthetic settings, line-control audit, complete tone download, independent PCM/tone controls,
codec readback, CLI link and machine map. The full 3453/map/CLI/native-machine
aggregate subsequently passed **116 tests in 389.09 seconds**.

Next: trace the later download request/readiness/INT1/reset sequence on both
live peers before making transport changes. Do not fabricate ACKs or skip the error.
