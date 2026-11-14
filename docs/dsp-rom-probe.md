# Reading the board through its monitor, and the DSP mask ROM

The physical target is the 20.16 MHz unit on `/dev/cu.usbserial-21210`, serial
`0009540034268322`. It is a US/Canada external unit with 512 KiB flash and
64 KiB RAM, supervisor 7.3.14 / DSP 3.0.13, dated 03/13/98. These version
strings are the same as in the reference `IDSDL302.ROM`. But they do not prove
that the firmware is identical.

> **Provenance.** `firmware/legacy-usrobotics/IDSDL302.ENG` describes a
> *modified* 20.16 MHz release. It is based on the stock 03/13/98 SDL and adds
> commands for configuration and for memory edits. Do not use the reference ROM
> as an unmodified stock replacement for this unit. The captured image is
> different from the pinned reference in 11,295 bytes.

## The mask ROM has not been read, and the readback route is closed

A TMS320C52 has a **4K x 16 mask-programmable ROM at program words
`0000..0fff`**. The ROM does not fill all of `0000..7fff`. The downloaded image
starts at `8000`. Lower addresses, for example `23f0`, `2100..2593` and `7a80`,
can be external program RAM or installed program RAM. But they cannot be part
of the ROM array.

There are three separate questions:

| question | current answer |
|---|---|
| Does a C52 die contain mask-ROM hardware? | Yes: 4K words at `0000..0fff`. We must photograph the package marking to make the identification physical. Now it is only an inference from the instruction set. |
| Is this unit's ROM programmed with the Courier bootstrap? | This is very probable, but the hardware does not prove it. After reset, the unit accepts and starts a download at `8000`. But an ASIC sequencer that writes external DSP program RAM while the core is in reset is still an alternative architecture. |
| Can externally supplied code or JTAG read it? | Unknown, until we do a test of the mask-programmable protection option on this unit. |

If the TI protection option is programmed, an instruction fetched from off-chip
memory reads invalid bus data for an on-chip program operand. The option also
blocks the emulator. Thus a downloaded `8000` probe and a usual JTAG dump both
fail by design. **On-chip SARAM is not on that exclusion list.** This is the
one gap in the protection.

This is the non-destructive discriminator, if you put an oscilloscope on the
board:

1. Photograph the DSP marking and compare it with the C52/C52LC PJ or PZ
   pinout.
2. **Monitor `MP/MC` at DSP reset.** Low maps the internal ROM, and high maps
   external program memory. The pin is sampled only at reset, but the `PMST`
   bit can change later.
3. Monitor `PS`, `STRB` and sufficient address lines during reset.

An external program fetch at address zero supports `MP/MC = 1`. If there is no
such fetch while the download handshake executes, that supports execution from
the internal ROM.

### Why the host-side route closes

The DSP has a real bulk readback channel to the host. You arm it with a mailbox
tag, pump it with `0x1c` bit 2, and read words at ports `0x60`/`0x62`. We
verified it end to end on hardware. Tag `46` is the nearest to a dump, because
its handler reads four **program** words from a table before it streams them:

```text
84d4  splk  @1e, #8617         ; arm: 16 words from ff80
84d6  lar   ar2, #ff80
84d9  lacl  @5b                ; the index at 03db
84da  add   #860b              ; unmasked
84dc  tblr  *+  ...            ; four program words into ff80..ff83
```

The arithmetic has no mask. Thus the index can get to all 16-bit program
addresses, which include the mask ROM. **All parts that a dump needs are
present, except control of the index.** And we cannot control the index.

`03db` has exactly two writers. `9773` only reads it. `ae98` writes the return
value of `ae12`, and `ae12` is a **six-way priority encoder**:

```text
ae12  call  ade8
ae14  sacl  @7d
ae15  bit   10, @7d ; lacl #05 ; retc tc      ; TI bit 10 is bit 5
ae18  bit   11, @7d ; lacl #04 ; retc tc
ae1b  bit   12, @7d ; lacl #03 ; retc tc
ae1e  bit   13, @7d ; lacl #02 ; retc tc
ae21  bit   14, @7d ; lacl #01 ; retc tc
ae24  lacl  #00 ; ret
```

It does a test of five bits, from the highest bit, and gives zero if no bit is
set. **By construction, its output is `0..5`.** Thus no control of its input can
make the range larger. The shape of the encoder limits the address of the
reader to `860b..8610`. This is not a clamp that you can bypass. Thus the
`84d3` route is closed, whatever its input is.

We traced the input all the same, and we found an important item. `ade8` does
an AND of four cells at `ffb0..ffb3`. **The host can write `ffb1` through tag
`48`.** The handler of that tag is `smmr @7a, #ffb1 ; ret`, with no range test.
This is the only host write into DSP data space that we found with no clamp.
`ffb2` is derived from it. But it does not help here. An AND can only clear
bits, and the other two terms come from a call-setup routine that an idle unit
has not run. We did a direct test in `artifacts/dsp-window-index-01/`: tag `48`
with `ffff`, then tag `46` armed and pumped. The index was still `0`.

**The best remaining lead** is `ffb8`/`fff8`. A streamer has its source address
in a data cell. If a host could write that cell, the streamer would give an
arbitrary DSP *data* read. The set that the host can write includes
`fff0`-`fff3`. That is adjacent to `fff8`, but it does not include it.

### And the datapump is already in hand anyway

The supervisor **downloads the program of the DSP through the I/O ports at each
boot**, and the load base is known:

- source flash `0x29080`, length `0xd87c` bytes = **27,710 words**
- extent flash `0x29080..0x368fc`
- entry requested at DSP word `0x8000`

```text
flash_offset = 0x29080 + 2 * (dsp_word - 0x8000)
```

Two independent checks agree:

- Flash `0x29080` holds the DSP reset code (`LDP #0; SPLK #ffff,@57; SETC
  INTM`). It maps to word `0x8000`, the address that `e3aa` requests.
- The resident sender at words `83d6..83ff` maps to flash `0x2982c..0x2987e`.
  That is in the `[0x29080,0x29880)` startup/sender region, which we identified
  separately.

The older hypothesis `0x29800 + 2·prog` puts word `0x8000` at `0x39800`. Do not
use it.

Thus flash `0x29080..0x368fc` of `courier-board.rom` is, byte for byte, the code
that the DSP executes from word `0x8000`. **If we read this code out of the DSP,
we would only get a copy of data that we already have.** The mask ROM would add
the **internal boot ROM** at words `0x0000..0x0fff`. That part is not in flash.

One question about low memory is still open. The image proves only the explicit
`23f0..23f2` write. The loader at `812b` reads its initial `BMAR` from the
external ASIC cell `ff62`. It copies four words that it gets through `ff58`,
increments `BMAR` for each word, and writes the final value back. Thus no part
of the payload sets that external start value to `2100..2593`. There was an
apparent lead that five more `bldp` sites install those coefficients. An
exhaustive scan closed that lead:

- Seven payload words contain the `57xx` opcode byte.
- Only two of them are instructions: the fixed `bldp *+` at `80a7` and the
  shared loader at `812b`.
- The other five are in tables with roots at `967a`, `a29a`, `a82a`, `c3a4` and
  `dc50`. No branch goes into these tables.

**That was coefficient data that we decoded as code.**

## The monitor

`ATGLK2` is the installed handler at flash `25ba9`. The prefix check is
`cmp word ptr [si],'LK'` and then `cmp byte ptr [si+2],'2'`. After `add si,3` /
`sub cx,3`, `jcxz` leaves the outer `G` in `BL`. Thus a bare `ATGLK2` matches no
selector. There are seven selectors:

| suffix | target | operation |
|---|---|---|
| `=` | `26e20` | Memory byte dump, 16 rows of 16 bytes |
| `R` | `26e8b` | Memory word dump, 16 rows of eight little-endian words |
| `I` | inline `25c45` | Read one I/O port, print one hex byte |
| `O` | inline `25c65` | Write one I/O port: `O<port>,<byte>` |
| `B` | `26eec` | I/O port block dump, 16 rows of 16 ports |
| `N` | inline `25c3d` | `or byte ptr [25e],1`; sets a flag, prints nothing |
| `U` | inline `25c8d` | `clc; ret`; accepted and ignored |

Addresses are hex CPU `segment:offset`. Each `=`/`R` request has a fixed length
of 256 bytes. The offset increments as a 16-bit register, thus a request that
goes past `ffff` wraps in the same segment. If you give only one address number,
the reader uses segment zero.

**The modified reference dispatches differently.** On the reference, `25ba9`
skips `LK2`. It sends the next character through `c800:0024` to an extension at
flash `49022`. The physical handler *must* have `LK2`, and it calls the byte
reader at `26e20` / word reader at `26e8b` directly. The readers are the same.
Do not assume that this board has the extension call or the optional-prefix
behaviour of the reference.

**Hazards.** `I`, `O` and `B` operate on CPU **I/O space**. This is the only
method to get to `0x40..0x5e` and `0x1c` (the ASIC bootstrap window and the
mailbox latches), because `=` and `R` cannot address I/O. But I/O reads can
have side effects. The receive path of the supervisor consumes mailbox replies
when it reads `58..5e`. Also, `B` reads 256 **consecutive** ports without
condition, and you cannot make the range smaller. **`B` can cause problems to a
live call and to a mailbox transaction that is in progress.** `O` is a write,
not a diagnostic.

**Each complete response ends with `ERROR`, but the data before it is
correct.** The cause is a count defect in the parser. `LODSB` at `26e2b`
consumes the colon but does not decrement `CX`. The hex parser does decrement
`CX` when it consumes a character. An isolated execution of the captured
handler for `LK2=8000:0000` prints exactly the 256 expected bytes and returns
with carry clear. It leaves `CX=1`, with `SI` at the carriage return. That test
bypasses the outer AT dispatcher. Thus this is a probable explanation, not a
reproduced end-to-end result.

## What has been captured off this board

| capture | extent | result |
|---|---|---|
| flash | physical `80000..fffff` | 524,288 bytes, `f3a8b013…`, 2,048 pages each read twice with zero retries, 1,107.8 s |
| RAM | `0000..feff` | two passes, 65,280 bytes each, 139.44 s, differing at 44 addresses |
| upper window | physical `10000..1ffff` | two passes, 65,536 bytes each, 144.79 s, differing at 17 bytes |

The three captures are read-only. They use only `AT`, `ATI7` and `ATGLK2=`, with
no upload and no memory-write command. Each capture has an offline audit. The
audit parses the saved responses again and compares them with the stored blocks
and hashes.

The first 256 bytes of flash are exactly the same as in the reference. This
includes the text `INT80186 Modem Functions`. The captured reset stub decodes
to flash base `80000` and entry `fc00:11e9`. These regions are exactly the same
as in the reference:

- the DSP reset/download block `[e370,e598)`
- the CPU byte/word readers `[26e20,26eec)`
- the DSP startup/sender region `[29080,29880)`

11,295 bytes in other areas are different. The 64 KiB windows at physical
`d0000` and `e0000` read as `ff` in all bytes. Erased reads cannot show if
these are separate blank banks or aliases.

**The upper window is the same RAM.** Five new lower/upper/lower groups match
fully. Each upper pass is different from the lower pass at 45 of 65,280
comparable bytes. 249 of 255 full pages match exactly. This is the same rate of
live-RAM change that the two lower passes show. It is not a different device.

**The RAM capture gave the cached settings block.** The emulator did not have
this block before:

```text
RAM 0752..0763: 64 96 03 08 0b 1a 64 96 03 ef 87 1d ef 87 1d ef 87 1d
Settings 1..6:  0, 30, 7, 30, 0, 0
```

The three redundant copies agree. Setting 3 is `7`. Its bit 0 satisfies the
enable condition for serial output that we traced in the firmware.

## The CPU I/O port map

All frequently used ports are **even and byte-wide**, from `0x00` to `0x62`.
They are a peripheral bank with a stride of two. The physical readback confirms
the stride and extends the bank to `0x7e`. That is 64 registers, not the 50
registers that the static sites use.

We made this map with `tools/io_port_scan.py` on the captured image. A linear
sweep loses synchronization in the little-endian datapump and in the
coefficient table. Thus the scanner accepts an `IN`/`OUT` opcode only when a
minimum of four disassemblies that started at earlier offsets agree on it. It
scans only `0x00000..0x29800`, `0x44000..0x7c000` and `0x7e000..0x80000`. A port
loaded into `DX` resolves only when an immediate `mov dx` gets to the site with
no branch, call or non-immediate redefinition between them. The run accepted
**971 sites** and did not resolve **295 `DX` sites**. Thus each count below is a
lower limit. Consensus decoding is a heuristic. Also, if a site exists, that
does not show that its path is reachable.

| port | sites | direction | function |
|---|---:|---|---|
| `0x00` | 12 | r/w | DTE serial data path |
| `0x0e` | 12 | write | Panel latch driver output |
| `0x10` | 30 | r/w | Board latch 0: hook relay, off-hook, NVRAM strobe/data/chip-select/clock; reads return NVRAM ready and data-out |
| `0x12` | 4 | r/w | Board latch 1: indicators, id-strap drive B; reads DTE DTR at bit `0x40` |
| `0x14` | 20 | r/w | Board latch 2: carrier-detect pair, id-strap drives A/C/D; reads ring detect (`0x02`) and strap sense (`0x08`) |
| `0x18` | 101 | r/w | DSP download strobe/status. `OUT 0x18,1` commits a four-word group, `OUT 0x18,4` submits the checksum; reads return ready bits |
| `0x1a` | 86 | r/w | Second strobe/status register, paired with `0x18` |
| `0x1c` | 26 | r/w | Mailbox valid/acknowledge. Bit 1 advertises a reply; supervisor acknowledges with `1c=02` |
| `0x1e` | 28 | r/w | Mailbox command register |
| `0x40`-`0x4e` | 59 | r/w | DSP bootstrap window A: eight byte latches carrying four payload words |
| `0x50`-`0x5e` | 125 | r/w | Window B and the runtime mailbox. `0x58`/`0x5a` carry tag low/high, `0x5c`/`0x5e` data low/high |
| `0x60`, `0x62` | 27 | read only | Third 16-bit read window, high byte at `0x62`, low at `0x60` |

The `0x40..0x4e` / `0x50..0x5e` split agrees with the alternating-window
downloader at `e47b`. It sends four words through the first bank with strobe 1,
and four words through the second bank with strobe 2.

The scan also shows sixteen-bit forms and odd-address forms (`0x03`, `0x05`,
`0x0d`, `0x11`, `0x1f`, `0x2d`, `0x4f`, `0x57`, `0xc3`). Each occurs at one or two
isolated sites, and no emulator run confirms them. They are more probably decode
noise than real registers. The hardware does not drive an odd port. But a dump
cannot show the difference between an unmapped odd port and a mapped port that
reads zero.

**The `0x60`/`0x62` window** is read-only for the CPU. No write site for these
ports exists in the scanned regions. All 27 sites are in one routine at
`01fe0..02128`. An indirect continuation vector at `[0x02d3]` controls this
routine. Each step writes the address of the next step into the vector, and
`call word ptr [0x2d3]` at `00674` dispatches it. Each step reads 16 bits as
`in al,0x62` and then `in al,0x60`. It adds the result to a buffer through
`[0x08a2]`, with a countdown at `[0x02d1]`. The supervisor uses the same
high-then-low convention on `5a`/`58` and `5e`/`5c`. Thus this is a third
inbound 16-bit window in the same family. **The DSP is its producer.** Refer to
the streamers below.

**No code reads `0x64`-`0x7e`.** No instruction that we found in the supervisor
reads or writes a port in that block. The only code that touches it is the
`0x60`/`0x62` reader. This result comes from a raw-byte refutation of each
candidate, not from a boundary heuristic. But it does not prove absence. A `DX`
loaded from memory, as the downloader does at `0e515`, can possibly get to those
ports on a path that this analysis cannot limit.

**Also, the streaming reading of that block is refuted.** Repeated reads do not
pop, advance or change the block in other ways. Thus these are sixteen stable
registers, and the `01fe0` machine polls one register. It does not empty a
queue. A register that gives the same value on each read cannot carry a stream.
Thus the block is not a candidate for a bulk inbound path.

**The `0xc0`-`0xc6` cluster** is a separate coherent block at `08332..083b5`. It
sets `PACS` to `0xe000` and sets `[0xff18]` to `0x10`. Then it reads
`0xc2`/`0xc0` and writes `0xc4`/`0xc6` while it streams `0x1554` words from
segment `0xe000`. An `AT` handler enters it, after a check for the literal `L`
at `08327`. This block programs a chip select again and drives a port bank that
no other code uses. Thus it is a **device-programming path, not a diagnostic
read**. Do not start it on the physical modem while its function is unknown.

## The output latches, and how to drive them safely

`ATGLK2O` writes CPU I/O ports. Thus you can drive the three output latches at
`0x10`, `0x12` and `0x14` from the AT interface. Part of the text that follows is
physical **write** evidence. These were the first writes of any type that we
sent to a unit in this investigation.

Two helpers drive the latches: `0x2771` (set bits) and `0x279b` (clear bits).
The port table is at `0x27c7`. `AH` is the bit mask. `AL` is a descriptor, and
its bit 3 must be set. `AL & 3` selects the port and the RAM shadow:

| `AL` | port | shadow |
|---|---|---|
| `08` | `0x10` | `[0x30e]` |
| `09` | `0x12` | `[0x30f]` |
| `0a` | `0x14` | `[0x310]` |
| `0b` | `0x12` | `[0x311]` - no call site uses it |

**The latches are write-only.** A read of `0x10`/`0x12`/`0x14` gives input
signals, not the latch contents. For this reason, the firmware keeps shadows
and does a read-modify-write on them, protected by `cli`. The initialization at
`0x2728` fills `0x30e..0x312` with `0xff`. Then it sets `[0x30e]=0xfe` and
`[0x30f]=0x7f`. The captured idle RAM holds `fe 7d f5 ff` at `0x30e..0x311`. You
can read it live with `ATGLK2=0000:0300`. No code reads `[0x310]`, and there is
no direct `out 0x14` in that bank. Thus port `0x14` keeps the value written to
it until the next helper call.

**`O` is a bare `out dx,al`.** It writes all eight bits and does not update the
shadow. Thus you must calculate a single-bit write manually from the current
shadow. `ATGLK2O0014,40` does not set bit 6. It clears the other seven bits.
After a write, the shadow and the latch do not agree. The firmware uses its
shadow and does not restore the latch itself. A changed bit stays changed until
an explicit write or a power cycle. Observed: when we set `0x12` bit 1, MR went
off and stayed off. The read-modify-write of the firmware has protection from
interrupts. A shadow read followed by a separate `O` write is not atomic
relative to it.

### Do not write port `0x10`

`0x1490` starts from `[0x30e]`. It sets bit 5 high and bit 3 low, and does
`out 0x0e,0x6f` to select. Then it changes bit 6 as a clock, and `in al,0x10`
reads the data back. `0x1540` restores the shadow and writes `out 0x0e,7`. This
is the bit-banged serial EEPROM that holds the saved profiles of the modem. The
same pattern occurs again at `0x27a6e..0x27b64` in a different bank. Direct
`out 0x10` writes drive these bits and bypass the helper API. Thus a scan of
helper call sites does not see them. **An arbitrary byte written to port `0x10`
can clock the NVRAM interface.**

### Confirmed function of the driven bits

We found these functions when we strobed single bits on a physical unit and
monitored the front panel. These are observations that the user reported, not
captured transcripts. Port `0x14` is active low: `0` lights the indicator.

| port | bit | function | evidence |
|---|---|---|---|
| `0x14` | 0 | CD lamp | observed |
| `0x14` | 1 | CS lamp (lit at idle) | observed |
| `0x14` | 2 | - | no driver located |
| `0x14` | 3 | driven, no visible effect | `0x22d6`/`0x22f3` |
| `0x14` | 4 | AA lamp | observed |
| `0x14` | 5 | ARQ lamp | observed |
| `0x14` | 6 | HS lamp | observed - **disputed, see below** |
| `0x14` | 7 | SYN lamp | observed |
| `0x12` | 1 | MR lamp (lit at idle) | observed |
| `0x12` | 3 | untested | `0x267d`/`0x269d`, gated on `[0xdfd]` |
| `0x12` | 4 | analog path: audible pop | observed - **disputed, see below** |
| `0x12` | 5 | untested | `0x25d0`, gated on `[0x693] & 6` |
| `0x12` | 7 | forced low at init, no driver | `0x2737` |
| `0x10` | 0 | CD line to the DTE | `0x92b1`/`0x9380` set on connect, `0x93a2`/`0x93d9`/`0x96a7` clear on teardown, all gated on `[0x5b4] & 2`; `0x0b45` clears on timer expiry |
| `0x10` | 3, 5, 6 | serial EEPROM bit-bang | `0x1490`..`0x15a5` |

> **Two rows do not agree with [board-verified-403.md](board-verified-403.md),
> which strobed the same bits on this same unit.** The sweep in that file puts
> **no lamp** on `0x14` bit 6. It identifies that bit as the front-panel button.
> The firmware supports this: `0x877cd` starts the self test only when that bit
> *reads low*, and `0x87e34` loops while it stays low, as for an input that is
> released. That file puts **HS** on `0x12` bit 4, where the row above records an
> audible pop. Five other attributions agree exactly between the two files. The
> two sides are panel observations that the user reported, thus no transcript
> can decide. To find the answer, strobe these two bits again, one at a time, and
> watch and listen. Until then, do not use either attribution as a base for more
> work.

Port `0x14` bit 0 drives the CD *lamp* and `0x10` bit 0 drives the CD *line*.
This agrees: `&C` controls the line, and the lamp follows the carrier. Some
panel indicators have no latch bit: RD, SD, TR and RS. We expect that the
hardware connects these to the UART and to the control lines.

### The self-test table, and why strobing was considered safe

`0x26a8` reads a nine-entry table at `cs:0x26f2`. It calls clear on each entry
and waits. Then it calls set on each entry, with interrupts masked. A dispatcher
at `0x26247` calls it with `lcall 8000:26a4` when the parsed value is `5`. We
did not identify the AT syntax that gets to that dispatcher.

| entry | `AX` | port | bit | entry | `AX` | port | bit |
|---|---|---|---|---|---|---|---|
| 0 | `1009` | `0x12` | 4 | 5 | `0209` | `0x12` | 1 |
| 1 | `400a` | `0x14` | 6 | 6 | `020a` | `0x14` | 1 |
| 2 | `100a` | `0x14` | 4 | 7 | `800a` | `0x14` | 7 |
| 3 | `010a` | `0x14` | 0 | 8 | `200a` | `0x14` | 5 |
| 4 | `0108` | `0x10` | 0 | | | | |

The firmware itself drives each of these bits in the two directions. Thus a
manual drive gets to no state that the firmware does not also get to. **That
argument is still correct. But the reading that the group is only front-panel
bits is not correct.** Entry 0 caused an audible pop. Thus this is a wider self
test than a lamp test. Entry 4 is on port `0x10`. Do not use it, because of the
NVRAM risk above, although it is in this table. The firmware drives port `0x12`
bits 3 and 5, but they are *not* in this table. Thus this argument does not
cover them, and we now know that the latch can get to the analog path.

### Port `0x14` bit 2, probed 2026-09-04

The live shadows read `fe 7d f5 ff`. This is exactly the same as the earlier RAM
capture. Thus the strobe was `f1` and the restore was `f5`. This was the
sequence:

1. `AT`, `ATI7`, `ATGLK2=0000:0300`.
2. Two `ATGLK2B0000` sweeps.
3. The write, then two sweeps.
4. The restore, then two sweeps.

Each phase needed two byte-identical sweeps before we accepted it. The restore
was in a `finally` block. The records are in `artifacts/io-latch-bit2-01/`.

**None of the 256 ports changed while bit 2 was low.** The sweep after the
restore is byte-identical to the baseline. Port `0x14` has no refresh path, thus
the bit really stayed low during the two sweeps between the write and the
restore.

That is a null result about **feedback, not about function**. A sweep sees only
the values that the CPU can read back. If a latch bit goes to a DSP pin, a lamp
or an analog gate, it does not show in the peripheral bank. The result shows
that bit 2 does not connect to a device that the supervisor can monitor through
I/O space. It also shows that the write/restore cycle does not change other
items. We did not examine if the bit has an effect on the front panel.

### Bearing on the DSP

No bit that the firmware drives is a DSP control line. Each bit is a
front-panel indicator, a DTE control line, the NVRAM interface or the analog
path. But this does **not** show that the latch bank has no DSP control. We
found no driver for `0x14` bit 2, `0x12` bits 0, 2 and 6, and `0x10` bits 1, 2,
4 and 7. If there is no driver, that is not evidence that no device connects to
the pin. The positive evidence that DSP reset is in a different location is
this: `0xe3ab`/`0xe429` drive `[0xff56]` bit 1 directly. That is a CPU port pin,
not an ASIC latch. This applies only to reset. It does not exclude a different
strap or enable that is related to the DSP.

## The mailbox, from the host's side

**A tag is a command index, not an address.** It selects one of 121 handlers
from a jump table at program `8401`. A value above `0x7f` never gets to the
table. Thus the `host_write(address, value)` shape that the native core models
is **not correct**. The plan to write DSP data `03e6` through the mailbox could
never operate, with or without a commit edge. That is why
`dsp-mailbox-write-01` and the queue runs saw nothing. A missing strobe was not
the cause.

**The host interface is not in the `8000+` image of the datapump, and it is also
not in the mask ROM.** The `bldp` at `80a7` installs the accessor at `23f0` into
low program memory at boot. The accessor decodes as `lacc * ; lamm * ; ret`. The
message cells are `ff57`, `ff5e` and `ff5f` in high data space. **The datapump
contains no `IN` instruction.** All data from the host comes through this
installed helper.

**The wire format.** An outbound message is a 16-bit tag word on `58`/`5a` and a
16-bit value on `5c`/`5e`, with the low byte at the lower port. The compact path
at `0fddb` sends a one-byte tag and a one-byte value, and sets the two high
lanes to zero. The variant at `12cbb` sends two full words from a ring at
`029e..02cd`. Thus the two halves really are 16 bits wide.

**Reads and writes use separate latches.** The interrupt writes `58`/`5a` for
outbound data and reads the same addresses for inbound data. A hardware test
wrote `58`/`5a` and then read them back unchanged. Thus an `ATGLK2I` of these
ports sees the side of the **board**, not the side of the host. A readback must
see that side.

**Bit 0 of `0x1c` is a standing request, and the answer to it is the commit.**
At its end, the interrupt writes the status word back to `1c` and `1e`. Only the
path that had nothing to send clears bit 0 first. Thus when the interrupt writes
that bit back **set**, it shows that a word is in the window. An idle unit reads
`1c` as `fd` on each poll, with bit 0 always asserted. This is because the
supervisor in command mode never has traffic and never answers. A host that
drives these ports through `ATGLK2O` must supply that edge itself.

**Twelve tags have no implementation**: `4c`, `5b`-`5d`, `64`-`6b`. Their table
entry is zero, thus `bacc` would send the DSP to program word `0000`. **Never
send these tags.**

### No host-writable cell yields a program read of the mask ROM

We compared the set of cells that the host can write with the handlers that use
them. The clamps are effective:

- Tag `39` accepts `0..5`.
- Tag `41` accepts `0..12`.
- `LAMM` does a zero extension. TI documents this, and `op_lamm` in
  `native/c5x_ops.ipp` implements it in that way. Thus a large host word cannot
  become negative and go past the `retc geq`.

Also, the one read that *is* a program read is not a data read. `c551` is a
six-entry table of routine addresses, `ca5b ca68 ca75 ca82 ca8f ca9c`.
`tblr @4d` gets a jump target, and the code that follows arms it. **The word
never goes back to the host.** Thus the host cannot see even the twelve
addresses that tag `41` gets to. The only item that is both "host-writable" and
"reads program memory" is a single six-entry jump table behind a clamp.

**This gives one hazard.** The limit of thirteen for tag `41` is larger than the
six-entry table that it indexes. Thus indices `6..12` get the instruction words
that follow the table as routine addresses. Entry six is `7a80`. This is below
the downloaded base but outside the `0000..0fff` ROM window of the C52. Thus it
is an uncontrolled jump into program memory, and we do not know its installed
contents. **Never send tag `41` with a value above five.**

## The DSP's streamers, enumerated and count-verified

We followed the jump table at program `8401` through each handler. This shows
which host tag gets to each streamer variant. It also shows if the source block
of each variant holds program memory or live data. `tests/test_dsp_window_stream.py`
records the result.

| tag | handler | arm stub | source | words | what it exposes |
|---|---|---|---|---:|---|
| `06` | `8489` | `848d` | `0307 03ba 0385 030f 031c 0be6` | 6 | Six discrete live call-state cells (a custom per-word streamer, not the `8684` engine) |
| `45` | `8623` | `8627` | `ff90` **or** `ff00` | 32 / 17 | Live data block; `@1f` bit 10 (`tc`) picks the variant at runtime |
| `46` | `84d3` | `8617` | `ff80` | 16 | First four words table-read from **program** `860b..8610`; the rest live `ff84..ff8f` |
| `47` | `863e` | `8642` | `ffc0` | 12 | Live data `ffc0..ffcb` |
| `57` | `8517` | `8617` | `ff80` | 16 | **Program** words near `85ff`/`8611` plus derived status |
| `58` | `864e` | `8652` | `ffc0` | 25 | Live data `ffc0..ffd8`; also sets `fff8 := 0a40` |
| `73` | `865e` | `8665` | `[fff8]` = `0a40` | 103 | Live DSP data RAM `0a40..0aa6` |
| `78` | `8671` | `8678` | `[fff8]` = `f993` | 5 | Live DSP data `f993..f997` |

Tags `73` and `78` do the two jobs from one handler. First,
`ldp #1ff ; splk @78,#imm` sets `fff8` (page `1ff` puts `@78` at `fff8`). Then
`ldp #007 ; retd ; splk @1e,#stub` arms the `[fff8]` streamer. The arm is in the
delay slot of `retd`. Tag `06` at `8489` uses the same idiom.

We verified this in three steps. We installed the `23f0` accessor. We armed one
tag through its jump-table handler. Then we pumped the resume path `847a` one
word at a time, exactly as a host does with `ATGLK2O001C,04`. Tag `46` is the
reference. It gives `0708 0708 0960 0960 0000...`, which is identical to the
physical `dsp-window-pump-02` capture. Thus the counts of the same harness for
the other tags are reliable.

| tag | data words | `ffb8` walk | `[ffb9]` immediate |
|---|---:|---|---:|
| `46` | 16 | `ff80` → `ff90` | `0x10` |
| `47` | 12 | `ffc0` → `ffcc` | `0x0c` |
| `73` | 103 | `0a40` → `0aa7` | `0x67` |
| `78` | 5 | `f993` → `f998` | `0x05` |

Each count was equal to the immediate of its arm stub. `ffb8` advanced by
exactly that number of cells. At the end, `[039e]` cleared to `0000`. Thus the
streamer disarms correctly and does not chain into the `ff18` continuation.

**A host driver must know two details:**

- The first pumped word of the stream is the **count**, not payload. The opening
  `bd 84b7` of the arm stub emits while `ar1` is still at `ffb9`. Thus word 0
  reads `0010`/`000c`/`0067`/`0005`. Pump `count + 1` times and discard word 0.
- The "pump me again" flag of the emit path and the poll of the resume path both
  resolve to data `0057`. (The `lamm *` of the accessor masks the ASIC address
  to page 0.) Thus **`0057` bit 2 is the handshake cell**.

In that run, the words were zero only because the source blocks are live
call-state RAM, and an idle core has not filled it. The run confirms the
addressing. We record one difference from a board, so that you do not think
that it is a property of the streamer. The minimal `47`/`73`/`78` handlers
return with `ARP = 0`. The resume accessor reads its status word through the
register that ARP selects. Thus the synthetic driver sets `LARP 1` before each
pump. The real mailbox interrupt sets this context when it starts. This does
not change the counts.

Hardware confirms the channel end to end. `artifacts/dsp-window-pump-02/` and
`-03/` are identical, except word twelve: `F6B2` against `F708`. This is a live
measurement in the calculated part of the block, and the program words are
stable. **Arm with a mailbox tag, pump with `1c` bit 2, and read the words at
`60`/`62`.** Only the index is missing.

## Remaining hardware integration

The supervisor code, the DSP sender and the serial parser exist, and they
execute together offline. **We have not found a method to put the monitor in
the RAM of the physical supervisor and transfer control to `0000:2000`.** Also,
the monitor expects a serviceable UART and peripheral mapping when it starts.
It is not a replacement for the reset vector.

An updated supervisor would also need a verified compatible SDL container and a
known restoration path. We have **not** shown that the `T` option of the stock
upload executes a RAM payload. Do not describe it as a RAM-only diagnostic
loader. The modified reference ROM is not a prepared hardware update, and the
raw kernel is also not one.

The supervisor-side counterpart (how code goes *into* the DSP) is in
[the firmware analysis](../courier_firmware_analysis.md#how-the-dsp-is-loaded-and-run).
It describes these items:

- the loader routines at file `0xe370`-`0xe711`
- the nine-entry overlay descriptor table
- the four-image overlay map
- the two transfer engines (`out 0x18` strobes for cold boot, `out 0x1e` for
  runtime swaps)

Segment `0x8000` maps linearly to physical `0x80000`. The resident kernel is
overlay 5: flash `0x29140`-`0x36e8e` → DSP `0x8000`-`0xeea6` in 7.4.16, and
`0x29080`-`0x368fc` → `0x8000`-`0xec3d` in 7.3.14. Each handler address in this
document is in that range and decodes correctly through
`flash = 0x29140 + 2*(dsp - 0x8000)`. This is a cross-check of the two analyses.
