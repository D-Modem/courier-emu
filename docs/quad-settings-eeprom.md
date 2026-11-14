# Quad QF060003: the settings EEPROM and what each record controls

`ATI7` on the Quad reported `V32bis,Terbo,V.FC,V34+`. It did not report HST, x2 or V90.
The firmware did not read any item of that list from a device. It is the XOR constant of the firmware,
which shows as data when the settings part is not installed.

The store is the same 93C66 Microwire part that the 302 and the 403 have. It is at the same
EEPROM word, in the same layout, and the firmware accesses it through the same 186EB PIO lines that
`machine.py` already translates. The Quad only needed a seeded part.

## The store

There are six settings, with three redundant bytes for each, and each copy uses a different obfuscation. The eighteen bytes are
at **EEPROM word 94**, and the firmware caches them in modem RAM at `0x86ee..0x86ff`.

| | |
|---|---|
| pointer table | `0xceb4a`: `86fd 86ee 86f1 86f4 86f7 86fa` |
| storage order | physical slots hold settings **2,3,4,5,6,1** |
| getter | `0xceae1`, index 1..6 in `AL`, carry set on failure |
| setter | `0xceb58`, reached from `0xceaa9` (the `=` command path) |
| validator | `0xceba7`, 2-of-3 majority, `AH` names the dissenting copy |
| far wrapper | `0xc041:0x0e5d` — how other segments read any index |

The three copies are `ror(b,2)+5`, `rol(b,1)-0x0f`, and `b xor 0x1d`. These are byte
for byte the transforms that `courier_emu.ram_dump.decode_settings` already implements
for the `e237` of the 302. The storage order is `IDSDL302_RECORD_ORDER`. The word is
`IDSDL302_SETTINGS_WORD`. This is not a store that is specific to the Quad. It is the Courier
settings part on a Quad card.

## The transport

The transport is bit-banged Microwire on the 80C186EB PIO registers. It is not an I/O port. This is
why a scan for `out 0x10` finds nothing:

| line | register | bit |
|---|---|---|
| DI | `[0xff5e]` | 7 |
| DO | `[0xff5a]` | 7 |
| CS | `[0xff56]` | `0x20` |
| CLK | `[0xff56]` | `0x04` |
| DO direction | `[0xff58]` | 7 — cleared for the frame, then restored |

The `rol al,1 / rcl bx,1 / rcr al,1` sequence shifts twelve command bits MSB-first out of `BX`.
At `0xc1753`, sixteen data bits are shifted back in
from `[0xff5a]` bit 7. Frame builders:

| routine | opcode | frame |
|---|---|---|
| `0xc16f7` | `AH=6` read | `ax = (di - 0x8632) >> 1; ah = 6; rol ax,4` |
| `0xc15e4` | `AH=5` write | same address arithmetic |
| `0xc1588` / `0xc158d` | — | fixed `bx = 0x4000` / `0x4c00` |

`(di - 0x8632) >> 1` puts RAM `0x8632` at EEPROM word 0. Thus, the record block at
`di = 0x86ee` is exactly word **94**. `machine.py` already maps each of
these lines to the 93C66 model. Thus, no new transport code was necessary.

## The failure mode when no part is fitted

Each record reads back zero, the majority vote fails, and the decoder returns
`0x00 xor 0x1d = 0x1d`. The boot decode at `0xc0940` uses the carry-set path.
That path skips only the first two bits, and then it reads `0x1d` as the feature
mask. `0x1d` has bits 2 and 3, and those two bits give the full reported
options list.

Thus, the `V32bis,Terbo,V.FC,V34+` before the seed was not an incorrect feature set. It was the
XOR constant. When `ATY14` prints `,,,,,`, this is the same fact on a different command:
six failed reads.

## What each setting controls

We measured one record at a time against a part with all other values at zero. We read the
`ATI7` profile that the firmware shows. To reproduce, use
`PYTHONPATH=. .venv/bin/python tools/probe_quad_settings.py`. The results are in
`artifacts/quad-settings-20260910/results.json`.

The baseline with all six at zero: `Product type US/Canada Rackmount`,
`Options V32bis`, no fax or cellular line.

### Setting 1 — country index → `[0x81c4]`

This is a plain index, not a bit field, into the country table at
`0xe6560`. Each entry has 118 bytes. Indices 0..22 are populated. Indices 23 and higher go past the end and show
garbage.

| | | | | | | |
|---|---|---|---|---|---|---|
| 0 US/Canada | 1 Japan | 2 Finland | 3 Sweden | 4 UK | 5 Norway | 6 Switzerland |
| 7 Netherlands | 8 South Africa | 9 Italy | 10 New Zealand | 11 Czech/Slovakia | 12 Belgium | 13 Denmark |
| 14 Australia | 15 France | 16 Germany | 17 International | 18 Austria | 19 Ireland | 20 Spain |
| 21 Portugal | 22 Malaysia | | | | | |

### Setting 2 — feature mask → `[0x8838]`, `[0x8839]`, raw in `[0x81d2]`

`0xc0940` distributes the bits: bit 0 → `0x8838 |= 0x04`, bit 1 → `0x08`,
bit 2 → `0x40`, bit 3 → `0x80`, bit 5 → `0x20`, bit 6 → `0x8839 |= 0x01`.
The code there does not test bits 4 and 7.

The options printer at `0xdf363` goes through one null-terminated string list
(`NONE HST V32bis Terbo V.FC V34+ x2,V90` at `0xdf45b`). Thus, each set mask bit
prints the *next* string, not a fixed string. That makes the list positional.
Thus, read it as measured pairs, and not as a table with one bit for each feature:

| setting 2 | `[0x8838]` | Options |
|---|---|---|
| `0x00` | `0x03` | `V32bis` |
| `0x01` | `0x07` | `HST,V32bis` |
| `0x04` | `0x43` | `V32bis,Terbo` |
| `0x08` | `0x83` | `V32bis,Terbo,V.FC` |
| `0x0b` | `0x8f` | `HST,V32bis,Terbo,V.FC` |
| `0x0f` | `0xcf` | `HST,V32bis,Terbo,V.FC,V34+` |
| `0x18` | `0x83` | `V32bis,Terbo,V.FC` |
| `0x1f` | `0xcf` | `HST,V32bis,Terbo,V.FC,V34+` |
| `0x20` | `0x23` | `V32bis,x2,V90` |
| `0x3f` | `0xef` | `HST,V32bis,Terbo,V.FC,V34+,x2,V90` |
| `0x7f`, `0xff` | `0xef` | unchanged from `0x3f` |

**Bit 5 is the x2/V90 bit**, and `x2,V90` is one combined list entry, not two.
This firmware cannot report x2 without V90, or V90 without x2. Bit 6 changes the
ISDN line to `V.110, V.120, SYNC, PPP, X.75, & PIAFS`. Bits 4 and 7 alone caused no
visible change. Bit 1 changes `[0x8838]`, but it does not change the printed text.

### Setting 3 — fax → `[0x862e]`

Only bit 0 has a visible effect. When it is set, `Fax Options Class 1/Class 2.0` shows.
When it is clear, the line is not shown. Bits 1..7 changed nothing.

The list at `0xdf47f` also has `Class 1` and `Class 2.0` as standalone
strings. But the three tests at `0xdf4c8`, `0xdf4d4` and `0xdf4e0` all test the
same bit 0, and no path gets to either string. They are dead, in the same way as the
`x2` string of the 211.

### Setting 4 — → `[0x862d]`, raw in `[0x81d3]`

| bit | effect |
|---|---|
| 0 | `Product type` gains an ` MSK` suffix |
| 5 | `Cellular Options MNP10 & MNP10EC` |
| 6 | `Cellular Options ETC` |
| 5+6 | `Cellular Options MNP10,MNP10EC & ETC` |
| 1,2,3,4,7 | no visible change |

`0xc09a6` forces `[0x862d] |= 0x04` immediately after the read. Thus, the record
never controls that bit.

### Settings 5 and 6 — no observable effect

The boot decode at `0xc0940` reads neither setting. A sweep of all eight bits of
each setting changed nothing in the `ATI7` profile. They are still stored, still
majority-checked and still printed by `ATY14`. The code that uses them
gets to them through the far wrapper, and not at boot.

## `ATY14`

`0xf0c7b` loops `cx` from 6 down to 1. It calls the getter with the index in `AL`
and prints each value, separated by commas. Thus, `ATY14` reports the settings in the sequence
**6,5,4,3,2,1**. The bare `,,,,,` is six failed reads, not
six empty values.

## A second writer: parameter `0x1f2`

`0xf88fc` sets the same derived bits from a byte that it reads with `lodsb`, not from
the EEPROM: bit 7 → `[0x8839] |= 1`, bits 6 and 5 → `[0x8838] |= 0x20`,
bit 1 → `[0x862d] |= 0x60`. When it clears those bits, it uses the cached raw settings `[0x81d2]` and
`[0x81d3]` as the baseline. It records in `[0x882e]` which bits it set last
(and not the EEPROM).

It is one handler in a **message-driven parameter interpreter** at
`0xf3b20..0xfffff` (one segment, base `0xf3b20`, with the first instruction
`mov byte [0x9bab], 0`). This is not the AT parser. During a full `ATI7` run,
none of `0xf3d24`, `0xf3e08`, `0xf3bb0`, `0xf784e`, `0xf88a3` or `0xf88db`
executes, not one time. AT commands go through the `0xc97a9` dispatcher.

| | |
|---|---|
| parse cursor | `[0x9c2c]`, shared by the whole interpreter |
| remaining length | `[0x9c72]` |
| selected handler | `[0x9c2e]`; `0x0bee` means unsupported |
| message buffers | `0x9bac` (filled at `0xf4975`, flagged `[0x9bab] = 1`), `0x8d45` |
| header | eight bytes — `0xf3bad` does `add bx,8` before seeding the cursor |
| id dispatch | 200-entry table at `cs:0x12e4` = `0xf4e04`, plus explicit ranges |

The identifier comes in `AX`, with `0x8000`/`0x4000` as flags. Most ids index
the table at `0xf4e04` (152 of its 200 entries are the unsupported stub). The
feature handler is **not** in that table. The code selects it explicitly:

```
f4889  cmp ax, 0x1f2
f488c  jne ...
f488e  mov ax, 0x4dbb          ; 0xf3b20 + 0x4dbb = 0xf88db
f4891  mov [0x9c2e], ax
```

Thus, **parameter id `0x1f2` sets or clears x2/V90, PIAFS and cellular**
at runtime. Its value field is 1..4 bytes. `0xf88e3` reads the length, then a
ladder of `lodsb` skips forward. Thus, only the **last** byte of the field
gets to the bit tests. A one-byte field and a four-byte field with the same
last byte have the same effect.

Thus, the EEPROM gives the base provisioning, and parameter `0x1f2` is the override on
it. This is why a card can ship with setting 2 bit 5 clear, and the field can
still enable it without a change to the part.

**The transport under it is not established.** The interpreter core is
jump-threaded. No near call and no far pointer goes to it. Thus,
we did not recover the connection between it and a wire. The eight-byte header that it skips does
agree with the backplane framing in [nmc-sdl-protocol.md](nmc-sdl-protocol.md)
(`attention`, eight-byte header, body, CRC). This points to the chassis NMC as
the sender, but that is a structural match and not a measurement.

## What is not established

- **What a real Quad with x2 provisioning has.** The `0x3f` above is synthetic. It
  shows only that bit 5 is the x2/V90 control. The 403 part
  ships setting 2 as `0x1f`, with bit 5 clear.
- **If the power-on self test of the Quad validates the part in the same way as the boot block of the 302.**
  The 403 part is accepted without errors, but we
  assume that `CHECKSUM_BYTE`/`CHECKSUM_SPAN` is also the layout of the Quad. We did not
  measure it.
- **The transport that delivers parameter `0x1f2`.** We recovered the handler and its
  identifier, but not what carries the message to the interpreter.
- **What uses settings 5 and 6.**
