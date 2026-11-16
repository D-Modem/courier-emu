# What is actually on the board

> **[board-map.svg](board-map.svg)** shows these parts and the nets between
> them. `tools/draw_board_map.py` makes it. Each net on it is a continuity
> reading. [asic-pinout.md](asic-pinout.md) has the pin tables and the
> reasons for each one.

We identified these parts from a photograph of the 20.16 MHz Courier of the
user (the unit that runs ID_SDL 4.03d, supervisor 7.4.16 / DSP 3.1.2). Where
the firmware can check a claim, we checked it against the firmware.

We read the markings from one photo of part of the board. The DAA/line section
is not in the photo. Thus this document does not say what is on it.

| marking | what it is |
|---|---|
| `NEC USA 1-016-905 9948LV001` | **the ASIC.** A USR part number on an NEC-fabricated gate array, date code week 48 1999; pinned out in [asic-pinout.md](asic-pinout.md) |
| `TI DSP 16-912 (C) US ROBOTICS D17140PQ` | the C5x-family DSP, custom-marked with a USR part number |
| `S80C186` | the Intel supervisor. Its `GCS0` (QFP pin 59) is the ASIC's chip select, so the ASIC's I/O window is set by the programmable limits at `0xff80`/`0xff82` rather than decoded in the ASIC. The pin readings identify it more precisely as an **80C186EB in the 80-lead QFP** - `RD`/`WR`/`ALE` on 36/37/38 and `INT0`/`INT2` on 62/64 all match that package's Table 7 exactly, and match the XL's not at all. Which is the device `courier_emu/uart.py`'s `EbSerial` already assumes |
| `TLC...320AC01CFN` | the voice-band codec, PLCC, next to the DSP |
| `ECLIPTEK EC11 40.320M` | the **ASIC's** oscillator, and the same part on both boards - so the DSP's clock and the codec's `MCLK` are board-independent. The **I-modem carries it too**, next to its own `1-016-905` ASIC ([imodem-board-map.md](imodem-board-map.md)), so this is a product-line constant rather than an analogue-Courier one. The 25 MHz 2806 carries a **second** crystal for the CPU alone; see [running-the-25mhz-image.md](running-the-25mhz-image.md) |
| `NEC D43256BGU-70LL` x2 | the **80186's** SRAM, `U4` and `U12`: not two banks but the **low and high byte lanes of one 32K x 16**. Both `CE#` on CPU `LCS` (QFP pin 60); separate `WE#` from two '32 gates, `U12`'s qualified by latched `A0` from the ASIC and `U4`'s by `BHE#` straight from CPU pin 39 |
| `CY7C199-15VC` x2 | the **DSP's** SRAM: 2 x 32Kx8, 64 KB = 32K words on a 16-bit bus |
| `ISSI IS61C256AH-15J` | 32Kx8 15 ns SRAM |
| `ADM707` | supervisory/reset - and on this board a **power-good reset only**, with its watchdog unused. **Pin 7, the active-high `RESET`, goes to ASIC pin 111**, and **pin 6 is not connected**, so the supervisor resets the ASIC and nothing else. **The CPU is reset by the ASIC**, through `R1` (1k, marked `102`) from ASIC pin 52 into `RESIN` (CPU pin 68) - so the reset tree is a chain: rails release the ASIC, the ASIC releases the CPU, the CPU's firmware releases the DSP and codec. The ASIC coming up first is required rather than incidental, since it holds the flash's `CE#` and so decides whether the CPU's first fetch can succeed. Note this **retires** the watchdog explanation [ram-probe-delivery.md](ram-probe-delivery.md) gave for the ~1.5 s bound on probe runs; the bound is measured, and its trigger has a candidate: the `0x81703` pulse on port `0x00` bit `0x40` has the cadence of a watchdog kick and the ASIC is the only part that could act on it - see [board-verified-403.md](board-verified-403.md#the-0x81703-pulse-is-the-asics-watchdog-kick). See [asic-pinout.md](asic-pinout.md) |
| `74VHC573`, `74VHC32`, `74VHC04` | bus glue. The '573 is an **address demultiplex latch**; there is exactly **one** '573 and it latches the **high** byte, `AD8`-`AD15` into `A8`-`A15`, with a `74VHC32` beside it. `A0`-`A7` come out of the **ASIC** instead - pins `71`-`64` carry system `A0`-`A7`, `A0` to the byte-lane gate and `A1`-`A7` to both memories - so the two parts split one address latch between them. The '32 makes both SRAMs' write enables - gate 4 to `U12` pin 27, gate 3 to `U4` pin 27 - each `OR`ing the board write strobe with a byte-lane term, ASIC pin 71 being the low lane's. See [asic-pinout.md](asic-pinout.md) |
| `PA28F400` | the **flash**. Intel 4 Mbit / 512 KiB, which is the 2806 dump exactly. Pinout confirmed against the Am29F400B 44-lead SO connection diagram - `A17`/`A7`/`A0` on pins 3/4/11 all match the board readings. `BYTE#` is tied high, so it runs in word mode and its `A`n is system `A`n+1 - pin 3 is system `A18`, pin 34 system `A17`. Data is unbuffered - flash `DQ11` (pin 22) lands straight on CPU `AD11` (QFP pin 20). **Both** high address pins come from the ASIC - its pin 73 to flash pin 3 (`A17`, system `A18`) and its pin 74 to flash pin 34 (`A16`, system `A17`); the old "74 is pin 3 or pin 34" conflict was one miscounted pin. ASIC pin 76 is flash `A15` (system `A16`). **Corrected 2026-09-18:** this row used to say ASIC pin 75 was the flash's `CE#`, "so the ASIC selects the flash and CPU `UCS` does not", and built a paging fold on it. Pin 75 goes to flash pin **13**, `GND`; flash `CE#` is on **CPU pin 61, `UCS`**, measured on the 2805 ISA board and confirmed by the reset stub programming `UCS_START` to the flash's own window. The address count was also wrong - four lines in (`A16`-`A19`), three out, with `A19` consumed by the `UCS` decode, which is a flat map rather than a fold. Between the ASIC and the '573 the flash's whole address bus is still accounted for, so the ASIC is the board's address latch; the select is not its. See [asic-pinout.md](asic-pinout.md) |
| `SN75188` x2, `U22` and `U23` | the **EIA-232 line drivers**, TTL in / EIA out, modem-to-DTE only; `RD` is traced to `U22` pin 2 and `CD` to `U23` pin 4 - **and the ASIC is on the other end of both nets**, so every modem-to-DTE signal leaving through a 75188 is an ASIC output. **Three of each part's four drivers are fed from the ASIC**: `U22` 2/4/10 from ASIC 46/49/50, and `U23` 2/4/10 from ASIC 12/9/11. Gate 4 is unused on both; `CD` is one of them and the other gates carry the rest of `CTS`/`DSR`/`RI`. See [asic-pinout.md](asic-pinout.md) |
| `74AHC04` | inverter; one gate sits in the `SD` path, see [asic-pinout.md](asic-pinout.md) |
| `TLC320AC03` codec | its serial interface goes **direct to the DSP** - `DOUT`/`DIN`/`FS` (FN pins 11/10/12) on DSP 43/106/104, each one pin from its TDM counterpart. The ASIC's single line to it is **`MCLK`** (pin 14, from ASIC 112), so the ASIC generates both audio timebases. `MON OUT` (pin 1) drives the **speaker**, and its gain - squelch, 0, -8, -18 dB - is register 4 bits `DS05`-`DS04`, so the speaker is switched by the DSP over `DIN` and by no board line at all. Four monitor states for an `AT` command set with four (`M0` plus `L1`/`L2`/`L3`), and squelch is the reset default. `OUT+`/`OUT-` (pins 3, 4) are the DAC's output to the line. See [asic-pinout.md](asic-pinout.md) |
| `H11B2` x2, `U14` and `U16` | **optocouplers** - the line-side isolation barrier, and the first named parts in the DAA section. Pin 5 of each, on the transistor side, goes to ASIC pins 19 and 22, so the ASIC **receives** both. Two isolated inputs from the line is the shape of ring detect plus loop-current sense, and that now stands rather than being argued away: this row used to hedge on the grounds that "ring sense already has a port (`0x14` bit 1)", but that port is the *read* side of a latch whose *write* side is CS/CTS, so it needs a physical input driving it and the opto is the candidate. See [board-verified-403.md](board-verified-403.md#the-ring-is-the-dte-receive-buffer-and-port-0x14-bit-1-is-its-cts). See [asic-pinout.md](asic-pinout.md) |
| `DS1489AM`, `U18` | the **EIA-232 line receiver** - the 1489 half of the 1488/1489 pair, EIA in / TTL out, DTE-to-modem. `1Y` (pin 3) goes to CPU `RXD0` and `2Y` (pin 6) to CPU `CTS0`, so **the DTE link is on serial channel 0** and `uart.py`'s `EbSerial` is on the right channel; `CTS0` is a real pin where the harness fabricates one. `4Y` (pin 11) goes to ASIC pin 48, most likely `DTR`. `3Y` is unread. See [asic-pinout.md](asic-pinout.md) |
| `RA5W-K` | the **hook relay**. The `OH` lamp is on its pin 9, which is why `OH` is the one panel line not on the ASIC |
| Atmel 93C66 | serial EEPROM, the NVRAM the settings cache comes from. On the 2806 it is the **CPU's**, not the ASIC's: `CS`/`SK` on CPU pins 52/57 (`P1.5`/`P1.2`) and `DI`+`DO` tied onto CPU 79 (`P2.7`). `ORG` floats, which on the Atmel part is x16 - 256 words, matching `nvram.py`. All eight pins are read: 5 and 8 are `GND` and `VCC`, and pin 7 floats, as Atmel's `DC` pin should. See [asic-pinout.md](asic-pinout.md) |

## The DSP's RAM is 32K words, and that is its program space

Two `CY7C199-15VC` give 64 KB. On the 16-bit program bus of the C5x, this is
**32K words - exactly `0x8000`-`0xffff`**. The downloads of the supervisor fill
this range. The overlay table writes `0x8000`-`0xf8b5` on 302 and
`0x8000`-`0xf949` on 403, approximately 31K words. Thus the size of the part
is correct for the job, with a small margin. It also replaces the arithmetic in
[who-produces-the-events.md](who-produces-the-events.md), which could not put
those downloads into one 32Kx8 device. There are two devices, and they belong
to the DSP, not to the supervisor.

The one address that this RAM does not cover is `0x23f0`. The mailbox
dispatcher of 302 and its stream resume poll both do a `calld` to it on each
pass. That address is below the external RAM, thus it must be on-chip. The C5x
User's Guide (SPRU056D) then lets us identify the part.

**Table 1-1, on-chip memory in 16-bit words:**

| device | DARAM | SARAM | ROM | serial ports |
|---|---|---|---|---|
| 'C50 | 1056 | **9K** | 2K | 2, includes TDM |
| 'C51 | 1056 | 1K | 8K | 2, includes TDM |
| 'C52 | 1056 | **none** | 4K | **1**, no TDM |
| 'C53 | 1056 | 3K | 16K | 2, includes TDM |
| 'LC56 | 1056 | 6K | 32K | 2, BSP |

When `PMST.RAM` is set, the SARAM is mapped into program space. For the 9K
part, the guide gives its range as **`0x0800`-`0x2BFF`**. `0x23f0` is inside
it. A 3K part goes only to `0x13ff`, and a 6K part only to `0x1fff`. A `'C52`
has no SARAM at all. Thus `PMST.RAM` and `OVLY` would have no meaning on it,
but this firmware sets both of them.

The guide gives the location two times, and both agree with what this firmware
does:

* **Program space.** With `CNF=0`, `RAM=1`, `MP/MC=1` (microprocessor mode,
  which is how this part runs), the 9K SARAM is at **`0x0800`-`0x2BFF`**.
  `0x0000`-`0x07FF` and `0x2C00`-`0xFFFF` are off-chip. `0x23f0` is inside the
  SARAM, and the external RAM at `0x8000`-`0xFFFF` is in the off-chip part.
  This is exactly what the download map needs.
* **Data space.** Table 8-8, `'C50` Local Data Memory Configuration,
  `OVLY=1`: registers `0x0000`-`0x005F`, B2 `0x0060`-`0x007F`, B0
  `0x0100`-`0x02FF`, B1 `0x0300`-`0x04FF`, **SARAM `0x0800`-`0x2BFF`**,
  off-chip `0x2C00`-`0xFFFF`. The prologue clears `0x0800`-`0x08FF` and
  `0x0B80`-`0x0BFF`. These clears, and the 302 mailbox ring at `0x0BD0`, are
  all in that SARAM window.

One more detail agrees. The `'C52` has one serial port and no TDM, but this
harness models a TDM ISR for the part.

An earlier revision of this section said that the 9K SARAM "decodes with
A15-A14 ignored" and thus mirrors. That is **Table 8-15, address ranges during
external DMA**. It applies to a DMA master that accesses the SARAM. It does not
apply to the program and data addressing of the CPU itself, which the two
tables above give.

> **Superseded 2026-09-13.** The DSP is a **'C51**. We measured this, and did
> not infer it. A write through data space is not visible through program space
> at `0x0800` or `0x1800`, but it is visible at `0x2400`. This shows 8K of
> on-chip ROM over `0x0000`-`0x1FFF`, not 9K of SARAM. `MP/MC` reads 0, not the
> 1 that the text below assumes. Refer to
> [board.md](board.md#which-dsp-a-c51-measured) and
> [artifacts/dsp-memory-test-2806](../artifacts/dsp-memory-test-2806/README.md).
> We keep the SARAM-range reasoning below as the route that we used. `calld
> 0x23f0` needs `0x2400` to be executable, and it is. It does not need the 9K
> part.

### The guide's figures, checked against the core region by region

The guide has three memory-map figures: program space in each MP/MC mode, and
local data memory. They agree with `native/c5x_core.h` at all points except
one constant:

| region | guide | core |
|---|---|---|
| program `0000`-`003F`, MP/MC=1 | external (vectors) | external |
| program `0800`-`2BFF` | SARAM if `PMST.RAM`, else external | same |
| program `2C00`-`FDFF` | external | external |
| program `FE00`-`FFFF` | DARAM B0 if `CNF`, else external | same |
| program `0000`-`07FF`, MP/MC=0 | 2K on-chip ROM | **4K**, `0000`-`0FFF` |
| data `0000`-`004F` | memory-mapped registers | same |
| data `0050`-`005F` | the 16 I/O ports PA0-PA15 | same |
| data `0060`-`007F` / `0080`-`00FF` | DARAM B2 / reserved | same |
| data `0100`-`02FF` | DARAM B0, reserved when `CNF` | same |
| data `0300`-`04FF` / `0500`-`07FF` | DARAM B1 / reserved | same |
| data `0800`-`2BFF` | SARAM if `PMST.OVLY`, else external | same |
| data `2C00`-`FFFF` | external | external, less the shared window |

The ROM row is a harness fixture, not a claim about the board. The firmware
runs with MP/MC=1, where that window does not exist. The probe kernels in
`dsp_probe.py` and `fsk.py` use microcomputer mode to hold 4K synthetic drivers
of their own. The header records this, and we did not change it.

**The last row is why the shared external window is ordinary.** The guide puts
*nothing* on-chip above `0x2BFF` in data space. It also puts nothing above it
in program space when `CNF` is clear, which is how this firmware runs. Thus a
reference to `0x8000`-`0xFEFF` is an off-chip bus cycle in **both** spaces: the
same address on the same pins. Thus one RAM that answers in the two spaces is
not a trick. It is a board that does not separate the two strobes. This is
exactly what the `bldp` of 302 from data `0x80f5` needs, and what
[dsp-map-302.md](dsp-map-302.md) measures.

## The NEC part is the ASIC

`1-016-905` is a US Robotics part number, not an NEC catalogue number. NEC
fabricated it, and USR designed it. A gate array in a package of that size, on
this board, is the part that all notes in this repository call "the interposed
ASIC". The notes model it as a black box.

That is an argument from placement, not a pin trace. **It now has a pin
trace**: [asic-pinout.md](asic-pinout.md) records that these lines all go to
this package: the address bus of the DSP, `AD0`-`AD7` of the CPU, the `IS`
strobe of the DSP and two CPU interrupt lines. Thus we describe the interposed
part, and do not infer it. Another fact also supports it. The I/O space of the
supervisor needs a device of exactly this description, and there is no other
candidate on the bus. From `artifacts/io-port-map/board-21210/`, the 80186
drives:

| ports | role |
|---|---|
| `0x0c`-`0x1a` | board latches: hook relay, NVRAM strobe, carrier-detect pair, ring detect |
| `0x1c`, `0x1e` | mailbox status and command |
| `0x40`-`0x4e` | the DSP download window |
| `0x50`-`0x56` | second window bank |
| `0x58`-`0x5e` | mailbox tag and data registers |
| `0x60`, `0x62` | the DSP-to-host stream window |

None of these is the peripheral block of the CPU itself, which is relocated to
memory `0xff00`-`0xffff`. None of them is flash or SRAM. All of them are one
device that connects the 80186 bus to the DSP, the codec, the DAA and the front
panel. The ASIC is the only device that remains to be that device.

Thus all the items that the notes give to "the ASIC" are in this package: the
mailbox, the DSP download path, the codec bring-up sequence that neither
processor does, the line detector that the harness answers by hand, and the
tone generator. The tone generator is why `--exchange` still hears silence when
the firmware dials. The behaviour of the ASIC is not published, and this
identification does not change that. But it does show that the missing item is
one part, and it shows which part.

## The oscillator settles the clock independently

`40.320M`. The 80C186 divides its oscillator input by two, thus CLKOUT is
**20.16 MHz**. This is what `ATI7` reports, and it is the number that
[the timebase note](hardware-timebase-and-audio-path.md) needed.

> That is the clock of the **CPU**. The DSP does not take this can directly. Its
> `X2/CLKIN` (pin 96) comes from **ASIC pin 119**. Thus the DSP runs at the rate
> that the ASIC makes. Refer to [asic-pinout.md](asic-pinout.md). We did not
> measure the frequency.

This removes an ambiguity in the timer argument. `T0CMPA` is 25,200, and the
80186 counts internally clocked timers at CLKOUT/4. But 25,200 gives a round
figure in the two cases: 5.000 ms at CLKOUT = 20.16 MHz, or 10.000 ms if
20.16 MHz were the crystal and CLKOUT half of it. The `&T1` slope of the
board, 1.000031 seconds for each `S18` unit, already selected the first case,
because seconds convert to ticks when you multiply by 200. Now the can on the
board gives the same result from the hardware side. 40.320 divided by two is
20.16, thus the timer clock is 5.04 MHz and the tick is 5.000 ms.

## The codec is a TLC320AC0x, and the firmware proves it

> **Withdrawn (2026-09-12): the photograph stands, the firmware proof does
> not.** The part next to the DSP on the 20 MHz board is really a TI
> `320AC01CFN`. But the code that this section gives as confirmation is only in
> `main211.xmf`, and that board has an Si3021/Si3014 pair and no TI codec. Thus
> the claim of the heading has no support, and is probably the opposite of the
> truth. Refer to
> [so the claim is withdrawn](#so-the-the-firmware-proves-it-is-a-tlc320ac0x-claim-is-withdrawn)
> at the end of this document. The disassembly below is still a correct reading
> of what that code does. Only the part that it is attributed to is incorrect.

The part next to the DSP is a TI PLCC with the marking `320AC01CFN`. The code
of the DSP itself confirms the family, independently of the photograph.

The TLC320AC0x connects to a TMS320 serial port. It uses **bit 0 of the
transmitted DAC word to request a secondary frame**, in which the DSP writes a
control register. This is exactly what the C52 does:

```
00c2  lacl #01 ; samm @21      ; first word after reset is 0x0001:
                               ; D0 set, asking for a secondary frame
01b8  apl  *, #fffe            ; ordinary sample: clear D0
01ba  lamm @6b ; or *+
01bc  samm @21                 ; ...then OR in the request flag
0200  and  #0000fffe ; samm @21  ; sample with D0 cleared
01ea  lamm @6c ; samm @21      ; the secondary frame: the control word
021d  lacl #00 ; samm @6b      ; request satisfied, clear the flag
```

`0x0188` is the blocking sender for this protocol. It puts the word in `@6c`,
sets `@6b`, does `idle` until the serial ISR sends it, and returns:

```
0188  samm @6c
0189  lamm @6b
018a  cc   8190, neq
018c  smmr @6b, #012f
018e  lacl #01 ; samm @6b
0190  idle
0191  lamm @6b ; bcnd 8190, neq
```

`0x0195` reads control words from a table at program `0x019c` and sends them
through the sender: `0911 0967 0956 0934 0923 0969 0989 bc07 1019 ba01 9019 f788 be4c
7718 8b8f 8711`. This is the initialisation of the codec. This document does
not decode the individual register fields. There is no TLC320AC01 datasheet in
`docs/`, and a guessed bit layout did not agree with the table.

### but that code is dormant, which is the interesting part

It runs at reset and then stops. In a 60M-instruction run, `dxr_writes` is
**3**, all at program `0x00c6`, and `tdxr_writes` is **0**. After it
initialises the codec, the DSP never transmits on a serial port. It polls in
one resident-bank loop: `DRR` 338,279 times, `TRCV` 676,558 times, and ASIC
external I/O `0x50`/`0x52`/`0x54` 338,279 / 411,025 / 676,556 times.

Thus the DSP initialises the AC0x and then does not drive it. Two readings
agree with this:

1. The ASIC is in front of the codec. The C52 configures the part one time,
   and after that the ASIC moves the samples. This is the topology for which
   `courier_firmware_analysis.md` already argues, from AN16 section 1.3 and
   from the four ASIC ports that the C52 sees.
2. One firmware operates two board variants, and this variant does not use the
   serial-codec path.

Nothing here selects one of them.

### The generations differ in the firmware, but not the way expected

The user gives these models: a 20 MHz Courier of approximately 1994-97, a
25 MHz V.Everything V.90 of 1998-2000, and a 25 MHz "business" Courier from
2000 with a V.92 update.

The AC0x code is a signature that you can search for. Thus the images that
have it are a fact, not an inference. We found the DSP payload of each image by
an anchor that they all share: `splk @2a,#0010 ; splk @28,#000a ; splk @29,#0001`,
the wait-state sequence. Then we searched for the codec code:

| image | clock / flash | payload at | AC0x code |
|---|---|---|---|
| `main211.xmf` (2003) | 25.8048 MHz, 736 KiB | `0x002fe` | **yes** |
| board, ID_SDL 4.03 | 20.16 MHz, 512 KiB | `0x2914a` | no |
| board, stock 7.3.14 | 20.16 MHz, 512 KiB | `0x2908a` | no |
| `IDSDL302.ROM` | 20.16 MHz, 512 KiB | `0x2908a` | no |

The anchor is at `0x29080` in the two stock 20.16 MHz images.
`courier_firmware_analysis.md` independently says that the DSP payload starts
there. Thus the method is checked, and the negatives are real. They are not
the result of a search that missed.

The two 20.16 MHz builds do not use the AC0x path. They configure **`TSPC`**
(`0x32`, the TDM serial port control register) at program `0x008a`.

> **Partly corrected.** This build drives the AC01 *and* sets up the TDM port.
> Thus "instead of" is too strong for the setup. But an earlier version of this
> note also said that an overlay reads `TRCV`, and that was incorrect. Those
> sites are a data table that was read as code. No code in any image reads
> `TRCV`.
>
> **Corrected again (2026-09-07): "and then unused" is wrong.** The receive half
> is not used, but the DSP *transmits* on that port continuously: `sacl @31` at
> program `0x81c9`, inside the idle task. We measured 21,976 `TDXR` writes in
> one run. Also, `TSPC` decodes to show that the DSP is the **master** there.
> Refer to [the second serial port](second-serial-port.md). Refer to [vpcm-datapump.md](vpcm-datapump.md). `main211` does not,
anywhere in program `0000..2000`.

Thus there is a real architectural split between generations, and the firmware
shows it. **Its direction is the opposite of "older TI, newer Si"**, at least
for the two generations that we can compare. The DSP-driven TI codec path is in
the *newest* image, and the oldest builds set up the TDM port.

This agrees with the photograph. The 20.16 MHz board has a TI AC01, and its
firmware never drives it from the DSP. This is what an ASIC that is master of
the codec looks like, and it is reading 1 above.

> **Corrected.** The last sentence is wrong for the ID_SDL 4.03 / DSP 3.1.2
> build. The table above shows only that these images do not contain the
> initialisation routine of *`main211`*, and that is true. That build has its
> own routine. Its serial ISR ORs a secondary-frame request into the word that
> it writes to `DXR`. This is exactly the AC0x protocol that this section
> describes above, and reset sends six control registers through it. Thus
> reading 1 has no support for this board. The `dxr_writes` is 3 measurement
> for that reading came from `main211`, where the DSP stops its transmission
> after reset. On this build, the DSP writes `DXR` on each sample. Also, the
> program addresses for the 20.16 MHz build in this section are `0x8000` below
> those in [codec-rate-312.md](codec-rate-312.md). The `TSPC` setup at `0x008a`
> here is `808a` there. Thus the two documents read the same instructions.

The position of `main211` in the lineup is an inference. It does not come from
a version string. Its payload is 736 KiB, but the two V.Everything boards
report 512 KiB of flash, and the file date is 2003. This points to the business
Courier.

> **Superseded (2026-09-12): the middle generation is now tested, and the
> container is flat after all.** `SV25.XMD` does not use record framing. Remove
> its 128-byte header and apply the same 128-byte XOR block transform that the
> recovery harness already uses (`recovery.decode_payload`, documented in
> [sv25-recovery.md](sv25-recovery.md)). Then the payload is flat. The shared
> anchor is at `0x296e0`. It is not absent. The raw search failed only because
> the bytes were still encoded.
>
> Hardware confirms that decode. The decoded image agrees with a 512 KiB
> capture of a 25 MHz board (supervisor 7.3.14 / DSP 3.0.13, ATI7 `25 Mhz`) in
> all bytes except the four checksum bytes at `0x77ffc..0x77fff`.
>
> **The result is that the middle generation groups with the old one, not the
> new one.** The 16-word control table `0911 0967 ... 8b8f 8711` is only in
> `main211.xmf`, at `0x628`. It is not in the 25 MHz build, the two 20.16 MHz
> builds, or `IDSDL302.ROM`. Refer to the part list below for the item that
> this table really initialises. It is not a TI codec.
>
> The 2000+ V.92 image is still not available here:
> `firmware/legacy-usrobotics/USR03232004/` is a compressed InstallShield
> package, and no extractor is installed.

### Which board has which part, recorded at last

Before, this section gave two possibilities and asked for "a datum from the
boards, not from the images". The owner supplied it on 2026-09-12, from the
units that the owner has:

| board | part on the DSP's serial port |
|---|---|
| the 20 MHz boards | **TLC320AC01** |
| the 25 MHz Courier 2806 | **TLC320AC03** |
| the 3453C - taken to be `main211.xmf` | **Si3021 + Si3014**, no TI codec |

This is three generations, with one part each. It removes the option "one
board, two parts in two roles". It also settles the direction: TI first,
Silicon Labs last. The earlier guess of "older TI, newer Si" was correct. The
firmware reading that seemed to show the opposite was at fault, as the text
below shows.

#### So the "the firmware proves it is a TLC320AC0x" claim is withdrawn

The proof above uses two observations, and the part list makes both of them
fail.

The control table at program `0x019c` is the stronger observation. It is in
`main211.xmf` and in no other image. We measured this, and did not infer it.
But the board of `main211` is the board that has **no TI codec at all**. Thus
that table is the bring-up of the Silicon Labs pair, not of a TLC320AC0x, and
the section title is exactly the opposite of the truth. This also restores
`CodecBringUp`. The last line of this document calls it questionable because it
runs an `SI3038.PDF` register sequence. But a Silicon Labs sequence is the
*correct* family for this build. Only the specific part number is now not
certain.

The secondary-frame protocol (bit 0 of the transmitted DAC word requests a
control frame) also cannot discriminate. It occurs on the two sides of the part
split: in `main211` (Si pair) and in the ID_SDL 4.03 build for a 20.16 MHz
board (AC01). This protocol is common to the build for a TI-codec board and the
build for a board with no TI codec. Thus it is evidence about the serial
framing, not about the silicon.

#### The AC01 to AC03 change is invisible to the DSP

Stock 7.3.14 runs on a 20.16 MHz AC01 board and also on the 25 MHz AC03
board. Its DSP payload is **byte-identical between them**. When we align them
on the shared wait-state anchor, there are 126,851 consecutive identical bytes.
They cover the payload and all three overlays, and end at the blank region
after `0x48000`. All the differences between those two images are in the
supervisor, not in the DSP.

Thus the firmware does not distinguish AC01 from AC03. Also, you cannot
identify an AC03 board from its DSP code.

> **The explanation offered for that has been withdrawn.** This text said that
> the ASIC is in front of the codec, thus the C52 does not have to know which
> variant is installed. Later continuity readings
> ([asic-pinout.md](asic-pinout.md)) put the `DOUT`, `DIN` and `FS` of the
> codec **directly onto DSP pins** 43, 106 and 104. The only line from the ASIC
> to the part is `MCLK`. The DSP talks to the codec directly, thus no part is in
> front of it.
>
> The simpler explanation stays, and it needs no ASIC: **AC01 and AC03 are the
> same family**, with the same serial protocol and the same register map. Thus
> the same DSP code drives each of them. The observation stays. The reason for
> it changes.

In both cases, `CodecBringUp` is questionable. It runs an `SI3038.PDF`
register sequence, and the code of the DSP itself initialises a different part.

## The DSP's low program memory is RAM, and the download shows it

[The timebase note](hardware-timebase-and-audio-path.md) argued that the
internal mask ROM of the C52 does not execute. It used the branch targets of
the reset code and the wait-state programming. A USR-marked TI DSP is exactly
what a mask-ROM part looks like. Thus that argument needed a better test than
it had.

There is a better test, and the runs already had it. The bridge does not assume
the transfer. It collects the actual download stream of the supervisor and
compares it with the image. Each run reports `bootstrap_match: true` at
`bootstrap_bytes: 60344`: 30,172 words, the full resident segment.

> **Corrected 2026-09-15.** The `0x0000` origin was a constant in `courier_emu/xmf.py`, not a measurement. The download call site of the supervisor names `8000`, and its overlay table puts the 2.1/2.2 rows at `8000`, `9d00`, `af50` and `dc00`. Thus an XMF also has no low block, and agrees with the ROMs. Refer to [hardware-timebase-and-audio-path.md](hardware-timebase-and-audio-path.md#3-corrected-the-xmf-payload-loads-at-8000-not-0000).


Thus the supervisor really transfers 30k words whose content is
`0x0000`-origin code, and this covers the full 4K mask-ROM window. The CPU
writes program `0000..0fff`, thus it is external RAM. None of this can tell if
the die also has a mask ROM that is never mapped.

## The flash is an Intel part, and the harness models an AMD one

The flash of the 2806 has the marking `PA28F400`. This is the Intel 4 Mbit
boot-block part. `courier_emu/flash_device.py` models an **AMD Am29F400AT**,
device code `0x2223`. The eleven-sector top-boot map of that part is
hard-coded as fixed geometry, not a parameter.

These two disagree, but this is not yet a bug, and the usual distinction
applies. Nobody read the AMD choice from a board. It was **inferred from the
update image**, `Ie030002.nac`. That image probes for a manufacturer word and
uses the AMD path when Intel does not answer. That image belongs to the
I-modem, not to the 2806, and no evidence shows that the two units have the
same flash. Thus there are two parts here, and possibly two correct answers.

This is important because the sector map of the file is load-bearing. Its
comment uses the boot-block layout of the Am29F400AT to conclude that the one
erase of the updater is in `SA8` and does not touch `SA9` and `SA10`: "which is
what a settings store in flash looks like". An Intel 28F400 has its own block
map, and `-T` and `-B` parts put the boot blocks at opposite ends. If the
updater actually runs on a board with the Intel part, that conclusion comes
from the incorrect geometry.

The easy check is the check that the update image itself does: read the
autoselect words from the 2806. Manufacturer `0x0089` is Intel and `0x0001` is
AMD, and the device word identifies the part and its boot orientation. This is
a monitor read. It will either confirm the marking or show that the marking and
the silicon disagree.
