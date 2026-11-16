# Where to put a probe on the DSP

The pin numbers are the TI numbers from SPRU056D Table A-4, *Signal/Pin
Assignments for the 'C50, 'C51, and 'C53 in 132-Pin BQFP*. They apply to this
board because the part has the marking **`D17140PQ`**. The TI device table
(page 1-4) gives `PQ` as the 132-pin BQFP package for the 'C50 and 'LC50.

This fact is important by itself. [board-parts.md](board-parts.md) found that
the part is a **'C50 or 'LC50 rather than the 'C52**. (We first wrote the core
for the 'C52.) That document used the memory use of the firmware as evidence:
the `0x23f0` call goes into a 9K SARAM, and `PMST.RAM` and `OVLY` are both set.
The package suffix gives the same result independently: a 'C52 is a **100-pin
QFP**, not `PQ`. Two unrelated methods identify the same part.

## The one pin that settles the mailbox medium

**`IS` - pin 90.**

`IS` is the strobe that selects the I/O space. SPRU056D Table A-8 gives `DS`,
`PS` and `IS` as three space selects on one shared address/data bus. Each
select is "always high unless low level is asserted for communicating to a
particular external space". Thus `IS` goes low for **one thing only**: an `IN`
or `OUT`, or an access to `PA0`-`PA15`. The SRAMs do not use it. They respond
to `DS` and `PS`.

All of the DSP-to-CPU mailbox uses `OUT` instructions. The sender at `0x83eb`
writes to ports `0x5e`/`0x5f`. The stream coroutine at `0x84b7` writes to port
`0x60`. Each of these instructions asserts `IS`.

> * **`IS` (pin 90) routed to the ASIC** - the ASIC decodes the I/O cycles of
>   the DSP. The mailbox is parallel, on the bus that the SRAMs also use.
> * **`IS` unconnected, tied, or going nowhere near the ASIC** - the ASIC
>   cannot see an `OUT`. Thus the mailbox must go to the CPU by a different
>   route. Then the serial reading is correct, and we must find how
>   `out @7d, 0x5e` gets to its destination.

This test is better than a count of the data traces. `IS` is a single pin with
exactly one function, and a meter can show if it connects to the ASIC.

> **Measured, 2026-09-13: `IS` is connected to the ASIC** - at the left edge of
> the package, seven pins up from the bottom corner. The first reading is
> correct. The mailbox is parallel, on the bus that the SRAMs also use. The
> `A0`-`A3` and `A5` lines of the DSP also go to the ASIC. Refer to
> [asic-pinout.md](asic-pinout.md).

The other pins of that group, for context: `DS` 89, `PS` 91, `R/W` 92,
`STRB` 93, `RD` 82, `WE` 83.

## The two serial ports

The second serial port and the "TDM port" use **the same pins and the same
registers**. `TSPC` bit 0 selects the mode. The bit table of SPRU056D gives
`TDM -> 0: TDM port is configured as standard serial port`. This firmware
writes `TSPC = 0x00f8`, with bit 0 clear. Thus the port operates as a usual
second serial port. Two of its pins have two functions. They have their TDM
function only when that bit is set, and here the bit is never set.

| signal | pin | port | what the firmware makes it |
|---|---|---|---|
| `DX` | 106 | primary | codec DAC data - written every sample |
| `DR` | 43 | primary | codec ADC data - read every sample |
| `CLKX` | 124 | primary | **input** (`SPC` `MCM = 0`) |
| `FSX` | 104 | primary | **input** (`SPC` `TXM = 0`) |
| `CLKR` | 46 | primary | input |
| `FSR` | 45 | primary | input |
| `TDX` | **107** | second | **driven constantly** - the one-way stream |
| `TDR` | **44** | second | never read by any instruction |
| `TCLKX` | **123** | second | **output** (`TSPC` `MCM = 1`) |
| `TFSX`/`TFRM` | **105** | second | **output** (`TSPC` `TXM = 1`); `TFRM` only if TDM=1 |
| `TCLKR` | 126 | second | - |
| `TFSR`/`TADD` | 125 | second | `TADD` only if TDM=1, so not here |

### What the board should look like if the firmware is right

You can do a test of each of these items with an oscilloscope or a meter:

1. **The DSP drives `TCLKX` (123) and `TFSX` (105).** `MCM` and `TXM` are both
   set, thus the DSP is the master of that bus. If these pins are quiet, the
   register decode is not correct.
2. **`TDX` (107) changes state all the time.** The idle task writes `TDXR` on
   each pass. **Follow pin 107**: its destination is the device that gets the
   DSP stream. That identifies the far end of the second port, which no test
   has found yet.

   > **Answered, 2026-09-13. `TDX` goes to `J7` pin 2 - a header.** `TFSX` is
   > `J7` pin 6 and `TDR` is `J7` pin 4. `TCLKX` connects to `TCLKR` through a
   > 100 ohm series resistor, which is correct for a clock that goes off the
   > board. The second serial port connects to no part on the board. It goes to
   > the header for instrumentation, and the firmware drives it if a device
   > listens or not. Refer to [asic-pinout.md](asic-pinout.md).
3. **`TDR` (44) is tied or floating.** The receive half is not used, for four
   reasons:
   - `IMR` never enables `TRNT`/`TXNT`.
   - The firmware never reads `TSPC`, thus it never polls `RRDY`.
   - The firmware never reads `TRCV` through MMR addressing.
   - The one direct-addressed candidate at `0xaa4b` is scratch.

   The note in the datasheet says "input pins that are unused may be connected
   to VDD or to an external pullup resistor". If `TDR` is tied high, that
   **confirms that the ASIC cannot send to the DSP on this port**. Then the
   board and the firmware both show that the second port is not the command
   link.
4. **A device that is not the DSP drives `CLKX` (124) and `FSX` (104).** The two
   pins are inputs here. The device that drives them controls the primary bus.
   This is the open question: is it the AC01 in stand-alone mode, or the ASIC?
   On the codec side, this test uses `M/S` on the TLC320AC01**CFN**, pin 18 of
   the **FN** package. That is a different part and a different package from
   the `PQ` of the DSP.

Tests 3 and 4 together find the topology. Test 3 removes the second port as a
candidate. Test 4 shows if the ASIC is on the primary port.


## `TDR` measured driving high and low (2026-09-07)

A probe on the board shows that pin 44 changes state all the time. We must
examine this result carefully, because it does not agree with the firmware in
**both** builds.

### The firmware, re-checked on the board's own image

Most of the disassembly work in this repository used `IDSDL302.ROM`, which is
**DSP 3.0.2**. The board runs **3.1.2**. Thus we did the check again on
`artifacts/courier-board-21210-capture-403/courier-board.rom`, the flash of the
board. Its DSP payload starts at `0x29140` (anchor at `0x2914a`). The
configuration of the second port is identical:

| | 3.0.2 | board 3.1.2 |
|---|---|---|
| `TSPC` writes | `0x0038` then `0x00f8`, at `0x808a`/`0x808c` | **identical** |
| `SPC` writes | `0x0008` then `0x40c8` | **identical** |
| `IMR` | `0x002a` | **identical** |
| `TRCV` reads via MMR | none | **none** |
| `TSPC` reads | none | **none** |

`IMR = 0x002a` is INT2, TINT and XINT. **The ASIC drives `INT2`, DSP pin 39**
(measured, [asic-pinout.md](asic-pinout.md)). Thus the one external interrupt
that the firmware enables is the CPU-to-DSP direction of the mailbox. The value
also does **not** include `RINT`, but the codec receive operates correctly. The
ports are synchronous, thus one interrupt for each frame services the two
halves. Thus "no interrupt enabled" alone does not prove that a port is not
used. For the TDM port, the proof has three independent parts:

- The firmware never enables `TRNT`/`TXNT`.
- The firmware never polls `RRDY`, because it never reads `TSPC`.
- The firmware never reads `TRCV`.

Thus the cause is not a difference in the firmware version. A device drives a
pin that no instruction in the two builds reads.

### Distinguishing `TDR` from `DR` without counting pins

`DR` is **43** and `TDR` is **44**. They are adjacent. `DR` carries the ADC
output of the AC01. It changes state on each frame, all the time, as the
reported measurement shows. An error of one pin, or a different pin-1
reference, gives exactly this result.

The clock is a better discriminator than the pin count:

> Use an oscilloscope to compare the suspect data pin with **`TCLKX` (123)**
> and **`CLKX` (124)**.
>
> * If it is synchronous with **`CLKX` (124)**, an **input** to the DSP, then
>   it is `DR`, and the signal comes from the codec.
> * If it is synchronous with **`TCLKX` (123)**, an **output** that the DSP
>   drives because `TSPC` `MCM = 1`, then it is really `TDR`. Then a device
>   really transmits into the second port.

Also find if `TDR` is only **strapped to `DR`**. Designers frequently tie an
unused serial input to an active adjacent signal, as an alternative to VDD. In
that condition, pin 44 changes state without an address to it.

If the pin passes the clock test, the finding is real and important: a device
transmits to the DSP on a port that this firmware never reads. Then one of
these is true: the ASIC broadcasts on that port and this build ignores it, or
the pin sees traffic for a different device.

## Correction: the board's ring is `0x0bc0`, not `0x0bd0`

We found this during the check above. It is important for the `ARCR` blocker.
The two builds are different:

| | 3.0.2 | board 3.1.2 |
|---|---|---|
| `CBSR1` (`@1a`) | `0x0bd0` | **`0x0bc0`** |
| `CBER1` (`@1b`) | `0x0bdf` | `0x0bdf` |
| ring size | 16 words | **32 words** |
| `lar ar7` at reset | `#0bd0` | `#0bc0` |

`CBCR` is `0x00ef` in the two builds. All text in this repository that gives
"`0x0bd0`-`0x0bdf`" describes `IDSDL302.ROM`. **On the board of the user, the
ring is `0x0bc0`-`0x0bdf`.**


## `TCLKX` and `CLKX` are driven differently - and that is the prediction

A probe shows that the two transmit clocks operate differently. The register
decodes predict exactly this. It also gives a measurement that answers the
`M/S` question **without a probe on `M/S`**.

| pin | signal | `MCM` | direction | driven by |
|---|---|---|---|---|
| 124 | `CLKX` (primary) | `SPC` bit 4 = **0** | **input** | whatever masters the codec bus |
| 123 | `TCLKX` (second) | `TSPC` bit 4 = **1** | **output** | the DSP itself |

Thus they *must* be different. The useful part is that we can predict the
frequency of each clock.

### `CLKX` decides the retraction

If the AC01 is the master, its `SCLK` is "generated internally by dividing the
master clock signal frequency by four" (terminal table of the datasheet,
`SCLK` pin 13 FN). This repository found **MCLK = 2.880 MHz** independently
before. The reset control words `A = 10`, `B = 20` give exactly 7200 Hz
through the rate equation of the part. `B = 19`/`B = 18` give exactly 7578.95
and 8000 Hz. Refer to [dsp-cpu-interconnect.md](dsp-cpu-interconnect.md).
Thus:

> **`CLKX` (124) at 720 kHz** = MCLK/4 with MCLK = 2.880 MHz. Two independent
> methods give the same number, and the AC01 is the master. Thus the ASIC is
> **not** on the primary serial bus, and the retraction in
> `second-serial-port.md` is still correct.
>
> **`CLKX` at a different frequency** - the AC01 does not generate it. The only
> other candidate on that bus is the ASIC.

The same pin gives a second, independent discriminator that does not need a
frequency counter:

> **Continuous or bursty?** An AC01 in master mode divides MCLK by four and
> runs freely. Thus `CLKX` is a continuous 720 kHz square wave at all frame
> rates. A bridge that clocks words across would make **bursts of 16 clocks**,
> one for each frame. Bursty `CLKX` shows that a device moves words on demand.
> The codec does not operate in that mode.

For scale: at 720 kHz, sixteen clocks take **22.2 us**. The frame period is
138.9 us at 7200 Hz, 131.9 us at 7578.95 Hz or 125.0 us at 8000 Hz. Thus an
oscilloscope easily shows the difference between the two conditions: the clock
is busy all the time, or it is busy for about 18% of the time.

### `TCLKX` gives the DSP's core clock, which nothing here has measured

The DSP drives `TCLKX` at **CLKOUT1/4**. The oscillator of the board is
40.320 MHz, thus:

| DSP `CLKOUT1` | `TCLKX` | ratio to a 720 kHz `CLKX` |
|---|---|---|
| 20.16 MHz (oscillator / 2) | **5.04 MHz** | 7x |
| 40.32 MHz (oscillator x 1) | **10.08 MHz** | 14x |

Thus a measurement of `TCLKX` gives the core clock of the DSP directly from the
pin. This repository only inferred that clock before. `CLKMD1` (pin 71) and
`CLKMD2` (pin 103) set the clock mode, if you must confirm the frequency.

> **If `TCLKX` is not driven at all**, the result is different and more
> serious. `TSPC = 0x00f8` sets `MCM = 1` and `XRST = 1`, and the idle task
> writes `TDXR` all the time. Thus the pin must show an active clock. A static
> `TCLKX` shows one of these faults: the `TSPC` decode is not correct, the port
> is not really enabled, or the pin identification is not correct. It would
> also remove the only reason to think that the DSP is the master of a bus.


## `M/S` reported switching, `TCLKX` possibly not driven (2026-09-07)

Two reports point to the same conclusion: **the pin numbering must have a
reference point before we can use any of these results.**

### `M/S` sits between two pins that pulse every frame

| FN pin | signal | I/O | behaviour |
|---|---|---|---|
| 14 | `MCLK` | in | **2.880 MHz** (derived - see below) |
| 15 / 16 | `FC0` / `FC1` | in | tied low if unused |
| 17 | `FSD` | **out** | active-low pulse, one per frame |
| **18** | **`M/S`** | **in** | static master/slave select |
| 19 | `EOC` | **out** | high at ADC conversion start, low at end - **one pulse per frame** |
| 20 | `DGTL GND` | - | DC |

`M/S` is an *input* between two *outputs* that both pulse at the frame rate. An
error of one pin in either direction gives a signal that looks exactly like
"driven high and low". This is the same problem as with `DR` (43) and `TDR`
(44).

**The discriminator is the phase relative to `FS` (pin 12).** `FSD` and `EOC`
are locked to the frame: one pulse for each `FS` period, with a fixed phase, at
7200-8000 Hz. A pin with that lock is one of these two signals. If the suspect
pin changes state *independently* of `FS` (at a different rate, in bursts, or
aperiodically), then it is really `M/S`.

### If it really is `M/S`, that changes the answer

The specification of `M/S` is a static select: "when M/S is high, the device is
the master and when low, it is a slave". Section 2.3 says that the *only*
difference is this: `SCLK` and `FS` are outputs when `M/S` is high and inputs
when it is low. Thus a dynamic drive of `M/S` is exactly the primitive that is
necessary to **time-share the primary serial bus**. The AC01 is the master and
exchanges samples while `M/S` is high. It releases `SCLK`/`FS` to the ASIC while
`M/S` is low.

In that condition, the codec ISR stores each `DRR` word into the ring without
condition. Thus it gets **both** codec samples and ASIC words. That is exactly
the claim that [second-serial-port.md](second-serial-port.md) withdrew, but
through a mechanism that no person had proposed. The ring would then be the
inbound command path. The interconnect would be tied to the `ARCR` ring gate,
and no wide parallel bus would be necessary. The retraction was of the
*argument* (register 6 has no master/slave bit, and that is correct). A
toggling `M/S` pin would be independent evidence for the *conclusion*.

Thus we must examine this carefully and not decide by assumption.

### Anchor the numbering first - two pins do it, and both pay twice

No measurement here confirms pin 1 of either package. If you read a 132-pin
BQFP from the wrong reference, **all** DSP numbers in this file move.

> **AC01 (44-pin PLCC): find `MCLK`, pin 14.** It must be **2.880 MHz**. That
> single reading anchors the numbering of the codec. It *also* independently
> confirms the MCLK value that this repository derived from the A and B
> registers. Thus if a pin reads 2.880 MHz, the number and the numbering are
> both correct.
>
> **DSP (132-pin BQFP): find `X2/CLKIN`, pin 96.** It must carry the board
> oscillator at **40.320 MHz**, the value on the marking of the oscillator can.
> `CLKOUT1` (110) is the other pin that is easy to identify.

Until one of these measurements is done, all pin numbers here are provisional.

### A correction to withdraw first: "the DSP transmits constantly"

An undriven `TCLKX` is less surprising than it first seems. The fault can be in
this repository.

[second-serial-port.md](second-serial-port.md) says that the DSP transmits on
the second port all the time. It gives the measurement "21,976 `TDXR` writes in
one 60,000-instruction sample window". **We took that measurement in the
emulator, and the writer is the idle task at `0x81b7`.** The DSP of the
emulator never goes out of idle. That is the `ARCR` blocker, the subject of
this investigation. Thus the figure shows that the idle task runs all the time
*because the DSP cannot go out of it*. It does not show that the firmware
streams all the time.

On a serviceable board, the DSP does real work and is in that idle task much
less. Thus a quiet `TDX`/`TCLKX` agrees with the firmware. The only part that
does not agree is this: with `MCM = 1`, `TCLKX` must run freely when no data is
transmitted. Thus if `TCLKX` is really static, one of these is true: the pin
identification is not correct, the `TSPC` decode is not correct, or this board
does not start that port.

**This is the same problem as with the codec receive queue and the `TRCV`
scan**: a measurement taken inside the model describes the model.


## Is `M/S` driven by the DSP's `XF`? What `XF` actually does

This is a good hypothesis, and the firmware gives a clear answer. `XF` is
**pin 109** on the DSP. `M/S` is **pin 18** on the AC01. A continuity check
between two named pins shows if they are connected. That is much better than
an argument from a waveform. But the waveform gives the *consequence* in the
two conditions.

### `XF` pulses low on every fourth frame

There are exactly **two** `XF` sites in all of the 3.1.2 resident. They are
both in the codec ISR:

```
8178  ldp  #007
8179  lacc @19            ; data 0x0399
817a  sub  #01
817b  sacl @19            ; decrement, every frame
817c  f788   xc  2, eq    ; ...only when it reaches zero:
817d  be4c   clrc xf      ;    XF low
817e  7718   dmov @18     ;    and reload: DMOV copies 0x0398 into 0x0399
...
8192  be4d   setc xf      ; XF high, every frame, unconditionally
```

The firmware reloads `0x0399`. An earlier reading of this listing did not
include `0x817e`. It read `0x0399` as a free-running 16-bit counter, with `XF`
low once each 65536 frames (about eight seconds). But `DMOV` writes the cell
*after* its operand. Thus each time the count gets to zero, the code fills it
again from `0x0398`. The code sets `0x0398` to **3** once at start-up
(`0x8087`) and never writes it again. We monitored the two cells during a
dialled 403 call (2026-09-26). `0x0399` goes 3, 2, 1, 0 and reloads. The only
writers are `0x817b` and `0x817e`.

Thus `XF` goes low on **every fourth codec frame**, for all of the run:

| frame rate | `XF` low pulses |
|---|---|
| 7200 Hz | 1800 per second |
| 8000 Hz | 2000 per second |
| 9600 Hz | 2400 per second |

Each low period continues from `0x817d` to `0x8192`. That is about 21
instructions, thus about **2-4 us**.

### What that means for each candidate

* **`XF` changes state all the time**, but at a quarter of the frame rate and
  with a duty cycle of a few percent. `EOC` (**19**) and `FSD` (**17**) pulse
  on *every* frame, at 7200-9600 Hz. Thus an oscilloscope can show the
  difference: a pulse on every frame, or a short low on every fourth frame.
* **`XF` cannot be bus arbitration.** A low period of 2-4 us cannot transfer a
  serial bus. One 16-bit frame at 720 kHz alone takes 22 us. Thus, if `XF` is
  the driver, the time-shared bus idea of the previous section is **not
  possible**.
* **`XF` probably does not drive `M/S`.** It would change the AC01 between
  master and slave for a few microseconds on every fourth frame. No serial link
  can operate with that. If the continuity check below finds `XF` on `M/S`,
  this reading of the firmware has an error.

### It also rules out the `slaa006` reading

[dsp-boot-transport.md](dsp-boot-transport.md) says "`XF` is wired to the
codec's `RESET`". That statement comes from the TI reference design `slaa006`.
It cannot apply to this board. A pulse on the `RESET` of the AC01 on every
fourth frame would set its registers back to their defaults (a 16 kHz rate for
a 10.368 MHz MCLK) hundreds of times each second. But the firmware programs
these registers **once**, at reset.

The other known use of `XF` is as the request half of the `XF`/`BIO` handshake
of the boot ROM at `0x0775`. That handshake pairs it with **`BIO` (pin 130)**.
If `XF` goes to a device that is not the codec, the candidate is the ASIC. A
strobe at a quarter of the frame rate also has the correct shape for a
sample-block tick to the ASIC or the CPU. The harness connects `XF` to nothing
on the Courier board.

### The test

> Continuity: **DSP pin 109 (`XF`)** to **AC01 pin 18 (`M/S`)**, and to the
> ASIC. Two named pins, one meter.
>
> On the waveform: a pin that changes state on every frame, at
> **7200-9600 Hz**, is `EOC` or `FSD`. A pin that stays high with a **dip of
> about 2-4 us on every fourth frame** is `XF`.

## The data and address buses, anchored (2026-09-07)

A board observation reports that the DSP connects to the ASIC on its 16 data
pins. Refer to [dsp-cpu-interconnect.md](dsp-cpu-interconnect.md). That record
had no pin numbers, but all other pin claims in this file have them. Here they
are, from the same SPRU056D Table A-4, 132-pin BQFP, that anchors the other
pins.

| signal | pins |
|---|---|
| `D0`-`D7` | 30, 29, 28, 27, 26, 25, 24, 23 - descending |
| `D8`-`D15` | 13, 12, 11, 10, 9, 8, 7, 6 - descending |
| `A0`-`A9` | 55, 56, 57, 58, 59, 60, 61, 62, 63, 64 - ascending |
| `A10`-`A15` | 72, 73, 74, 75, 76, 77 - ascending |
| `IS` / `DS` / `PS` | 90 / 89 / 91 |
| `R/W` / `STRB` | 92 / 93 |
| `RD` / `WE` | 82 / 83 |

The numbering shows two facts. You can check both of them on the board.

**The data bus is one contiguous block: pins 6-13 and 23-30.** The pins between
them are power and reserved pins: `VDDD` 14/15, `VSSD` 20/21, and the
not-connected pins 16-19 and 22. Thus all sixteen data lines go out of the
package from one area of one edge. That agrees with an observation that says
"the 16 data pins". They look like a single group, and no other signals are
among them.

**The address lines and the strobes are on a different edge.** `A0`-`A15` are
55-64 and 72-77. `IS`, `DS`, `PS`, `R/W` and `STRB` are 89-93, immediately
after them. Thus an inspection that shows that the data bus goes to the ASIC
shows nothing about `IS`. That inspection did not look at that side of the
part. For this reason, the data-pin observation cannot show which of these is
true: the ASIC decodes I/O cycles, or the ASIC only monitors the memory bus.
The pin that separates these two readings is far from the pins that we traced.

**Where to put the meter next**, in this sequence:

1. **`IS` (90) to the ASIC.** This is the single decider. It is low for
   `IN`/`OUT` and for `PA0`-`PA15`. It is high for all accesses that the SRAMs
   answer.
2. **`A0`-`A3` (55-58) to the ASIC.** Four lines are sufficient to separate
   `PA7`, `PA14` and `PA15`. If the ASIC has the data bus and `IS` but no
   address lines, it cannot tell the mailbox tag port from the data port. Then
   the programming model in the firmware could not operate as written.
3. **`R/W` (92) and `STRB` (93).** These give the direction and the cycle
   timing. The ASIC needs them to answer a read of `PA7`, and not only to latch
   writes.

Do the `IS` measurement before the other two. If `IS` is not connected, 2 and 3
are not important, and the alias hypothesis becomes the active hypothesis.

**Confirmed electrically (2026-09-07).** We measured `IS` to the ASIC with a
meter. Then we measured the address decode by its effect, not by continuity. A
mailbox frame sent to ports `0x4e`/`0x4f` arrives on the host exactly as a
frame sent to `0x5e`/`0x5f`. A frame sent to `0x6e`/`0x6f` does not arrive.
Thus the ASIC does not decode `A4`, but it decodes `A5`. The pin readings
showed the same result. Refer to `artifacts/dsp-port-fold-01/` and
[dsp-cpu-interconnect.md](dsp-cpu-interconnect.md).
