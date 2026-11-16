# The 2806's own firmware runs, and always could

We started this file to find what is necessary to run the firmware of the
25 MHz Courier 2806. All pin readings in [asic-pinout.md](asic-pinout.md) come
from this board. The investigation went through three incorrect premises
before the answer was **nothing**. The image runs now, on the machinery that is
already here. We keep the incorrect turns below, because we got to each of
them by a reasonable route.

## It runs

```
artifacts/boot-2806-capture-20260913/boot_run.py \
    artifacts/courier-2806-25mhz-flash-20260912/courier-board.rom 60000000
```

**Since 2026-09-13, that command needs no arguments** other than the image.
The tick is now the default (refer to the section below). `board_id` already
had the default 7. The EEPROM fixture is not necessary - with and without it,
the profile is different by three bytes. The recipe in the artifact gives all
three explicitly, because that is what we ran. The `ATI7` of the board:

```
USRobotics Courier V.Everything Configuration Profile...

Product type           US/Canada External
Options                HST,V32bis,Terbo,VFC,V34+,x2,V90
Clock Freq             25 Mhz
Flash ROM              512k
Ram                    64k
Supervisor rev         7.3.14
DSP rev                3.0.13
```

Supervisor 7.3.14, DSP 3.0.13, 25 MHz, 512k flash, 64k RAM - exactly the 2806
that [board-parts.md](board-parts.md) describes. No 25 MHz mode, no loader
change and no paging model were necessary.

`serial_text` is **7 data bits and even parity**, not 8N1 - all 430 bytes of
that profile have even parity and none have odd parity. Thus, to read it, mask
it to seven bits. That is the choice of the firmware: `S0CON` is mode 1, eight
bits on the wire. The firmware puts ASCII in seven of them and parity in the
eighth.

A real board gets to the correct format in two ways - it **autonegotiates**
from the `AT` prefix, and the format is **stored in the settings EEPROM**.
Neither way works here. The autonegotiation has nothing to measure. On the
board, the received data goes inverted through a 74AHC04 into `T1IN` (CPU pin
78), so that the firmware can measure the time of a bit cell.
[asic-pinout.md](asic-pinout.md) traced this path, but the harness does not
model it. If the input has bit 7 set, there is no response. This is the same
gap from the other end. Also, no fixture has a stored format. When we boot
this capture with no NVRAM, with the 302 fixture and with the 403 fixture, we
get 427, 430 and 473 bytes of profile. All three have the parity bit set.

**There is no captured 93C66 image in this repository.** One image would solve
this and several other caveats about blank fixtures. The part is now fully
mapped - `CS`/`SK` on CPU 52/57, `DI`+`DO` on CPU 79. Thus to read one from a
board is a known task, not a search.

## The tick is the default now

Before, `tick_ms` was off by default. The reason was that it changes the call
timing, and it was not known which behaviour is correct. **A run without the
tick is not a slower run, it is a broken run** - refer to the next section.
Thus the default is now `SUGGESTED_TICK_MS`, 5 ms. To get the old behaviour,
give `tick_ms=0` or `--tick-ms 0`.

It is still a substitute. We do not know what makes the real periodic edge.
The actual correction is to model that. The default substitute only prevents
each long run from stopping at the same wall.

## The fault that started this was a missing tick

When you run the same image under `artifacts/mailbox-tap-atdt-01/tap_run.py`,
it stops with `UC_ERR_INSN_INVALID` at **5,684,093** instructions, at
`0x2e3:0xd112`, linear `0xff42` - in RAM, not in flash. That looked like a gap
that is specific to the board, and this file had a long argument that it was
one.

**It is not.** `tap_run.py` does not give `tick_ms`, and
[machine.py](../courier_emu/machine.py) says clearly that the tick "is not
driven by default". If you run the **20.16 MHz 4.03d capture** in the same way,
it stops at **5,689,414** instructions - in 0.1% of the same location. Two
boards, two generations, the same wall. With `tick_ms=5`, the two images run
to a limit of 60,000,000 instructions with no error.

Thus the fault was that the harness did not give the firmware its timebase.
The address where it stopped is only the location where that occurs.

## The wrong turns, and what settled each

We keep these items because the routes were reasonable, and evidence, not a
new reading, gave the corrections.

**"Every behavioural target here is a 20.16 MHz image."** Incorrect: `T0CMPA`
(`0xff32`) shows that the ROM builds are 20.16 MHz (`6270`) and that **each XMF
supervisor is 25.8048 MHz** (`7e00`). A comment in `courier_emu/daa.py` already
said this. We settled it when we read the constant from eight images.

**"The capture is a supervisor image misrouted through the ROM model."**
Incorrect: it ends in the same reset stub as the 4.03d capture - `fa ba a4 ff
b8 00 80 ef`, then a far jump into `fc00`. It is 45.7% byte-identical to that
capture. This is as close as that capture is to `IDSDL302.ROM` (45.2%).
`CourierRom` is the correct identification. We settled it when we compared the
three images.

**"The gap is board-specific, and the flash paging is the suspect."**
Incorrect, and the reason is the useful part. **The ASIC is the same part
across the old and the middle generations.** Thus an explanation specific to
the board, for a fault that only the image of this board showed, was doubtful
from the start. The failure of the 4.03d capture at the same instruction count
confirms it. We settled it when we ran the other capture under the same
conditions.

**Retracted 2026-09-18.** This item also said that "the paging finding itself
stands - the ASIC does hold the flash's `CE#`". That is not true. Flash `CE#`
is on CPU `UCS`. The reset stub above is the proof, in the bytes of this file:
`ba a4 ff b8 00 80` is `mov dx,0xffa4` / `mov ax,0x8000`. This programs
`UCS_START` to the base of the flash before anything else runs. The ASIC
consumes one upper address line, but the `UCS` decode consumes `A19`, and that
is what a flat map looks like. Refer to
[asic-pinout.md](asic-pinout.md#the-fold-four-address-lines-in-three-out).
Now a boot that does not exercise paging is the usual case, not a puzzle.

## What this leaves

This is not a porting problem. Two smaller problems remain:

* **Nothing in the repository had run this image.** The target guidance points
  to `IDSDL302` and the 4.03d capture, both 20.16 MHz, but all of the pin
  readings come from the 2806. That gap was real. A command closes it. No new
  code is necessary.
* **`SV25.XMD` still cannot execute.** It decodes to this capture byte for
  byte, but not the four checksum bytes at `0x77ffc..0x77fff` - we verified
  this here. `machine.run` fails when it maps an `XmdImage`
  (`UC_ERR_WRITE_UNMAPPED`). A decoder that cannot run what it decodes is a real
  gap, but only for convenience: the bytes can already run in their captured
  form.

## The three generations

| generation | images | clock | flash / RAM |
|---|---|---|---|
| old | `IDSDL302.ROM`, the 4.03d capture | 20.16 MHz | 512k / 64k |
| **middle - this board** | the 2806 capture, `SV25.XMD` | 25.8048 MHz | 512k / 64k |
| new | `main211.xmf`, `3453Bv2.1.1.xmf` | 25.8048 MHz | 1024k / 256k |

`main211` is the **newest** generation - V.92, rev 2.1.1, dated 2003. It is not
a variant of this board. [board-parts.md](board-parts.md) gets to the same
division from the firmware side: "the middle generation groups with the old
one, not the new one". The shared ASIC shows the same thing from the hardware.
The most practical proof is that **one recipe boots the two images**.

Thus there is no cost when we use 302/403 as behavioural references here. This
board is related to the old generation, with a faster clock, and its own image
operates on the same machinery.

## The clock, which is settled

`CLKOUT` is **25.8048 MHz** and the crystal is **51.6096 MHz**. This comes from
the firmware alone, and two items confirm it:

* `T0CMPA` is `0x7e00` = 32,256, against 25,200 for the 20.16 MHz builds. The
  ratio is exactly 1.28, and 32,256 at `CLKOUT/4` is a 5.000 ms tick.
* The baud divisors are 167 and 335, against 130 and 258. Through
  `baud = CLKOUT / (8 x (N+1))`, 25.8048 MHz gives **exactly** 19200 and 9600.
  A round 25 MHz misses the two values by 3.1%, and no 8N1 link accepts that.

`51,609,600 / 19,200 = 2688` exactly - the crystal was selected so that the UART
divides perfectly. The 20.16 MHz board has errors of 0.19% and 1.35%. The CPU
crystal has the marking `R0936391`, a house part number that does not give a
frequency.

**This is only the domain of the CPU.** The ASIC runs from the shared
40.320 MHz oscillator on the two boards. Thus the clock of the DSP and the
`MCLK` of the codec are independent of the board. This is why the DSP payload
is byte-identical across the two boards, while the supervisors are different.
