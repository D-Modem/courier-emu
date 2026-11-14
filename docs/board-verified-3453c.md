# What the 3453C board has confirmed

The board is a Courier V.Everything V.92, "CTR21 External", on
`/dev/cu.usbserial-FT4TQOFT` at 19200. We probed it for the first time on
2026-10-03. It has stock firmware - no ID_SDL - and it is exactly the image that
the repo already has, `docs/3453C_v2.3.33/2_3_33.XMF`. The raw captures are in
`artifacts/3453c-board-identity-20261003/` and `artifacts/3453c-parameter-sector-20261003/`.
The working notes for each address below are in
[atg-monitor-2.3.33.md](../artifacts/3453c-board-identity-20261003/atg-monitor-2.3.33.md).

Unless a section tells you differently, we read all values with `AT`, `ATI*`,
`ATGSI` and `ATG=`/`ATGR` memory reads. The exceptions, all for the session
only, are: `ATQ0`, `ATS0=9` (the modem answered one call), and `AT~C#0` (the
country changed to US/Canada in RAM).

> **The capture `f8000-fbfff.bin` holds the stored dial-security password in clear text**
> (sector offset `0x5f`). Do not commit it. `at-screens.txt` has it redacted.

## Identity

| | |
|---|---|
| `ATI7` | supervisor **2.3.33** (05/03/11), DSP **2.1.41** (06/04/08), DAA rev `0013`, 25 MHz, 1024k flash, 256k RAM |
| product | `ATI0` `5608A`, product ID `99345303`, options HST V32bis Terbo V34+ V90 V92 |
| `ATI1` | `13D9` |
| serial | `5MBSXA6P0183` (also at parameter-sector offset `0x11`) |
| DAA | Si3034 chipset, Si3021 + Si3014 - datasheet now at [SI3034.PDF](SI3034.PDF) |
| DSP | marked `TI 16.0036.00 (C) US ROBOTICS D172B1PJ92` (read off the board) |

In all of this document, physical address = file offset + `0x40000`. The XMF
covers only `0x40000..0xf7fff`. The parameter sectors and the boot block above
it are on the board, and we have now captured them (below).

## ATG: a full monitor, no prefix, no gate

Stock 2.3.33 has the ID_SDL-style monitor. The main AT table is at `0x85e50`
(indexed from `!`, with `~` remapped after `Z` by the dispatcher at
`0x816a5`). `G` -> `0x824af`. There is no `LK2` prefix (7.6.7 must have one)
and no dial-security check.

| form | effect |
|---|---|
| `ATGR[seg:]off` | 128 words from `es:[bx]` - **use this one** |
| `ATG=[seg:]off` | 256 bytes; with `seg:` it prints the dump then `ERROR` (the handler skips `dec cx` after `:`) |
| `ATGIport` / `ATGOport,val` | one port read / **write** |
| `ATGBport` | 256 consecutive port reads - disruptive, as on the 403 |
| `ATGhhhhdddd` | queue `ff00 hhhh dddd` to the DSP |
| `ATGSI` / `ATGSIhhhh` | tag `0x80` / tag `0x84` with a raw Si3021 control word (below) |
| `ATGT`, `ATGN`, `ATGU`, 4-hex | as on the 403 |

The hidden command `ATI92` prints the V.92 `+p` settings.

## Mailbox: the 403 layout

INT0 (vector `0x0c` -> `6770:0000`, handler `0x67700`) services the mailbox.
The status is `in 1e`/`1c`:

- Bit 0 sends the next queue word (ring `0x2e0..0x30f`, tail `[0x2dc]`, head
  `[0x2de]`). An `ff` high byte starts a pair. A single word `hhll` goes out as
  tag `hh`, data `ll`.
- Bit 1 reads the tag `5a:58` (tags `>= 0x80` are ignored) and the data
  `5e:5c`.

The tags `7c`/`7b`/`7d`/`7e` go into `[0x283]+[0x285]`/`[0x287]`/`[0x27f]`/`[0x281]`.
The other tags go to `call [0x2da]`. The acknowledgement is `out 1c`. Thus
**`ATGI0058`..`005E` reads the last reply and does not consume it**. The idle
supervisor sends `ff00 000f 0600` regularly. The last reply at idle was
`0047:0007`.

## The DAA, decoded against the Si3034 datasheet

* The data of tag `0x84` is the Si3021 secondary-frame control word: `D13` =
  read, `D12:8` = register, `D7:0` = data. `0084:0502` writes reg 5 = `02`.
  `0084:3100` **reads** reg 17. `0084:1468`/`1408` address reg 20, which the
  datasheet does not list.
* The tags `7d`/`82`/`83` carry the "Impedance match byte" and the "SI DAA
  register 17/18" of the country table (`0x677ff`) - Si registers 16, 17, 18.
  The value `0x2c` of CTR21 in reg 16 is complex AC termination with TBR21 DC
  termination. That explains the `0x82`/`0x83` traffic that the 3453B notes
  could not identify.
* DAA rev `[0x287]` = `0x0013`. Bit `0x10` is set, which starts the SI polling
  of the supervisor. It is not raw reg 13. `CBID<<4 | REVB` (international line
  side, Si3014 rev C) agrees, but it is not confirmed.
* We sent `ATGSI` on hook three times, and again during ringing. The requests
  left the queue, but **no tag `0x7e` reply came back**. It is not known
  whether DSP 2.1.41 handles tag `0x80`.

## Country: `AT~C`

`AT~C?` gives 28 tables, `00:US/Canada` .. `27:Turkey`. This unit is **08,
CTR21**. `AT~C#n` sets `[0x173]` and `[0xa37]`, and copies table `n`
(`7b59:0d42 + n*0x80`) to RAM `0x1f71`. We tested it with `n` = 0, and then
`ATI7` reads "US/Canada External". It does not send the Si registers again
(the last `7d` in the queue stayed `2c`). `[0xa37]` is parameter-sector offset
1. Thus the stored country stays `08` until something writes the sector again.
`AT~X!` restarts into the loader - do not send it. We did not read `~F!`,
`~C!`, `~P?` and `~P!`.

The dump routine of the country table (`0x7d898`) gives a label to each field.
`country-params-live.txt` is the live CTR21 table, decoded with those labels.

## Ringing

A US ring (2 s on / 4 s off) on the connected line:

* is timed: `[0x1d94]` = 1 during a burst, `[0x1d90]` counts it to about
  `0x1a0`, and `[0x1d96]` latches it;
* passes the CTR21 qualifiers (13-80 Hz, >= 200 ms, silence before RING 1.2 s)
  and the US qualifiers;
* is counted, but **only when S0 > 0** - `0x6e52d` skips the S1 increment at
  S0 = 0. With `ATS0=9`, S1 went 1..8 at intervals of about 6 s, and the modem
  answered the ninth ring (`NO CARRIER`);
* flashes AA - and **never prints `RING`**. This is true with Q0, with no other
  user of the port, with passive listening, and under the CTR21 and the US
  tables. RI never asserted (it is possibly not wired through the adapter).

The ring counter reports through `57bb:c73a -> [0x2ac]` as event 3 or 9. Each
`[0x2ac]` state ignores event 3. The result printer is `0x62ee1` (`RING` =
code 2, table `0x80187`, Q in `[0x953]`). Its caller `0x5b565` is called
indirectly. We did not find where code 2 is issued.

## Parameter sectors and boot block

`f8000-fbfff.bin`: four 4 KiB sectors, all programmed, versions `0x39`..`0x3c`.
**All four checksums are valid** under `parameters.checksum`. The newest is a
byte-for-byte copy of RAM **`0x0a36`** - not `0x0a06` as in `main211`. Thus
offset `n` is RAM `0x0a36 + n`: `0x00` flags `c0`, `0x01` country `08`, `0x11`
serial, and the profile from `0x30`.

`fc000-fffff.bin`: the boot block. No image in the repo has it. It contains
the SDL Xmodem recovery loader and the reset vector
`cli; mov dx,ffa4; mov ax,8000; out dx,ax; jmp fc00:1d11`.

## What is still needed

**2026-10-03 ROM recovery update:** We have now recovered the DSP mask ROM of the 3453C with a temporary PMST.MP/MC mapping probe. It is **4,096 words at 0000..0FFF**. We captured it two times, and the two captures are identical. The live PMST was 18B8 before and after. The tail of the mapped window at 1000..1FFF agrees with the downloaded RAM. The bootstrap at 0F46..0F7C uses I/O 8057 and 8058..805B. This confirms the different first-download protocol that we describe below. [Capture, binary, disassembly, and verification](../artifacts/3453c-dsp-mask-rom-read-20261003/README.md). The older observations below that the ROM is not available describe the investigation before this recovery. The recovered boot loader is now integrated. The ROM downloads the resident, the resident loads its low overlay, and the CPU gets to command mode. [Idle comparison and remaining peripheral gaps](../artifacts/3453c-emulator-boot-20261003/README.md).

1. **The DSP's first download - the 3453 family's own loader.** `./courier run 2_3_33.XMF`
   stops at "C51 mask ROM did not arm its NMI vector". This is because the
   bridge maps the mask ROM only when the resident does not change `MP/MC`
   (`boot_rom.maps_onchip_rom`). The C resident sets `MP/MC = 1`, but only in
   its own prologue, after it was downloaded. At reset, `MP/MC` is the pin, and
   the DSP of this board boots.

   If you map the ROM at reset (a `sitecustomize` patch of `maps_onchip_rom`,
   with no repo change), the NMI is armed and the loader runs. Then it fails at
   the second group: **"C51 ROM loader did not acknowledge strobe 1"**. The
   recovered loader (`0638..0652`, from the 20.16 MHz board of the 302/403
   family) takes group 1 on strobe 1 from window `0x58`, and group 2 on
   **strobe 2** from `0x5c` - the `out 18,1` / `out 18,2` of the 403
   ([c51-cpu-loader.md](c51-cpu-loader.md)). The 3453 download at `0x66700` is
   different. It sends group 1 to `40..4e` with `out 1e,1`, and group 2 to the
   port in `[0x1ff3]` with the strobe in `[0x1ff2]`. **Each 3453 image
   hard-codes those to `0x40` and `1`**: 2.1.1 (`0x69cb5`), 2.2.05, 2.3.12 and
   2.3.33 (`0x666bc`; the RAM of the board reads `1`/`0x40`). The two halves of
   each block go through one window on one strobe.

   Thus all of the 3453 family uses a first-download protocol that the mask
   ROM of the repo does not implement. **The loader of that ROM is also not in
   any image**: no run of `0610..0652`, and none of its instruction pairs
   (`bit 0,@56 ; bcnd`, `rpt #3 ; bldp ; lacl #1 ; samm @56`,
   `splk @56/@57 #ffff`), occurs in 2.1.1, 2.2.05, 2.3.12, 2.3.33, the boot
   block or the parameter sectors. But 2.3.33 has the overlay loader of the
   resident at program `1150..1171`. It shows the DSP side of the 3453
   transfer: it polls **I/O port `0x8057`** bit 9, does
   `rpt #3 ; in *+, #8058` (four words from I/O `0x8058`) and `bldp`, then
   acknowledges with `out 0300 -> 0x8057`. There is one four-word group for
   each handshake, through I/O space. The recovered ROM uses the memory-mapped
   cells `@56`/`@58..5f` instead. A 3453 mask ROM that does the first download
   must use this protocol.

   **The same failure now stops `main211`**. It started with `f01e9d8` ("Gate
   the DSP mask ROM on the part"), which mapped that ROM for B-series XMF
   images for the first time. `f01e9d8~1` boots `3453Bv2.1.1.xmf` correctly.
   `f01e9d8` and `HEAD` do not.

   The part itself shows that it is different silicon. The 302/403/2806 DSP is
   `TI DSP 16-912 (C) US ROBOTICS D17140PQ`, a 'C51 by write-readback
   ([board.md](board.md)). This one is
   `TI 16.0036.00 (C) US ROBOTICS D172B1PJ92` - a different USR part number, a
   different TI mask code, and the **PJ** suffix. board.md gives PJ as the
   package of the 'C52 (PQ is the package of the 'C50/'C51). A 'C52 has 4K of
   ROM at `0000..0fff`, no SARAM, one serial port and no TDM. The C series
   agrees: its block at program `0000..0ff9` is 4,090 words. It fills the 4K
   window that `MP/MC = 1` changes into external RAM, and its `PMST.RAM` bit
   has no SARAM to map. Thus the first download belongs to the D172B1 mask
   ROM, which the repo does not have. It is visible only while `MP/MC = 0` -
   from reset until the prologue of the resident sets it. Thus, to recover it,
   it is necessary to use a [ROM probe](dsp-rom-probe.md) that clears `MP/MC`
   and reads `0000..0fff` on this board, which is invasive. The conclusion
   that the part is a 'C52 comes from the suffix and the map. Nothing here
   measured it.
2. **A parameter-sector path for 2.3.33.** `courier_emu/parameters.py` is the
   3453B layout at RAM `0x0a06`. This image reads it at `0x0a36`, and now a
   real sector exists to supply it. You cannot test it until item 1 lets
   2.3.33 boot.
3. **Why `RING` is never printed** - the issuer of result code 2.
4. **Tag `0x80`'s handler in DSP 2.1.41**, and the receive dispatcher of the
   2.x DSP in general. Its layout is different from 3.x (there is no
   `lar ar1,#ff5e` pair in the resident).
5. **The rest of flash** (`0x40000..0xf7fff`) against the XMF, with `ATGR` or
   `ATXMODEM` option 1, to confirm that the board runs this image byte for
   byte. We also did not calculate `ATI1 = 13D9` from the image.
6. **Board parts**: the DSP, RAM and ASIC markings and the Si3021/Si3014
   placement - we did not read any of this from the hardware itself.
