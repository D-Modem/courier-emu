# The call-overlay publication is a 2.1/2.2 step applied to 302/403

There is one question: why does a 302/403 run not go past V.8? This document does not answer it.
It removes an incorrect answer that all such runs depend on, and it points again
the instrument that had to report the failure.

## The 2.1/2.2 arrangement, which is real

`bridge.py` has three constants and a comment:

```python
# Call overlay 7 is stored at b9c0 with branches already linked for c418. The
# ASIC publishes that bank over c418..ce6f when it starts the datapump.
C50_CALL_OVERLAY_SOURCE = 0xB9C0
C50_CALL_OVERLAY_DESTINATION = 0xC418
C50_CALL_OVERLAY_SIGNATURE = bytes.fromhex("4a6908e3")   # lacl @4a ; bcnd ...
```

That describes the 2.1/2.2 family.
[c52-v8-static-analysis.md](c52-v8-static-analysis.md) independently gives
`main211.xmf`, `main2205.XMF` and `3453Bv2.1.1.xmf` an overlay source of
`b9c0`/`b9c8`. The mechanism is "stored here, runs there": the branches of the stored copy
are already linked for `0xc418`.

## On 302/403 the signature matches code that is already in place

`_find_call_overlay` scans the resident bank for the signature. The two images
give **two** hits, and the one that it accepts is the incorrect one:

| image | hit | `size = (0xc418 - source) * 2` | taken |
|---|---|---|---|
| 302 | `0xba2f` | 5074 | **yes** |
| 302 | `0xca41` | -3154 | no, negative |
| 403 | `0xba0b` | 5146 | **yes** |
| 403 | `0xca1d` | -3082 | no, negative |

The accepted block is not a stored overlay. Its branches are linked for its own
address:

```text
ba2f  lacl  @4a
ba30  bcnd  ba3c, neq        ; <- ba3c, not c425
ba32  lacl  @4d
ba33  bcnd  ba3c, eq
ba35  sach  @4d
ba36  lar   ar1, #03c8
ba38  rpt   #02 ; tblr *+ ; add #03 ; sacl @4b
ba3c  lacl  @48
ba3d  bacc
```

Thus, the harness copies 2,537 words of **live, self-linked resident code** to
program `0xc418`. The copy goes across `0xc418`-`0xce00`, where each internal
branch in the copy still points back into `0xba2f`.. The resident bank
had its own code there. On 403, `0xc81a` is
`splk @04, #038d ; splk @2b, #0003 ; splk @1b, #c821`. On 302, entry 3 of the originate
slot table is `0xc557`, in the overwritten span.

**The note of the 2.1/2.2 profile itself already says that these are two different transfer
protocols**: an update payload that strobes one window on `0x1e`, against the `e47b`
downloader of a flash ROM that alternates two windows on `0x18`. 302 and 403 are flash
ROMs, and they have the real overlay table
([dsp-overlays.md](dsp-overlays.md)): overlay 6 at `0x9d00`, 7 at `0xb000`, 8 at
`0xdc00`. The `0xc418` publication is a third, incompatible item.

## Where the dispatcher actually is

When we search correctly for the same signature, it gives three copies in each image. The
overlay copies have a two-word guard that the resident copies do not have:

| image | resident | resident (2nd) | overlay 6 | overlay 7 |
|---|---|---|---|---|
| 302 | `0xba2f` | `0xca41` | `0xade8` | `0xc529` |
| 403 | `0xba0b` | `0xca1d` | `0xadf5` | `0xc528` |

```text
ade6  bit   1, @4c        ; the overlay copies only
ade7  retc  ntc
ade8  lacl  @4a
```

All four are the same routine as the `0xc418` of 2.1/2.2, including the identical
`lar ar1, #03c8` table pointer.

## What this does and does not establish

**Established.** The V.8 instrumentation of the native core is fixed to the 2.1/2.2
addresses:

```cpp
if (previous_pc == 0xc418) { ++m_v8_dispatches; m_v8_record = ...; }
bool negotiation_loop = previous_pc == 0xc7f7 || previous_pc == 0xc81a ||
    previous_pc == 0xc853;
```

`0xc7f7`, `0xc81a` and `0xc853` are the 2.1/2.2 divide loops from the static
analysis. On 302/403, they are ordinary resident routines. Also, `0xc418` becomes
`lacl @4a` **only because the misplacement put it there**. Thus,
`v8_dispatches` on a 302/403 run counts the entries to the injected copy, not to the
dispatcher of the firmware itself. On this target, these counters give no useful
information.

**Not established.** That this is *the* reason that V.8 does not complete. These
counters are write-only. They are exported in the status struct and never feed
back into the execution. Thus, the instrumentation half causes blindness, not the failure.
The copy itself overwrites live code, and it is a defect alone. But
nothing here traces a failing V.8 exchange to it. The correct state is that the
one instrument for this question pointed to the incorrect firmware, and
no run has yet asked the question with the instrument pointed correctly.

**The native V.8 tone bootstrap is also not the cause.** `detect_v8_tones`,
the write to `@0306` and the `0x0100` bit in `@039f` all have a gate on
`m_v8_mode`. That value stays `Off` unless `set_v8_calling` /
`set_v8_answering` is called, and `bridge.py` calls those only under
`legacy_carrier_fallback`. In a normal run, the firmware owns the two cells, as the
comment there says.

## The run

The two changes are in. The core takes its dispatcher addresses from the image
(`Bridge._v8_dispatch_addresses`, the same signature over the resident bank and
each declared overlay). `_find_call_overlay` now requires that the candidate is
**pre-linked for the destination**: its first branch target must be
`0xc418 + 0x0d`. The stored copy of 2.1/2.2 satisfies this, and a self-linked
resident copy does not.

A 403 linked pair, `ATX0` + `ATDT5551234` against `ATA`, 85 M instructions
(`artifacts/v8-dispatcher-403-01/`):

| | A base | A gated | B base | B gated |
|---|---:|---:|---:|---:|
| `v8_dispatches` | 22,471 | 22,471 | 21,172 | 21,172 |
| `v8_dispatch_pc` | `0xba0b` | `0xba0b` | `0xba0b` | `0xba0b` |
| **`v8_handler` (`@48`)** | **0** | **0** | **0** | **0** |
| `v8_countdown` (`@4a`) | 0 | 0 | 0 | 0 |
| `v8_flags` (`@4d`) | 0 | 0 | 0 | 0 |
| `v8_rx_peak` | 0 | 0 | 0 | 0 |
| `negotiation_audio.rms` | 0 | 0 | 0 | 0 |
| `overlay_downloads` | 0 | 0 | 0 | 0 |
| `call_overlay_available` | True | **False** | True | **False** |

`base` is the same command with the pre-linked test forced true, which is the old
behavior. **Each V.8 number is identical.** Only `call_overlay_available`
changes, and `call_overlay_active` was already false in the two runs. Thus, the misplaced
block was found but never published in this run. The gate removed a latent
hazard and changed nothing that we can see here. It did not cause any of the results
below.

### Three things the run says

**1. The dispatcher runs.** `0xba0b` is the resident copy of 403, entered 22,471
times on the originator. The instrument now reports.

**2. It has no handler.** `@48` is zero, and so are `@4a` and `@4d`. Thus, each
entry uses the short path (`bcnd ba18, eq` directly to `lacl @48 ; bacc`)
and branches to program address **0**. In 2.1/2.2, the
`c509`/`c527`/`c54d`/... sites install the handlers when they write into `@48`. Nothing installs one
here. The state machine spins on a null vector.

**3. There is no audio.** `v8_rx_peak`, `rms` and each tone bin are
zero on the two sides, also in the baseline. The DSP receives no line samples. Thus,
the V.8 exchange has nothing to detect, also if a handler were installed.

### What (3) is downstream of

The codec receive block has a gate on `m_call_tdm_active`. That flag has exactly two
setters, and both are in `_activate_call_overlay`, behind
`self._call_overlay is not None`. With the correct gate, that path now
correctly does not run on a flash ROM. It was never the correct trigger for a flash
ROM, because a flash ROM loads its datapump through the real overlay table over ports
`0x18`/`0x1e`.

But `overlay_downloads` is **0**, thus that does not occur either. This document
cannot call that a bug: [datapump-dispatch-gate.md](datapump-dispatch-gate.md)
records that a plain dial never gets to the loader, because the discriminator
answers equal. Only the leased and the `&T1`/`&L1` configurations get to it. Thus, when a plain
`ATDT` run has no datapump overlay, this can be correct firmware behavior.
The modelling defect behind it is that the line-audio gate is connected to the 2.1/2.2 publication.


## Why there is no audio from the originator: the two ends stop at different times

The audio capture (`artifacts/v8-dispatcher-403-01/audio/`) divides the question
clearly. `b-tx` and `a-rx` are **identical**: 23,841 nonzero samples, peak
17,188, from sample 96,273 to 120,113, which is 12.03 s to 15.01 s. This is the
answer tone, delivered to the originator sample for sample. The socket, the
7200-to-8000 conversion and the framing all work. `a-tx` is 127,200 frames of
zero, but the core says that the datapump of side A wrote 5,176 nonzero samples into
`m_line_tx`. The samples exist, but none got to the wire.

### The instrumented answer

`Bridge._line_service` counts each branch of `_service_line`. One 403 pair,
`artifacts/v8-dispatcher-403-01/run-instrumented.json`:

| | A (originate) | B (answer) |
|---|---:|---:|
| `_service_line` calls | 77,786 | 77,786 |
| `no_codec_clock` | 1 | 1 |
| **`originate_return`** | **0** | **0** |
| `fallback_frames` | 0 | 0 |
| `drained_frames` | **228** | 158 |
| `buffer_left` | 126 | 737 |
| `line.frames` shipped | **158** | 158 |
| `line.connected` | **False** | True |
| `line.error` | *the far end closed the line* | - |

> **The originate early return was not the cause.** An earlier revision of this
> document proposed the `not self._call_overlay_active` guard in
> `_service_line` as the cause. The reasons were that it is the only
> originate/answer asymmetry in that function, and a 69%/99% shipping split.
> It operates **zero** times in this run, on the two ends. The inference was not correct,
> and the guard is not the cause.

The buffer of A is almost empty at the end (126 samples). Thus, nothing is stuck. A
calls `_service_line_frame` **228** times, and only **158** of them get to the
peer. The other **70 frames are exactly 7.00 s**. That is the shortfall that the
previous revision measured and explained incorrectly as an unshipped tail. They are not
unshipped. They are shipped into a socket that is already closed.

### The two instances diverge by 44 % in line time

The two ends stop at the same 85,000,000 x86 instructions, and that is not the
same quantity of call:

| | A | B |
|---|---:|---:|
| x86 instructions | 85,000,000 | 85,000,000 |
| DSP instructions | 276,637,801 | 243,300,764 |
| codec samples produced | 164,278 | 114,428 |
| **codec time** | **22.82 s** | **15.89 s** |

B gets to its budget at 15.89 s of line time and exits. A continues to 22.82 s
and communicates with nothing. The answer tone that A responds to comes at 12.03 s -
15.01 s, at the end of the life of B. Thus, **A makes each nonzero sample
after B has gone.** That is why `a-tx` is silent from the start to the end, and not
only late: A had nothing to send until the last second of the run of B, and
sent it after that.

This is a fault of the harness, not of the firmware. When two instances are paired on
an instruction budget each, and their ratios of instructions to codec samples are different by
44 %, they get different clocks on a shared wire. The line socket pairs them
frame for frame. Thus, the end with the shorter life silently truncates the call. A run
that ends in the middle of the exchange gives no conclusion about V.8.

### What to fix, and what it does not explain

Budget the pair on **line frames** and not on x86 instructions, or run until
the two ends agree that they are done. Until then, no linked-pair run gives a
conclusion about the negotiation.

It is still separately true that `@48` is zero during all 22,471 dispatches
(refer to the text above). The truncation does not explain that, because the code enters the dispatcher
from the first seconds. The two faults are live. This one must be
cleared first, because it makes each run unreadable after 15.89 s.

## Budgeting on line frames: the truncation is fixed, and A is still silent

`--line-frames N` on `run` and `link` stops each side after it has exchanged N
line frames. `Bridge.line_frame_budget` operates `Machine.request_stop` from
`_service_line_frame`. Thus, the two ends exit at the same point in *call* time, and
`--instructions` is only a ceiling.

`artifacts/v8-line-frames-403-01/`, 300 frames against a 250 M ceiling:

| | A (originate) | B (answer) |
|---|---:|---:|
| `line.frames` | 300 | 300 |
| `line.connected` at exit | **True** | **True** |
| `line.error` | none | none |
| `buffer_left` | 2 | 2 |
| x86 instructions | 97,386,495 | 111,219,711 |
| codec samples | 216,007 | 216,007 |
| **codec time** | **30.00 s** | **30.00 s** |

The divergence is gone: identical call time, the instruction counts are different by
14% as expected, no socket closes before the other end, and nothing is left in
either buffer. The mechanism works.

**But it changed nothing about the audio.** Over 30 s, with the two ends alive
during all of the time:

| wav | frames | peak | nonzero | span |
|---|---:|---:|---:|---|
| `b-tx` | 240,000 | 17,188 | 23,841 | 12.03 s - 15.01 s |
| `a-rx` | 240,000 | 17,188 | 23,841 | 12.03 s - 15.01 s |
| **`a-tx`** | **240,000** | **0** | **0** | - |
| **`b-rx`** | **240,000** | **0** | **0** | - |

`line_tx_nonzero` is 5,176 on A, the same value as in the truncated run, and
`a-tx` is 240,000 zeros.

> **Superseded.** The section above concluded that the silence of A came from
> the truncation, that is, that A made each nonzero sample after B
> had gone. **That is disproved.** With 30 s and the peer alive during all of that time,
> A makes exactly the same 5,176 nonzero samples, and still puts none of them
> on the wire. The truncation was real and it was correct to fix it, but it was not the cause of the silence of A.

### What that leaves

The samples are in the buffer of the core itself: `m_line_tx` holds 216,007 words, of
which 5,176 are nonzero, and the same array is what `line_tx_samples` gives to the
bridge. `_exchange_tx_index` starts at zero, no core rebuild occurred
(`core_rebuilt_at: 0` on the two ends), and almost all of the array was
consumed: 240,000 line samples shipped against 216,007 codec samples produced.
At 7200-to-8000, that is the full stream. Thus, the nonzero words were read out
of the array, and they did not get to the socket.

There are two candidates, and we tested neither: the codec-to-line conversion in
`_take_line_audio`, and the one of the four `m_line_tx.push_back` sites on the
core side that the nonzero writes of A come from. `line_dac_writes` is 0, thus they are not
the DAC slot of the datapump. The audio of B goes through the same conversion without damage. This
is an argument against the resampler and for the write path, but it is an argument,
not a measurement.

## The transmit array and the bridge's reading of it disagree

The datasheets are not the missing item here. When we follow the silence of A down to the
sample, we find a contradiction in the harness.

`Bridge._final_line_tx_scan` reads the full `m_line_tx` of the core one time, at the
end of the run. Thus, the answer cannot depend on when it was sampled. Next to it,
`_take_line_audio` now records how much it consumed and the peak that it saw:

| | A (silent) | B (audible) |
|---|---:|---:|
| core counter `line_tx_writes` | 216,007 | 216,007 |
| core counter `line_tx_nonzero` | 5,176 | 29,375 |
| final scan total | 216,007 | 216,007 |
| final scan nonzero | 5,176 | 29,375 |
| final scan peak | **22,748** | **28,040** |
| final scan first nonzero | 27,412 (3.81 s) | 20,406 (2.83 s) |
| bridge consumed | 216,003 | 216,003 |
| bridge index reached | 216,003 | 216,003 |
| **peak the bridge saw** | **0** | **17,188** |

The final scan agrees exactly with the counters of the core itself, on the two ends. And
the bridge consumed indices 0 to 216,002. These **include** index 27,412,
where the first nonzero sample of A is, but the bridge got a peak of zero.

The same disagreement is on the audible end, at a smaller scale. The array of B has a peak
of 28,040, but the bridge only saw 17,188, which is also the peak in
`b-tx.wav`. Thus, the view of the bridge agrees with what got to the wire
in the two cases. It is the *array* that has values that the bridge never read.

These items are excluded, each by measurement and not by a code read:

* **Not a core rebuild.** `core_rebuilt_at` is 0 on the two ends, and `bootstraps`
  is 1.
* **Not trimming.** `m_line_tx` has exactly one `clear()`, in `reset()`, and no
  `erase`, `resize` or `pop_front`.
* **Not the resampler.** The peak is zero *before* the codec-to-line
  conversion, not after it.
* **Not an out-of-range read.** The accessor returns 0 after the end, but each
  index in question is far inside an array that the same call reports as 216,007
  long.
* **Not the truncation**, and **not the originate early return**. Both are settled
  above.

A `std::vector` does not change a value at an index that is already
written. Thus, one of these two measurements does not measure what it seems to measure.
That is the next item to find. It is a bookkeeping fault in the harness,
and not an item of the AC01, the ASIC or V.8. **Do not make conclusions about the
firmware from a transmit path in this state.**

### The next question, singular

Is `@48` ever written on this image, by any site, in any configuration?
If nothing writes it, the dispatcher at `0xba0b` is not the live V.8 state
machine on 403, and the signature match is misleading. Then the overlay copies at
`0xadf5` and `0xc528` would be the candidates, and neither can run until an
overlay is downloaded. That is a static question, and it must be asked statically
before another run.

## The next question, answered: `@48` is written, and the dispatcher is still not it

First, two faults in the instrument. Then the answer.

**The originate gate stopped the arming for a dialed call.** `_maybe_start_originate_engine`
returned unless `daa.operation == "originate"`. Its docstring explains this:
it was written for the leased line, where the originating side never dials.
After the socket path got a digit receiver, the operation changes to `"dialing"`
on the first digit. Thus, the originating end stopped the arming completely. A dialing
seizure now qualifies after the called party has answered. That is when a real
originating modem starts V.8. It does not put CM under its own digits.

**`@48` was read from the incorrect data page.** The core sampled `m_data[0x48]`.
A direct operand on the C5x resolves to `(DP << 7) | offset`. Thus, that reading
assumes `DP == 0`. The measurement at the dispatch shows that **DP is 0x180**. Thus, `@48` is data
address **0xc048**, and `@4a`/`@4d` are `0xc04a`/`0xc04d`. Each
earlier report of a null handler read a cell that the firmware never uses.

**And the image does write it.** A static scan of the 403 resident segment for
stores to the direct operands:

| cell | sites |
|---|---:|
| `@48` | 57 |
| `@4a` | 26 |
| `@4d` | 58 |

Almost each `@48` site is `splk @48, #<the address two words later>`:
`a688: splk @48, #a68a`, `bb55: splk @48, #bb57`, `e637: splk @48, #e639`.
Thus, `@48` is a continuation vector, and `lacl @48 ; bacc` resumes it. This is
the same arrangement as the `c509`/`c527`/`c54d` sites of 2.1/2.2. The signature
match is not misleading because of missing writers.

### What the corrected instrument says

A 403 pair with `--answer-on-ring`, 600 line frames:

| | A (originate) | B (answer) |
|---|---:|---:|
| `v8_dispatches` | 47,425 | 62,759 |
| `v8_dispatch_pc` | `0xba0b` | `0xba0b` |
| `v8_dispatch_dp` | `0x180` | `0x180` |
| **`v8_handler` (`0xc048`)** | **0** | **0** |
| `v8_countdown` (`0xc04a`) | 0 | 0 |
| `v8_flags` (`0xc04d`) | 0 | 0 |
| `v8_record` | `0xb779` | `0x0194` |
| line audio produced | DTMF only | answer tone, 2.98 s |

`@48` is zero at each dispatch **on the two ends, including the end that works**.
In this run, B sends a full 2.98 s 2100 Hz answer tone, but its handler vector
reads null during 62,759 dispatches of the same routine at the same page.

**Thus, `0xba0b` is not the live V.8 state machine on 403.** That was the
alternative that the document itself gave, and the evidence now supports it. A routine with a vector
that is null on the side that negotiates successfully is not the routine that does
the negotiation. Do not use `v8_dispatches`, `v8_handler`, `v8_countdown` and `v8_flags`
as V.8 progress on this target, at any page where they are sampled.

The mailbox stream separates the two ends. Their originated tags
almost do not overlap. A makes `0008:*` (`0008:0080` 673 times, `0008:0880` 387,
`0008:0885` 128), and B makes `0016:*` (`0016:0080` 895, `0016:0088` 116).
They share only `0002:0000`, `0008:0000` and `000f:0000`. The two ends run
different programs, and the question of why A never transmits is about that
difference and not about `0xba0b`.

### Also settled since the sections above were written

The transmit-array contradiction at the end of the previous section is
solved. It was not a bookkeeping fault of the type that we guessed there. The
supervisor resets the DSP two or three times in each call. `reset()` clears
`m_line_tx`, but the output cursors of the bridge did not restart with it. Thus, the
start of each generation was skipped. The two measurements were correct, but they
read different generations of the array. The cursors now reset with the
core. `a-tx` is no longer silent because of that. It carries the dialed
digits. `b-tx` increased from 23,841 nonzero samples to 38,914.

## The mailbox tag difference is one report from two detector banks

The previous section said that the two ends "run different programs", because
their originated tags almost do not overlap: A makes `0008:*`, and
B makes `0016:*`. That interpretation is too strong, and the code shows it.

**The two tags come from the same instruction.** Each originated message on
the two ends is sent at `pc 83d4`, in a generic sender at `0x83bf`:

```text
83c0  lacc  @79 ; sub @78 ; retc eq     ; ring empty, nothing to send
83cd  lar   ar1, @79                    ; read pointer into the ring at ff60
83ce  bit   15, *                       ; does a data word follow?
83cf  lacl  *+ ; and #7fff
83d3  out   @7d, 005e                   ; the tag
83d6  out   @7d, 005f                   ; high word, always 0000
83de  out   *+, 005f                    ; the data word, if bit 15 was set
```

Thus, the "tag" is only the first word that the caller queued, masked to 15 bits, and
bit 15 means that one word follows. It has no function of its own. The enqueue is
the routine above it at `0x83b0`, and the image has **118 call sites**.

**The two sites are the same report.** `0x9c93` and `0x9f02` are structurally
identical: the tag, then the same payload:

```text
9c93  lacc  #00008008        9f02  lacc  #00008016
9c95  call  83b1             9f04  call  83b1
9c97  lacl  @2f              9f06  lacl  @2f
9c98  and   #00008fff        9f07  and   #00008fff
9c9a  call  83b1             9f09  call  83b1
```

The two send `@2f & 0x8fff`. These are not two subsystems. They are one status word,
reported from two locations.

**The difference is the detector bank above each one.** `a09b` is a threshold
compare. The caller points `ar1` at a measurement cell and puts a constant in the
accumulator, and `xc 2, leq` sets a bit in `@2f` on the result.

| site | cell | threshold | bit set |
|---|---|---|---|
| `9c7e` | `03be` | `2adb` | `0x0040` |
| `9c87` | `01fe` | `59d8` | `0x0080` |
| `9c90` | `01fa` | `61d7` | `0x0100` |
| `9ef0` | `03b8` | `47a2` | `0x0010` |
| `9ef9` | `03b6` | sum > `1f40` | `0x0400` |

Thus, `@2f` is a bitmap of detector results, and the tag identifies which bank
filled it. A runs the bank at `0x9c78`, and B runs the bank at `0x9ee8`. That is what
an originating end and an answering end must do. The tag difference is a
result of the two roles. It is not evidence of a fault. The payload
histograms agree with that bitmap. The most frequent value of A is `0x0080`, exactly the
bit that `9c87` sets. The most frequent value of B is also `0x0080`, with `0x0400` and `0x0008` added,
which are the bits that its own bank sets.

**One asymmetry to keep.** After the report, B always calls `a0b3`
(`9f0b`). A calls it only when bit 10 of `@2f` is clear
(`9c9c: bit 10, @2f ; cc a0b3, ntc`). Bit 10 is `0x0400`, which is the bit that
`9ef9` sets from the energy sum at `03b6`. It is in the payloads of B
(`0016:0408`, `0016:0448`) and in none of the payloads of A. Thus, on this run, A always
makes that call. We do not establish here if `a0b3` is the routine that acts on a detection, and
we make no claim about what these banks detect. The cells and
thresholds are recorded above, so that the question can be asked directly.
