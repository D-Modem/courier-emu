# Courier firmware lineage

This is a classification of the firmware assets in this repository. It does not
claim that all files are interchangeable. The clock, the CPU, the line interface, and the
container format are compatibility boundaries. The evidence column tells
if a conclusion comes from a parsed image, from supplied release material, or
only from a filename.

## The family tree

```
USR/3Com remote access
├── Analog Courier V.Everything — Intel 80186/80188-class supervisor + TI C5x DSP
│   ├── 20.16 MHz / 512 KiB flash
│   │   ├── stock SDL 3.02: IDSDL302.ROM / IDSDL302.XMD
│   │   └── Russian ID_SDL 4.01–4.03: ID20C* and ID20D*
│   ├── 25 MHz (25.8048 MHz in main211) / 512 KiB or later 736 KiB image
│   │   ├── stock SDL: SV25.XMD, SDL0430*, SV_49.XMD
│   │   └── Russian ID_SDL 4.01–4.03: ID25C* and ID25D*
│   └── later V.92 Courier update series: 3453B/3453C XMF images
├── Courier I-modem / ISDN — Intel 386EX + AMD Am79C30A
│   └── IE/IM releases in NAC or XMP containers, including Ie030002
└── Total Control / NETServer ISP platform
    ├── Quad x2 Modem NAC — 80186 + C50, shared analog Courier code lineage
    ├── Network Application Cards: analog/digital modem and PRI/ISDN service code
    └── HiPer ARC/DSP/NMC/MultiSpan DMF firmware
```

The two top-level branches are architectural. They are not only software revisions.
The analog branch boots an 80186/80188-class supervisor and downloads C5x DSP
programs. The I-modem branch executes 386EX code and initializes the Am79C30A
ISDN front end. For the proof at the register level, refer to
[the ISDN front-end analysis](imodem-isdn-front-end.md).

## Analog Courier V.Everything

| Subfamily | Images in this tree | Clock / storage | CPU architecture | Region and identity | Evidence / confidence |
| --- | --- | --- | --- | --- | --- |
| Stock 3.02 reference | `IDSDL302.ROM`, `IDSDL302.XMD` | 20.16 MHz, 512 KiB flash | Intel 80186/80188-class + TI C5x family DSP | US/Canada External; supervisor 7.3.14, DSP 3.0.13, dated 1998-03-13 | Direct ROM strings plus two hardware probes; high confidence. |
| ID_SDL 4.01/4.02 | `ID20C401`, `ID20D401`, `ID20D402`; `ID25D401`, `ID25D402` | `ID20` = 20.16 MHz; `ID25` = 25 MHz | Same analog 80186/C5x platform | Russian AON modification, based on the 1998 International SDL; documentation says it supports US/Canada and International hardware but is adapted for Russian/ex-USSR lines | Bundled `FILE_ID.DIZ` and CP866 release notes; high confidence for intended target, not a guarantee of installed country configuration. |
| ID_SDL 4.03 | `ID20C403`, `ID20D403`; `ID25C403`, `ID25D403` | Same `ID20` / `ID25` split | Same analog 80186/C5x platform | Same Russian AON / International base. `D` 4.03 is the verified 20.16 MHz board lineage: supervisor 7.4.16, DSP 3.1.2 | Release notes identify the clock and modification; the 20.16 MHz `D` lineage is additionally verified against the 403 capture. |
| Stock 25 MHz XMDs | `SV25.XMD`, `SDL0430.XMD`, `SDL0430N/SDL0430N.XMD`, `SV_49.XMD` | 25 MHz board family, 512 KiB flash | Same analog 80186/80188-class + C5x family | `SV25` is a probed US/Canada External 25 MHz family image; the country configuration of the other files is not established | `ATI7`/ROM family evidence for `SV25`; XMD overlay decoding for the group. |
| Other analog XMD assets | `SDL1202I/V90XX.XMD`, plus duplicate package copies of `SDL0430.XMD` and `SV_49.XMD` | 512 KiB XMD payload; clock not yet established for `V90XX` | Same analog 80186/80188-class + C5x family | No regional conclusion | The decoded overlay table proves analog V.Everything lineage; it does not prove a clock/region. |
| V.92 XMF series | `3453Bv2.1.1`, `3453Bv2.2.05`, `3453C_v2.3.12`, `.15`, `.31`, `.33` XMF | 25.8048 MHz for `main211`/2.1.1; 736 KiB update image | Same analog 80186/C5x software lineage | Courier V.Everything V.92 update packages; region is not established by their bundled `Firmware.txt` | Parsed XMF layout and timer constant; high for format/clock of main211, unknown region for the series. |

`C` and `D` in the ID_SDL filenames are the 4.01c/4.01d,
4.02d, or 4.03c/4.03d suffixes of the release. They are not CPU types. Also, `20` and `25` are
explicit labels for clock compatibility in the release material. They are not version
numbers. Do not flash an `ID20` image on an `ID25` board, or an `ID25` image on an `ID20` board.

At first, we captured the physical 20.16 MHz reference board with stock 7.3.14
/ DSP 3.0.13. Later, it ran ID_SDL 4.03d / 7.4.16 / DSP 3.1.2. That is a
software update in one analog hardware lineage at 20.16 MHz. It does not make
the 25 MHz images equivalent.

## I-modem / ISDN line

| Series | In-repository forms | CPU / line hardware | Release lineage | Region |
| --- | --- | --- | --- | --- |
| I-modem | `Ie030002.nac`, `Ie030002.xmp`, and IE/IM archives under `docs/x2/` | Intel 386EX, AMD Am79C30A ISDN controller | IE 1.02.03 (1996), IM 2.00.09 (1996), IM 1.05.01 (1997), IE/IM 2.01.04 (1997), IE 2.02.02 (1997), IE/IM 2.04.05/06 (1998), IE 3.00.02 (2000) | Not established by current evidence. |

`Ie030002.nac` and `Ie030002.xmp` are two encodings of the same 753,664-byte
payload with the base at physical `0x40000`. Neither includes the boot block of the I-modem
or the reset vector. The `.nac` stream is binary records in a style similar to Intel HEX. The
`.xmp` body is XOR-obfuscated with `0x45`. These files are incompatible with
the analog XMF/XMD update path, although they have the same Courier branding.

[imodem-firmware-timeline.md](imodem-firmware-timeline.md) documents the feature history
of the I-modem independently: x2 appears in
2.01.04 and V.90 in 2.04.05/06. That timeline is a timeline of protocol features.
It is not a regional classification.

## Quad x2 Modem NAC

| Series | In-repository forms | CPU / line hardware | Line modes | Evidence |
| --- | --- | --- | --- | --- |
| Quad x2 Modem NAC | `QF060003.NAC` (6.0.3), `QR060103.NAC` (6.1.3), both 1998-09-22 | Intel 80186 + TMS320C50, per channel | One combined image: `%D0` Standard Analog (POTS), `%D1` T1 Mode (DS0), `%D2` ISDN PRI Mode | Byte-level comparison against `IDSDL302.ROM` and `main211`, the `%D` help table, and an 8M-instruction execution run. |

This is the branch that is closest to the standalone analog Courier in this tree. The
Quad NAC has more shared 32-byte blocks, and a longer identical run, with the
analog SDL 3.02 ROM than `main211` has. Its product-name table adds
`Analog Quad`, `Digital Quad`, and `Analog/Digital Quad` to the Courier list.
Its digital support is at the DS0 level, not at the T1-framer level. The shared runs
are mostly tables on the two sides. Thus, this is a shared source lineage. It is not
proved byte-identical executable code.

The two images execute without a fault when they start at their `0x80000` load base.
Then they stay in a loop that polls their chassis host interface. For the measurements, the run
result, and the limits of each conclusion, refer to
[quad-x2-modem-nac.md](quad-x2-modem-nac.md).

## Total Control / NETServer: the larger x2-era platform

The `docs/x2/` directory also contains the ISP-side equipment that shows the
remote-access role of the I-modem clearly. It contains operational code for NETServer Network
Application Cards (`LE`/`LF`), a PRI NAC image (`DP030105`), a NETServer ISDN
NAC image (`LI030534`), HiPer ARC router firmware, and HiPer DSP/NMC/
MultiSpan card firmware. This is a product/platform lineage that the
I-modem also has. It does not claim that they run the same binary or processor. The I-modem
is proved to be 386EX/Am79C30A. The HiPer ARC firmware explicitly names a PowerPC.

For the split for each package, refer to [`docs/x2/README.md`](x2/README.md). It also gives
the direct strings that link the server code to I-modem pools, PRI spans, and
B-channels. It also records a byte-level comparison. The I-modem and the
NETServer/PRI images that we can examine have a common Ready Systems VRTX marker. But we found no
non-trivial identical run of application code of 32 bytes or longer.
The server cards explicitly use VRTX32/I386. The I-modem identifies VRTX/86 on
its 386EX.

## Container and payload types

| Type | What it contains | Applicable branch | Handling |
| --- | --- | --- | --- |
| Raw `.ROM` | Complete 512 KiB analog flash image, including boot block | Analog | `courier rom-info`; bootable subject to matching board hardware. |
| `.XMD` | 128-byte SDL header plus an encoded complete 512 KiB analog flash image | Analog | Decode before comparing code/offsets with a ROM. XMD offsets are not flash offsets. |
| `.XMF` | Courier application update with product header, supervisor, and C5x payload; no board boot block | Analog | `courier info` / `extract`; an application update, not a raw flash dump. |
| I-modem `.NAC` | 32-byte header plus binary Intel-HEX-style ISDN update record stream | I-modem / ISDN | `courier nac-info` / `extract`; programs the shared ISDN update payload. |
| `.XMP` | Header plus XOR-obfuscated ISDN update payload | I-modem / ISDN | `courier xmp-info` / `extract`; equivalent decoded payload to the matching NAC. |
| Other `.NAC` payloads | Product-tagged 3Com SDL/NAC card updates, including NetServer and PRI cards; their framing differs from I-modem NAC | Total Control / NETServer; a separate analog DSP component also appears in an SDL package | Do not feed these to `courier nac-info`; classify from package/product tag and content. |

## What remains unknown

- The *running country setting* of a file is stored/configured separately from its
  wide product family. “US/Canada External” is proved only for the two probed
  reference units. The Russian ID_SDL packages can explicitly operate in multiple countries,
  but their main purpose is Russian lines.
- `SDL0430*`, `SV_49`, `V90XX`, and the XMF updates have no complete regional
  proof in this tree. Thus, we intentionally do not give them the label US-only or
  International-only.
- The instruction set makes the “C5x DSP family” certain. On the photographed 20.16 MHz
  board, the specific analog board part is more probably C50/LC50 than C52. Do not apply
  that conclusion about the component to all images.
- The 736 KiB XMF sequence is a later software lineage of the 25 MHz family. But this repository
  directly measures only the 25.8048 MHz timing of `main211`.

For the direct evidence, refer to
[courier_firmware_analysis.md](../courier_firmware_analysis.md),
[xmd-container.md](xmd-container.md),
[hardware-timebase-and-audio-path.md](hardware-timebase-and-audio-path.md),
and [board-parts.md](board-parts.md).
