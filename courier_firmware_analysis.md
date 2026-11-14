# Courier V.Everything Firmware Analysis — `SV25.XMD`

This is an analysis of the USRobotics Courier firmware image that we use for tests.
It supports the V.90 interop work. It applies especially to the blocker "Courier retrains
to Tone A right after our DIL, never sends CPt". Refer to the `courier-retrains-after-dil` memory.

## File facts

| | |
|---|---|
| File | `docs/SV25.XMD` |
| Size | 524,416 bytes = `0x80` header + `0x80000` (512 KB) image |
| Date | 1998-03-13 |
| MD5 | `872b9696eca7156ba22f1c874601b874` |
| Product | **USRobotics Courier V.Everything** (banner at file `0x263B7`) |
| Type | **SV = Supervisor** image, SDL/XMODEM-downloadable (`.XMD`) |

## Processors

The `ATUSR` easter egg of the modem confirms the supervisor CPU. We corrected the DSP part
number from the code, not from the string. Refer to the text below.

```
INT80188 Modem Functions      -> supervisor CPU = Intel 80188 (16-bit x86)
TMS32025 DSP Functions         -> datapump DSP  = TI TMS320C5x (16-bit fixed-point)
Copyright (c) 1988..1992 USRobotics
```

The `TMS32025` credit string is **not** the part number of the installed DSP. It is
a 1988–1992 copyright banner. The banner stayed in the firmware after the hardware changed.
The code in flash is **C5x**, not C25. We corrected this on 2026-09-05. Before that date,
this file accepted the string as correct. Evidence: the DSP init at flash `0x29080` is
`SPLK #ffff,@57`. `SPLK` does not exist on a C25. It is a C5x addition. This is not
the only example. A little-endian sweep of the full datapump decodes 1,824
`SPLK`, 913 `XC`, 884 `RETCD`, 761 `LAMM`, 639 `SAMM`, 406 `BSAR` and 307 `SACB`.
It also decodes the delayed-branch forms `BD`/`CALLD`/`CCD`/`BCNDD`. A C25 cannot
encode any of these instructions. This agrees with the independent conclusion in
[the DSP ROM probe notes](docs/dsp-rom-probe.md). Those notes found C5x from the same
init sequence. The evidence does not identify the exact C5x variant (C50/C51/C52).

Thus `SV25.XMD` (without the 0x80 header) is **exactly 0x80000 = 512 KB**. This is the size of
the full flash. The file contains BOTH the 80188 supervisor AND the TMS320C5x
datapump.

**But an `.XMD` payload is not a byte-aligned copy of flash**. Before 2026-09-05, this file
assumed that it was. Measurement: the code regions of
`IDSDL302.XMD` and `IDSDL302.ROM` have the same firmware name. But they are not equal (6.5%)
and they are not complements (3.8%). The `.XMD` code entropy is 7.84–7.85. The entropy of the
ROM is 7.13. A byte scan finds 303–353 printable strings in the first `0x29000` of the `.XMD`,
and 851 in the ROM. Thus a **transform that we did not identify yet** changes the `.XMD`
code payload. The x86/DSP boundary detector puts the boundary of `SV25.XMD` at `0x2a2c0`.
That location does not decode to the init sequence. The detector finds no boundary
in `IDSDL302.XMD`. Only the fill regions align, as a direct complement:
`0x44000–0x7C000` is 97.9% `ROM_byte == XMD_byte ^ 0xFF`. **Do not read `.XMD`
offsets as flash offsets** until we know the transform.

## Image map

The offsets below describe **flash as read from the device** (`IDSDL302.ROM` and the
board captures in `artifacts/`). They are not `.XMD` offsets. Refer to the caveat under
[Processors](#processors) for the reason that the two do not align.

| file range | ~size | contents |
|---|---|---|
| `0x00000–0x00080` | 128 B | header: signature/checksum + `NHCFG` tag + `0x4A` fill |
| `0x00000–0x29080` | ~164 KB | **Intel 80188 supervisor** (x86-16 byte code) + string/resource tables |
| `0x08000–0x0C000` | ~16 KB | word-structured pockets (DSP tables / small overlay) |
| `0x29080–0x43700` | ~106 KB | **TMS320C5x DSP datapump** (16-bit words: code + tables + overlays) |
| `0x44000–0x7C000` | ~224 KB | **`0xFF` fill** (unused, erased flash) |
| `0x7C000–0x7E000` | ~8 KB | DSP coefficient table (int32, ~-774 default taps) |

The boundary is sharp. The even/odd byte-distribution divergence is a discriminator
between word code and byte code. It is about 0.4 in the 80188 region, and it increases
sharply at the boundary. The boundary is at **`0x29080`**. Before 2026-09-05, this file
gave `0x29800`. That was an error of 0x780 bytes (960 words). We measured C5x opcode-byte
density in 64-byte steps. The boundary is at `0x29080` in `IDSDL302.ROM` and in the 7.3.14
board capture. It is at `0x29140` in the 7.4.16 capture, because the supervisor became 0xC0 bytes
larger and moved the datapump. Thus the boundary is **different for each image. Measure it again for each image. Do not assume it**.
The documented `LDP #0; SPLK #ffff,@57; SETC INTM` init sequence also starts at `0x29080`.
`0x29800` is in the middle of the stream, 960 words into the datapump.

The DSP words are **little-endian** (low byte first). We corrected this on
2026-09-05. Before that date, this file said big-endian. We retract below each conclusion
that used that reading. Decisive evidence: the DSP
initialization at flash `0x29080` reads, as little-endian C5x,
`bc00 / ae57 ffff / be41` = `LDP #0; SPLK #ffff,@57; SETC INTM`. This agrees with the
sequence in [the DSP ROM probe notes](docs/dsp-rom-probe.md). Big-endian
gives `lar ar0, @3c` and then garbage. The old supporting claim was that
big-endian `B`/`CALL` (`FF80`/`FE80`) targets looked like correct code addresses.
A count shows that this claim is false. In the full `0x29080–0x43700` region, the aligned
byte pair `ff 80` occurs **once** and `fe 80` occurs **never**. Thus it was never evidence
for either order. The **multiple overlays** conclusion is still correct, for independent
reasons. The datapump is much larger than the 64K word program space. Also, a
little-endian C5x disassembly of the DSP 3.1.2 tail at `0x41280` branches
internally around a base near `0xdf70`, not linearly from the `0x8000` kernel.

**The DIL-analysis and constellation-design code is DSP code in `0x29080–0x43700`. This
code decides to send CP or to stop and retrain.**

## Format — NOT encrypted, NOT compressed

The initial entropy (about 7.8) and the poor gzip ratio (about 83%) *looked* like compression.
For the flash image, this was incorrect. The flash image is **plaintext, uncompressed** code.
(Note: the 7.8 value is an `.XMD` measurement. Flash measures 7.13 in
the same x86 window. The disassembly below, on flash, proves the conclusion of this section,
and the conclusion is still correct. But it gives no information about `.XMD`. We now think that the
higher entropy of `.XMD` comes from a real transform. Refer to the text above.) The 80188
half is 16-bit x86. The high entropy comes from many 5-byte far-calls
(`9A seg:off`) between tables, not from a transform. Disassembly heuristics
(branch coherence) cannot tell x86 code from data. 16-bit x86 is so dense that
random bytes also score as "coherent". Thus, to find the type of each region, we used the even/odd
word-structure metric above, not disassembly.

Proof: the disassembly at the banner-print site (file `0x263AF`):

```
0263af: 9a 41 9e 00 80   lcall 0x8000:0x9e41     ; far call into bank at seg 0x8000
0263b4: e8 6f 17         call  0x27b26           ; "print inline ASCIIZ" routine
0263b7: "USRobotics Courier V.Everything",0       ; inline string (call-then-db idiom)
0263de: a0 29 01         mov al,[0x129]          ; prints a 3-byte version as
0263e1: 9a d6 9d 00 80   lcall 0x8000:0x9dd6     ;   [0x129]:[0x128]:[0x127]
0263e8: 9a 13 16 00 80   lcall 0x8000:0x1613     ; print-char routine
```

### Layout
- `0x00000–0x00080` — 8-byte signature/checksum (`b7 f0 b2 fd d8 ec bc bd`) + `NHCFG` tag + `0x4A` fill
- `0x00080–0x44000` — active code + data + DSP tables (bank-switched x86)
- `0x44000–0x7C000` — **`0xFF` fill** (unused, erased flash)
- `0x7C000–0x7E000` — DSP coefficient table (see below)
- tail — mostly `0xFF`

Before 2026-09-05, this file gave the fill byte as `0x00`. That value came
from the `.XMD` files, and it is correct for them. **Flash as read from the device is
`0xFF`**: 100.0% of `0x44000–0x7C000` in the 7.3.14 board capture, and 97.9% in
`IDSDL302.ROM`. The difference is important. `0xFF` is erased flash that was never
programmed. `0x00` would be zeros that the firmware wrote intentionally.

### Quirks
- **Bank switching**: a 512 KB ROM cannot fit in one 64 KB segment. Near calls (`E8`)
  stay in the bank and disassemble linearly. Far calls (`9A 8000:xxxx`) page into
  another bank. We did **not solve the bank→file mapping yet**. The simple `seg*16` and
  `+0x80` header offsets both fail. Thus more work is necessary to resolve cross-bank calls.
- **String obfuscation**: the firmware stores some UI strings **case-toggled** (XOR `0x20`
  on letters only). For example, the credits at `0x100` read `jOHN wIERSEMA`. The firmware stores other strings (the
  banner, diagnostics) in normal case. To read them correctly, for each run of text, select
  the form ({identity, case-toggled}) that has more lowercase letters.

## Extracted content (confirmed)

### V.90 downstream rate table (file `0x019B02`) — the far-end DS0 rate grid
```
32 → 48000 bps   36 → 53333 bps
33 → 49333 bps   37 → 54666 bps
34 → 50666 bps   38 → 56000 bps
35 → 52000 bps   39 → 57333 bps
```
This is the 1333 bps grid. It gives the exact rate codes that the Courier maps for V.90 downstream.

### V.34 trellis code set (file `0x018D84`)
`8S-2D`, `16S-4D`, `32S-2D`, `64S-4D` trellis codes.

### x2 connect-result vocabulary (file `0x00AB80..0x00ADB0`)
The firmware has explicit USR x2 connect-rate strings. They are divided across XOR-encoded
sub-blocks:

```
x2
41333/ARQ/x2
42666, 42666/ARQ, 42666/x2, 42666/ARQ/x2
44000, 44000/ARQ, 44000/x2, 44000/ARQ/x2
45333, 45333/ARQ, 45333/x2, 45333/ARQ/x2
46666, 46666/ARQ, 46666/x2, 46666/ARQ/x2
48000, 48000/ARQ, 48000/x2, 48000/ARQ/x2
49333, 49333/ARQ, 49333/x2
54666, 54666/ARQ, 54666/x2, 54666/ARQ/x2
56000, 56000/ARQ, 56000/x2, 56000/ARQ/x2
57333, 57333/ARQ, 57333/x2, 57333/ARQ/x2
64000, 64000/ARQ, 64000/x2, 64000/ARQ/x2
```

This confirms that the supervisor can report x2 as a different modulation/rate
label. Later disassembly corrected the initial conclusion from the string scan. The
capture has separate `x2 Status` and `V.90 Status` formatter headers at flash
`0x1bff0` and `0x1c0a0`. The diagnostic enum near them contains
outcomes that are specific to x2 (remote not x2/server, multiple codecs, incompatible
versions, and 3200-baud restrictions). Possibly x2 and V.90 share the normal link diagnostics.
But x2 is more than a result-code label.

### x2 / V.90 feature-gate and NVRAM evidence

There is static evidence for an installed-feature gate. Thus the datapump support is not only unconditional:

- XOR key `0x32` at file `0x1879D` decodes an S-register help entry:
  `S30` bit `1` = **`Enable feature upgrades`**.
- XOR key `0x32` at file `0x18EA6..0x18ED7` decodes the modulation-control
  help entries:
  - `S57` includes `V34+`, `V34`, and `VFC` bit labels.
  - `S58` bit `1` = **`x2`**.
  - `S58` bit `2` = **`BLER monitor`**.
- XOR key `0x64` at file `0x1C4A0` decodes:
  `Channel will not support 3200 baud.`
  `Channel is x2-capable but feature not installed.`
- XOR key `0x26` at file `0x07939..0x07953` decodes self-test vocabulary:
  `ram`, `nvram`, `dsp`, `testing`, `leds and speaker`, `ok`, `no communicate`.
- XOR key `0x26` at file `0x1C84D` decodes `NVRAM Sett.s`. This confirms that the
  diagnostic text has an NVRAM settings/report surface that the user can see.

### Recovered `ATY14` source and feature decode

The `ATY14` handler is at `0x85250`. It prints `[0x0a0c]` down to `[0x0a07]`,
one byte for each field, with commas between them. When `[0x0a06]` reads `0xff`, it prints the
`,,,,,` literal at `0x8525a` instead.

The parameter-block unpack at `0x7e007` writes those seven bytes. It
copies bytes 0..6 of the accepted configuration record to `0x0a06..0x0a0c`. Thus
the printed fields are record bytes 6, 5, 4, 3, 2, 1. This agrees with the field names
from the archived post:

| `ATY14` field | name | RAM | record byte |
|---:|---|---|---:|
| 1 | unused1 | `0x0a0c` | 6 |
| 2 | unused2 | `0x0a0b` | 5 |
| 3 | type1 | `0x0a0a` | 4 |
| 4 | type2 | `0x0a09` | 3 |
| 5 | **features** | `0x0a08` | 2 |
| 6 | country | `0x0a07` | 1 |

This corrects the guess above. On this firmware, the configuration register dump
comes from the **memory-mapped parameter sector that the firmware searches at `0xf8000`**. It does not come from
the Microwire serial EEPROM that the firmware bit-bangs on port `0x10`. The unpack also copies
`[0x0a07]` to `[0x0173]` (country), `[0x0a09]` to `[0x0a04]`, and `[0x0a0a]` to
`[0x0a03]`. A bit in the `[0x0a06]` flags byte gates each of these copies.

The code at `0x7e024` decodes field 5 through a table of five entries at `0x7e072`:

| features bit | value | label | sets `[0x19d7]` |
|---:|---:|---|---|
| 0 | 1 | HST | `0x04` |
| 1 | 2 | Fax | `0x0a` |
| 2 | 4 | Terbo | `0x4a` |
| 3 | 8 | V.FC / V.34 | `0xca` |
| 4 | 16 | **V.90 on this firmware** | `0x6a` |

The table has exactly five entries. Thus this firmware recognises exactly five
feature bits. Bit 4 is real and the firmware decodes it. It is the only entry that
sets `[0x19d7]` bit `0x20`.

**Bit 4 is not x2 here.** The archived post about `ATY14` is about an older
Courier. Its label is not correct for this 2002 build (the banner reads
`Copyright (c) 1988 - 2002 by USRobotics`). There are two items of evidence:

- `0x77d47` tests `[0x19d7]` bit `0x20`. The result decides if the firmware adds `,V90` to the
  `ATI7` options list. A sector with bit 4 set gives
  `HST,V32bis,Terbo,VFC,V34+,V90,V92`. A sector with bit 4 clear gives
  `HST,V32bis,Terbo,VFC,V34+,V92`. The firmware always sends `,V92`.
- The options table at `733c:49c4` contains an `x2` entry at `733c:49d6`.
  But `mov si, 0x49d6` does not occur in the image. No code can
  select the entry. Thus this firmware cannot report x2. The x2 connect-rate
  vocabulary in the list above is unused data that stayed from older builds.

`0x82e7d` tests the same `[0x19d7]` bit `0x20` to select the product code
that `ATI`/`ATI0` reports. Thus that code follows V.90, not x2:

| `[0x19d7]` bit `0x20` | EEPROM fitted | `ATI` |
|---|---|---|
| set | yes | `5608` |
| set | no | `5608A` |
| clear | yes | `3368` |
| clear | no | `3368A` |

We confirmed this in the emulator with a synthesised parameter sector. Features `031`
gives `ATI` = `5608` and an options list that includes `V90`. Features `015`
gives `3368` and an options list without `V90`.

### Parameter sector layout beyond the first seven bytes

The firmware copies the full accepted record to `0x0a06`, one byte to one byte. Thus record byte *i*
goes to `0x0a06 + i`. The firmware unpacks only bytes 0..6 into the named fields above.
The remaining bytes are a packed configuration image.

The code at `0x64044` expands bytes `0x1d..0x2f` (RAM `0x0a23..0x0a35`) into the
profile bytes `0x0932..0x0955`. The unpacker reads a `(shift, mask)` control
table at `0x63f8d` in sequence. For each field, it stores `(source >> shift) & mask`. When `shift` is zero, it moves to
the next source byte. That gives 36 fields from 19 source
bytes. Important entries:

```text
src+5 >> 4 & 0x0f -> [0x0940]
src+5 >> 0 & 0x0f -> [0x0941]
```

`[0x0941]` is a **test-mode selector**. `0x5bc57` and `0x5bc8d` compare it
with 6. For each value `>= 6`, the code does `ljmp 0x7a59:0000` into a diagnostic
dispatcher. The dispatcher selects a handler by `([0x0941] - 6) * 2`. Then it does
`call [0x1fbc]` in an endless loop. It never goes back to the normal boot path.

This explains an error that is easy to make when you synthesise a parameter sector. If you fill the
record with `0xff`, `[0x0941]` unpacks to 15. Then the firmware enters test
mode 9 and seems to stop in the rate module at `0x7abaa`. The two spin loops
there wait on `[0x1fe7]` and `[0x1fe8]`. `[0x1fe7]` is an inverted copy of port `0x14` bit `0x01`.
Events 3 and 9 at `0x7a64e` set `[0x1fe8]`. The two loops have complementary exit
conditions. Thus no static input releases both. The firmware operates correctly.
The record is incorrect. If the packed config of a sector decodes to correct values, the firmware boots
directly to the main loop.

Interpretation: a persistent settings/feature path controls x2. `S58`
is possibly the runtime modulation mask. `S30` is possibly the bit that
permits feature-upgrade handling. The message "x2-capable but feature not
installed" is the strongest sign of this behavior: the firmware can recognize some Courier hardware/line state as capable,
but an installed-feature flag stops x2. At boot, the firmware loads this flag from the
parameter sector into the settings block of the supervisor, as the trace above shows. We did **not find** a literal unlock-key
string or key-entry prompt in the firmware image yet.

Live-command evidence: `ATY14` returns a compact configuration-register
dump of six fields:

```text
unused1,unused2,type1,type2,features,country
```

This agrees with the static evidence above better than the theory that `ATY14` is a last-call
counter report. On a 03/13/98 US/Canada external unit with the `ATI7` options
`HST,V32bis,Terbo,VFC,V34+,x2,V90`, `ATY14` reports:

```text
000,000,030,007,031,000
```

Fields 3 and 4 (`030,007`) are the product type. They agree with the `ATI7` product
profile. Field 5 is the `ATC8` protocol-availability byte. On this unit it is
`031` decimal (`0x1F`). Thus HST, fax, Terbo, V.FC/V.34, and x2 are enabled.
On this firmware, `ATI7` reports V.90. But in this older mapping, V.90 is not a separate documented
`ATC8` bit. Confirmed `ATC8` feature bits:

| bit | value | meaning |
|---:|---:|---|
| 0 | 1 | HST |
| 1 | 2 | Fax |
| 2 | 4 | Terbo |
| 3 | 8 | V.FC / V.34 |
| 4 | 16 | x2 |

Field 6 is the country code. On this unit it is `000`, which agrees with US/Canada.

Scott found archived field-upgrade notes. They give this sequence for older Courier
firmware:

```text
ATY14        ; note the country/config string
ATGN         ; enable config changes
ATC10=0      ; US/Canada country code
ATC8=31      ; enable x2
ATNX         ; save changes
```

A later disassembly of the 403 capture identifies `ATNX` as a supervisor restart.
It is not a demonstrated NVRAM-save operation. The same investigation identifies
numeric `ATN` as a manual rate-change event that depends on the state. It is not
a random DSP procedure call. Refer to [the command analysis](docs/undocumented-atn-commands.md).

This sequence agrees closely with the observed `ATY14` string. But we did not confirm the write
commands on the 03/13/98 image:

- `ATC10=0` agrees with field 6 (`000`) and with the decoded country table. The first
  entry of that table is `US/Canada` at about flash `0x20480..0x20520`.
- `ATC8=31` agrees with field 5 (`031`). The same post says that `ATC8=15` disables x2.
  This confirms that bit `0x10` is the x2 bit in that config word. This bit numbering can be
  different from the runtime
  `S58` modulation mask, where the help text labels bit `1` as `x2`.
- Literal scans found no clean `ATGN`, `ATNX`, `ATC8`, or `ATC10` strings. That
  agrees with the tokenized command parser. But it also means that these
  write/config verbs are possibly not in this firmware, or that a different gate controls them.

> **CAUTION: DO NOT SEND `ATGN`, `ATC8=...`, `ATC10=...` OR `ATNX` TO A KNOWN-GOOD INTEROP UNIT.**
> Treat these commands as NVRAM/country write commands. Use them only on a modem that you can lose,
> or when you have a full NVRAM/flash recovery plan.

Read-only captures of `ATY14`,
`ATI7`, `ATS30?`, `ATS57?`, and `ATS58?` are safe. They are sufficient to compare the
installed-feature state of different units.

Capture `ATY14` with `ATS30?`, `ATS57?`, and `ATS58?` on each unit:

```text
ATS30?   ; feature-upgrade enable bit lives here in help text
ATS57?   ; V34+/V34/VFC modulation mask
ATS58?   ; bit 1 = x2, bit 2 = BLER monitor in help text
ATY14    ; compare field 5 with the feature/modulation state
```

Possibly the 5th `ATY14` field is different on different units or NVRAM profiles with the same firmware
image. In that case, it is the confirmed protocol-availability byte that gates
HST/fax/Terbo/V.FC/V.34/x2 availability. The diagnostic bundle now records these
S-registers before `ATY14`.

Search for the formatter/handler:
- The image does not store `ATY14` as a literal command string (`Y14`, `y14`, and `ATY14`
  do not occur in the image). This agrees with the tokenized `AT` parser model.
- Live probes show the accepted Y commands
  (`0..6,8,9,11,12,14,15,16,17`). This set does not occur as a simple bitmap
  (`0x03DB7F`) or byte sequence in raw flash.
- We searched for a static comma-separated formatter (`mov al,','` and then
  the known resident far call for character output). The search found no candidate in
  the visible supervisor body. The only two direct calls to resident output helpers
  that we found are in the banner/version formatter.
- Current interpretation: the `ATY14` producer is in the code. But probably
  the resident/banked command dispatcher or an encoded diagnostic
  table interpreter selects it. To find the exact routine, put the next dynamic watchpoints on
  the resident character-output helper and on the bytes/words whose decimal values
  become `000,000,030,007,031,000`.

### Link-diagnostic vocabulary — the ATI6/ATI11-style readouts (file `~0x01CC00`)
```
V.90 Status                 (file 0x01C38D)
Far Echo Loss ... dB
Roundtrip Delay ... msec
Timing Offset ... ppm
Carrier Offset ... ppm
RX Upshifts / RX Downshifts
Constant Carrier / Carrier Usage
```
**This is the find that is most useful now**. Refer to "How this helps the blocker".

### DSP coefficient table (file `0x7C080`)
Little-endian int32. Most values are `-774`, and then `-781, -1087, -915, -901, ...` follow.
These are fixed-point constants that the firmware loads into the datapump DSP (default/init taps).

### Other
- Country/config list: US/Canada, Japan, Finland, Sweden, UK, Norway,
  Switzerland, Netherlands, South Africa, Italy, New Zealand, Czechoslovakia,
  Belgium, Denmark, Australia, France, Germany, International, Austria, Ireland.
- "Lowest Speed Limit", "SDL Xmodem file transfer — (Y)es (N)o (T)est", reset/dial UI
- Developer credits (`0x100`): John Wiersema, Glenn Bushey, Kevin Lacey,
  Brinn Gilbert, Doug Blatt, Art Johnson, Pete Jankus, Bill Pierce, Ken Starkey, Joe F…
- The firmware prints the version at runtime from RAM `[0x127..0x129]` as an X:Y:Z triplet.
  (It is not a literal string in the image. The init code sets it.)

## Architecture summary

- **Supervisor**: Intel 80188 (16-bit x86). Uncompressed and plaintext. You can disassemble it
  as x86-16. It controls AT/S-registers, protocol sequencing, status/diagnostic
  displays, and DSP overlay loading. It occupies `0x0–0x29080` (`0x29140` in 7.4.16).
- **DSP datapump**: TI TMS320C5x, **little-endian** 16-bit words, at `0x29080–0x43700`
  (about 106 KB), and tables at `0x08000–0x0C000` and `0x7C000`. We confirmed that it is executable
  (the init block decodes cleanly and 95% of its branch targets are in
  `0x8000–0x8400`). It has multiple overlays. **The DIL /
  constellation / retrain logic is here.** capstone has no C5x support. Use
  [`tools/c5x_disasm.py`](tools/c5x_disasm.py) (in this repo, derived from MAME), or the
  TMS320C5x processor module of IDA.

### DSP-supervisor mailbox/status handoff

The strongest concrete handoff that we found is a supervisor x86 reader block at
file `0x13D00` (payload/flash `0x13C80`). It reads 16-bit words from the DSP.
The high byte comes on I/O port `0x5E` and the low byte comes on I/O port `0x5C`. Then the block stores
the words in a small RAM status cluster:

```asm
13d00: in   al,0x5e   ; high byte
13d02: mov  ah,al
13d04: in   al,0x5c   ; low byte
13d06: mov  [0x0b2f],ax
13d09: ret

13d0a: in   al,0x5e
13d0c: mov  ah,al
13d0e: in   al,0x5c
13d10: mov  [0x0304],ax
13d13: test byte [0x033f],0x04
13d18: je   0x13d2d
13d1a: mov  ax,[0x0304]
13d1d: shr  ax,0x0a
13d20: and  ax,0x0007
13d23: mov  bx,ax
13d25: mov  ax,0x0006
13d28: sub  ax,bx
13d2a: mov  [0x0b26],al
13d2d: mov  byte [0x0b28],0x01
13d32: ret

13d33: ... -> [0x0306], sets [0x0b28]=1
13d42: ... -> [0x0308], sets [0x0b27]=1, [0x0b28]=0
13d56: ... -> [0x030a], sets [0x0b27]=1, [0x0b28]=0
13d6a: ... -> [0x030c], sets [0x0b27]=1, [0x0b28]=0
```

We confirmed that `[0x0B2F]` is the raw V.90 status word that `ATI11` uses. The formatter
at file `0x1C3B0` takes `([0x0B2F] >> 8) & 7`. When `[0x089D] & 0x20` is clear, it changes value `1` to value
`8`. Then it uses the result as an index into the V.90-status string pointer
table at logical `CS:0x517E` (physical file `0x1C3DE`).

The DSP word at `[0x0304]` is probably the rate/shift bucket. The reason is that the
supervisor calculates `[0x0B26] = 6 - (([0x0304] >> 10) & 7)` when `[0x033F] & 4` is
set. A direct xref search of raw flash found only this write/derivation path. We found no
simple `mov al,[0x0B26]` and no direct read of `[0x0304]` by a formatter.
Thus `[0x0304]/[0x0B26]` is a strong candidate for the speed/rate-status handoff of the DSP.
But the final consumer probably goes through the encoded diagnostic
table interpreter or a banked overlay, not a simple inline formatter.

## How this helps the "retrain after DIL" blocker

The decision to retrain or to send CP has two parts:
- **Protocol sequencing / status** → supervisor (you can disassemble it and get access to it).
- **DIL analysis + constellation design** (probably the part that *rejects* our DIL)
  → DSP datapump (access to it is more difficult).

**Immediate result, with no more RE:** the diagnostic vocabulary above shows that the
Courier reports its *own* measurement of our downstream signal. During a live
attempt, `ATI6` / `ATI11` (and the "V.90 Status" display) show **Timing Offset
(ppm)**, **Carrier Offset (ppm)**, **Roundtrip Delay**, **Far Echo Loss**, and
**Up/Downshift** counts until the moment that the Courier stops. This lets us tell the difference between:
- a **timing/carrier-offset** problem → this points to our clock recovery / DPLL
  (`clock_recovery.c`) and RTP sample-rate accuracy, and
- a real **constellation/impairment** rejection of our DIL.

### Confirmed useful AT diagnostics on our 03/13/98 Courier units

Probe run on 2026-07-26, on `/dev/cu.usbserial-21210`:

| Command | Result on 03/13/98 US/Canada Courier | Interop value |
|---|---|---|
| `ATI6` | supported | Last-call counters, retrain/BLER/link timeout counts, disconnect reason. |
| `ATI7` | supported | Firmware identity: 03/13/98 supervisor `7.3.14`, DSP `3.0.13`, 20.16/25 MHz split. |
| `ATI11` | supported | Extended physical diagnostics: modulation, carrier/symbol rate, levels, SNR, echo loss, round-trip delay, timing/carrier offset, V.90 status. |
| `ATY8` | supported, hidden from `AT$` | Verbose `00:`..`FF:` diagnostic table. Empty when idle. Probably a byte-indexed datapump/stat table. Capture it after a failed V.90 training. |
| `ATY11` | supported | Frequency/level curve from the last call. Empty until a call fills the channel-probe state. |
| `ATY12` | supported | `Recv`/`Xmit` table with 16 rows. This document does not give its meaning. Capture it to compare with speed-shift and V.90 status changes. |
| `ATY14` | supported | Config-register dump with six fields: `unused1,unused2,type1,type2,features,country`. Field 5 is the `ATC8` protocol-availability byte (`031` on a unit with x2 enabled). Field 6 is the country (`000` = US/Canada). |
| `ATY15` | supported, hidden from `AT$` | Current physical DIP-switch state. Not for each call, but useful as provenance when you compare units. |
| `ATY17` | supported, hidden from `AT$` | Verbose 16-bit diagnostic matrix. Empty when idle. Probably datapump/state memory. Capture it after a failed V.90 training. |
| `ATY4DT<number>` | supported | Diagnostic dial form. If you put `Y4` before `DT<number>`, the modem sends call-progress dumps during dialing/training. Use `tools/cx_at.py usry4dial <number>`. |
| `ATY0`..`ATY6`, `ATY9`, `ATY16` | `OK` with no report body | The Y dispatcher accepts them, but most are not useful when idle. `ATY4` is useful when you add it to a dial command as `ATY4DT<number>`. |
| `ATY7`, `ATY10`, `ATY13`, `ATY18`..`ATY20` | `ERROR` | This firmware does not implement them. |
| `ATI16`, `ATI17` | `ERROR` | Newer Courier 56K Business documents use these as aliases for support connection reports. This 1998 V.Everything firmware does not implement them. |
| `AT+MS=?`, `AT+MS?`, `AT+GMM`, `AT+GMR`, `AT&V`, `ATI8`, `ATI9`, `ATI12`..`ATI14`, `ATI18`..`ATI20` | `ERROR` | Do not use generic later-Hayes diagnostics for these units. |
| `ATUSR` | `ERROR` on `/dev/cu.usbserial-21210` | The credits/proc strings are in the image. But in command mode, this unit did not accept the easter-egg command that other people reported. |

Run the post-call bundle before you send `ATZ` or power-cycle the analogue modem:

```bash
./.venv/bin/python tools/cx_at.py --dev /dev/cu.usbserial-21210 usrdiag
```

For a single deeper capture, also run this command. This is especially important immediately after the Courier retrains
and does not send CPt:

```bash
./.venv/bin/python tools/cx_at.py --dev /dev/cu.usbserial-21210 usrdeepdiag
```

To capture the call-progress diagnostic dump of the Courier during the dial/training,
use the `ATY4DT<number>` form:

```bash
./.venv/bin/python tools/cx_at.py --dev /dev/cu.usbserial-21210 usry4dial 6001 --wait 120
```

For a failed V.90 attempt, keep this minimum evidence:

- `ATI6` disconnect reason, and `Retrains Requested/Granted`, `Blers`, and
  `Link Timeouts`.
- `ATI11` `Timing Offset`, `Carrier Offset`, `Roundtrip Delay`,
  `Recv/Xmit Level`, `SNR`, `Near/Far Echo Loss`, and raw `V.90 Status`.
- `ATY11` frequency-level slope/notches.
- `ATY12` raw table and `ATY14` config string. Compare `ATY14` field 5 on different
  units, because it is the confirmed `ATC8` protocol-availability byte.
- `ATY8`/`ATY17` raw tables when you do a deep capture. If they change from zero
  only after a failed call, a diff of the idle output and the post-call output can possibly identify the
  path for the datapump reject reason.

External cross-checks:
- The official USRobotics Courier command reference documents `ATI11` as the
  extended link screen, and the newer `ATI16`/`ATI17` as connection reports. But our
  firmware is older than those aliases.
- Archived USR support discussions use `ATY11` after failed V.90 calls as the
  frequency-curve display. This agrees with the output of the command on our unit.

Firmware/string-scan evidence:
- Most of the help/S-register vocabulary is near flash `0x18000..0x1A200`.
  This includes the V.34/V.90 control bits in `S54`..`S58`.
- The `ATY14` country-code table is near flash `0x20480..0x20D00`.
  The order, from Courier command references and static confirmation, is:
  `0=US/Canada`, `1=Japan`, `2=Finland`, `3=Sweden`, `4=UK`, `5=Norway`,
  `6=Switzerland`, `7=Netherlands`, `8=South Africa`, `9=Italy`,
  `10=New Zealand`, `11=Czechoslovakia`, `12=Belgium`, `13=Denmark`,
  `14=Australia`, `15=France`, `16=Germany`, `17=International`, `18=Austria`,
  `19=Ireland`.
- The extended V.90 status strings are at flash `0x1C30D` and `0x1CB88..0x1CBDF`
  (`V.90 Status`, `Far Echo Loss`, `Roundtrip Delay`, `Timing Offset`,
  `Carrier Offset`, `RX Upshifts`).
- The V.90 downstream rate grid is at flash `0x19A82`.
- The firmware-loader prompt `SDL Xmodem file transfer - (Y)es (N)o (T)est` is
  at flash `0x27CBB`. This confirms a hidden firmware-update path that
  `AT~X!` starts. That command is dangerous. Do not send it during diagnostics.
- The visible `AT$` help does not list a plain `Y` command family. But live
  probes show a numeric `ATY<n>` dispatcher. `ATY8`, `ATY15`, and `ATY17`
  are the new useful hidden surfaces from this pass.

## Container format (SDL/XMODEM download)

`524416 = 4097 × 128`. This is exactly 4097 XMODEM blocks. Block 0 (`0x00–0x80`) is the
SDL download header (checksum bytes + `NHCFG` tag + `0x4A` fill). The remaining
4096 blocks are the 512 KB flash image. **flash offset = file offset − 0x80.**
Send this file only after you start the Courier SDL loader with `AT~X!`.

## SDL/XMODEM firmware loader reversal

**Command entry:** public update instructions and firmware strings identify the
loader command as **`AT~X!`**. Do not use plain `ATXMODEM`. That was a short form in earlier
versions of these notes. The Courier update path does not accept it.
After confirmation, the command causes permanent changes.

**Other `AT~` commands:** we found none. A full payload scan finds exactly
one clean, NUL-terminated tilde command token, `~X!`, at flash `0x7C14D`
(file offset `0x7C1CD`). Other raw `0x7E` occurrences look a little like commands,
for example `~N`, `~0H`, and `^~!U`. But they are in dense code/table
regions, and they do not have the loader-command structure around them. There are no literal
`AT~` strings. This is normal, because the parser stores only the
command token after `AT`.

**AT parser / ERROR path anchors:**

- The normal command processor does not store commands as literal `AT...`
  strings. It seems to tokenize the input after `AT` and dispatch by command family.
- A probable `AT` entry recognizer is at flash `0x29380`:
  - `cmp al,0x41` checks for `A`. On a match, it writes `0x1864` to runtime word
    `[0x50]`. This probably selects the next parser state.
  - The next state at flash `0x293B8` reads the current input byte from
    `SS:[0xFF76]` / `SS:[0xFF78]` and changes it to uppercase with `and al,0x5F`. Then
    `cmp al,0x54` checks for `T`.
  - On `T`, it writes runtime words `[0x50]=0x1967` and `[0x54]=0x0385`.
    This agrees with an entry into the command parser after `AT`. On a character that is not `T`, it writes
    `[0x50]=0x190B`. This agrees with a rejection of the `A...` prefix, or a return to
    the handling of non-command input.
  - Both paths end with a write of `0x8000` to `SS:[0xFF02]` and `iret`. Thus this
    is probably an interrupt/state-machine input path, not a linear
    subroutine.
- The result-code text table at flash `0x0A490` is XOR-encoded with key `0xB0`:
  `OK`, `CONNECT`, `RING`, `NO CARRIER`, `ERROR`, `1200`,
  `NO DIAL TONE`, `BUSY`, `NO ANSWER`, and other items. `ERROR` starts at flash `0x0A4AB`.
  This is probably the final output table. The firmware uses it when a command handler rejects a
  token or has no match.
- The `AT$` help/category vocabulary has a separate encoding. One decoded anchor
  is flash `0x1773E` with XOR key `0x3D`. It includes:
  `Result Codes`, `Speaker`, `Responses`, `Register`, `Command`, `Time`,
  `Dial`, `Wait`, `Tone`, and `Test`. This is probably help text, not the parser
  table.
- A raw-code search for `cmp al,0x7E` found one routine that looks real, at flash
  `0x16345`. But that path uses `0x7E` as a protocol flag byte and returns
  carry/clear. It is probably V.42/HDLC flag handling, not an `AT~` dispatcher.
- The parser state writes are real. But in the raw flash image, the consumer is not a simple
  indirect call. Searches for `call/jmp [0x50]`,
  `call/jmp far [0x50]`, and the same forms for `[0x44]`/`[0x54]` found no
  hits. There are more direct state-slot writes in supervisor code near this location:
  `[0x50]=0x1892` / `[0x54]=0x19CE`, `[0x50]=0x0F23` / `[0x54]=0x0F1C`, and
  `[0x50]=0x08A7` / `[0x52]=0x9EB0`. This pattern shows that `[0x50]`/`[0x54]`
  are probably scheduler/parser-state slots, not one static command
  jump table. The dispatcher is probably in resident RAM or in a banked overlay.
- The recovery loader has its own internal address model. Its bootstrap starts
  at flash `0x7DBC0` and refers to internal offsets such as `0x1B14` and
  `0x1BA4`. When you reverse that copy, use `internal offset = flash - 0x7C000`.

**State machine that the user can see, reconstructed from strings:**

1. `AT~X!` starts the loader. The loader prints:
   `SDL Xmodem file transfer - (Y)es (N)o (T)est >`
2. `N` cancels.
3. `T` starts a verification path that does not flash, and prints:
   `* Test mode - Flash ROM will not be modified *`
4. After `Y` or `T`, the loader prints:
   `Begin Xmodem file transfer now.`
5. The modem receives an XMODEM stream of 128-byte blocks.
6. When the transfer is complete, it prints:
   `SDL Xmodem file transfer completed.`
7. It prints `Resetting modem...`, and then `Calculating CRC...`.
8. If the image validation passes, it prints `OK` and resets. If the validation fails, it
   prints `failed.` or, in the recovery path, `Flash ROM failure.`

**There are two copies of the loader strings/code:**

| flash offset | evidence | role inference |
|---|---|---|
| `0x27CBB` | plain `SDL Xmodem file transfer`. The status strings near it are partly plain and partly XOR-encoded: key `0x69` for transfer/test/CRC text and key `0x72` for corrupted-firmware text | Normal supervisor command-mode loader. |
| `0x7C14D` | literal `~X!` token, and then another `SDL Xmodem file transfer` copy at `0x7C1DB`. Status strings XOR-encoded with keys `0x29` and `0x65` | Recovery/resident loader copy. Probably the firmware uses it when the main firmware checksum fails. |

Decoded normal-loader status strings:

| flash offset | XOR key | decoded text |
|---|---:|---|
| `0x27CFB` / `0x27D02` | plain prefix, then `0x69` | `Resetting modem...` |
| `0x27D11` | `0x69` | `Calculating CRC...` / `OK` / `failed.` |
| `0x27D35` | `0x69` | `* Test mode - Flash ROM will not be modified *` |
| `0x27D66` | `0x69` | `Begin Xmodem file transfer...` |
| `0x27D8E` | `0x72` | `MODEM FIRMWARE IS CORRUPTED. FIRMWARE DOWNLOAD IS NECESSARY.` |
| `0x27DD0` | `0x72` | `Flash ROM failure.` |

Decoded recovery-loader status strings:

| flash offset | XOR key | decoded text |
|---|---:|---|
| `0x7C20C` | `0x29` | `completed.` |
| `0x7C219` | `0x29` | `Resetting modem...` |
| `0x7C231` | `0x29` | `Calculating CRC...` / `OK` / `failed.` |
| `0x7C255` | `0x29` | `* Test mode - Flash ROM will not be modified *` |
| `0x7C286` | `0x65` | `Begin Xmodem file transfer now.` |
| `0x7C2AE` | `0x65` | `MODEM FIRMWARE IS CORRUPTED. FIRMWARE DOWNLOAD IS NECESSARY.` |

**File/container facts from `SV25.XMD`:**

- The file length is exactly `0x80080` bytes: one 128-byte SDL header and one
  512 KiB flash image.
- The file does not contain XMODEM framing. A terminal puts each 128-byte file
  chunk into standard XMODEM framing.
- The first block starts with the bytes
  `b7 f0 b2 fd d8 ec bc bd 4b 1f 37 13 ca 4a 4a 4a`, then `NHJ`, `NHCFG\r`,
  and then `0x4A` fill to the end of the 128-byte block.
- The 512 KiB payload starts immediately at file offset `0x80`.
- The header field that changes is the 16-bit value at header offset `0x0A`. We compared
  ten `.XMD` images (`ID20_401/402/403`, `ID25_401/402/403`, `SDL0430`,
  `SDL0430N`, `SV25`, `SV_49`). In all of them, bytes `0x00..0x04`, `0x06..0x09` and `0x0C` are
  identical. Only `0x05` (two observed values, `0xec`/`0xed`) and `0x0A..0x0B`
  change. One sample cannot show the difference between a constant and a checksum. This is
  the reason that earlier passes tested "the first header words" as a block.
- The `0x0A` field is a real checksum that depends on the payload. It is not a build serial.
  `SDL0430.XMD` and `SDL0430N.XMD` are different in only 237 of 524,288 payload bytes
  (0.05%). But they have the unrelated values `0x76ea` and `0x8f31`. That avalanche
  also excludes all additive constructions.
- These tests show what the `0x0A` field is **not**. The tests do not depend on init or xorout
  (they use the GF(2)-affine property of CRCs and the linearity of sums). Thus they
  exclude full families, not only single configurations:
  - additive byte and word sums, in each endianness, over each prefix length;
  - CRC-16 with **all 65,536 polynomials**, reflected and non-reflected, with each
    endian reading, over the full payload;
  - the CRC of the firmware (refer to the text below) over `0x40000..0x77FFE`, `0..0x77FFE`,
    `0..0x80000`, `0x40000..0x80000`, `0..0x44000`, `0x40000..0x78000`, and over
    each prefix length with both init values.
- It depends on payload content **below `0x40000`**. `SDL0430`, `SDL0430N` and
  `SV_49` are byte-identical over flash `0x40000..0x77FFE` (the checksum of all three is
  `0xd195` there). But they have three different `0x0A` values. Thus the covered region
  cannot include that range. This agrees with the diffs: each small pairwise diff between
  these images is in `0x002c0..0x26f5c`.
- We did not recover the `0x0A` field yet. It is different from the CRC
  that the modem verifies. We *did* recover that CRC. Refer to "The application CRC
  the loader verifies" below. We do not know if `0x0A` gates a flash, or if only
  the internal build tools of USR check it.
- `ID_SDL20.EXE` does not contain the algorithm. The DOS downloader contains none of
  the header magic (`b7f0b2fd`, `bcbd4b1f`), neither tag (`NRJ`, `NHCFG`), no
  16-byte run of the `0x4A` fill, and no chunk of the payload. All its CRC strings have
  the form `Modem reports bad CRC`. It streams the file and relays the status.

> **CAUTION: DO NOT SEND `AT~X!` DURING NORMAL DIAGNOSTICS.** If it is
> absolutely necessary, `T` seems to be a test path that does not flash. But `T` also starts the loader,
> and the loader waits for an XMODEM transfer. Thus use it only on a unit that you can lose, or when
> you reverse the loader.

## 80188 memory architecture (segment `0x8000` resolved — see retraction below)

**Recovery-loader update (2026-09-03):** for `SV25.XMD`, a chained
128-byte XOR decode solves the setup-table obfuscation and the mapping break after the bootstrap
that the text below describes. The initial payload key is `0x55`. Then the last decoded byte of
each block becomes the next key. The decoded reset stub supports flash at
`0x80000`. The recovery bootstrap copies its own `0x1b14` bytes into low RAM
and enters through `INT 13h`. `courier recovery-run SV25.XMD` now executes that
path through the full SDL prompt with emulated serial input. This path does not need a speculative
bank switch. Refer to [the recovery harness documentation](docs/sv25-recovery.md)
for the evidence, the input/flash-ID assumptions, and the observed CRC mismatch. The
historical notes below still apply to the resident/overlay map of the normal supervisor,
which is not solved. But the recovery decode replaces their conclusions about the recovery loader.

Tools that we built and that operate correctly:
- **`c25dis.py`** (scratchpad): an accurate port of the TMS320C25 disassembler of MAME
  (Tony La Porta table). **It is incorrect for two reasons: the instruction set is C5x, not
  C25, and we gave it big-endian words**. The "verified correct" note was about
  the table port, not about the instruction set or the byte order. Use [`tools/c5x_disasm.py`](tools/c5x_disasm.py) with little-endian words
  instead. It decodes the `0x29080` init block with zero undecoded words, and 95%
  of its branch targets are in `0x8000–0x8400`.
- x86-16 **Capstone** disassembly, installed locally under
  `/private/tmp/capstone-py`, and recursive descent from the confirmed banner
  code. The recursive descent follows only real control flow (this prevents the "x86 decodes anything" error).

What the recursive descent found:
- The banner code (flash `0x26337`) runs **from flash**. It makes far calls to a
  **resident code segment `0x8000`** (26 different target offsets `0x0A2C…0xF42C`,
  about 47 call sites). There is **no bank-select `OUT` before each call**.
- ~~`segment 0x8000` does **not** map linearly to flash~~. **We retracted this on
  2026-09-05. It does map linearly: `physical = 0x80000 + offset`. Thus
  `8000:xxxx` is file offset `xxxx`.** Probably the earlier attempts
  searched for a *flash base* to add. But the flash is already at physical
  `0x80000`, and the segment offset is directly the file offset. Evidence: the
  206 different far-call targets in `seg 0x8000` have 1053 call sites. When we read them at `file == offset`, **84% start
  with three instructions that look like a correct prologue**.
  At an intentionally incorrect base, the noise floor is 41%. Also, the targets with the most calls
  are typical far-call trampolines. For example, `0xe951` (211 sites) and
  `0x8110` (107 sites) both decode as `call bx ; retf`. The DSP loader block
  gives independent confirmation: `8000:e447` from
  [the DSP ROM probe notes](docs/dsp-rom-probe.md) is exactly at the DSP
  checksum routine at file `0xe447`. The far call in that code,
  `lcall 8f43:0224`, resolves to file `0xf654`, a clean `call 0xf688 ; retf` thunk.
  The model "segment `0x8000` = the 64 KB RAM" came from the old claim. Do not
  use it. Refer to
  [How the DSP is loaded and run](#how-the-dsp-is-loaded-and-run).
- Hardware interface in real code: immediate `IN` from ports **`0x19`, `0x3E`**, and
  `OUT` through `DX` at flash `0x26390/0x2D690`. These are candidate DSP/UART/mailbox ports.

New bootstrap anchors from the loader pass:
- A startup island that looks like normal supervisor code at flash `0x295DC` (probably logical
  offset `0x15DC` in a `0x28000` bank). It sets `DS`/`ES`/`SS` to zero, sets `SP=0x00F8`,
  writes `[0xFFA8]=0x00FF`, and then does 36 `OUT DX,AX` setup writes from
  `CS:[0x1A50]`.
- Recovery-loader startup at flash `0x7DBC0` (logical offset `0x1BC0` in the
  `0x7C000` recovery bank): the same register setup, 36 `OUT DX,AX` writes from
  `CS:[0x1B14]`, and then 9 byte-wide setup writes from `CS:[0x1BA4]`.
- The recovery setup table gives a strong obfuscation/bus-decode hint. If you XOR the
  first 27 records with `0xA1`, you get possible internal control writes of the 80188 type,
  such as `0xFF32=0x007E`, `0xFFA4=0x8000`, `0xFF60=0x801B`,
  `0xFF64=0x0021`, and `0xFF56=0x00DB`. This does not prove that the CPU sees decoded
  values. But it is a useful bank/alias hypothesis. The raw code continues
  into bytes that are not stable x86. Thus the static view does not show some combination of bank switching, bus
  decode, and/or a copied RAM image.

**Why we are still blocked:** to disassemble the resident routines (`8000:xxxx`) or
the DSP overlay loader, we must know the runtime flash→RAM/overlay address mapping. The
80188 reset vector is **not** at file `0x80070` (flash `0x7FFF0`, top-mapped), as we
expected. There is no standard `EA` far jump at that location. The flash is bank-switched, or
stored in non-linear order at coarse granularity. The bootstrap setup possibly
changes the visible code/data mapping before it gets to the resident body.

## Emulation feasibility

**Emulation is possible, but the work depends on the scope.**

- **Emulation of the recovery SDL loader is the best first target.** It is compact,
  it has a confirmed bootstrap at flash `0x7DBC0`, and it has a known command token
  (`~X!`). It needs only serial/XMODEM, flash-write, CRC/checksum, and a small
  model of the 80188 I/O registers. This is probably possible with Unicorn or a small
  8086/80188 interpreter, after we model the bank switch that follows the setup writes.
- **Emulation of the AT command surface is possible after we reconstruct the resident
  image.** We already have the `A`/`T` input-state anchors and the result
  code table. But the real dispatcher after `AT` probably goes through the
  `[0x50]`/`[0x54]` scheduler slots in resident RAM or in a banked overlay. The first
  useful emulator must send bytes through the input interrupt path, stub
  `SS:[0xFF76]` / `SS:[0xFF78]` / `SS:[0xFF02]`, and trap the output-result routines.
- **Full modem emulation is a larger project.** It includes 80188 + TMS320C5x,
  banked flash/RAM, DSP program/data overlays, serial/UART, DAA/line-side
  hardware, and mailbox behavior that is sensitive to timing. It is possible, but it is not
  the shortest path to interop diagnostics.

Recommended next step for emulation: build a loader harness with a narrow scope, not a full
machine. Hook `IN`/`OUT`, log the 80188 setup writes, implement sufficient bank aliases
to go past the bootstrap, and stop on serial-output calls. If the harness gets to the
`SDL Xmodem file transfer` prompt, extend the same harness to the AT
parser.

## Recovered C52 line-audio interface

A trace of the instruction flow and the data flow corrects the initial on-chip-serial
hypothesis. A Courier ASIC external-I/O frame carries the modem/DAA waveform:

- the code reads external I/O `0x54` at program `0xb300` and `0xb304`. Then it copies the value to
  active input cell `0x007f`;
- program `0x8c24` does the matching `OUT` for each frame to external I/O
  `0xb2e5`. The source is output cell `0x00cb`;
- the `TRCV` reads at `0x8c1a`/`0x8c1e` are framing drains. The code loads `DRR`
  into `AR3`, where it is part of the address/bookkeeping state. Neither is the
  linear PCM endpoint.

The resident service slot is 172 instructions / 258 modeled C52 cycles. A later
trace of the call overlay shows that this is an internal TDM slot cadence, not a direct
25 MHz / 9.6 kHz codec period. The ASIC does the line-rate selection. The
emulator puts signed-16 idle input in a queue at `0x54`, captures the resident `OUT`
words, and models the board dial-command handoff that is not in the firmware.
An end-to-end `ATDT123` run sends three verified DTMF pairs through the real
firmware `OUT` instruction. This handoff is still a board-side model. It is not
the internal datapump mailbox, which we did not recover.

### The missing C52 TDM vector now reaches downloaded firmware

The final `IMR=0x0080` of the C52 enables interrupt index 7. The vector slot of this interrupt is
program `0x0010`. That slot is in the customer mask ROM, which we do not have.
This is the reason that the interrupt executed downloaded reset code before.
We can now recover the branch target without an invented negotiation: low
program `0x0228..0x024c` is a complete frame ISR that ends in `RETE`. Its first
words (`bdff 0852 bfb0 0003 bf90 ...`) are the build-specific successor of the
older C51 interrupt-side routine. Its frame arithmetic has the same shape.

The core can now supply that one recovered mask-vector branch. Each completed
C52 DAC `OUT` at `0xb2e5` raises interrupt 7. When `IMR` and `INTM` accept it,
execution enters `0x0228`, runs the downloaded ISR, and goes back to the interrupted
sample loop. This is only ASIC/frame scheduling. The DSP still generates all of the V.8 signal.
A run of 30,000 instructions accepts 133 frame interrupts and records
1,060 data writes from PCs `0x0228..0x024c`. The core keeps low-bank `OUT 0x006a` traffic
as a TDM control slot. It does not add it to line PCM, which would be incorrect.

When we ran the fuller call entry at `0x2285` with this scheduler, we found the next
real opcode gap: `CPL dma` against `DBMR` at `0xa05a`. We implemented the documented compare,
and the path now continues and does not stop. But the
native DAC is still almost silent and `[0x00cc]` is still clear. Thus the next task is the
control/state publication that occurs around this frame ISR. It is not synthesized V.8
menus.

## Recovered DAA originate contract

Dynamic execution of `ATD1` identifies the dial-tone contract on the supervisor side:

- the originate routine at physical `0x5db51` does an off-hook settle wait.
  Then it loads call-progress timeout `0x2580` into timer word `0x0289`;
- it waits at `0x5dbe7` until detector byte `0x0649` becomes five;
- a timeout branches through `0x5dc4a` and sets call-progress flag `0x08d9.4`. Then it
  selects result code 6, `NO DIAL TONE`;
- qualification continues into the dialer overlay. The hardware-timer waits of that overlay
  use `0x08d6` and `0x0161` for pre-dial and make/break cadence.

The behavioral DAA of the emulator supplies a North American 350+440 Hz dial tone
through the confirmed C52 line ADC. It debounces five 100 ms frames, publishes the
recovered `0x0649 = 5` event, removes the dial tone, and starts DTMF at the active
C52 DAC boundary. With this, the original supervisor gets to `OK`. A quiet or disconnected
modeled line keeps the original `NO DIAL TONE` path. We now know the part
from the board, and we know its register semantics (refer to the text below).
We did not confirm the mapping of those fields onto the ASIC
ports that the firmware reads.

## DAA chipset identity — Si3021 + Si3014

We read the part numbers on the board: an **Si3014** on the line side at the phone
jack, and an **Si3021** on the digital side near the CPU. This is a Silicon
Laboratories two-chip silicon DAA. It is the serial-interface member of the family
of the Si3034/35/44/56 chipsets. `docs/` contains the Si3038 datasheet
(the AC'97 sibling, Si3024 + Si3014), AN16 (multiple-device support for the
serial parts), and AN19 (layout).

The topology is more important than the part number. AN16 section 1.3 is
"ASIC Master with single Si3021/56 Slave". In that topology, the Si3021 is in slave mode, and
a device that is not a DSP supplies SCLK and FSYNC. All measurements here
agree that the Courier uses this topology, with the ASIC as the master:

- the C52 configures its serial port as a **slave** and then disables
  it (refer to the text below). Thus it never drives the bus;
- the C52 has access to the outside world only through four ASIC external-I/O ports;
- AN16 figure 1 connects the `FC/RGDT` ring-detect output of the DAA to the
  `INT0` pin of the DSP. But the recovered ring detector on this board is an 80186
  input latch bit (port `0x14`, bit `0x02`). This is a board-level indication, not
  the DSP pin. This agrees with an ASIC between the two.

Thus an accurate DAA model does not answer on the C52 serial port. It must
answer where the firmware reads, which is the ASIC boundary:

| surface | rate | state today |
|---|---|---|
| C52 external I/O `0x50` | 201,524 reads in a 30 M-instruction `ATDT` run, once per service frame, program `0x8c1f` | the host mailbox window's low word |
| C52 external I/O `0x54` | two times for each frame, program `0xb300`/`0xb304`: the line ADC | the behavioral DAA supplies it |
| C52 external I/O `0x56`/`0x57` | one write each at program `0x2b`/`0x02`, both `0xffff` | unmodelled |
| 80186 ports `0x40`..`0x4e` | eight latches, about 7,550 writes each for each `ATDT` run, never read | the host mailbox window |

Before, this document listed port `0x50` as an open question. The code read it once for each frame,
and it floated high because nothing drove it. It does not float. The harness
publishes the eight-byte host window into C52 I/O `0x50`..`0x53`. Both
mailbox commands of an `ATDT` run contain `ffffffffffffffff`. Thus the `0xffff` that the
program reads is a value that the host wrote. There is no spare port on the C52
side. Its only external reads are this window and the line ADC.

The 80186 side also has no register read path. In the same run, ports `0x40`..`0x4e` get
about 7,550 writes each and **zero reads**. Thus, in principle, the supervisor cannot
poll a status byte from the DAA.

But the supervisor has the mailbox, and one of the mailbox messages is the
identity of the DAA. Refer to "The DAA identity arrives as mailbox tag 0x7b" below. The
supervisor gets information about the part one time.

### What the datasheet says the status should carry

The Si3038 register map uses AC'97 addresses, and the serial parts use different register
numbers. Thus these are the *fields*, not addresses. They
agree with the items that this project listed as unmodelled: ring qualification,
loop-current loss, and billing tone. `courier_emu/codec.py` now
contains them:

| field | register | meaning |
|---|---|---|
| `LCS[3:0]` | 5Eh | loop current in 6 mA steps; 0 is under 0.4 mA, 1111 is over 155 mA |
| `RDTP` / `RDTN` | 5Eh | ring detected, positive and negative half-cycles reported separately |
| `BTD` (with `BTE`) | 5Eh / 5Ch | billing tone detected, off-hook held through the tone |
| `FDT` | 5Eh | line-side to system-side frame lock |
| `ROV` | 5Eh | receive overload |
| `OHS` | 5Ch | on-hook speed, fast or slow |
| `RT` | 5Ch | ring threshold, 11-22 or 17-33 V RMS |
| `RZ` | 5Ch | ringer impedance, maximum or synthesized |
| `DCT[1:0]`, `ACT` | 5Ch | DC termination (FCC / Japan / CTR21) and AC termination |
| `DIAL`, `LIM[1:0]`, `VOL[1:0]` | 62h | DTMF headroom, current limit, line voltage trim |

### The bring-up nobody on this board performs

The initialization procedure of the datasheet is a sequence with a handshake in the
middle:

1. write a value to `3Ch` (a register reset);
2. program the sample rate in `40h`/`42h`;
3. write `0x0000` to `3Eh` to power the part up;
4. **poll `3Eh[7:0]`** until it reads `0x0f` (line 1) or `0x33` (line 2);
5. program the GPIO registers `4Ch`..`54h`;
6. program the DAC/ADC levels in `46h`/`48h`;
7. program the country-specific line parameters in `5Ch` and `62h`.

Step 4 is the discriminator. It must have a controller that can *read* the
codec, and neither processor on this board has one. The 80186 only writes
`0x40`..`0x4e`, and the two external reads of the C52 are the host window and the
line ADC. Thus the device that runs this sequence is on the far side of the ASIC. This is
exactly the topology of AN16 section 1.3. The ring detector
on an 80186 latch bit already showed this.

`courier_emu/codec.py` models this topology. `SiliconDaa` is the register file. It contains the reset
defaults and the supported rate table of the PLL. It calculates the readiness byte again each time and does not
latch it. It assembles register `5Eh` from the line and does not store it.
`CodecBringUp` is the ASIC-side master that runs the seven steps on
it. The model has real ordering constraints:

- if the PLL stays at zero, the readiness poll never completes, because no
  line-side communication occurs. This is the reason that step 2 comes before step 3;
- the reference and GPIO start one frame before the converters. Thus the poll of step 4
  reads `0x03` before it reads `0x0f`;
- an access to a line-side register before the ISOcap barrier is up latches `CLE`
  and discards the write. Thus a bring-up in the incorrect order leaves a trace.

The register addresses are those of the Si3038. The Si3021 on the board gets access to the same
line-side fields through its own control frames, and it uses different numbers for them.
Thus an address in that module means "the register that contains this field". It is never a
value that the Courier firmware sends.

There is no register read path. Thus the bridge drives the model, and nothing polls it. The
bridge gives it one ASIC service frame for each 100 ms. It supplies the hook state and the line
state from the behavioral DAA, and the ring cadence from the ring source. It
reports the model under `dsp_bridge.codec`. The model now contains loop-current sense, ring
qualification, frame lock, and the country settings. If we find a read path to
those fields, it will connect to the same object.

### The DAA identity arrives as mailbox tag 0x7b

> **This section is about `main211.xmf`, not `SV25.XMD`. Corrected on 2026-09-19.**
> Each address here is a physical address in the Courier 3453B v2.1.1 supervisor (analog: the image contains no "ISDN" string).
> This image loads at **file + `0x40000`** - `0x5c6b6` is file `0x1c6b6`, `0x6ad5b`
> is file `0x2ad5b`, `0x82b64` is file `0x42b64`. All of these locations are **zero** in
> `SV25.XMD`. `SV25.XMD` contains no reference to `[0x281]`, `[0x283]`, `[0x285]`
> or `[0x287]` in any addressing form. The section is correct for the image that we
> read it from, but it is in the incorrect document. Refer to
> [the RAM-map collision](docs/datapump-dispatch-gate.md).


The supervisor *does* get one item of information about the DAA: its revision. `ATI7`
prints it. The receive handler at `0x6ad5b` reads a tag from the mailbox
header ports `0x58`/`0x5a`. It rejects all values at or above `0x80`. It dispatches
four DAA tags, and each tag gets its data word from `0x5e`/`0x5c`:

| tag | destination | carries | requested by |
|---|---|---|---|
| `0x7b` | `[0x287]` | the DAA revision | — (sent unprompted) |
| `0x7c` | `[0x283]` and `[0x285]` | the line reading `[0x649]` qualifies on | `0x7c00` |
| `0x7d` | `[0x27f]` | unidentified | unidentified |
| `0x7e` | `[0x281]` | a line-side register read | `0x8000` |

The code itself shows the function of `0x7e`. An AT diagnostic at `0x82b64` matches the
literal `"SI"`. With no argument, it sends request `0x8000`, waits, and prints
`[0x281]` under `"\r\nta_report_si_read="`. With an argument of four hex digits, it
parses the argument into `BX` and sends command `0x0084`, the register **write**. Then the
consumer at `0x5e576` tests only bits 0 and 1 of `[0x281]`. Each bit has
its own four-hit debounce in `[0x647]`/`[0x648]`. Then the consumer clears the word. These bits
are `RDTN` and `RDTP`, the two ring-detect half-cycles of register `5Eh`.
They are reported separately, as the datasheet describes. `test byte [0x287], 0x10` gates both the read and the
write. Thus the line-side revision decides
if the path is active.

The supervisor already sends `0x0084` writes during a normal boot:
`0084:1468` and `0084:1408`, and `0084:0100` on a call. Thus this path is not only for
diagnostics. None of it runs in the harness now. For the reason, refer to "The mask is
set at boot and never cleared" below.

Three sites read `[0x287]`:

```
0x77edb   mov ax, [0x287]          ; ATI7's "DAA rev", printed as four hex digits
0x77ee3   cmp word [0x287], 0
0x77ee8   jne  ...                 ; zero falls through to the inline string
          " : DAA Failure (zero is Invalid)"
0x8369d   cmp word [0x287], 4
0x836a2   jne  ...                 ; 4 prints "00345302", anything else "XX345302"
```

Thus the firmware has its own decision about this word. Zero is a failed DAA, and
4 is the revision that this build expects. The reason is that 4 is the value that changes the
product ID from the placeholder `XX345302` to `00345302`. Nothing in the
harness sent the message. Thus each run reported a DAA that the firmware
considered invalid:

```
Product ID             XX345302        DAA rev  0000
```

The bridge now puts tag `0x7b` in the queue with the revision of the modelled part. It
does this on the **first** DSP download, not the second.
The coprocessor-ready pair `0x02`/`0x03` is part of the dial/answer boundary. A
part identifies itself at power-up, before a call. The identity must be
available before the first `ATI7`. That run reports:

```
Product ID             00345302        DAA rev  0004
```

The revision is still a guess. We got 4 from the product-ID branch,
not from a part. It does **not** have bit `0x10` set. Thus the value that
gives the better product ID is also the value that keeps the `si` register path
disabled. In the datasheet, register `5Ah` contains the revisions of two chips in
one word (`REVA[3:0]` system side, `REVB[3:0]` line side, `CBID` at bit 8, with
`0010` = Rev B and `0011` = Rev C). With this register, the two firmware tests are two
different fields, not a contradiction. `== 4` matches the full word.
`& 0x10` is `REVB` bit 0, which separates a Rev C line side from a Rev B line side. If
`[0x287]` is that register, then a real board with a Rev C line side prints
`XX345302`, and the placeholder is correct. To find the answer, the `si` path must
run, and it cannot run yet.

> **Measured on 2026-10-03 on a real 3453C** (stock 2.3.33 / DSP 2.1.41, CTR21):
> `ATI7` prints `DAA rev 0013` and `ATGR0000:0280` shows `[0x287]` = `0x0013`.
> Bit `0x10` is set. Thus on the hardware, the `si` path is active. 2.3.33 has the same
> `== 4` test (`0x830e2`, strings `00345303`/`XX345303`). `0x13` goes to the `XX`
> branch, and the board prints `99345303`. Thus `XX` is a placeholder that
> later code fills (with `99` on this CTR21 unit). It is not a failure marker.
> We compared with the part on the board (`docs/SI3034.PDF`, Si3021 + Si3014). The `0x0084`
> data word is the Si3021 control word (`D13` = read, `D12:8` = register).
> Thus `0084:3100` is a read of register 17, not a write. On the Si3021, the ring
> bits are register 5 bits 6/5, not bits 0/1. Thus `[0x281]` is not a raw register.
> The decode is in `artifacts/3453c-board-identity-20261003/atg-monitor-2.3.33.md`.
> Refer to `artifacts/3453c-board-identity-20261003/`.

`0x7d` is the only tag for which we found no consumer. The only other
location that uses it is a printer at `0x794de`. The printer shows `[0x283]` `:` `[0x27f]` `:`
byte `[0x64c]` as a colon triple. We injected marker values for all three tags
and confirmed delivery in the trace. The values did not occur on a page that we can get to.

### The C52 serial port is configured once and disabled

A trace of the writes of the C52 to its memory-mapped registers shows the full
serial life of the program:

```
program 0x00be   SPC <- 0x0008    receiver and transmitter held in reset
program 0x00c0   SPC <- 0x40c8    both out of reset, burst frame sync,
                                  TXM = MCM = 0: externally clocked slave
program 0x00c2   DXR <- 0x0001    prime the transmitter
program 0x00c6   DXR <- 0x0001    prime again
program 0x00cb   IMR <- 0x002a    unmask INT2, TINT and XINT
program 0x8189   SPC <- 0x0000    shut the port down
```

`SPC = 0x40c8` is the slave configuration of AN16. Two primes of `DXR`
with `XINT` unmasked show an interrupt-driven transmitter. An unconditional jump from the boot block into the
high bank goes to the shutdown at
`0x8189`. There is no condition. The enable word `0x40c8`
occurs exactly **once** in the full DSP image. On all paths that the code can get to,
including a full `ATDT123` on a dial-tone line, `SPC` stays zero and `DXR`
keeps its three boot writes. During this time, the code reads `DRR` tens of thousands of times.

Thus this program never opens the serial link. The datapump
mailbox does not gate it. No code that can run in the image enables it again.

## SIP line adapter

The behavioral DAA can now terminate on a minimal SIP/SDP/RTP client. The adapter
uses the recovered `ATD` number to make an INVITE URI. It does this only after the
`0x0649 = 5` dial-tone transition of the firmware. The SIP trying/ringing/connected/failed states
update the DAA operation state. PCMU RTP is converted between 8 kHz and
the confirmed 9.6 kHz line cadence of the ASIC. The current DTMF assist goes in
at the recovered C52 line-output write. It is carried in-band. It is not sent
as SIP events. The datapump did not accept the originate command yet.

A loopback PBX validation of `ATD123` gave `INVITE sip:123@127.0.0.1`,
completed `200 OK`/ACK, sent 250 RTP packets, and decoded the first packet burst
as 697+1209 Hz. This proves the chain firmware command → DAA qualification → SIP signaling
→ C52 audio → PCMU RTP. A subsequent live call from 6000 to 7800 received `200 OK`
and exchanged 1,152 inbound / 507 outbound RTP packets. But the firmware still
returned `NO CARRIER`.

We now know that the failure is below SIP. During that call, the supervisor sent
30 two-word runtime messages through ports `0x58..0x5e`. None of them
got to the datapump. The incoming supervisor event tags `0x02`, `0x03`, `0x09`,
and `0x4d` execute their recovered handlers, but this does not correct the problem.

An earlier revision of this section said that the read at C52 program `0x8c1f` was the
command poll of the datapump. It gave "recover the `0x58..0x5e` to C52 `0x50/0x51`
valid/ack timing" as the next necessary step. That lead is closed. Refer to the text below.

### The window word `0x50` is not a command port

The C52 image has no `IN` for port `0x50`. On a C5x, data addresses
`0x50..0x5f` are reserved. This core decodes them as external I/O.
This is the only reason that they occur in the I/O event log. The site is one
instruction:

```
8c19  0100  LAR   AR1, @00
8c1a  1130  LACC  @30            ; TRCV
8c1c  0320  LAR   AR3, @20       ; DRR
8c1e  1130  LACC  @30
8c1f  4650  BIT   @50, 6         ; TC = bit 9 of the host window word
...
8c24  0c80  OUT   *, 0xb2e5      ; the line DAC
8c3d  be4a  CLRC  TC             ; and the bit is discarded here
8c3e  7980  B     0xb2e9
```

`BIT` writes only `TC`. No instruction between `0x8c1f` and the `CLRC TC` at
`0x8c3d` reads it. The code reads the word once for each sample and discards it. Three
checks on the running core agree:

| check | result |
|---|---|
| each of the 12 header values that the supervisor sends, put at window words `0x50`/`0x51`, over a run of 3.4 M instructions | byte-identical in each counter, including the stop PC |
| `IMR` after boot | `0x0000`. The core cannot accept a host interrupt |
| all 2,274 runtime messages of a run, applied as `host_write(header, data)` into C52 data space | no change |

Thus the resident program has no host-to-datapump command path of any type.

A differential `AT`/`ATDT123` capture now gives much more information about the board-side protocol.
The bridge reports a complete histogram, and the first 80186
instruction and PC for each different message.  Plain command mode sends only
12 words.  Dialling adds a one-time `0082:0060` transition. Then it puts
this block of 12 messages in the queue again and again:

```
0082:0020  0082:0000  0015:0000  001f:0000
0019:020d  0019:020d  0016:0000  0016:0000
001a:3000  001b:0c08  0013:0001  001f:8000
```

The apparent send PCs identify two real transmit paths, not C52 data
writes.  `0x6ad47..0x6ad5f` sends the single pending word at `[0x02ca]`.
`0x6ae81..0x6aec3` reads a circular queue at `[0x02e0..0x030f]` with pointer
`[0x02dc]`.  Thus the values below `0x80` are board/ASIC register commands.
The model that used their headers as C52 data addresses was completely
incorrect.  `0082:0060` is the first originate-mode transition.

We also recovered the producer.  The generic immediate sender is
`0x5d76b`. If `[0x02cb]` is free, it stores `AX` at `[0x02ca]`. If not, it
puts `AX` in the queue.  The call at `0x5dc03` occurs immediately after the five-hit detector wait
is successful. It enters ASIC routine `0x6ae51`:

```
6ae51  mov ah,82h
6ae53  mov al,[1fab]       ; ASIC register-shadow byte
6ae56  or  al,60h
6ae58  and al,7bh          ; set 60, clear 84
6ae5a  call update-shadow
6ae5f  call send-immediate ; emits 82:60 with the default shadow
6ae64  mov ah,82h
6ae66  mov al,[1fab]
6ae69  and al,3bh          ; clear 40,80,04; leaves 20 initially
6ae6b  call update-shadow
```

Thus the later `82:20` and `82:00` messages are successive writes to the
same ASIC control register. They are not random event tags.  The adjacent init
routine at `0x6adff` also publishes shadow bytes `[0x1faa..0x1fac]` as
registers `0x7d`, `0x82`, and `0x83`, and then two `0x84` words.  This shows that
`[0x1fab]` is the software shadow of register 0x82. It also shows that the call-progress routine at
`0x5dbb0..0x5dc63` is the source of its originate transition.

An `ATA` differential run uses the same `82:60 -> 82:20 -> 82:00` path. Thus
these bits select common line-operation phases. They do not select originate or
answer modulation.  The emulator now shows the shadowed block under
`dsp_bridge.asic`: register values and write counts, the decoded phase of register `0x82`,
and the ring-indicate bit of register `0x83`.

The read/modify/write masks give a useful individual meaning to each high bit of `0x82`.
They are not only four opaque states:

| bit | observed sequencing | inferred ASIC output |
|---:|---|---|
| `0x80` | set in held state `a0`, explicitly cleared before `60` | call-engine hold |
| `0x40` | set only for `60`, then immediately removed from the shadow | start strobe |
| `0x20` | present in `a0`, `60`, and `20`; cleared on shutdown | line/datapump enable |
| `0x04` | explicitly cleared by both transition masks | unknown interlock |

Thus the sequence `a0 -> 60 -> 20 -> 00` means **engine held while
enabled -> release hold and start strobe -> enabled/run -> disabled**.  This
is the first interpretation that explains each mask operation, the short pulse
of bit 6, and the common originate/answer path.  The emulator reports
these as `engine_hold`, `start_strobe`, and `line_enable`.

The supervisor code excludes two possible interpretations.  C52 reset is a
separate path at `0x69bf1..0x69c84`. It changes 80186 peripheral register
`0xff56`, floats ports `0x1c/0x1e`, waits until both words read `0xffff`, and
then enters downloader `0x69cd2..0x69deb`.  Dynamic `ATD` and `ATA` runs execute
that bootstrap only one time. The `0x82` transition does not reset the C52 or download it again.
Also, the explicit eight-byte downloader does the program loading/bank placement with
`[0x1fb2]/[0x1fb3]` and ports `0x40..0x4e`. That path does not read a
`0x82` shadow value.

Thus `0x82` is not the C52 reset control. Also, there is no code evidence
that it selects a downloaded program bank.  It comes after line-detector
qualification, `ATD` and `ATA` use it identically, and it is shut down at `0x5e5e8`.
These facts identify it more precisely as the **line/call engine enable and start
strobe** of the ASIC.  The initial `0xa0` is the held/initialised state of the engine, not the
reset state of the C52.  The code and a feature differential answer an important naming question. There is
no separate "enter V.92" command on the supervisor side.  We did two `ATDT123` runs that were
identical except for one item. One run had the full `hst,fax,terbo,v34,v90` parameter sector, and
the other had only `hst`. Both runs sent the same call-engine stream, value for value:

```
82:60 -> 82:20 -> 82:00
13:01, 15:00, 1f:00, 19:020d (twice), 16:00 (twice),
1a:3000, 1b:0c08, 13:01, 1f:8000
```

The V.90 feature bit changes product reporting and capability policy. This build
always prints V.92. Neither changes the ASIC call
start.  The other V.92 text references in the supervisor are for reporting,
configuration, and post-call diagnostics.  None of them sends a different value into
`[0x1fab]`, the queue helper, or the C52 downloader.

Thus the supervisor code activates the **generic automatic
negotiation datapump**, at `0x5dc03 -> 0x6ae51 -> 82:60`.  Later, that datapump must select
V.92 from the V.8/V.8bis and training exchange with the far
end. If necessary, it falls back to V.90/V.34.  The 80186 has no entry point
that is only for V.92.  The missing implementation is the ASIC
consumer of the repeated `0x13/0x15/0x16/0x19/0x1a/0x1b/0x1f` block, and the
DSP-side start/frame state that it causes. When we recover that generic consumer,
the code can get to the existing V.92 code.

### Where the command stream is consumed

The executable code shows the full limits of this, although
the implementation of the consumer is not in the XMF.  The 80186 producer ends
at four byte-wide output latches:

```
port 58 = command/header low
port 5a = command/header high
port 5c = argument low
port 5e = argument high
port 1c = valid/acknowledge state
```

After `OUT 5e,AL`, no 80186 routine dispatches the command locally.  In the image, the only
software on the far side is the C52, and it cannot be the
consumer:

- its downloaded program never executes an `IN` from these 80186 ports;
- the eight-byte C52 window is the separate `0x40..0x4e` bootstrap surface;
- when we apply each runtime pair as C52 data writes, no execution state changes;
- its only steady external reads are the reserved/frame word that agrees with
  `0x50`, and line ADC `0x54`; and
- the program discards each tested command value at `0x50` before it uses `TC`.

The receive direction proves the same topology.  The 80186 reads replies
from `0x58..0x5e`. These include the DAA identity and detector results that come from
outside the two processors. Bit 1 of port `0x1c` shows that they are available.  Thus the
bidirectional queue ends in the hardware command engine of the Courier ASIC, which is
between the two processors.  It is not a missing 80186 routine or a hidden entry in the
downloaded C52 program.

The code also limits what that hardware engine does with the call block.
Commands `0x13..0x1f` repeat while register `0x82.5` enables the engine.
`0x82.6` starts it, and when `0x82.5` is cleared, the engine stops.  The evidence shows that the same ASIC is
the master of the Si3021 serial link, and the source/sink of the framed
ADC/DAC words of the C52.  Thus the consumer is the line-frame/call state
machine of the ASIC. It translates the queue into DAA transactions and DSP frame/control
state.  Its gates or microcode are in the silicon. They are not in the supplied
firmware files. The XMF contains only the producer and the downstream C52
payload.

A first behavioral implementation now consumes that block.  It stores
registers `0x13..0x1f`. It recognizes the observed `0x1f:0000 -> 0x1f:8000`
rising edge as commit. It starts the call engine one time. It returns tags `0x02` and
`0x03`, because the recovered supervisor receive table maps those to its two
coprocessor-ready latches.  It counts repeated commit edges, but it does not send
the ready reports again.  In an `ATDT123` run of 8 M instructions, the original firmware
accepts both replies and changes its callbacks to `50ad,18e3,4cac`, with
`[0x1cf0]=1`. The C52 still sends only its single nonzero startup sample.

That result validates the guessed **command acceptance/ready** half of the ASIC
contract. It also shows that the ready replies alone do not activate the
modulation code.  The remaining guessed half must be frame/control state for the DSP,
which the ASIC generates on commit. Another supervisor tag cannot replace it.

There is a DSP-side interpretation of the control block that is not an accident: each
command number is the address of a C52 memory-mapped control register.

| command | C52 register | supplied value |
|---:|---|---:|
| `0x13` | `AR3` | `0001` |
| `0x15` | `AR5` | `0000` |
| `0x16` | `AR6` | `0000` |
| `0x19` | `ARCR` | `020d` |
| `0x1a` | `CBSR1` | `3000` |
| `0x1b` | `CBER1` | `0c08` |
| `0x1f` | `BMAR` | `0000 -> 8000` |

The byte lanes must be swapped at the ASIC/C52 boundary.  The unswapped pair
`CBSR1=3000, CBER1=0c08` gives a descending circular buffer, which is not possible.
The physical C52 values are the coherent `CBSR1=0030, CBER1=080c`.  Thus the full
batch becomes `AR3=0100`, `ARCR=0d02`, `CBSR1=0030`, `CBER1=080c`,
and `BMAR=0080`.  This is strong independent evidence that these are real
C52 register lanes, and not command numbers that are the same by accident.

The behavioral consumer now collects those values into a batch. It publishes them to the
C52 atomically on the wire-level `BMAR=8000` (C52 `0080`) commit edge.  This is very different
from the earlier failed experiment, which replayed each mailbox pair at
random instruction boundaries. The ASIC controls the frame boundary, and the
`BMAR` transition is its commit marker.  A full run accepts 77 commits and
stays stable, but it still sends no carrier.  Thus this recovers one item of
DSP control state that looks real. It also shows that the register batch alone is not
the missing frame event.  The next control surface is the event that comes with
the atomic register publication. This is most probably the C52 frame/TDM edge of the ASIC, or a
program-memory block move that `BMAR` selects.

The earlier behavioral V.8 fallback, with its limits, is no longer attached to normal
calls. It proved that 1300 Hz CI and 2100 Hz ANSam can go through the recovered
9.6 kHz line path. But it also replaced each subsequent DSP DAC word and hid
the failure that we investigate. The explicit native tone API is still useful as
a transport test. The bridge now releases the DAC after the board-side DTMF. Thus
V.8 and all later modulation must come from downloaded DSP code.

We now know that the calculated call-engine entry is at C52 program `0x2295`.  If we force
that PC from the settled service state, the code immediately executes `BLPD *BMAR`. Then it
branches through `0xa9a9`, runs a large datapump initializer, and goes back
to the 169-instruction service cycle.  At first, it stopped at two missing
core operations. When we implemented the documented C5x `BLPD BMAR` and `MAC`
semantics, the full path completed.  This is the first recovered
call-time transition in the original C52, and not behavioral line
synthesis.  The ASIC commit now enters `0x2295` after it publishes
`BMAR=0x0080`. A regression test executes 5,000 instructions from that entry. The test
makes sure that the code goes back to stable line-frame output without an unsupported
opcode.

`ATA` and originate commits still enter the recovered C52 call boundary. But they
no longer arm synthesized ANSam or CI. `dsp_bridge.asic.v8_armed` now means that
the datapump entry was requested. Nonzero DAC output after the dial is evidence that the
firmware advanced. It is not evidence that a fallback was attached.

The bridge reports `call_engine_started`, `commit_edges`,
`dsp_register_commits`, and the complete latched command register block under
`dsp_bridge.asic`. Thus you can monitor each subsequent DSP-side experiment.

The recovered responsibilities now give the ASIC boundary a narrow definition:

- arbitrate the 80186 command queue and interrupt/status handshake;
- bootstrap the C52 through the eight-byte `0x40..0x4e` window;
- master the Si3021 serial DAA and report its identity/status;
- frame the 9.6 kHz ADC/DAC stream visible at C52 external I/O;
- carry line detector and ring-indicate state; and
- sequence a call through register `0x82` independently of whether the
  supervisor selected originate or answer.

A dynamic trace also recovers queue helper `0x6b067` (`MOV [BX],AX` at
`0x6b083`). The trace now records its return address and, when a wrapper is used, also the outer producer.
This separates detector polling (`0x6db4c/0x6db5b`), call
control (`0x6cebc`), and other producers. Thus the trace does not give each command
to the common sender.

We still know well what the runtime channel of the supervisor *is*. A run of 12 M instructions has 2,274
two-word messages, with a valid/ack handshake on port
`0x1c` (`in 0x1c` 2,279, `out 0x1c` 4,558). The `0x40..0x4e` window is used
only for the two program downloads. But the consumer of the channel on the board is not the
C52 code that these images run. There are two remaining candidates. Possibly the datapump entry
is in the downloaded low bank, and the code never enters it here. Or possibly the channel
ends in the ASIC and not in the C52.

## The datapump is resident, idle, and gated on one bit

A static decode of a C5x image gives too many results, because each word decodes.
If we take the instruction boundaries from a real run, this problem does not occur. With that method, all
that the C52 executes in steady state is **167 instructions**. One pass of
it is 169 instructions. This is about 6% of the 2,604 cycles that a 25 MHz part has for each
9.6 kHz sample. The code enters it at `0x0cb1` for each sample, and it runs:

```
0cb1 (low bank)  ->  c1cd  ->  de89  ->  8c19  ->  b2e9  ->  c7f7
                 ->  e24b  ->  b30b  ->  de9c  ->  8195  ->  a8c7  ->  back
```

The first result is that the code **enters the downloaded bank**. The image has
three program segments. The supervisor downloads only the low segment (`0x0000..0x75d9`),
and the loop head at `0x0cb1` is in it.
The datapump is resident and it runs. It does not wait for a start.

### The gate

Near the end of each pass:

```
a8c7  b5cc  LAR   AR5, #0xcc
a8c8  bf09  LAR   AR1, #0x02ff
a8ca  4b80  BIT   *, 4          ; bit 4 of [0x00cc]
a8cb  e900  CC    0xb4d4, TC    ; never taken
```

`[0x00cc]` reads zero on each sample of each run. Thus the code never enters `0xb4d4`.
When we set bit 4 manually, the datapump changed state for the first time:

| | line-DAC writes | non-zero samples | parked PC |
|---|---:|---:|---|
| untouched | 14,102 | 1 | `0x8195` (resident bank) |
| `[0x00cc]` bit 4 set | 15,515 | 10 | `0x0bda3` (downloaded bank) |

### What sets `[0x00cc]`

The datapump sets it, from a value that it keeps in a closed loop. A trace of
each data write into the frame block shows that four sites write zero to `[0x00cc]` on each
sample: three in the `0xde89` prologue, and `0x81a0`. `[0x00cc]` is one cell above `[0x00cb]`,
the line-DAC source. `0x81a0` is the last of the
four before the test. A single-step run of the block with signal on the line
shows the full chain:

```
b304  ADD  @54        ; ACC 00000000 -> ffffe605, the held ADC word
b305  SACL @7f        ; [0x7f] = e605
b306  LACB            ; ACC <- ACCB = 05550000, and the sample is gone
b307  SACH @7e        ; [0x7e] = 0555
b308  SACL @7d        ; [0x7d] = 0000
...
b30b  LACC @7e, 16    ; and the pass ends by rebuilding ACCB
b30c  ADDS @7d        ;   from the same two cells
b30d  SACB
...
81a0  SACL *          ; [0x00cc] = [0x7d]
a8ca  BIT  *, 4       ; bit 4 of it
```

Thus `[0x00cc]` is the low half of a 32-bit word that the datapump moves from sample
to sample through `[0x7e]:[0x7d]` and ACCB. It holds `0x0555_0000` for the full
run (high half `0x0555`, low half zero). Thus bit 4 is clear and the gate stays
closed.

This also explains why a signal changes nothing. The line sample *does* get to the
accumulator at `0xb304`, and the code *does* store it, to `[0x7f]` at `0xb305`. Then `LACB` at
`0xb306` loads ACC from ACCB again and the sum is discarded. Also, a `TBLR` from a program table
at `0x81b1` writes over `[0x7f]` before any instruction reads
it. In this state, the design of the code stops the receive path. The input from the harness
is not the cause.

Also, nothing outside can set the word. We held each cell of the
on-chip data space of the C52 in turn (1,952 cells), and compared the line-DAC counts, the
serial registers, the parked PC and the cycle count. Only **eight** cells changed the run:

| cell | what it is |
|---|---|
| `[0x00cb]`, `[0x00cc]` | the DAC source of the frame block, and the gate |
| `[0x007f]` | the scratch cell that gets the discarded sample |
| `[0x0082]` | changes the run, but gives no output |
| `[0x037d]`, `[0x037e]`, `[0x03fd]`, `[0x03fe]` | the same `@7d`/`@7e` offsets on the DP pages that `0xde9c` and `0xa8d0` select |

An idle datapump reads almost nothing: not its own RAM, not the line, not
the host window, and not an interrupt (`IMR` is zero). The event that starts it does
not come through an input that this build of the C52 monitors.

### The receiver is gated off, not merely unsignalled

We supplied a 2100 Hz, 1800 Hz or 980 Hz tone at the confirmed
9.6 kHz cadence, or noise, to the ASIC line input, instead of silence. Each counter stayed identical:
19,984 line-DAC writes, one of them non-zero, `[0x00cc]` always
zero, and the same parked PC. The datapump does not respond to a signal
until it gets a command. This agrees with the gate above. It excludes the theory
"it listens but it hears nothing".

### What `0xb4d4` expects on entry: nothing, because it is not code

We forced the gate and caught the first entry. This shows the state at entry:
`DP` 0x380, `ARP` 5, `AR5` = `0x00cc`, `ACC` `ffffff00`, `ACCB` `05550000`,
`[0x7b..0x7f]` = 0, 0, 0, `0555`, 0. Then 570 instructions follow. They decode as a
sequence of `LAR AR0, @xx` over a smooth numeric sequence, with runs of `0xffff` between the parts:

```
b4d4: 0053 0064 0079 0092 ffff ffff ffff ffff ffff 0093 0078 0061 0052 0049
b4e2: 002a 002f 003a 0047 005f 007d 009e ffff ffff ffff 009f 007b 005e 0046
```

That is a table, not a routine. Execution continues into `0xc418`, `0xe580` and
`0xb671`, runs 1,171 instructions there, and returns. Thus the earlier interpretation
of `0xa8cb` as an active conditional call into the datapump was incorrect. When we force the
bit, the CPU runs into data. The ten non-zero line words that it gave are
the result of this. They are not a carrier.

### The reset code, which is anchored, says something different

Program `0x0000` is the only origin that is not a guess, because it is the bank that the
supervisor downloads. It is clear C5x startup code:

```
0000  LDP  #0
0007  SPLK #0x0010, @2a     ; CWSR
0009  SPLK #0x000a, @28     ; PDWSR
000b  SPLK #0x0001, @29     ; IOWSR
0011  SPLK #0x27bd, @7d ; LST ST1
0014  APL  #0x07f8, @07 ; OPL #0x00b0, @07   ; PMST: AVIS, OVLY, RAM
001d  LAR  AR1, #0x0100 ; RPTZ #0x3ff ; SACH *   ; clear 1,024 words
00bd  SPLK #0x0008, *   ; SPC = 0x0008
00bf  SPLK #0x40c8, *   ; SPC = 0x40c8, receiver out of reset
00c9  LACC #0x002a ; SAMM @04              ; IMR = 0x002a
00cc  CLRC INTM                            ; interrupts on
00cf  CALL 0x8188
```

The `CALL 0x8188` literal goes exactly to the location where the code writes `SPC` again. This is the only
site in the image that contains `0x40c8`, and here it writes `0x0000`. Thus the reset code opens the serial
port, and the routine that the reset code calls closes it immediately.
"No code that can run in the image enables it again" was only half of the explanation.

### Two earlier measurements were mine, not the firmware's

`courier_c5x_get_data` and `courier_c5x_set_data` go directly to the data array
and do not use the C5x register decode. Thus a read of address `0x04` gives
`m_data[0x04]`, not `IMR`. **`IMR` is not zero.** It is `0x002a` after
reset. At the end of each sample, the code at `0x81be` writes `0x0080` to it.

### Interrupt 7 is enabled, and raising it re-runs the boot

We raised each of the sixteen interrupts in turn. Exactly one changes the run:
number 7, the TDM serial port. At first, it looked like the datapump started
to operate. The executed instruction sites increased from 167 to 521, most of the line-DAC
words changed from zero, and the C52 started to write its serial transmit
register. But that is not the cause. A count of the locations of those instructions:

| | sites | instructions below `0x00d0` | `0x0010` entered | SPC writes |
|---|---:|---:|---:|---:|
| idle | 167 | 0 | 0 | 0 |
| interrupt 7 driven | 521 | **5,895** | **5** | 15, from `00be`, `00c0`, `8189` |

`PMST.IPTR` is zero. Thus interrupt 7 vectors to program `0x0010`, which is
in the reset code. The 354 more sites are the boot path. The SPC and DXR
writes are those of the boot. The line output is the DC level that the boot leaves.
When we drive the interrupt, the C52 partially boots again.

### There is no vector table in this image

That collision is not a small item. It is the main question. `PMST.IPTR` can only
put the table on one of 32 two-kiloword boundaries. A C5x table has 2 words
for each vector, usually a branch. We scored all 32 permitted bases for a run of
consecutive two-word branches with targets in a loaded segment. The
longest run is **one slot**, at `0xc800`. A search of the full
image also finds no table: the longest runs are `0x519a` (14),
`0x2184` (8) and `0xbb70` (7), and all three are usual sequential `CALL`
code. `0xbb70` is seven identical `CALL 0xc881`.

Also, the code does not write the area again after boot. In 600,000 instructions of startup, the
only executed instruction that touches program memory is one `BLPD` at
`0x0030`, and `BLPD` reads program into data. There is no `TBLW` and no `BLDP`. The reset
code stays on the vector area for the full run.

Thus the vectors are not in the XMF. The interpretation that agrees with the data is this: the C52 is in
microcomputer mode. Its program `0x0000..0x0fff` is on-chip ROM that contains
the vector table and the bootstrap that receives the download. Neither is in
this image. Thus the harness assumes that the downloaded segment
starts at program `0x0000`, and this puts the downloaded init on the vectors.

### No image in the tree has one either

The table is also not in images other than `main211`. We scanned all fifteen images here (six
XMFs, four XMDs, the ISDN ROM, `.nac`, `.sdl` and `.xmp`), in both byte orders,
for runs of two-word branch slots. We found no table. The
15-slot and 16-slot runs in `SV25.XMD`, `SDL0430.XMD`, `SV_49.XMD` and
`IDSDL302.XMD` are filler: one repeated word, `7d77`, `7a37` or `7077`. The
runs in the XMFs are all the same sliding window over one block of sequential
`CALL` code (`0xa624` in the 2.1/2.2 builds, `0x4554` in `main2205`). The
targets of these calls repeat and do not spread. If the handler word must change, nothing
remains.

Also, a C52 boot ROM cannot be in these files. It is a TI mask ROM. USR does not
supply it in a firmware update.

### What the family does share, and where it splits

The DSP payload of each XMF starts at file `0x2f0` with reset code. There are two variants:

| build | opening |
|---|---|
| `main211`, `main2205`, `3453Bv2.1.1` | `LDP #0` · `SPLK #0xffff, @57` · `SPLK #0, @7a` · `SETC INTM` |
| `2_3_33`, `MAIN_2.3.12/15/31` | `LDP #0xfe` · `SPLK #0xffff, @53` · **`OUT @53, 0x8057`** · `LDP #0` · `SPLK #0, @7a` · `SETC INTM` |

The three older builds are byte-identical over their full opening. The 2.3.x
build is different in two ways that are important. Its first action, before it sets
wait states or other items, is an external write of `0xffff` to I/O port
`0x8057`. Also, it programs different wait states: `PDWSR` `0x2000` instead of
`0x000a`, and `IOWSR` `0x0101` instead of `0x0001`.

### What the wait states say

`PDWSR` gives a two-bit field to each 16K block of program and data space. `IOWSR`
gives one to each pair of I/O ports (or to each 8K block when the `BIG` bit of `CWSR` is
set). `CWSR` sets if a field means 0/1/2/3 wait states or 0/1/3/7
(SPRU056D §9.4.1–9.4.3, tables 9–5 and 9–10). Both builds write `CWSR` `0x0010`:
`BIG` set, and each space on the plain 0/1/2/3 scale. With this, we can decode the two
`PDWSR` words:

| build | field | range | wait states |
|---|---|---|---:|
| 2.1/2.2 (`0x000a`) | Program 1 | `0x0000..0x3fff` | **2** |
| | Program 2 | `0x4000..0x7fff` | **2** |
| | everything else | | 0 |
| 2.3.x (`0x2000`) | Data 3 | `0x8000..0xbfff` | **2** |
| | everything else | | 0 |

We can also decode the two `IOWSR` words. 2.1/2.2 `0x0001` gives one wait
state to I/O `0x0000..0x1fff`. 2.3.x `0x0101` gives one to that block, and also one to `0x8000..0x9fff`.
That block contains port `0x8057`, which is the port that its first instruction
writes.

Software wait states apply only to **off-chip** accesses. A zero value gives no information,
because zero is also the value for a region that is not important. But a
non-zero field shows that the firmware expects external memory there. Thus:

- **The 2.1/2.2 boards put program `0x0000..0x7fff` off-chip**. This is exactly
  the range of the 30,172-word segment that the supervisor downloads
  (`0x0000..0x75d9`). The download is in external program RAM at `0x0000`.
- The 2.3.x boards need no wait states in program space. Instead, they put
  slow external memory in **data** `0x8000..0xbfff`. The two generations connect
  their external memory to different spaces.

This gives the answer for `MP/MC`. Table 8–3 says that microcomputer mode puts 4K of on-chip ROM
at program `0x0000..0x0fff`, where wait states have no effect. Two wait states
across `0x0000..0x3fff` have a function only with **`MP/MC` = 1**, with all
program space off-chip. For that reason, the default of the pin is now 1. The reason is not
convention. The flat program space that this harness always had is
correct, and now we know why.

In both cases, all builds in the tree have reset code in the vector area,
across five years and two product lines. It is not a special property of one
image.

### The memory map, now modelled

`PMST` contains `MP/MC`, `OVLY` and `RAM`. This core parsed all three and
did not use them. It now decodes both spaces through the map of the C52:

The regions are those of the C52, from tables 8–3 and 8–10, and not the general data for the
family. **The C52 has no SARAM**. Thus `PMST.RAM` and
`PMST.OVLY` have no effect on this part. Its data space is off-chip only from
`0x0800` and up, with two reserved gaps below that address.

| space | region | when |
|---|---|---|
| program | on-chip ROM, `0x0000..0x0fff` | `MP/MC` = 0 |
| program | DARAM B0, `0xfe00..0xffff` | `CNF` |
| program | external | otherwise |
| data | memory-mapped registers, `0x0000..0x005f` | always |
| data | DARAM B2 `0x0060..0x007f`, B0 `0x0100..0x02ff` (unless `CNF`), B1 `0x0300..0x04ff` | |
| data | external, `0x0800..0xffff` | always |
| data | reserved — `0x0080..0x00ff` and `0x0500..0x07ff` | |

`MP/MC` is a pin. An image does not record it. Thus the core gets it as an input,
and the default is 0. This is the level that this core always gave when the firmware
reads `PMST`, and the firmware does read it. `courier_c5x_set_mpmc_pin`
changes it. Over a run of 1.5 M instructions, both levels end at the same PC. Thus
the bit has almost no effect on behaviour, and it gives the accounting.

There is no on-chip ROM to put in the window, because no XMF contains one. When no ROM is
supplied, the window still answers from the downloaded image, as before.
The core counts these fetches. That count shows the size of the assumption.
Over a 12 M-instruction `ATA`:

```
program_external 13,843,991    program_rom 692,059    rom_holes 692,059
data_registers    1,176,533    data_daram 1,384,195
data_reserved       692,047    data_external 69,208
```

If a dump of the ROM of the C52 becomes available, `courier_c5x_load_rom` accepts it. Until
then, `dsp_bridge.dsp_memory_map` reports the mode bits, the wait-state decode,
the counts for each region and the hole count on each run.

Two of those counts are important.

`program_rom` is 692,059 also with the pin at 1. The reason is that the code writes zero to `PMST`
in the middle of the run. The same stores at `0xb626`, `0xb65f`, `0xb667`, `0xb677` and
`0xb67c` that set `IMR` and `IFR` to zero do this. This clears `MP/MC` and opens the ROM
window again under the running program. Firmware does not intentionally change the part from
microprocessor mode.

`data_reserved` is 692,047: **in each run, almost 700,000 data accesses go to the
reserved windows of the C52.** These are the frame-block cells `[0x00ca]` through
`[0x00cd]`, which hold the line-DAC source and the gate at the start of this section.
The C52 has nothing in the range `0x0080..0x00ff`. On silicon, those
addresses have no storage. This is an independent confirmation, from the
memory map of the part and not from behaviour, of the conclusion of the vector-table
search from the other direction: the addresses that the low bank calculates are
not at the locations that the code expects.

### Two core defects found on that path

- **TREG0 was not memory-mapped.** `LT` and the related instructions wrote `m_treg0`,
  but a data-space access to `0x0c` saw a cell that nothing updated. Its
  neighbours TREG1, TREG2 and DBMR were all mapped. We repaired this. It is not on the
  idle loop. Thus no result above changes.
- **The BIO pin is not implemented**. `GET_TP_CONDITION` always answers false for "BIO low".
  Thus each conditional instruction that tests
  it can never be true. There are 711 candidate sites in the image, including `0x0cc0`, a
  `CCD` a few words after the loop head. The code gets to none of them. A count of evaluated
  opcodes over a run, idle and with the gate forced, gives **zero**. Thus the TODO
  has no effect now. It becomes important when a new state gets to one of these sites.

## Datapump is present & readable — but needs human-driven RE

A decode of real code confirms that the DSP region contains real V.34/V.90
datapump code, for example at file `0x040F98`:
```
rptk B5h ; mac $4450,*0+,AR3     ; 182-tap MAC, coeffs @prog 0x4450
rptk B5h ; mac $5450,*0+,AR3     ; another 182-tap filter @0x5450
mac  $2756 ; blkp $CD2F ; macd $37C4 ; macd $28C4 ...
```
That is a **bank of 182-tap correlators / matched filters**: the equalizer /
DIL-correlation machinery. The `mac` coefficient tables (for example, file `0x320A0` =
prog `0x4450`) hold 182 signed values of large amplitude. This agrees with **DIL /
probing reference sequences**. It is a strong candidate for the DIL-correlation input.

**What automation cannot do here** (scope made smaller on 2026-09-05). The DSP load/base
problem below is **solved**. Refer to [How the DSP is loaded and run](#how-the-dsp-is-loaded-and-run)
for the descriptor table, the overlay map and the transfer protocol. The remaining tasks:
- Isolate the specific DIL/constellation-design routine. This task needs a person who can
  recognise routine boundaries, coefficient tables, and algorithm shape.
- ~~Identify what drains the supervisor's command queue~~. Done. Refer to
  [the queue consumer](#the-queue-consumer-and-the-0x58-0x5e-mailbox).

**Recommendation:** load `SV25.XMD` into **IDA** (it has a TMS320C5x processor
module) or Ghidra, region `0x29080–0x43700`, **little-endian** words, and analyze it
manually. Start from the FIR bank at `0x040F98` and the reference tables at prog
`0x4450/0x5450`. The region and the (now corrected) endianness are the reliable
part of this start. The verified code site, the candidate DIL tables and the
`c25dis.py` output all came from big-endian decoding. You must derive them again.
Alternatively, a live DSP dump from the modem avoids the base/overlay problem
completely.

## How the DSP is loaded and run

We found this on 2026-09-05. We made a diff of the two board captures (`artifacts/
courier-board-21210-capture-01`, supervisor 7.3.14 / DSP 3.0.13, and
`-capture-403`, 7.4.16 / 3.1.2), and we disassembled the supervisor with capstone in
16-bit mode. The diff makes it possible to check the results. The start of the DSP payload moved from
`0x29080` -> `0x29140` between the two. Thus each constant that points to DSP code
must also move, and each constant below does move.

**Segment `0x8000` maps linearly to physical `0x80000`, that is file offset 0.** Thus
`8000:e447` is file `0xe447`. This answers the "segment 0x8000 does not map
linearly" note at other locations in this file, at least for the DSP loader.

### The loader routines

These are file offsets. In 7.4.16, the full block moved **`+0x30`**.

| routine | 7.3.14 | 7.4.16 | job |
|---|---|---|---|
| `dsp_bootstrap` | `0xe370` | `0xe3a0` | `fff8` request, 8x `0x0083` window words, strobes 1 then 2 |
| `dsp_reset_entry` | `0xe3aa` | `0xe3da` | latch an address, pulse reset, poll for the ack from the DSP |
| `dsp_checksum` | `0xe447` | `0xe477` | 16-bit word sum of a payload range |
| `dsp_dl_win40` | `0xe46e` | `0xe49e` | bulk downloader, window `0x40` (**no callers**) |
| `dsp_dl_win50` | `0xe47b` | `0xe4ab` | bulk downloader, window `0x50` |
| `overlay_dispatch` | `0xe5d5` | `0xe605` | runtime overlay swap, table-driven |
| descriptor table | `0xe711` | `0xe741` | 6 bytes/entry, `cs:`-relative |

### Cold boot

Three sites do this (`0x47b`, `0x4ac`, and the reinit path at `0x7516`/`0x7567`).
All three use identical immediates:

```asm
call dsp_bootstrap
mov  ax, 0x8000        ; DSP entry word address
call dsp_reset_entry
mov  ax, 0             ; source offset within the DSP segment
mov  cx, 0xdd4e        ; source end   (0xd87c in 7.3.14)
call dsp_dl_win50
```

`dsp_checksum`/`dsp_dl_*` use `ax`/`cx` as byte offsets and calculate the word
count as `(cx-ax)/2`. Note: `mov ax, 0` disassembles as `ax, 0`, not `ax, 0x0`. A
filter that accepts only immediates with a `0x` prefix gets the *entry
address* from two instructions before, without a warning, and gives an incorrect source base.
We made that error during this analysis, and we found it.

### The overlay descriptor table

`overlay_dispatch` uses the **low nibble of the request byte at
`[0xe3c]`** as the table index, with stride 6:

| field | meaning |
|---|---|
| `+0` | source start offset in the segment of the overlay |
| `+2` | source end offset; word count = `(end - start) / 2` |
| `+4` | **DSP destination word address** |

The source segment comes from a hardcoded compare chain immediately before the
table. Indices 6, 7 and 8 each have their own segment. All other indices use
the DSP base segment. Entries 0-4 are zero, and 9-15 are after the end
of the real table (they decode as garbage. The table has 9 entries, 54 bytes).

**The map, 7.4.16** (7.3.14 in parentheses where it differs):

| idx | segment | flash range | words | DSP range |
|---|---|---|---|---|
| 5 | `a914` (`a908`) | `0x29140-0x36e8e` | 28327 (27710) | `0x8000-0xeea6` |
| 6 | `b6e9` (`b690`) | `0x36e90-0x3d0f4` | 12594 (11510) | `0x9d00-0xce31` |
| 7 | `bd10` (`bc2f`) | `0x3d100-0x40b94` | 7498 (7499) | `0xb000-0xcd49` |
| 8 | `c0ba` (`bfd9`) | `0x40ba0-0x44634` | 7498 (7350) | `0xdc00-0xf949` |

Entry 5 is the resident kernel. Its three fields are exactly the cold-boot
immediates. Thus **the cold boot is only overlay 5, sent through the other
transfer engine**. The code loads overlays 6, 7 and 8 on demand. They overlap
the resident range intentionally. Overlay 8 overlays the top of the kernel from `0xdf70` and up, and
continues after its end.

A request for overlay **6 chains to 8**. The dispatcher loads 6, then writes `8` to
`[0xe3c]` and goes back into the loader. Thus those two always come as a pair.

Four checks, all exact, in both images:
- entry 5 == the cold-boot immediates;
- the four images divide the payload with only 2-12 byte alignment gaps;
- overlay 8 ends exactly at the payload end (`0x44634`, and `0x436fc` in 7.3.14);
- the base of overlay 8, `0xdc00` + 880 words == `0xdf70`. Branch-target scoring independently gives the same value as the
  load base of the 3.1.2 tail at file `0x41280`.

The total growth before overlay 8 is `617 + 1084 - 1 = 1700` words. This agrees with
the `-1700..-1704` word relocation delta that we measured independently with a diff of the
payloads. **Most of the DSP 3.1.2 work is in overlay 6** (+1084 words), not in
the tail.

### The DSP receive side

We traced the host->DSP direction on 2026-09-05. Three facts control it:

**The resident kernel contains no `in` instruction.** A linear sweep of
overlay 5 finds `out` to DSP-side I/O `005e`/`005f` (the sender at `83d3`-`83de`)
and `0060` (the streamer emit at `849e`), but no port reads. The code does not poll the
mailbox through an I/O port. It reads it from **MMR `0x57`** through the
`23f0` accessor of the datapump, and a status bit gates it: `bit 15, @7d` in 3.0.13, `bit 14`
in 3.1.2.

**The interrupt vector table is not in flash.** The init at `0x8012` does
`apl @07, #07f8` and then `opl @07, #00b0` with `DP = 0` (set at `0x8004`, with no
`ldp` between). Thus `@07` is really PMST. Neither mask sets bits 15-11. Thus
those bits become clear. On the standard C5x PMST layout, that field is **IPTR**, which
puts the vector table at program `0x0000`. That address is outside all loaded overlays.
The supervisor never writes it. Thus the *first-level* mailbox ISR is in memory
that the flash image does not supply (on-chip ROM, or low memory that a different source fills).
The handler bodies below are in the loaded kernel. This is
the same low window that the DSP ROM probe samples as "thirty-two words at program
addresses `0x0000..0x001f`". It is directly the open C52 mask-ROM question.
The IPTR interpretation depends on the standard PMST bit assignment. We did not
confirm this assignment with a datasheet here. The masks are exact.

**Dispatch is a table-indexed computed goto**, and its base is *different for each firmware
build*. In 3.1.2, the chain at `0x839e` reads:

```
839e  lacl @7d          ; the received tag
839f  sub  #7f
83a0  retc gt           ; reject tag > 0x7f
83a1  add  #00008468    ; acc = tag - 0x7f + 0x8468 = tag + 0x83e9
83a3  tblr @7c          ; handler = program[0x83e9 + tag]
83a5  bacc
```

| image | DSP rev | table base |
|---|---|---|
| capture-01 | 3.0.13 | **`0x8401`** (pinned by `tests/test_dsp_window_stream.py`, 8/8 tags) |
| capture-403 | 3.1.2 | **`0x83e9`** (from the arithmetic above, 8/8 tags) |

We verified both. We read the table and checked that each entry goes to the
documented arm idiom: `ldp #007 ; retd ; splk @1e, #<stub>`, or `ldp #1ff` for
the tags that point `fff8`. **Do not use a table base from one build in a different build**. The two
bases are different by `0x18` words, and the handlers that they point to by `0x19`. If you compare
the table of 403 with the handler list of 3.0.13, you get a false uniform offset. We
made that error here, and we found it.

Thus the full receive path is: mask-ROM vector at `0x0000` -> kernel ISR -> read MMR
`0x57` through the `23f0` accessor -> tag into `@7d` -> `tblr` the dispatch table of the build
-> handler arms a streamer or does the command. The `0xff00`-framed pair
of the host (command, then destination) comes through this path. But **we did not
identify the kernel code that consumes a `0xff00` frame**. That claim is still open.

### Cross-check against the DSP-side streamer work

The handler addresses in `tests/test_dsp_window_stream.py` and
[the DSP ROM probe notes](docs/dsp-rom-probe.md) independently confirm the overlay-5 map, from the opposite direction.
We got those addresses when we executed
the datapump on the native C52 core, with no reference to a flash offset. Each
address in that table (`8401` jump table, handlers `8489`-`8678`, engine `8684`,
resume `847a`) is in the DSP range of overlay 5. When we read them through
`flash = 0x29140 + 2*(dsp - 0x8000)`, we get exactly the documented code:

- arm stub `8617` (tags 45/46/57) decodes as `splk *, #ff90 ; xc 2, tc ;
  splk *, #ff00`. This is the runtime `ff90`/`ff00` selection on `tc` that the probe
  notes describe. This is almost a signature. It is not a coincidence.
- handler `8489` decodes with `lar ar1, #030f`, and its stub `848d` with
  `lar ar1, #031c`. These are two of the six live call-state cells in the list for tag `06`.
- stub `8642` (tag 47) decodes with `splk *, #0019`. Stub `8665` (tag 73) decodes with
  `splk @79, #f992`, adjacent to the documented `f993` source for tag `78`.

Caveat for that last group: a *linear* decode that starts exactly at a labelled stub
address is not always aligned on an instruction. The reason is that some stubs are in `retd`
delay slots (the probe notes also record this). Thus some count immediates are
one word off. This confirms the addressing, not each count. The emulator run in the probe notes
gives the counts.

### The dial-digit handoff

We traced this on 2026-09-05. The answer has two parts. Do not mix them.

**In the emulator, digits do not go through the mailbox.** A differential run shows
this: `ATDT111` and `ATDT999` on `main211.xmf` give **byte-identical** mailbox
streams (1628 messages, the same seven tags, the same counts, the same arguments, the same
order). But the line audio is correctly different: 451 windows detect `1`, and
452 detect `9`. The tap operates correctly. The digits are not on that path.
We know the cause, and this file records it at another location: `begin_dialing`
in `courier_emu/bridge.py` calls `core.set_dtmf_digits`. This gives the digits
directly to the C52 and bypasses the dial code of the supervisor. That is the
board-side model that replaces the unrecovered handoff. Thus this result gives
no information about the real firmware. It only proves that the model bypasses the path.

During dialing, the mailbox carries a **periodic service exchange**. In each
cycle, there are three of `{0x01, 0x0f, 0x84}` and one of `{0x82, 0x83, 0x67}`. The cycle repeats
about 135 times. A plain `AT` control run sends the same seven tags with the same
arguments and only 12 messages. Thus the cycle is also not specific to dialing.

**In static analysis, the real handoff looks like mailbox commands `0x20`/`0x21`.** In
the 7.4.16 capture:

| file | role |
|---|---|
| `0x22250` | dial-mode entry A: `[0xd74] = 0`, `[0x3bd5] = 8` |
| `0x22254` | dial-mode entry B: `[0xd74] = 2`, `[0x3bd5] = 0` |
| `0x21f49` | emitter reached from A |
| `0x21fa0` | emitter reached from B |

Both emitters run the same selector. Thus the mode cell selects the command:

```asm
mov  ax, 0x20
test byte [0xd74], 2
jne  .send
mov  ax, 0x21          ; mode 0 -> command 0x21, mode 2 -> command 0x20
.send:
mov  bx, cs:[si]       ; per-call parameter
mov  [0x2bc], bl
mov  [0x2b4], bl
lcall 8f46:01e4        ; the three-word {0xff00, tag, arg} sender
```

Four sites in the dial code in segment `0x9efe` call the two entries:
`0x20f14`, `0x20f70` (entry A) and `0x20fa5`, `0x213d5` (entry B). Each site
gives a far callback pointer (`mov dx, cs` with `si = 0x1be` or `di = 0x24f`.
Both offsets are code, not tables) and a selector in `ah`. Only three locations write
an immediate to `[0xd74]`: those two entries and `0x0b80f`.

**This is a candidate, not a proof**. An attempt to execute it failed, but
the failure gave useful information. We know that `0x20`/`0x21` are the DSP
commands for each dial mode on the dial path. We also know that neither occurs in an emulator run. The tap
saw only `0x01`, `0x0f`, `0x67`, `0x7d`, `0x82`, `0x83`, `0x84`.

#### The firmware never reaches that code, and removing the injection does not help

The same selector is in each image. Thus we can follow the site across the images:

| image | selector | mode cell |
|---|---|---|
| capture-403 (7.4.16) | file `0x21f72`, `0x21fb8` | `[0xd74]` |
| capture-01 (7.3.14), `IDSDL302.ROM` | file `0x21e92`, `0x21ed8` | `[0xe88]` |
| `main211.xmf` | file `0x46555`, `0x4659b` (physical `0x86555`) | `[0x2006]` |

We disabled `core.set_dtmf_digits` and ran `ATDT123` on `main211.xmf` again.
This confirmed that the bypass was active (one interception, `'123'`). Nothing
else changed: the same 1628 messages and the same seven tags, no `0x20`/`0x21`.
The DTMF audio stopped (451 detections of `1` became one false window).

That is a definite negative result, and you do not need a PC hook to see it. Between the
selector and the `lcall` that sends the message, there is **no branch out**. The
`jne` skips one instruction. Thus if the code gets to the selector, it sends the message.
Thus no `0x20`/`0x21` on the wire means that the firmware never got to `0x86555`.

The reason is that the interception is not at `begin_dialing`. The bridge
parses the AT command text (`courier_emu/bridge.py`, `text.find("D")`,
remove `T`/`P`, keep only dial characters), seizes the DAA, and supplies the detector
window. The model does the dialing at the **DTE-command level**, above the mailbox
and above the dial sequencer of the firmware. Thus the firmware never gets a request to dial, and
`set_dtmf_digits` is only the audio half of a larger replacement.

Thus, for tones that the firmware generates, the dial must be modelled at the line, not at the
command parser. The supervisor must drive the DAA. This is not a one-line
change. Until then, `0x20`/`0x21` stay a static candidate. We did not execute the code that shows what the `cs:[si]`
parameter is, or if one message carries one digit.

Note: tags `0x82`, `0x83` and `0x84` are more than the `0x7f` limit of the DSP dispatcher. Thus
they are not dispatch tags, and we do not know their meaning. They are the
only traffic in the service cycle that we cannot explain.

### What the dial sequencer is waiting on

We traced this on 2026-09-05 on `main211.xmf` with `ATDT123`. We used range-limited
`UC_HOOK_CODE` probes, which we installed with a wrapper around `Uc.hook_add` (the machine adds its
own hooks in `run`, thus there is no other extension point). We first validated each probe below
on a region that we know is active. The same harness, when it monitors the
mailbox consumer, records 102,272 instructions. It records `0x6ad5b` 816 times,
`0x6aea5` 812 times and the three-word sender `0x6b05f` 25 times.

**The code never enters the dial code.** Zero instructions execute in
`0x85000`-`0x87000`. There are 25 far-call sites in other parts of the image that
target that region, and **none of them executes**. The firmware gets to the `main-loop`
milestone and stays there.

**But the AT handler does arm the dial.** Two cells are different from a plain `AT`
control run:

| cell | `ATDT123` | `AT` |
|---|---|---|
| `[0x298]` | `0x1d9f` | `0` |
| `[0x1cf0]` | `1` | `0` |

`[0x298]` holds a **near** callback pointer. The code reads it at `0x5beb3` with
`CS = 0x5b5e`, which resolves to physical **`0x5d37f`**. A probe over that
routine shows that it **never executes**. Thus the sequencer is armed, but it never
continues.

(Note: `supervisor_call_cells` in a run result is the *final value* of each cell.
It is not a count of calls. `"0298": 7583` is decimal `0x1d9f`, the pointer.)

**What it waits for.** The DAA state at the end of the run:

```
operation=dialing  off_hook=True  line_state=dial-tone
detector_qualified=True   dial_tone_present=False   dial_tone_qualified=False
```

The five-hit detector of the supervisor is satisfied (`detector_qualified`). But
the dial tone is not present and it is never qualified. The design of the model causes this. The
behavioral DAA supplies 350+440 Hz only for sufficient time to qualify the detector.
Then it **removes the central-office tone and starts the parsed digits on the C52
directly**. Thus the condition that would advance the armed callback never occurs,
and the firmware waits without end while the model completes the call without it.

This is the full scope of the replacement. It is not one bypass, but three
layers: the bridge parses the `ATD` text at the DTE level, the DAA simulates the
line transition, and `set_dtmf_digits` supplies the audio. If you remove only the
third layer, you get silence. An earlier experiment showed this.

**To get to `0x20`/`0x21`, model the line, not the call.** Specifically:
keep the dial tone present and qualified until the firmware removes it, let the armed
callback at `CS:0x1d9f` run, and do not inject digits. Then the sequencer runs,
the code gets to the dial-mode entries, and we can observe if `0x20`/`0x21` carry one digit for each
message. We do not have to infer it. We do *not* know
which code calls the callback, or what exact predicate it
tests. We know only that the callback is armed, that the code never enters it, and that dial-tone
qualification is the state that the model does not supply.

### Two transfer engines

The cold boot and the runtime swap use different hardware paths:

| | cold boot (`dsp_dl_win50`) | runtime (`overlay_dispatch`) |
|---|---|---|
| data latches | `0x40-0x4e`, alternating with `0x50-0x5e` | `0x40-0x46`, then `0x48-0x4e` |
| commit strobe | `out 0x18, 1` / `out 0x18, 2` | `out 0x1e, 1` / `out 0x1e, 2` |
| checksum | `out 0x18, 4`, poll bit 2 | none |
| finish | poll `in 0x18` bit 2 | `out 0x1e, 4` |
| preemptible | no | yes. Tests `[0xe3c]` again for each group |

Runtime state bytes: `[0xe3c]` request (low nibble = index. Nonzero = pending.
Cleared on completion), `[0xe3b]` watchdog countdown (`0xc8` at start, `0xfe`
after ack), `[0xe39]` checksum accumulator, `[0xe36]`/`[0xe37]` boot-downloader
window selector.

### What actually loads DSP RAM

Nothing loads a DSP *ROM*. The on-chip mask ROM of the DSP **is** the loader. Each
word that comes from flash goes into DSP **program RAM**:

1. `dsp_reset_entry` latches the destination address through ports `0x40`/`0x42`.
   It clears bit 1 of the GPIO word at `[0xff56]`, writes `0xffff` to `0x18`/`0x1a`
   and `0x1c`/`0x1e`, and waits for `0x1f4` loops. Then it toggles `[0xff56]` bit 1 again to
   release the reset.
2. Then it polls `in 0x1a:0x18` and `in 0x1e:0x1c` for `0xffff`/`0xffff` (an
   **acknowledgement from the DSP**), and answers `out 0x1c, 2`.
3. Only after this does the supervisor stream code.

Step 2 is the important observation. A device on the DSP already executes
and answers *before the supervisor sends one word of firmware*. Thus the responder
must be on the chip: mask ROM or hardware bootstrap. The supervisor never writes DSP
program memory directly. It gives words to that resident responder, which puts
them at the address from step 1. The destination addresses are `0x8000-0xf949`,
that is program space. The evidence shows that the kernel executes from `0x8000`.

For runtime overlays, the DSP already runs. Thus the destination comes
as a **mailbox message**, not through the reset latches. `overlay_dispatch`
loads the destination into `bx` and calls `8f43:0224` (file `0xf654`) with
`ax = 2`. This puts three words, `{0xff00, 2, dest}`, into a 24-word
circular queue at `0x29e-0x2cc` (head `[0x29a]`, tail `[0x29c]`, initialised at
`0x1dce`). Then the bulk words follow through the port-`0x1e` engine.

### The queue consumer and the `0x58`-`0x5e` mailbox

We found this on 2026-09-05. We searched for *writes to the queue head* `[0x29a]`. The
producer advances the tail. Thus only the consumer changes the head. The search found 14
sites: the initialiser at `0x1dce`, three copies of a two-word drainer
(`0xf521`, `0x12cbb`, `0x139bc`), two single-word variants that run in interrupt context
(`0x12d99`, `0x13ab4`. Both end with `mov [0xff02], 0x8000` (the 80188 EOI
register) and then `iret`), and a helper at `0xfd77` that removes one word from the queue or fails.

The handoff goes through a **staging word at `[0x289]`**. Its idle sentinel is
`0x7f3f`:

```asm
mov  ax, 0x7f3f
xchg [0x289], ax       ; take whatever is staged, mark the slot idle
cmp  ah, 0x7f
je   idle              ; nothing was staged
cmp  ah, 0xff
jne  send_single
call 0xf521            ; high byte 0xff -> two-word drainer
```

This is the function of the `0xff00` word that the overlay dispatcher puts in the queue: **a frame
marker. The staging logic consumes it and never transmits it**. It selects the
two-word drainer. The drainer sends the remaining two words of the message (the command and
the destination) as a pair:

| queued word | destination |
|---|---|
| `0xff00` | consumed as a frame marker, not sent |
| command (`2` for an overlay load) | low byte `out 0x58`, high byte `out 0x5a` |
| DSP destination address | low byte `out 0x5c`, high byte `out 0x5e` |

Usual traffic (high byte not `0xff`) goes one word at a time, through
`0x58`/`0x5a` only. When the staging slot is idle, `0x11f49` fills it again from
the queue through `0xfd77`. `0xfd77` returns carry set when head == tail. Bit 0 of `[0x285]` gates the full pump.
The ISR sets this bit from `in 0x1e`/`in 0x1c` bit 2. This bit is
the "I can accept a word" signal of the DSP.

This also shows that `0x5c`/`0x5e` is **bidirectional**. The code writes it here as the
high half of a host->DSP message. The code at file `0x13d00` reads it (high byte `0x5e`,
low byte `0x5c`) as DSP->host status. The byte order is the same in both
directions: low byte on the even port, high byte on the odd port.

Thus the destination address goes to the DSP as mailbox word 2 of a `0xff00`-framed
message. The resident kernel, which already runs, receives it. Then it puts the
overlay words that follow through the port-`0x1e` bulk engine.

## The supervisor's time base is not driven

The timeouts of the supervisor use a chain of countdowns that one routine
services: the routine decrements each of `[0x15b]`, `[0x15d]`, `[0x174]`, `[0x738]`, `[0x73a]`, `[0x742]`,
`[0x84f]`, `[0x1d74]`, `[0x2d4]` and `[0x32d]` one time in each
pass. For some of them, it makes a call when they become zero. The chain entry is
`5b5e:0b1a` (physical `0x5c0fa`), which is the handler on **vector 0x0f**:
INT3 on the 80186.

In a payload run, that routine never executes. `ATI11` shows this:
`0x62d63` sets `[0x328]`, `0x62d68` arms `[0x32d]` with 20 ticks, and
`0x62d6d` loops until the flag clears or the count becomes zero. The
command is designed to stop correctly. With no tick, it waits without end, and
the page stops after "Modulation". `ATI10` stops in the same way.

A periodic edge on vector `0x0f` does complete both pages, but it is
incorrect. The interrupt controller shows that `int3` is **masked** for the full run,
while `int0` and the timer are unmasked. Thus the board cannot
accept that edge. If we inject it, the call behavior changes: two linked instances answer
`OK`, but a run without the edge reports `NO CARRIER`. `NO CARRIER` is the
correct answer for an `ATA` with no modelled DAA. Thus the harness
obeys the mask. It does not send an edge on vector `0x0f` while `int3` is masked.
`ATI10`/`ATI11` stay unfinished. A fabricated edge does not finish them.

For some time, the DSP interrupt looked like the real source. Vector `0x0c`
(INT0, unmasked) enters at `0x6ad00`. It starts with code that looks like a divider:
`inc byte [0x176]`, a compare with 25, and when the count gets to 25,
`mov byte [0x66c], 0x80`. A trace of that flag gives the answer, and it does not support
the hypothesis. `[0x66c]` bit `0x80` is a watchdog alarm, not a tick.
No code tests it to decide if the chain runs. Refer to "The two
handlers watch each other" below. The chain still has exactly one entry, the
masked vector.

### The mask is set at boot and never cleared

The mask on `int3` does not come from a condition that the harness does not satisfy. The setup table of the peripheral
control block, which the `out` at
`0x5ba06` writes one word at a time, masks it directly:

```
out 0xff1e = 0x000b     INT3 control: priority 3, MSK (bit 3) set
out 0xff08 = 0x0068     IMASK: INT0, INT2 and INT3 masked
```

Nothing writes these registers again. After the block moves into memory,
the firmware changes only `0xff16` (DMA1), `0xff18` (INT0, ten times) and
`0xff1a` (INT1). It never changes `0xff1e` or `0xff08`. In the full image, the only accesses
to IMASK after boot are two read-modify-writes, at `0x5f3b5` and
`0x7a619`. Both are `or ax, 0x0004`: they set the DMA1 bit and keep the bit
of INT3.

The handler also has no other entry. A sweep of each byte for `rel16`
references across its full 64 KiB segment finds no `call` and no `jmp` to
`0x5c0fa`, and none to the second prologue at `0x5c178`. Only a vector can get
to it.

The register offsets here are from the **80C186EB/EC** map, not the map of the original
80186: IMASK at `+0x08`, the interrupt controls at `+0x18`..`+0x1e`, timer 0
at `+0x30`..`+0x36`, and the chip selects at `+0xa0`..`+0xa8` as start/stop
pairs. This is the shape that `rom.py` decodes from the reset stub. Arithmetic confirms the base `0xff00`:
the code writes the max count of timer 0, `0x7e00`, to
`0xff32`, and that is the 32,256 that the timer model reports as `compare_a`.

### The one enabled periodic source is a stub

Timer 0 *is* unmasked, and it fires: 2,842 timer interrupts in a run of 14 M
instructions. Its handler, vector `0x08` at `5b5e:1246` (physical `0x5c826`), is:

```
0x5c826   c70602ff0080   mov word ptr [0xff02], 0x8000    EOI
0x5c82c   cf             iret
```

It acknowledges and returns. Thus the payload has no active periodic service.
The source that connects to the countdown chain is masked, and the source that is enabled
has no effect.

### The same table is in every image here, including a boot block

The cause is not an update payload without its boot block. The
identical setup table is in each Courier firmware in the tree, with the
same `1eff 0b00` entry:

| image | table at |
|---|---|
| `main211.xmf`, `3453Bv2.1.1.xmf` | `0x1b908` |
| `main2205.XMF` | `0x1b928` |
| `MAIN_2.3.12/15/31.XMF`, `2_3_33.XMF` | `0x17ed8` |
| `IDSDL302.ROM` | `0x326` |

`IDSDL302.ROM` is a complete flash part, and `0x326` is in its boot block.
Thus the boot block also masks INT3. This did not change from 2.1.1 through 2.3.33, and it is the same
in two products. The two images share only this table. The
byte-identical window around it is 62 bytes (−40..+22). Two entries immediately
outside it are already different: `[0xff70]` is `0x8102` in the ROM and `0x814f`
in `main211`, and `[0xff60]` is `0x8082` and `0x80a7`. The registers are the same, and the values are
specific to the board. Only the interrupt configuration does not change.

For comparison, the **386** payload of the ISDN Courier has all the items that this one does not have.
`Ie030002.nac` initialises the 8259 pair and accepts 2,894 delivered interrupts
in a run of 20 M instructions. It programs all three 8254 counters as mode 2 rate
generators at 641.5 Hz, 133.6 Hz and 33.4 Hz, and it runs VRTX on them, with
5,822 `int 0x30` kernel calls in the same run. That is an example of a live time base on
this hardware family.

### The two handlers watch each other

`[0x66c]` is a bitfield, not a flag. 335 accesses in the image use each
bit from `0x01` to `0x80`. Both interrupt handlers write bit `0x80`,
and each handler writes it when the *other* handler has stopped.

The tick side is at `0x5c18f`, in the countdown chain:

```
test byte [0x1fb9], 1
jne  0x5c1b2                 ; the check is switched off
cmp  byte [0x176], 0
jne  0x5c1b2                 ; a DSP interrupt arrived this tick, so all is well
inc  byte [0x177]            ; otherwise count consecutive silent ticks
cmp  byte [0x177], 3
jb   0x5c1b7
mov  byte [0x66c], 0x80      ; three silent ticks: raise the alarm
or   byte [0x1fb9], 2
0x5c1b2:  mov byte [0x177], 0
0x5c1b7:  mov byte [0x176], 0    ; and reset the DSP counter every tick
```

The DSP side is the divider above: `inc byte [0x176]`. When it gets to 25
and no tick has cleared it, the same `mov byte [0x66c], 0x80` occurs. Thus the
tick sets the alarm when the DSP stops, and the DSP sets it when the
tick stops. The bit has no timing information. It means "the other handler has stopped".
The code that waits uses it as an abort. `0x5dbe0` tests it immediately
before the detector wait, and jumps to the timeout at `0x5dc53` when it is set.
There are about a hundred `test byte [0x66c], 0x80` sites.

In this harness, that watchdog is always tripped. Only `0x5c1b7` clears `[0x176]`, and
`0x5c1b7` is in the handler that never runs. Thus the byte counts without limit,
and for 231 of each 256 counts it is at or above 25. Over an `ATDT` run of 30 M instructions:

| site | executions |
|---|---:|
| `0x6ad00` INT0 entry | 6,618 |
| `0x6ad11` `mov byte [0x66c], 0x80` | 5,969 |
| `0x5c0fa` INT3 entry | 0 |
| `0x5c1b7` `mov byte [0x176], 0` | 0 |

Nine of ten DSP interrupts set the alarm. The instruction is a `mov`, not an
`or`. Thus each of those approximately 6,000 stores also clears bits `0x01`..`0x40`. These are six other
flags that hundreds of sites in the image read and write. The masked
interrupt does more than stop the countdowns. Because it is absent, a shared byte
becomes corrupt several thousand times in each run. Consider this effect when you interpret behaviour
from a run.

### What the mask costs

The last action of the handler before its EOI is a call into the DAA:

```
0x5c69d   e86c1d         call 0x5e40c
0x5c6a0   9af900d06a     lcall 0x6ad0, 0x00f9
0x5c6a5   ff16dd06       call word ptr [0x6dd]
...
0x5c6b6   c70602ff0080   mov word ptr [0xff02], 0x8000
0x5c6bc   cf             iret
```

`0x5e40c` is a prescaler: `inc [0x642]`, a compare with `[0x640]`, and on
wrap, `call word ptr [0x65e]`. It drives the state chain that is armed at `0x5db6c`
(period 3), `0x5dbb2` (4) and `0x5dc11` (20). Those states send `0x7c00` and
`0x8000` to the board and consume the replies. The replies come as mailbox tags:
`0x7c` into `[0x285]`/`[0x283]` and `0x7e` into `[0x281]`. `[0x285]` has three bands:
zero / `1..0x60` / above `0x60`. The low band increments `[0x649]`.
This is the five-hit detector byte that the originate contract above uses.

Thus the replacements in the harness do not replace a missing device. `[0x649]`,
`[0x8d6]` and the `[0x14e]`/`[0x152]` delay pair are all counters that this one
handler services. The harness forges them because the interrupt that would service
them is disabled. An accurate drive of `int3` would make all of these replacements unnecessary
together. Also, the forged `[0x649]` keeps the poller from
running. Thus no run has sent a `0x7c00` request or received a `0x7c` reply yet.

`[0x289]` is **not** part of that list, but an earlier revision of this
section put it in the list. Its servicer is active. Refer to the text below.

### Two clocks, not one

The code decrements each countdown above at exactly one site. For all countdowns except
one, that site is in the masked handler. A scan of the full image
for `inc`/`dec` on each of them gives a single exception:

```
[0x289]   sites in the INT3 handler: 0    elsewhere: 1  (0x6ade5)
```

`0x6ade5` is in the tail of the **DSP** interrupt, vector `0x0c`. This vector is
unmasked, and it runs:

```
0x6add3   cmp word [0x161], 0
0x6add8   je  0x6adde
0x6adda   dec word [0x161]
0x6adde   cmp word [0x289], 0
0x6ade3   je  0x6ade9
0x6ade5   dec word [0x289]
0x6ade9   pop es ; popaw
0x6adeb   mov word [0xff02], 0x8000     EOI
0x6adf1   iret
```

That handler advances exactly three items: `[0x176]`, the watchdog counter
above, and the two countdowns `[0x161]` and `[0x289]`. Nothing else.

`[0x289]` is the detector wait. It is armed at `0x5db8d` and tested at `0x5dbe7`. It is
the interval that the originate path waits on the line. Thus it is on
a **live** clock, and each run now advances it. Over the same 30 M
`ATDT` run as above:

| site | executions |
|---|---:|
| `0x6ade5` `dec word [0x289]` | 6,616 |
| `0x6adda` `dec word [0x161]` | 0 (never armed on this path) |
| `0x5dbe7` the detector wait's compare | 15,416 |
| `0x5dc4a` that wait timing out | 0 |

`[0x161]` is also a real timer. Eleven sites arm it and fourteen sites
compare it. A dial does not use it.

This division agrees with the board better than one time base: the
tick does the supervisor housekeeping, and the DSP frame interrupt does the tasks that
must follow line time. It is also evidence that the countdown chain is
really dormant in these builds, and not only something that the harness
does not trigger. The reason is that the parts of the firmware that must keep line
time are not on it.

### Pacing the chain from the DSP interrupt

If the DSP frame interrupt keeps line time, the next test is clear:
let it also pace the countdown chain. Send vector `0x0f` one time for each DSP
interrupt, and monitor the result in the firmware. This is now available as
`--tick-source dsp`, disabled by default, on both `run` and `link`.

It runs, and the consistency check of the firmware confirms this:

| site | with the tick paced | before |
|---|---:|---:|
| `0x5c0fa` INT3 entry | 6,691 | 0 |
| `0x5e40c` the poller | 6,691 | 0 |
| `0x5c1b7` `mov byte [0x176], 0` | 6,691 | 0 |
| `0x6ad11` the watchdog stamp | **0** | 5,969 |

The mutual watchdog stops its alarms for the first time. This is not an accident. Its two
limits *set the permitted ratio*. The DSP interrupt must come at least one time
in three ticks, or the tick side sets the alarm. The tick must come at least
one time in twenty-five DSP interrupts, or the DSP side sets the alarm. Thus the number of ticks for each DSP
interrupt must be between 1/25 and 3, and 1:1 is in that range. The firmware gives the range.
The firmware does not give the choice of 1:1 in the range. That choice is still a
guess.

Downstream, events that had never occurred started to occur. The host-to-board
traffic now included `0084:3100` (the revision-gated register write at `0x5e551`),
and also `0080:0000` and `007c:0000` (the `si` read and the detector request).
With the forged `[0x649]` still in place, `ATDT5551234` answered `OK`. All
previous runs answered `NO CARRIER`.

When we removed the forgery, we got useful information. The poller sent requests and
nothing answered. The firmware reported `NO DIAL TONE`. This is the correct answer for
a line that it cannot hear, and the firmware got it through its own code, not through our code.
Then we answered `0x7c00` with a value in the `1..0x60` band. This increments
`[0x649]` through the path of the firmware for the first time.

Both parts of this are now in the tree. The bridge answers the detector
request each time that the DAA has a signal on the line. `dsp_bridge`
`detector_replies` counts these answers: 44 in a linked run of 40 M instructions. When
the chain is paced, the two forgeries of the harness are disabled together. The harness does not
write `[0x649]` at `0x5dbe7`, and it does not set to zero the `[0x289]` wait in which that count runs.
The reason is that the firmware controls both after the poller is active. Then a linked
pair leaves command mode. It changes the DTE callback table from `acdf,1fce,a8d9`
to `50ad,18e3,4cac`, and answers `OK`. `OK` is not a call result code, and the
line is still silent on both sides. Thus the supervisor operates
on state that the harness supplied. These are not two modems that trained.

### What parks the state chain

It does not get to five hits, and the reason is not a stall. State `0x3023`
(physical `0x5e603`) is only a `ret`. It is an idle state that does nothing, and the code
points the chain at it intentionally. Of 1,657 dispatches in that run:

```
3023 (idle ret)          1,644
2e44 send 0x7c00             3
2e53 send 0x8000             3
2e62 consume [0x285]         2
2f5a gate block              2
2eb7 send 0x7c00 (loop B)    1
2ec6 send 0x8000  (loop B)   1
2ed5 consume      (loop B)   1
```

Thus the chain armed, went through both request/consume loops, and then
stopped in the idle state. Fifteen sites write `0x3023` into `[0x65e]`. Two of them cause
this: `0x65512`, the main loop of the supervisor, and `0x5dbfa`, immediately after the
detector wait. The chain **applies only during a line operation**. The code arms it at
`0x5db6c`, `0x5dbb2` and `0x5dc11` when a line operation starts. It parks it immediately when the wait
ends or the supervisor goes back to its command loop.

That is correct behaviour, and it moves the remaining problem. The window closed
because the detector never qualified. The pacing is not incorrect. In
the window, the chain got about twelve dispatches and got one low-band value
in two consume passes. The reason is that a reply that goes into the queue when the request is written
is possibly not visible when the consume state runs next. Thus the remaining
problem is the delivery timing. It has the same shape as the `0x02`/`0x03`
handshake that the bridge already models: a reply must be on the bus when
the consumer polls. It is not sufficient to put it in the queue. Otherwise, five hits in the 500-decrement
window is easy: at 1:1 with a prescaler of 3, they need about
fifteen dispatches.

This does not show two items. The 1:1 ratio is a choice in the permitted
band, not a measurement. Also, the experiment used revision `0x33`. With the
default 4, the gate at `0x5e547` fails and `0084:3100` never occurs. Thus the
revision question is now important. It is not only cosmetic.

### Why this is the blocker for placing and answering calls

Most of the items that a call needs are downstream of this one interrupt. The qualification of the
response after a seizure is the `[0x649]` path. Ring qualification is the
`[0x647]`/`[0x648]` debounce on the ring bits of tag `0x7e`, counted against the
S-register at `[0x92a]`. The pre-dial interval is `[0x8d6]`. Call progress goes
through the same `[0x65e]` state chain. The handler on
the masked vector services all of these. At each item that the harness forges, the
firmware stops to show us what the board would do. Instead, it shows us what we
gave it.

The exception makes the problem smaller in a useful way. The wait of the originate path
on the line, `[0x289]`, is on the live clock. Thus not all of the call path is
dark. In a wait that already operates, the missing item is the counter for which the wait
waits. Thus `[0x649]` is the only counter between the current state
and an originate that runs fully under the control of the firmware.

We tested four explanations for the mask, and we closed three. It is not
a condition that the harness does not satisfy: nothing in the image writes the register
a second time. It is not an incorrect reading of the register map: the max count of timer 0
confirms the base. It is not an update payload that depends on the work of a boot block:
the one complete flash ROM here masks it in its own boot block. The remaining explanation
is that the countdown chain is dormant in all builds that we have, and that the
shipping modem keeps time at a location that we did not examine. These images alone cannot
answer this. A RAM or state dump from a physical Courier
(already the item with the highest leverage under "Possible next steps") would answer it
directly: read `[0x176]`, `[0x177]`, `[0x66c]` and the mask of the interrupt controller
on a running modem, and the answer is clear.

But the pacing experiment above makes one interpretation of that less probable. If the chain
were vestigial in these builds, it would give nonsense when it runs.
Instead, it put both watchdogs into their healthy state, sent the register write
that its revision gate requests, and answered a dial through its own code. That
is not proof that the board drives it from the DSP frame. It shows only that no other
configuration that we tried here satisfies the consistency checks of the firmware.

## The DTE front end the harness stands in for

A payload run does not have the UART front end of the board. Thus the harness
installs its callbacks at the main-loop milestone. We recovered four more parts of that
same contract when we operated a live console:

- **Attention prefix.** `0x65f03` receives the assembled line, and the harness
  removes the `AT`/`at` prefix there. The other half of the contract was
  missing: a line with no prefix went through without change. Thus `I3` ran as
  `ATI3`. The terminator advances the command state for all input,
  because that state machine is downstream of the detector. Thus a completed
  line without the prefix now goes back to command-line-ready, and the harness does not call the
  parser: no result code, nothing executed. `A/` and `A>` are the
  two-character forms of the detector, and the harness does not change them.

- **One command line at a time.** The state machine publishes itself as the
  callback pointer at `0x02ac`. `a8d9` collects a line one character at a time.
  The terminator advances it to `a910`, which parses and prints. The
  end-of-command path at `a8b1` clears the collector and goes back to `a8d9`.
  Bytes that come in the `a910` window go into a buffer that nothing
  parses. The type-ahead flag of the firmware at `0x1cf2` carries a line to the next state,
  and the front end sets it. When the harness holds input until
  `a8d9`, a second and third command answer.

- **Collect versus keystroke.** At `0x662d0`, the receive path tests the
  collect flag `0x1cee` bit `0x40`. If it is armed, the path adds the byte to the command buffer at
  `0x1cf5`. If it is clear, the path goes to `0x662d7` and sets bit `0x20`. A
  running command waits on this flag for a keystroke. The help pages loop on that flag:
  `test byte [0x1cee], 0x20`, nine sites in `main211`. One of them is the
  `0x73824` loop for "Strike a key when ready". If the harness arms the collector for
  each delivered byte, those keystrokes become command text and the pager
  never continues.

- **A reset builds the table again.** `ATZ` loads the profile again and writes the
  callbacks again with the defaults for no board. When we installed the replacement only one time,
  the DTE did not respond after `ATZ`. The next typed byte entered the receive ISR at
  `0x5d5b0`, went through the null callback into the fatal entry at
  `5b5e:0000`, and flashed error `0x0b` for the remaining session.

Echo is part of the same layer. The setting is `[0x092d]`. `ATE0`/`ATE1`
change it, and the `no-echo` option switch keeps it clear at `0x63e93`. Thus the
harness echoes from the byte of the firmware, not from its own flag.

## The parameter flash service the update image does not carry

`AT&W` assembles a sector image in RAM. Then it calls the boot block through
`int 0x0a` with an ASCII service letter in `BL`:

| service | meaning |
|---|---|
| `E` (0x45) | erase the 4 KiB sector selected by `ES` |
| `W` (0x57) | program the word in `AX` at `ES:DI`, then advance `DI` |
| `S` (0x53) | firmware-update path |
| `L` (0x4c) | block lock/select |

The writer at `0x7dfa8` does a blank check of the destination at `0x7e0e3`: 2,048
words against `0xffff`. If that check fails, it erases. Then it writes the assembled
image one word at a time. An update payload has no boot block. Thus each of
those calls goes to a vector that does not exist, and `AT&W` stops on the first call.
The harness answers `E` and `W` with a modelled part. `S` and `L` still
stop the run. The harness does not continue on a guess.

The firmware itself checks that the answers agree with the part. The sector
that it writes passes the CRC that `parameters.py` calculates independently. Its own
reader finds the value again after a new boot. Repeated stores rotate the
four sectors and erase one to wrap. No program tries to set a bit in
a word that is not erased.

`ATY15` is not missing. This store gates it. `0x8339f` tests
`[0x0a03]` bit `0x04` before the code can get to the `cmp al, 0x0f` case.
`0x7e05c` loads `[0x0a03]` from sector offset `0x04` (type1) only
when flags bit 3 of the sector is clear. With a sector of that type, the
command prints the factory switch page. That page reports all ten option switches.
It is an independent check of the board model.

## Emulator core corrections

We found two defects in the C52 core when we followed the serial path:

- **Indirect addressing modes 8 and 9 were missing.** The ARU field is bits
  6-4, and bit 3 selects the ARP update. Thus `100` is `*BR0-`, the
  bit-reversed form. The service overlay gets to it at program `0xe581` after
  the serial port answers a transmit-ready poll, and the core stopped completely
  there. The core had `*BR0-` at modes `0x6`/`0x7`, which that encoding
  reserves.
- **The serial port had no status bits.** `SPC` read back exactly the written value.
  Thus `XRDY` and `RRDY` never set, and a transmit handshake could not complete.
  The core now answers them from the state of the port.

## Possible next steps

1. **Live RAM/state dump from the physical modem** (highest leverage): if the
   Courier has a memory-peek / debug-monitor function, a dump of segment
   `0x8000` (RAM) gives the resident code directly. A dump of DSP program RAM
   during a V.90 handshake gives the *active* overlay. This avoids the full
   static bank-mapping problem. Probe the debug AT commands that this firmware
   supports (USR has some undocumented commands).
2. **Interactive disassembler + human loop**: load the flash into IDA/Ghidra (IDA
   has a TMS320C5x module) and resolve the boot/bank config manually. Start from
   the verified banner anchor and the port `0x19/0x3E` I/O. This is slow RE
   in many sessions. It is not possible to automate it here, because of the decode-anything problem.
3. **Mine the DSP data tables** (possible now): most of the datapump region is
   data. Extract the constellation/interleaver map (`flash 0x3B780`) and the
   coefficient tables. They describe the constellation machinery, and you do not need
   code RE for them.
4. **Correlate live** (a connected call is necessary): compare `ATI6`/`ATI11` Timing/Carrier
   Offset + echo with our DIL timing. This tells clock-recovery problems from constellation
   rejection.
5. **Answer as the DAA at the ASIC boundary**: find what the C52 reads
   once for each frame from external I/O `0x50` at program `0x8c1f` (the code that
   consumes it, and the bits that it tests). Then drive it from the line model.
   Do not let it float high. The datasheet fields above give the contents of that
   status. The eight supervisor latches at `0x40`..`0x4e` are the other half of the same
   boundary. The firmware writes each of them about 15,000 times during a dial.
6. **Trace the tick**: find how `[0x66c]` bit `0x80`, which the DSP interrupt sets
   each 25 entries, gets to the countdown chain at `0x5c0fa`. That would give
   the supervisor a time base from the source that the board has. With
   it, each firmware timeout would operate, including the `ATI10`/`ATI11` pages.

## Complete flash ROM — `IDSDL302.ROM`

This is a 1998 512 KiB ROM dump of a Courier V.Everything **external** (`$USR0100\\MODEM\\
PNPC107\\Courier V.Everything EXT`, copyright through 1998). It is the full
part, not an update payload. Thus it answers some questions that `main211.xmf`
could leave only as modelling choices. `courier-emu rom-info` recovers all of it
from the image.

### The image places itself

The last sixteen bytes are the 80186 reset vector. The stub there programs
the chip select that decodes the ROM, and then it jumps:

```asm
ffff0  cli
ffff1  mov dx, 0xffa4        ; UCS start, 80C186EB chip-select unit
ffff4  mov ax, 0x8000
ffff7  out dx, ax
ffff8  jmp far 0xfc00:0x1a21
```

Thus the ROM occupies `0x80000..0xfffff`, and the boot block entry is at
physical `0xfda21`. Then the boot stub replays two setup tables (36 word
writes and 9 byte writes). These give the remaining map:

| register | value | meaning |
|---|---|---|
| `0xffa4`/`0xffa6` | `0x8000`/`0xffce` | flash `0x80000..0xffc00` |
| `0xffa0`/`0xffa2` | `0x0000`/`0x200a` | RAM `0x00000..0x20000`, 128 KiB |
| `0xffa8` | `0x10ff` | peripheral control block relocated into **memory** at `0x0ff00` |

That last row is important: the harness already hooks memory
`0xff00..0xffff` as the peripheral control block, and here the firmware
programs that relocation itself.

The byte table sets the initial values of the board latches. Two of its values are exactly the values that
the boot of the 2002 firmware writes: port `0x12` = `0x7f`, port `0x14` = `0xf5`.

### The boot block the update image does not carry

`main211.xmf` starts at the application. The ROM has about 6 KiB above it, at
`0xfbff0..0xfda69`, that the update never replaces. This code does these steps, in sequence:

1. programs the peripheral control block from the two tables,
2. copies its own 0x1975 bytes to physical zero (the first 0x400 bytes of that
   block are an interrupt vector table, thus the copy installs the vectors and the
   code together), and enters through `int 0x13`,
3. polls input port `0x10` bit `0x08` with a timeout, and then bit-bangs the
   Microwire settings EEPROM,
4. calculates the CRC-16 of the full flash, one segment at a time,
5. jumps into the application at `0x80000`.

The CRC routine at relocated `0x03e0` is the same per-byte CCITT update
that we recovered from `main211.xmf` at `0x72930` and implemented in
`courier_emu/parameters.py`. This is confirmed across builds that are four years apart.

Step 3 changes a claim that we made from the update image alone. `main211.xmf` has no
NVRAM profile load at boot. But the code that reads the
EEPROM at power-on is in the boot block, and an XMF update does not contain the boot block.
When we boot this ROM with the EEPROM model of the emulator, it reads word 0,
finds `0xffff`, and programs it to `0x0000`. This is the initialisation of a part that
is not configured.

A second `SDL Xmodem file transfer` copy is at `0xfc1db`, in the boot
block. A recovery loader must be at this location.

### The parameter sectors are the top of the same part

The search at `0x7e07c` reads four 4 KiB sectors from `0xf8000`. In this image,
all of them are erased. Thus a dumped image cannot supply a parameter sector.
The manufacturer writes it for each unit. The ROM does show that the
region is not a separate part. It is the top of the same flash, immediately
below the boot block.

### Cross-build confirmation of the board model

The ROM has the same latch driver, and the code calls it in the same way (`mov ax, mask << 8 |
index; call`), with the same index encoding: read entry at `0x827d1`,
set/clear at `0x82771`/`0x8279b`, shadow read at `0x82750`. This ROM also reads each board input
that the 2002 firmware reads:

| signal | `main211.xmf` | `IDSDL302.ROM` |
|---|---|---|
| identification strap sense | 5 sites | 5 sites, same mask/index |
| board option input `0x80`/port `0x10` | 1 site | 1 site |
| DTR, port `0x12` bit `0x40` | 3 sites | 3 sites |
| carrier-detect switch, port `0x14` bit `0x04` | `0x5e3cf` | `0x82876` |

The carrier-detect handler has an identical structure: the same mask, the same shadow
bit `0x20`, the same flag bit (equivalent to `[0x652]`), and the same setting byte cleared to
zero for `&C0`.

The option switches are at different locations. This build reads seven of them from one
port (index 3, masks `0x01`, `0x02`, `0x04`, `0x08`, `0x10`, `0x20`, `0x80`).
The 2002 firmware puts the same functions on ports `0x10`, `0x12`,
and `0x14`. We matched them by the value that each one writes:

| function | ROM port/mask | `main211.xmf` port/mask |
|---|---|---|
| result codes displayed | `0x12` `0x01` | `0x14` `0x20` |
| numeric result codes | `0x12` `0x02` | `0x10` `0x02` |
| auto answer off (S0) | `0x12` `0x04` | `0x14` `0x10` |
| echo off | `0x12` `0x08` | `0x12` `0x10` |
| quiet in answer mode | `0x12` `0x10` | `0x12` `0x08` |
| DTR override (S14) | `0x12` `0x20` | `0x12` `0x20` |
| quiet, capability-gated | `0x12` `0x80` | `0x12` `0x80` |
| carrier detect forced on | `0x14` `0x04` | `0x14` `0x04` |

Two are on the same pin in both builds, and each row has one identical function.
Thus this is independent confirmation of the function of each switch. It is not a
switch numbering. The bit order of the ROM also does not follow the published switch
numbers. Thus a physical unit is still necessary to find which position on the case drives which pin.

### Booting it

`courier-emu run IDSDL302.ROM` boots the ROM from its reset vector. The harness detects the image
type from the file. The ROM maps at the location that its own chip select gives.
The harness dispatches real-mode software interrupts. Thus the boot block can
enter through the vector table that it installs at physical zero.

The peripheral timers are modelled from the instruction clock. This lets
the ROM pass its self-test:

```asm
80432  mov word ptr [0xff46], 0xc000   ; T2CON: enable
80438  mov word ptr [0xff42], 0        ; T2CMPA: a zero compare is 65,536
8043e  mov word ptr [0xff40], 0        ; T2CNT
80444  test word ptr [0xff46], 0x20    ; wait for MAX COUNT
8044a  je 0x444
```

The model includes the enable gate (the timer accepts a new ENABLE only when INHIBIT is
set in the same write), the rule that a zero compare is the full range (this self-test
uses it), single-shot versus continuous, and the sticky max-count bit. It
also includes the mask side of the interrupt controller, which is
important. The boot table writes `IMASK = 0x0079`, which masks the timers. If
a timer interrupt goes through that mask, it goes to a handler that is
consistent only later in the sequence.

### The system tick is calibrated from an external interrupt

With the timers modelled, the ROM continues to a different wait, at `0x80a52`:

```asm
80a52  push ax
80a53  mov ah, byte ptr [0x12a]        ; the tick byte
80a57  add ah, al                      ; al = how many ticks to wait
80a59  cmp ah, byte ptr [0x12a]
80a5d  jne 0xa59
```

Nothing advances that byte. The reason is that this firmware does not run
its tick from a fixed timer period. `0x9eb73` starts timer 1 as a
stopwatch with a 54,166-tick timeout and unmasks INT1. Then the INT1 handler at
`9ea4:0722` does the calibration:

```asm
9f162  mov word ptr [0xff46], 0xe001   ; T2CON: enable, interrupt, continuous
9f169  mov ax, word ptr [0xff38]       ; timer 1's count - the measured interval
9f16c  rcr ax, 1
9f16e  and ax, 0x7fff
9f171  add ax, word ptr [0xff38]       ; one and a half times it
9f175  mov word ptr [0xff42], ax       ; T2CMPA: the system tick period
9f178  mov word ptr [0xff12], 0        ; unmask the timer interrupt
9f183  mov word ptr [0xff3e], 0x6001   ; stop timer 1
9f189  mov word ptr [0xff1a], 8        ; mask INT1 again
```

Thus timer 2 is the tick. Its period is one and a half times the time until the
first INT1 edge comes. We do not know what drives INT1 physically.
`--int1-after MS` supplies one edge as a harness stimulus, in the same way that
`--ring` supplies the ring cadence. With it, the sequence runs: timer 1 stops
with a count, timer 2 is programmed, the timer interrupt is unmasked, and a
timer 2 tick comes through vector 19.

Then two items stop it before the tick runs. A trace shows both:

- The measured interval is about 45,000 ticks. One and a half times
  that value is more than sixteen bits. Thus the tick period becomes 2,112 ticks, not
  the intended value. The interval depends on the time that the firmware keeps
  interrupts disabled after it starts the stopwatch. Here, that is about 10,000
  instructions. The accuracy of this value depends on an instruction-to-time
  ratio that we calibrated with the 2002 build, not with this build.
- Code at `0x8e3e6` and `0x8e487` uses timer 2 again as a scratch delay (enable,
  zero compare, poll max count). This clears the interrupt bit that the tick needs.
  On hardware, some device must put those in sequence with the tick. We did not
  recover which device.

We intentionally did not change the XMF path. An update image enters at the
application, after the boot block that programs the control block. The calibrated helpers of the harness
already supply its delays. If the model answers its
timer reads instead, its own timer interrupt service routine goes
on a path from which it does not return. The harness still records its writes. Thus a run now
reports what it programs: compares of 32,256, 40,624, and 65,535 on the three
timers.

## The application CRC the loader verifies

We recovered this from `IDSDL302.ROM` and verified it numerically. This is the value of
the `Calculating CRC...` step of the loader. It is the modem-side value that the DOS downloader
reports through `ERROR(%02d) Modem reports bad CRC`. It is also the check that decides
if the modem accepts a downloaded image.

| Property | Value |
|---|---|
| Algorithm | reflected CRC-16/CCITT, poly `0x1021` (reflected `0x8408`), init `0xFFFF`, no final XOR |
| Catalogue name | CRC-16/MCRF4XX (check `0x6f91` over `"123456789"`; the same routine with init `0x0000` gives KERMIT's `0x2189`) |
| Region | flash `0x40000..0x77FFD`, i.e. `0x37FFE` bytes |
| Stored as | little-endian 16-bit word at flash `0x77FFE` |
| Verification | `IDSDL302.ROM` computes `0x53bc`; the word stored at `0x77FFE` is `0x53bc` |

Code anchors. All are bank offsets in the recovery loader at flash `0x7C000`. (Add
`0x80000` to get the physical address that the harness reports, because the reset
stub of the ROM maps it at `0x80000..0xFFFFF`.)

| Bank offset | Role |
|---|---|
| `0x03e0` | byte-wise CRC update; state in `cs:[0x104]` |
| `0x0a75` | loads and prints the `Calculating CRC` string at `0x0231` |
| `0x0a83` | `call 0x14ce` |
| `0x0ab0` | `mov cs:[0x104], 0xffff`: sets the initial value of the accumulator |
| `0x0fdb` | phase 1: segments `0x8000..0xB000`, full 64 KiB each |
| `0x1052` | `mov cs:[0x104], 0xffff`: resets the accumulator before phase 2 |
| `0x1059` | phase 2: segments `0xC000..0xF000` |
| `0x1060` | `mov cx, 0x7ffe`: the walk of the `F000` segment stops two bytes early. Thus the stored word is not in the CRC |
| `0x1090` | `cmp ax, es:[si]` with `ES=0xF000`, `SI=0x7FFE`: compares the calculated value with the stored value |

The update step at `0x03e0` is a byte-swapped form of the reflected CCITT
update. It is not a table lookup:

```
mov di, ax              ; preserve caller AX; AL is the input byte
mov dx, cs:[0x104]      ; DX = running CRC
xor al, dl              ; AL = byte ^ (crc & 0xff)
mov dl, al
mov ah, 0               ; AX = t, zero-extended
shl ax, 4               ; DX ^= t << 4
xor dx, ax
shr ax, 1
xchg dl, dh             ; byte-swap the accumulator
xor dx, ax              ; DX ^= t << 3
shl ax, 4
and ah, 7               ; AX = (t << 7) & 0x7ff
xor dx, ax
shl ax, 1
xor dl, ah
mov cs:[0x104], dx
```

This gives two corrections to earlier notes:

- **`0x14ce` is not a mailbox dispatch.** It sets `ES=0x8000` and writes `0x00f0`
  to `es:[0]`. With the mapping of this ROM, segment `0x8000` is physical
  `0x80000`, which is the base of the flash array. `0xF0` is the AMD/Fujitsu
  `Am29F0x0` reset command, which puts the device back into read-array mode. Thus the code puts
  the flash back into a readable state immediately before the CRC walk reads it.
- **Segment `0x8000` is not RAM in this image.** We dumped physical
  `0x80000..0x8FFFF` after a harness run of 40M instructions. The bytes are identical to
  `IDSDL302.ROM[0:0x10000]`, with zero differences. The "segment `0x8000` = the
  64 KiB RAM" model is part of the XMF analysis, where the update payload maps at
  `0x40000`. It does not apply to a complete flash part that maps itself at
  `0x80000`. The code that we saw execute at `pc=0x804db` is ROM at file offset
  `0x4db`. It is visible in static analysis at all times.

Caveats. We verified the CRC on exactly one image, and no other image here
can confirm it. The region also assumes that the code takes the phase-2 path through `0x1052`.
But a numerical match over a `0x37FFE`-byte region is probably not
a coincidence.

**No update image contains this field**. This fact is the most useful evidence
about it. We checked twelve images. The ten `.XMD` payloads all hold `0x0000` at flash
`0x77FFE`. The two sparse flash images that `tools/unpack_sdl.py` reconstructs
from `SDL_CS2.EXE` and `SDL_7666.EXE` hold `0xFFFF` (erased) there. In them, the CRC
region is 98% empty, because those C51-era packages load to flash
`0x00000..0x3C000`, fully below the region. We scanned each trailer position in
all ten `.XMD` payloads, for both a `0x40000` and a `0` start. We found no
self-consistent CRC. The number of hits is at or below the approximately 8
coincidences that chance gives from 524,288 positions at 1-in-65,536. The
one repeated pair (`SDL0430` and `SV_49` at `0x7d24e`) is one coincidence
that we counted two times, because those two images are different only below `0x40000`. The same scan
gives `('0x40000', '0x77ffe', '0x53bc')` on `IDSDL302.ROM`. Thus it does find
the field when the field is present.

This supports, but does not prove, this theory: **the modem calculates this CRC after
it programs the flash, and it writes the CRC to `0x77FFE` itself**. Thus the CRC is only in a flash part
that was programmed and read back, never in a download payload. This
agrees with the fact that `IDSDL302.ROM` is a dumped part. It also agrees with the address snooper
at `0x0e90`, which latches values for `F000:7FFE`. We did not trace the write path that would
prove it. If the theory is correct, only another dumped ROM can
confirm the CRC. No update image can.

You do not need an emulator to calculate it. Use the routine above exactly as written,
start with `0xFFFF`, and run it over `rom[0x40000:0x77FFE]`. The result is the stored
word.

## `ATI1` and the ATI dispatch table

The documentation says that `ATI1` is "the ROM checksum". It is **not** the download CRC above.
Do not mix the two. On the 20.16 MHz unit, `ATI1` reports `1A11`,
and the download CRC of that image is `53BC`. But they cover the *same*
region. Thus each one confirms that boundary for the other.

### Reference hardware

We probed two Couriers over serial to get these values. Both report
`ATI0` = `5607` and supervisor `7.3.14` / DSP `3.0.13`, dated 03/13/98:

| Unit | `ATI7` Clock Freq | `ATI1` | Matching image family |
|---|---|---|---|
| 20.16 MHz, US/Canada External | `20.16Mhz` | `1A11` | `IDSDL302.ROM` (contains `20.16Mhz`, no `25 Mhz`) |
| 25 MHz, US/Canada External | `25 Mhz` | `49E2` | `SV25.XMD` family |

`ATI7` on the 20.16 MHz unit agrees with `IDSDL302.ROM` on each field that it prints.
Those strings are in one template block at `0x1a97a..0x1a9be`: `20.16Mhz`
(108922), `512k` (108951), `7.3.14` (109069), `3.0.13` (109086), and also `03/13/98`
(4197) and `US/Canada` (131118). This shows that the ROM is the correct *build*
for that unit. It does **not** show that the flash contents are identical.
Refer to the open question at the end of this section.

### The dispatch table

This is a table of 16-bit near offsets at file `0x25D9B`, immediately after the
`[ ACCESS DENIED ]` string. The entries for commands that are not implemented are `0xFFFF`. The
bank base is `0x24D20`. We found it from the known location of the `ATI0` handler at file `0x25E05`.
That code tests bit `0x20` of `[0x089d]` to select one of the inline strings
`5607` and `3367`. This is the same product-code selector that we found before at
`0x82e7d`.

| Index | Offset | File | Index | Offset | File |
|---|---|---|---|---|---|
| `ATI0` | `0x10e5` | `0x25e05` | `ATI8` | `0x120b` | `0x25f2b` |
| `ATI1` | `0x1104` | `0x25e24` | `ATI9` | `0xffff` | — |
| `ATI2` | `0x1122` | `0x25e42` | `ATI10` | `0x10c1` | `0x25de1` |
| `ATI3` | `0x114e` | `0x25e6e` | `ATI11` | `0x10ca` | `0x25dea` |
| `ATI4` | `0x109d` | `0x25dbd` | `ATI12..14` | `0xffff` | — |
| `ATI5` | `0x10a6` | `0x25dc6` | `ATI15` | `0x10d3` | `0x25df3` |
| `ATI6` | `0x10af` | `0x25dcf` | `ATI16` | `0x10dc` | `0x25dfc` |
| `ATI7` | `0x10b8` | `0x25dd8` | | | |

A probe of `ATI0..ATI16` on the 20.16 MHz unit returns `OK` for
`0,1,2,3,4,5,6,7,10,11,15` and `ERROR` for `8,9,12,13,14,16`. That agrees with the
`0xFFFF` pattern of the table on 15 of 17 entries. `ATI8` and `ATI16` have handlers,
but a runtime gate stops them. The hardware pattern gives the
alignment of the table. If you read the table from an incorrect offset, you get a table that looks
correct but is incorrect. Thus use the support pattern to confirm again each similar
table that you find in another image.

`ATI4`, `ATI5`, `ATI6`, `ATI10`, `ATI11`, `ATI15` and `ATI16` are 9-byte stubs of
the form `mov bx, 0x3560; call far 0x971b:0x59ce; ret`. `ATI7` has the same shape
and the same `BX`, but it calls `0xc800:0x000c` instead. `BX` holds the *same
constant* in all eight. Thus it is not the report selector. The value that selects
the report comes through a different path (most probably the parsed command
number in a variable). We did not find it.

### The `ATI1` routine

The handler of `ATI1` at file `0x25E24` is a thin wrapper:

```
push cx
lcall 0x8000:0x9e11     ; CRLF
lcall 0x8000:0x0836     ; compute the checksum, result in AX
lcall 0x8000:0x9d76     ; print AX as four hex digits
lcall 0x8000:0x9e11     ; CRLF
pop cx
ret
```

Segment `0x8000` is the ROM base (physical `0x80000`). Thus `0x8000:0x0836` is file
offset `0x836`. `ATI2`, the RAM test, calls the adjacent `0x808`.

The routine at `0x836` is a far wrapper around `0x83a`. `0x83a` sets `BX` to zero and
calls the helper at `0x860` one time for each segment `0xC000`, `0xD000`, `0xE000` and
`0xF000`. Then it returns `BX` in `AX`. The helper reads `0x8000` words (64 KiB) in each
segment. For `0xF000`, it loads `CX` with `0x3FFF`, thus it stops two bytes
early. It reads each word with `lodsw`, and `xor dx,dx; xchg dl,ah` divides the word into its
low byte in `AX` and high byte in `DX`. It adds both to `BX`. There is no
CRC and no final transform:

> **`ATI1` = (sum of every byte over flash `0x40000..0x77FFD`) mod 2^16**

The region is identical to the region of the download CRC, and it also stops two bytes early
at the end of the `0xF000` segment.

### Open: no image reproduces a unit's `ATI1`

The sum of `IDSDL302.ROM` is `0xBD4A`, and the 20.16 MHz unit gives `1A11`. The sum of
`SV25.XMD` is `0x4828`, and the 25 MHz unit gives `49E2`. Also, none of the ten
`.XMD` payloads agrees with either unit. Two explanations are still open:

1. The summed region contains data that is different for each unit (a serial number, country or
   configuration bytes). In that case, `ATI1` is always different for each unit and
   can never validate a generic image. `SV25.XMD` is within 442 of its unit.
   This agrees a little with this explanation, but byte-sum distances are not reliable
   evidence.
2. The images are really different from the flash contents of the units.

It is easy to find which explanation is correct: find the location of the serial number (`0009540034268322`
on the 20.16 MHz unit). If it is in `0x40000..0x77FFD`,
explanation 1 is confirmed, and you cannot use `ATI1` for image validation.

Until we know the answer, read `ATI7` agreement as "same firmware build",
not "same flash contents".

## Why a ROM run emits nothing: the tick chain

A `courier run IDSDL302.ROM` gives no serial output. The cause is not
the UART model. In 40M instructions, the code enters the character emitter at `0x8000:0x15f0`,
the hex-word printer at `0x9d76` and the newline routine at `0x9e11`
**zero** times each. The firmware never tries to print, because the boot never
gets to that point.

The stall is in a delay routine at `0x8000:0x0a52`:

```
mov ah, byte ptr [0x12a]   ; tick counter
add ah, al                 ; target = now + N
cmp ah, byte ptr [0x12a]   ; spin until reached
jne  -6
```

Five entry points at `0x0a40`, `0x0a44`, `0x0a48`, `0x0a4c` and `0x0a50` select
delays of `0x14`, `5`, `4`, `2` and `1` ticks. When the counter does not change, the compare
never succeeds. The two instructions at `0x0a59`/`0x0a5d` execute 17,233,307 times
each, about 85% of the full run.

The full counter chain:

| Step | Evidence |
|---|---|
| `[0x12a]` is incremented at `0x0ae5` (`inc word ptr [0x12a]`) | the only such instruction in the image |
| `0x0ae5` is in the ISR that starts at `0x8000:0x0a70` (`sti; cld; pushaw; push es`) | — |
| That ISR is installed on IVT vector `0x0F` | emulated IVT: `0x0f -> 8000:0a70` |
| The harness gates this edge on its `int3` source | `SOURCE_CONTROL[0xFF1E]` in `timers.py` |
| The boot block masks INT3 | `OUT 0xFF1E, 0x000B` at `pc=0xfda3e`. `0x08` is the mask bit |
| The harness obeys the mask and does not send the edge | `machine.py`, the `enabled("int3")` guard |

Nothing else can get to the ISR. The image contains no `INT 0Fh` instruction, no
near call or jump to `0x0a70`, and no stored far pointer to it (the single byte
match for `70 0a 00 80` at file `0x3f1` is in unrelated code).

**The mask handling of the harness is correct here. The observation
that this firmware masks INT3 is also correct.** Two errors are easy to make. We record them because both used
much time:

- **Access to the peripheral control block is through I/O port space, not memory.**
  The firmware programs it with `OUT`. Thus a Unicorn `UC_HOOK_MEM_WRITE` over
  `0xFF00..0xFFFF` sees nothing, and it looks as if the firmware never writes registers such as
  `0xFF1E`. Use the I/O hooks, or `io_events`, to see them.
- **The part is an 80C186EB, not an original 80186, and its peripheral layout
  is different.** The timers are at `0xFF30..0xFF46` and the interrupt controller is at
  `0xFF08..0xFF1E`. The original part puts the timers at `0xFF50` and the
  interrupt controller at `0xFF20..0xFF3E`. Thus `0xFF3E` here is the control register of timer 1
  (`0xE001` = EN|INH|INT|CONT), *not* INT3 control, and `0xFF1E` is
  the int3 control register, not a timer. The map in `timers.py` is correct.
  Do not read these addresses with an original-80186 datasheet. This error is
  easy to make two times.

**Open question.** We did not confirm the vector assignments of the EB
here. Thus we do not know if IVT vector `0x0F` (where the tick ISR is
installed) is really the source that has its mask at `0xFF1E`. If, on this part,
vector `0x0F` is for a different, unmasked source, then the gate of this edge on
`int3` is incorrect. That would explain why the emulated boot stalls but real
hardware does not. Find the answer in the 80C186EB documentation before you change
`machine.py`. The guard there is intentional, and the XMF paths depend on it.

### What forcing the counter shows

When a code hook advances `[0x12a]` artificially, the spin decreases from 17,233,307
executions to 384. Then the boot runs to completion. It gets to the main service
loop, where `0x9237` calls `0xb3bc` and `0xb402` in turn, about 781,000 times, and idles
normally. Thus the machine is much closer to correct operation than "no serial output"
shows. One counter that does not change causes all of the silence.

In that state, it still prints nothing, because nothing gives it input. The code never consumes queued serial
input. With `--serial-input-hex 415449310d` (`ATI1\r`), the run
ends with `serial_input_remaining: 5` and `serial_interrupts: 0`. Serial input
delivery is a second, independent gap.

### The second gap: the serial front end is XMF-only

The tick is necessary, but it is not sufficient. When the boot runs to the
main service loop, a ROM run still prints nothing and still consumes no input.
`serial_interrupts` stays `0` and all queued bytes remain (`--serial-input-hex
415449310d` ends with `serial_input_remaining: 5`).

The cause is a scope limit in the harness, not a defect. The serial
front end in `machine.py` is set up only for XMF images:

| Component | Keyed to | Reached by a ROM? |
|---|---|---|
| arming triggers `0x65F03`, `0x65D42`, `0x5CE66`, `0x5CE6A` | XMF payload mapped at `0x40000` | no. A ROM maps at `0x80000` |
| arming writes `0x1D26`, `0x1CEE`, `0x2AC` | XMF supervisor RAM layout | no |
| `ready_callback` `0xA420` / `0xA7A0` / `0xA8D9` | `_alternate_supervisor` / `_supervisor_23`, both derived from `supervisor_offset` | no. `CourierRom` does not have this attribute |

Thus `_serial_started` never latches, and the interrupt injector never runs.
We confirmed this directly. On `IDSDL302.ROM`, `_serial_started` is `False` before and
after a run of 20M instructions, `serial_interrupts` is `0`, and all five input bytes
are still in the queue. The same fact explains the only two reads of port `0x00` in such a run:
the firmware never gets to the point where it would poll the UART.

Thus "a ROM run emits nothing" has **two** independent causes, not one: the
tick that does not change (refer to the text above), and this. Interactive AT operation on a ROM image is not implemented.
It is not broken. We built the ROM path for boot and CRC analysis, and it
does these correctly. To support AT operation, port the front end: arming triggers at ROM
addresses, and the ROM equivalents of those three RAM variables and the
parser callback.

### The ROM's own serial front end

To port the front end, the ROM-side equivalents of the XMF variables above are necessary.
We found them.

**Character sink.** `0x8000:0x15f0` is the primitive that sends one character (`AL` holds
the byte). Its send path continues to `0xf11a`, which is not a UART write.
It is a gated buffer append:

```
test byte ptr [0xea7], 1     ; output enabled?
stc / je   ret               ; no -> discard the character, return carry
cmp  byte ptr [0x3424], 1    ; mode gate
stc / jne  ret
mov  bx, word ptr [0x3ca4]   ; output write pointer
mov  byte ptr [bx], al
inc  word ptr [0x3ca4]
clc / ret
```

Thus `[0xea7]` bit 0 and `[0x3424] == 1` gate all output, and `[0x3ca4]` is the write
pointer. On a harness run, both gates are clear (`00` and `00`). Thus the code discards each character
without a message.

This is **not** an independent fault. Exactly one instruction in the image sets
that bit: `or byte ptr [0xea7], 1` at file `0x2171f`. A run of 20M instructions
never executes it, and it executes no instruction in the routine around it. The gate is
downstream of the boot stall. If the boot gets sufficiently far, the firmware opens the gate
itself. Thus a silent ROM run has two causes, not three: the tick that does not change, and the
input path that is only for XMF.

**Init state machine.** The function pointer at `[0x298]` dispatches it
(`call word ptr [0x298]` at `0xf564`). Each state puts a command word into a
ring buffer through `0xf65c` (write pointer `[0x29c]`, read pointer `[0x29a]`, buffer
`0x29e..0x2cd`, wrap at `0x2ce`, carry set when full). Then it waits
some ticks and advances `[0x298]`. With the tick forced, a run gets to
`[0x298] = 0x0150`, and the ring write pointer advances to `0x02a6`. Thus the
sequence does progress. Only the tick stops it.

**Receive side.** The timer 2 ISR (vector `0x13`) assembles input one bit at a time.
It reads `[0xff5a]`, rotates, and shifts the bit into `[0xb59]` (`rcl al,3` and then
`rcr byte ptr [0xb59],1`). It branches when a full byte has shifted through. Timer 1
(vector `0x12`) calls the periodic service at segment offset `0x133`.

**Tick calibration.** Vector `0x0D` (INT1, which `--int1-after` sends)
is the calibration ISR. It sets the control of timer 2 (`[0xff46] = 0xE001`), calculates a
compare value from the count of timer 1 (`[0xff38]`) and stores it to `[0xff42]`. Then it
writes `[0xff12] = 0`, which unmasks the timer. This is the "external interrupt that
calibrates its tick" in the docstring of `InterruptController`. We now know its location.

### Why boot still stops short: the settings EEPROM

With the tick supplied (`--tick-ms`), a ROM run boots past the delay loops and
idles in its main service loop. But it still prints nothing. The reason is not a
stall. The firmware has no valid configuration, and it correctly does not open its
DTE port.

The chain. We confirmed that each step executes:

1. `0xe2e9` calls the settings reader nine times to fill the nine-word block at `0x752`.
2. `0xe237` decodes one setting. It uses the pointer table at `0xe2a0`, reads a
   three-byte record, and validates it.
3. On failure, it returns carry. At `0x0923`, the boot does `mov al, 3; call ...;
   jb skip; mov [0x695], al`. Thus a failed read leaves `[0x695]` at zero.
4. At `0x216f2`, `test byte ptr [0x695], 1` gates the full block that ends in
   `or byte ptr [0xea7], 1` at `0x2171f`. This is the instruction that opens output.
5. When `[0xea7]` bit 0 is clear, the emitter at `0xf11a` discards each character.

In a harness run, the block at `0x752` reads back as all zeros, all four validation
calls fail, and output is never enabled. `--nvram` and
`--parameter-sector` do not help, because neither supplies this path.

**The chip is the chip that the harness already models, but a different driver gets access to it.**
`nvram.py` models a 93C66 (256 x 16 Microwire) on board latch 0, I/O port `0x10`.
This is the driver that an XMF uses (`5b5e:1801`). The driver of the ROM, at `0x1401`, bit-bangs
the 80C186EB port pins instead:

| Signal | Register and bit |
|---|---|
| chip select | `0xff56`, bit `0x20`. Asserted one time and held |
| clock | `0xff56`, bit `0x04`. Data is clocked on the rising edge |
| data pin direction | `0xff58`, bit `0x80`. Cleared to drive, set to sample |
| data to the chip | `0xff5e`, bit `0x80` (the port 2 latch) |
| data from the chip | `0xff5a`, bit `0x80` (the port 2 pin register) |

These are one bidirectional data line on port 2 pin 7, not separate DI and DO
pins. The driver writes it through the latch while `0xff58` bit `0x80` is clear.
Then it sets that bit and samples the same pin through `0xff5a`. The bit numbers are
`0x80` and not `0x01`. `rol al, 1` / `rcl bx, 1` moves the *top* bit of the port
byte. A quick reading of the routine can give the opposite order. For each command bit, the
driver writes the data bit, sets `0x20`, raises `0x04`, and then lowers it.

It clocks 12 bits out (`cx = 0x0c`) and 16 bits in (`cx = 0x10`): a dummy `0`, the
start bit, opcode `10`, and eight address bits. This is a standard 93C66 read.

**Address mapping.** The code builds the command word as `ax = 0x0600 | index` and then
`rol ax, 4`, where `index = (di - 0x696) / 2`. Thus RAM is a copy of the EEPROM from
`0x696`:

```
eeprom word = (ram address - 0x696) / 2
```

Thus the settings block `0x752..0x763` is EEPROM words 94..102. Those 18
bytes hold six three-byte records. The table at `0xe2a0` selects them:

| Setting | Record | Setting | Record |
|---|---|---|---|
| 1 | `0x761` | 4 | `0x758` |
| 2 | `0x752` | 5 | `0x75b` |
| 3 | `0x755` (gates output) | 6 | `0x75e` |

The records are obfuscated, not plain. The decoder at `0xe237` applies
`ror 2` / `add 5`, `rol 1` / `sub 0x0f`, and `xor 0x1d`. Thus you can
make valid records if you do those steps in the opposite order.

Thus, for a ROM run to get to its banner, two items are necessary: a second front end for the existing 93C66
model on those four pins, and words 94..102 filled
with correctly encoded records. A blank EEPROM reads zeros, which is exactly the
state that fails now.

### The unresolved part

The boot block masks INT3 early. Thus, if the delay at `0x0a52` really ran before
a later step unmasked it, real hardware would stop at exactly the same location.
But it does not stop: the reference 20.16 MHz unit boots and answers `AT` normally.
Thus the probable interpretation is **not** a defect in interrupt delivery. It is an
earlier divergence: the emulated boot gets to a delay call before the tick source
is enabled. A forced counter hides that divergence. It does not repair
it. The open task is to find the branch where the emulated path leaves the hardware path.
This is possible, because a working unit is available for comparison.

### Incidental confirmation of the CRC region

The same runs confirm the application CRC boundary again, from an independent
direction. During power-on, the ROM calculates its own checksum with the routine that it copied into
low RAM. Addresses `0x3e0` and `0x106a` each execute exactly 229,374 times, which
is `0x37FFE`. This is exactly the size of the region `0x40000..0x77FFD` that we recovered from
the loader.

## Older C51 SDL package and V.8 frame path

The DOS `SDL_49.EXE` stores firmware in 16-byte records. Each record is followed by a checksum,
a `0x10` marker, and a 24-bit address token. `tools/unpack_sdl.py` removes that
framing, joins continuation runs, decodes the `02 00 00 02` load
descriptor of each module, and reconstructs a sparse 1 MiB flash image. The C51 resident DSP
image loads at program `0x8000`. Call overlay 7 downloads to `0xb000`.
The mapping is exact in the reconstructed flash: module 10 at physical/file
`0xa9140` supplies 55,392 bytes at C51 program `0x8000`, and module 12 at
`0xbc3b0` supplies 14,976 bytes at program `0xb000`. For example, dispatcher
word `BACC` at program `0xc537` is byte `20 be` at flash `0xbee1e`. This independently
confirms the overlay origin. The supervisor selects it with `[0x0d28]=7` and
transfers it through ports `0x40..0x4e`, with command/status port `0x1e`.

The V.8 setup of overlay 7 occupies `0xb4c5..0xb55c`. Its dispatcher is
`0xc529..0xc537`, and its state table is `0xc538..0xc5e9`. The indirect branch
at `0xc537` reads callback word `[0x03c8]`. Handlers that start at `0xc5ea` and
`0xc5f9` advance it through the table and get to the matched-filter code near
`0xc9d9`. This path showed missing instructions in the native core. The core now has implementations for `MACD`, `SQRA`,
`SQRS`, `SUB ...,16`, `NORM`, `ZALR`, `ABS`, and `SATH`.

The line output of the older ASIC is external C51 I/O port `0x006a`. Startup clears
it at program `0x804e`. The two runtime paths write words at `0x81ea` and
`0x8205`. The native sample collector now captures that port. We now know why the two paths
are separate. Before, we only saw that they alternate. The interrupt-side
entry at `0x81cc` first executes `LDP #0x17`, uses data page `0x0b80`, writes
its `@0x7b` word at `0x81ea`, and ends in `RETE` at `0x81f0`. The datapump calls
the other entry, `0x81f5`, from exactly `0xb318` and `0xcf99`. That entry keeps the
page of the caller (`DP=0x0380` on the V.8 path) and tests `BIT @0x1f,8` (effective cell
`0x039f`). It branches to `0x89da` while that bit is clear. With bit 8 set, it
continues and writes the `@0x7e` word of the page (`0x03fe`) at `0x8205`.
In dynamic runs, the clear phase takes 166 instructions and sends nothing. The set phase takes
20 instructions and does one `0x8205` write. Thus `0x81ea` is the
interrupt/control slot, and `0x8205` is the paced datapump slot. If you use each
`0x006a` write as consecutive PCM, you mix two different TDM slots.
The paced slot agrees with one complete line sample at **9.6 kHz**. This is the
same rate that the later board uses.

When we force the ready bit, this proves transport and captures nonzero words. But it does not
give valid V.8 audio yet, because the C51 mask-ROM scheduler and the real ASIC
phase word are missing. We also decoded and implemented the other boundary that stopped the core before.
`0xbe71` at `0xcfa6` is `INTR 17`, specifically the software
TRAP vector. It pushes `PC+1`, masks interrupts, saves the interrupt context,
and goes to `(PMST.IPTR<<11)|0x22`. `RETI` restores that context and keeps
`INTM` set. This removes an opcode gap in the emulator. It also gives a precise location for the
remaining hole: vector `0x22` and its handler are in the C51
mask ROM, which we do not have. They are not in the downloaded resident or overlay image.

We now know the exact initial V.8 table selector. At `0xb4da`, the code loads AR1 with
`0x006f`. It masks that control word to its low two bits, ORs in `0x0050`,
and tests bit 1. It first installs table `0xc544`. Then `XC 2,TC` conditionally
replaces it with `0xc53c`. Thus `[0x006f]&2` selects `0xc53c`, and a clear bit
selects `0xc544`. Dynamic execution confirms that the resulting words are `0x0052`
and `0x0050`. Later states explicitly install `0xc548` at
`0xb50d`, `0xc538` at `0xb521`, `0xc540` at `0xb544`, and `0xc53c` at `0xb559`.
Thus the table choice is a DSP-local originate/answer control, not an ASIC
address. The ASIC supplies phase-ready bit 8 at `[DP|0x1f]`, and the low
control bits at `[0x006f]` select the V.8 state family. A launch through the
real selector now operates correctly: set ARP1, set `[0x006f]=2`, and enter `0xb4d7`.
The routine normalizes the control to `0x0052` and installs `0xc53c`. Then the
`0xc529` dispatcher enters `0xc5f9`, not a manually set callback. It
advances the active handler to `0xc61c` and keeps pattern `0x0303` in the
state block. If we call the dispatcher again without the mask-ROM frame service, it only
toggles state word `[0x03ca]` between zero and one and keeps `0xc61c` active.
Thus the slot interpretation is no longer unclear. The missing
emulator step is in the DSP control path that drives the `0x81cc` control
interrupt, publishes bit 8 in `[0x039f]`, and resumes the V.8 callback one time for each
audio slot. It is not another table selector. It is also not evidence that the initiating
behavior belongs to the ASIC.

## C52 call-overlay publication and recovered service slot

The later C52 image contains the call datapump as a runtime program overlay at
source `0xb9c0`, with `0x0a58` words copied to destination `0xc418`. If the core publishes
that bank immediately, this is incorrect: the resident idle service still executes
through the destination range before the ASIC commits the call bank. Thus the native
ASIC model keeps the overlay pending and publishes it atomically with
the call entry.

The missing mask-ROM dispatcher also sets a specific entry ABI. The
call initializer starts at the overlapping instruction stream at `0x2295`. The core
must enter it while resident code is at `0xb2f6`, with TDM phase zero and
128 to 192 C52 cycles before the next 258-cycle frame edge.
If the core enters at a random instruction or at the incorrect subframe, the code writes zero to
`IMR` after about 45 frames, and the datapump stays near `0xc81a`. At the
recovered service slot, it installs `IMR=0x9880`. IRQ 7 continues through the
downloaded ISR at `0x0228`, and the overlay sends continuous nonzero samples.
On this same edge, the ASIC also changes the shared `0x50..0x5f` pins from download-window data to
running TDM latches.

A trace of the reads and writes in the ISR gives more precise locations for the external TDM slots.
The handler reads prior/control words at `0xfff8..0xfffd`. It reads the
normalization word at `0xfffe` three more times from PC `0x0241`. It writes the
oversampled line result to `0xfffd` at PC `0x0238`, and it writes the repeating
control word to `0xffff` at PC `0x0247`. Constant-value experiments identify
`0xfff8` and `0xfff9` as the two input-delay terms that the code multiplies by the phase
coefficient at `0xfffa`. A change to either one changes the result much.
A change to `0xfffd` before the ISR, or a change to `0xfffe`, has no effect. The ASIC now
shifts each new 9.6 kHz ADC word through `0xfff8/0xfff9`, and it uses a boxcar filter to change the
`0xfffd` polyphase output back to line rate. The code uses I/O `0x5b`/`0x5e` only
during a short initializer near `0xb627..0xb669`, not continuously.

The 258-cycle interrupt is a TDM *slot* clock of about 96.9 kHz. It is not the
9.6 kHz codec rate. Thus complete 960-sample DSP frames pace the physical line exchange,
not the faster supervisor instruction clock. This
removed a large queue of old idle samples. That queue had delayed the current call audio
by many emulated seconds.

The linked-line model now also supplies exchange dial tone until an originating
side starts to dial. Then it changes to the loop/audio of the peer. It no longer
needs the obsolete second-bootstrap assumption. The ASIC only latches repeated supervisor register
commits. It does not write them asynchronously into a
running C52. This prevents the corruption of the datapump context by hundreds of later `AR3..BMAR` command blocks.

With one side that originates and one side that answers, both consume current line-rate
peer samples and give different output for each role. We can now see that the input is
live. When we supply the answer stream instead of zero, receive
filter cells `0x035c`, `0x069c`, and `0x0b49` change. The long
convolution loops at `0xc81c` and `0xc855` consume these cells. A linked run of 50 million instructions
exchanges 79,018 samples for each side, without an old backlog or an emulator error.
But it still does not get to `CONNECT`. The remaining blocker is the call-state
transition/callback after these filters. This includes the
ASIC-to-supervisor completion publication, which we did not model yet. The code polls native `TRCV/TDXR` during
initialization, but it does not carry the continuous stream.

### The firmware route to CM/JM, and the word that blocks it

The answer-side experiment that entered `0x2295` again after it detected CI was
incorrect. `0x2295` is the call initializer, which runs one time. A second entry discarded
the live datapump context, and after some time it wrote zero to `IMR`. The downloaded
overlay stays active across the CI/ANSam handoff. The ASIC now only stops its
bootstrap tone and releases the callback-ready bit of the overlay. It does not
invent a second firmware entry.

When we follow that route, we see the V.8 state engine of the firmware. Handler
`0xc617` calls the indirect dispatcher at `0xc418` while timer 0 counts down.
The dispatcher reads handler pointer `0xc617` from data register `0x48`. When
the countdown ends, the handler executes the setup through `0xc6bc` and
enters the convolution/division loop at `0xc853`:

```text
c852  ZPR
c853  BCNDd c853, GEQ
c855  LTS   *+, AR2       ; delay slot
c856  MPYU  *-, AR1       ; delay slot
```

The first operand pair is exact: data `0xa51b` is zero and data `0xd2a8` is
one. The subsequent cells on both walks are zero. `ZPR` clears the first product.
Thus `LTS` never decreases the positive accumulator. AR1 moves up and AR2 moves
down without end, while IRQ 7 continues to service TDM. This is not a missing
callback. It is the callback, which runs on a data vector that is not there.

Two limited perturbations show what is missing. When we set only `0xa51b` to
`0xffff`, the first call returns and the active handler changes from
`0xc617` to `0xc597`. When we put `0xffff` across the full walked range, the
firmware goes farther, through `0xc865`/`0xc872`. When we copy program words into the
range instead, the code then branches through a zero handler. This is clearly
incorrect. We did not keep any of these perturbations as a device model, and their
audio is not evidence of CM or JM. They prove that the next input is an
ASIC/external-data vector. It is not another PC, BIO edge, normalization constant, or
supervisor message.

Thus the practical route to **CM/JM and later stages** is:

1. keep the call overlay and its `IMR=0x9880` context live after CI/ANSam;
2. release callback-ready bit 8 at `0x039f` when the opposite bootstrap signal
   qualifies;
3. recover and publish the external-data vector that the ASIC produces, which starts at
   `0xa51b`, before `c617` dispatches the next state; and
4. let `c418` advance the firmware handler table normally, and then publish its
   completion/status word to the supervisor.

The summary now reports `0xa51b`, `0xd2a8`, the role detector byte `0x0306`,
and the 980/1180 Hz V.21 scores for each frame. Thus a future vector experiment
can be proved false: it is not sufficient to get to a later PC. CM/JM must occur as strong
300-bit/s V.21 low-channel symbols in the firmware DAC output.

### Publishing a guessed vector does not work

We did the next step that we proposed above. It corrects one part of
that conclusion: `0xa51b` is the first missing operand, but it is **not the
start of one contiguous ASIC vector that we can reconstruct from the line
samples**.

The core now records each entry into the three identical numerical loops at
`0xc7f7`, `0xc81a`, and `0xc853`. It records the accumulator, the source address/value,
and the paired address/value. With the callback held low until native CI/ANSam
qualification, the first entry that the firmware controls is always:

```text
loop=c853  ACC=00007fef  source=a51b:0000  pair=d2a8:0001
```

Then we tried these models at the real read boundary:

- a single `ffff` or Q15 `8000` at `a51b`;
- the same value in the descending four-word cells `a51b`, `a517`, ...;
- a contiguous block over the surrounding external-data range;
- the latest 960 codec samples, both contiguous and four-phase interleaved;
- program-space words mirrored into data space; and
- a Q15 result returned directly to the source operand of all three loops.

The first two let `c853` return. But later calls request `a517` and other
work cells. When we fill those, the code gets to `c81a`. The next source of `c81a` is register `0035`
(`TRAD`), and then `ffd0`. When we force those, the code gets to `c7f7`, and its source becomes
`0000`. Constant-Q15 publication can keep all three routines in execution. But it
makes them cycle hundreds of thousands of times. Then it clears `IMR`, and it
gives no strong 980/1180 Hz symbols. When we mirror program words, the code then
branches through a zero handler. Raw codec history also gets to later loops, but
it fails their fixed-point tests. These results clearly prove the models false. They are not candidate
implementations, and none of them is still enabled.

Thus the values are intermediate fixed-point work products. The state routines of the firmware give their
addresses. They are not a wire-format sample or a detector array.
The customer-ROM/ASIC scheduler, which we do not have, must run an upstream producer that
builds that workspace before it releases `039f.8`. The update firmware
contains the consumers and coefficient tables, but not that producer. The supplied images alone
give no way to synthesize it with correct values. A
physical C52 data-memory capture at callback release, or the customer mask ROM,
is necessary. The new loop diagnostics define the minimum useful capture:
`ST0/ARP`, all AR registers, ACC/PREG/TREG0, and data around the reported source
and pair for each of the three loop PCs.

### Replacing the DAA layer with a modeled line

The three-layer replacement above now has two layers. `--exchange` attaches a modeled
central office (`courier_emu/exchange.py`) that runs on the codec sample stream.
It holds 350+440 Hz dial tone while the loop is seized and not dialed.
It decodes DTMF from the transmit samples of the DSP with a Goertzel receiver. It
returns ringback, busy, reorder or 2100 Hz answer tone, as applicable to the
dialed number. On `main211.xmf` with `ATDT5551212` routed to `answer`:

```
exchange: dialed=5551212 digits_decoded=5551212 outcome=answer
          rings_delivered=2 state=connected
serial:   OK / CONNECT
```

The middle layer (the DAA that simulated the line transition) is removed. The
`line_state` of the DAA now follows the signal from the exchange, and its five-hit detector
debounce counts the samples that the exchange delivered (`CourierDaa.observe`).
The two outer layers remain. The bridge still parses `ATD` at the DTE level and still
asks the C52 to send the digits through `set_dtmf_digits`. The change is that
those digits now must go through the line and be read back from it. Also, the model
no longer removes the dial tone of the firmware at the moment that dialing
starts.

For that to run, we had to change two orderings. Before, the harness made both of these line-side decisions:

- The ASIC call engine now waits until the exchange connects the call. It does
  not start on the detector debounce. Without that gate, the datapump starts
  at seizure, and the transmit stream is a flat 1300 Hz V.8 calling tone for ten
  seconds. The modem never dials, and the exchange correctly times out into
  reorder. That run is the clearest evidence that the harness, and not the firmware,
  controls the datapump entry.
- The exchange dial tone releases dialing. The start of the call
  engine does not release it, because that would cause a deadlock with the gate above.

Still unresolved: the armed callback at `0x5d37f` does not place this call.
To get to it, the dial code of the supervisor at `0x85000`-`0x87000` must run. No
run has entered that code.

### The firmware's own dial code, running

We traced this on 2026-09-05 on `main211.xmf` with `ATDT5551212`, `--exchange`, and all
DTE-level replacements removed. The earlier conclusion in this file (that the code never enters the dial
code, and that `[0x298]` is an armed dial callback) was incorrect
in both parts. `[0x298]` holds the pointer to the serial transmit ISR of the supervisor
(`0x5d37f` ends in `iret` after it pushes a byte to `0xff6a`). The code at `0x5d334` selects it from
three variants. It is not related to dialing.

**The dial path. The firmware does all of it:**

| step | address | what it does |
|---|---|---|
| parse | `0x82652` | reads the dial string, folds `P`/`p` to `T` under `[0x94b]` |
| settle | `0x5db51` | off-hook settle, `[0x289] = 0x1f4` |
| detect | `0x5dbda` | `[0x289] = 0x2580`, then waits for `[0x649] >= 5` |
| give up | `0x5dc4a` | `call 0x63491; db 8` - the `NO DIAL TONE` result |
| encode | `0x6353c` | character to keypad index: `'0'`-`'9'` pass through, `'#'` to `0x0a`, `'*'` to `0x0b`, `'A'`-`'D'` to `0x0c`-`0x0f` |
| dial | `0x63553` | sends `0x1600`, waits `[0x161] = 0x0c`, sends `0x13` + index |
| hold | `0x82342` | tone duration from S11 at `[0x8e9]`, `/0x6b` |
| gap | `0x8235b` | interdigit, the same countdown less `0x30` |
| pulse | `0x822a3` | the pulse-dial loop, break/make from `bx`/`dx` |

`[0x649]` is the five-hit line detector, fed from the `0x7c` poll's reading at
`[0x285]`, which `0x5e4c4` bands: at or below `0x60` present, above it counted
against `[0x92a]` and then aborted with result `0x27`. `[0x66c]` bit 7 is "a
result code is pending", not dial tone; `0x63491` is the inline-argument
setter that raises it and stores the code in `[0x823]`.

**What was blocking it.** The receive handler at `0x6ad6e` reads a tag from
`0x58`/`0x5a` and the word from `0x5e`/`0x5c`. The bridge served the C52 status
latch on `0x5c`/`0x5e` whenever the core was active, so a reply it had already
queued arrived as `0xffff`: the detector consumer banded that above `0x60` and
hung up after one reading. With queued replies owning the data lanes, the
firmware counts its own hits and accepts dial tone on its own.

**What it produces.** Each digit goes out as `0x16:0000`, the tone generator's
three constant lanes (`0x19:020d`, `0x1a:3000`, `0x1b:0c08`), the digit on
`0x13`, and `0x16:0000` again when the tone ends. For `5551212` that is
`0013:0005` three times, then `0001`, `0002`, `0001`, `0002`, each about 600 ms
apart on the firmware's own timers. The bridge renders them, the exchange
decodes them back off the line, and the number arrives whole.

The call-start block uses the same `0x13`/`0x16` lanes with the same constants;
nothing in a single message tells the two uses apart. What separates them here
is the line - a digit only means anything while the loop is seized and the call
has not come up.

Still outstanding: the result code. `ATD` ends in command mode, because the
exchange answers with 2100 Hz and nothing behind it trains.

### What the call overlay writes, and why it is not audio

Measured 2026-09-05 with `set_synthetic_line(False)`, which stops the core
substituting its hand-written DTMF and V.8 tones for the datapump's DAC
accumulation - and stops it discarding that accumulation to make room.

An answered call reaches the overlay: ring the modeled line, let the firmware
answer, and `call_overlay_active` goes true with the recovered bank executing.
The frame ISR at `0x0228` then runs every codec slot:

```
022c  add     #0000824d      ; table base
022e  tblr    @7a            ; table read
0230  lacc16  @7c            ; ACC = phase high << 16
0231  adds    @7d            ;     + phase low
0232  lt      @7b
0233  mpy     #0028
0234  lta     @7a
0235  mpy     @78
0236  mpya    @79
0237  sach    @7c            ; phase high
0238  sacl    @7d            ; phase low
...
0245  sacl    @7a
0246  bldd    @7a, #ffff     ; out to the ASIC slot
```

At DP `0x1ff`, `@7c`/`@7d` are `0xfffc`/`0xfffd`. So **`0xfffd` is the low half
of a 32-bit phase accumulator, not the DAC word.** The core read it as the DAC,
which is why the datapump's output measured as broadband noise: the captured
stream is a linear ramp with a constant step of `-14704` per sample, wrapping
16 bits - about 2.15 kHz at the 9.6 kHz codec rate.

The word the ISR computes from that phase goes out through `@7a` to `0xffff`.
That slot carries exactly two distinct values, near-DC, so it is not a waveform
either. `set_line_dac_slot` makes the choice switchable rather than assumed.

Where the datapump's PCM actually leaves the C52 is therefore unresolved. The
`tblr` at `0x022e` against a table based at `0x824d` is the next thread: a table
read on this path is what a phase-to-amplitude lookup looks like, and its
result is overwritten in `@7a` before the store at `0x0245`.

Two things are settled by this measurement. The V.8 tones a run emits are
`C5xCore::dtmf_sample()` - 1300 Hz gated 500 ms on/off for calling, 2100 Hz with
15 Hz AM and 450 ms reversals for answering - not firmware output. And V.21 is
generated nowhere; the harness only scores 980/1180 Hz symbols it never sees.

> **Superseded 2026-09-08.** `C5xCore::dtmf_sample()`, `set_dtmf_digits` and
> `set_synthetic_line` have been deleted. There is no harness tone generator
> left to switch off, so every measurement below that qualifies itself with
> `set_synthetic_line(False)` is now simply the unconditional behaviour. The
> DSP is the whole audio path; on 3.0.13 it emits its own DTMF
> (`artifacts/dtmf-emulator-302-01`).

### Where the audio path is not: four measurements

Measured 2026-09-05 on an answered call with `set_synthetic_line(False)`, so
nothing but the C52 can put anything on the line.

**1. The overlay runs and stalls where the file already said it would.**
`v8_dispatches` 89, `negotiation_loop_entries` 14, `negotiation_loop_pc`
`0xc853`, and the PC trace is dominated by `0xc853`. So the datapump's
negotiation is executing and spinning in the loop that needs the absent
ASIC-produced workspace.

**2. The frame ISR at `0x0228` is the polyphase resampler, not a DAC writer.**
It runs about **ten times per codec sample** - the write counts for the ASIC
block are `0xfffd`, `0xfffb`, `0xffff` at 10.09 per sample, `0xfffa` at 20.2,
`0xfffc` at 30.3 - which is the 25 MHz/258-cycle TDM slot rate against the
9.6 kHz codec. It reads the slot number from `@52`, indexes four descriptors at
program `0x824d` (`bf09 04fd be59 bb3f`), and filters the ADC pair `@78`/`@79`
by them into the 32-bit accumulator `@7c`/`@7d`.

**3. Nothing in the block is a waveform.** De-interleaved by TDM phase, slot
`0xffff` carries two to four distinct values in every phase, peak/rms 0.066.
The whole overlay writes only 723 distinct cells, and every one outside
`0xfff8`-`0xffff` fewer than 200 times in 98,237 codec samples. A running
datapump would touch far more than that.

**4. The receive path is backlogged by about forty seconds.** A known 1800 Hz
tone from the far end appears nowhere in the ISR's output - and the reason is
not the firmware. Routing the harness's ADC injection through `DM_WRITE16`
makes it visible: `0xfff8` is written once per codec sample, 24,979 times, and
**every write carries the same value**. `codec_rx_queued` is 495,360 against
`codec_rx_consumed` 101,020, so the queue runs about five times faster than the
DSP drains it and `front()` is still silence from before the call came up.

That last one is a harness bug, not a firmware property, and it invalidates any
earlier reading that assumed the datapump had heard the line. The codec receive
queue has to be paced to consumption before the transmit side can be judged at
all.

So the audio path is not at `0xfffd` (a phase accumulator), not at `0xffff`
(two values), and the input at `0xfff8` never varies. `set_line_dac_slot` and
`line_phase_samples` make each of those measurable rather than assumed.

### The two clocks disagree by about four times

Pacing the modeled line on the codec rather than on the 80186 instruction count
removes the receive backlog exactly - `codec_rx_queued` 132,480 against
`codec_rx_consumed` 132,480, ratio 1.00, backlog 0 - and immediately exposes
why the backlog existed.

Over 60,000,000 instructions the codec clocks 132,480 samples, which at 9.6 kHz
is 13.80 s of line time. That implies **4,348 80186 instructions per
millisecond**. `INSTRUCTIONS_PER_MS` in `daa.py` is **1,111**, calibrated from
the answer machine's tick counter reaching the country minimum of 180 during
one 2 s ring burst. The two disagree by 3.91x.

At the board's 20 MHz that is 4.6 clock cycles per instruction on the codec's
figure and 18.0 on the DAA's. 4.6 is an ordinary 80186 mix; 18.0 is not.

Neither is independently verified. The codec figure inherits the C5x cycle
model and the 5:4 scheduling ratio between the two processors; the DAA figure
inherits the assumption that one ring burst is what takes the counter to 180.
But they cannot both stand, and every line-side timing in the harness rests on
one or the other.

The immediate consequence is visible in the answer probe. With the line paced
correctly it advances about four times slower per instruction than before, so
the firmware's own timeouts - which count in instructions - expire against it:
the answered call in that run stays up for 6 line frames out of 147, and the
1800 Hz far-end tone that was supposed to prove the receive path reaches the
datapump for 600 ms before the modem hangs up. `0xfff8` still reads as one
distinct value across the run.

So the receive path is now correctly paced and still unproven, and the thing
standing in the way is a clock calibration rather than anything in the
firmware.

### What the firmware says a second is: 200 ticks

Found 2026-09-05 in the user's own board image,
`artifacts/courier-board-21210-capture-403/courier-board.rom` (supervisor
7.4.16 / DSP 3.1.2), and confirmed against `main211.xmf`.

Both builds convert an S-register byte, which is in seconds, to a countdown by
multiplying by 200:

| build | sites |
|---|---|
| 403 ROM (7.4.16) | `0x82206`, `0x952b5`, `0xa23ef`, `0xa570a`, `0xa5914` |
| main211 (2.1.1) | `0x5dc8c`, `0x70fa6`, `0x82635`, `0x82862`, `0x828c8` |

each `mov ah, 0xc8 ; mul ah`, storing to the cell the wait then counts down -
`[0xc9a]`, `[0xae5]`, `[0xd85]` in the 403; `[0x8d6]` in main211, which
subtracts `0x50` afterwards where the 403 subtracts `0x0f`. **So the firmware's
own arithmetic puts one tick at 5.0 ms.**

The two builds are the same codebase relocated. Every `mov ah, imm ; mul ah`
site appears in both in the same order with the same factors - 200, 4, 8, 10,
24, 100, 100, 10, 20, 60, 60 - and the wait shapes match too: main211's
`test byte [0x66c], 0x80 ; cmp word [0x8d6], 0` at `0x82afd`, loaded with 2000,
is the 403's `test byte [0x225], 0x80 ; cmp word [0x488], 0` at `0xa5b9b`,
loaded with the same 2000. 7.4.16 reorganises the dial-tone wait itself into a
dispatch on `[0xaf0]` rather than main211's inline poll, which is why its
countdown cell `[0xaea]` holds no 9,600 literal.

Against that 5 ms, both of the harness's figures are out by about two:

| | ms per tick |
|---|---|
| firmware, from the image | **5.0** |
| harness ROM path, `tick_ms=10` | 10.0 |
| `daa.py`, from the ring calibration | 11.1 |

`daa.py` derives `INSTRUCTIONS_PER_MS = 1,111` from 2,000,000 instructions
taking the counter to 180, read as one 2 s ring burst. That is 11,111
instructions per tick either way; at the firmware's own 5 ms it makes
`INSTRUCTIONS_PER_MS` **2,222**, not 1,111. And the reading it rests on looks
wrong in the same direction: 180 ticks at 5 ms is 900 ms, which is an ordinary
minimum ring-burst length to qualify on, where 2 s is the whole cadence.

None of this reaches the codec-implied 4,348, so that model stays separately
suspect - this settles the supervisor's timebase, not the C5x's.

**The falsifiable part.** On the 403 board the dial-tone wait is `S6 x 200`
ticks. If one tick is 5 ms then `ATD` to `NO DIAL TONE` takes exactly `S6`
seconds, so timing it at several `S6` settings must give a slope of 1.000
seconds per unit. `tick_probe --dial-wait` measures precisely that.

## Repro notes

Analysis tooling: Python + `capstone` (x86-16). macOS blocks reads under
`~/Downloads` (TCC) — the file had to be copied into the repo first.
