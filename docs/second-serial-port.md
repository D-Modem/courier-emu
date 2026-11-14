# The DSP's two serial ports, and which end the ASIC is on

> **Retracted (2026-09-07).** The section below with the title "The ASIC masters the
> primary serial bus" is not correct. The consequence that we took from it has no support.
> That consequence was that the ASIC inserts command words into `DRR`, and that thus the ring at `0x0bd0` is an
> inbound command stream. The argument needs the codec to be a
> slave on that bus, and it takes this from "register 6 = `0x20`". But **register 6
> has no master/slave bit**. It is the digital configuration register. The `M/S` **pin**
> sets the role (datasheet Table 2-1), and no
> measurement here has read this pin. Free-run (`DS05`) only selects if the
> conversion rate follows A and B or the external frame-sync interval. It has a
> meaning in codec mode, it is redundant in stand-alone mode, and it agrees with
> the two modes. Also, the clock and frame master has a *timing* role. This role
> would not put the data of the master on `DIN`/`DOUT`. Thus, "bus
> master" does not cause "inserts its own words" in either case. The standard
> topology is the AC01 as stand-alone master that controls a slave DSP. This topology agrees with all
> recorded firmware facts, and [ac01-codec-protocol.md](ac01-codec-protocol.md)
> already says it. Refer to [dsp-cpu-interconnect.md](dsp-cpu-interconnect.md).
>
> These items here are still correct: the `SPC`/`TSPC` decodes, the DSP as master of the
> second port, and its continuous transmission on that port.

We examined the board, and the link between the ASIC and the DSP looks
like a serial interface. The firmware agrees. The two serial ports are
configured for opposite roles.

## The ASIC masters the primary serial bus

Each of the two register decodes below is not unusual alone. But together, they
cause a conclusion:

* **The DSP is a slave on the primary port.** `SPC = 0x40c8` has `MCM = 0`. Thus,
  `CLKX` is an input. It has `TXM = 0`, thus `FSX` is an input. The DSP does not
  clock or frame that bus.
* **The codec is a slave on it too.** Register 6 = `0x20` puts the AC01 in
  free-run. It is wired in slave/codec mode, where (datasheet section 2.13)
  "the shift clock and the frame sync are both externally generated".

Two slaves on one synchronous serial bus need a master, and **the only other
device on it is the ASIC**. Thus, the ASIC makes `SCLK` and `FS` for the
DSP-codec link, and it decides when each word moves.

That makes the ASIC exactly the parallel-to-serial bridge that its 80186 side looks
like. The supervisor writes it through a parallel window at ports `0x40`-`0x5e`,
and it clocks words into the DSP over a serial bus that it controls.

### The consequence the harness has not modelled

The codec ISR stores **each** word that arrives at `DRR` into the ring at
`0x0bd0`, unconditionally:

```
8190  mar *, ar7 ; sar ar7, @11 ; lar ar7, @10   ; the ring write pointer
8193  lamm @20                                   ; DRR - whatever was clocked in
8194  sacl *+                                    ; into the ring
```

The main loop of the resident reads that same ring with `AR7`. Thus, the ring is not
a codec-sample buffer that the code also reads. It is **the DSP's inbound serial
stream**, and the main loop is its consumer.

The harness only puts line audio on that bus. As bus master, the ASIC can
also insert its own words, because a parallel-to-serial bridge exists to do this.
If it does, the inbound command path goes through `DRR`, and the harness has never
supplied a single word of it.

That is a different candidate reason for why the DSP never leaves its idle task. The
`ARCR` gate is the other candidate, and the two candidates can both be true.

## What the firmware programs

The firmware writes the two control registers at reset through MMR addressing. Thus, these
two sites are not ambiguous:

```
8089  lacl #38 ; samm @32     ; TSPC = 0038  (reset held, modes set)
808b  lacl #f8 ; samm @32     ; TSPC = 00f8  (released)
...
8091  splk *, #0008           ; SPC  = 0008
8093  splk *, #40c8           ; SPC  = 40c8
```

We decoded these against SPRU056D Table 9-13. Bit 4 `MCM` selects the `CLKX` source,
bit 5 `TXM` selects the `FSX` direction, and bit 0 is `TDM` on `TSPC` only:

| register | value | bits | `MCM` | `TXM` | the DSP is |
|---|---|---|---|---|---|
| `SPC` (primary) | `0x40c8` | FSM XRST RRST Soft | 0, `CLKX` input | 0, `FSX` input | **slave** |
| `TSPC` (second) | `0x00f8` | FSM MCM TXM XRST RRST | 1, `CLKX` **output** | 1, `FSX` **output** | **master** |

Bit 0 of `TSPC` is clear. Thus, the port is **not** in TDM multiprocessing mode. It
operates as an ordinary second serial port. Here, "TDM port" is only the name of the register
block.

The two roles are exactly correct for the device on each port:

* The **AC01 is on the primary port** and supplies `SCLK` and `FS`. For this reason,
  the DSP is the slave there. Refer to
  [ac01-codec-protocol.md](ac01-codec-protocol.md).
* On the **second port, the DSP controls the clock and the frame sync**. Thus, the DSP clocks the device
  at the other end.

## The DSP transmits on it continuously

The idle task writes `TDXR` on each pass. `0x81b7` is the handler that the idle state
gets to: `@1b` contains `0x8138`, which is `intr 17`. This vectors through ROM
`0x0022` to `@69` = `0x81b7`. The handler starts with `ldp #000`. Thus, its `sacl @31` at
`0x81c9` is really `TDXR`:

```
81b7  ldp  #000
81b9  lar  ar5, @74
81ba  lacc16 *+ ; adds *-      ; a 32-bit value from a pair
81bc  lt   @76 ; sath ; satl   ; scaled by TREG
81bf  sacl @7c
81c0  lar  ar5, @75            ; ...and a second one the same way
81c6  and  #00ff
81c8  add  @7c, 8
81c9  sacl @31                 ; TDXR = (first << 8) | (second & 0xff)
81ca  rete
```

Thus, it packs two scaled bytes into each word. We measured **21,976 `TDXR` writes**
in one sample window of 60,000 instructions, against **zero `TRCV` reads**.

## What this corrects

[board-parts.md](board-parts.md) said that the TDM port is "configured and then
unused". The receive half is unused. But the transmit half is one of the most frequent
activities of the DSP. The scan for that claim looked for `TRCV` reads, and then it made
a conclusion about the full port.

## The receive half really is unused - and here is why that is not circular

The obvious objection to "zero `TRCV` reads" is this: the harness never sends
a word on that port, so nothing could read one. That objection is correct about
the *runtime* measurement. This measurement alone proves nothing. It is the same trap
as the codec receive queue: nothing arrived, so the firmware consumed
nothing, so the model looked consistent with itself.

The static evidence is independent of it, and it agrees:

* **`IMR` is written exactly one time**, at `0x809e` during reset, with `0x002a`:
  INT2, TINT and XINT. `TRNT` is bit 6 and `TXNT` is bit 7. **Neither is enabled
  anywhere in the 27,710-word resident.** Thus, an arriving word could not cause an
  interrupt.
* **`TSPC` is written two times at reset and never read.** Nothing polls `RRDY` on
  that port. Thus, polling also could not find an arriving word.
* **`TRCV` is never read through MMR addressing anywhere in the resident.**

The one candidate with direct addressing, `lacl @30` at `0xaa4b`, is not a register
read:

```
aa4b  lacl @30 ; sub #4f52 ; retc neq     ; 0x4f52 = "RO"
aa4f  lacl @31 ; sub #4b43 ; retc neq     ; 0x4b43 = "CK"
```

That is a check of an ASCII signature ("ROCK") against cells on a different data
page, in a chain of `retc neq` guards. It is not `TRCV`/`TDXR`.

Thus, the link is **one-way: DSP to ASIC**. `RRST` is set in `TSPC`, and this keeps the
receiver out of reset. But nothing in the firmware ever reads the data that it
receives.

Note what the adjacent routine at `0xaa30` does, because by chance it uses
the same registers. It writes `@74`, `@75`, `@76`, `@77` with
`0x0302`, `0x0303` and `0x18`. These are exactly the cells that the idle task reads
to build its `TDXR` word. Thus, that routine configures *what* the DSP sends
out of this port: two source pointers and a shift.

## What it does not establish

We did not trace the other end of the second port, and nothing here shows that the
ASIC is on it. That is the board observation, not a firmware result. Also, we do not know
what the packed byte pairs carry. They are two independently scaled
values sent on each idle pass. This agrees with metering or control, but
that is a guess.

This is certain: **the DSP is the master of a serial link on which it transmits constantly,
and the harness models that link as fully inert.** `queue_serial_rx` supplies
the primary port. Nothing ever sends a word on `TRCV`, and the emulator counts the `TDXR` writes
and discards them. If the ASIC answers on that port, the emulator has never
received the answer. This is a candidate explanation for why the DSP never leaves its idle
task. The other candidate is the `ARCR` gate in
[what-runs-and-what-blocks.md](what-runs-and-what-blocks.md).
