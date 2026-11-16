# The DSP's mailbox poll, and what is actually starved

The first title of this file was "what it takes to make a call complete". Two of its
blockers are now removed. [datapump-gate-403-addresses.md](datapump-gate-403-addresses.md)
resolves the problem that the datapump puts nothing on the line. Also, the
mailbox poll (the blocker that gave this file its new name) **does not block.**
We measured this with the 403 board image, a leased-line pair, and 400M instructions on each side:

| | side A |
|---|---|
| DSP reads of the status latch `@57` | 342,624 |
| CPU->DSP messages delivered | 82 |
| DSP reads of the tag/word cells `0x5e`/`0x5f` | 35 |
| DSP acknowledgements (`samm @57` from `0x839d`) | 5,064 |
| **DSP->CPU messages sent** (`out` to port `0x5e`) | **1** |

The DSP polls constantly, takes each message that it gets, and acknowledges.
The `ARCR` compare below is satisfied at rest. `ar7` and `arcr` both read
`0x0bc8` in a live run. Thus, the gated block runs, and the full interpretation that "messages
overwrite each other while the DSP does not look" is **wrong**. Keep
the `NDX` measurement in this file. Discard the conclusion that we made from it.

The direction that gets no data is the **other direction**. We traced the sender of the resident at `0x83bf`
over its last 128 entries with a carrier up. It exited at `0x83c2`
(`retc eq`, the ring read and write pointers equal) **each time**. It never
gets to the host-window gate at `0x83c9`, and thus also not to the `out` at `0x83d3`.
`@78` and `@79` both read `0xff52` at the end of the run. Nothing puts data
into the outbound ring. Thus, the supervisor gets one event for each call, and no
negotiation can continue.

For the next step, refer to [datapump-gate-403-addresses.md](datapump-gate-403-addresses.md),
in the section "Overlay 8 is loaded and never entered".

## The status register is PA7, and the harness models one bit of it

Four routines in the resident all read `0xff57`:

```text
839b:  bit 15, @7d   -> bit 0    host message pending
83d6:  bit 14, @7d   -> bit 1    (also requires @79 != @78)
847a:  bit 13, @7d   -> bit 2    then dispatches through data 0x039e
80f8:  and #0200     -> bit 9
```

SPRU056D tells what that address is. Section 3.5.11 and 8.3.2: `0000h-004Fh`
is on-chip memory-mapped registers, and `0050h-005Fh` is memory-mapped I/O:
`0x50` = PA0 through `0x5F` = PA15, with `0x60`-`0x7F` scratch-pad DARAM B2. Also,
Figure 5-10: `LAMM`/`SAMM`/`LMMR`/`SMMR` force the 9 MSBs of the address to
zero. Thus, `lamm *` with `AR1 = 0xff57` really reads `0x57`.

**Thus, `0x57` is PA7, a real external I/O port, and these four routines poll a
status word that the ASIC controls.** The mechanism comes from TI. The bit meanings come from the
ASIC, and no TI document gives them.

The harness raises `HOST_MESSAGE_PENDING` (`0x0001`) directly. The harness does not raise the other bits,
but it is possible for them to be set. The
tag-`0x02` handler of the DSP at `0x8255` does `lacc #0700 ; samm @57`, and thus writes bits 8,
9 and 10 itself. The `out 0x1c` path of the CPU raises bits 1 and 2 through
`_set_dsp_status(set_bits=value & 6)`. An earlier version of this section said that
bits 1, 2 and 9 are "never set", and it concluded that the polls return immediately. The
measurement above contradicts that: `0x839b` and the routines near it run hundreds of
thousands of times and do real work.

**Where to look for the rest.** The parallel window of the 80186 at ports `0x40`-`0x5e`
supplies PA0-PA7 of the DSP. `_publish_window` already models this window.
Thus, the code that sets the bits of PA7 is 80186 code in an image that this repository has. That
is a static-analysis question against the supervisor. It is not a question without an answer
about an undocumented part. The path of `0x847a` through data `0x039e` and `bacc` is
the path that looks like "start this task".

## Where the DSP actually is

We sampled the program counter over 60,000 instructions after the download:

```text
  0x0022-0x0023     3.7%     ROM interrupt dispatch
  0x80d0-0x80e1    31.6%     the resident's main loop
  0x80e4-0x80f1    22.3%       ...and its indirect dispatch through @1a/@1b
  0x8138-0x8139     5.6%
  0x8189-0x8197     0.6%     the codec ISR, receive half
  0x819e-0x81aa     0.5%     the codec ISR, transmit half
  0x81b7-0x81ca    35.4%     a dispatched handler
```

There are eleven regions and 102 different addresses, out of a 27,710-word resident. The DSP is
**healthy and idle**. It runs its main loop, dispatches through the handler cells
at `@1a`/`@1b`, and services the codec in each frame. It has not stopped, it has not crashed,
and it is not in a wait. But nothing has ever requested it to do work. Its only
external reads are I/O `0x51`: 106 reads in 60,000 instructions.

The steady-state loop is `0x80d0 → 0x80f1 → 0x80d0`. It gets to the
block-level work at `0x80c8` only through the `cmpr eq` branch below. All four of the polls
are in that block:

```text
80c6  call 8223
80c8  call 839b     ; the host mailbox poll
80ca  call 83d6
80cc  call 847a
80ce  call 80f8
```

If we force `ARCR` to a value that `AR7` gets to (`0x0bd0` or `0x0bde`), the block runs,
and the DSP goes from 103 different program addresses to 159. **That is a
diagnostic, not a fix**. Nothing on the board writes it manually, and the
mechanism that writes it is the `@10` reload below.

**In the 403 runs, this block runs in all cases.** A live pair reads `ar7 = arcr =
0x0bc8`. The compare agrees, the block executes, and the status latch is read
342,624 times in one run. Thus, independent of what the harness models about
`ARCR`, `ARCR` is not the reason why nothing requests work from the DSP.

## The mailbox dispatch itself works

We gave one message to the resident and compared the executed addresses:

| | distinct PCs | furthest PC |
|---|---|---|
| no message | 338 | `0x8487` |
| one message delivered | **397** | **`0x8b8c`** |

The DSP leaves idle, dispatches through the tag table at `0x8480`, runs a
handler and comes back. It gets to `0x86e9`, which is next to one of the twelve
`splk @1a, #8139` sites that put the task pointer back to idle. No part of the
receive path is defective. On the 403 image, the DSP looks sufficiently often:
35 tag/word reads against 82 deliveries in a run of 400M instructions, and it acknowledges each one.
The direction that carries nothing is the sender of the DSP itself.

## The ARCR compare, and what it actually tests

The poll is in the block at `0x80c8`. The main loop gets to this block only when
`cmpr eq` finds that `AR7` agrees with `ARCR`. The ring is known exactly: `0x802e` sets
`CBCR = 0x00ef`. This selects `AR7` for circular buffer 1, with `CBSR1 = 0x0bd0` and
`CBER1 = 0x0bdf`. If `ARCR` is at any location in that ring, the block runs one time on each
pass, a few hundred times each second. That is a sensible mailbox poll rate. With `ARCR` at
zero, it would run **one time, during initialisation**.

Before, we reported that second case as the live behaviour, on a run that showed 87
delivered messages and almost no consumed messages. That is not what the 403 image
does: `arcr` reads `0x0bc8` together with `ar7`, the compare agrees, and the block
runs. The "almost nothing consumed" value was the DSP->CPU count, which we read
as the CPU->DSP count.

**`@10` is data `0x0390`, and `0x0390` is where `AR7` is kept.** Direct
addressing is relative to DP, and `ldp #007` is immediately before the
`lar ar0, @10` at `0x8105` and `0x810d`. The steady-state loop goes through the
`ldp #007` at `0x80e6` on each pass. Thus, `@10` is *not* the memory-mapped `AR0` at
data `0x0010` that an interpretation with DP 0 would give. That is the trap here. `sar ar7,
@10` at `0x808f` and `0x81a1` store the cell. `lar ar7, @10` at `0x80c5` and
`0x8192` restore it.

This makes the sequence coherent and self-contained:

```text
80c5  lar  ar7, @10     ; AR7 <- saved ring pointer
...   the gated block
80d0  lar  ar0, @10     ; AR0 <- the same cell, and ARCR/INDX with it
80d1  cmpr eq           ; TC = (AR7 == ARCR)
80d2  bcnd 80c8, tc     ; ...so: has AR7 moved off its saved value?
```

The compare does not wait for an unknown component to fill an uninitialised register.
It tests the **live ring pointer against its own saved
value**, and `ARCR` is loaded again from that slot on each pass. It needs nothing
external.

## The `NDX` side effect is real, measured on the part

That interpretation depends on `lar ar0` loading `ARCR` as a side effect. The
`LAR` page and Table 4-3 of SPRU056D say that it does this when `NDX` is clear. The prose of its section 3.5
says that it does this when `NDX` is set. The document cannot resolve this itself. Thus, we asked
the part: `artifacts/ndx-probe-01/`, on the live board. We loaded `AR0` in three ways
with each polarity. We wrote the sentinels `ARCR = 0xEEEE` / `INDX = 0xDDDD` again
before each load, so that "loaded" and "untouched" cannot be confused:

| | `PMST` | `lar ar0, @7b` | `lark ar0, #55` | `lar ar0, #4321` |
|---|---|---|---|---|
| **`NDX` clear** | `00b0` | `ARCR`/`INDX` = **`1234`** | = **`0055`** | = **`4321`** |
| **`NDX` set** | `00b4` | `ARCR`/`INDX` = `EEEE`/`DDDD` | - | - |

1. **The side effect is real on this part.** It is not a documentation artefact.
2. **The `LAR` page and Table 4-3 have the correct polarity.** The prose is wrong.
   This firmware clears `NDX` explicitly at `0x8012` (`apl @07, #07f8` then
   `opl @07, #00b0`). Thus, the side effect is **active** on the live board.
3. **It is not restricted to 'C2x instructions.** `lar ar0, #4321` is the 'C5x
   long-immediate form, and it also loaded `ARCR` and `INDX`. Any load of
   `AR0` causes it, with any encoding. The manual says "'C2x
   compatibility", and this is misleading about the scope.

The kernel sent `AR0` back in the two halves (`4321`, then `1234`) to prove that the loads
executed. Without that, a sentinel that did not change could only mean a skipped
instruction.

**The core does not model this.** It parses `m_pmst.ndx` and never reads it. Thus,
this is a model that we know is wrong. It is not a neutral omission.

## The unresolved part

If we implement the side effect, we get exactly the predicted state (`ARCR` =
`0x0bdc`, in the `0x0bd0`-`0x0bdf` ring), and **the firmware stops operating in the
harness**. `INDX` gets the same value. A stride of 3036 corrupts all 317
`*0+`/`*0-` sites in the resident. The DSP does not get to its main loop, and nothing
controls the codec (`dxr_writes` 17,931 -> 15, `tdxr_writes` 801,645 -> 0).
If we restrict the effect to `ARCR` alone, or to one `LAR` encoding, the firmware still does not operate.

**The board does this and runs.** Thus, the harness must explain the failure.
It is not evidence against the mechanism. If we add the side
effect again without a solution for the `*0+` behaviour, we would replace a wrong model with a
defective one. Thus, we intentionally do not change the emulator.

This is still a real model that we know is wrong. It is not a **blocker** now, because
the block that we thought it gates runs in all cases. Refer to the start of this file.

## The open measurement

On the board, `0x0390` reads `0x0000` in all sixteen samples
(`artifacts/dsp-at10-01/`). The control is important, because a defective
probe also returns zero. The same kernel pointed at data `0xffff` returned `0x0083` sixteen
times, which agrees with `artifacts/dsp-boot-word-01`. Thus, the path reads live cells, and the
zero is a real reading.

But we took it while idle and on hook, and after the monitor had reset the DSP. Thus, it
is the value that the resident left, and not a sample of the running loop.
With `@10` at zero, `AR7` restores to zero, `ARCR` is set to zero, and the compare
agrees. This agrees with a block that runs during initialisation and never
again. It does **not** show that `@10` is zero during a call. The ring and task
machinery may be set up only when a connection starts.

**The next useful step is to sample `0x0390` during a call.** This needs a
probe that runs together with the firmware and does not replace it. `cooperative_probe.py`
has this shape, but it cannot get to DSP data memory now.

`ARCR` is shared scratch, and this is one reason why it was difficult to interpret. The
only write of the resident to it, `samm @19` at `0x9644`, calculates
`(@7e >> 10) + 0xd9fe`. This is a **program** address for a table walk, and `0xafdf`
reads it back. It is a general-purpose ARAU register that the firmware uses again for other work,
exactly as SPRU056D suggests.

Refer to [dsp-cpu-interconnect.md](dsp-cpu-interconnect.md).

## Smaller things still known wrong

None of these items blocks a call:

* **No ring trip on the `--ring` path.** `machine.py` ORs the ring-detect bit
  from `RingSource.present()` without an off-hook gate. Thus, when you answer a `--ring`
  call, the detector stays asserted for the full call. `LineExchange` does this
  correctly. `RingSource` does not.
* **The boot transport is the wrong mechanism**, but it gets to the correct
  state. Refer to [dsp-boot-transport.md](dsp-boot-transport.md).
* **`XRDY` is optimistic on the legacy TDM path**, because that path models no
  framing on the primary serial port.
* **Codec gain, high-pass and loopback are decoded but not applied** to samples.
* **The four-bit part identity at supervisor `0x287f9`** is not modelled. Thus, it
  reads floating bits, and six sites branch on the result.

## Ruled out - do not re-run these

**Wiring the ASIC ports together instead of interpreting them.**
`COURIER_ASIC_TRANSPARENT=1` copies the 80186 side onto the I/O ports of the DSP.
It does not decode the writes of the supervisor and synthesise the status. It does not
replace the protocol: the `0x1c` handshake of the supervisor is a sequence, not
a register image.

**Reading `@10` as the memory-mapped `AR0` at data `0x0010`.** DP is 7 at each
of those sites. Thus, it is data `0x0390`.
