# The 3453B needs the C51 mask ROM; the 3453C unmaps it

We measured this against `artifacts/dsp-onchip-rom-20mhz-8k/c5x-onchip-rom-8k.bin`,
the 8K ROM recovered from the 20.16 MHz board, on 2026-09-15. The addresses
are C5x program words. Background: [the download architecture](c51-cpu-loader.md) and
[the origin correction](hardware-timebase-and-audio-path.md#3-corrected-the-xmf-payload-loads-at-8000-not-0000).

## Each family says so itself, in PMST

The residents of the two families start with the same prologue - the same
wait states, the same `splk @7d, #27bd`, the same `apl @07, #07f8`. They
become different at the next instruction, the `opl` that sets PMST:

| | `opl @07` | IPTR | interrupt vectors | MP/MC |
|---|---|---|---|---|
| 2.1.1, 2.2.05 | `00b0` | 0 | `0000` | **left at the pin** |
| 2.3.12, .15, .31, .33 | `18b8` | 3 | `1800` | **forced to 1** |

`apl #07f8` keeps bit 3. Thus the B series never writes `MP/MC`. On the 2806
board, the pin reads 0 and the ROM stays mapped. With `IPTR` at zero, the
interrupt vectors of the part *are* the table of the ROM at `0000`. The C
series sets bit 3 directly - there is no on-chip ROM in the program map - and
moves the vectors to `1800`, in its own downloaded resident.

The two families literally share the prologue. The init of the ROM at
`0610..0619` is byte-identical to the B resident through `apl @07, #07f8`.
The first word where the C resident is different is that `opl`.

## What the C series carries instead

The first 32 words of the ROM are a dispatch table - `b 0670`, then `lamm @6x ;
bacc` pairs that vector through the mailbox cells. Each 2.3.x image has that
table at program **`1802`**. No 2.1/2.2 image has it at any address:

```
MAIN_2.3.12/15/31, 2_3_33    trampoline table at 1802
3453Bv2.1.1, main2205, main211   nowhere
```

16 of the first 20 slots are identical and in the same sequence. This
includes the pair `setc intm … clrc intm ; ret`. The head branch points at
`0f46` instead of `0670`. `TRNT`/`TXNT` become `rete`. The copy stops after
`@6a`, but the ROM continues to `@7b`. The two families write handler
addresses into the same cells (`@64`, `@65`, `@6b..@77`, `@7a`). Thus the C
series must have a dispatcher, and because no ROM is mapped, it must supply
one.

## Nothing else came from the ROM

The block of 2.3.12 at program `0000..0ff9` is exactly in the ROM window, but
it is not related to the ROM: **11 words identical out of 4,090**, nine of
them `0000`, and the longest identical run is **one word**. No 64-byte run of
the ROM occurs in any 2.3.x file. It is usual datapump code - the head of the
relocated table branches into it at `0f46`. This code clears buffers, installs
handler addresses and calls `4235`/`4241` in the resident.

Specifically, the **service loader of the ROM is not copied**. The `0000`
block contains no `BLDP`. The 80 `BLDP` instructions in the resident are its
own overlay loader, at the same relative offset as in the B series (`1165`
against `8168`). Thus these images do not tell what does the *first* download
on a 3453C - the transfer that installs the resident before any of this runs.
The supervisor drives the same ports (`40..5e`, `18`, `1c`) as a 302/403
supervisor. This implies that a DSP-side loader still listens. We did not test
where this loader is on a part that then unmaps the ROM. A 3453C that runs
2.3.33 is now on the bench. Its DSP boots and answers mailbox tags. Refer to
[board-verified-3453c.md](board-verified-3453c.md).

## What is at `1800`, then: RAM, and probably the same RAM

The vectors are in memory that the download writes. Row 5 is one contiguous
transfer - start `0`, end `cbc0`, which arrives at program `1000..75df`. The
trampoline table is at `1802`, in the middle of the stream. The same `BLDP`
writes as the code on each side of it install it. Thus `1800` is writable
program memory on that board. That is the reason to unmap the ROM in the same
prologue that points the vectors there.

The images do not tell which writable memory it is, but the extents are
suggestive. If you take each row of the table of each family, the resident and
the four overlays:

| | program extent | words |
|---|---|---|
| 3453B | `8000..f5d9`, row 9 to `f707` | 30,472 |
| 3453C | `0000..75df`, row 9 to `7707` | 30,472 |

The extent is the same `0x7708` words. The extent of the C series is exactly
`0x8000` lower. The two `CY7C199` parts of the B board are 32K words, and its
image fills them with about 1.5K left. The C image must have the identical
quantity at the other end of the map. The simplest hardware for that is the
same pair of RAMs, with the top address line decoded the opposite way. This is
what `MP/MC=1` makes possible, because with no ROM at `0000..1fff`, all of the
64K is external.

`PMST.RAM` is set. Thus on-chip SARAM would map into program space if the part
had SARAM that gets to `1800`. Only a `'C50` (9K, `0800..2bff`) or a `'LC56`
(6K, `0800..1fff`) has this. The bit is not evidence of SARAM, because the B
images set the same bit, and their program never comes near the SARAM window.
It is inherited boilerplate in the two families. Also, no part with SARAM that
gets to `1800` can hold more than one tenth of a 30K image.

To find the decode itself, a 3453C board on the bench is necessary. The open
question above also needs it.

## It is not about V.92

V.92 is already in the B series: `3453Bv2.1.1` has the `+PQC` quick-connect
command set and the `V.92` identity string, the same as 2.3.33. `MOH_status`
occurs from 2.2.05. The DSP payload of the C series is **smaller** - 48,199
words against 55,638, a decrease of 7,439 words - and it asks for the same
`0x7708`-word extent as the B series. The move into low memory did not give
more space and did not cover an added feature. On this evidence, it is a board
change, not a change for firmware size.

## Reproducing

```sh
./courier info MAIN_2.3.12.XMF        # the four segments, from the supervisor's table
./courier dsp-run MAIN_2.3.12.XMF --instructions 100000
```

`dsp-run` reports `resident_origin` and boots from it. 2.3.x reads `1000`.
2.1/2.2 read `8000`.
