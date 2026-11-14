# The board

This file describes the 20.16 MHz Courier and the 25 MHz Courier 2806. We
identified the parts from photographs and from continuity readings that the
owner made. Where the firmware can check a claim, we checked the claim against
the firmware.

> **For each pin, the board that gave the reading is important.** The **DSP
> side transfers**: stock 7.3.14 runs on the 20.16 MHz AC01 board and on the
> 25 MHz AC03 board. Its **DSP payload is byte-identical between the two
> boards**. There are 126,851 consecutive identical bytes, which include the
> payload and all three overlays. Code that is this identical cannot operate
> two different interfaces. Thus `IS`, `INT2`, `READY` and the data bus are
> findings about the two boards.
>
> **The CPU side does not transfer.** All of the difference between the two
> images is in the supervisor, and a difference in the CPU-side wiring would
> show there. `ALE`, `RD#`, `WR#`, the interrupt lines and the unconnected
> `INT0` are findings about the 2806 only.
>
> **The owner metered a third board, the 2805 ISA internal, on 2026-09-18.**
> The record of that work is in
> [asic-pinout.md](asic-pinout.md#the-2805-isa-board---a-third-unit-and-the-first-internal-one).
> That board confirms the memory side on a second unit. It is different on the
> panel side: an internal card has no lamps, and the board uses the bottom-edge
> pins of the ASIC again for a 16550 that faces the host.
>
> The pin readings below are from the **2806**. The ASIC marking is from the
> **20.16 MHz** board. Nobody has read the marking on the ASIC of the 2806.
> Thus, no evidence shows that the two boards have the same gate array. A read
> of that marking is the least expensive open item here.

## The parts

| marking | what it is |
|---|---|
| `NEC USA 1-016-905 9948LV001` | **the ASIC.** A USR part number on a gate array that NEC made, week 48 1999. There is no catalogue part, no datasheet, and the metal is custom. |
| `TI DSP 16-912 (C) US ROBOTICS D17140PQ` | the C5x-family DSP, with a custom marking. Possibly a **'C50 or 'LC50**, not the 'C52 that the core models. Refer to the text below. |
| `S80C186` | the supervisor. More exactly, an **80C186EB in the 80-lead QFP**: `RD`/`WR`/`ALE` on 36/37/38 and `INT0`/`INT2` on 62/64 agree exactly with Table 7 of that package, and do not agree with the XL. `uart.py`'s `EbSerial` already assumes this device. Its `GCS0` (pin 59) is the chip select of the ASIC. |
| `TLC...320AC01CFN` | the voice-band codec, PLCC, adjacent to the DSP. The 2806 has an **AC03** in its place. |
| `ECLIPTEK EC11 40.320M` | the oscillator of the **ASIC**. Both boards have the same part. Thus the DSP clock and the codec `MCLK` do not change between the boards. The 2806 has a **second** crystal for the CPU only. |
| `NEC D43256BGU-70LL` x2 | the SRAM of the **80186**, `U4` and `U12`. They are not two banks. They are the low and high byte lanes of one **32K x 16**. |
| `CY7C199-15VC` x2 | the SRAM of the **DSP**: 2 x 32Kx8 = 32K words on a 16-bit bus, exactly `0x8000`-`0xffff`. |
| `ISSI IS61C256AH-15J` | 32Kx8 15 ns SRAM. |
| `ADM707` | supervisory reset. On this board it is **a power-good reset only, and its watchdog is not used**. |
| `74VHC573`, `74VHC32`, `74VHC04` | bus glue. There is exactly **one** '573, which latches the **high** byte. The ASIC latches the low byte. |
| `PA28F400` | the **flash**. Intel 4 Mbit / 512 KiB, which is exactly the size of the 2806 dump. |
| `SN75188` x2, `U22`/`U23` | the **EIA-232 drivers**, TTL in / EIA out, modem-to-DTE only. The ASIC supplies three of the four gates of each part. |
| `DS1489AM`, `U18` | the **EIA-232 receiver**, EIA in / TTL out, DTE-to-modem. |
| `74AHC04` | inverter. One gate is in the `SD` path. |
| `H11B2` x2, `U14`/`U16` | **optocouplers**. They are the isolation barrier of the line side, and the first named parts in the DAA section. |
| `RA5W-K` | the **hook relay**. The `OH` lamp is on its pin 9. This is why `OH` is the one panel line that is not on the ASIC. |
| Atmel 93C66 | serial EEPROM, which stores the settings. On the 2806 it is the EEPROM of the **CPU**, not of the ASIC. |

The DAA/line section was not in the photograph. Thus this file does not
describe it, except for the two optocouplers.

## The ASIC is the entire board outside the two processors

The 80186 communicates with all other parts through the ASIC. The C5x
communicates with the 80186 through it, and the line-side parts answer to it.
On the I/O bus of the CPU, it is not one peripheral of many: **it is the only
device on that bus**. This is a measurement, not a figure of speech. The CPU
moves its own peripheral control block into *memory* at `0xff00`-`0xffff`, and
flash and SRAM are also memory. Thus, any device that answers an `IN` is the
gate array.

It has four functions:

1. **The I/O of the board.** Ports `0x10`, `0x12`, `0x14` carry the hook relay,
   the NVRAM strobe, the carrier-detect pair, ring detect and the option straps.
2. **The bootstrap of the DSP.** It holds the C5x in reset and writes the
   program RAM of the C5x through the `0x40`-`0x4e` window.
3. **The mailbox.** It connects *CPU I/O ports* to *DSP data-memory cells*. The
   two address spaces are not related, and the ASIC joins them. For the
   emulator, this is the most important function of the ASIC. Refer to
   [dsp-cpu-link.md](dsp-cpu-link.md).
4. **The address latch.** It latches the low address byte of the CPU for the
   two memories, and it drives the top three address lines of the flash. It
   does **not** drive the `CE#` of the flash. `UCS` drives it. *Corrected
   2026-09-18 - this read "the memory controller ... folds four upper address
   lines into three".*

**Not the timebase.** The 5.000 ms tick is Timer 0 of the 80186 itself, with a
max count of 25,200 at CLKOUT/4. Four methods confirmed this. One method was a
counter routine on the modem, which logged exactly 200.0 increments each
second. `40.320 / 2 = 20.16 MHz` CLKOUT, thus the timer clock is 5.04 MHz.
25,200 gives a round figure in the two cases: 5 ms at 20.16 MHz CLKOUT, or
10 ms if 20.16 was the crystal. The `&T1` slope of the board, 1.000031 s for
each `S18` unit, had already selected the first case.

**Not in the audio path of the CPU.** We swept all ports during analogue
loopback. Only the four handshake registers changed. No CPU port carries
samples.

**Not the tone generator**, although the README said this at one time. A dial
sends `0x16:0000`, then three constant lanes `0x19`/`0x1a`/`0x1b`, then the
keypad index on `0x13`. When the tone ends, it sends `0x16:0000`. Those lanes
are host-write tags. Their handlers write to **DSP data memory** at `0x03ad`,
`0x0392` and `0x03f1`. The tone parameters go to the C5x, thus the
synthesiser is part of the datapump.

## The CPU's I/O space

The ASIC decodes only **even** addresses. All 64 odd ports below `0x80` read
`0x00`. The decode **stops at `0x7f`**. Above that address, all 64 even ports
read back their own address and all odd ports read `0x00`, which is a bus that
nothing drives. Thus there are 64 registers, and the firmware uses about half
of them.

**The idle default is `0x00`, not `0xff`.** On the board, 96 of the 128 ports
below `0x80` read zero. The harness returns `0xff` for each port that it does
not model. `courier_emu.asic_ports` holds the measured map, and
`asic_ports.seed()` gives it in the form that `port_values` accepts. It is
**not connected by default**. The map is the idle, on-hook state. If a run goes
off hook, static values from that state can be worse than `0xff`.

| ports | sites | idle | what it is |
|---|---|---|---|
| `0x00` | 12 r/w | `00` | DTE serial data path |
| `0a` `0c` `0e` | 5r / 21w | `f7` `60` `07` | configuration; `0e` is the panel latch driver, write-only |
| `10` `12` `14` | 20r / 34w | `86` `8a` `7e` | **board latches** - hook relay, NVRAM, carrier-detect pair, ring detect, straps |
| `18` `1a` `1c` `1e` | 104r / 137w | `ff` `ff` `fd` `ff` | **the handshake**, the group with the most traffic; `1c`/`1e` are the mailbox status pair, `18` is the DSP command port of the ROM images and `1e` that of the XMF images |
| `40`-`4e` | 20r / 45w | `ff` | **the DSP download window** - eight latches that carry four payload words |
| `50`-`56` | 9r / 8w | `ff` | second window bank |
| `58` `5a` / `5c` `5e` | 68r / 44w | `20` `00` / `0e` `00` | **the mailbox** - tag pair and data pair |
| `60` `62` | **27r / 0w** | `4b` `00` | **DSP-to-host stream** - input only |
| `64`-`7e` | 3r / 0w | `78 09 8f a7 e8 aa b6 97 51 51 06 4f b3` | almost never read; identity or strapping |

Two rows give their own evidence. **`60`/`62` has zero write sites in all of
the image**. Thus data goes in one direction only, out of the DSP. Also, **ten
of the thirteen values in `64`-`7e` are byte-identical** to a sweep from the
time when this unit ran stock 7.3.14, not ID_SDL 4.03. The same values across
two firmware versions and two sessions show fixed configuration. The three that
are different (`68`, `6a`, `70`, and also `58` and `60`) are state.

**Nothing reads `0x64`-`0x7e`.** No instruction in the supervisor reads or
writes a port in that block. The only code that touches it is the `0x60`/`0x62`
reader. This result comes from a raw-byte refutation of each candidate, not from
a boundary heuristic. But it is not a proof of absence. A `DX` loaded from
memory, as the downloader does at `0e515`, can get to those ports on a path
that the analysis cannot bound.

**Also, the streaming interpretation of that block is refuted.** Repeated reads
do not pop, advance or change it. Thus those are sixteen stable registers. The
`01fe0` machine polls one register. It does not empty a queue.

> **The `0xc0`-`0xc6` cluster is a device-programming path, not a diagnostic
> read.** The block at `08332..083b5` sets `PACS` to `0xe000` and `[0xff18]` to
> `0x10`. Then it reads `0xc2`/`0xc0` and writes `0xc4`/`0xc6` while it streams
> `0x1554` words from segment `0xe000`. An `AT` handler that looks for a literal
> `L` starts it. **Do not start it on the physical modem.** It is `ATNL`. Refer
> to [probing.md](probing.md).

> **The monitor gives incorrect data about the download window.** `ATGLK2I` and
> the `IN` of the CPU agree on 51 of 64 ports. They disagree on all twelve of
> `0x40`-`0x56`, and the pairing is inverted. If a statement about the window
> comes from a monitor sweep, take the reading again.

Only four ports are different between idle and `AT&T8` analogue loopback: `18`
(`c0`/`c6`/`c7`), `1a` (`c0`), `1c` (`f9`) and `1e` (`fb`). `1c` and `1e` both
change on bit 2, which is the bit that the mailbox interrupt of the supervisor
acknowledges. `18` changes *within* the active state, thus it carries a live
signal. When the loop is on hook and there is no call, most of the ASIC does
nothing.

> **A reset sweep gives a clean negative and shows a structural limit.** A
> sweep before and after an `ATZ` finds **0 of 256 ports different**, because
> the monitor is firmware. The board stops its answers when it restarts. You
> can read it again only when the supervisor is back at its command loop. The
> outage is less than 375 ms. To move the download window, a transition that the
> monitor can survive is necessary. There are only two. Power-on, which you
> cannot see through the monitor of the firmware. And a call setup, which needs
> the loop off hook.

## Orientation and pin numbering

The part has 120 pins, 30 on each side. The index dot is at the **bottom
left**. This is in the frame of the part itself, seen from above, with the
`NEC USA 1-016-905` markings upright. Use this orientation before you check
these data again.

The numbering uses the JEDEC convention: pin 1 is at the dot, and the numbers
go counter-clockwise in a top view. **The owner confirmed this.** The owner
took the readings and recorded them in this frame:

| pins | edge | direction |
|---|---|---|
| `1`-`30` | bottom | left to right |
| `31`-`60` | right | bottom to top |
| `61`-`90` | top | right to left |
| `91`-`120` | left | top to bottom |

The owner took the readings with a local numbering for each side. Use these
translations:

- **top** pin = `91 - N`, counted left to right.
- **right** pin = `61 - N`, counted top to bottom.
- **left** pin = `121 - N`, counted bottom to top.

Three independent checks agree with the direction. First, the bottom-edge
readings are on the one edge that was not read, and on the edge where we
predicted the panel. With clockwise numbering, five of them would be on pins
that we measured as the DSP data bus. Second, the four upper address lines of
the CPU are on four ASIC pins, and these step over a supply pair at a corner.
Third, **we read all eight corner pins and all eight are supplies**:

| corner | pins | | corner | pins |
|---|---|---|---|---|
| bottom left | `120` `GND`, `1` `VCC` | | top right | `60` `GND`, `61` `VCC` |
| bottom right | `30` `VCC`, `31` `GND` | | top left | `90` `VDD`, `91` `GND` |

A corner pad is a supply with *either* numbering direction. Thus this check
confirms the count of 30 on each side, not the direction. But it is true at
all locations that we checked, and the inferred bus runs below depend on it.

Each bare pin number below is an **ASIC** pin. We name DSP and CPU pins as
such, because otherwise the numbers are the same.

![The ASIC's pins as currently mapped](asic-pinout.svg)

`tools/draw_asic_pinout.py` makes this image, and it holds the map as data.
When you get a new reading or a correction, edit the table here **and** `PINS`
in the tool. Then run the tool again. [board-map.svg](board-map.svg) answers
the other question - which part communicates with which part. It comes from
`tools/draw_board_map.py` in the same way.

![The board's parts and the nets between them](board-map.svg)

## What is connected

The tables mark the measured pins. If the measured ends of a bus run are
contiguous and in sequence, we **inferred** the remainder of the run, and the
tables mark these pins as inferred.

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

Pin `72` is the only pin on this edge that is not read.

### Right edge - CPU bus control, the DTE, and the telco

| local | pin | signal | CPU pin |
|---|---|---|---|
| 1 | 60 | `GND` | - |
| 2 | 59 | `A18` **in** | 31 |
| 3 | 58 | `A19` **in** | 32 |
| 4 | 57 | `ALE` | 38 |
| 5 | 56 | `WR#` | 37 |
| 6 | 55 | `RD#` | 36 |
| 7 | 54 | *unread* - the most probable location of the chip select of the ASIC | - |
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

This edge has three groups. CPU bus control is at the top, the EIA-232
interface of the DTE is in the middle, and the telco is at the bottom. `ALE`,
`WR#` and `RD#` are adjacent. Pin `54` is between `RD#` and the first
interrupt. The decode for the `0x00`-`0x7f` I/O window is probably at that
location.

CPU `INT0` (CPU pin 62) is **not connected**.

Eleven pins are not read here, `32`-`36` and `39`-`44`. This is the largest
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
`D8`-`D15` and `101`-`108` for `D7`-`D0`. Thus we inferred the twelve pins
between them. **Pin 100 is between the two groups.** From the shape of the run
only, we predicted a ground that divides the two halves of the bus. Then we
measured it.

Pin `117` is the only pin on this edge that is not read.

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

On the bottom edge, the local numbering and the absolute numbering are the
same. `23`, `26` and `28` are not read.

**`AA` is on two pins**, 13 and 21, but the firmware drives one bit (`0x14` bit
`0x10`). Possible causes are: two drivers for more lamp current, a sense return,
or two nets with the `AA` label that the reading merged. This is not resolved.
A continuity check between the two pins will give the answer.

## The part is a memory controller

**The ASIC latches the low address byte of the CPU.** An 80C186EB multiplexes
`AD0`-`AD15` and drives `A16`-`A19` separately. The one `74VHC573` on the
board latches the high byte (`'573` pin 9 is `D7`, CPU pin 11 is `AD8`). No
other part on the board latches the low byte, but the flash and the SRAM both
need it. ASIC pin 70 goes to RAM pin 10 and flash pin 11. On those parts, both
pins are `A0`:

| ASIC pin | system address | where it goes |
|---|---|---|
| 71 | `A0` | '32 pin 12 - byte lane, never reaches a memory |
| 70 | `A1` | RAM pin 10, flash pin 11 - those parts' `A0` |
| 69-65 | `A2`-`A6` | *inferred* |
| 64 | `A7` | RAM pin 4 - that part's `A6` |

There are eight consecutive pins for the eight bits latched from `AD0`-`AD7`.
Thus the memory address bus comes from three sources: `A0`-`A7` from the ASIC,
`A8`-`A15` from the '573, and `A16`-`A19` from the CPU. The exception is the top
three lines of the flash, which also come from the ASIC.

**Each address label at the memories is shifted by one.** On a 16-bit bus, `A0`
selects the byte lane and does not go to the address pins of a memory. Thus the
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

`'32` pin 13 is flash pin 43, `WE#`, the write strobe of the board. `'32` pin 10
is CPU pin 37, `WR#`. The lane terms are not symmetrical, and the cause is the
bus itself. `A0` arrives latched from the ASIC, because `AD0` is multiplexed and
no other part holds it. `BHE#` arrives raw from the CPU, because on the 80C186EB
it is a dedicated pin. Gates 1 and 2 of the '32 are not read.

**The CPU selects its SRAM itself**, with `LCS` (pin 60). At one time, the
records put `LCS` and `UCS` both on the common `CE#` net, but the two cannot
both be correct. `UCS` holds the `CE#` of the *flash* (refer to the retraction
below). Thus `LCS` is on the SRAM, and that off-by-one error is closed. `LCS` is
programmed to `0x00000`-`0x20000`, low memory from zero, which is the correct
location for the SRAM.

> **Retracted 2026-09-18. The ASIC does not select the flash; `UCS` does.**
> ASIC pin 75 goes to flash pin **13**, `GND`, not to flash pin 12. Three
> items of evidence agree, and no evidence now disagrees:
>
> * **A second board.** The 2805 ISA board has the same `1-016-905` ASIC and
>   the same `PA28F400`. On it, pin 75 meters to flash 13, flash 13 meters to
>   ground, and flash 12 (`CE#`) meters to **CPU pin 61, `UCS`**. The remainder
>   of the edge transfers exactly: `70` to flash 11 *and* RAM 10, `73` to flash
>   3, `74` to flash 34, `76` to flash 35. Four pins agree and one pin
>   disagrees. This is a mistake in the reading, not a bond-out difference.
> * **The firmware.** The reset stub has a single function: it programs
>   `0xFFA4` (`UCS_START`) to `0x8000`. This gives a `UCS` window of
>   `0x80000`-`0xffc00`, which is 512 KiB, exactly the flash. The two images
>   do this, stock 7.3.14 and `IDSDL302.ROM`. If `UCS` does not select the
>   flash, there is no reason to program `UCS` to the size and location of the
>   flash. Read it with `CourierRom.chip_selects()`.
> * **This file contradicted itself.** It recorded `LCS` (60) and `UCS` (61)
>   both on the common `CE#` net of the SRAM pair, but the two cannot both be
>   correct. `UCS` on the flash resolves this: `LCS` takes the SRAM. Thus the
>   open probe that asked which of the two answers is closed.
>
> The same region already gave one off-by-one error, the "74 is pin 3 or pin
> 34" conflict. The text above records it as one miscounted pin. This is the
> second.
>
> We did not change the paragraph and the table below, because the address
> readings still support their reasoning. We withdraw only the `CE#` row and the
> conclusion from it.

**And the ASIC selects the flash.** Flash pin 12, `CE#`, comes from ASIC pin 75.
`UCS` is the upper chip select of the 80186. It is active at reset and fetches
the first instruction, and on this board it does not go to the boot device.

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
lines of the flash. The '573 supplies the middle lines. These two parts supply
all of the address bus of the flash. But **the select comes from the CPU**,
thus the old last sentence of this section is not correct. The readings show
that the ASIC is the **address latch** of the board, for the two memories and
across all of the bus. The next section opens again the question of whether it
is more than that.

### The fold: four address lines in, three out

The four upper address lines of the CPU arrive together, on four ASIC pins.
These pins step over the corner supply pair at `61`/`60`:

| CPU pin | line | ASIC pin |
|---|---|---|
| 29 | `A16` | 63 |
| 30 | `A17` | 62 |
| 31 | `A18` | 59 |
| 32 | `A19` | 58 |

**Four in, three out.** That is exactly what a **flat** map needs. Thus this is
no longer evidence of paging.

`UCS` decodes `0x80000`-`0xfffff`, thus in the window of the flash, system
`A19` is always 1. The flash does not need it. In word mode, `A0`-`A17` of the
part carry system `A1`-`A18`, and the ASIC sends out exactly those top three:
system `A16`, `A17`, `A18`. The fourth input line, `A19`, tells the ASIC that
the address is in the flash region. There is no reason for it to go out. Four
in and three out is a **pass-through, and the decode uses `A19`**. It is not a
fold.

Thus the argument from "the decode uses one bit" to "thus paging" **is not
correct**. Also, `CE#` is on `UCS` and not on the ASIC. Thus the
memory-controller interpretation also loses its other support.

**Also, there is no space for paging.** `UCS` decodes `0x80000`-`0xfffff`:
512 KiB, which is all of the `PA28F400`. Paging means access to a large device
through a *smaller* window. The retracted text said exactly that, "a 512 KiB
device reached through a smaller window". But the window is not smaller. The
CPU addresses each byte of the part directly. Thus there is not only no
evidence for a paging register. There is also no function for one.

**`A19` is still not explained.** It goes to the ASIC on the two boards (pin 58,
CPU pin 32, metered on the 2806 and the 2805). `UCS` holds `CE#`, thus the ASIC
does not need `A19` to gate a signal. A usual answer is that the ASIC uses it to
put its own address outputs in tri-state outside the flash region, and this
needs no register. That is a guess about *why* the line is there, not a
measurement. It is the one open item that this retraction leaves.
The position now is simple. Nobody has identified a port bit as a paging
register. Nothing in `courier_emu` pages the flash. The flat 512 KiB image of
the harness gives the same behaviour as the two boards. The flat map explains
the observation that previously gave an argument for paging. One question
remains: why does a gate array carry the high address lines, and not a latch
with the other lines? Board layout is a sufficient answer. Also, the ASIC
already holds `A0`-`A7`. Neither answer needs a register.

### The memories sit on the CPU's raw `AD` bus

Flash pin 22 (`DQ11`) goes to CPU pin 20 (`AD11`). Flash pin 31 (`DQ15`) goes
to CPU pin 28 (`AD15`). These are two data lines, one from each byte. Each goes
directly to the related multiplexed bus line, with no part between them.

Thus the flash and the SRAM pair connect directly to `AD0`-`AD15`, and they
use the strobes to separate address and data themselves. There is no buffer and
no transceiver. The ASIC has only `AD0`-`AD7`, as an **input**, for the latch.
The two use the same wires for different reasons. The 8-bit CPU port of the
ASIC shares the bus with a 16-bit memory system. It is not in front of that
system.

## The part is the DSP's entire external interface

**The ASIC is a 16-to-8 width converter.** All sixteen DSP data lines are on the
package, but only eight CPU lines are. `AD8`-`AD15` go to the SRAMs of the CPU
and do not go to the ASIC. Thus the ASIC gives a **16-bit port to the DSP and an
8-bit port to the CPU**, and this part does the conversion.

The 16-bit half is a DSP-side finding and transfers to the two boards. The 8-bit
half is a CPU-side finding and does not transfer. This is important for the
conclusion that it seems to give. [The port map above](#the-cpus-io-space)
interprets the 64 odd ports that return `0x00` in the probe as the upper byte of
a 16-bit register that nothing drives. An 8-bit CPU interface changes that
interpretation to "nothing is there". But we did the port sweep on the
20.16 MHz board and this trace on the 2806. Thus the new interpretation is a
candidate, not a replacement, until somebody reads the marking of the 2806.

**The two directions of the mailbox are physical.** `IS` (DSP pin 90) on ASIC
`114` gives DSP-to-CPU. The I/O strobe of the DSP goes to the ASIC, thus
`out @7d, 0x5e` at `0x83eb` and the writes of the stream coroutine to port
`0x60` arrive in this chip. `INT2` (DSP pin 39) on ASIC `109` gives the other
direction. It is the interrupt that the firmware arms.
[dsp-cpu-link.md](dsp-cpu-link.md) records `IMR = 0x002a`, which unmasks
`INT2`, `TINT` and `XINT`.

`R/W` on `115` and `STRB` on `116` complete the group. The ASIC can identify a
DSP read and a DSP write, and it has the strobe to time it. Thus the mailbox is
not write-only, and the polling loop has a physical read path. With `IS` and
the sixteen data lines, the ASIC has the **complete external bus control
group** of the DSP. The SRAM pair is the only other device on that bus.

**`READY` is tied high, thus all wait states come from software.** DSP `READY`
goes to `VDDD`. The C5x samples it to extend an external access. Thus no device
on the two buses can extend a DSP cycle, and this includes the ASIC. All timing
comes from the software wait-state generator of the DSP itself.
[hardware-timebase-and-audio-path.md](hardware-timebase-and-audio-path.md) uses
this as an anchor. This removes one possibility: the ASIC is **not** a bus
arbiter and cannot slow the DSP. If a mailbox read is not ready, polling must
handle it, because the hardware cannot make the DSP wait.

### The ASIC generates both timebases in the audio path

**ASIC pin 119 goes to DSP pin 96, `X2/CLKIN`.** This is the external clock
input of the DSP, not pin 97 `X1`. `X1` carries a signal only when a crystal is
connected across it, and this board gets its clock from a can. **The clock of
the DSP comes from the ASIC.**

This fact is of a different type from the other facts in this file. All other
pins carry signals that the firmware changes. This pin sets the speed at which
the DSP executes all instructions. The `ECLIPTEK EC11 40.320M` can is the one
oscillator of the board, and it supplies the CPU. The DSP gets the clock that
the ASIC makes from it. Thus the ASIC can divide, gate or stop the clock of the
DSP. Nothing in this repository considered that the machine cycle of the DSP
possibly is not a board constant. A fixed divide is the most probable case, and
we checked the timing numbers of the firmware against a real board. But this
was an assumption, not a known fact.

**ASIC pin 112 is the `MCLK` of the codec** (`AC03` pin 14), and that value
*is* known. It comes from the firmware, not from a scope.
[ac01-codec-protocol.md](ac01-codec-protocol.md) calculates it from the divider
registers of the codec. The DSP writes `A = 10` and `B = 20`, and the
`fs = MCLK/(2AB)` formula of the datasheet applies. Three sample rates, each
from an independent source, give the same result: **MCLK = 2.880 MHz**. This is
exactly `40.320 / 14`. Thus the divider in the ASIC is 14, and the pin reading
confirms the path of the signal.

This is true on the two boards. The 25 MHz crystal of the 2806 is **for the CPU
only**. The ASIC always runs from the same 40.320 MHz can. Thus the `MCLK` of
the codec and the clock of the DSP do not change between the boards. This is
why the DSP payload can be byte-identical across the two boards while the
supervisors are different. Refer to
[running-the-25mhz-image.md](running-the-25mhz-image.md).

`MCLK` is more important for the codec than for the DSP, because the codec
divides its conversion rate from it. The reference point of the datasheet is "a
16-kHz data-conversion rate and 7.2-kHz filter bandwidth for a 10.368-MHz master
clock". If `MCLK` changes, all of those values change. The sample rate has more
than sufficient evidence and is safe. But we now know that the divide that makes
it is **inside a part with registers**.

### The DSP's timer output comes back to the ASIC

Pin `113` is DSP pin 122, **`TOUT`**, the on-chip timer output of the C5x. Pin
`119` drives `CLKIN`. Thus the clock relation goes in the two directions: the
ASIC supplies the clock of the DSP, and the timer of the DSP sends a signal back
to the ASIC.

Thus a periodic hardware signal arrives at the part that generates the
interrupts of the CPU. This repository has an open question of exactly that
shape. [machine.py:596](../courier_emu/machine.py) describes `INT0` as "the
board's frame edge" and says "nothing on the CPU side produces that edge". A ROM
run replaces the edge there.

**It is a candidate and not yet more.** There is a specific problem: CPU `INT0`
(pin 62) is not connected on this board. Thus the signal from `TOUT` does not
arrive there. One of these is true: the edge comes in on `INT1` or `INT2`, or
the `INT0` reading is not correct, or `TOUT` does not carry the frame edge.
**The period of `TOUT` will give the answer.** If it is the same as the 5 ms
tick that the harness models, or the frame rate of the mailbox, the
identification is complete. Put a scope on DSP pin 122.

### The codec is the DSP's, not the ASIC's

| `AC03` pin | name | direction | DSP pin |
|---|---|---|---|
| 11 | `DOUT` | out of the codec - ADC results | 43 |
| 10 | `DIN` | into the codec - DAC data and commands | 106 |
| 12 | `FS` | frame sync | 104 |

Those DSP pins are immediately adjacent to pins that we already identified:
`TDR` on 44, `TFSX` on 105, `TDX` on 107. This is the usual pattern of the two
serial ports of the C5x, interleaved on the package. Each of the three readings
is next to its predicted neighbour.

Thus the serial interface of the codec goes to **the serial port of the DSP
itself, with no ASIC between them**. The single line from the ASIC to the codec
is the master clock. **That contradicts a claim that is still in the
repository**: [board-parts.md](board-parts.md) says that the ASIC is in front
of the codec, and thus hides the AC01/AC03 difference from the DSP. That is not
possible. Two boards run byte-identical DSP payloads with different codecs, but
this is not the explanation.

### The speaker is not on the board side

We looked for the gate of the speaker here two times, and we withdraw the two
readings. The two optocouplers are **not** the gate. `U14` and `U16` are
`H11B2` photodarlingtons, and the ASIC is on their transistor side. Thus the
ASIC receives through them. Also, a darlington opto is slow and not linear. The
audio for a call-progress speaker is already on the logic side of the barrier.
A later reading put the speaker on the `MON OUT` of the codec, with register 4
bits `DS05`-`DS04` as its volume. That gives squelch and three gains, and the
`AT` command set has exactly four states. But nobody **measured** this, and we
withdraw it fully.

We know where the speaker is *not*. On the 20.16 MHz board, we drove ASIC port
`0x00` bit `0x40` and bit `0x04` directly. This gave no sound on hook or off
hook. The speed was slow, so that you can hear each click, and only the relay
made a sound. Thus the `0x81703` pulse that ticks once for each lamp is not the
speaker, and a CPU port sweep cannot find it. The live paths are on the DSP
side. [2806-codec-mailbox-control.md](2806-codec-mailbox-control.md) traces
them. Mailbox tag `0x0f` sets a gain for a scaled copy of the ADC samples to
ASIC I/O `0x50`. The `M` handler of the CPU drives a latch on port `0x12` mask
`0x10`, and has two conditional `L` paths on masks `0x20` and `0x40`. On that
board, RAM `0x0693` read `0x22`. This value sets the monitor gain to zero and
makes the direct volume writer return without a write. Thus neither of the
programmable paths was active.

**Nobody has identified the physical speaker circuit.** Do not use codec word
`0409` and the register-4 monitor bits to say that the speaker connects to
`MON OUT`. Nobody measured that wiring.

### The DSP and the codec share one reset net

DSP `RS` (pin 127) does not come from the ASIC. It goes to pin 8 of the codec,
`RESET`. The harness drives that net from bit 1 of `0xFF56`, and models **only**
the DSP side. [machine.py:2384](../courier_emu/machine.py) floats the transfer
interface of the DSP and sets `_dsp_in_reset`, and nothing occurs to the codec.
On the board, each of those pulses also resets the codec. The conditions of
reset in the datasheet return the codec registers to their defaults. Thus, after
a DSP reset, all codec state that the firmware set before the reset is lost.
The harness does not know this.

## The reset tree

| part | reset source | how |
|---|---|---|
| the **ASIC** | `ADM707` pin 7 | active-high power-good reset, into ASIC pin `111` |
| the **CPU** | the **ASIC**, pin `52` | through `R1` (1k) into `RESIN`, CPU pin 68 - *not* the `ADM707`, whose pin 6 is unconnected |
| the **DSP** and the **codec** | the **CPU**, in software | `P1LTCH` (`0xff56`) bit 1 = `P1.1` = **CPU pin 58**, one net to DSP `RS` (pin 127) and the codec |

Thus the boot sequence is not an inference:

1. The rails come on. The `ADM707` releases the **ASIC**.
2. The ASIC releases the **CPU**.
3. The firmware of the CPU releases the **DSP** and the codec.

Each part stays in reset until the part that it depends on is ready. The ASIC
holds the `CE#` of the flash. Thus it controls whether the first instruction
fetch of the CPU can be successful. By design, the ASIC is the first part out of
reset.

**The reset of the DSP is confirmed at the two ends.** The harness drives
`DSP_RESET_PORT`/`DSP_RESET_BIT` ([machine.py:54](../courier_emu/machine.py)),
bit 1 of `0xff56`. That is `P1.1`. The board puts DSP `RS` on CPU pin 58, which
is the pin that the port-pin calculation predicted. We recovered the model from
the firmware, predicted the pin, and read it on the board.

The asymmetry has three results:

* **The CPU always runs before the DSP.** Only the CPU can take the DSP out of
  reset. Thus the wiring sets the boot sequence, not a firmware decision.
* **It is not known what holds the DSP at power-on.** The port pins of the
  80186EB come out of reset in their chip-select function, not as driven GPIO.
  Thus the level on that net in the first microseconds depends on the default
  of `P1CON` and on the pull resistor of the board, if there is one. If the net
  floats high, the DSP is *released* before the CPU loads data into its RAM.
* **There are two methods to stop the DSP.** This net is the documented method.
  The other method is the clock, which comes from the ASIC. A part that supplies
  the clock of another part can stop that part without a reset.

**Examine the 1k series resistor.** A gate array drives the reset of a
processor through a resistor. This is for damping, or to let another device
override the node. With 1k in series, a device that pulls `RESIN` low at the CPU
end wins without contention. This is the usual method to let a reset button or
a debug header assert reset on a line that a chip already drives. The other
connections on CPU pin 68 will show which of the two it is.

### And it retires an explanation the repository was relying on

[probing.md](probing.md) says that a measured limit of about 1.5 s on each probe
run comes from the **1.6 second watchdog** of the `ADM707`, "which matches the
observed bound". **The owner reports that this board uses the `ADM707` only as
a power-good reset.** Thus there is no `WDI` source to find, and no watchdog is
in use.

These items stay correct, and one item does not:

* **The observations stay correct.** Cleared RAM, a restored vector, and `AT`
  answers again. We measured these many times.
* **The reboot path of the firmware stays correct.** That file shows that the
  path clears RAM and builds the IVT again, and the state after the run agrees.
* **The cause is now not known.** Something stops those runs at about one and a
  half seconds, and it is not the watchdog of this part.

There are two candidates. One is a **software** failsafe in the supervisor,
which sees that a probe changed the vector of timer 0. This needs no hardware,
and it agrees with firmware that builds its own IVT again. The other is the
**ASIC**, which is in the reset tree and receives timer signals. If you
cooperate with the firmware, you can disarm a software reboot. That file
already recommends this method for other reasons.

If a datasheet number agrees with an observation, it is a good clue but a bad
proof. Because of the 1.6 s coincidence, nobody examined the problem more.

## The panel and the DTE interface

**The ASIC drives the front-panel LEDs.** We mapped the lamps a long time before
this trace. [probing.md](probing.md) has the table for each bit. We measured it:
we drove one bit at a time and looked at the panel. `courier_emu/panel.py`
models the latch driver. This trace adds **the part that contains the
latches**. Before it, no document connected the panel to a part.

This is important because the panel is the only output of this system that a
person can read without instruments. All other observations need the monitor at
its command loop, a flash dump, a port sweep or a meter. The panel continues to
operate through the states that these methods cannot get to. Examples are the
outage across a reset, which [the port map above](#the-cpus-io-space) shows as a
structural limit of the monitor, a call in progress, and a training sequence
that stops.

**The transceivers**: two **SN75188** quad line drivers, `U22` and `U23`, drive
out. One **`DS1489AM`** quad receiver, `U18`, receives in. This is the
1488/1489 pair, and we found one half at a time.

| `U18` output | pin | goes to | CPU pin | what the DTE sends |
|---|---|---|---|---|
| `1Y` | 3 | CPU `RXD0` | 3 | `TXD` - the DTE's data |
| `2Y` | 6 | CPU `CTS0` | 1 | `RTS` |
| `4Y` | 11 | ASIC pin 48 | - | `DTR`, most likely |
| `3Y` | 8 | *unread* | - | - |

**The DTE is on serial channel 0.** The transmitted data of the DTE arrives at
`RXD0`. `courier_emu/uart.py` models this. Its `EbSerial` docstring says
"Serial port 0 of the 80C186EB".

**`CTS0` is a real pin, but the harness simulates it.** `uart.py` models
`clear_to_send` as a substitute and sets it with each character that it
delivers. Its own comment says that the chain "is reached by the right bit for
the wrong reason". The `RTS` of the DTE comes through `U18` gate 2 to CPU pin 1.
This is a specific harness item with a target that we know is correct.

**The transmit path is asymmetric, and the design is intentional.** Receive data
goes directly from the receiver to the CPU. Transmit data leaves the CPU on
`TXD0` (pin 2) into ASIC pin 51, and ASIC pin 46 supplies the `RD` driver. The
data of the DTE gets to the CPU with no change. The data of the modem to the DTE
goes through the gate array. A part in one direction only must do something to
that direction. A possible function is to gate the receive line during handshake
or retrain. **Nobody has identified a port bit for it.**

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

Thus each modem-to-DTE signal that goes out through a 75188 goes out through
the ASIC. There are six driver inputs: `U22` gates 1-3 and `U23` gates 1-3.
Gate 4 is not used on the two parts. The six inputs are for five signals (`RD`,
`CD`, `CTS`, `DSR`, `RI`). Thus one more signal crosses than we named, or one
gate is a spare. We do not know the path of `DSR` and `RI`.

On a 1488/75188, gates 2 and 3 have two inputs each, and the ASIC is on `3B`.
The signal on `3A` is not the ASIC. It is an enable level, or a second source
that gates that output. Read that pin before you assign a signal to the gate.

**This explains a failure that the harness records.**
[The board measurements below](#measured-on-the-4-03d-board) show `CS`, `RD`
and `AA` change after `SELF TEST COMPLETED`, with no panel write near that
point. The three lamps have three *different* mechanisms. `AA` is a latch bit
that the firmware writes. `CS` is an ASIC pin with no port behind it. `RD`
follows the input of the 75188. A model that makes the panel follow the serial
signals must do this for each lamp separately.

`RD` is the only lamp that does not go to the package. Before you use that
difference, probe again from `U22` pin 2 back to the ASIC. The same reading was
incorrect two times for `CD`.

## The line side

**We found the isolation barrier, and the ASIC is on the receive side.** Pins
`19` and `22` go to optocouplers `U14` and `U16`, pin 5 of each. The parts are
`H11B2` photodarlingtons: LED in, transistor out. Pin 5 is on the transistor
side. Thus **the ASIC is on the output side of the two barriers: it receives,
and it does not drive.** The connection (collector, base or emitter) changes how
the pin is biased. It does not change which part sends and which part receives.

Two isolated inputs from the line is a known pattern. **Ring detect and
loop-current sense** are the signals that a modem of this period brings across
as logic. The firmware side already has a name for one of them: ring sense,
port `0x14` bit 1. In
[daa-line-interface-2016mhz.md](daa-line-interface-2016mhz.md), a cadence
machine samples it from a 5 ms ticker. Probably, one of `19` and `22` is its
physical source.

**The phone-line header is a module interface, not a line connection.** It has
a minimum of **twelve** positions, and three ASIC pins go to it: `37`, `38` and
`29`. Tip and ring do not need twelve pins. With the two optocouplers, there are
five line-side pins on two edges. Nobody has identified the module on the other
side. This is the largest subsystem that is not mapped.

Previously, we paired `37`/`38` as the hook drive and the ring sense. That
pairing was based on exactly two line-side pins for the two line-side signals
that have ports. But there are five pins, and an opto is a better candidate for
ring detect. We do not know what the header pair carries.

## The DIP switches

There are ten positions, and the board reads them in two different ways:

| switch | where |
|---|---|
| 1 | **CPU pin 80** (`P2.6`), read in `P2PIN` at `0xff5a` bit `0x40` |
| 2, 4-10 | ASIC bottom-edge pins 2-8 and 20 |
| 3 | ASIC pin **118** |

| ASIC pin | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 20 |
|---|---|---|---|---|---|---|---|---|
| DIP switch | 2 | 5 | 4 | 10 | 9 | 8 | 7 | 6 |

Pins `5`-`8` are a clean descending run: switches 10, 9, 8, 7. The other pins
are not in pin sequence. Thus **the port bit in which the firmware reads a
switch does not follow the position**, and that mapping must come from the
firmware. Pin 20 is away from the group, among the lamps. Read it a second
time.

**`P2PIN` bit 6 is not modelled.** `machine.py` models bit 7 as the data line of
the 93C66, and bit 5 as the serial receive that the autobaud timer of the ROM
samples ([machine.py:2340](../courier_emu/machine.py),
[machine.py:2345](../courier_emu/machine.py)). A read of bit 6 returns the value
that the emulated register holds at that time, not a switch position. (A comment
near that code calls `ff5a` an "ASIC latch". This is not correct: `0xff5a` is
the `P2PIN` of the 80186EB itself. The behaviour does not change, but the name
is wrong.)

**Switch 1 is the DTR override, and two firmware families read it at a
different location.** The owner reports its function: off is DTR normal, on is
DTR always asserted. Thus, possibly `P2.6` carries the DTR *signal* and not the
switch. A short of the sense line to its asserted level gives the same
behaviour, with no firmware involvement. The behaviour cannot show which is
correct. But `courier_emu/panel.py` maps `dtr-override` to ASIC port `0x12` bit
`0x20` on the XMF supervisor (recovered at `0x63d31`/`0x63d48`). The 302/403
ROM builds read the same switch on the same port bit through a different
selector. Thus, on the two firmware families that we mapped, it is a strap that
the firmware reads through the ASIC. If the 2806 sends it to `P2.6`, that is a
**third** switch wiring. This is possible, but it needs more than one continuity
reading.

**The strap scan is real, but it is not these switches.** In `panel.py`,
`id-strap-drive-a`..`d` and `id-strap-sense` are a matrix with four drives and
one sense. We recovered it from the scan of the supervisor at `0x5bfc6`:

| line | port | bit | driven at |
|---|---|---|---|
| `id-strap-drive-a` | `0x14` | `0x40` | `0x5bfed` |
| `id-strap-drive-b` | `0x12` | `0x02` | `0x5c001` |
| `id-strap-drive-c` | `0x14` | `0x10` | `0x5c015` |
| `id-strap-drive-d` | `0x14` | `0x20` | `0x5c03d` |
| `id-strap-sense` | `0x14` | `0x08` | *read* |

Four drives and one sense read four **board-ID straps**, one time at boot. This
is a different physical item from the DIP bank. This file had merged the two,
because nobody had read either of them. Eight switches on eight dedicated pins
is not a matrix. Four drive lines are there to save pins, but this part used the
pins. Now the count is correct: ten switches, one on the CPU and nine on the
ASIC.

### The unpopulated four-switch footprint

The owner reports a location for a second DIP bank of four, with no parts
installed, near the serial connector. The owner suggested that it possibly
selects between the two serial channels of the CPU.

**One probe showed that this is not correct: CPU pin 8, `TXD1`, is not
connected.** A UART channel with a transmit pin that is not connected is not a
port. Thus serial channel 1 of the CPU is not used, and there is no second
serial path to select.

The remaining items are a coincidence, not a mechanism. There is a spare
receiver channel (`U18` `3Y`), two spare driver gates (`U22` and `U23` gate 4)
and a UART that is not used. All are real, and none connect to each other.
Spare gates on a quad part are usual. The footprint has a different function.
Probe its pads against the three unread bottom-edge pins and against ground,
because the common of the installed bank is grounded.

**A bank that sends a signal on a different path needs no port bit.** That is
the pattern of the suggestion of the owner, and that pattern leaves no trace in
the image. `panel.py` names eight option switches that the supervisor reads,
but there are ten wired positions. Thus two positions already change no bit
that the firmware examines.

## The second serial port goes to a debug header

[dsp-cpu-link.md](dsp-cpu-link.md) asked this question and could not answer
it. The idle task drives `TDX` all the time, and nothing showed where the data
went.

| DSP signal | DSP pin | lands on |
|---|---|---|
| `TDX` | 107 | `J7` pin 2 |
| `TDR` | 44 | `J7` pin 4 |
| `TFSX` | 105 | `J7` pin 6 |

It does not connect to a part on the board. It comes out for instruments, and
the firmware drives it on each pass of the idle task, also when no device
receives.

**That is a live diagnostic stream on real hardware.** It is a fourth source,
after the monitor, the flash images and port sweeps. Unlike the monitor, it does
not need the supervisor at its command loop. We do not know what the stream
contains.

We did not trace `TCLKX` (123) directly. But there is a 100 ohm resistor from it
to `TCLKR` (126). This is series termination, which is correct for a clock that
goes off the board into a header. It also explains why `TCLKR` has no source of
its own. This agrees with a stream in one direction out to `J7`. The receive
half is wired for completeness, but it is never read: `TDR` is on the header,
but no instruction reads it.

## The EEPROM is the CPU's

Two parts of `courier_emu` disagree about the access path to the Atmel serial
EEPROM. `panel.py` puts `nvram-strobe`, `-data-in`, `-chip-select` and `-clock`
on ASIC port `0x10`. `machine.py` drives the same 93C66 from the CPU. On this
board, `machine.py` is correct, and each predicted net is confirmed:

| 93C66 pin | net | CPU pin | harness register |
|---|---|---|---|
| 1 `CS` | chip select | 52 (`P1.5`) | `0xff56` bit `0x20` |
| 2 `SK` | clock | 57 (`P1.2`) | `0xff56` bit `0x04` |
| 3 `DI` + 4 `DO` | one shared net | 79 (`P2.7`) | `0xff5e` / `0xff5a` bit `0x80` |
| 5 `GND` | ground | - | - |
| 6 `ORG` | **floating** - selects x16 | - | - |
| 7 `DC` | floating - no bond inside | - | - |
| 8 `VCC` | supply | - | - |

**The shared data net is the special one.** `DI` and `DO` are separate pins on
the chip. One net that carries the two is not an accident. It is exactly what
`machine.py` assumes when it drives `P2LTCH` and then samples `P2PIN` for the
same bit. We **recovered that model from the driver in the ROM**. We inferred it
from the sequence of register writes, and we read the shared pin from the code,
not from the board. Now the board shows the same result.

**A floating `ORG` is a setting, not a gap.** On the Atmel part, an unconnected
`ORG` has an internal pull-up and selects x16: 256 words of 16 bits, 512 bytes.
`courier_emu/nvram.py` already models this. We selected it because the driver
reads and writes words, and the boot block copies 512 bytes. We read the
marking. Thus the pull-up comes from the datasheet, and this is specification,
not inference.

This also completes the chip-select allocation of the CPU:

| CPU select | goes to |
|---|---|
| `GCS0` (pin 59) | the ASIC |
| `LCS` (pin 60) | both SRAMs' `CE#` - but see `UCS` |
| `UCS` (pin 61) | **a RAM's pin 20** (`CE#`) - *not* the flash, which the ASIC selects |
| `P1.2/GCS2` (pin 57) | **not a select** - EEPROM clock, driven as GPIO |
| `P1.5/GCS5` (pin 52) | **not a select** - EEPROM chip select, driven as GPIO |

The firmware uses two generic selects as usual outputs. It sets this explicitly
through **Port 1 Control at `0xff54`**: bit 0 set, bits 2 and 5 clear. Nothing
in `courier_emu` reads it.

These mappings came from different firmware families: the ROM builds for the CPU
path, the XMF supervisor for the ASIC path. Thus this result applies to the
2806, and it tells nothing about the other board.

## The interrupt map, and why it is not yet a discrepancy

On this board, CPU `INT0` (pin 62) is not connected, and the ASIC drives `INT1`
and `INT2`. On the 80186, `INT2` is interrupt type 14, `0x0e`. `machine.py`
models the frame edge of the board as `INT0`: `INT0_VECTOR = 12`, type `0x0c`
([machine.py:585](../courier_emu/machine.py)).

These do not agree, but it is **not yet a harness bug**. The harness models the
20.16 MHz board with ID_SDL 302/403. The pin reading is from the 2806 with stock
7.3.14. The CPU side is the half that does not transfer. Two boards can wire
their interrupts differently.

Thus there are two questions, and only one is open here. **On the 2806**, which
vector does `INT2` get to? **On the 20.16 MHz board**, is the frame edge `INT0`?
Nothing above gives evidence for the second question. To answer it, read the
`INT0` pin of that board.

The two checks are easy, and neither needs a scope. The IVT is at physical `0`
and is RAM, and the monitor reads it. [probing.md](probing.md) already uses this
method. **Read vectors `0x0c` and `0x0e`.** The vector that holds a real far
pointer into flash is the edge that the ASIC of that board drives. The interrupt
control registers of the 80186 give a second method.

## Measured on the 4.03d board

| what | board | emulator | where |
|---|---|---|---|
| identity | `7.4.16` / `3.1.2`, serial `0009540034268322` | same | `ATI7` |
| transmit levels | `[0cd9]=32c8`, `[0cdb]=0c08` | matches with `idsdl403` | [datapump-dispatch-gate.md](datapump-dispatch-gate.md) |
| settings page | `B0 F1 M1 X7 &A3 &B1 &G2 &H1 &I0 &K1 ...` | same | `ATI5` |
| NVRAM self test | `TESTING NVRAM  OK` | same | `0x81412` |
| product code | `5607A` | same | `ATI0` |
| ROM checksum | `6C04` | same | `ATI1` |
| self test | runs only with the front panel button held | same, `--port 0x14=0xb5` | `0x877cd` |

The self test gives the same result line for line, through the dipswitch page
to `SELF TEST COMPLETED`.

### The settings EEPROM

The boot block copies all of the 512-byte part into RAM `0x058e..0x078d`, and
calculates its checksum there at `0x81412`. Byte 511 holds the sum of bytes
0..509. The routine adds byte 510 and then removes it again immediately.

Because of that window, `artifacts/courier-board-21210-ram-403/` contains the
part itself. `CourierNvram.idsl403_fixture()` is those 512 bytes, not
synthesised data. Three items of evidence show that it is the store. It is
identical across the two capture passes. Its stored byte `0xbd` agrees with the
rule, where the adjacent ranges give `0xbe` and `0xbc`. It has the +S register
block at the offset that we calculated from the ROM before we read the capture.

**A fixture with a valid checksum over erased bytes is worse than no fixture.**
An intermediate revision did that. The firmware accepted the erased profile, and
the run lost all of its DTE output.

### The front panel

`0x877cd` starts the self test only when port `0x14` bit `0x40` reads low. Then
`0x87e34` loops while it is still low, which is a contact that the user
releases. It is the button, not a DIP switch. Because `carrier-detect-override`
was mapped onto it, each `--dip-preset dedicated-line` run booted into the self
test.

The lamp stage goes through a table of nine entries at `0x8275f`, one line for
each ~281,500 instructions:

| idx | port/bit | lamp | idx | port/bit | lamp |
|---|---|---|---|---|---|
| 0 | `0x12`/`0x10` | HS | 5 | `0x12`/`0x02` | MR |
| 1 | `0x14`/`0x40` | *no lamp - the button* | 6 | `0x14`/`0x02` | **CS** |
| 2 | `0x14`/`0x10` | **AA** | 7 | `0x14`/`0x80` | **SYN** |
| 3 | `0x14`/`0x01` | **CD** | 8 | `0x14`/`0x20` | ARQ/FAX |
| 4 | `0x10`/`0x01` | OH, and the relay | | | |

The four bold lamps are measured. We drove them one at a time with
`ATGLK2O0014` against a rest state of `0xff`, and looked at the panel. Each bit
had a different blink count, thus we could not confuse them. CS is different
from the others: it goes off each time the port is released. Thus this latch
drives it, and it idles low.

The other five come from the release sequence that we read from the board, and
the alignment checks itself. Exactly one of the nine steps did nothing that we
saw. It is on `0x14` bit `0x40`, the button, which has no lamp. Thus we did not
have to assume the location of the silent step.

    bit 0x01 (0xff <-> 0xfe)   CD blinks alone
    bit 0x10 (0xff <-> 0xef)   AA blinks alone
    bit 0x80 (0xff <-> 0x7f)   SYN blinks alone Index 4 reads as a
lamp that *comes on* in the middle of the sweep, not one that goes off. This is
true in the sequence of the board and in the emulated run. This identifies OH
and the relay as one line.

Port `0x14` reads its **inputs**, not this latch. `0xfe`, `0xff` and `0x7f` all
read back as `0x7e`. Thus you cannot read the rest state. It is `0xff`, which is
the value that `0x82803` writes to release. A first attempt used the `0x7e` read
as its baseline, which held the two bits driven all the time. It reported that
CD and SYN changed together from bit `0x80`. That result came from the
baseline, not from the board.

**This table shows which latch bit lights which lamp during the test. It does
not show that the supervisor drives that lamp in service, and usually it does
not.** RD, SD, TR, RS and CS are RS-232 signals before they are lamps, and they
follow the wire. Across a full dial of 150M instructions, the panel gets 23
writes. `carrier-detect-a` and `carrier-detect-b` are never driven. All changes
come from the board-ID strap scan at boot and from the hook relay. The lamp
stage is a lamp *test*. The firmware takes control of lines that it usually
leaves to the hardware, so that you can see each lamp. Thus the sweep is
satisfactory to name the lamps. But you cannot reverse the result into "the
supervisor controls this lamp".

#### Two bits conflict with dsp-rom-probe, on this same board

[probing.md](probing.md) has its own single-bit strobe table, from this unit
(`/dev/cu.usbserial-21210`, serial `0009540034268322`). It lists the same nine
self-test entries in the same sequence. Five attributions agree exactly: CD on
`0x14` bit 0, CS on bit 1, ARQ on bit 5, SYN on bit 7, MR on `0x12` bit 1.
**Two do not agree:**

| bit | dsp-rom-probe | this file |
|---|---|---|
| `0x14` bit 6 (`0x40`) | HS lamp, observed | *no lamp* - the front-panel button |
| `0x12` bit 4 (`0x10`) | analog path, audible pop | HS lamp |

The two sides are panel observations that the user reported, thus neither
transcript gives the decision. The firmware gives the decision. `0x877cd` starts
the self test only when port `0x14` bit `0x40` **reads low**. Then `0x87e34`
loops while it is still low. That is an input that the user releases, and a lamp
drive does not do that. Also, the sweep here saw nothing occur on that step.

**To get the answer, strobe the two bits again one at a time.** Look at the
panel and listen. Strobe `0x14` bit 6 from a rest state of `0xff`, and `0x12`
bit 4 from its shadow. If bit 6 lights nothing and `0x12` bit 4 lights HS, this
file is correct, and the two rows of dsp-rom-probe move. Until then, do not use
either attribution as a base for more work.

### The hook

Port `0x10` bit `0x01` drives the relay and the OH lamp together, **active
high**. `0xdf` energizes the relay, and `0xde` releases it. Chip-select stays
low all the time. The model had the hook on bit `0x04`, active-low. A dial
asserts the two bits: `0x01` at `c8fbe`, and `0x04` about 43,500 instructions
later at `c8fe1`. Thus the incorrect bit still gave an off-hook, but late.

`[0x020d]` bit `0x02` copies the hook state: `0x09` on-hook, `0x0b` off-hook.
We changed it when we energized the relay manually with `ATGLK2O0010,DF`. All
other candidate cells were identical between board and emulator. **The emulator
never writes `[0x020d]`.** A `--mem-watch 200:220` across a full dial finds 96
writes in that range, and all are to `[0x0210]`. The predicate at `0x8b449`
tests bit 0 of this same cell before its success branch. Thus the cell is on
the path.

### Two port read-backs

| port | board | emulator |
|---|---|---|
| `0x10` | `0x86` on-hook, `0x87` off-hook | `0xff`, with the NVRAM bits overlaid |
| `0x00` | `0x00` | `0x33` on the input bits |

On the board, port `0x10` bit `0x01` copies the hook state, but the emulator
answers open bus. Thus, if a firmware routine reads the port back to update
`[0x020d]`, it gets the information that the line is always off hook.

Port `0x00` is worse, because this project selected that value. We set it to
answer `PORT0_INPUTS` high, because an answer from the latch removed the option
list from `ATI7`. The board answers `0x00`. The four bits are not capability
inputs that read high. The guess was wrong, and the cause of the change in the
option list is still not known.

The general shape of the port space is in
[the port map above](#the-cpus-io-space). Only even ports decode, the decode
stops at `0x7f`, and the idle default is `0x00` where the harness returns
`0xff`.

## The output latches, and how to drive them safely

`ATGLK2O` writes CPU I/O ports. Thus you can drive the three output latches at
`0x10`, `0x12` and `0x14` from the AT interface. Part of the text below is
physical **write** evidence. These were the first writes of any type to a unit
in this investigation.

Two helpers drive the latches: `0x2771` (set bits) and `0x279b` (clear). The
port table is at `0x27c7`. `AH` is the bit mask, and `AL` is a descriptor. Bit 3
of `AL` must be set. `AL & 3` selects the port and the RAM shadow:

| `AL` | port | shadow |
|---|---|---|
| `08` | `0x10` | `[0x30e]` |
| `09` | `0x12` | `[0x30f]` |
| `0a` | `0x14` | `[0x310]` |
| `0b` | `0x12` | `[0x311]` - no call site uses it |

**The latches are write-only.** A read of `0x10`/`0x12`/`0x14` returns input
signals, not latch contents. This is why the firmware keeps shadows and does a
read-modify-write against them with `cli` protection. Initialization at
`0x2728` fills `0x30e..0x312` with `0xff`, then sets `[0x30e]=0xfe` and
`[0x30f]=0x7f`. The captured idle RAM holds `fe 7d f5 ff` at `0x30e..0x311`.
You can read it live with `ATGLK2=0000:0300`. Nothing reads `[0x310]`, and there
is no direct `out 0x14` in that bank. Thus port `0x14` holds the written value
until the next helper call.

**`O` is a bare `out dx,al`.** It writes all eight bits and does not update the
shadow. Thus you must make a single-bit write manually from the current shadow.
`ATGLK2O0014,40` does not set bit 6. It clears the other seven bits. After a
write, the shadow and the latch disagree. The firmware trusts its shadow and
does not restore the latch itself. A changed bit stays changed until an explicit
write or a power cycle. We saw this: when we set `0x12` bit 1, MR went off and
stayed off. The read-modify-write of the firmware has interrupt protection. A
shadow read followed by a separate `O` write is not atomic against it.

### Do not write port `0x10`

`0x1490` starts from `[0x30e]`, sets bit 5 high and bit 3 low, and does
`out 0x0e,0x6f` to select. Then it toggles bit 6 as a clock, and `in al,0x10`
reads data back. `0x1540` restores the shadow and writes `out 0x0e,7`. That is
the bit-banged serial EEPROM that holds the saved profiles of the modem. The
same pattern occurs again at `0x27a6e..0x27b64` in another bank. Direct
`out 0x10` writes drive these bits and do not use the helper API. Thus a scan of
the helper call sites does not find them. **An arbitrary byte written to port
`0x10` can clock the NVRAM interface.**

### Confirmed function of the driven bits

We found these functions when we strobed single bits on a physical unit and
looked at the front panel. These are observations that the user reported, not
captured transcripts. Port `0x14` is active low: `0` lights the indicator.

| port | bit | function | evidence |
|---|---|---|---|
| `0x14` | 0 | CD lamp | observed |
| `0x14` | 1 | CS lamp (lit at idle) | observed |
| `0x14` | 2 | - | no driver located |
| `0x14` | 3 | driven, no visible effect | `0x22d6`/`0x22f3` |
| `0x14` | 4 | AA lamp | observed |
| `0x14` | 5 | ARQ lamp | observed |
| `0x14` | 6 | HS lamp | observed - **disputed, see below** |
| `0x14` | 7 | SYN lamp | observed |
| `0x12` | 1 | MR lamp (lit at idle) | observed |
| `0x12` | 3 | untested | `0x267d`/`0x269d`, gated on `[0xdfd]` |
| `0x12` | 4 | analog path: audible pop | observed - **disputed, see below** |
| `0x12` | 5 | untested | `0x25d0`, gated on `[0x693] & 6` |
| `0x12` | 7 | forced low at init, no driver | `0x2737` |
| `0x10` | 0 | CD line to the DTE | `0x92b1`/`0x9380` set on connect, `0x93a2`/`0x93d9`/`0x96a7` clear on teardown, all gated on `[0x5b4] & 2`; `0x0b45` clears on timer expiry |
| `0x10` | 3, 5, 6 | serial EEPROM bit-bang | `0x1490`..`0x15a5` |

> **Two rows conflict with [the board measurements below](#measured-on-the-4-03d-board), which
> strobed the same bits on this same unit.** That sweep puts **no lamp** on
> `0x14` bit 6, and identifies it as the front-panel button. The firmware
> supports this: `0x877cd` starts the self test only when that bit *reads low*,
> and `0x87e34` loops while it stays low, which is an input that the user
> releases. It puts **HS** on `0x12` bit 4, where the row above records an
> audible pop. Five other attributions agree exactly between the two. The two
> sides are panel observations that the user reported, thus neither transcript
> gives the decision. To get the answer, strobe those two bits again one at a
> time, and look and listen. Until then, do not use either attribution as a
> base for more work.

Port `0x14` bit 0 drives the CD *lamp*, and `0x10` bit 0 drives the CD *line*.
This is consistent: `&C` controls the line, and the lamp follows carrier. The
panel indicators with no latch bit are RD, SD, TR and RS. We expect that the
hardware connects these to the UART and the control lines.

### The self-test table, and why strobing was considered safe

`0x26a8` goes through a table of nine entries at `cs:0x26f2`. It calls clear on
each entry, waits, then calls set on each entry with interrupts masked. A
dispatcher at `0x26247` gets to it with `lcall 8000:26a4` when the parsed value
is `5`. We have not identified the AT syntax that gets to that dispatcher.

| entry | `AX` | port | bit | entry | `AX` | port | bit |
|---|---|---|---|---|---|---|---|
| 0 | `1009` | `0x12` | 4 | 5 | `0209` | `0x12` | 1 |
| 1 | `400a` | `0x14` | 6 | 6 | `020a` | `0x14` | 1 |
| 2 | `100a` | `0x14` | 4 | 7 | `800a` | `0x14` | 7 |
| 3 | `010a` | `0x14` | 0 | 8 | `200a` | `0x14` | 5 |
| 4 | `0108` | `0x10` | 0 | | | | |

The firmware itself drives each of these in the two directions. Thus, a manual
drive gets to no state that the firmware does not also get to. **That argument
is still correct. But the interpretation that the group is only front-panel is
not correct.** Entry 0 made an audible pop, thus this is a larger self-test than
a lamp test. Entry 4 is on port `0x10`. Do not include it, because of the NVRAM
risk above, although it is in this table. The firmware drives port `0x12` bits 3
and 5, but they are *not* in this table. Thus this argument does not apply to
them, and we now know that the latch gets to the analog path.

### Port `0x14` bit 2, probed 2026-09-04

The live shadows read `fe 7d f5 ff`, which is exactly the same as the earlier
RAM capture. Thus the strobe was `f1` and the restore was `f5`. The sequence was:
`AT`, `ATI7`, `ATGLK2=0000:0300`, two `ATGLK2B0000` sweeps, the write, two
sweeps, the restore, two sweeps. Each phase needed two byte-identical sweeps
before we accepted it, and the restore was in a `finally` block. The data is in
`artifacts/io-latch-bit2-01/`.

**Zero of the 256 ports changed while bit 2 was held low**, and the sweep after
the restore is byte-identical to the baseline. Port `0x14` has no refresh path.
Thus the bit really stayed low across the two sweeps between the write and the
restore.

That is a null result about **feedback, not function**. A sweep sees only the
data that the CPU can read back. A latch bit that goes to a DSP pin, a lamp or
an analog gate does not show in the peripheral bank. The result shows that bit 2
does not connect to anything that the supervisor can see through I/O space. It
also shows that the write/restore cycle changes nothing else. We did not check
whether the bit is visible on the front panel.

### Bearing on the DSP

No bit that the firmware drives is a DSP control line. Each one is a front-panel
indicator, a DTE control line, the NVRAM interface or the analog path. But that
does **not** show that the latch bank contains no DSP control. `0x14` bit 2,
`0x12` bits 0, 2 and 6, and `0x10` bits 1, 2, 4 and 7 have no driver that we
found. If there is no driver, this is not evidence that nothing connects to the
pin. The positive evidence that DSP reset is at a different location is that
`0xe3ab`/`0xe429` drive `[0xff56]` bit 1 directly. That is a CPU port pin, not
an ASIC latch. This applies to reset only. It does not exclude a different
DSP-related strap or enable.

## Which DSP: a 'C51, measured

The core models a 'C52. **It is not a 'C52**, and the firmware shows this in
three ways.

**It is also not a C2x.** A census of 1200 words finds `splk` (98), `samm`
(71), `lamm` (31), `bsar` (32), `bd` (32), `calld` (31), `retd` (36), `retcd`
(108), `lacc16` (21), `bcnd` (48), `bldd` (13), `smmr` (19), `lmmr` (2) and
`apl`/`opl`/`xpl` (14). None of these has a C2x encoding. A TMS320C25 cannot run
this program. The C50, C51, C52 and C53 have the same instruction set and
different on-chip memory. Thus the census sets the family, and the **memory
map** must select the member.

SPRU056D Table 1-1, on-chip memory in 16-bit words:

| device | DARAM | SARAM | ROM | serial ports |
|---|---|---|---|---|
| 'C50 | 1056 | **9K** | 2K | 2, includes TDM |
| 'C51 | 1056 | 1K | 8K | 2, includes TDM |
| 'C52 | 1056 | **none** | 4K | **1**, no TDM |
| 'C53 | 1056 | 3K | 16K | 2, includes TDM |
| 'LC56 | 1056 | 6K | 32K | 2, BSP |

**1. The firmware maps SARAM that a 'C52 does not have.** Its prologue is:

```text
8014  apl @07, #07f8      ; keep bits 3-10
      opl @07, #00b0      ; set bits 4, 5 and 7
```

On a C5x, bit 4 is `PMST.RAM` and bit 5 is `PMST.OVLY`. These two bits map
on-chip SARAM into program space and overlay it into the two spaces. A build
sets them only on a part that has SARAM to map. Bit 7 is the LSB of `IPTR`. It
puts the vector table at `0x0080`, which also needs on-chip memory there. On a
'C52, all three bits have no function.

**2. `0x23f0` agrees only with the 9K part.** The mailbox dispatcher of 302 and
its stream resume poll both do `calld 0x23f0` on each pass. That address is
below the external RAM, thus it must be on-chip. With `PMST.RAM` set, the guide
gives the program range of the 9K SARAM as **`0x0800`-`0x2BFF`**. A 3K part
gets only to `0x13ff`, a 1K part to `0x0bff`, a 6K part to `0x1fff`. **Only the
'C50 includes `0x23f0`.**

Data space agrees. Table 8-8 with `OVLY=1` puts SARAM at `0x0800`-`0x2BFF`. The
block clears of the prologue are at `0x0100-0x04ff`, `0x0800-0x08ff` and
`0x0b80-0x0bff`, and the mailbox ring of 302 is at `0x0bd0`. All of these are in
that range.

**3. The 'C52 has one serial port and no TDM.** But this firmware configures
`TSPC`, the TDM serial port control register, and the idle task transmits on
that port all the time.

> **The 403 build does not need the 9K.** It puts the same helper in the bank at
> `0x80e8`. Thus only the older build gets to `0x23f0`. On this evidence, a
> board with 403 can be a **'C51**: 1K SARAM at `0x0800`-`0x0bff` still includes
> the ring at `0x0bd0` and the clears of the prologue. The 'C52 is excluded on
> all builds.

**4. The package suffix gives the same result.** `TI DSP 16-912 (C) US ROBOTICS
**D17140PQ**`: `PQ` is the TI suffix for the 132-pin BQFP. The 'C50, 'LC50,
'C51 and 'LC51 have it. The 'C52 is **PJ**, and the 'C53 is also not a PQ part.
The pin work above already used the *PQ* pinout of SPRU056D Table A-4 to find
`VDDD` and `IS`. Thus this was already in the evidence, but nobody saw it. The
remainder of the marking is a custom USR number and gives no information.

### It is a 'C51, and the 2K dump was a quarter of the ROM

**Measured 2026-09-13** on the 25 MHz board, not inferred:
[artifacts/dsp-memory-test-2806](../artifacts/dsp-memory-test-2806/README.md).
The test writes two patterns through data space, and reads the same addresses
back through program space. SARAM seen from the two spaces is one physical
memory and must follow the write. ROM cannot follow it.

| address | data write lands | program space follows |
|---|---|---|
| `0x0800` | yes | **no** |
| `0x1800` | yes | **no** |
| `0x2400` | yes | **yes** |

With `MP/MC=0` and `PMST.RAM=1`, a 'C50 maps 9K of SARAM into program space over
`0x0800`-`0x2BFF`. Thus all three addresses would follow. The observed split is
the 'C51 map: **8K of on-chip ROM at `0x0000`-`0x1FFF`** has priority over SARAM
in program space, and writable memory is above it.

| | SARAM | **ROM** | serial | verdict |
|---|---|---|---|---|
| 'C50 / 'LC50 | 9K | 2K | 2 | excluded by the write-readback |
| **'C51 / 'LC51** | **1K** | **8K** | 2 | **the part** |
| 'C52 | none | 4K | 1 | excluded by the `PQ` suffix and by SARAM use |

We read all of the 8K into
`artifacts/dsp-onchip-rom-2806/c5x-onchip-rom-8k.bin`, and most of it is not
programmed. It contains 1920 words of boot code at `0x0000`-`0x077F`, a
128-word mailbox block at `0x1F80`, and 6144 words of a 32-word `FFFF`/`0000`
array pattern. Since then, we also read all of the part of the 20.16 MHz board.
It agrees byte for byte at all programmed locations of the ROM. `0x0780`-`0x07FF`
has that same pattern. Thus the old 2K capture did not stop at a boundary. It
went past the end of the programmed part.

### MP/MC is 0, and this file said 1

`PMST` sampled on the board reads `00b0`: `IPTR` 0, `AVIS` 1, `OVLY` 1, `RAM` 1,
**`MP/MC` 0**. This is microcomputer mode. Previously, nobody had read `MP/MC`
directly. Now this caveat is closed, and the answer is the opposite of the
assumption in the text below and in [board-parts.md](board-parts.md). That
assumption was that the firmware runs MP/MC=1, and thus that the on-chip ROM
window does not exist. The window exists, and it is 8K.

`RAM` and `OVLY` also read as **already set on entry**, before each kernel in
`dsp_probe.py` executes the `opl @07, #0030` instruction. That instruction never
changed anything.

**We did not update the memory-map rows below for this.** We wrote them for
MP/MC=1 and a 2K ROM, and we now know that both are wrong. The measured data is
the table above.

### What that means for the core

`native/c5x_core.h` gives the part 4K of program ROM, three DARAM blocks and
**no SARAM**. Thus `PMST.RAM` and `PMST.OVLY` have no effect, and all addresses
from `0x0800` up are `External`. The three memory-map figures of the guide agree
with the core at all locations *except* these:

| region | guide | core |
|---|---|---|
| program `0000`-`003F`, MP/MC=1 | external (vectors) | external |
| program `0800`-`2BFF` | **SARAM if `PMST.RAM`**, else external | external, always |
| program `2C00`-`FDFF` | external | external |
| program `FE00`-`FFFF` | DARAM B0 if `CNF`, else external | same |
| program `0000`-`07FF`, MP/MC=0 | 2K on-chip ROM | **4K**, `0000`-`0FFF` |
| data `0000`-`004F` / `0050`-`005F` | registers / the 16 I/O ports | same |
| data `0060`-`007F` / `0100`-`02FF` / `0300`-`04FF` | B2 / B0 / B1 | same |
| data `0800`-`2BFF` | **SARAM if `PMST.OVLY`**, else external | external, always |
| data `2C00`-`FFFF` | external | external, less the shared window |

**Thus the necessary correction is to the memory map, not only to the part
number**: SARAM mapped by `PMST.RAM`/`OVLY`, not a stub. Nobody has made or
tested this correction. The ROM row is a harness fixture, not a claim about the
board. The firmware runs MP/MC=1, where that window does not exist. The probe
kernels in `dsp_probe.py` and `fsk.py` use microcomputer mode to hold their own
4K synthetic drivers.

**Also, the shared external window is usual, not a trick.** The guide puts
nothing on-chip above `0x2BFF` in data space. It also puts nothing above it in
program space with `CNF` clear, and this firmware runs with `CNF` clear. Thus a
reference to `0x8000`-`0xFEFF` is an off-chip bus cycle in **the two** spaces:
the same address on the same pins. If one RAM answers the two, the board does
not separate the two strobes. The `bldp` of 302 from data `0x80f5` needs this.

> An earlier reading said that the 9K SARAM decodes "with A15-A14 ignored", and
> thus mirrors. That is **Table 8-15, address ranges during external DMA**. It
> applies to a DMA master that gets access to the SARAM, not to the program and
> data addressing of the CPU itself.

### Its program memory is RAM, above `0x8000`

The bridge does not assume the transfer. It collects the actual download stream
of the supervisor and compares it with the image. Each run reports
`bootstrap_match: true` at `bootstrap_bytes: 60344`. That is 30,172 words, all
of the resident segment.

> **Corrected 2026-09-15.** The origin of that segment is `0x8000`, not
> `0x0000`. Thus this gives no information about the mask-ROM window. `0x0000`
> was a constant in `courier_emu/xmf.py`. The download call site of the
> supervisor names the destination that it requests. For 2.1.1 and 2.2.05 that
> is `8000`, and the other rows of the overlay table are at `9d00`, `af50` and
> `dc00`. Each branch target in the payload has bit 15 set. At origin `8000` this
> needs no explanation, but at origin `0000` it needed a mask. The download
> match is a content match. It never found the location of the words. Refer to
> [hardware-timebase-and-audio-path.md](hardware-timebase-and-audio-path.md#3-corrected-the-xmf-payload-loads-at-8000-not-0000).

Thus the supervisor transfers 30k words into the external RAM at `0x8000`, and
it addresses nothing below that address. A part with mask ROM in its low 8K
needs this. It also agrees with the `MP/MC`-low measurement in
[which DSP: a 'C51, measured](#which-dsp-a-c51-measured). The 2.3.x XMFs do not
agree with it: their table loads at `1000`, with one row at program `0000`.

The two `CY7C199-15VC` give 64 KB = **32K words, exactly `0x8000`-`0xffff`**.
This is the range that the downloads of the supervisor fill (`0x8000`-`0xf8b5`
on 302, `0x8000`-`0xf949` on 403, about 31K words). The size of the part is
correct for the function, with a small margin.

## The codec, and a withdrawn identification

| board | part on the DSP's serial port |
|---|---|
| the 20 MHz boards | **TLC320AC01** |
| the 25 MHz Courier 2806 | **TLC320AC03** |
| the 3453C - taken to be `main211.xmf` | **Si3021 + Si3014**, no TI codec |

Three generations, one part each, reported by the owner from the units in hand.
TI first, Silicon Labs last.

**The firmware does not prove the part, and a claim that it did is withdrawn.**
The 16-word control table at program `0x019c` - `0911 0967 0956 0934 0923 0969
0989 bc07 1019 ba01 9019 f788 be4c 7718 8b8f 8711` - was offered as proof of a
TLC320AC0x. It appears in `main211.xmf` **and nowhere else**, and `main211`'s
board is the one carrying **no TI codec at all**. So that table is the bring-up of
the Silicon Labs pair, and the claim was exactly inverted. (This rehabilitates
`CodecBringUp`, which runs an `SI3038.PDF` sequence: a Silicon Labs sequence is
the right family for that build, and only the part number is in doubt.)

The secondary-frame protocol - bit 0 of the transmitted DAC word requesting a
control frame - cannot discriminate either, because it appears on both sides of
the split: in `main211` (Si pair) and in the ID_SDL 4.03 build for an AC01 board.
A protocol common to both is evidence about serial framing, not about silicon.

**The AC01-to-AC03 change is invisible to the DSP**, and the reason is not the
ASIC. An earlier explanation had the ASIC fronting the codec so the DSP need not
know which variant is fitted; the continuity readings put `DOUT`, `DIN` and `FS`
straight onto DSP pins 43, 106 and 104, with the ASIC's only line being `MCLK`.
The simpler explanation survives and needs no ASIC: **AC01 and AC03 are the same
family**, same protocol, same register map, so identical DSP code drives either.

## The flash is Intel and the harness models an AMD part

The 2806's flash is marked `PA28F400`, Intel's 4 Mbit boot-block part.
`courier_emu/flash_device.py` models an **AMD Am29F400AT**, device code `0x2223`,
with that part's eleven-sector top-boot map hard-coded as fixed geometry.

Those disagree, but not yet in a way that is demonstrably a bug. The AMD choice
was never read off a board: it was **inferred from the update image**,
`Ie030002.nac`, which probes for a manufacturer word and takes the AMD path when
Intel does not answer. That image is the I-modem's, not the 2806's.

What makes it worth recording is that the sector map is load-bearing: the file
reasons from the Am29F400AT's boot-block layout that the updater's one erase lands
in `SA8` and leaves `SA9`/`SA10` untouched, "which is what a settings store in
flash looks like". An Intel 28F400 has its own block map, and `-T` and `-B` parts
put the boot blocks at opposite ends.

**The cheap check is the one the update image itself performs**: read the
autoselect words out of the 2806. Manufacturer `0x0089` is Intel, `0x0001` is AMD,
and the device word names the part and its boot orientation. That is a monitor
read.

The flash pinout is confirmed against the Am29F400B 44-lead SO diagram - `A17`,
`A7` and `A0` on pins 3, 4 and 11 all match the board readings - and `BYTE#` is
tied high, so it runs in word mode and its `A`n is system `A`n+1.
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

## What is still unknown

Sixteen of the 120 pins are unread; of the rest, seventeen are inferred middles
of measured runs (the two DSP data groups and `A2`-`A6`). The top and left edges
are finished but for one pin each; the bottom edge is at 26 of 30; the right
edge has eleven unread, `32`-`36` and `39`-`44`.

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
16. **Whether `&T1` is the codec's analog loopback.** Register 5 `DS01`-`DS00` =
    `00` is analog loopback and the bring-up writes `0505`, which is not. A
    `0504` in the payload would tie the `AT` diagnostic to a hardware mode; its
    absence would say the loopback is arithmetic in the DSP. No hardware needed.
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
