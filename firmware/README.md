# Firmware catalogue

This directory is the entry point for firmware assets. It intentionally does
not duplicate each image. The established locations of the source families in `docs/`
do not change, and the list below gives them. The only asset set that we moved
is the previously generic `docs/New Folder With Items/`. It is now
`firmware/legacy-usrobotics/`.

Before you do experiments or flash a board, read the
[firmware lineage map](../docs/firmware-lineage.md) for compatibility. Evidence supports this map. It
separates the 20.16 MHz and 25 MHz analog images from the incompatible 386EX I-modem/ISDN family.
It also marks the regional classifications that are not yet proved.

## Primary Courier images (kept in `docs/`)

These are the six 736 KiB XMF supervisor/DSP containers that the emulator uses.
Each directory keeps its companion `Firmware.txt` and its original ZIP.

| Version | Extracted image | Original archive |
| --- | --- | --- |
| 2.1.1 | `docs/3453Bv2.1.1/3453Bv2.1.1.xmf` | `docs/3453Bv2.1.1.zip` |
| 2.2.05 | `docs/3453Bv2.2.05/main2205.XMF` | `docs/3453Bv2.2.05.zip` |
| 2.3.12 | `docs/3453C_v2.3.12/MAIN_2.3.12.XMF` | `docs/3453C_v2.3.12.zip` |
| 2.3.15 | `docs/3453C_v2.3.15/MAIN_2.3.15.XMF` | `docs/3453C_v2.3.15.zip` |
| 2.3.31 | `docs/3453C_v2.3.31/MAIN_2.3.31.XMF` | `docs/3453C_v2.3.31.zip` |
| 2.3.33 | `docs/3453C_v2.3.33/2_3_33.XMF` | `docs/3453C_v2.3.33.zip` |

Git ignores the XMF payloads because they are redistributable binary
inputs. Git continues to track the small provenance files and the archives.

## Active local inputs (kept at repository root)

The working-copy inputs of the emulator intentionally stay at the root:
`3453Bv2.1.1.xmf`/`main211.xmf`, `main2205.XMF`, `MAIN_2.3.12.XMF`,
`MAIN_2.3.15.XMF`, `MAIN_2.3.31.XMF`, and `2_3_33.XMF`. Also
`IDSDL302.ROM`, `IDSDL302.XMD`, `SDL0430.XMD`, `SV_49.XMD`, `SV25.XMD`,
`Ie030002.nac`, and `Ie030002.xmp`. Git ignores these local binary inputs.
Some of them are duplicates of the catalogued source copies. We intentionally keep them
at the location where command-line experiments and ad-hoc analysis look for them.

## Legacy USRobotics collection (relocated here)

`legacy-usrobotics/` is an imported collection of firmware updaters, their
expanded payloads, and the related installers. The package archives stay next to
their extracted directories to keep the provenance.

| Family | Firmware payloads | Notes |
| --- | --- | --- |
| ID_SDL 3.02 | `IDSDL302.XMD`, `IDSDL302.ROM`, `idsdl302/IDSDL302.ROM` | The two ROM files are byte-identical; SHA-256 `49f4182c…f2ccc5`. |
| ID_SDL 4.01–4.03 | `ID20C401`, `ID20C403`, `ID20D401`–`ID20D403`, `ID25C403`, `ID25D401`–`ID25D403` `.XMD` files | Each has an adjacent extracted updater directory and/or ZIP. |
| Sportster/V.90 SDL | `SDL0430N/SDL0430N.XMD`, `SDL0430X/SDL0430.XMD`, `SDL0430X 2/SDL0430.XMD`, `SDL_V90 2/SV_49.XMD`, `SV_49.XMD`, `SDL1202I/V90XX.XMD` | The two SDL0430X payloads and the two SV_49 payloads are duplicate pairs. |
| Other modem images | `2332-sdl302/Ie030002.nac`, `2332-x302*/Ie030002.xmp`, `1.00.015.dlf`, `v1_00_20120820.hex`, `v1_17_20140619.hex` | Keep the matching ZIP/RAR/EXE updater packages with these files. |

There are 16 `.XMD` payload files in this collection. For the container format, refer to
[`docs/xmd-container.md`](../docs/xmd-container.md).
Use the paths above. Do not use the old generic import directory.

## Other established firmware archives (kept in `docs/`)

- `docs/usrdl/` — USRobotics download/update packages (12 MB).
- `docs/x2/` — x2, V.90, HiPer DSP/NMC, and NETServer-era packages (209 MB).
  This is a mixed collection of I-modem and Total Control/NETServer packages. Before you
  think that two packages are interchangeable, read
  [`docs/x2/README.md`](../docs/x2/README.md).
- `docs/pm/` — PM modem firmware revisions (`pm3_3.5`, `pm3_3.8`,
  `pm3_3.9`, and `pm3_3.9b9`).
- `docs/494-01.zip`, `docs/5436-files.zip`, `docs/MODEM.RAR`, and
  `docs/R54548.EXE` — standalone archived firmware/update material. We keep the
  original names until we identify their hardware provenance.

PDFs, INF files, installers, and extracted application files are not
directly executable modem firmware. They stay with their source package as
context. The actual payload can be in an embedded archive or updater.

The two `artifacts/courier-board-21210-capture-*/courier-board.rom` files are
hardware captures. They are not distributable source firmware. They stay with the
experiments that made them. We did not move them into this inventory.
