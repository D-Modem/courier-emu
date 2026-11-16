# Firmware images out of the SDL upgrade packages

`docs/usrdl/` contains seventeen vendor flash-upgrade packages. Until now, they were
only archives. This work makes the firmware in them readable. We use this to find
what the Sportster Vi DSVD package really is.

`extract_sdl.py` can read the two carriers:

- **`SDL*.EXE`**: the DOS loaders. The image is in the loader as a sequence of
  binary download records of sixteen bytes each:
  `[len=0x10] [addr hi] [addr lo] [type=00] [16 data] [checksum]`. The sum of the full
  record is zero mod 256. Because of that checksum, we identified the format. We did not
  guess it. 13,193 consecutive records are valid in
  `SDL.EXE`, and 18,090 in the V.90 `SDL20.EXE`.
- **`*.XMD`**: the images that the XMODEM loader of the modem accepts. There is a 64-byte
  header. Then the firmware follows, under a flat **XOR 0x55**.

```bash
python3 artifacts/sdl-image-extraction-01/extract_sdl.py extract SDL.EXE --out /tmp/img
python3 artifacts/sdl-image-extraction-01/extract_sdl.py compare a.img b.img
```

`images.json` records the output from four packages, with the sha256 of each image.
Git does not track the images. You can make them again from the
archives, and Git tracks the archives.

## What is not established

The record addresses are 16 bits and they wrap. Thus, they put the records in order in a
segment, but they do not give their location in a 512 KiB flash. If the address does not
increase by 0x10, the tool reports a segment break (17 in the Sportster loader, 27
in the V.90 loader). It does not invent a mapping. **Nothing here is a
flash-accurate image. Do not give any of it to the emulator as a flash-accurate image.** It
is good for strings and for structure, but not for addresses.

We did not decode the 64-byte XMD header. It changes for each build near an `NHCFG`
marker. The packages have warnings that the "wrong model will make your unit inoperable".
Thus, a checksum and a model gate are the probable candidates. But that
is a guess, and we did not test it.

## The Sportster Vi DSVD is a cut-down Courier

`dsvd-sdl.exe` is in a directory of Courier upgrades, and its label is
Sportster. We compared its image with the international Courier 7666 build
(`comparison.txt`):

- **919 of its 1,184 strings (77.6%) are also in the Courier.**
- The **ATI7 field layout is identical**: `Product type`, `Options`,
  `Supervisor date`, `Supervisor rev`, `Clock Freq`, `Fax Options`.
- The Sportster image contains the **product-name table with `Courier` and
  `Sportster` as adjacent entries**, and the literal banner string
  `USRobotics Courier V.32`.
- The **result-code table is the same table in the same order**: `CONNECT`,
  `RING`, `NO CARRIER` ... `9600/ARQ`, `4800`, `7200`, `12000` ... The
  HST entries (`9600/HST`, `4800/ARQ/HST`, `12000/ARQ/HST`) are removed from the
  sequence, and the DSVD codes are added at the end.

The removed items are the premium feature set of the Courier, and only that set:

| | Courier 7666 | Sportster Vi |
|---|---|---|
| HST result codes / Dual Standard | present | removed (11 vestigial references remain in shared tables) |
| Dial Security | 3 references | none |
| Remote Access | 8 references | none |
| `CURRENT DIPSWITCH SETTINGS` | present | none |
| `Serial Number` in ATI7 | present | none |
| ASL statistics (Naks, SREJ, Reversals) | present | none |
| Developer credits block | full | stripped |

The added item is the DSVD voice path: `AUDIO date`, `AUDIO rev`,
`Audio Sampling Rate`, `Algorithm Selection`, `Blocking Factor`, and the
`-SMUTE=n` / `-SMUX=n` commands. Also, the trellis labels have different words. The
Courier says `16S-4D trellis code`, and the Sportster says `16S-4D map`.

The two are not builds of one tree from the same time. The copyright line of the Sportster
stops at 1993. The line of the Courier 7666 continues to 1995, but the date of the Sportster package
is 12/95. It looks like a 1993 fork of the Courier supervisor, which was
maintained separately after that.

## One thing worth carrying into the emulator

The loaders give the name of their CPU. `SDL_7666.EXE` (international, 11/95) says
**`INT80188 Modem Functions`**. The V.90 `SDL20.EXE` (03/98) says
**`INT80186 Modem Functions`**. Thus, there are two different part strings in the Courier
line. Find which is correct before you think that all builds have the same bus width.
This is a string, not a measurement. We did not check it against a board.
