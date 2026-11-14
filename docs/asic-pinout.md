# Pinning out the NEC ASIC

[board-parts.md](board-parts.md) identifies the ASIC only by its marking:
`NEC USA 1-016-905 9948LV001`. This is a USR part number on a gate array that
NEC made in week 48 of 1999. `1-016-905` is the USR number and `LV001` is the
NEC lot code. The metal layer is custom, thus there is no catalogue part and no
datasheet. Thus we identify the part by its connections. This file records them
from the continuity readings of the owner.

> **These readings are from the 25 MHz Courier 2806.** This is the AC03 board,
> supervisor 7.3.14 / DSP 3.0.13, dumped in
> `artifacts/courier-2806-25mhz-flash-20260912`.
>
> The marking above is **not** from that board. We read it from a photo of the
> **20.16 MHz** unit that runs ID_SDL 4.03d, which
> [asic-port-map.md](asic-port-map.md) probed through the monitor. **No person
> has read the marking of the ASIC on the 2806.** Thus nothing shows that the
> two boards have the same gate array. To read the text on this ASIC is the
> easiest open item here.

## Which findings cross between the boards

> **A third board was added on 2026-09-18.** It is a **2805 ISA internal**
> board, with the same ASIC and the same flash, but we have no slot to run it
> in. Its readings are together in
> [its own section](#the-2805-isa-board---a-third-unit-and-the-first-internal-one),
> not in the tables below. It agrees with them on the memory side, but it is
> different on the panel side. This board caused us to withdraw the flash `CE#`
> claim.


**The DSP side transfers.** [board-parts.md](board-parts.md) shows that stock
7.3.14 runs on the 20.16 MHz AC01 board and on this 25 MHz AC03 board. It also
shows that the **DSP payload is byte-identical on the two boards**: 126,851
consecutive identical bytes, which include the payload and all three overlays.
Code that is identical to this level cannot communicate with two different
interfaces. Thus `IS`, `INT2`, `READY` and the data bus are findings about the
two boards.

**The CPU side does not transfer.** The same comparison finds that all of the
difference between those images is in the supervisor. A different CPU-side
wiring would show at exactly that location. `ALE`, `RD#`, `WR#`, the interrupt
lines and the unconnected `INT0` are findings about the 2806 only.

## Orientation and pin numbering

The part has 120 pins, 30 on each side. The index dot is at the **bottom left**
in the frame of the part, viewed from above with the `NEC USA 1-016-905`
markings upright. Put the part in this orientation before you check any of
these readings again.

We use the JEDEC convention: pin 1 is at the dot, and the numbers go
counter-clockwise in a top view. **The owner confirmed this.** The owner took
the readings and owns the frame in which they were recorded:

| pins | edge | direction |
|---|---|---|
| `1`-`30` | bottom | left to right |
| `31`-`60` | right | bottom to top |
| `61`-`90` | top | right to left |
| `91`-`120` | left | top to bottom |

We took the readings with local numbers for each side. The translation is:

- **top** pin = `91 - N`, counted from left to right
- **right** pin = `61 - N`, counted from top to bottom
- **left** pin = `121 - N`, counted from bottom to top

Three independent checks agree with the direction:

- The bottom-edge readings are on the one edge that we had not read, and on the
  edge where we predicted the panel. If we read the edge clockwise, five of them
  would be on pins that we already measured as the DSP data bus.
- The four upper address lines of the CPU go to four ASIC pins that step over a
  corner supply pair.
- **We read all eight corner pins, and all eight are supplies:**

| corner | pins | | corner | pins |
|---|---|---|---|---|
| bottom left | `120` `GND`, `1` `VCC` | | top right | `60` `GND`, `61` `VCC` |
| bottom right | `30` `VCC`, `31` `GND` | | top left | `90` `VDD`, `91` `GND` |

A corner pad is a supply in *either* direction of numbering. Thus this confirms
the count of 30 on each side, not the direction. But it is correct at all
locations where we checked it, and the inferred bus runs below use it.

Each bare pin number below is an **ASIC** pin. We name DSP pins and CPU pins as
such, because the numbers would be ambiguous.

![The ASIC's pins as currently mapped](asic-pinout.svg)

`tools/draw_asic_pinout.py` generates this figure, and it holds the map as
data. When you add or correct a reading, edit the table here **and** `PINS` in
that tool. Then run the tool again. [board-map.svg](board-map.svg) answers the
other question (which part communicates with which part). It comes from
`tools/draw_board_map.py`, with the same rules.

![The board's parts and the nets between them](board-map.svg)

## What is connected

The tables mark the measured pins. If the measured ends of a bus run are
contiguous and in sequence, we **infer** the remaining pins of the run, and the
tables mark them as inferred.

### Top edge - the address side

| local | pin | signal |
|---|---|---|
| 1 | 90 | `VDD`, shared with DSP pin 15 (`VDDD`) |
| 2-5 | 89-86 | DSP `A0` `A1` `A2` `A3` |
| 6 | 85 | DSP `A5` - `A4` is **not connected** |
| 7-14 | 84-77 | CPU `AD0`-`AD7` |
| 15 | 76 | flash pin 35, `A15` (system `A16`) |
| 16 | 75 | flash pin 13, `GND` - **not** the flash's `CE#`; see the retraction below |
| 17 | 74 | flash pin 34 (`A16`, system `A17`) |
| 18 | 73 | flash pin 3 (`A17`, system `A18`) |
| 19 | 72 | *unread* |
| 20 | 71 | latched `A0` **out** - 74VHC32 pin 12 (`4A`), the low byte lane's term in `U12`'s `WE#` |
| 21 | 70 | latched `A1` **out** - RAM pin 10 and flash pin 11, which are those parts' own `A0` |
| 22-26 | 69-65 | latched `A2`-`A6` **out** *(inferred)* |
| 27 | 64 | latched `A7` **out** - RAM pin 4, which is that part's `A6` |
| 28 | 63 | CPU `A16` **in** - CPU pin 29 |
| 29 | 62 | CPU `A17` **in** - CPU pin 30 |
| 30 | 61 | `VCC` |


Pin `72` is the only pin on this edge that we did not read.

### Right edge - CPU bus control, the DTE, and the telco

| local | pin | signal | CPU pin |
|---|---|---|---|
| 1 | 60 | `GND` | - |
| 2 | 59 | `A18` **in** | 31 |
| 3 | 58 | `A19` **in** | 32 |
| 4 | 57 | `ALE` | 38 |
| 5 | 56 | `WR#` | 37 |
| 6 | 55 | `RD#` | 36 |
| 7 | 54 | *unread* - the prime suspect for the ASIC's own chip select | - |
| 8 | 53 | `INT2`/`INTA0#` | 64 |
| 9 | 52 | `RESIN` **out** - through `R1`, 1k | 68 |
| 10 | 51 | `TXD0` **in** - serial channel 0's transmit | 2 |
| 11 | 50 | `U22` pin 10 (`3B`) | - |
| 12 | 49 | `U22` pin 4 (`2A`) | - |
| 13 | 48 | `U18` pin 11 (`4Y`) - the EIA receiver | - |
| 14 | 47 | `INT1` | 63 |
| 15 | 46 | `U22` pin 2 (`1A`) - **the `RD` net** | - |
| 16 | 45 | `GND` | - |
| 23 | 38 | phone-line header pin 6 | - |
| 24 | 37 | phone-line header pin 5 | - |
| 30 | 31 | `GND` | - |

This edge has three groups: CPU bus control at the top, the EIA-232 interface
of the DTE in the middle, and the telco at the bottom. `ALE`, `WR#` and `RD#`
are adjacent. Pin `54` is between `RD#` and the first interrupt. The decode for
the `0x00`-`0x7f` I/O window would be at that location.

CPU `INT0` (CPU pin 62) is **not connected**.

We did not read eleven pins here: `32`-`36` and `39`-`44`. This is the longest
unread run on the package. The DTE group is above it and the telco pins are
below it.

### Left edge - the DSP's bus, its clock, and the codec's

| local (from top) | pin | signal |
|---|---|---|
| 1 | 91 | `GND` |
| 2 | 92 | DSP `D15` |
| 3-8 | 93-98 | DSP `D14`-`D9` *(inferred)* |
| 9 | 99 | DSP `D8` |
| 10 | 100 | `GND` - the bus-splitting pin |
| 11 | 101 | DSP `D7` |
| 12 | 102 | DSP `D6` |
| 13-17 | 103-107 | DSP `D5`-`D1` *(inferred)* |
| 18 | 108 | DSP `D0` |
| 19 | 109 | DSP `INT2` (pin 39) |
| 20 | 110 | `GND` |
| 21 | 111 | `ADM707` pin 7 - the supervisor's active-high `RESET` |
| 22 | 112 | `AC03` codec pin 14, `MCLK` - the ASIC's **only** line to the codec |
| 23 | 113 | DSP `TOUT` (pin 122) - the DSP's timer output |
| 24 | 114 | DSP `IS` |
| 25 | 115 | DSP `R/W` (pin 92) |
| 26 | 116 | DSP `STRB` (pin 93) |
| 27 | 117 | *unread* |
| 28 | 118 | **DIP switch 3** |
| 29 | 119 | DSP `X2/CLKIN` (pin 96) - **the ASIC clocks the DSP** |
| 30 | 120 | `GND` |

The five measured data pins are in two exact descending runs: `99`-`92` for
`D8`-`D15` and `101`-`108` for `D7`-`D0`. Thus we infer the twelve pins between
them. **Pin 100 is between the two groups.** We predicted a ground between the
two halves of the bus from the shape of the run alone, and then we measured it.

Pin `117` is the only pin on this edge that we did not read.

### Bottom edge - the panel, the DIP switches, the barrier

| local | pin | signal |
|---|---|---|
| 1 | 1 | `VCC` |
| 2 | 2 | DIP switch **2** |
| 3 | 3 | DIP switch **5** |
| 4 | 4 | DIP switch **4** |
| 5 | 5 | DIP switch **10** |
| 6 | 6 | DIP switch **9** |
| 7 | 7 | DIP switch **8** |
| 8 | 8 | DIP switch **7** |
| 9 | 9 | **`DCD`** - `U23` pin 4 (`2A`), the `CD` driver's input; reaches the 2805's UART `DCD` (pin 59) |
| 10 | 10 | **`CTS`** - drives the `CS` (Clear to Send) lamp here; reaches the 2805's UART `CTS` (pin 60) |
| 11 | 11 | **`RI`** - `U23` pin 10 (`3B`); reaches the 2805's UART `RI` (pin 61) |
| 12 | 12 | **`DSR`** - `U23` pin 2 (`1A`); reaches the 2805's UART `DSR` (pin 62) |
| 13 | 13 | `AA` lamp |
| 14 | 14 | `ARQ` lamp |
| 15 | 15 | **Talk/Data** switch |
| 16 | 16 | `HS` lamp |
| 17 | 17 | `SYN` lamp |
| 18 | 18 | `TR` lamp - **and the 2805's UART `DTR` (pin 50) lands here**, which is a direction conflict; see the 2805 section |
| 19 | 19 | optocoupler `U14` pin 5 - the line-side barrier |
| 20 | 20 | DIP switch **6** |
| 21 | 21 | `AA` lamp, **second pin** |
| 22 | 22 | optocoupler `U16` pin 5 - the line-side barrier |
| 24 | 24 | `GND` |
| 25 | 25 | `RS` lamp |
| 27 | 27 | `MR` lamp |
| 29 | 29 | phone-line header pin 12 |
| 30 | 30 | `VCC` |

On the bottom edge, the local numbers and the absolute numbers are the same. We
did not read `23`, `26` and `28`.

**`AA` connects to two pins**, 13 and 21, but the firmware drives one bit
(`0x14` bit `0x10`). The cause can be a double drive for lamp current, a sense
return, or two nets with the label `AA` that the reading merged. This is not
resolved yet. But the 2805 section below gives more data: 13 is on the same
copper as pin **43**, and a SOT-23 transistor is between that net and 21.
## The part is a memory controller

**The ASIC latches the low address byte of the CPU.** An 80C186EB multiplexes
`AD0`-`AD15` and drives `A16`-`A19` separately. The one `74VHC573` on the board
latches the high byte (`'573` pin 9 is `D7`, CPU pin 11 is `AD8`). No other part
on the board latches the low byte, but the flash and the SRAM both need it. ASIC
pin 70 goes to RAM pin 10 and to flash pin 11. Both of these are `A0` on those
parts:

| ASIC pin | system address | where it goes |
|---|---|---|
| 71 | `A0` | '32 pin 12 - byte lane, never reaches a memory |
| 70 | `A1` | RAM pin 10, flash pin 11 - those parts' `A0` |
| 69-65 | `A2`-`A6` | *inferred* |
| 64 | `A7` | RAM pin 4 - that part's `A6` |

Eight consecutive pins carry the eight bits latched from `AD0`-`AD7`. Thus the
memory address bus comes from three sources: `A0`-`A7` from the ASIC,
`A8`-`A15` from the '573, and `A16`-`A19` from the CPU. The exception is the top
three lines of the flash, which also come from the ASIC.

**Each address label at the memories is shifted by one.** On a 16-bit bus, `A0`
selects the byte lane and never goes to the address pins of a memory. Thus the
`A`n of each part is system `A`n+1. `BYTE#` is tied high, thus the flash is in
word mode. This confirms the shift, and it is not only an inference: `A0`-`A17`
address 256K words, which is the 512 KiB that the dump measures.

**The SRAM pair is one 32K x 16 bank.** The two `CE#` pins are connected
together, and the two `OE#` pins are connected together. Only the write enables
are separate:

```text
U12 WE#  =  ASIC pin 71 (A0)  OR  write strobe      - low byte lane
U4  WE#  =  CPU BHE# (pin 39) OR  write strobe      - high byte lane
```

`'32` pin 13 is flash pin 43, `WE#`, the board write strobe. `'32` pin 10 is CPU
pin 37, `WR#`. The two lane terms are different because the bus is different
for each lane. `A0` comes latched from the ASIC, because `AD0` is multiplexed
and no other part holds it. `BHE#` comes raw from the CPU, because it is a
dedicated pin on the 80C186EB. We did not read gates 1 and 2 of the '32.

**The CPU makes its own SRAM select**, and it is `LCS` (pin 60). An earlier
record put both `LCS` and `UCS` on the common `CE#` net, but both cannot be
correct. Later we found that `UCS` holds the `CE#` of the *flash* (refer to the
retraction below). Thus `LCS` is on the SRAM, and that error of one pin is
closed. `LCS` is programmed to `0x00000`-`0x20000`, low memory from zero, which
is the correct location for the SRAM.

> **Retracted 2026-09-18. The ASIC does not select the flash. `UCS` selects
> it.** ASIC pin 75 goes to flash pin **13**, `GND`, not to flash pin 12. Three
> items agree, and no item now disagrees:
>
> * **A second board.** The 2805 ISA board has the same `1-016-905` ASIC and the
>   same `PA28F400`. On it, pin 75 meters to flash 13, flash 13 meters to
>   ground, and flash 12 (`CE#`) meters to **CPU pin 61, `UCS`**. The other pins
>   of the edge transfer exactly: `70` to flash 11 *and* RAM 10, `73` to flash
>   3, `74` to flash 34, `76` to flash 35. If four pins agree and one pin does
>   not agree, that is a reading error, not a bond-out difference.
> * **The firmware.** The single job of the reset stub is to program `0xFFA4`
>   (`UCS_START`) to `0x8000`. This gives a `UCS` window of `0x80000`-`0xffc00`,
>   512 KiB, which is exactly the flash. The two images do this: stock 7.3.14
>   and `IDSDL302.ROM`. There is no reason to program `UCS` to the size and
>   location of the flash if `UCS` does not select the flash. Read it with
>   `CourierRom.chip_selects()`.
> * **This file did not agree with itself.** It recorded `LCS` (60) and `UCS`
>   (61) both on the common `CE#` net of the SRAM pair, but both cannot be
>   correct. `UCS` on the flash resolves this: `LCS` selects the SRAM. Thus the
>   open probe that asked which of the two answers is closed.
>
> The same region already had one error of one pin: the "74 is pin 3 or pin 34"
> conflict, recorded above as one pin counted incorrectly. This is the second
> error.
>
> We keep the paragraph and the table below as written, because the address
> readings still support their reasoning. We withdraw only the `CE#` row and the
> conclusion that came from it.

**And the ASIC selects the flash.** Flash pin 12, `CE#`, comes from ASIC pin 75.
`UCS` is the upper chip select of the 80186. It is active at reset and gets the
first instruction, and on this board it does not go to the boot device.

| flash pin | flash's name | system address | from ASIC pin |
|---|---|---|---|
| 11 | `A0` | `A1` | 70 |
| ... | `A1`-`A6` | `A2`-`A7` | 69-65 *(inferred)* |
| 4 | `A7` | `A8` | 64 |
| 35 | `A15` | `A16` | 76 |
| 34 | `A16` | `A17` | 74 |
| 3 | `A17` | `A18` | 73 |
| 12 | `CE#` | - | ~~75~~ - **CPU pin 61, `UCS`**; ASIC 75 is `GND` |

The ASIC supplies the bottom eight address lines and the top three address
lines of the flash. The '573 supplies the middle lines. Thus the two parts
supply all of the address bus of the flash. But **the select comes from the
CPU**, thus the last sentence of this section before the retraction is not
correct. The readings show that the ASIC is the **address latch** of the board,
for the two memories and for all of the bus. The next section opens again the
question if it is more than that.

### The fold: four address lines in, three out

The four upper address lines of the CPU arrive together, on four ASIC pins that
step over the corner supply pair at `61`/`60`:

| CPU pin | line | ASIC pin |
|---|---|---|
| 29 | `A16` | 63 |
| 30 | `A17` | 62 |
| 31 | `A18` | 59 |
| 32 | `A19` | 58 |

**Four lines go in and three lines go out.** That is exactly what a **flat** map
needs. Thus this is no longer evidence of paging.

`UCS` decodes `0x80000`-`0xfffff`. Thus, in the window of the flash, system
`A19` is always 1. The flash never needs it. In word mode, the `A0`-`A17` of the
part carry system `A1`-`A18`, and the ASIC sends exactly those top three: system
`A16`, `A17`, `A18`. The fourth input line, `A19`, tells the ASIC that the code
addresses the flash region. There is no reason for it to go out. Four in and
three out is a **pass-through, and the decode uses `A19`**. It is not a fold.

Thus the argument from "the decode uses one bit" to "thus there is paging" is
**not correct**. Also, with `CE#` on `UCS` and not on the ASIC, the reading of
the part as a memory controller loses its other support at the same time.

**Also, paging is not possible.** `UCS` decodes `0x80000`-`0xfffff`: 512 KiB,
which is all of the `PA28F400`. Paging means access to a large device through a
*smaller* window. The retracted text said exactly that: "a 512 KiB device
reached through a smaller window". But the window is not smaller. The CPU
addresses each byte of the part directly. Thus we do not only lack evidence for
a paging register. A paging register would have no function.

**We cannot yet explain `A19`.** It goes to the ASIC on the two boards (pin 58,
CPU pin 32, metered on the 2806 and the 2805). With `UCS` on `CE#`, the ASIC
does not need it to gate a signal. A usual answer is that the ASIC uses it to
qualify its own address outputs, so that they go to tri-state outside the flash
region. That answer needs no register. This is a guess about *why* the line is
there, not a measurement, and it is the one open item that this retraction
leaves. The position now is simple:

- No person has identified a port bit as a paging register.
- No part of `courier_emu` pages the flash.
- The flat 512 KiB image of the harness gives the same behaviour as the two
  boards.
- The flat map explains the observation that supported paging before.

We must still say why the high address lines go through a gate array and are
not latched with the other lines. The board layout, and the fact that the ASIC
already holds `A0`-`A7`, are sufficient answers. Neither answer needs a
register.

### The memories sit on the CPU's raw `AD` bus

Flash pin 22 (`DQ11`) goes to CPU pin 20 (`AD11`). Flash pin 31 (`DQ15`) goes to
CPU pin 28 (`AD15`). These are two data lines, one from each byte, that go
directly to the matching multiplexed bus line, with no part between them.

Thus the flash and the SRAM pair connect directly to `AD0`-`AD15`. They do their
own address/data separation from the strobes. There is no buffer and no
transceiver. The ASIC has only `AD0`-`AD7`, as an **input**, for the latch. The
two parts are on the same wires for different reasons. The 8-bit CPU port of the
ASIC shares the bus with a 16-bit memory system. It is not in front of that
system.
## The part is the DSP's entire external interface

**The ASIC is a 16-to-8 width converter.** All sixteen DSP data lines go to the
package. Only eight CPU lines go to it. `AD8`-`AD15` go to the SRAMs of the CPU
and do not go to the ASIC. Thus the ASIC gives a **16-bit port to the DSP and an
8-bit port to the CPU**, and this part does the conversion.

The 16-bit half is a DSP-side finding and transfers to the two boards. The 8-bit
half is a CPU-side finding and does not transfer. This is important for the
question that it appears to answer. [asic-port-map.md](asic-port-map.md) reads
the 64 odd ports of the probe, which return `0x00`, as the undriven upper byte
of a 16-bit register. An 8-bit CPU interface would replace that reading with
"there is nothing at that address". But we did the port sweep on the 20.16 MHz
board and this trace on the 2806. Thus this is a candidate, not a replacement,
until someone reads the marking of the 2806.

**The two directions of the mailbox are physical.** `IS` (DSP pin 90) on ASIC
`114` gives the DSP-to-CPU direction. The I/O strobe of the DSP goes to the
ASIC. Thus `out @7d, 0x5e` at `0x83eb` and the writes of the stream coroutine
to port `0x60` arrive in this chip. `INT2` (DSP pin 39) on ASIC `109` gives the
other direction. It is the interrupt that the firmware arms:
[dsp-pin-probes.md](dsp-pin-probes.md) records `IMR = 0x002a`, which unmasks
`INT2`, `TINT` and `XINT`.

`R/W` on `115` and `STRB` on `116` complete the group. The ASIC can identify a
DSP read and a DSP write, and it has the strobe for the timing. Thus the mailbox
is not write-only, and the polling loop has a physical read path. With `IS` and
the sixteen data lines, the ASIC has the **complete external bus control
group** of the DSP. The SRAM pair is the only other device on that bus.

**`READY` is tied high, thus all wait states come from software.** DSP `READY`
goes to `VDDD`. The C5x samples it to make an external access longer. Thus no
device on either bus ever makes a DSP cycle longer, and this includes the ASIC.
All timing comes from the software wait-state generator of the DSP.
[hardware-timebase-and-audio-path.md](hardware-timebase-and-audio-path.md) uses
this as a reference. This removes an option: the ASIC is **not** a bus arbiter
and cannot slow the DSP. If a mailbox read is not ready, the software must poll,
because the hardware cannot make the DSP wait.

### The ASIC generates both timebases in the audio path

**ASIC pin 119 goes to DSP pin 96, `X2/CLKIN`.** This is the external clock
input of the DSP. It is not pin 97 `X1`, which carries a signal only when a
crystal connects across it, and this board uses a clock can. **The clock of the
DSP comes from the ASIC.**

This fact is of a different type from the other facts in this file. All other
pins carry signals that the firmware changes. This pin sets the rate at which
the DSP executes all code. The `ECLIPTEK EC11 40.320M` can is the one
oscillator of the board, and it supplies the CPU. The DSP gets the clock that
the ASIC makes from it. Thus the ASIC can divide, gate or stop the clock of the
DSP. No part of this repository considered that the machine cycle of the DSP
can possibly change. A fixed divide is the most probable, and we checked the
timing numbers of the firmware against a real board. But this was an
assumption, not a known fact.

**ASIC pin 112 is the `MCLK` of the codec** (`AC03` pin 14). We know this value,
not from an oscilloscope but from the firmware.
[ac01-codec-protocol.md](ac01-codec-protocol.md) calculates it from the divider
registers of the codec. The DSP writes `A = 10` and `B = 20`, and the datasheet
equation `fs = MCLK/(2AB)` applies. Three sample rates that we found
independently all give **MCLK = 2.880 MHz**. This is exactly `40.320 / 14`.
Thus the divider in the ASIC is 14, and the pin reading confirms the path of the
clock.

This is correct on the two boards. The 25 MHz crystal of the 2806 supplies
**only the CPU**. The ASIC uses the same 40.320 MHz can on the two boards. Thus
the `MCLK` of the codec and the clock of the DSP do not depend on the board.
That is why the DSP payload can be byte-identical on the two boards while the
supervisors are different. Refer to
[running-the-25mhz-image.md](running-the-25mhz-image.md).

`MCLK` is more important for the codec than for the DSP, because the conversion
rate is divided from it. The reference point of the datasheet is "a 16-kHz
data-conversion rate and 7.2-kHz filter bandwidth for a 10.368-MHz master
clock". If `MCLK` changes, all of those values change. The sample rate is
over-determined and safe. But we now know that the divide that makes it is
**inside a part with registers**.

### The DSP's timer output comes back to the ASIC

Pin `113` is DSP pin 122, **`TOUT`**, the on-chip timer output of the C5x. Pin
`119` drives `CLKIN`. Thus the clock relationship goes in the two directions:
the ASIC clocks the DSP, and the timer of the DSP sends a signal back into the
ASIC.

That is a periodic hardware signal that goes to the part that generates the CPU
interrupts. This repository has an open question with exactly that shape.
[machine.py:596](../courier_emu/machine.py) describes `INT0` as "the board's
frame edge" and says "nothing on the CPU side produces that edge". A ROM run
supplies a replacement for it.

**This is only a candidate now**, and there is a specific problem. CPU `INT0`
(pin 62) is not connected on this board. Thus the signal from `TOUT` does not
go to that pin. One of these is true: the edge comes in on `INT1` or `INT2`, the
`INT0` reading is not correct, or `TOUT` does not carry the frame edge. **The
period of `TOUT` will give the answer.** If it is the same as the 5 ms tick that
the harness models, or the frame rate of the mailbox, the identification is
complete. Put an oscilloscope on DSP pin 122.

### The codec is the DSP's, not the ASIC's

| `AC03` pin | name | direction | DSP pin |
|---|---|---|---|
| 11 | `DOUT` | out of the codec - ADC results | 43 |
| 10 | `DIN` | into the codec - DAC data and commands | 106 |
| 12 | `FS` | frame sync | 104 |

Those DSP pins are immediately next to pins that we already identified: `TDR`
on 44, `TFSX` on 105, `TDX` on 107. The two serial ports of the C5x are
interleaved on the package in this pattern. Each of the three readings is next
to its predicted neighbour.

Thus the serial interface of the codec goes to **the serial port of the DSP,
with no ASIC between them**. The single line from the ASIC to the codec is the
master clock. **This does not agree with an existing claim.**
[board-parts.md](board-parts.md) says that the ASIC is in front of the codec,
and that it thus hides the AC01/AC03 difference from the DSP. That cannot be
correct. Two boards run byte-identical DSP payloads with different codecs, but
that is not the explanation.

### The speaker is not on the board side

We tried two times to find the gate of the speaker here, and we withdraw the two
readings:

- The two optocouplers are **not** the gate. `U14` and `U16` are `H11B2`
  photodarlingtons, and the ASIC is on their transistor side. Thus the ASIC
  receives through them. Also, a darlington opto is slow and not linear. The
  audio that a call-progress speaker needs is already on the logic side of the
  barrier.
- A later reading put the speaker on the `MON OUT` of the codec, with register 4
  bits `DS05`-`DS04` as its volume: squelch and three gains, for an `AT` command
  set with exactly four states. That reading was **not measured**, and we
  withdraw all of it.

We know where the speaker is *not*. A direct drive of ASIC port `0x00` bit
`0x40` and bit `0x04` on the 20.16 MHz board makes no sound, on hook or off hook
([board-verified-403.md](board-verified-403.md)). Thus a sweep of CPU ports
could not find it. The live paths are on the DSP side.
[2806-codec-mailbox-control.md](2806-codec-mailbox-control.md) traces them:

- Mailbox tag `0x0f` sets a gain for a scaled copy of the ADC sample to ASIC I/O
  `0x50`.
- The `M` handler of the CPU drives a latch on port `0x12` mask `0x10`, with two
  conditional `L` paths on masks `0x20` and `0x40`.

On that board, RAM `0x0693` read `0x22`. This sets the monitor gain to zero, and
the direct volume writer returns without a write. Thus neither programmable path
was active.

**We have not yet identified the physical speaker circuit.** Do not use codec
word `0409` and the register-4 monitor bits to say that the speaker connects to
`MON OUT`. No person measured that connection.

### The DSP and the codec share one reset net

DSP `RS` (pin 127) does not come from the ASIC. It goes to pin 8 of the codec,
`RESET`. The harness drives that net from bit 1 of `0xFF56`, and it models
**only** the DSP side. [machine.py:2384](../courier_emu/machine.py) floats the
transfer interface of the DSP and sets `_dsp_in_reset`, but nothing occurs to
the codec. On the board, each of those pulses also resets the codec. The reset
conditions of the datasheet set its registers back to the defaults. Thus all
codec state that the firmware set before a DSP reset is lost after the reset,
and the harness does not know that.

## The reset tree

| part | reset source | how |
|---|---|---|
| the **ASIC** | `ADM707` pin 7 | active-high power-good reset, into ASIC pin `111` |
| the **CPU** | the **ASIC**, pin `52` | through `R1` (1k) into `RESIN`, CPU pin 68 - *not* the `ADM707`, whose pin 6 is unconnected |
| the **DSP** and the **codec** | the **CPU**, in software | `P1LTCH` (`0xff56`) bit 1 = `P1.1` = **CPU pin 58**, one net to DSP `RS` (pin 127) and the codec |

Thus the boot sequence is not an inference:

1. The rails come up. The `ADM707` releases the **ASIC**.
2. The ASIC releases the **CPU**.
3. The firmware of the CPU releases the **DSP** and the codec.

Each part stays in reset until the part that it needs is ready. The ASIC holds
the `CE#` of the flash, and thus it decides if the first instruction fetch of
the CPU can succeed. By construction, the ASIC comes out of reset first.

**Both ends of the DSP reset are confirmed.** The harness drives
`DSP_RESET_PORT`/`DSP_RESET_BIT` ([machine.py:54](../courier_emu/machine.py)),
bit 1 of `0xff56`. That is `P1.1`. The board puts DSP `RS` on CPU pin 58. The
port-pin arithmetic predicted that pin. We recovered the model from the
firmware, predicted a pin from it, and read that pin on the board.

The asymmetry has three consequences:

* **The CPU must run before the DSP.** Only the CPU can take the DSP out of
  reset. Thus the wiring sets the boot sequence. It is not a decision of the
  firmware.
* **We do not know what holds the DSP at power-on.** The port pins of the
  80186EB come out of reset in their chip-select function, not as driven GPIO.
  Thus the level on that net during the first microseconds depends on the
  default of `P1CON` and on the pull resistor on the board, if there is one. If
  the net floats high, the DSP is *released* before the CPU has loaded data into
  its RAM.
* **There are two methods to stop the DSP.** This net is the documented method.
  The other method is the clock, which comes from the ASIC. A part that supplies
  the clock of a different part can stop it without a reset.

**Examine the 1k series resistor.** If a gate array drives the reset of a
processor through a resistor, the resistor is there for damping, or to let a
different source override the node. With 1k in series, a device that pulls
`RESIN` low at the CPU end wins without contention. This is the standard method
to let a reset button or a debug header assert reset on a line that a chip
already drives. The other connections on CPU pin 68 will show which of these is
correct.

### And it retires an explanation the repository was relying on

[ram-probe-delivery.md](ram-probe-delivery.md) says that the **1.6 second
watchdog** of the `ADM707` causes a measured limit of about 1.5 s on each probe
run, "which matches the observed bound". **The owner reports that this board
uses the `ADM707` only as a power-good reset.** Thus there is no `WDI` source to
find, and no watchdog is in use.

This is the status of the claims:

* **The observations are correct.** Cleared RAM, a restored vector, and `AT`
  that answers again: we measured these many times.
* **The reboot path of the firmware is correct.** That file shows that the
  firmware clears RAM and builds the IVT again. The state after the run looks
  like that.
* **We do not now know the trigger.** An item stops those runs after about one
  and a half seconds, and it is not the watchdog of this part.

These are the candidates:

- A **software** failsafe in the supervisor that sees that another code has
  taken the vector of timer 0. This needs no hardware, and it agrees with a
  firmware that builds its own IVT again.
- The **ASIC**, which is in the reset tree and gets timer signals.

You can prevent a software reboot if you cooperate with the firmware. That file
already recommends that route for other reasons.

A datasheet number that agrees with an observation is a good clue but a bad
proof. Because of the 1.6 s coincidence, no person examined this further.

## The panel and the DTE interface

**The ASIC drives the front-panel LEDs.** We mapped the lamps long before this
trace. [dsp-rom-probe.md](dsp-rom-probe.md) has the table for each bit, which we
measured when we drove single bits and monitored the panel.
`courier_emu/panel.py` models the latch driver. This trace adds **the part that
contains the latches**. Before, no document connected the panel to a part.

This is important because the panel is the only output of this system that a
person can read without instruments. All other observations need the monitor at
its command loop, a flash dump, a port sweep or a meter. The panel continues to
operate in the states that those methods cannot get to:

- the outage across a reset, which [asic-port-map.md](asic-port-map.md)
  documents as a structural limit of the monitor
- a call in progress
- a training sequence that stops

**The transceivers**: two **SN75188** quad line drivers, `U22` and `U23`, drive
the outputs. One **`DS1489AM`** quad receiver, `U18`, receives the inputs. This
is the 1488/1489 pair, and we found it one half at a time.

| `U18` output | pin | goes to | CPU pin | what the DTE sends |
|---|---|---|---|---|
| `1Y` | 3 | CPU `RXD0` | 3 | `TXD` - the DTE's data |
| `2Y` | 6 | CPU `CTS0` | 1 | `RTS` |
| `4Y` | 11 | ASIC pin 48 | - | `DTR`, most likely |
| `3Y` | 8 | *unread* | - | - |

**The DTE is on serial channel 0.** The transmitted data of the DTE arrives at
`RXD0`. `courier_emu/uart.py` models this: its `EbSerial` docstring says
"Serial port 0 of the 80C186EB".

**`CTS0` is a real pin, but the harness makes a false value for it.** `uart.py`
models `clear_to_send` as a replacement and sets it with each delivered
character. Its own comment says that the chain "is reached by the right bit for
the wrong reason". The `RTS` of the DTE comes through `U18` gate 2 to CPU pin 1.
This is a specific harness item with a target that we know is correct.

**The transmit path is asymmetric, and this is intentional.** The receive data
comes to the CPU directly from the receiver. The transmit data goes out of the
CPU on `TXD0` (pin 2) into ASIC pin 51, and ASIC pin 46 supplies the `RD`
driver. The data of the DTE goes to the CPU without change. The data of the
modem to the DTE goes through the gate array. A part that is on only one
direction is there to do something to that direction. The obvious candidate is
to gate the receive line during handshake or retrain. **No person has
identified a port bit for it.**

### Which panel signals are in the ASIC, and which are not

The handshake lines are in the ASIC, and the data lines are not:

| signal | where | |
|---|---|---|
| `CD` | ASIC pin 9 → `U23` pin 4 (`2A`) | out to the DTE, latch at `0x10` bit 0 |
| `RD` | ASIC pin 46 → `U22` pin 2 (`1A`) | out to the DTE |
| `CS` | ASIC pin 10 | out to the DTE, **no established port** |
| `TR` | ASIC pin 18 | follows the DTE's `DTR`, read at `0x12` bit `0x40` |
| `RS` | ASIC pin 25 | follows `RTS`, **which has no port at all** |
| `SD` | 74AHC04 between CPU pins | **not on the ASIC**; the group reading is retired |
| `OH` | RA5W-K relay, pin 9 | not on the ASIC |

Thus each modem-to-DTE signal that goes out through a 75188 also goes through
the ASIC. Six driver inputs are used: `U22` gates 1-3 and `U23` gates 1-3. Gate
4 is not used on either part. These six inputs carry five signals (`RD`, `CD`,
`CTS`, `DSR`, `RI`). Thus one more signal goes through than we named, or one
gate is spare. We cannot yet account for `DSR` and `RI`.

On a 1488/75188, gates 2 and 3 have two inputs each, and the ASIC is on `3B`.
The signal on `3A` is not from the ASIC. It is an enable level, or a second
source that gates that output. Read that pin before you assign a signal to the
gate.

**This explains a failure that the harness records.**
[board-verified-403.md](board-verified-403.md) shows `CS`, `RD` and `AA` change
after `SELF TEST COMPLETED`, without a panel write near that point. The three
lamps have three *different* mechanisms:

- `AA` is a latch bit that the firmware writes.
- `CS` is an ASIC pin with no port behind it.
- `RD` follows the input of the 75188.

A model that makes the panel follow the serial signals must do this for each
lamp separately.

`RD` is the only remaining lamp that does not go to the package. Probe it again
from `U22` pin 2 back to the ASIC before you use that distinction. The same
reading was already incorrect two times for `CD`.

## The line side

**We found the isolation barrier, and the ASIC is on the receiving side.** Pins
`19` and `22` go to pin 5 of the optocouplers `U14` and `U16`. These parts are
`H11B2` photodarlingtons: LED in, transistor out. Pin 5 is on the transistor
side. Thus **the ASIC is on the output side of the two barriers: it receives, it
does not drive.** If the pin is the collector, the base or the emitter, that
changes the bias of the pin. It does not change the direction of the signal.

Two isolated inputs from the line is a usual shape. A modem of this period
brings **ring detect and loop-current sense** across as logic. The firmware side
already has one of them named: ring sense, port `0x14` bit 1.
[daa-line-interface-2016mhz.md](daa-line-interface-2016mhz.md) describes a
cadence machine that samples it from a 5 ms ticker. One of `19` and `22` is very
probably its physical source.

**The phone-line header is a module interface, not a line connection.** It has
a minimum of **twelve** positions, and three ASIC pins go to it: `37`, `38` and
`29`. Tip and ring do not need twelve pins. With the two optocouplers, that is
five line-side pins on two edges. We have not identified the module on the far
side, and this is the largest subsystem that we have not mapped.

An earlier reading paired `37`/`38` as the hook drive and the ring sense. That
reading assumed that there were exactly two line-side pins for the two
line-side signals with ports. But there are five, and an opto is a better
candidate for ring detect. We do not know what the header pair carries.
## The DIP switches

Ten positions, and they are read two different ways:

| switch | where |
|---|---|
| 1 | **CPU pin 80** (`P2.6`), read in `P2PIN` at `0xff5a` bit `0x40` |
| 2, 4-10 | ASIC bottom-edge pins 2-8 and 20 |
| 3 | ASIC pin **118** |

| ASIC pin | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 20 |
|---|---|---|---|---|---|---|---|---|
| DIP switch | 2 | 5 | 4 | 10 | 9 | 8 | 7 | 6 |

Pins `5`-`8` are a clean descending run - switches 10, 9, 8, 7. The rest is
scrambled relative to pin order, so **whichever port bit the firmware reads a
switch in is not positional** and that mapping has to come from the firmware.
Pin 20 sits away from the group, among the lamps, and is the one entry worth a
second reading.

**`P2PIN` bit 6 is not modelled.** `machine.py` models bit 7 as the 93C66's data
line and bit 5 as the serial receive the ROM's autobaud timer samples
([machine.py:2340](../courier_emu/machine.py),
[machine.py:2345](../courier_emu/machine.py)); a read of bit 6 returns whatever
the emulated register happens to hold rather than a switch position. (A comment
near that code calls `ff5a` an "ASIC latch". It is not - `0xff5a` is the
80186EB's own `P2PIN`. The behaviour is unaffected; the name is wrong.)

**Switch 1 is the DTR override, and two firmware families read it elsewhere.**
The owner reports its function: off is DTR normal, on is DTR always asserted.
That raises the possibility that `P2.6` carries the DTR *signal* rather than the
switch, since shorting the sense line to its asserted level gives the same
behaviour with no firmware involvement. The behaviour cannot distinguish them.
But `courier_emu/panel.py` maps `dtr-override` to ASIC port `0x12` bit `0x20` on
the XMF supervisor (recovered at `0x63d31`/`0x63d48`), and the 302/403 ROM
builds read the same switch on the same port bit through a different selector.
So on both firmware families mapped so far it is a strap the firmware reads
through the ASIC. If the 2806 routes it to `P2.6` instead, that is a **third**
switch wiring - not impossible, but it needs more than one continuity reading.

**The strap scan is real but it is not these switches.** `panel.py`'s
`id-strap-drive-a`..`d` and `id-strap-sense` are a four-drive, one-sense matrix
recovered from the supervisor's scan at `0x5bfc6`:

| line | port | bit | driven at |
|---|---|---|---|
| `id-strap-drive-a` | `0x14` | `0x40` | `0x5bfed` |
| `id-strap-drive-b` | `0x12` | `0x02` | `0x5c001` |
| `id-strap-drive-c` | `0x14` | `0x10` | `0x5c015` |
| `id-strap-drive-d` | `0x14` | `0x20` | `0x5c03d` |
| `id-strap-sense` | `0x14` | `0x08` | *read* |

Four drives and one sense read four **board-ID straps**, read once at boot - a
different physical thing from the DIP bank, which this file had folded into it
because both were unread. Eight switches on eight dedicated pins is not a
matrix; four drive lines exist to save pins and this part spent the pins. The
arithmetic now closes: ten switches, one on the CPU, nine on the ASIC.

### The unpopulated four-switch footprint

The owner reports room for a second DIP bank of four, unpopulated, near the
serial connector, and suggested it might select between the CPU's two serial
channels.

**One probe killed it: CPU pin 8, `TXD1`, is not connected.** A UART channel
whose transmit pin goes nowhere is not a port, so the CPU's serial channel 1 is
unused and there is no second serial path to select between.

What remains is a coincidence rather than a mechanism - a spare receiver channel
(`U18` `3Y`), two spare driver gates (`U22` and `U23` gate 4) and an unused UART
are all real and none are wired to each other. Spare gates on a quad part are
ordinary. The footprint is something else, and what is left to probe is its own
pads, against the three unread bottom-edge pins and against ground, since the
populated bank's common is grounded.

**A bank that reroutes a signal needs no port bit at all**, which is the shape
of the owner's suggestion and the shape that would leave no trace in the image.
`panel.py` names eight option switches the supervisor reads against ten wired
positions, so two already move no bit the firmware looks at.

## The second serial port goes to a debug header

This is the question [dsp-pin-probes.md](dsp-pin-probes.md) posed and could not
answer: `TDX` is driven constantly by the idle task and nothing accounted for
where the data went.

| DSP signal | DSP pin | lands on |
|---|---|---|
| `TDX` | 107 | `J7` pin 2 |
| `TDR` | 44 | `J7` pin 4 |
| `TFSX` | 105 | `J7` pin 6 |

It is not wired to any part on the board. It is brought out for
instrumentation, and the firmware drives it on every pass of the idle task
whether anything is listening or not.

**That is a live diagnostic stream available on real hardware** - a fourth
source after the monitor, the flash images and port sweeps, and unlike the
monitor it does not need the supervisor to be at its command loop. What the
stream contains is unknown.

`TCLKX` (123) is not directly traced, but there is a 100 ohm resistor from it to
`TCLKR` (126) - series termination, which is what a clock driven off-board into
a header wants, and it explains why `TCLKR` has no source of its own. Consistent
with a one-way stream out to `J7`, the receive half wired for completeness and
never read: `TDR` is on the header but no instruction reads it.

## The EEPROM is the CPU's

Two parts of `courier_emu` disagree about how the Atmel serial EEPROM is
reached. `panel.py` puts `nvram-strobe`, `-data-in`, `-chip-select` and `-clock`
on ASIC port `0x10`; `machine.py` drives the same 93C66 from the CPU. On this
board `machine.py` is right, and every predicted net is confirmed:

| 93C66 pin | net | CPU pin | harness register |
|---|---|---|---|
| 1 `CS` | chip select | 52 (`P1.5`) | `0xff56` bit `0x20` |
| 2 `SK` | clock | 57 (`P1.2`) | `0xff56` bit `0x04` |
| 3 `DI` + 4 `DO` | one shared net | 79 (`P2.7`) | `0xff5e` / `0xff5a` bit `0x80` |
| 5 `GND` | ground | - | - |
| 6 `ORG` | **floating** - selects x16 | - | - |
| 7 `DC` | floating - no bond inside | - | - |
| 8 `VCC` | supply | - | - |

**The shared data net is the distinctive one.** `DI` and `DO` are separate pins
on the chip; one net carrying both is not an accident, and it is exactly what
`machine.py` assumes when it drives `P2LTCH` and then samples `P2PIN` for the
same bit. That model was **recovered from the ROM's driver** - inferred from the
sequence of register writes, with the shared pin read off the code rather than
the board. The board now says the same thing.

**`ORG` floating is a setting, not a gap.** On the Atmel part an unconnected
`ORG` is pulled up internally and selects x16: 256 words of 16 bits, 512 bytes -
which is what `courier_emu/nvram.py` already models, chosen because the driver
reads and writes words and the boot block copies 512 bytes. The marking is read,
so the pull-up is the datasheet's and this is specification rather than
inference.

That also completes the CPU's chip-select allocation:

| CPU select | goes to |
|---|---|
| `GCS0` (pin 59) | the ASIC |
| `LCS` (pin 60) | both SRAMs' `CE#` - but see `UCS` |
| `UCS` (pin 61) | **a RAM's pin 20** (`CE#`) - *not* the flash, which the ASIC selects |
| `P1.2/GCS2` (pin 57) | **not a select** - EEPROM clock, driven as GPIO |
| `P1.5/GCS5` (pin 52) | **not a select** - EEPROM chip select, driven as GPIO |

Two generic selects spent as ordinary outputs is a choice the firmware makes
explicitly, through **Port 1 Control at `0xff54`** - bit 0 set, bits 2 and 5
clear. Nothing in `courier_emu` reads it.

These mappings came from different firmware families - the ROM builds for the
CPU path, the XMF supervisor for the ASIC path - so this settles the 2806 and
says nothing about the other board.

## The interrupt map, and why it is not yet a discrepancy

On this board CPU `INT0` (pin 62) is unconnected and the ASIC drives `INT1` and
`INT2`. On the 80186 `INT2` is interrupt type 14, `0x0e`. `machine.py` models
the board's frame edge as `INT0` - `INT0_VECTOR = 12`, type `0x0c`
([machine.py:585](../courier_emu/machine.py)).

Those do not agree, and it is **not yet a harness bug**: the harness models the
20.16 MHz board running ID_SDL 302/403, the pin reading is from the 2806 running
stock 7.3.14, and the CPU side is the half that does not transfer. Two boards
are allowed to wire their interrupts differently.

So there are two questions and only one is open here. **On the 2806**, which
vector does `INT2` reach? **On the 20.16 MHz board**, is the frame edge `INT0`?
Nothing above bears on the second; it needs that board's own `INT0` pin read.

Both are cheap and neither needs a scope. The IVT is at physical `0` and is RAM,
and the monitor reads it - the method
[ram-probe-delivery.md](ram-probe-delivery.md) already uses. **Read vectors
`0x0c` and `0x0e`**; whichever holds a real far pointer into flash is the edge
that board's ASIC drives. The 80186's interrupt control registers settle it a
second way.

## The 2805 ISA board - a third unit, and the first internal one

A **Courier 2805 ISA internal** (barcode `00280500 R:2`) was metered on
2026-09-18. It carries the same `1-016-905` ASIC - date code **9726**, against
the 2806's 9948 and the I-modem's 9612 - and the same `PA28F400` flash, so the
tables above are a hypothesis it can test rather than a map it inherits. It has
**no ISA slot available**, so nothing here is a live reading; it is continuity
only.

It has already paid for itself twice: its flash readings caught the `CE#` slip
retracted above, and its UART nets are the first measurement of what the ASIC's
panel pins do on a board with no panel.

### What transfers, pin for pin

| ASIC | goes to | same as 2806 |
|---|---|---|
| `63` | CPU 29, `A16` | yes |
| `62` | CPU 30, `A17` | yes |
| `59` | CPU 31, `A18` | yes |
| `58` | CPU 32, `A19` | yes |
| `70` | flash 11 **and** RAM 10 - the split address latch | yes |
| `73` | flash 3 (`A17`, system `A18`) | yes |
| `74` | flash 34 (`A16`, system `A17`) | yes |
| `76` | flash 35 (`A15`, system `A16`) | yes |
| `75` | flash 13, `GND` | **no** - and the 2806 was wrong, see above |

All four upper address inputs and all three flash address outputs are now
measured on two boards independently. Four in, three out is not a transcription
of one board's readings.

### What replaces the EIA section

There are no `SN75188`s and no `DS1489AM`. In their place is a **`TL16PNP550AFN`**
- a TI Plug-and-Play ISA 16550 in a 68-pin PLCC - facing the host. The DTE is
the ISA bus, so the part that made TTL into EIA levels on the 2806 makes TTL
into bus registers here. Everything inboard of that boundary appears unchanged,
which is why `EbSerial` on CPU serial channel 0 should apply to this board as it
stands.

The pin numbers are the datasheet's, from
[TL16PNP550A-SLLS190B.pdf](TL16PNP550A-SLLS190B.pdf) - SLLS190B, March 1995,
revised March 1996 - held here so nobody has to find it again.

| UART pin | datasheet name | dir | 2805 | 2806's same signal |
|---|---|---|---|---|
| 6 | `SIN` | I | ASIC 46 | ASIC 46 to `U22` pin 2 - the `RD` net |
| 49 | `RTS` | O | CPU 1 (`CTS0`) | `DS1489` `2Y` to CPU 1 |
| 50 | `DTR` | O | ASIC **18** - *not* the predicted 48 | ASIC 18 is the `TR` lamp; `DS1489` `4Y` goes to ASIC 48 |
| 51 | `SOUT` | O | CPU 3 (`RXD0`) | `DS1489` `1Y` to CPU 3 |
| 59 | `DCD` | I | ASIC 9 | ASIC 9 to `U23` pin 4 - the `CD` driver |
| 60 | `CTS` | I | ASIC 10 | ASIC 10, recorded as "the `CS` lamp" |
| 61 | `RI` | I | ASIC 11 | ASIC 11 to `U23` pin 10 (`3B`) |
| 62 | `DSR` | I | ASIC 12 | ASIC 12 to `U23` pin 2 (`1A`) |

**Every net lands on the signal the 2806 says it should.** `RD` reaches `SIN`,
the `CD` driver's source reaches `DCD`, the host's `RTS` reaches `CTS0` and the
UART's `SOUT` reaches `RXD0`. The DTE architecture transfers whole: the same
signals in the same directions, with the 550 doing in bus registers what the
75188/1489 pair does in EIA levels. `EbSerial` on CPU serial channel 0 describes
this board as it stands.

### `ASIC 10` is `CTS`, and that corrects the 2806's table

This section first read ASIC 10 as a **repurposed** pin - the `CS` lamp on the
external, something else on the internal - and concluded that the ASIC's
bottom edge is re-used on a board with no panel. **That was wrong, and the
datasheet is what corrects it.** UART pin 60 is `CTS`, and `CS` is the *Clear to
Send* lamp. It is the same logical signal with a different consumer: on the
external it lights a lamp, on the internal it drives the host UART's `CTS`
input.

So the correction runs the other way, and improves the 2806's own map. Two
bottom-edge entries above name a **destination** where they could name a
**signal**:

| ASIC pin | recorded as | is |
|---|---|---|
| 9 | "`U23` pin 4 - the `CD` driver's input" | **`DCD`** |
| 10 | "`CS` lamp" | **`CTS`** |

That is the method rule below in miniature - a trace that stops at a part's
input pin has found one end of a net, not the whole of it - applied to a lamp
rather than a line driver.

`ASIC 11` and `12` then close the modem-status group the same way, and neither
needs a correction: both were already recorded as 75188 driver inputs, and they
reach `RI` and `DSR`. All six of the 2806's driver-fed signals now have names.

Nothing yet says whether the *rest* of the bottom edge transfers. Eight DIP
switches and a Talk/Data switch have no obvious internal-card equivalent, and
those readings remain the 2806's alone.

### `DTR` on ASIC 18 does not fit, and the direction is why

Every net above keeps its direction. `ASIC 10` drives the `CS` lamp on the
external and the UART's `CTS` **input** on the internal - an ASIC output in
both cases, which is why that one reconciled cleanly.

`ASIC 18` does not. UART pin 50 is `DTR`, an **output** from the 550, so on the
2805 ASIC 18 is an **input**. On the 2806 it drives the `TR` lamp, which makes
it an **output**. The same pin cannot be both unless something is being
reconfigured, and three readings are possible:

1. **The `TR` lamp entry is a destination, not a signal** - the lamp sits on
   the `DTR` net rather than being driven by a dedicated ASIC output, and ASIC
   18 is the `DTR` input on both boards. This is the same correction `ASIC 9`
   and `10` just took, and `TR` is *Terminal Ready*, so the signal name fits.
2. **The gate array reconfigures the pin** per product variant.
3. **One of the two readings is wrong.**

**Reading 1 is the one the firmware supports.** `DTR` is a DTE-to-modem signal:
the terminal drives it and the modem senses it, so an ASIC pin carrying `DTR`
should be an input on *any* board. And the firmware treats it as one -
`courier_emu/panel.py` puts `0x12` bit `0x40` in the **input** map as
`dte-dtr`, sampled at `0x5e375` and re-polled at `0x5e395` and `0x5e3b5`, with a
low reading posting supervisor events 6 and 7. The supervisor reads `DTR`; it
never drives it. The panel table above already says pin 18 "follows the DTE's
`DTR`, read at `0x12` bit `0x40`" - which is a sense input described as a lamp.

So the `TR` lamp is most likely sitting **on** the `DTR` net rather than being
driven by a dedicated ASIC output, exactly as `CS` turned out to be `CTS`.

That leaves `DS1489` `4Y` to **ASIC 48**, recorded as "most likely `DTR`" - an
inference, never confirmed, and now the weaker of the two. Both pins cannot be
the `DTR` input. The 2805 is the argument against 48: it has no EIA receiver,
so if 48 were the sense pin there was nothing stopping USR routing the 550's
`DTR` to it, and they routed it to 18 instead.

**Measured 2026-09-18: ASIC 48 goes nowhere on the 2805.** That was offered
here as the probe that separates the two, and it is not - *both* readings
predict a dead pin 48 on a board with no EIA receiver. The result is consistent
with either, and the claim that it would decide was wrong.

What the readings actually leave is two sound arguments pointing opposite ways:

* **For 18.** A gate array's pin functions are fixed silicon and do not move
  between boards. The 2805 puts `DTR` on 18, so if `DTR`-sense is a die
  function it is on 18 on both. The address-side transfers support the
  same-silicon premise.
* **For 48.** The `DS1489` has four receivers and the DTE-to-modem set has
  exactly three members - data, `RTS`, `DTR`. `1Y` is data and `2Y` is `RTS`,
  so by elimination `4Y` into ASIC 48 is `DTR`. That is why the entry reads as
  it does.

Both hold, so their shared premise is the wrong one: **48 and 18 are probably
not alternatives but two ASIC pins on one net** - `1489` `4Y` feeding 48, 18 and
the `TR` lamp together, probed from different ends on different days and written
down as separate facts. This file already carries an unexplained instance of the
same shape: `AA` on ASIC pins 13 and 21 for one firmware bit.

**The probe that does separate them is on the 2806, not the 2805: meter ASIC 18
against ASIC 48.** Continuous means one net and both entries stand. Open means
they are genuinely different pins and the 2805 decides which one carries `DTR`.

### There are two `93C66`s, so nothing is shared

The 550 has its own serial-EEPROM interface - `CS` (54), `SCLK` (55), `SIO`
(57) - and the datasheet specifies an **`ST93C56/66` or equivalent** holding
"the clock prescalar divisor and PnP resource data", organised x16 with `ORG`
tied high or floating. That is the same part in the same configuration as the
2806's settings NVRAM, and pin **58** is an arbitration line that goes low when
"either the TL16PNP550A **or controller**" is accessing the EEPROM - so TI
expected the part to be shared, and this section first inferred that it was.

**It is not. The 2805 carries two `93C66`s.** One is the PnP controller's
resource store and one is the supervisor's settings NVRAM, and the arbitration
pin buys nothing here because the parts are separate. So `nvram.py`'s 256-word
map still describes a part the supervisor owns alone, and a captured settings
EEPROM off this board is directly comparable with the 2806's - **provided the
right one of the two is read.** Tell them apart by metering `CS`: the
supervisor's answers to a CPU pin (`CS`/`SK` on 52/57, `DI`+`DO` on 79 over
there), the PnP one to UART pin 54.

### Three oscillators, and the clock

| | marking | frequency |
|---|---|---|
| X1 | `eb726391` | the CPU's - **50 MHz**, inferred |
| X2 | 22.118M | the UART's - `12 x 1.8432 MHz` |
| X3 | `R0730318` | the ASIC's - 40.320 MHz, the product-line constant |

The 80C186EB halves its crystal input to make `CLKOUT`, which is why the
20.16 MHz board runs the CPU off the ASIC's 40.320 and needs no second can.
A 25 MHz `CLKOUT` needs 50 MHz in, so a third oscillator is the signature of a
25 MHz board - and X1 carries a house number rather than a frequency, so the
50 MHz is arithmetic, not a reading.

X2 settles what the UART is: `22.1184 / 16 = 1,382,400`, so divisor 12 gives
115200. The 550 makes its own baud rate from its own crystal and is a real
autonomous UART the host drives, not something the modem's CPU clocks.

### What this board is for

Its DSP is **not** the TI `D17140PQ`. It is a Sierra Semiconductor `SC34350CQ`
(`HBS-66A4ETW`), alongside a `TLC320AC01CFN` codec, an Atmel `93C66`, two
`CY62256-70SNC` and a USR flash label dated `11-22-96`. A Sierra datapump will
not take the four-row C5x overlay table in
[dsp-overlays.md](dsp-overlays.md), and cannot hold the TI mask-ROM loader at
`0610` that the supervisor hands its first block to - so this is most likely a
separate firmware family rather than a strap variant, and `courier_emu`'s C5x
model does not describe it.

**Dumping its flash decides that**, and `CourierRom.dsp_overlays` runs the test
as it stands: a four-row table loading at `8000`/`9d00`/`b000`/`dc00` means the
same lineage, its absence means a separate target. Its `93C66` is SOIC-8 and
clip-readable, and **no captured 93C66 image exists in this repository from any
board**.

### Pin `43`, pin `13`, and four readings the clamp diodes invented

Metered 2026-09-19, continuity and diode mode, board unpowered. It started as a
question about whether the pinout constrains the I/O port map, and it produced
one net and a method rule.

**The one confirmed connection: `13`-`43` reads 0.00 V, both boards.** That is
copper. Pin `43` had been unread - it sits in the `39`-`44` run on the right
edge - and it is common with a bottom-edge pin on two unrelated layouts.

**A transistor sits on that net.** `Q8`, SOT-23, marked `A12`, with `R20`
(`561`, 560 Ohm) above it and `R57` (`103`, 10 kOhm) below. One side goes to ASIC
`21`; the other side's two pads reach `14` and `43`. A 560 Ohm series resistor and
a 10 kOhm base resistor around a small-signal SOT-23 is an LED driver stage, which
is the first independent support for `21` being a lamp node driven through a
transistor rather than from the gate array's own pin. Terminal assignment is
**not** established - it was guessed from package geometry, and the `A12`
marking has not been resolved to a part.

**What the clamp diodes invented.** Every other reading in that session fell in
the 0.6-1.4 V band and conducted both ways:

| pair | reading | was taken to mean | is |
|---|---|---|---|
| `14`-`24` (`GND`) | 0.9 / 0.6 | `14` is a ground pin | an ordinary I/O pin clamping to the rail |
| `14`-`U17` pin 4 | 1.3 / 0.6 | the ASIC holds the opto's emitter | `U17` pin 4 is ground; `14` clamps to it |
| `14`-`43` | 1.0 / 1.3 | one net across the transistor | two pins, no copper |
| `13`-`21`-`43` on the 2806 | beep | a three-pin net, or a bonded triple | `13`-`43` copper; `21` through a junction |

Each of those carried a hypothesis that is now retired: a board-ID strap link at
`43`; an internal bond making `13`/`21`/`43` one node; a ring-detect signal on
the bottom edge; and a **four-pin DAA** in which the ASIC owned both ends of each
optocoupler and could bias it. The DAA is the two collector pins it always was,
`19` and `22`, and the opto emitters are grounded. ASIC `14` and `15` keep their
2806 attributions (`ARQ` lamp, Talk/Data switch); nothing here touches them.

**What does not follow.** The pin map constrains the *shape* of the port map -
only `AD0`-`AD7` reach the package, and pin `54` between `RD#` and the first
interrupt is where the I/O window's decode would be - but it does not attribute
ports. The DIP switches are the proof: every switch pin is known and the order
is scrambled relative to pin order, so which port bit reads which switch has to
come from the firmware. See [asic-port-map.md](asic-port-map.md).

## Method rules this board taught

**A continuity reading to ground is not evidence that a pin is a ground.** It is
evidence that a pin is grounded *at that moment*. The DIP bank's common is
grounded, so any pin tied to ground through a closed switch reads exactly like a
supply. Pin `118` sat in the left-edge table as "DSP `VSSC`/`VDDI`, decoupled"
because switch 3 was closed when that pass was taken; pin `15` was recorded as
ground because the Talk/Data button was pressed. **Only readings taken with the
switch moved distinguish them.**

That direction is the dangerous one. A switch reading on a supply pin is
obviously wrong and gets challenged. A supply reading on a switch pin looks like
the pad-ring convention holding up, agrees with everything around it, and gets
believed.

Grounds without independent corroboration want re-reading with the switches
open. `100` and `120` are corroborated by position and by the bus shape that
predicted them; the corner pins are safe for the same reason. `24` is not - it
was taken in the same pass as pin 15 and has not been re-read.

**A trace that terminates at a part's input pin has found one end of a net, not
the whole of it.** `CD` and `RD` were both listed as "not on the ASIC" on the
strength of landing at a 75188's TTL-side input; both are ASIC outputs. The
claim was about where the probe stopped. `OH` is the only one of that original
list that is safe, because a relay coil is a terminus rather than an input.

**On an unpowered board, only 0.00 V is a connection.** Every I/O pin on an IC
carries ESD clamp diodes to its supply rails, so a diode-mode probe between any
two pins of an unpowered part reads two clamps in series - **0.6-1.4 V, and it
conducts in both directions**. A pin against ground reads one clamp, ~0.6 V. A
beep-mode meter beeps at all of it.

The control reading that settles it: ASIC `2` (DIP switch 2) against ASIC `29`
(CPU `A17`) reads **1.3 / 1.4**. Those two pins cannot be connected, so the band
belongs to the package, not to any net.

A real junction is ~0.6 V one way and open the other. A real net is 0.00 V both
ways. Anything between is the die talking, and it says only that both probes
landed on the same part. See the 2805 section below, where this rule retired
four readings and a hypothesis built on each.

**Off-by-one pin miscounts happen.** Three have been found: the top edge counted
from 60 rather than 61 (making one flash line `73` instead of `74`, and hiding
that `73` and `74` are two different flash pins), CPU pin 28 recorded where 29
was meant, and `LCS`/`UCS` on adjacent CPU pins 60 and 61. When two readings
conflict on adjacent pins, that is the likely explanation rather than anything
subtle.

## Reference tables, carried so nobody has to fetch them

### 80C186EB, 80-lead QFP - Table 7

The part is an **80C186EB in the 80-lead QFP**, not the plain `S80C186` that
[board-parts.md](board-parts.md) records from the marking: the XL's QFP puts
`ALE` on pin 10 and `INT0` on 31, which these readings are nothing like. Every
CPU pin number in this file checks against this table, `INT3` excepted.

| pin | name | pin | name | pin | name | pin | name |
|---|---|---|---|---|---|---|---|
| 1 | `CTS0` | 21 | `AD4` | 41 | `S1` | 61 | `UCS` |
| 2 | `TXD0` | 22 | `AD12` | 42 | `S0` | 62 | `INT0` |
| 3 | `RXD0` | 23 | `AD5` | 43 | `DEN` | 63 | `INT1` |
| 4 | `P2.5/BCLK0` | 24 | `AD13` | 44 | `HLDA` | 64 | `INT2/INTA0` |
| 5 | `P2.3/SINT1` | 25 | `AD6` | 45 | `HOLD` | 65 | `INT3/INTA1` |
| 6 | `P2.4/CTS1` | 26 | `AD14` | 46 | `TEST` | 66 | `INT4` |
| 7 | `P2.0/RXD1` | 27 | `AD7` | 47 | `LOCK` | 67 | `PDTMR` |
| 8 | `P2.1/TXD1` | 28 | `AD15` | 48 | `NMI` | 68 | **`RESIN`** |
| 9 | `P2.2/BCLK1` | 29 | `A16` | 49 | `READY` | 69 | **`RESOUT`** |
| 10 | `AD0` | 30 | `A17` | 50 | `P1.7/GCS7` | 70 | `OSCOUT` |
| 11 | `AD8` | 31 | `A18` | 51 | `P1.6/GCS6` | 71 | `CLKIN` |
| 12 | `VSS` | 32 | `A19/ONCE` | 52 | `P1.5/GCS5` | 72 | `VCC` |
| 13 | `VCC` | 33 | `VSS` | 53 | `VSS` | 73 | `VSS` |
| 14 | `VSS` | 34 | `VCC` | 54 | `VCC` | 74 | `CLKOUT` |
| 15 | `AD1` | 35 | `VSS` | 55 | `P1.4/GCS4` | 75 | `T0OUT` |
| 16 | `AD9` | 36 | `RD` | 56 | `P1.3/GCS3` | 76 | `T0IN` |
| 17 | `AD2` | 37 | `WR` | 57 | `P1.2/GCS2` | 77 | `T1OUT` |
| 18 | `AD10` | 38 | `ALE` | 58 | `P1.1/GCS1` | 78 | `T1IN` |
| 19 | `AD3` | 39 | `BHE/RFSH` | 59 | `P1.0/GCS0` | 79 | `P2.7` |
| 20 | `AD11` | 40 | `S2` | 60 | `LCS` | 80 | `P2.6` |

Source: Intel `80C186EB/80C188EB, 80L186EB/80L188EB` datasheet, Table 7. Names
in the 188EB's parentheses are dropped.

### TLC320AC01, FN package - terminal functions

| pin | name | pin | name | pin | name | pin | name |
|---|---|---|---|---|---|---|---|
| 1 | `MON OUT` | 8 | `RESET` | 15 | `FC0` | 22 | `ADC GND` |
| 2 | `PWR DWN` | 9 | `DGTL VDD` | 16 | `FC1` | 23 | `ADC VMID` |
| 3 | `OUT+` | 10 | `DIN` | 17 | `FSD` | 24 | `ADC VDD` |
| 4 | `OUT-` | 11 | `DOUT` | 18 | `M/S` | 25 | `IN-` |
| 5 | `DAC VDD` | 12 | `FS` | 19 | `EOC` | 26 | `IN+` |
| 6 | `DAC VMID` | 13 | `SCLK` | 20 | `DGTL GND` | 27 | `AUX IN-` |
| 7 | `DAC GND` | 14 | **`MCLK`** | 21 | `SUBS` | 28 | `AUX IN+` |

Source: TI `TLC320AC01C` data manual, SLAS057D.

## Readings that need retaking

1. **The `SD` group.** Recorded as CPU pins 4, 7 and 63 plus 74AHC04 pin 11. CPU
   63 is `INT1`, now read from both ends (ASIC `47` to CPU `63`). CPU 7 is
   `P2.0/RXD1`, the receive half of a channel whose transmit pin is not
   connected. Two of three have failed, so **where the `SD` lamp is driven from
   is unknown again** and the group should be retaken pin by pin rather than
   reinterpreted.
2. **`'573` pin 19**, recorded as reaching RAM pin 1 and flash pin 20. Flash pin
   20 is `DQ10`, a *data* line; RAM pin 1 is `A14`, an address line. No latch
   output is both.
3. **The `A7` net** at flash pin 4 and RAM pin 3, recorded as running to `'573`
   pin 12. The '573 latches `A8`-`A15` and cannot carry `A7`; the ASIC drives
   system `A7` from pin 64. Retake toward the ASIC.
4. **CPU `INT3`**, recorded on CPU pin 75. Table 7 gives 75 as `T0OUT`; `INT3` is
   pin 65. If `T0OUT` really is on that net, a timer output going somewhere is a
   finding in itself.
5. **`LCS` or `UCS` on the SRAM bank.** The pair shares one `CE#` net, so one of
   the two adjacent readings is wrong. Probe RAM pin 20 against CPU 60, then
   against 61; exactly one should answer. The 80186's `LCS` covers low memory
   from address zero and `UCS` the top of the space, so the firmware's memory map
   follows from which.
6. **A second `RS` reaching codec pin 13.** Pin 13 is `SCLK`, the serial shift
   clock, which is not a reset of anything and belongs on the DSP's shift clock
   beside the three serial lines on DSP 43, 104 and 106. Almost certainly a
   mislabel, and it has a predicted destination to check against.
7. **Pin `24`, recorded as `GND`** in the same pass as pin 15, which turned out
   to be a pressed button. Re-read with the panel's switches moved.
8. **Every entry taken in beep mode.** A beep-mode meter beeps through the
   package's ESD clamps at 0.6-1.4 V, so any reading taken that way records that
   two probes landed on the same part rather than on the same net. The entries
   most exposed are the ones that already needed the destination-versus-signal
   correction three times, on the bottom edge. Re-read at a 0.00 V threshold in
   diode mode, noting lead polarity; this is an audit of the method, not of any
   one pin.

## What is still unknown

Fifteen of the 120 pins are unread; of the rest, seventeen are inferred middles
of measured runs (the two DSP data groups and `A2`-`A6`). The top and left edges
are finished but for one pin each; the bottom edge is at 26 of 30; the right
edge has ten unread - `32`-`36`, `39`-`42` and `44`, with `43` now read as the
`13` net.

In the order they would pay:

1. **The frequency at DSP pin 96.** The ASIC drives the DSP's clock and nothing
   here knows what rate it produces. A scope on that pin is the only thing that
   answers it, and the DSP's machine cycle - which the timebase note and every
   DSP-side analysis treat as a board constant - follows from it. `CLKMD1` (DSP
   pin 71) and `CLKMD2` (pin 103) say what the DSP divides it by, and those are
   meter readings.
2. **Whether there is any paging at all.** *Downgraded 2026-09-18.* This used to
   read "the paging register" and be the largest unmodelled behaviour on the
   board. The ASIC does **not** drive the flash's `CE#` - `UCS` does - and its
   four-in/three-out address path is what a flat map needs, with `A19` consumed
   by the `UCS` decode. Nothing now argues for a paging register, and the flat
   512 KiB image the harness uses matches both boards. What remains open is the
   weaker question of why the top three address lines are routed through the
   ASIC at all.
3. **The left edge's last two, `112` and `117`**, against the DSP control signals
   still missing. The ASIC has the data bus, `IS`, `R/W`, `STRB`, `INT2` and the
   clock. Four candidates would each change something: **`DS` (DSP pin 89) and
   `PS` (91)** - `IS` alone makes the ASIC an I/O device, `DS` would put it in
   the DSP's *data memory* alongside the SRAM; **`MP/MC` (pin 5)**, which decides
   whether the DSP boots from on-chip ROM or external memory, and which
   [board-parts.md](board-parts.md) records as running at 1 without saying who
   sets it; **`BIO` (130)** and **`XF` (109)**, a handshake pair the firmware
   could poll and answer with. Two pins for four candidates.
4. **The phone-line header's pinout.** Twelve positions, three of them reaching
   the ASIC, with two optocouplers beside them. Continuity to the `RA5W-K`'s coil
   names the hook output; watching the pins while the line rings names the ring
   input.
5. **Which port bit each DIP switch appears in**, and what is on the other side
   of switch 1. Live through the monitor rather than with a meter: flip each
   switch in turn and watch which port bit moves. It also shows which switches
   are read by nothing. For switch 1, one probe on its other terminal -
   ground/`VCC` makes it a strap on `P2.6`, the DTR net makes `P2.6` the signal
   and the override hardware. A second check separates them live: unplug the DTE
   so nothing asserts DTR, then toggle the switch.
6. **What gates the transmit path.** `TXD0` goes into the ASIC and the `RD`
   driver comes out of it while receive reaches the CPU directly. A part on one
   direction only is there to do something to it, and no port bit is identified.
7. **What `J7` carries.** The DSP's second serial port streams continuously to
   that header and nothing knows what is in it. A capture, not a meter - and the
   one item here that could produce new information about the *firmware* rather
   than about the board.
8. **The right edge's unread block**, `32`-`36` and `39`-`44`. By elimination it
   is where the codec and the DAA behind the phone-line header must land. Not a
   single probe but the place to sweep once the targeted ones are done.
9. **Why `AA` is on two ASIC pins**, 13 and 21, when the firmware drives one bit.
   A continuity check between them.
10. **What else is on CPU pin 68**, and **what level ASIC pin `52` takes while
    the ASIC is itself in reset.** If it does not hold low, the CPU is released
    before the ASIC is ready and the boot chain above describes the steady state
    rather than power-on.
11. **CPU `RESOUT` (pin 69)**, and **`INT4` (pin 66)**. Neither has been
    followed.
12. **`U18`'s output `3Y`** (pin 8). Three DTE inputs are accounted for, so the
    fourth channel is spare or carries something unexpected.
13. **Top-edge pin `72`.** Three of that edge's four unread pins went to the
    flash, so `72` is most likely a fourth flash line. Completeness rather than a
    question with something riding on it.
14. **The unpopulated four-switch footprint's pads**, against the three unread
    bottom-edge pins and against ground.
15. **The codec's `M/S` (pin 18).** The firmware's free-run configuration implies
    the codec is the slave and the DSP drives `SCLK`/`FS`. One meter reading.
    `MCLK` needs no reading - it is 2.880 MHz, solved from the divider registers.
16. ~~**Whether `&T1` is the codec's analog loopback.**~~ **Answered: yes.** The
    resident writes register 5 with `0508` at `90c3` and `90e1`, both real code
    paths under the cell `0x6f` state word, through the register writer at
    `8770`. `DS01`-`DS00` = `00` is analog loopback, and `0508` has it - so the
    loop is *inside the AC01*: "In loopback, `OUT+` and `OUT-` are internally
    connected to `IN+` and `IN-`" (docs/ac01.txt 2.15.2). There is no external
    switch and the ASIC is not involved; the DSP throws it over `DIN`. The
    bring-up's `0505` at `80bd` is the normal setting, as this entry said.

    This stayed open because the entry guessed the wrong encoding. It looked
    for `0504` - `DS02` set - and the firmware writes `0508`, with `DS03` set.
    Same field, so a literal grep for `0504` found only a coincidence in a
    byte-pair table at `c269`. Enumerate every `bf80 05xx` and mask `DS01`-`DS00`
    instead of grepping one value.
17. **DSP `A6` (61) and `A7` (62), and a second pass on `A4` (59).** The hole in
    the address decode: the firmware writes port `0x60`, which needs `A6`, and
    six lines with a gap at `A4` cannot produce it. At least one more address
    line is on an unread edge.
18. **`GCS0 Start`/`Stop` at `0xff80`/`0xff82`, and Port 1 Control at
    `0xff54`.** Those define the address range that selects the ASIC and which
    `P1` pins are generic chip selects. Both are readable out of a run with no
    hardware at all, and nothing in `courier_emu` looks at either.
19. **The 2806's ASIC marking.** Still unread, and it is what decides whether any
    of the CPU-side findings here transfer to the 20.16 MHz board.
