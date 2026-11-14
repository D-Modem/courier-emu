# The I-modem board, and the address map its chip selects draw

A photograph of the board answers several questions that the image could only
suggest. The harness modelled one of these items incorrectly.

## What is on it

| marking | what it is |
|---|---|
| Intel **KU80386EX25** | the CPU, as [imodem-isdn-front-end.md](imodem-isdn-front-end.md) worked out from its peripheral registers |
| AMD **AM79C30AJC/J** | the ISDN front end - the part at ports `0300`-`0307` |
| AMD **AM7945JC** | a second AMD telecom part, not addressed by anything this image executes - see below |
| Intel **TE28F400** and AMD **AM29F400AT** | *two* 4 Mbit flash parts, side by side |
| LGS **GM76C8128ALLFW70** x2 | 128K x 8 SRAM each - 256 KiB paired |
| ISSI **IS61C256AH-12** x2 | 32K x 8 SRAM - the DSP's |
| USR **DSP EBS-64A56DW** (`D17140PQ`, `16-912`) | the DSP, custom-marked |
| NEC **USA 1-016-905** (`9612KVA09`), U15 | **the ASIC** - the same USR part number as the analogue Courier's `1-016-905 9948LV001`, a different lot and date code (week 12 1996 against week 48 1999). Pinned out from the analogue board in [asic-pinout.md](asic-pinout.md) |
| Altera **EPM7032LC44-15T** (`USR 19457`, `D9546`) | a 44-pin CPLD, fitted **alongside** the ASIC - see below |
| ECLIPTEK **40.320M** | the ASIC's oscillator, the same part and frequency as both analogue boards carry ([board-parts.md](board-parts.md)) |
| ECLIPTEK **50.000M** | the 386EX's own oscillator, halved to the `KU80386EX25`'s 25 MHz |
| **74VHC573**, **74VHC245**, **ACT16245** | address latch and bus buffers |
| Sipex **SP503CP** | the DTE transceiver |

The board also has an **AT&T** part with the marking `T 7256 ML2` (date code
`9613S`), and the line section: a Valor **ST15069** transformer module, a
Takamisawa **RY5W-K** relay, a CP Clare **LH1502** solid-state relay and an
**XCA111E** optocoupler.

## The ASIC and the CPLD are both fitted, and which does what is open

Before, this file gave only the Altera and said that the board latches belong
to it. The photograph that we read the table from did not show U15, and the
NEC ASIC is there. Thus it is **not** established that the latch bank at ports
`0x10`-`0x1e` belongs to the CPLD. The interpretation that the I-modem is a
design without an ASIC was an artefact of a partial photo.

Two firmware details now have a different interpretation. The board-init sweep
at `40509` writes `0x0c` = `0x60` and `0x14` = `0xf5`. These are the values
of the analogue board for those latches - `asic_ports.IDLE` for `0x0c`, and the
restore shadow in the port `0x14` bit 2 probe of [board.md](board.md) for the
other. Two latches that agree across two product lines are what shared silicon
looks like. This is more than the shared signal-id convention that
[imodem-d-channel.md](imodem-d-channel.md) already records.

But one fact does **not** agree with the ASIC: the same sweep writes ports
`0x03` and `0x07`. On the analogue board, each odd port in `0x00`-`0x7f` reads
`0x00`, all 64 of them ([asic-port-map.md](asic-port-map.md)). A split - the
ASIC on the even latches, and the CPLD that decodes the odd ports and `0x100`
- would explain that fact. It would also explain why the board-revision flag
at `[c8f1]` bit 2 changes the lamps between `0x100` and the older latches.
That is an inference, and nothing in the image states it. A trace of the
device that drives `0x100` gives the answer.

The ASIC is **not** the memory controller here, independent of its other
functions: the flash is on the own `CS4` and `UCS` of the 386EX (below). On
the analogue board, the ASIC holds flash `CE#` and folds `A17`-`A19`.

## The AT&T part is the NT, and the board is the integrated-NT variant

The board in the photograph is the integrated-NT version, with an analogue
jack next to the ISDN jack. This identifies the AT&T part. It is the U
transceiver: the line jack and the Valor transformer are on one side, and an
S/T loop to the LIU of the Am79C30A is on the other side. It does on the board
what an external NT1 does in a box.

That agrees with all of the actions of the firmware, and it is why it needs
no model. An integrated NT is autonomous by design: the 386 never configures
it. This is why there is no window for it in I/O space and nothing in the CS1
and CS3 windows above 1 MiB. Also, the strings of the firmware have no `NT1`,
`2B1Q` or `U-Interface`. The only loopback text in the image is for the
analogue and digital loopbacks that each Courier has. For the emulator, the S
interface starts at the LIU of the Am79C30A, and `courier_emu/am79c30.py`,
which drives that LIU through its I.430 states, is all of the line.

The analogue jack also identifies the other unknown part. A POTS jack needs an
audio path between a B channel and a handset. This is exactly the purpose of
the MAP and the peripheral port of the DSC - `PP_PPCR1` is enabled at init and
`MCR1`-`MCR4` are not routed because there is no call. The **Am7945**, which is
off the bus next to the analogue line section, is the natural occupant of that
path. This is still an inference, but now it has good support.

## The Am79C30A is the part at 0300, and the Am7945 is not on the bus

It is useful to keep these separate, because we now know that the board has
two AMD telecom parts. The chip at `0300`-`0307` is the **Am79C30A**, and there
is no doubt about this. The indirect register file agrees exactly with its
block widths - seven bytes to `DLC_1_7`, two to `DRCR`, forty-six to
`MAP_1_10`. The IRQ14 handler uses CR/IR, DR, DSR1, DER, DCTB/DCRB and DSR2 in
the direct-map sequence of that part
([imodem-d-channel.md](imodem-d-channel.md)).

The firmware does not get to the **Am7945** through I/O space. We made a
census of each port that a run of 40 million instructions touches, with the
code site for each. It shows nothing that looks like a second device:
`0x00`-`0x16` are written one time each from one board-init sweep at `40509`,
and otherwise belong to the board latches. `0x1a` is the DSP handshake.
`0x100` is the lamps. There is no second command/data pair.

Such a part could be on the own **peripheral port** of the DSC without being
visible. The firmware enables that port at init and never routes it:
`PP_PPCR1` is set to `07` and `PP_PPCR3` to `01`, but `MCR1`-`MCR4` stay at
zero because there is no call. That, the transmit and receive filter
coefficients of the MAP, and the analogue line section on the board all point
to an audio path between a B channel and an analogue handset. This is what an
I-modem does when you connect a telephone to it. But that is an inference from
the firmware and the board. The image does not state it. The datasheet of the
Am7945, or a probe of its pins that go to the DSC, would give the answer.

## The map, from the chip-select unit

The firmware programs the chip-select unit of the 386EX at init. When we read
back what the firmware writes to `f400`-`f438`, we get the memory map of the
board directly. The `ADH` of each channel carries A25:A16, and its `ADL` bits
15:10 carry A15:A10. The mask registers name the bits that are not compared:

| channel | ADH | window | size |
|---|---|---|---|
| CS0 | `0000` | `00000`-`1ffff` | 128 KiB |
| CS5 | `0002` | `20000`-`3ffff` | 128 KiB |
| CS4 | `0004` | `40000`-`7ffff` | 256 KiB |
| CS2 | `000c` | `c0000`-`fffff` | 256 KiB |
| UCS | - | **not determined** | - |
| CS1 | `0010` | `100000`+ | 16 KiB |
| CS3 | `0010` | `104400`+ | 16 KiB |

CS0 and CS5 are contiguous: **256 KiB of SRAM at `00000`-`3ffff`**. This is
the pair of LGS parts, and it is exactly the `Ram 256k` that `ATI7` reports.

**UCS is only half programmed.** The firmware writes `UCSADL` and nothing more
- `f432`, `f434` and `f436` are never written in a full run. Thus the upper
chip select keeps its reset window, and this file does not claim to know what
that window is. A device decodes `80000`, because the flash identify at
`34983` probes there (`es = 8000`, no bank loop, no parameter). But we did not
recover the extent of that window.

### 768 KiB mapped, 1 MiB fitted

`40000`-`fffff` is **768 KiB**, and `ATI7` says `Eprom 768k`. It is also
exactly the span of the NAC payload, which loads at `40000` and continues to
`f8000` - all of the flash image except the top 32 KiB boot block. Three
numbers that agree have some value.

But two 4 Mbit parts are **1 MiB of silicon**, and 768 KiB is not 1 MiB. Thus
at least 256 KiB of the installed flash is not mapped into the first megabyte.

The update image shows the composition of that 768 KiB. `Ie030002.nac` is
840,105 bytes on disk - 42,222 records, of which 42,023 carry data and 197 set
the segment address. It flattens to **753,664 bytes, 736 KiB, at
`40000`-`f8000`**. It divides exactly on the chip-select boundary:

| region | bytes | | erased |
|---|---:|---|---:|
| `40000`-`7ffff` | 262,144 | 256 KiB - all of CS4 | 3.8% |
| `80000`-`f8000` | 491,520 | 480 KiB - 512 KiB bar the top 32 KiB | 18.5% |

Thus the image supplies exactly one full 256 KiB window and one full 512 KiB
part, without the boot block that it does not replace. 256 + 512 is the
768 KiB. The composition is **one part mapped fully at `80000`-`fffff` and half
of the other part at `40000`-`7ffff`**. This is the interpretation proposed
above, and now the image agrees with it, not only the address arithmetic. The
256 KiB that is not mapped is the remaining part of the CS4 part.

This also means that the first 256 KiB of the payload is not "the updater,
loaded into RAM": RAM stops at `3ffff`, and the initialiser relocates its
working copy down to `0ce00`. `40000` is flash. Thus that 256 KiB is the own
contents of flash part B, and the NAC image is a dump of the two mapped
windows. It is not only what an update writes.

A caution about the use of `ATI7` as corroboration: this repository already
found that `ATI7` reports a firmware constant as if it was measured. Its
options list on the Quad ([quad-settings-eeprom.md](quad-settings-eeprom.md))
was the own XOR constant of the firmware that appeared as data, and nothing
was read from a part. `Eprom 768k` can also be a constant. In that case, it
records what the design intends, not what is installed.

This is certain in the two cases: the region at `40000`-`80000` that this
repository called "the updater, in RAM" is its own chip-select window, and a
flash part is the obvious occupant.

That is important for the open question of
[imodem-d-channel.md](imodem-d-channel.md). The settings block at `2600:d476`
is never filled in a run, and the harness has only modelled the part at
`80000`. A second flash that the harness treats as usual RAM is a candidate for
the source of the settings block.

## The part at 0x80000 is AMD, and the harness was answering as Intel

The default identify of `courier_emu/flash_device.py` was Intel. Thus each run
took the Intel branch - `50` clear status, `20`+`d0` erase, `70` status. The
board has an Am29F400AT at that window. Thus a real board takes the **AMD**
branch, and the difference is important:

| identity | autoselects | erases | programs |
|---|---:|---:|---:|
| Intel (what the harness answered) | 4 | 4 | 0 |
| AMD Am29F400AT (what is fitted) | 6 | 1 | 4096 |

With Intel, the updater erased and then **programmed nothing**. With AMD, it
erases its sector and writes 4,096 words - the update actually occurs. The
model now has the default `manufacturer 0x0001`, `device 0x2223`, and has the
AMD command set together with the Intel set: `aa`/`55`/`a0` then a write to
program, `aa`/`55`/`80` then `aa`/`55`/`30` to erase a sector, `10` for the
full part, `f0` to reset.

The sector map is the map of the part itself, and it confirms a guess. The
Am29F400AT is top boot: seven 64 KiB sectors, then 32, 8, 8 and 16 KiB. The
one erase of the updater is at flash offset `78100`. This is in **SA8, the
first 8 KiB boot sector**. That is exactly the 8 KiB block size that
[imodem-isdn-front-end.md](imodem-isdn-front-end.md) inferred from the erase
address alone. Now it comes from the part, not from reasoning. An update
never erases and never programs SA9 and SA10 above it. This is what a settings
store in flash looks like.

We recovered one more detail at the same time: `34975` clears bit 7 of the P2
latch of the 386EX and loops 6,000 times before it touches the flash. It sets
the bit again after. That is the write protect, and it is why port `f86a`
toggles around each flash operation.

## The DIP switches

The external unit has a switch bank, and the own display of the firmware tells
where it is - a guess is not necessary. The printer at `0xc7924` sends

```
CURRENT DIPSWITCH SETTINGS
DIPSWITCH #1   ON
DIPSWITCH #2   ON
```

It reads each switch through the board-signal helper at `a400:1e0a`, with an
id from a table at `0xc79a3`. The table has **two** entries - `0x4023` and
`0x1023` - and the bytes after them are code. Thus the firmware reads only two
switches, independent of the number on the enclosure.

Those ids decode through the same scheme as the other signals of the board
([imodem-d-channel.md](imodem-d-channel.md)): the low byte indexes the
input-port table at `a5f97`, whose entry 3 is **port `0x12`**, and the high
byte is the mask. Thus the two switches are bits of one port:

| switch | id | port | mask |
|---|---|---|---|
| 1 | `0x4023` | `0x12` | `0x40` |
| 2 | `0x1023` | `0x12` | `0x10` |

Port `0x12` is next to the enclosure latch at `0x14`, which is entry 2 of the
same table.

The sense is inverted, as on the modem-status lines: the signal helper reports
that a switch is present when its bit reads **0**, and the printer calls that
`ON`. Thus a port that is not modelled and answers 0 always read as the two
switches ON. `courier_emu/isdn.py` keeps this default, so that older runs do
not change. `isdn-run --dipswitch 1=off` sets one switch.

We know only part of what they do:

* `0xa5fb4` reads **Switch 2** at boot. When it is ON, it sets `[ca3f]` bit 7
  with `[ca38]` bit 2 clear. When it is OFF, it does the opposite. Five sites
  test that flag.
* **Switch 1** is visible from outside. When it is OFF, the modem stops to
  answer the AT interface completely - `ATDT` gets no response, not
  `NO CARRIER`. This is what the result-code or dumb-mode strap of a Courier
  does.

Neither setting changes what `ATD` does on the D channel: with all four
combinations of the two switches, an `ATDT` still transmits no layer-2 frame.
