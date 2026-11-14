# The 25 MHz board's DSP carries the same mask, and the ROM is 8K

We took this capture after we reflashed the 2806 from stock 7.3.14/3.0.13 to ID_SDL v4.03d
(`artifacts/xmodem-program-id25-403`). This reflash put `ATGLK2W` on this board,
and only because of it could we send the probe. After it, the board has the same supervisor and DSP revision
as the 20.16 MHz unit. Thus, the only difference between the two is the clock.

## The answer to the question this was run for

`0x0000`-`0x07FF` from this board is **byte-identical** to
`artifacts/dsp-onchip-rom-01`, which we took from the 20.16 MHz unit.
The two have `sha256 3e30fb31ac87fc9d0b8a85da245511ef3caa4e83249f56b5852d9d0829e93f67`.
It is the same mask in the two generations. It is not necessary to model any part of the DSP boot path
two times.

## The C50/C51 test in probing.md is invalid as written

That test says: read `0x0800` two times. On a 'C50, the two reads must be
**different**, because `0x0800` is the 9K SARAM that holds the live
scratch of the firmware. We ran it here two times, and the two reads are byte-identical. The test
would score this as 'C51.

It is not a 'C51 result. The test is defective. The probe *resets the DSP* and
takes control of it. Thus, the firmware with the scratch that the test wanted to monitor does not
run when the probe reads the first word. Neither part can give a read that changes under this probe.
Thus, identical reads give no information.

> An earlier revision of this file said that the cause was that `PMST` starts with its reset
> defaults. That was wrong, and `artifacts/dsp-memory-test-2806` shows why:
> `PMST` reads `00b0` on this board, with `RAM` and `OVLY` **already set**, before
> the `opl @07, #0030` that each kernel here executes. We took the reset-defaults explanation
> from the manual and not from the part.

The test that operates correctly is a write-readback. It is in
[artifacts/dsp-memory-test-2806](../dsp-memory-test-2806/README.md). **The part
is a 'C51: 8K of on-chip ROM at `0x0000`-`0x1FFF`.** Thus, the
`0x0000`-`0x07FF` capture of this directory was a quarter of the ROM. The remaining part is now
here too.

## The whole 8K, and it is mostly unprogrammed

`c5x-onchip-rom-8k.bin`, 8192 words, `sha256 70db9861…`. We assembled it from the six
1K windows in this directory. Only three regions contain data:

| | words | |
|---|---|---|
| `0000`-`077F` | 1920 | the vector table, the boot loaders, ending `077a: b 0779` |
| `0F80`-`0FFF` | 128 | a mailbox handshake block |
| `1F80`-`1FFF` | 128 | **byte-identical to the `0F80` block** |

All other words (6016 words) are a **32-word period of 16 x `FFFF` then 16 x
`0000`**. Unprogrammed mask cells read as this pattern here. The same pattern
continues from `0x0780` through `0x07FF`. For this reason, the 2K capture looked like it
ended in padding. Those last 128 words are unprogrammed ROM. They are not a boundary.

> **Corrected.** At first, this file interpreted the two identical 128-word blocks as
> one block that the mask puts at the end of each 4K page. That is not correct. The part of the 20.16 MHz board
> returns the **pure array pattern** at `0x0F80` and the same block at `0x1F80`,
> in the two read paths. The mask contains the block one time, at `0x1F80`. This part
> also returns it from `0x0F80`, and the other part does not. Refer to
> [dsp-onchip-rom-20mhz-8k](../dsp-onchip-rom-20mhz-8k/README.md).

## Is it really unprogrammed, or is protection hiding it?

The program-memory protection of TI prevents instructions fetched from **off-chip
memory** from reading on-chip program memory. It does not name SARAM. Each
read above ran from a kernel at program `0x8000`, which is off-chip. This is exactly
the configuration that the protection blocks. Thus, before we could claim "unprogrammed", we had to read
the empty regions again from code that executes on-chip.

`--via-saram` copies the read loop into SARAM with `bldp` and calls it there.
That path existed before, and the record said that it "returned nothing". But its
gadget address was `0x0900`. We selected this address when we thought that the part was a 'C50 with
9K of SARAM from `0x0800`. On the real part, `0x0900` is **on-chip ROM**. Thus, the
gadget was never written, and the call ran ROM. `ROM_DUMP_GADGET` is now `0x2000`.
The sweep found the SARAM at this address.

| window | read from SARAM vs. read from `0x8000` |
|---|---|
| `0x0000`-`0x03FF` | **identical** - 975 distinct values, the vector table |
| `0x0C00`-`0x0FFF` | **identical** - the array pattern, and the `0x0F80` block |

The `0x0000` window is the positive control. It proves that the staged loop really
executed and really read. If the gadget had not been written, the call would have stopped
on garbage and not returned the vector table. The `0x0C00` window is the
question, and the protection does not hide anything there.

**Also, the empty span is mapped, not absent.** If `0x0800`-`0x1FFF` were only
undecoded, nothing in it would answer. But `0x0F80` and `0x1F80` return
stable, coherent code. The ROM decodes across the full 8K, and only small parts of it are
programmed.

## The memory map, measured

From `artifacts/dsp-memory-test-2806/sweep`, 21 addresses:

| program | |
|---|---|
| `0000`-`1FFF` | 8K on-chip ROM. Writes through data space never appear. `0x0400` reads `3cc4`, real ROM content, as the control |
| `2000`-`23FF` | **1K SARAM** - a write to data `0x0800` comes back from program `0x2000`, and data `0x0A00` from program `0x2200` |
| `2400`- | external RAM, the same memory in both spaces |

Data space: SARAM at `0x0800`-`0x0BFF`, and external memory above it. Note that the buffer at data
`0x1000` is external data memory. This is a different memory from program `0x1000`.
For this reason, a read of program `0x1000`-`0x13FF` never had a collision with it.

## Reproducing

```sh
python -m courier_emu.probe_transport --reference IDSDL302.ROM --rom-dump \
    --rom-origin 0 --rom-words 0x400 --output artifacts/dsp-onchip-rom-2806/half0
python artifacts/dsp-onchip-rom-2806/run-board.py \
    artifacts/dsp-onchip-rom-2806/half0 /dev/cu.usbserial-FT4TQOFT
```

`--reference IDSDL302.ROM` is not a claim about the flashed firmware. The
monitor copies the DSP launch and download routines from this file. Only
`IDSDL302` contains them in the form that `probe_transport` recognises. We took the 20.16 MHz
capture in the same way, while that board ran 4.03d.

Each run here restored the board. After each run, `AT` answered and the watchdog put
the timer-0 vector back. We checked this each time.
