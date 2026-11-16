# ATG monitor in stock 2.3.33 (static, not yet run on the board)

These are physical addresses, with `2_3_33.XMF` loaded at `0x40000` (physical = file + 0x40000).
The code segment for the command module is `0x813C`. This comes from the ATI table: `jmp cs:[bx+1477]`
at `0x8280e`, table at `0x82837`.

## Route

The main AT letter table is at `0x85ea0` (cs-relative words): `G` = `10ef` -> `0x824af`.
There is no dial-security or password test on the route. `[0x178]` bit 0, which gives
`[ ACCESS DENIED ]` for ATI10, is not tested by G. **There is no `LK2` prefix**. (7.6.7
needs one. 2.3.33 does not need one, the same as 4.03d.)

| Form | Handler | Action |
|---|---|---|
| `ATGSI` | `0x824df` | queue word `8000` (6770:077b), print `ta_report_si_read=` + `[0x281]` |
| `ATGSIhhhh` | `0x824c2` | queue `ff00 0084 hhhh` |
| `ATGT` | `0x8252d` | 8-word x16 dump at `0000:(([0x2b8]-e0)&fff0, min 5700)` - the saved stack |
| `ATG=[seg:]off` | `0x83c00` | 256 bytes from `es:[bx]`; no `seg:` means segment 0 |
| `ATGR[seg:]off` | `0x83c6b` | 128 words, same addressing |
| `ATGIport` | `0x826ba` | one `in al, dx` |
| `ATGBport` | `0x83ccd` | 16x16 consecutive `in` - **256 ports, disruptive** (see docs/probing.md) |
| `ATGOport,val` | `0x826da` | one `out dx, al` - **write** |
| `ATGN` | `0x825cb` | sets bit 0 of `[0x29c]` (403: `[0x158]`) |
| `ATGU` | `0x82702` | `clc; ret` |
| `ATGhhhh` | `0x8257e` | parse, then `57bb:21ab` (403: `8000:1ef1`) |
| `ATGhhhhdddd` | `0x8258e` | queue `ff00 hhhh dddd` via `6770:0777` |
| other lengths | `0x825ad` | parse, then `57bb:21a7` (403: `8000:1eed`) |

The queue helper `0x67eab` is identical byte for byte to `0xf678` of the 403, except for the cells:
ring `0x2e0..0x30f`, tail `[0x2dc]`, head `[0x2de]` (403: `198..1c7`, `194`/`196`).
It also drops a word silently when fewer than 6 bytes are free. Thus, a serial `OK` still does not prove the delivery.

## The mailbox: the INT0 handler at `0x67700` (vector `0x0c` -> `6770:0000`)

The register layout is the same as on the 403. The status is `in 1e`/`in 1c`, masked to 2 bits, and kept in `[0x2c6]`:

* **bit 0, host->DSP empty:** the handler takes the next queue word. The pending pair state is in `[0x2ca]`
  (sentinel `7f3f`). A word with the high byte `ff` starts a pair (`0x67881`). A single
  word `hhll` goes out as **tag `00hh`, data `00ll`**: `58`=hh, `5a`=0, `5c`=ll, `5e`=0.
* **bit 1, DSP->host ready:** the tag comes from `5a:58`. The handler ignores tags `>= 0x80`. Tags
  `7c`/`7b`/`7d`/`7e` copy the data (`5e:5c`) to `[0x283]+[0x285]` / `[0x287]` / `[0x27f]` / `[0x281]`.
  Then `call [0x2da]` dispatches the other tags.
* Acknowledge: `out 1c` with `[0x2c6]` (low byte, then high byte). End of interrupt through `[ff02]=8000`.

Thus, a read of `58`..`5e` with `ATGI` is passive, as on the 403. The code that I first thought was the drainer
(`0x68241..0x6836d`: status bits at `18`/`1a` select `dx` = `54`/`58`/`5c`) is **not** the mailbox.
Its function is not identified.

## ATGSI

This is the same diagnostic that the 3453B has (courier_firmware_analysis.md, "The DAA identity arrives as
mailbox tag 0x7b"). `ATGSI` queues the single word `8000` (tag `0x80`), yields three times, and prints
`[0x281]` (the last line-side register read of tag `0x7e`: the RDTN/RDTP ring bits). `ATGSIhhhh` queues
`ff00 0084 hhhh`, the line-side register **write**. The supervisor itself sends `0084:1468`,
`0084:1408`, `0084:3100`, `0084:0502`. Its own line poller (`0x5ab64..`, state in `[0x686]`) sends
`8000` and `7c00` only when `[0x287] & 0x10`.

**The DAA revision of this board is `0x0013`** (`[0x287]`, and ATI7). Bit `0x10` is set, thus the SI path is
live on real hardware. The 3453B notes could only guess this value (they used 4).

## What it does and does not give

* Any 80186 memory (RAM, flash, peripheral control block through `=`/`R`), read-only.
* Any single I/O port read. Port writes through `O`.
* DSP commands by tag through the normal queue.
* **No direct DSP memory read.** That needs a DSP-side handler for a tag, as before.

Other: the hidden `ATI92` (`0x845f2`, not in the ATI table) prints the current/stored `+p` (V.92) settings.

## First board reads, 2026-10-03 (`atg-first-reads.txt`)

Idle, on hook, 19200. `AT` answered before and after.

* `ATG=0000:0000` printed the 256 bytes and then **`ERROR`**. This is a quirk of the firmware, and it agrees with the
  code: the `=` handler consumes the `:` with `lodsb` but never does `dec cx` (`0x83c0b`).
  `R` does it (`0x83c7b`). Thus, `=seg:off` leaves the parser one character wrong.
  The dump itself is correct. `ATGR` with a segment answers `OK`.
* IVT: most vectors are `57bb:xxxx` (supervisor), and some are `7a4d:`. **INT0 (vector `0x0c`)
  -> `6770:0000`**, the module that holds the DSP queue helper. Vector `0x0a` (DMA0) ->
  `0000:2070`, a handler in RAM. Vector `0x16` -> `d4a0:0000`.
* Queue: tail `[2dc]` = head `[2de]` = `02ee` -> empty. The ring holds old
  repeated `ff00 000f 0600` frames, plus one `5700 5800 0600`. The idle supervisor
  sends tag `000f`, data `0600`, routinely.

## ATGSI on the board, 2026-10-03 (`atgsi-reads.txt`, `atgsi-mailbox.txt`)

* Cells before and after: `[0x27f]`=0, `[0x281]`=0, `[0x283]`=0, `[0x285]`=`00ff` (the "no reading"
  sentinel), `[0x287]`=`0013`.
* Three `ATGSI`: three `8000` words were queued (`2ee`->`2f4`) and drained. Each one printed
  `ta_report_si_read=0000`.
* Mailbox holding registers before and after: tag `0047`, data `0007`, no change. **No tag-`0x7e`
  reply arrived**. The printed 0000 is the old cell, not a reading. On hook, the line state is not known.
  We did not establish if DSP 2.1.41 handles tag `0x80`. Its dispatcher does not have
  the same layout as 3.x (no `lar ar1,#ff5e` pattern in the resident).

## Against the Si3034 datasheet (Si3021 + Si3014; `docs/SI3034.PDF`, Rev 2.02)

The `0x84` data word agrees exactly with the Si3021 secondary-frame control word (Figures 26/27):
`D15:14 = 00`, `D13` = R/W (1 = read), `D12:8` = register, `D7:0` = data.

| supervisor sends | decodes as |
|---|---|
| `0084:0502` | write reg 5 (DAA Control 1) = `02`: OHE, off-hook pin enabled, on hook |
| `0084:0100` | write reg 1 (Control 1) = `00` |
| `0084:3100` | **read** reg 17 (International Control 2: MCAL CALD LIM BTE ROV BTD), sent only when `[0x287]&0x10` |
| `0084:1468`, `0084:1408` | reg 20 - outside this datasheet's map (it stops at 19) |

Thus, `ATGSIhhhh` is a raw Si3021 register access, write or read. It is not only a write.

`[0x287]` = `0x0013` is **not** raw reg 13. (That would give REVB = 4, which is not in Table 21.) It does agree with
`CBID<<4 | REVB`: CBID = 1 (international line side; this is a CTR21 unit) and REVB = `0011` =
**Si3014 rev C**. With that interpretation, the `& 0x10` gate of the firmware is "international line side",
and `== 4` is CBID 0 with REVB 4. This is the best fit, but it is not confirmed.

In the datasheet, the ring bits are reg 5 D6 (RDTN), D5 (RDTP) and D2 (RDT). The tag-`7e`
consumer of the supervisor tests bits 0 and 1 of `[0x281]`. Thus, the DSP repacks before it replies, or it reads a different
item. The 80186 never sees a raw Si3021 register. The DSP controls the link, thus the reply formats are
those of the DSP.

## Ringing, 2026-10-03 (`atgsi-ring-live.log`, `ring-now.log`)

The line was connected and ringing. The AA LED flashed with each ring (live S0=000, thus AA is otherwise dark).
With Q0 set (volatile), over about 30 s: **S1 stayed 000, there was no `RING` result, and RI never went high**. `ATGSI` gave 0000.
The reply cells and the mailbox (`0047:0007`) did not change. Thus, an item drives the AA LED on ring, but the
supervisor never counts a ring, and no tag-`7e` reply arrives. Candidates that we did not test: the ring
qualification (cadence/frequency for a CTR21 build on this line) rejects the ring after the
raw detect, or the raw ring-detect line drives the LED, not the counted ring.

### The ring handler, `0x6e3c9..0x6e58c` (static, plus a RAM dump taken after ringing)

The live S-registers are at `0x902` (S0). Thus, S1 = `[0x903]`, S70 = `[0x948]`. (We found this when we dumped
`0000:0000..3fff` with `ATG=` and matched the ATI4 values. A second matching run at `0xa67` is not the live copy. We did not check its function.)

* The handler first counts S70 (distinctive ring types) (`[0x1d9e]`). With S70 = 0, no type is enabled, and the
  handler accepts any ring (`[0x1d9c]=0`, `[0x1d9d]=2`). **S70 does not block a US ring.**
* `0x6e52d`: `cmp [0x902],0 ; je 0x6e56d`. **With S0 = 0, S1 is never incremented.** When S1 reads 000
  during ringing, this is the behavior of the firmware with auto-answer off. It is not evidence of a rejected ring.
* In other conditions: `inc [0x903]`. When S1 >= S0, it queues word `7a00` to the DSP (tag `0x7a`, answer)
  and raises event 9. Below S0, it raises event 3.
* Events go through `57bb:c73a` -> `call [0x2ac]`. In idle, `[0x2ac]` = `a7b0` (`0x62360`). That handler acts
  only on events 0 and 9. Thus, with S0 = 0, the ring raises event 3 into a handler that ignores it.
* The RAM after ringing shows that the handler ran: `[0x1da4]` = 2 (latched from `[0x1d9d]`),
  `[0x1f60]` copied from `[0x1f57]`.
* We did not yet find where the `RING` text and RI come from.

### S0=9 test (`ring-s0-9.log`, volatile ATQ0S0=9, restored to S0=0 after)

US-cadence ring. S1 counted 1..8 at intervals of about 6 s (2 s on / 4 s off). Thus, the ring is detected,
qualified and counted. At the 9th ring, the modem answered (the serial line went quiet), then `NO CARRIER`
came about 4 s later. **No `RING` result was printed at any point, also with Q0.** Thus, ring counting works,
and the only open question is the `RING` result code (and RI), not the ring detection.

## Country parameter table (RAM `0x1f71..0x1ff1`), `country-params-live.txt`

A hidden dump routine at `0x7d898` (far, prints `ADDRESS VALUE DESCRIPTION`) goes through this table.
`0x825d3` is the related writer (`0..0x80`, word-sized at 10,2c,2e,32,34,3a,47,53,63,6c,72,75).
We decoded the values from the board RAM dump with the descriptions of the routine itself. The full list is in the txt.
These items are important here:

* Ring: min length 40x5 = 200 ms. Frequency 2400/180..2400/30 = 13.3..80 Hz. T_off_min 380x5 = 1.9 s.
  "Ring Silence, the amount of time before RING" 120x10 = 1.2 s. Distinctive ring type 0 = usa.
  **A US ring (20 Hz, 2 s on / 4 s off) passes all of them**. This agrees with the S1 count of it.
* CID modulation 2 (V.23), CID timing 2 (UK).
* `[0x1fea]` "Impedance match byte" = `2c`, `[0x1feb]` "SI DAA register 17" = `bc`, `[0x1fec]` "SI DAA
  register 18" = `02`. `0x677ff` sends these as tags `7d`, `82` (`& fb`) and `83`. Thus, tag
  `0x7d` is Si register 16 (`2c` = ACT complex AC termination, DCT = 11 TBR21), `0x82` is reg 17, and `0x83` is reg 18.
  That explains the "unexplained" `0x82`/`0x83` traffic in courier_firmware_analysis.md.

## Why no RING - not found

These items are excluded, statically: the ring qualification (above), S70 (zero = accept any), the ring-silence timer
(`0x6e151`, 1.2 s; on expiry, it starts caller ID with tag `0x79` only when `[0x287] & 0x10` is clear,
which is not the condition on this board), and the ring counter (`0x6e3c9..0x6e58c`). The counter reports through
`57bb:c73a -> [0x2ac]` as event 3 (below S0) or 9 (at S0, with tag `0x7a` = answer). **Each state
handler that is assigned to `[0x2ac]` ignores event 3**, or only changes state on it. Thus, that path never prints.
The result printer is `0x62ee1` (ax = code, gate: `[0x202e]` bit 0, `[0x953]` = Q, table at `0x80187`,
`RING` = 2). Its only direct caller is in the routine at `0x5b565`, which has no direct callers.
The code gets to it indirectly. Where code 2 is issued is still open.

## Country selection: the `AT~` family (`country-list.txt`)

The main AT dispatcher is at `0x816a5`. The characters `!`..`Z` index the table at `0x85e50` (base `!`). `~` is
remapped (`sub al,23h`) to the slot after `Z` -> `0x82eaf`, which reads two characters:

| form | action |
|---|---|
| `AT~C?` | list the 28 tables as `nn:name` (`7b59:1ca0`) - **run on the board**, read-only |
| `AT~C#n` | `[0x173]` = `[0xa37]` = n, then `7b59:1b8b` copies table n (`cs:0d42 + n*80h`, seg `7b59`) to RAM `0x1f71` |
| `AT~C!` | gated on `[0x287] & 0x10`, -> `57bb:acae`, unread |
| `AT~F!` | `7b59:1c9c` then four `57bb:1424`, unread |
| `AT~X!` | `lcall 777c:1ebe` then far return to `ffff:0000`-style restart - the `~X!` token in courier_firmware_analysis.md; do not send |
| `AT~P?`, `AT~P!` | only when `[0xa32] & 8`; unread |

The index `[0x173]` = 8 (CTR21) live. `0x1c` means "custom table at RAM `0x17a8`". At boot, `0x583db`
sets `[0x173]` from `[0xa37]`. When the value is above `0x1c`, it uses 8. `AT~C#n` itself writes only RAM.
We did not check if `[0xa37]` goes to NVRAM/flash (for example through `&W`).

## Why `ATGLK` gives OK but `ATGLK2` gives ERROR (static parser trace)

We confirmed this from `2_3_33.XMF`. The selected instructions are saved in
`atglk-parser-2.3.33.asm`. This is a static trace, not a new hardware test.

* The G handler (`0x824af`) has no LK or LK2 prefix check. Its subcommand
  dispatch (`0x82524..0x8257b`) recognizes T, =, I, O, N, R, B and U.
* With two or three characters left, `LK` and `LK2` both use the other-length
  path at `0x825ad`. That path calls the hex parser at `57bb:b245` (`0x62df5`).
  The parser initializes DX to zero, stops at L, restores SI/CX, returns AX=0 and
  clears carry (`0x62dfb..0x62e25`). It does not consume L or K.
* Then G calls `57bb:21a7` (`0x59d57`) with AX=0. When `[0x1a07]&1` enables it, that helper can put
  AL into the pending DSP byte cell `[0x2cb]`.
  Thus, this is not a pure no-op. It does not consume the command text.
* The main dispatcher (`0x816c7..0x816cb`) continues to parse the remaining
  text. L maps to `0x82ae4`, and K maps to `0x82abd`. Their decimal parser
  (`0x62d70..0x62da0`) supplies zero when no digits are present.
* Thus, `ATGLK` executes the zero-byte path of G, then L0, then K0, and it is successful.
  `ATGLK2` executes the same G path and L0, then K2. The K handler compares
  AL with 2 at `0x82ac4`. For values >=2, it branches to the carry-set error return
  at `0x82b15`. The main dispatcher changes carry into ERROR.

This explains the reported responses without an unlock prefix. The command
can change ordinary L/K settings and can send a DSP byte. OK does not prove
that LK is a monitor password. This G dispatcher has no W branch.
