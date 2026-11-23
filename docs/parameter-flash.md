# The parameter flash

## The parameter flash, and storing a profile

`AT&W` writes the working profile to the parameter store. That store is four
4 KiB sectors at physical `0xf8000`. Each sector ends in a 32-bit version at
`0xffa` and a CRC-16/CCITT at `0xffe`. The search at `0x7e07c` calculates the
checksum of all four sectors. It keeps the highest version that verifies.
`parameters.py` documents the layout, and the `parameters` subcommand builds a
sector.

The writer at `0x7dfa8` does not access the part directly. It calls the boot
block through `int 0x0a` with an ASCII service letter in `BL`:

| service | meaning |
|---|---|
| `E` (0x45) | erase the 4 KiB sector selected by `ES` |
| `W` (0x57) | program the word in `AX` at `ES:DI`, then advance `DI` |
| `S` (0x53) | firmware-update path, not modelled |
| `L` (0x4c) | block lock/select, not modelled |

An XMF update image carries only the application. Thus, in a run that you build
from one, that vector points at nothing, and `AT&W` stops at the first call.
When a part is attached, the harness answers `E` and `W`. This is what `AT&W`
needs, and no more. `S` and `L` still stop the run. The harness does not
continue on a guess.

```sh
./courier run main211.xmf --parameter-flash board.flash --at ATS0=7 --at 'AT&W'
./courier run main211.xmf --parameter-flash board.flash --at 'ATS0?'
```

The second run answers `007`. The harness makes the file in the erased state
(`0xff`). The blank check at `0x7e0e3` looks for this value. The harness
accepts a 4 KiB file as the first sector. The run reports a `flash` block with
the erase count, the program count, and the version and checksum validity of
each sector.

If you store many times, the firmware uses the sectors in sequence. To go back
to the start, it erases one sector. The writer of the firmware itself drives
all of this. `refused_bits` counts the bits that a program had to set and not
clear. It stays zero while the model and the firmware agree about the result of
an erase.

When a stored profile is attached, `ATI5` shows it, and not the page for an
empty store.


## Parameter sector

The persistent configuration is in a 16 KiB parameter flash. The firmware
searches it at physical `0xf8000`, and the XMF update image does not carry it.
The search at `0x7e07c` examines four 4 KiB sectors. It calculates the checksum
of bytes `0x000..0xffd` and compares it with the word at `0xffe`. It keeps the
sector with the highest 32-bit version at `0xffa`. The firmware copies the
selected sector to `0x0a06`, one byte for one byte. Thus, sector offset *i*
goes to RAM `0x0a06 + i`:

| offset | RAM | role |
|---|---|---|
| `0x00` | `0x0a06` | flags; bit 3 keeps `[0x0a03]` clear |
| `0x01..0x06` | `0x0a07..0x0a0c` | country, features, type2, type1, unused2, unused1 |
| `0x11..0x1c` | `0x0a17..0x0a22` | serial number, 12 ASCII characters |
| `0x1d..0x2f` | `0x0a23..0x0a35` | packed config, expanded at `0x64044` |
| `0x30..0x61` | `0x0a36..0x0a67` | working-profile image, scattered at `0x6406f` |
| `0xffa` | | 32-bit version |
| `0xffe` | | CRC-16/CCITT over `0x000..0xffd` |

The firmware expands the packed config through the `(shift, mask)` table at
`0x63f8d` into the 36 profile bytes `0x0932..0x0955`. It scatters the profile
image to `0x08de` plus the 50 offsets listed at `0x63fd6`. It reads the serial
number as nine characters at `0x0a17` plus three at `0x0a20` (`0x835bb`).
`0x77bb9` reads four `0xffff` words as "no serial fitted".

A dump of the real part is not practical. Thus, `parameters` synthesizes a
sector that the firmware accepts. The sector has the power-on defaults of the
firmware for the packed config and the profile image. Thus, only the fields
that you set change:

```sh
./courier parameters params.bin --serial 12345678 \
  --feature hst --feature fax --feature terbo --feature v34 --feature v90
./courier run main211.xmf --instructions 8000000 \
  --parameter-sector params.bin --at ATY14
```

This gives the same configuration dump that a unit with all features reported.
`ATI7` shows the full profile, with the serial number:

```text
000,000,030,007,031,000

Product type           US/Canada Internal
Product ID             XX345302
Options                HST,V32bis,Terbo,VFC,V34+,V90,V92
Clock Freq             25 Mhz
Serial Number          12345678
```

The first byte of the sector gates each unpacked field. The firmware applies a
field when its bit is clear. `--flags` sets this byte. Bit 3 sets whether type1
gets to `[0x0a03]`. `0x8339f` tests bit `0x04` of that byte before the firmware
can get to the `ATY15` case. Thus, the default `0x08` is the cause of the
`ERROR` answer to that command. With a sector that has bit 3 clear and type1
with `0x04`, the command prints the factory switch page. This page reports all
ten option switches as the firmware reads them:

```sh
./courier parameters params.bin --serial 12345678 --flags 0
./courier run main211.xmf --instructions 9000000 \
  --parameter-sector params.bin --at ATY15
```

```text
CURRENT DIPSWITCH SETTINGS
DIPSWITCH #1   ON
DIPSWITCH #2   OFF
DIPSWITCH #3   ON
...
```

Archived notes for older Courier firmware call feature bit 4 (value 16) x2. But
on this 2002 build, it gates V.90. `0x77d47` uses it to add `,V90` to the
options list. `0x82e7d` uses it to select the `5608` product code, not `3368`.
The options table has an `x2` string at `733c:49d6`, but nothing in the image
loads it. Thus, **this firmware cannot report x2**.

The board identification straps select the enclosure that `ATI7` reports. This
is a useful cross-check against a physical unit:

| `--board-id` | capability | `ATI7` product type |
|---:|---|---|
| 2, 9, 12 | `0x29`, `0x28` | Internal |
| 5 | `0x14` | Rackmount |
| 7, 13 | `0x22` | External |

This does not agree well with the default. Codes 2/9/12 have capability bit
`0x08`, the settings-EEPROM bit, but they report Internal. The External codes
do not have this bit. Also, `0x667cb` has a special case for capability `0x22`
only: it always returns `OK`. Thus, an external unit is probably
`--board-id 7`. This also changes the product code to the form with the `A`
suffix (`5608A`/`3368A`). A run of `ATI` on real hardware will give the answer.
