# How the DSP and the ASIC/CPU are connected

**Update, 2026-09-07:** New board probes explain and correct the NDX/PA7 interaction.
See [the board comparison and corrections](dsp-mailbox-board-fix.md). The older
ARCR/INDX blocker conclusions below are historical. The new probes replace them.

This document is a synthesis for one question: what is the path that the 80186
supervisor and the C5x datapump use to send data to each other? It keeps the
items that the hardware proves apart from the items that we infer. It also
retracts one claim that sent the debug work in the wrong direction.

**The short version.** A *logical* path is proven. On the live board, a kernel
on the DSP wrote its I/O ports `0x5e`/`0x5f`, and 2048 words arrived at the
80186. The *physical* arrangement is now also known, and it is the simple one.
The ASIC is on the 16 data pins of the DSP. Also, `IS` is connected to the
ASIC. `IS` is the I/O-space strobe, and only an `IN`, an `OUT` or a
`PA0`-`PA15` access asserts it. Thus the ASIC decodes the I/O cycles of the
DSP on the same bus as the SRAMs, and the serial theory is retired. Refer to
"The physical objection, resolved" below.

## The proven part

The evidence is `artifacts/dsp-onchip-rom-01/`, and **only** that directory:
"read from the DSP of a live Courier", 20.16 MHz board, ID_SDL v4.03d,
2026-09-07. We put a kernel in supervisor RAM with `ATGLK2W` and started it
from the Timer 0 interrupt. The kernel ran at DSP program `0x8000`, read the
on-chip ROM with `RPT`/`TBLR`, and returned 2048 words. Its sender is the
outbound pattern of the resident. In `build_rom_dump_probe`, that pattern is
exactly `out @7c, 0x005e` / `out *+,
0x005f` / `2 -> @57`. The returned image has a plausible reset vector
(`0000: b 0670`) and 1307 different values. Two independent runs agree.

Thus **the I/O-space writes of the DSP get to the 80186 on the real board.**
We measured this result.

The ROM came off the board **in two halves**. The cause is that the watchdog
resets the DSP before a 2048-word frame can complete. The two real captures
are `artifacts/dsp-onchip-rom-01/half0-frame.txt` and `half1-frame.txt`.
`dsp-onchip-rom-01/manifest.json` records how we joined them.

> **Make sure that you cite the correct directory.** The top-level
> `dsp-rom-half0/`, `dsp-rom-half1/`, `dsp-rom-dump-v*`, `dsp-rom-transport-v*`
> and `dsp-rom-sample-v1` directories are the **emulator dry-runs** of the
> same kernel. They have `hardware_tested: false`, and their `serial_text` is
> a synthetic ramp (`0x1234 + 0x193n`). The hardware captures of the two halves
> are *in* `dsp-onchip-rom-01/`, and they start with `7980 0670 0860 BE20`.
> That is real code, not a ramp. Two earlier versions of this document had
> this wrong in two opposite directions. The first version cited a dry-run as
> the proof. The second version used the same flag to conclude that nobody
> took a half-dump on hardware. Both were wrong. The dry-runs and the real
> runs only use the same kernel and the same names.
>
> `artifacts/dsp-boot-word-01/` is real hardware, but it also does not prove
> this. Its kernel is put in memory and started in the same way. It shows
> what the ASIC supplies at DSP data `0xffff`, not the return path.

The three windows, from `artifacts/io-port-map/board-21210/` and
`artifacts/cpu-port-map-01/`:

| direction | 80186 side | C5x side | commit/resume |
|---|---|---|---|
| CPU → DSP | tag `0x58`/`0x5a`, data `0x5c`/`0x5e` | tag `PA14` (`0x5e`), data `PA15` (`0x5f`) | CPU writes bit 0 of `0x1c`; DSP acks by writing 1 to `PA7` |
| DSP → CPU | `0x60`/`0x62`, **27 reads / 0 writes** in the whole image | the sender, one word per interrupt | CPU acks bit 2 of `0x1c` |
| download | `0x40`-`0x4e`, eight latches | program RAM, DSP held in reset | no "go" - releasing reset is the go |
| status | `0x1c`/`0x1e` | `PA7` (`0x57`) | bit 0 host message pending, bit 9 gates `0x80f8` |

On the DSP side, the dispatcher reads the tag, rejects tags above `0x7f`, and
branches through a 121-entry jump table. `PA0`-`PA15` are not a peripheral
block and not reserved space. SPRU056D section 3.5.11 and Table 8-8 make DSP
data `0x0050`-`0x005F` the sixteen I/O ports. Ordinary data addressing and
`IN`/`OUT` can both get to them. **The ASIC is the device on the other side of
these ports.**

### Why a board inspection sees no parallel traces

A board inspection found no traces from the address/data pins of the DSP to
any device other than its two `CY7C199` SRAMs. This objection stopped the
work. The data that follows makes the objection weaker, but it does **not**
remove it. Refer to "The physical objection".

SPRU056D Table A-8 gives `DS`, `PS` and `IS` as three *space-select strobes*
on **one** address/data bus: "Data, program, and I/O space select signals.
Always high unless low level is asserted for communicating to a particular
external space." Thus an I/O cycle drives the same address and data pins as a
data cycle. Only the strobe that goes low is different.

Thus an I/O port on the C5x is not a separate parallel port with its own pins.
If the ASIC is on that bus, it connects to the *same nets* that go from the
DSP to its SRAMs, and `IS` qualifies it. This removes one form of the
objection, because there is no second, dedicated 32-wire bus to look for. But
it does not remove the objection.

## What this does and does not block

It is important to keep these items apart, because this question used much
time. **The physical medium is not on the critical path of the emulator.**

The harness does not simulate traces. It simulates what `out @7c, 0x5e` does
on one side and what `in al, 0x5c` returns on the other. Two sources confirm
that programming model:

- SPRU056D section 3.5.11 and the Table 8-8 note put the sixteen I/O ports
  `PA0`-`PA15` at data `0050h`-`005Fh`. Data addressing, MMR addressing and
  `IN`/`OUT` can all get to them.
- The on-chip ROM came off the live board through exactly that protocol: poll
  `PA7` bit 1, tag to `PA14`, word to `PA15`, `2` back to `PA7`. `bridge.py`
  already implements this protocol.

The ASIC can make those sixteen ports with twenty parallel taps, a shift
register, or a different method. In all cases, **the instruction streams of
the two processors see the same thing, and the emulator is already correct
about it.** It is useful to find the medium for the board documentation. But
it will not change a line of code, and it is not what stops a call.

The *rate* is what stops CPU-DSP communication in the harness. The `ARCR`
compare gates the mailbox poll of the DSP. Thus delivered messages overwrite
each other before the DSP reads them. That is the blocker, and it is in
[what-runs-and-what-blocks.md](what-runs-and-what-blocks.md).

## The channel discipline is a single-word window with ready/ack

The firmware answers this part, and the two sides now agree on it. **Each
DSP-CPU transfer in this firmware moves one word and then stops for an
acknowledgement.** No code does a block transfer.

**DSP side, the mailbox sender** (`0x83eb`):

```
83eb  0c7d 005e      out  @7d, 005e     ; tag
83ee  0c7d 005f      out  @7d, 005f     ; word
...            lacl #02 ; samm @57      ; raise "message ready"
```

**DSP side, the stream sender** (`0x84b7`). This sender is a *coroutine*:

```
8499  ae80 849f      splk *, #849f      ; where to resume next time
849b  7d80 84b7      bd   84b7, *
849d  bf09 0385      lar  ar1, #0385    ; ...the source for *this* word
...
84b7  0c80 0060      out  *, 0060       ; exactly one word
84b9  ff00           retd
84ba  b904           lacl #04
84bb  8857           samm @57           ; raise "stream ready", and return
```

Each resume point (`0x8499`, `0x849f`, `0x84a5`, `0x84ab`, `0x84b1`) sends one
more word from a different address and then yields again. Before it continues,
the resume poll at `0x8462` tests bit 13. Because of the `bit` inversion, this
is **bit 2**.

**CPU side, the stream reader** (`0x1fec`). It is the mirror image of the
stream sender:

```
001fec  e462         in   al, 0x62      ; high byte
001fee  8ae0         mov  ah, al
001ff0  e460         in   al, 0x60      ; low byte
001ff2  8987d502     mov  [bx+0x2d5], ax
001ff6  80eb02       sub  bl, 2
001ff9  7805         js   0x2000        ; ...done
001ffb  881ed102     mov  [0x2d1], bl
001fff  c3           ret                 ; one word per call
```

It assembles **one** 16-bit word from two byte reads, stores it, steps a
counter, and returns. `[0x2d3]` holds the address to resume at. Thus the full
receiver is a state machine that starts again once for each acknowledgement.
A second variant at `0x2037` does the same operation into a pointer at
`[0x8a2]`, with a length counter at `[0x8a0]`/`[0x8a1]`.

Thus the ASIC supplies a **one-word holding register with ready/ack flow
control** in the two directions. In the full image, the `0x60`/`0x62` window
of the CPU has 27 read sites and **zero** write sites.

### What that does and does not prove

It **excludes** shared memory or any random-access window between the two
processors. Neither side has a buffer that it can index into. There is one
word in transit, and one handshake for each word. Software sees a serial link
in this way, and this agrees with the board.

But this result alone does **not** exclude a narrow parallel mailbox register.
That register must use the same discipline for the same reason. If we call
this a proof of a serial medium, it is the third over-reading in the history
of this document. Thus we do not call it a proof here. This statement is
correct: **no data in the firmware contradicts a serial link, and the item
that we thought contradicted it does not.**

That item was "the DSP has a wide parallel window". This is not true. The full
I/O footprint of the DSP is eight ports, and the DSP accesses them one word at
a time:

| port | use |
|---|---|
| `0x5e` / `0x5f` | mailbox tag and word (`out`, `0x83eb`) |
| `0x60` | the stream sender (`out`, `0x84b7`) |
| `0x68`-`0x6c` | written at reset (`0x8048`-`0x8056`) and in the ISR region |
| `0x57` (`PA7`) | the status latch, read by `lamm` from `0xff57` |

The wide window at `0x40`-`0x4e` is on the **CPU** side only. Also, `0x60` and
`0x68`-`0x6c` are **outside** `PA0`-`PA15` (`0x50`-`0x5f`). Thus the statement
in [what-the-asic-does.md](what-the-asic-does.md), "the ASIC presents at most
sixteen 16-bit registers to the DSP", is too narrow. Those ports are ordinary
I/O addresses that do not alias into data space.

## What the primary port's interrupt actually is

The residents themselves answer this question. The same sequence is in all of
them: 403 and 302 at `0x8090`, 2.1.1 at `0x80bd`, 2.3.31 at `0x109d`:

```
lar  ar1, #22        ; SPC
splk *,   #0008      ; both halves into reset, FSM on
splk *,   #40c8      ; RRST and XRST released; MCM = 0, TXM = 0
lacl #01 ; samm @21  ; prime DXR
bit  11, *           ; spin on XRDY - wait for an *external* frame edge
bcnd back, ntc
samm @21             ; reload DXR
lamm @06 ; samm @06  ; write-1-clear whatever latched during the spin
lacl #2a ; samm @04  ; IMR = INT2 | TINT | XINT
clrc intm
```

`MCM = 0` and `TXM = 0` make the DSP a slave. The AC01/ASIC controls `CLKX` and
`FSX`, thus the frame edge is external. The frame scheduler of the emulator
models this. `IMR = 0x002a` is bits 1, 3 and 5. Bit 5 is **`XINT`**, the
transmit interrupt. `RINT` is bit 4, and it is not enabled.

A cold start of the 403 resident confirms this from start to end. When the part
stops at `0x813c`, it has `IMR = 002a` and `SPC = 40c8`. The dispatch cells of
the mask ROM hold `@65 = 8178` (`XINT`) and `@64 = 819d` (`RINT`). `819d` is the
same unused stub that `@6a` holds for NMI. Only `XINT` has a handler.

Thus the frame service is the interrupt of the *transmitter*, not of the
receiver. Now the function of `@6b`/`@6c` at `0x8138` is clear:

```
8138: samm @6c    ; the word to hand the codec
8139: lacl #03
813a: samm @6b    ; three frames' worth
813b: idle        ; wait for the frame interrupt
813c: lamm @6b
813d: bcnd 813b, neq
813f: ret
```

The full AC01 register-load path of the resident goes through that `IDLE`.
The path is `lacc #010a ; call 8138`, then `#0214`, `#0300`, `#0409`, `#0505`,
`#0620`, with the register in the high byte and the value in the low byte. If
you suppress the frame interrupt, the part stops there permanently.

### `INT2` is the host's doorbell, and its handler does nothing on purpose

The full vector table of the mask ROM is `lamm @6x ; bacc`. Each vector
dispatches through a data cell, and the resident fills these cells from the
table at `0x812d`:

| cell | vector | 403 value |
|---|---|---|
| `@60` | `INT1` | `81ba` - bare `rete` |
| `@61` | `INT2` | `819d` at cold start - but see below |
| `@62`-`@64`, `@66`, `@67`, `@6a` | `INT3`, `INT4`, `RINT`, `TRNT`, `TXNT`, `NMI` | `819d` |
| `@65` | `XINT` | **`8178`** - the frame ISR |
| `@68` | `TINT` | **`81fb`** |
| `@69` | - | **`81a6`** - packs two bytes into `TDXR` |

Thus, of the three bits that `0x002a` enables, `XINT` and `TINT` have handlers,
and **`INT2` is enabled with a handler that only returns**. This is not an
error, and the board shows its function. ASIC pin 109 goes to DSP pin 39,
which is `INT2` ([asic-pinout.md](asic-pinout.md), measured).

The CPU-to-DSP path is *polled*. It is not interrupt-driven. `0x80ea`:

```
80ea: setc intm
80eb: calld 80e8, * ; lar ar1, #57   ; read PA7 through the 80e8 gadget
80ee: clrc intm
80ef: and #0200 ; bcnd 80fc, neq     ; bit 9 -> the host has a group
80f6: lar ar0, @10 ; cmpr eq
80f9: xc 1, tc ; idle                ; otherwise sleep
80fb: ret
```

The transfer itself is at `0x80fc`:

```
810e: lar ar1, #58                   ; the ASIC's four-word window
8110: splk @09, #0003                ; BRCR = 3
8112: rptb #811e
8114:   calld 80e8 ... ; mar *+ ; sacl @7d
811a:   bldp @7d                     ; into PROGRAM memory at BMAR
811b:   lamm @1f ; add #01 ; samm @1f
8120: lacc #0300 ; samm @57          ; ack in PA7
8127: intr 17
```

That is the firmware download, and the command path has the same shape. The
handler has no work to do, because the work is in the loop. The only function
of the pin is to **end the `IDLE` at `0x80fa`**. If you set the flag but do not
assert the pin, the DSP still gets there. But it gets there only when a
different event wakes it, for example the codec frame or the timer. Thus a
transfer moves forward at the frame rate, not when the host has a group ready.

#### `INT2` is not always the do-nothing stub

`819d` is only the cold-start value of `@61`. Three routines change it:

```
823d: splk @61, #819d ; splk @68, #81fb ; opl @1f, #0100   ; wake-only
8245: splk @61, #81bb ; splk @68, #81fb ; apl @1f, #feff   ; DAC mode
824d: splk @61, #819d ; splk @68, #81fb ; apl @1f, #feff   ; wake-only
```

`0x81bb` reads the phase word of the ASIC at `@52` and masks it to two bits.
Then it indexes the four-entry table at `0x81e0`, runs a multiply-accumulate
chain and writes port `0x6a`. Thus in that mode, **each `INT2` edge is a
polyphase DAC slot**. The same pin is both the mailbox doorbell and the output
tick. The same idiom is in all builds. 302 changes `@61` between `81ae` and
`81cc` at `0x824e`. 2.1.1 changes it between `8224` and `8228` at `0x8293`.

An earlier version of this section said that the `INT2` handler was a bare
`rete` "on purpose". That is true for the wake-only mode and for the cold
start. It is not true for the part in general.

#### `INT1`: nothing drives it

`@60` holds `81ba`, which is also a bare `rete`. It is a second stub, one word
before `0x81bb`. The two ends show that the line is not used in this firmware:

* **The DSP never enables it.** No code sets `IMR` bit 0. The only writes that
  certainly get to `IMR` are `samm @04` and, in the 2.x builds, the
  `and #ffcf ; or #0010` pair. `samm @04` writes `0x002a` once in the 403 and
  302. The pair changes bits 4 and 5 only. Also, no code writes `@60` after the
  init table copy at `0x812d`. Each apparent `splk @60` in the images is
  DP-relative and writes ordinary data.
* **The CPU never asserts it.** The pin is 80186 **P1.7** (CPU pin 50,
  `P1.7/GCS7`). It is on the same `P1LTCH` at `0xff56`, where bit 1 is DSP `RS`
  and bit 3 is DSP `NMI`. In the full 403 supervisor, only these instructions
  change that latch:
  * `AND`/`OR` on bits 2, 5 and 6.
  * `AND AX,00ff ; OR AX,0020` (the EEPROM).
  * `AND AX,fffd` at `0x8e3f1` (reset).
  * `OR AX,0008` at `0x8e445` (NMI).

  No code drives bit 7 low, and the init value of the latch is `0xdb`, with
  bit 7 high.

Thus `INT1` is wired, stays deasserted, and is masked at the two ends.
[board-verified-403.md](board-verified-403.md) reads `f7fe` from `@60` at the
end of a dial. That value is an overlay that uses the cell again as B2 scratch.
The same reuse puts the counter and word of the codec handoff in `@6b` and
`@6c`, which are the `INTR 12` and `INTR 13` cells.

### And the 2.x builds can move it to `RINT`

Immediately after the 2.1.1 and 2.3.x residents enable `0x002a`, they test data
`0x012f`. If it is set, they do this:

```
lamm @04 ; and #ffcf ; or #0010 ; samm @04
```

This clears `XINT` and enables `RINT`. It is the same frame, but the other
interrupt, and the configuration selects it. The 403 and 302 removed this
branch and use `XINT` only.

This gives the model: **one external frame edge latches both `RINT` and
`XINT`**. Each interrupt is behind its own half of the `SPC` reset
(`RRST`/`XRST`). `IMR` and `INTM` decide recognition, as on the part. If the
model latches only one of the two, it cannot run both variants. An older model
gated the edge on `RRST`, which is the reset bit of the receiver. This gated
the 403 service on a register that the 403 never reads.
## If the link is serial, it is the *primary* port, not the second one

The first guess is this: the C50 has two serial ports, one port is for the
codec, thus the other port is for the ASIC. The firmware shows that this guess
is wrong. The second port cannot carry the interprocessor link **in either
direction**.

**It cannot carry CPU to DSP.** For that, the DSP must read `TRCV`, and it
never does:

* The code writes `IMR` only once, at `0x809e`, with `0x002a`. `TRNT` is bit 6
  and `TXNT` is bit 7. No code in the 27,710-word resident enables them, thus
  a word that arrives cannot cause an interrupt. (`samm @04` is the only write that
  certainly gets to `IMR`. `splk @04` is DP-relative, and each `splk @04` in
  these images is on a non-zero page. A raw opcode scan for `8804` finds one
  hit in each of the 302 and 403 residents, both at `0x809e`.)
* The code accesses `TSPC` through MMR addressing only twice, both at reset
  (`samm @32` at `0x808a` and `0x808c`). It never reads `TSPC`. Thus it also
  never polls `RRDY`.
* No code reads `TRCV` through MMR addressing.
* The one direct-addressed candidate, `lacl @30` at `0xaa4b`, is scratch on a
  non-zero data page. We checked this, and it is not only a claim. Its helper
  at `0xaa68` **writes** `@30`-`@33` (`sacl @30`, `sach @31`, `sacl @32`,
  `sach @33`) as a 64-bit rotate. With `DP = 0`, this helper would store to the
  read-only `TRCV` and write `TSPC` again in a shift loop. Thus it is not the
  TDM block. (The adjacent `0xaa14`-`0xaa21` is a symmetric coefficient table
  that the disassembler shows as code.)

**It also does not carry DSP to CPU.** The two senders use `OUT`, not `TDXR`.
The mailbox at `0x83eb` writes ports `0x5e`/`0x5f`. The stream coroutine at
`0x84b7` writes port `0x60`.

The second port sends one continuous stream in one direction. The idle task at
`0x81b7` packs two scaled bytes from data `0x0302`/`0x0303` and writes `TDXR` on
each pass. Several routines point it again at the same pair (`0xaa34`,
`0xab50`, `0xc594`, `0xceff`). Thus the mode controls *what* it sends. That is a
data sink, not a command channel, and we do not know yet what is at its far end.

Also, the ports of the 'C5x are **synchronous** (`CLKX`/`FSX`). They are not a
start/stop UART, thus no device here is a 16550. The ASIC end would be a shift
register in the gate array. On the second port, the **DSP** is the master
(`TSPC = 0x00f8`, `MCM = 1`, `TXM = 1`). Thus the DSP would supply the clock,
not the ASIC.

### Which leaves the primary port, and one pin decides it

On the primary port, the DSP is a **slave**. `SPC = 0x40c8`. `MCM = 0`, thus
`CLKX` is an input. `TXM = 0`, thus `FSX` is an input. A different device
drives that bus.

If that device is the AC01 in stand-alone/master mode, the ASIC is not on the
serial link. If the AC01 is in **codec/slave** mode, it also does not drive the
clock. Then the ASIC is the only other candidate. In that case, the primary
serial port is the CPU-to-DSP path. The words from the ASIC arrive at `DRR`
and go into the ring at `0x0bd0`, which the main loop reads. This theory agrees
with a serial board. It would also connect the interconnect to the `ARCR` ring
gate, which is the live blocker.

The firmware **cannot** select one of these two, for the reason given above.
The `M/S` **pin** sets the role, not a register bit, and free-run does not
imply it. Thus one measurement on an accessible package pin is necessary:

> **Probe `M/S` on the TLC320AC01CFN: pin 18 of the FN (PLCC) package**
> (from the terminal table of the datasheet, which gives numbers for the FN
> package. With the same numbers, `MCLK` is pin 14 and `PWR DWN` is pin 2).
>
> * **High**: the AC01 is master. It supplies the clock for the primary bus, the
>   ASIC is not on it, and the interprocessor link is at a different location.
> * **Low**: the AC01 is a slave. It does not drive `SCLK`/`FS`, and the DSP
>   also does not. Thus a third device drives them, and the ASIC is the only
>   candidate on that bus.

That one reading resolves the retraction recorded above. It also shows if the
`0x0bd0` ring is a codec buffer or the inbound command stream. It does this
without a trace of the board.

## The physical objection, resolved

The count must still be correct. To capture `out` to `PA14`/`PA15` and to
answer reads of `PA7`, the ASIC must have these connections: the **16 data
lines** of the DSP, sufficient address lines to separate the ports (~4), and
`IS` plus the read/write strobes. That is about **20-23 connections**, not 32.
All of them are taps onto nets that already exist. But they must still
physically get to the ASIC.

The reported inspection found no such connection. If the board really has no
such connection, then one of these items is true. This document cannot say
which:

1. **The taps exist, and the inspection did not see them.** The SRAMs use the
   same nets. The ASIC can be physically between or adjacent to the DSP and its
   RAMs. Thus, from above, "traces go from the DSP to its RAMs" and "the ASIC
   is on those nets" look the same. This is a continuity question, not a visual
   one.
2. **I/O cycles alias into the shared RAM.** We wrote `build_io_alias_probe` in
   `courier_emu/dsp_probe.py` to test this hypothesis, and it agrees best with
   the inspection. If an `out` goes into the external RAM of the DSP, the ASIC
   can already read that RAM. It must read it, because it loads 30,172 words of
   program into it. In that case, the mailbox needs **no** I/O-specific wiring.
   The probe writes one port and reads it back in six ways, which include a
   read from external RAM at data `0x8053`. The probe is built, but it is not
   connected to the CLI, and nobody has run it.
3. **The return path is not what the code of the kernel shows.** This is the
   least probable item, because the sender is three instructions. But nobody
   has checked it independently.

Item 2 would also agree with the boot observation. The DSP could boot by
**serial** download (its ROM loader, on the primary port). At runtime, it could
still get to the supervisor through RAM-aliased I/O cycles. Serial boot and a
mailbox that works can both be true.

**The test that decides is easy, and it does not need the emulator:** run the
I/O-alias probe on the board, or measure the continuity from the pins of the
ASIC to the data bus of the DSP and `IS`.

### The data bus does reach the ASIC (2026-09-07)

A board observation reports that the DSP connects to the ASIC on its **16 data
pins**. This selects **reading 1**, not the serial hypothesis. It does this
because it removes the premise of the serial theory. The earlier inspection
saw traces that went only to the two `CY7C199`s, and the statement "the mailbox
cannot be parallel" came from that inspection. If the ASIC is on the data bus,
no part of this document needs a serial medium.

The shape agrees. The SRAMs divide the bus into `D0`-`D7` / `D8`-`D15` (refer to
[dsp-map-302.md](dsp-map-302.md) on the 32Kx8 parts). Thus a device on all
sixteen lines is not on one RAM only. It is on the bus of the DSP itself. That
is exactly the "between or beside the DSP and its RAMs" arrangement that
reading 1 predicts.

**This result does not do two things.**

* **It does not separate reading 1 from reading 2.** The two readings put the
  ASIC on the same sixteen wires. In reading 1, the ASIC decodes the I/O cycle.
  In reading 2, the ASIC only monitors the memory bus, and an `out` goes into
  RAM that the ASIC can already read. The two readings use the same data pins,
  thus these pins cannot select one reading. The test that decides is the same
  as before, and it is one pin: **`IS`, pin 90** (refer to
  [dsp-pin-probes.md](dsp-pin-probes.md)). If `IS` goes to the ASIC, the ASIC
  decodes `OUT`, and `PA0`-`PA15` are ASIC registers. If `IS` does not go near
  the ASIC, the alias reading is correct, and the mailbox needs no I/O-specific
  wiring.
* **It is not yet connected to numbered pins.** This repository does not have
  the `D0`-`D15` pin numbers from SPRU056D Table A-4. All other pin claims here
  have pin numbers, but this claim does not. Get the pin numbers before you
  accept this claim as fact. The M/S pin numbers needed the same caution.

The method also has the same limit as the inspection that it overturns. From
above, a net that goes near the ASIC and a net that ends on it look the same.
The reading that counts is continuity to the pins of the ASIC, in the two
directions.

**More meter readings, with the easiest first:** `IS` (90) to the ASIC. Then
sufficient address lines to separate the ports (~4). Then `R/W` (92) and `STRB`
(93). Adjacent pins on that edge, to help you find the position: `DS` 89, `PS`
91.

### `IS` is connected to the ASIC (2026-09-07)

A meter on **pin 90** shows continuity to the ASIC. This answers the question
that this document kept open through three revisions.

`IS` has only one function. SPRU056D Table A-8 gives `DS`, `PS` and `IS` as
three space-select strobes on one address/data bus, each "always high
unless low level is asserted for communicating to a particular external space".
The SRAMs need only `DS` and `PS`. Thus `IS` goes low only for an `IN`, an
`OUT`, or an access to `PA0`-`PA15`. If a device connects to `IS`, the only
purpose is to decode the I/O cycles of the DSP. That net has no other function.

**Thus reading 1 is correct.** The ASIC is on the nets that go from the DSP to
its two `CY7C199`s, and `IS` qualifies it. `PA0`-`PA15` are real ASIC
registers. `out @7d, 0x5e` is a parallel write into a hardware register on the
gate array. The poll of `PA7` is a parallel read from a hardware register.

**What that retires:**

* **The serial medium.** It is now not only unsupported but also unnecessary.
  This document hedged some statements as "nothing in the firmware contradicts
  a serial link". You can remove those statements. It is not necessary to
  defend them.
* **Reading 2, the RAM alias.** Its only advantage was that it needed no
  I/O-specific wiring. But there is I/O-specific wiring. `build_io_alias_probe`
  in `courier_emu/dsp_probe.py` has no question to answer now. It is still not
  connected and nobody ran it, and this can stay so.
* **Reading 3, a return path that is different from what the code of the
  kernel shows.** It was already the least probable item. It was only necessary
  to explain how three `out` instructions got to the CPU if the bus did not
  carry them.

**What it does not answer.** These items are now the open ones:

* **How much address the ASIC has.** Answered: `A0`-`A3` (55-58) **and `A5`**
  (60), without `A4` (59). Refer to "The decode is five lines" below. This item
  is not open now, and it answers the alias question that it was for.
* **If the ASIC also answers `DS`.** In `artifacts/dsp-boot-word-01/`, the ASIC
  supplies `0x0083` at DSP **data** `0xffff`. That is a `DS` cycle, not an `IS`
  cycle. Now that the gate array is known to be on the bus, that reading is
  easier to accept than before. But an SRAM with `/CE` tied low would answer
  the same cycle. Thus it is not yet certain that this word comes from the
  ASIC. Refer to [dsp-map-302.md](dsp-map-302.md) on what drives the chip
  selects of the RAMs.

**No emulator change is necessary.** The harness does not simulate traces. It
simulates what `out @7c, 0x5e` does on one side and what `in al, 0x5c` returns
on the other, and that programming model was already correct. This answers the
board documentation question, as the section above predicted. The blocker on
CPU-DSP communication is still the mailbox poll rate. Refer to
[what-runs-and-what-blocks.md](what-runs-and-what-blocks.md).

### The decode is five lines: `A0`-`A3` and `A5`

The next reading came back. `A0`-`A3` (55-58) and **`A5`** (60) go to the ASIC,
and **`A4`** (59) does not. This retires the alias that the previous revision
of this section predicted. `0x60` is **not** `PA0`, and the stream sender at
`0x84b7` writes its own register.

**These five lines give a unique decode for each port that the DSP uses.** The
full I/O footprint of the firmware is `0x57`, `0x5e`, `0x5f`, `0x60` and
`0x68`-`0x6c`. In `0x50`-`0x5f`, the low nibble separates them. `0x60` and
`0x68`/`0x6a`/`0x6c` have `A5` high and `A4` low. The `PA` bank has `A5` low
and `A4` high. Thus the two groups cannot collide. In the second group, the
low nibble separates the ports again.

**The important point is that the ASIC uses `A5` but not `A4`.** This is not a
random decision to use fewer lines. `0x5x` and `0x6x` are different in *both* bits 4 and 5. Thus one
line separates the banks, and the other line is redundant. A designer who
connected the gate array to only one of the two lines knew that there were
exactly two banks to separate. Thus this is positive evidence for the two-bank
model, not only data that agrees with it:

| bank | `A5` | ports | what it is |
|---|---|---|---|
| `0x50`-`0x5f` | low | `PA0`-`PA15` | the memory-mapped I/O ports, aliased into data space at `0x0050`-`0x005f` |
| `0x60`-`0x6f` | high | `0x60`, `0x68`-`0x6c` | pure I/O space, no data-space alias |

**Thus the register file is larger than sixteen**, and the statement "at most
sixteen" in [what-the-asic-does.md](what-the-asic-does.md) is wrong, for the
reason given first. The correction stays. The doubt about it in the previous
revision does not stay.

**A falsifiable prediction, and an easy one.** Because `A4` is not connected,
the ASIC cannot separate ports that are different *only* in bit 4. The firmware
never uses those ports, but a probe can:

* an `out` to port `0x40` must go into `PA0` (`0x50`)
* an `out` to port `0x47` must go into `PA7` (`0x57`), which you can read back
  directly through the status latch at `0xff57`
* an `out` to port `0x70` must go to the same location as `0x60`

You cannot test these items if you write a value and read it back. The
DSP-side registers of the ASIC are not general storage. `PA7` returns status
bits, independent of who wrote it. `PA0` is a sample sink and a boot-word
source. Thus the test must be **differential on an effect that you can see**.
The mailbox is that effect, and this repository already used it from start to
end on hardware.

`build_port_fold_probe` in `courier_emu/dsp_probe.py` is that kernel. It is the
proven outbound sender, and it sends a pattern that you can recognize. The tag
and data go out on **`0x4e`/`0x4f`**, not on `0x5e`/`0x5f`. No other item
changes: not the frame, not the ack, not the host capture. The ack stays
`samm @57`. That is a data-space MMR write, not an I/O cycle, thus it is not
part of the test.

```bash
.venv/bin/python -m courier_emu.probe_transport \
  --reference IDSDL302.ROM --output artifacts/port-fold-01 --port-fold
```

**Run the positive control first.** It is the same kernel on the real ports:

```bash
.venv/bin/python -m courier_emu.probe_transport \
  --reference IDSDL302.ROM --output artifacts/port-fold-control-01 \
  --port-fold --fold-tag-port 0x5e --fold-data-port 0x5f
```

How to read the result:

| control | folded | conclusion |
|---|---|---|
| frame arrives | frame arrives | `A4` is not decoded - the fold is real, and `0x4e` *is* `PA14` |
| frame arrives | nothing | `A4` is decoded after all, and the visual reading of pin 59 is wrong |
| nothing | either | the run did not work; the folded result means nothing |

The third row shows why the control is necessary. Here, a negative result is
silence, and silence has many causes.

### Run on the board: the fold is real (2026-09-07)

`artifacts/dsp-port-fold-01/`. Three runs on the live unit. We put each image
at `0x3000` with `ATGLK2W` and verified that it was byte-exact before we
started it.

| run | ports | payload | result |
|---|---|---|---|
| control | `0x5e`/`0x5f` | `4E00` | `CDRP1 DONE`, 8 words, `SUM:701C` |
| **A4 fold** | `0x4e`/`0x4f` | `F700` | **`CDRP1 DONE`, 8 words, `SUM:B81C`** |
| A5 control | `0x6e`/`0x6f` | `A500` | `CDRP1 START`, then `CDRP1 ERR TAG` |

**`A4` is not decoded.** A mailbox frame sent to `0x4e`/`0x4f` arrives in
exactly the same way as a frame sent to `0x5e`/`0x5f`. **`A5` is decoded**:
`0x6e`/`0x6f` delivers nothing. This result excludes the other reading, in which
the ASIC ignores the address bus and answers each `IS` cycle. Thus the
electrical behavior of the board confirms the visual reading of pins 55-58, 59
and 60 by their effect.

**The payload pattern is important.** The first fold attempt used the `4E00`
of the control again. Thus its frame looked the same as a second run of the
kernel that the DSP already held in program RAM. The download could fail
without an indication and give the same output. We do not count that attempt.
The run above sends `F700`, which only the newly downloaded kernel can send.
`--fold-pattern` is for this purpose, and each run on the board must use its
own pattern.

**The emulator was wrong, and now it is correct.** The harness compared
`port == 0x5E` and predicted `CDRP1 ERR TAG` for the folded run. The board sent
the frame. `bridge.ASIC_DSP_PORT_MASK` now models the measured decode, and all
three runs give the same frames as the board, byte for byte. Note its stated
limit: nobody tested bits 6 and 7. Thus the mask can be narrower than the
decode of the board, and it will accept `0x0e` where the board possibly does
not.

**Two procedural notes for persons who do this test again.** Each item caused
one failed run here:

* The `arm.txt` of `emit_ram_writes.py` only hooks IVT vector 8, and on this
  board that starts nothing. `T0CON` at `0xff36` reads `0x8021` (`EN=1`,
  `INT=0`). Thus timer 0 runs but never causes an interrupt. To start the
  monitor, a separate `ATGLK2WFF36,A021` is necessary. This is what
  [ram-probe-delivery.md](ram-probe-delivery.md) means by "enabling timer 0's
  interrupt".
* **The board reboots after each run.** Thus, before a second run, write
  `ATGLK2W0020,3000` / `ATGLK2W0022,0000` again. If you do not, the run gives
  no output, and it looks like a failed probe. An earlier version of this note
  said "the monitor restores vector 8", which was wrong. Refer to
  [ram-probe-delivery.md](ram-probe-delivery.md) on the watchdog reset. That
  reset restores the vector, clears RAM and brings `AT` back as one event.
## The retraction: the ASIC is not shown to master the primary serial bus

[second-serial-port.md](second-serial-port.md) says that the ASIC generates
`SCLK` and `FS` for the DSP-codec link. From this, it concludes that the ASIC
puts its own words into `DRR`. Then the ring at `0x0bd0` would be an inbound
*command* stream that the harness never supplied. **The premise is not true,
thus the conclusion is also not true.**

The argument needs the two devices on that bus to be slaves. For the DSP, the
argument reads this correctly from `SPC = 0x40c8` (`MCM = 0`, `TXM = 0`). For
the codec, it reads it from "register 6 = `0x20` puts the AC01 in free-run, and
it is wired in slave/codec mode". That step has two errors:

* **Register 6 has no master/slave bit.** It is the *digital configuration*
  register: free-run, FSD output enable, 16-bit mode, force secondary, software
  reset, software power-down (datasheet section 2.20.7). The **`M/S` pin** sets
  the master/slave role. Table 2-1 says: "Master/slave select input. When M/S is
  high, the device is the master and when low, it is a slave." Firmware cannot
  set it, and nothing in this repository has measured it.
* **Free-run does not imply slave/codec mode.** `0x20` is `DS05`, and free-run
  does only one thing. It makes the ADC/DAC conversion rate follow the A and
  B registers, not the external frame-sync interval. In codec mode, that is a
  real choice. In stand-alone mode, the rate already comes from A and B, thus
  the bit is redundant but it causes no problem. It agrees with **both**
  topologies and does not select one of them.

Without that premise, the standard topology agrees with all firmware facts
that we recorded. TI wires this topology in its own `slaa006` reference
design: **the AC01 is the stand-alone master, and it generates `SCLK` and `FS`
for a slave DSP.** [ac01-codec-protocol.md](ac01-codec-protocol.md) already says
the same ("the AC01 is on the primary port and supplies `SCLK` and `FS`").
`second-serial-port.md` contradicts this, but it does not say so.

The same argument has a second, independent gap. If the ASIC *were* the clock
and frame master, that is a **timing** function, not a data function. When a
master drives `SCLK` and `FS`, this does not put its data on `DIN`/`DOUT`.
Thus "bus master" does not lead to "inserts its own words into `DRR`" in either
case.

Thus the ring at `0x0bd0` is what it looks like: a codec sample ring. The
inbound command path is the mailbox, which is proven and which the emulator
already models.

## The codec's control words decode cleanly, and give MCLK

`docs/` now has the TLC320AC01 datasheet. Thus we can read the six control
words that the firmware of this board sends at reset, and it is not necessary
to guess them. The secondary-word format (section 2.19.1) is two control bits,
`R/W`, a 5-bit register address in `DS12`-`DS08`, and 8 bits of data:

| word | register | data |
|---|---|---|
| `010a` | 1, A register | 10 |
| `0214` | 2, B register | 20 |
| `0300` | 3, A′ (phase) | 0 |
| `0409` | 4, amplifier gain | 9 |
| `0505` | 5, analog configuration | 5 |
| `0620` | 6, digital configuration | `0x20` = free-run |

The decode agrees with the rate equation of the part,
`fs = MCLK / (A x 2 x B)`. With A = 10 and B = 20, it gives exactly
**7200 Hz**, which is the measured rate of the dial path.
[codec-rate-312.md](codec-rate-312.md) finds that the V.34 path selects B = 19
and B = 18. These give exactly **7578.95 Hz** and **8000 Hz**. Thus three
independent rates agree with their known values from one constant:

> **MCLK = 2.880 MHz**, which is the 40.320 MHz oscillator of the board divided
> by exactly **14**.

That is a new datum. It also shows where MCLK comes from. The `MCLK` of the
AC01 is an input in all modes, and the board has one oscillator can. The ASIC
is the only part that could divide it. Thus the ASIC supplies the master clock
of the codec, independent of whether it supplies the shift clock.

Also, **the firmware never programs registers 7 and 8**. Register 8 is the
frame-sync number. A master device needs it to know how many slaves are in the
chain. Register 7 is the frame-sync delay, which "must be the last
register programmed when using slave devices". Because these registers are not
programmed, *master-with-slaves* is not possible. Stand-alone mode or codec
mode remain, and the firmware cannot give more data than this. One look at the
`M/S` pin is necessary to decide.

## The live blocker, and a lead that does not work yet

The topology is not what stops the communication between the two processors.
The cause is that the mailbox poll of the DSP almost never runs. The poll is in
the block at `0x80c8` (program `0x00c8`. This file uses the `+0x8000`
convention). The main loop gets to it only when `cmpr eq` finds that `AR7` is
equal to `ARCR`:

```
80d0  0010           lar     ar0, @10     ; @10 under DP=7 is 0x0390
80d1  bf44           cmpr    eq           ; AR7 vs ARCR
80d2  e100 80c8      bcnd    80c8, tc
```

`AR7` is the ring pointer. `0x802e` sets `CBCR = 0x00ef`, which selects `AR7` for
circular buffer 1 with `CBSR1 = 0x0bd0` and `CBER1 = 0x0bdf`. Data `0x0390`
is the ring **write** pointer that the serial ISR keeps at `0x8191`/`0x81a1`.
Thus the compare is intended as a ring rendezvous. Any `ARCR` value in the ring
makes the mailbox poll run once on each pass.

But in the emulator, `ARCR` holds `0xec3e`. This is a **program** address that
the table walk at `0x9644` leaves there. That walk has the only `samm @19` in
the resident. Thus the compare never matches, and 87 delivered messages
overwrite each other before the DSP reads them.

### The lead: PMST.NDX, which is real but does not fit

The `lar ar0, @10` immediately before each `cmpr eq` has no purpose if the
compare reads `ARCR`. The idiom is at three sites (`0x80d0`, `0x8105`,
`0x810d`). SPRU056D explains why it could have a purpose. The cause is PMST
bit 2, `NDX`:

> *(LAR instruction reference, page 6-124)* "You can maintain software
> compatibility with the 'C2x by clearing the NDX bit. This causes any 'C2x
> instruction that loads auxiliary register 0 (AR0) to load the auxiliary
> register compare register (ARCR) and index register (INDX) also."

Table 4-3 agrees, and gives the reset value as 0. This firmware **clears
`NDX` explicitly** at `0x8012`. `apl @07, #07f8` clears bits 0, 1 and 2, and
the next `opl @07, #00b0` sets only bits 4, 5 and 7. Thus, in theory, each
`lar ar0` writes the ring write pointer to `ARCR`. The core implements none of
this. `native/c5x_core.cpp` parses and stores `m_pmst.ndx`, but it reads the
value only to make the register again.

If we implement it, we get exactly the predicted state: `ARCR` becomes
`0x0bdc`, in the ring. **But this breaks the firmware.** `INDX` gets the same
value. A stride of 3036 corrupts all 317 `*0+`/`*0-` indexed-addressing sites
in the resident. The DSP does not get to its main loop, and nothing drives the
codec (`dxr_writes` 17,931 → 15). The firmware also fails if we apply the side
effect only to `ARCR`, or only to the direct/indirect `LAR` encoding.

Thus we **reverted** the change. The position is:

* The mechanism is real and documented. It is the only mechanism that we found
  that would put a ring address in `ARCR`.
* The firmware clears `NDX`. The table of the datasheet says that this
  *enables* the side effect.
* But this firmware ran on real hardware, and it cannot operate with the side
  effect that the datasheet describes.

One of these three items must be wrong. Also, SPRU056D contradicts itself on
the polarity. The text in section 3.5 says that the side effect occurs when NDX
is **set**. The LAR page and Table 4-3 say that it occurs when NDX is
**clear**. Thus the document cannot reliably decide this question, and the
actual behavior of the part is the open question. A hardware probe is the easy
test that decides: a kernel that clears `NDX`, does `lar ar0, #1234`, and sends
back `ARCR` and `INDX`.

## The channel is interrupt-driven, and the harness invents the interrupt

All the sections above are about the *ports*. This section is about the line
that gives the *time*. The harness does not model this part.

On the 403 board, IVT vector `0x0c` (INT0, an external pin) reads
`8f46:0000`, and that address is the full DSP-to-CPU path:

```
8f46:0000  fb        sti
           fc        cld
           60        pushaw
           06        push es
           e41e      in   al, 0x1e
           8ae0      mov  ah, al
           e41c      in   al, 0x1c
           250300    and  ax, 3          ; two bits, and nothing else
           a37f01    mov  [0x17f], ax
      test 1 -> out 0x58, 0x5a, 0x5c, 0x5e        ; host -> DSP send
      test 2 -> in al,0x5a / in al,0x58 / call [0x192]   ; DSP -> CPU receive
           a17f01    mov  ax, [0x17f]
           e61c      out  0x1c, al       ; ack: the status written back *set*
           86c4      xchg ah, al
           e61c      out  0x1c, al
```

**No code in the image calls or jumps to that address.** We searched all 512
KiB for a near call, a near jump, a far call and the bare word `0000` with
segment `8f46`. We found no reference. Only the vector starts the handler.
Thus each message that the two processors receive is one entry to this
interrupt. The "supervisor never pops" symptom is about an interrupt line, not
about a polling loop.

A second copy, almost the same, is at `8f46:0939` (file `0xfd99`). It masks to
`7`, not `3`, and it adds a bit-2 branch that does `lcall 8000:067b`. No code
refers to it either. We did not find which of the two handlers the vector
points to in each firmware state. The run that we measured below enters the
handler at offset zero.

### What the harness does instead

[machine.py:1565](../courier_emu/machine.py:1565) raises vector `0x0c` each time
that `FRAME_INSTRUCTIONS` have elapsed since the last one.
[machine.py:523](../courier_emu/machine.py:523) gives the reason directly:
"Nothing on the CPU side produces that edge, so a ROM run has to stand in for it
the way it already stands in for the tick." On the board, the ASIC drives that
pin from the mailbox state. In the harness, it runs freely.

We measured this on the 403 plain dial that fails, with `--trace-pc` on each
branch of the handler:

```sh
./courier run artifacts/courier-board-21210-capture-403/courier-board.rom \
    --with-dsp --exchange --exchange-number 6245=answer --tick-ms 5 \
    --board-id 7 --nvram-fixture idsdl403 --at 'ATDT6245' \
    --instructions 150000000 --summary \
    --trace-pc 8f460=int0_entry --trace-pc 8f4bc=recv_branch \
    --trace-pc 8f4c9=recv_call --trace-pc 8f4d0=ack_1c --trace-pc 8f495=send_branch
```

| | count |
|---|---|
| INT0 entries | 12,809 |
| receive branch taken (bit 1) | 61 |
| send branch taken (bit 0) | 6 |
| `dsp_originated_messages` | 28 |
| reads of `0x5c`/`0x5e` | 28 each |

12,809 interrupts to carry 34 events. Each of the other 12,775 reads a
status that the ASIC never asserted, and acknowledges it again when it writes
it back to `0x1c`.

The tag that the handler reads shows the same problem more clearly. In the 57
calls to `[0x192]`, the word from `0x5a`/`0x58` is:

    0008   28 times    the resident's messages, all of them
    0000   29 times    an empty lane

Thus the 28 real messages arrive. But the free-running edge also makes 29 more
receive cycles. Each of these cycles reads an empty mailbox and dispatches on a
tag of zero. The channel is not silent in the harness. The harness drives it
randomly against a request line that nobody asserts.

This alone does not prove that the free-running edge causes the 403 dial to
fail. But it shows that the harness never had a correct model of the one event
that the full channel uses.

### Measured: the edge free-runs at 2.4 kHz, and the reply cadence is 20 ms

**Run on hardware, 2026-09-09**, `artifacts/coop-int0-01` and `-02`. The board
was at `/dev/cu.usbserial-11420`, ID_SDL 4.03d, supervisor 7.4.16, DSP 3.1.2,
with a line in the jack. The stimulus was a bare `ATD`, held for 6 s and then
aborted (`NO CARRIER`).

    interrupts            15,868 in 6.61 s   =  2,401 / s
    0x1c = fd             1,895 of the last 1,920 entries
    0x1c = ff                25 of them
    0x1e = ff             1,920 of 1,920

**The first claim above is wrong, and we withdraw it.** The ASIC does *not*
assert this pin from the mailbox state. The pin runs freely at 2,401 Hz, and
the handler polls `0x1c` on each interrupt. This is why `0x1c` reads `fd` for
98.7% of the entries: bit 0 is set, bit 1 is clear, and there is no work. Thus
the harness is correct *in kind* when it uses a periodic edge. A paragraph said
that the board would show if the edge is event-driven. The board answered
that question, and the answer is against the hypothesis that caused the
question.

The harness has the rate wrong, and it is wrong in the opposite direction to
what "12,809 interrupts to carry 34 events" suggested. That run covers 6,858
ticks of 5 ms, which is 34.3 s of emulated time. Thus it raises **373 INT0 per
second**, and the board raises 2,401. The harness does not service its mailbox
too frequently. It services it **six times too slowly**.

The part that is really a signal is bit 1:

    entries between consecutive 0x1c = ff, in order:
    48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 58 81

There are twenty-two consecutive intervals of exactly 48 interrupts. At
2,401 Hz, that is **20.0 ms**. It is a 50 Hz report from the DSP, accurate to
the sample. The last two intervals become longer when the dial is aborted and
the loop is released. The earlier capture had a ring that stopped when it was
full. Thus it holds the *first* 0.8 s after the stub was armed, before the hook closes. In
that capture, `0x1c` stays at `fd`, with no bit 1. Thus the cadence does not
run freely with the interrupt. It starts with the seizure.

The harness must produce that shape. It is a much more specific target than
"the resident should report something". The target is a message every 20 ms
while the loop is off hook. Now the harness has 28 heartbeats at 70 ms
intervals, and nothing reads them.

### And the harness cannot yet run at that rate

If we set the edge to the measured 2,401 Hz, **the one path that worked
breaks**:

| | 391 Hz (default) | 2,401 Hz (measured) |
|---|---|---|
| 302 plain | `6245`, ringback, answer | `""`, dial-tone |
| DTMF blocks | 136 | **770** |
| DSP-originated messages | 389 | 389 |
| 403 plain | `""`, idle | `""`, idle |

The cause is in the last part of the handler. The handler does not stop at the
acknowledgement:

```
00f4d8  e8155b        call 0x14ff0
00f4db  b001          mov  al, 1
00f4dd  9a76060080    lcall 8000:0676
00f4e2  833e340100    cmp  word ptr [0x134], 0
00f4e7  7404          je   0xf4ed
00f4e9  ff0e3401      dec  word ptr [0x134]
```

This code runs on each entry, without a condition. **This interrupt is the fine
timebase of the firmware.** Thus, if the rate increases six times, each
countdown that it drives elapses six times faster in emulated time. The dial
sends 5.7x the tone blocks, and the exchange decodes no digits from them.

The two numbers cannot both be correct, and the board is not the item that is
wrong. The same firmware dials on the board at 2,401 Hz, with the same
`dec [0x134]`. Thus the harness has a *second* error, and the 391 Hz rate hid
it. This error is between this countdown chain and the codec-sample clock that
the exchange uses to measure digit lengths. The next task is to find it. It is
now a bounded question, not a guess: one item in the harness is wrong by a
factor of six against a rate that is now certain.

Until then, the default stays at `MODELLED_FRAME_HZ = 391`. The other parts of
the harness agree with this rate. `--frame-hz` gives the comparison again with
one flag:

```sh
./courier run IDSDL302.ROM --with-dsp --exchange \
    --exchange-number 6245=answer --tick-ms 5 --board-id 7 \
    --nvram-fixture idsdl302 --at 'ATDT6245' --instructions 150000000 \
    --summary --frame-hz 2401
```

We keep the wrong rate as the default on purpose, and we record this decision.
The alternative is a harness that is correct about this interrupt but cannot
complete a call. That would replace a number that we know is wrong with a test
bench that does not work.

`0x1e` did not change in the two captures. The `mov ah, al` of the handler
carries some value, but it does not carry it here.

### How it was measured

`courier_emu.cooperative_probe --hook int0` chains this vector in the same way
that the INT3 mode chains the tick. Here the method is easier. The original
offset is **zero**, thus the segment `0x01a0` puts the stub at `0x1a00`. That is
the bottom of the `0x1600`-`0x2b00` region that `AT&T8` does not erase. The full
gap up to the live firmware data at `0x1aab` is free for its 42 bytes. One word
arms the stub, the same word disarms it, and there is no intermediate state.

The stub records `0x1e` and `0x1c` in the order that the handler uses. Thus you
can compare the columns directly with the `and ax,3` that the handler does on
them. Then it does `jmp far
8f46:0000`, thus the firmware services the interrupt exactly as if the vector
had started it directly. This gives the real edge *rate* and the real status
*at* each edge. These are the two numbers that the harness now invents.

This mode refuses the mailbox lanes `0x58`-`0x62`. In other modes, a sample of
these lanes can possibly race the firmware. In INT0 it certainly races the
firmware, because the handler after this stub reads exactly those lanes. If
the stub reads a byte, the handler does not get that byte.

`courier_emu.cooperative_run` drives the full sequence on the board: identity,
vector check, place, verify, arm, stimulus, disarm, read out. The disarm is in
a `finally`. The first hardware run taught it two things:

* **The ring must wrap.** If the ring stops when it is full, it keeps the
  *oldest* entries. At 2,401 Hz, a 1,920-entry ring is 0.8 s. `coop-int0-01`
  became full before the hook closed, and it recorded 1,920 samples of an idle
  mailbox. A ring that wraps keeps the newest entries. A wrap counter adjacent
  to the pointer changes "at least capacity" into the exact interrupt count.
  This is why the 2,401 Hz value is available.
* **A full ring is not a lower bound on other items.** The handler took 15,868
  interrupts, and the ring kept 1,920. We measured the 20 ms cadence across the
  kept window. It is not evidence about the 15.6 s of interrupts that are not in
  the window.

## What the hardware does during a dial-tone wait: almost nothing

`artifacts/coop-int0-cells-01` and `-02`, on the live 403 board, 2026-09-09.
This is the INT0 hook again, but it samples **RAM cells**, not ports. The 403
handler caches the word for the DSP at `[0x183]`/`[0x184]` before it writes
`0x58`-`0x5e`. A co-resident `mov al,[imm16]` cannot disturb a cached word in
the way that an `in` disturbs a mailbox lane. The stimulus was a bare `ATD` on
a connected line. It found dial tone and continued to `NO CARRIER`.

| | window | `7f3f` | `013f` |
|---|---|---|---|
| `-01`, non-wrapping | first 0.80 s: the seizure | 1,917 | **3** |
| `-02`, wrapping | last 0.80 s: after dial tone, into the carrier wait | 1,918 | **2** |

`0x7f3f` is the idle sentinel of the handler (`mov ax, 0x7f3f ; xchg [0x183], ax`).
Thus it means "nothing to send". The only other value that the supervisor put
on the mailbox during a full dial is **`0x013f`, five words, each for one
interrupt only**. There is no burst at the seizure, no burst when it found dial
tone, and no burst when it started the carrier wait.

`-02` also confirms the interrupt rate independently. 8,680 interrupts in
3.62 s is **2,397.8 Hz**. `coop-int0-02` measured 2,401, thus the difference is
0.1%.

### Which settles where the dial-tone report comes from

**The supervisor does not arm anything.** The hypothesis had two parts: a
detector must get a command to listen, and the supervisor of the harness stops
before it sends that command. Both parts are wrong. No command arms a detector
on the board, and the harness already sends the same traffic. On the `ATX2`
dial that fails, the emulated supervisor sends **six** words through this path:
five `013f` and one `1500`. That is the behavior of the board, with slightly
more of it.

Thus the CPU-to-DSP direction is correct, and the dial tone is not lost there.
The data that tells the supervisor that the DSP found dial tone goes **DSP to
CPU**. We measured the 20 ms reply cadence of that direction above, and nothing
in the harness reads it.

### And that leaves one gap, in the resident rather than the plumbing

The real 3.1.2 hears dial tone, and its board continues. We gave the emulated
3.1.2 a known tone through the serial port of the codec and kept all other
items the same. It
[says exactly what it says to silence](board-verified-403.md#answered-the-tone-was-wrong-and-the-resident-does-detect):
134 messages, the same three tags, the same `drr_reads`.

Now we know the two ends of the supervisor side. It sends what the board
sends, and it waits for a report that the DSP of the board clearly produces.
The difference that remains is what the emulated resident *does* with audio that
it clearly receives. That is a question about the C52 core and the detector of
the resident, not about the mailbox.
