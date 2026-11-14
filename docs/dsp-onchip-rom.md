# The DSP's on-chip ROM, read off the board

`artifacts/dsp-onchip-rom-01/c5x-onchip-rom.bin` is **2048 words read from the
DSP of the live 20.16 MHz Courier** on 2026-09-07, SHA-256
`3e30fb31ac87fc9d0b8a85da245511ef3caa4e83249f56b5852d9d0829e93f67`. It is the
object that all the arguments in [dsp-map-302.md](dsp-map-302.md) tried to find. It
answers them by measurement, not by inference.

## How it was taken

1. `probe_transport --rom-dump` builds a RAM monitor for the 80186 that has a
   C5x kernel. It uses the launch and download routines of the reference itself,
   relocated out of flash.
2. `tools/emit_ram_writes.py` changes the image into `ATGLK2W` commands. 2096
   word writes put it at `0x3000`-`0x405f`. A read-back compares it byte for
   byte with the image, with zero mismatches.
3. Interrupt vector 8 is set to `0000:3000`. Then **`T0CON` is written with
   `0xa021`**. Timer 0 was already in operation with `T0CMPA` = 25200, the 5 ms
   tick, but its `INT` bit was clear. Thus, the tick was polled, not vectored.
   When that one bit is set, the monitor starts.
4. The monitor resets the DSP and downloads the kernel. The kernel reads
   program memory with `RPT`/`TBLR` and sends each word back through the mailbox with the tag as a
   sequence number. The monitor prints the frame on the DTE serial port.

## Two things that had to be got right, and were not obvious

**The read does not need to run from SARAM.** At first, the kernel staged its
`TBLR` loop into on-chip SARAM with `bldp`. The reason was that the program-memory
protection option of TI stops instructions from off-chip memory when they read
on-chip program memory, and the documentation does not name SARAM. That variant returned nothing.
Then the 56-word sample probe read `0x0000`-`0x001f` from a kernel at `0x8000`
and got the vector table back. This proves that **protection is not programmed on
this part**. Thus, the staging was not necessary, and it only added a possible failure.

**The watchdog of the board limits the run.** The board resets a halted monitor after
about one and a half seconds, and that time is not sufficient to print 2048 words as `NNNN:VVVV`.
The first full attempt printed 491 words and was cut in the middle of a line.
The collected buffer was lost, because the firmware clears RAM on reboot. The dump
now prints four hex digits for each word, not eleven bytes, and it is taken in two
halves of 1024. The collection was never the problem. It was already complete when
the reset occurred.

## What it contains

Program `0x0000` is a vector table. It is **not** the alias of the kernel
that read it: the kernel starts with `be41 bc06`, and this table starts with `7980 0670`:

```
0000  7980 0670  b     0670          ; reset
0002  0860       lamm  @60           ; every interrupt dispatches indirectly
0003  be20       bacc                ; through a DARAM B2 cell
0004  0861 be20  lamm @61 ; bacc
...
```

Thus, downloaded code installs its own handlers when it writes data cells `0x60`-`0x6e`.
That is exactly what the clear `lar ar1, #60 / rpt #1f` in the 302 prologue at
`0x801e` prepares.

The reset target is the **boot loader**:

```
0670  setc intm ; ldp #000
067a  apl  @07, #ffd8        ; PMST: clear OVLY and the low bits
067c  opl  @07, #0010        ; PMST: set RAM
0680  splk @28, #ffff        ; PDWSR: maximum wait states
0682  splk @05, #0080        ; GREG
0684  lar  ar1, #ffff
0686  lacl *-                ; read data 0xffff - the boot source word
068c  lacl @60 / and #0003   ; dispatch on its low two bits
068f  bcnd 06c6, eq
0694  bcnd 069b, eq
069b  lar  ar1, @65          ; ...and for that mode
069c  lacc *+ / sacl @66 / sacl @1f   ; destination address -> BMAR
```

It reads its boot table from **data memory at `0xffff`**, which is the top of
the ASIC window, and gets a destination address from it. That is how the
parallel download of the supervisor gets to the part. It is the mechanism that
[dsp-map-302.md](dsp-map-302.md) argued for from only the download *order*:
destination first, reset pulse, then the block, with no "go" after it, because
the loader itself transfers control.

## What this settles

* **MP/MC = 0. The part runs in microcomputer mode.** Program `0x0000`-`0x07ff`
  is on-chip ROM. It is not the external RAM that would alias
  there because A15 is not connected. We inferred this two times, and now we read it.
* **The boot loader is real, and it starts the downloaded program**. Thus,
  `entry_word == 0x8000` of `dsp_download` is a boot-table destination. It is not
  an assumption that the scan enforces.
* **The vector base is zero.** The firmware sets PMST bit 7 (`AVIS`), not
  `IPTR`. The earlier emulator incorrectly decoded IPTR as bits 15–7. Figure 4–3 of TI
  puts IPTR at 15–11 and AVIS at 7. Vectors occupy 2K-word pages.
  Thus, the timer vectors to `0x0008`, through `lamm @63 / bacc`.
  `0x0088` is a numeric table in the captured ROM, not an interrupt vector.

## What it does not settle

The frame has no controls or completion marker. Thus, the evidence for the
content is the tag sequence during the collection, the declared word count and the
checksum. There are also two independent confirmations. A truncated earlier run
returned words `0x0000`-`0x01ea`, and it **agrees with this run on all 491 words**.
The 56-word sample probe returned `0x0000`-`0x001f` separately.

We did not read `MP/MC` itself from the pin. The evidence that the on-chip ROM is mapped is
that program `0x0000` holds this table and not the words of the kernel.

## Running it in the emulator

Load the recovered image with `load_rom`, set `MP/MC = 0` and start
the core at `0x0000`. Then it boots exactly as the disassembly shows:

```
0000 -> 0670 -> PMST and wait-state setup -> read data 0xffff -> serial boot
```

**The boot mode is the word at data `0xffff`.** The loader first uses its low two
bits (`and #0003`, and only `0` gets to the serial paths). Then it uses `bit 12`
and `bit 13` of it (bits 3 and 2) to select between three variants. When the
cell reads `0`, the loader selects the **8-bit** serial mode at `0x06f7`, which
assembles words from byte pairs. When **bit 2** is set, it selects the 16-bit mode at
`0x06e2`. That single bit is what the ASIC has to present.

The boot table that it then reads on the serial port is:

| word | meaning |
|---|---|
| 1 | destination address, kept in `@66` and loaded into `AR1` |
| 2 | length; added to the destination and stored in `ARCR` |
| 3.. | the block, written with `TBLW` and `MAR *+` |

One detail is important when you feed it: **the terminating `CMPR EQ` runs
at the top of the loop, before the write**. Thus, after the last block word, one
more word must clock through to make the comparison operate. Without it, the
loader stays in its wait at `0x06dc` after it wrote the full block correctly.
That is exactly what the first attempt here did. It looks like a failure
until you examine the iteration count.

With destination `0x8000`, the 27710-word 302 resident and one more word at the end,
the loader completes and branches to `0x8000`. The firmware then runs its
prologue **once** and stops in the `idle` at `0x814d`. This is the same location that
the manually forced `set_pc(entry_word)` of the harness gets to. Now the code gets there through the
boot path of the part itself.

Two results are important:

* **The ASIC feeds the DSP serially.** The supervisor writes a parallel window
  at ports `0x40`-`0x5e`. The loader reads `DRR` and polls `SPC`. Thus, the ASIC
  changes those parallel writes into serial words on the port of the DSP.
  This repository had not identified that function of the ASIC.
* **The vectors now have memory under them.** Interrupts dispatch through the
  `lamm @6x / bacc` table of the ROM, and not into unloaded space. Thus, the timer
  runaway at `0x0088` that
  [dsp-map-302.md](dsp-map-302.md) records is a result of the missing ROM.
  It is not a fault in the firmware.

## Bridge integration (2026-09-07)

`--with-dsp` now automatically selects this ROM for the captured 20.16 MHz
DSP 3.0.13 and 3.1.2 payloads (302 and 403). It identifies them by the payload SHA-256.
The bridge clears the preloaded resident and starts at reset in microcomputer mode.
It serializes the captured download of the supervisor through the ROM loader.
It repeats this procedure on a second download. Other payloads keep their
existing behavior. We do not assume that the captured mask ROM is correct for the 25 MHz board.

The interrupt-vector override is removed for these payloads. The correct decoding of the PMST
fields keeps IPTR at zero. Thus, timer and serial interrupts run through the
ROM into the handlers that the firmware installs in B2 RAM. This also corrects the
earlier `IPTR = 1` interpretation in this document and in `dsp-map-302.md`.

A second core correction lets an IMR-enabled interrupt wake `IDLE` while INTM is
set. The execution continues after IDLE and does not enter an ISR. The two fixes follow
[TI SPRU056D, Figure 4–3 and section 4.10.1](https://www.ti.com/lit/ug/spru056d/spru056d.pdf).

`tests/test_dsp_boot_rom.py` transfers the two builds through the two ASIC windows.
This includes a second reset/download. The test checks that the resident was initially empty,
and verifies real serial ISR activity and zero ROM holes. It tests separately the
placement of the PMST fields, the vector relocation and the wakeup from masked IDLE.

The ASIC transport is still a model. It buffers the parallel transfer and feeds
the serial boot table when the supervisor sends its checksum. This does not
reproduce the hardware timing of each word, and it does not validate the ASIC checksum circuit.
`queue_codec_rx` still supplies DRR/RRDY. Thus, the boot words are in the codec
receive counters. A successful boot and an AT response do not establish modem
training or a working data connection.
