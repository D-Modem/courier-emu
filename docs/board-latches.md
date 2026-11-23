# Board latches, front panel and NVRAM

All board outputs go through one read-modify-write latch driver. We recovered
it at these physical addresses: `0x5e2b0` (set), `0x5e2e5` (clear), `0x5e335`
(read an input port) and `0x5e294` (read the shadow). Callers pass
`AX = mask << 8 | index`. The index table at `0x5e31c` and the shadow bytes
seeded at `0x5e26c` give this map:

| index | port | shadow | contents |
|---:|---|---|---|
| 0 | `0x10` | `0x064d` | hook relay, settings-EEPROM bit-bang pins |
| 1 | `0x12` | `0x064e` | indicators, error-blink code byte |
| 2 | `0x14` | `0x064f` | indicators, board-ID strap drives |
| 3 | `0x12` | `0x0650` | second `0x12` signal group |

The two entry points have special cases for `AX == 0x0408` and
`AX == [0x065c]`. The set path at `0x5e2b4` jumps into the clear body. The
clear path at `0x5e2e9` jumps into the set body. `0x0408` is latch 0 bit
`0x04`. Thus, the firmware **asserts the hook relay when it drives its latch
bit low**. The firmware sets latch 0 bit `0x01` high over exactly the same
window (`0x5db4e` on seizure, `0x5e197` on release).

Each run now reports a `panel` block with these items: the current latch
values, the asserted state of each named line, `off_hook` and a change trace:

```text
i=2191703 port=0x10 value=0xf2 pc=0x5e317 +hook-relay
i=2191740 port=0x10 value=0xf3 pc=0x5e2e0 +off-hook-aux
i=2291289 port=0x10 value=0xf2 pc=0x5e317 -off-hook-aux
i=2291366 port=0x10 value=0xf6 pc=0x5e2e0 -hook-relay
```

The harness names a bit only where the firmware shows the function of the
line. Two runtime DTE lines now also have names:

- `0x5de57` drives latch 2 bits `0x01` and `0x80` as one pair. It clears them
  together at `0x5de65`/`0x5de6b` when the `&C` setting at `[0x09e9]` is zero.
  If not, it sets them together at `0x5de7d`/`0x5de83`. `&C0` is "carrier detect
  always on". Thus, the cleared level is the asserted level, and these bits are
  the carrier-detect pair. It is not known which bit is the DTE pin and which is
  the front-panel lamp. Thus, the harness reports them as `carrier-detect-a`
  and `carrier-detect-b`.
- Input port `0x12` bit `0x40` is DTR. `0x5e375` samples it. `0x5e395` and
  `0x5e3b5` poll it again. The two transitions post supervisor events 6 and 7.
  When S14 bit 0 is set, `0x5e887` changes a low reading into event 10.

`courier_emu/panel.py` reports the remaining indicator bits on `0x12` and
`0x14` with placeholder names and the addresses of their driver wrappers. A
physical reference is necessary to map them to the legends of the front panel.

### Option switches

The option switches of the board are input bits on the same latch ports. The
firmware samples them with the same `mov ax, mask << 8 | index; call 0x2d4a`
form that the straps use. It reads six switches while it builds the profile at
`0x63d31..0x63ec2`. It reads the carrier-detect switch separately at
`0x5e3cf`. The firmware reads a **closed** switch as a low bit, so the sense is
inverted. Each switch also records itself in the shadow word at `[0x0659]`.

We confirmed each row below with a run of `ATI4` with only that input bit pulled
low. Then we compared the profile that the firmware prints. Thus, the effect
column is observed, not inferred:

| switch | port/bit | closed behaviour | observed |
|---|---|---|---|
| `result-codes` | `0x14` `0x20` | `0x63e2e` clears the quiet setting at `[0x092f]` | `Q0` |
| `quiet-answer` | `0x12` `0x08` | `0x63e54` sets `[0x092f]` to 2 | `Q2` |
| `quiet-answer-alt` | `0x12` `0x80` | `0x63e75` sets `[0x092f]` to 2 | none — gated on capability bits `0x08` and `0x20` at `0x63e40` |
| `numeric-results` | `0x10` `0x02` | `0x63e17` leaves `[0x092e]` clear | `V0` |
| `no-echo` | `0x12` `0x10` | `0x63e93` leaves `[0x092d]` clear | `E0` |
| `dtr-override` | `0x12` `0x20` | `0x63d48` leaves S14 at `[0x094e]` clear | `S14=000` |
| `carrier-detect-override` | `0x14` `0x04` | `0x5e3e1` clears `[0x09e9]` | `&C0` |
| `no-auto-answer` | `0x14` `0x10` | `0x63eb5` leaves S0 at `[0x08de]` clear | `S00=000` |

Three of these names are corrections. `[0x08de]` is S0, not a profile source.
Thus, that switch is the auto-answer switch, and its closed position stops the
modem from answering. The switches that had the names `verbose` and `echo` both
*disable* those settings when they are closed. The names now tell what the
switch does when you close it. A physical unit is necessary to map them to the
switch numbers on the case.

`--dip` closes a switch, and you can use it many times. The first use replaces
the default set. `--dip none` leaves all switches open. By default,
`result-codes` is closed, because a DTE that is directly attached needs result
codes. When this switch is open, the modem is really silent. This is the real
behavior. Before, the harness hid it with a direct write to `[0x092f]`:

```sh
./courier run main211.xmf --instructions 4000000 --at AT --dip none
```

### Dedicated-line operation

On a dedicated line, no DTE holds DTR high and no call setup occurs. Thus, the
modem must ignore DTR and keep carrier detect on. `--dip-preset
dedicated-line` closes `result-codes`, `dtr-override` and
`carrier-detect-override`. It leaves `no-auto-answer` open. Thus, S0 keeps its
flash default of 1, and the modem answers on the first ring:

```sh
./courier run main211.xmf --instructions 12000000 \
  --dip-preset dedicated-line --at ATI4
```

The firmware confirms all three settings in its own profile dump: `&C0`,
`S14=000` and `S00=001`.

### Ring detection

The answer machine at `0x70fb4` polls input port `0x14` bit `0x02` with a
direct `in al, 0x14`. Each state in it waits for an edge of that bit. Thus, if
a line never changes level, the machine stays in its first state forever. The
harness now models that bit. An idle line does not ring, and `--ring` drives
the bit with a cadence.

```sh
./courier run main211.xmf --instructions 40000000 \
  --ring --at 'AT#CID=1' --summary
```

The harness has no wall clock. Thus, it changes the cadence from milliseconds
through the instruction count. `0x70fe0` accepts a burst when the tick counter
at `[0x1d50]` gets to the country minimum at `[0x1f5c]`. This build loads that
minimum with 180.

Before, we used that counter as the calibration for the conversion. We assumed
that the burst that gets to 180 is a 2 s North American ring, that one firmware
tick is 10 ms, and that the instruction clock is 1,111 for each millisecond. We
withdraw the two figures:

- The tick is 5 ms. We measured it from the timer 0 compare that each build
  programs on its own crystal. Thus, 180 ticks is a minimum qualification of
  900 ms, not a full burst. Also, the derivation was circular, because
  `machine.py` makes the tick itself at `tick_ms * INSTRUCTIONS_PER_MS`.
- The instruction clock is 4,348 for each millisecond. This value comes from
  the sample count of the codec itself.

See [Hardware time base and audio
path](hardware-timebase-and-audio-path.md).

With that cadence, the answer machine qualifies bursts (`0x70fe9`). It sets the
ring-indicate line (`0x70ff0`). It posts its ring message (`0x71026`) into the
supervisor event queue at `0x02e0`. Two gates are important there:

- `[0x094e]` is `#CID`, expanded from packed-config byte 11 of the parameter
  sector. When it is zero, the two ring message sites do not post. `AT#CID=1`
  enables them.
- `[0x0287]` bit `0x10` gates the second ring path, and it reads zero here.

The answer itself does **not** yet occur. Nothing acts on the queued ring
events, with or without `--with-dsp`. Thus, no `RING` gets to the DTE, and the
hook relay stays released. The next item to recover is the consumer of that
queue.

### Answering

`ATA` gets to the same `0x5dbe7` line-detector wait as `ATD`. An answering
seizure has no dial tone to find. Thus, for `answer`, the DAA qualifies
detector byte `[0x0649]` on a connected line. For `originate`, the DAA
continues to require dial tone:

```sh
./courier run main211.xmf --instructions 40000000 \
  --at ATA --daa-line quiet --summary
```

This changes `NO DIAL TONE` to `NO CARRIER`. This is the correct result when
the modem answers into silence: the line is seized and qualified, and then
training fails for the reason that the SIP section gives. We infer from the
shared wait that `[0x0649]` is the line-side detector and not a counter for dial
tone only. The image does not state this.

### Board identification straps

The scan at `0x5bfc6` identifies the board. It drives four latch lines low, one
at a time (latch 1 bit `0x02`, latch 2 bits `0x40`, `0x10`, `0x20`). It shifts
input port `0x14` bit `0x08` into a four-bit code. `0x5c051` finds that code in
the table at `0x5c06b`. `0x5c05c` stores the result as the board capability byte
at `0x0a02`. We know the function of two capability bits:

- `0x08` is "settings EEPROM fitted". All NVRAM paths test it.
- `0x40` sends `0x5bb0f` directly to the fatal blinker.

| code | capability | | code | capability |
|---:|---|---|---:|---|
| 2 | `0x29` | | 9 | `0x28` |
| 5 | `0x14` | | 12 | `0x28` |
| 7 | `0x22` | | 13 | `0x22` |

Codes 11 and 14 map to `0x42` and `0x48`, which have the fatal bit. All other
codes are empty table entries, and `0x5c064` stores zero. `--board-id` drives
the straps and rejects the codes on which the firmware cannot run. Its default
is 2. This is the lowest code for a board with an EEPROM and no fatal fault.
`none` leaves the lines floating. The firmware reads this as no board.

You cannot find from the image which of 2, 9 and 12 a given board revision
straps. They are different only in capability bit `0x01`, and the function of
that bit is not known. The default is a constrained inference, not a verified
board ID.

Real hardware cannot have floating straps, and the firmware sees this
condition as a fault. This has two visible results:

- `0x667cb` maps a zero or `0xff` capability byte directly to result code 4.
  Thus, `ATI1`, `ATI2`, `ATI3`, `ATI7`, `ATZ` and `ATS30?` answered correctly
  and then reported `ERROR`.
- `0x82ea4` selects the product code from capability bit `0x08`. A board with
  an EEPROM answers `ATI` with `3368`. A board without one answers `3368A`.

The settings store is a 93C66-class Microwire EEPROM (256 x 16). The firmware
bit-bangs it on latch 0. The driver is at `0x5ccc0..0x5cdf9`:

| routine | role |
|---|---|
| `5b5e:16e0` | read word; `[0x8d2]` = address, result in `[0x8d3]` |
| `5b5e:1746` | write word; `[0x8cf]` = address, `[0x8d0]` = data, EWEN/EWDS bracketed |
| `5b5e:17c6` | build and clock the twelve-bit command frame |
| `5b5e:17d2` | shift bits most-significant first |
| `5b5e:1801` | presence poll; input port `0x10` bit `0x08` must read high |

`5b5e:17c6` makes `bx = ((opcode & 3) | 4) << 8 | address`. It rotates this
value left by four before it clocks twelve bits. The twelve bits are one pad
bit, the start bit, two opcode bits and an eight-bit address. The latch bits
are: `0x20` chip select, `0x40` clock, `0x10` data in on write and data out on
read.

To attach a persistent image, use `--nvram`. If the file does not exist, the
harness makes it blank (all ones, as an unprogrammed part). After the run, the
harness writes the file back:

```sh
./courier run main211.xmf --instructions 7000000 \
  --at AT --nvram settings.nv --summary
```

For a deterministic `IDSDL302.ROM` boot, you can attach the recovered
six-record settings cache in memory. This also attaches the `+S` register
defaults that `AT+SF` loads. Without them, the DSP dials at zero level, as the
board did. This leaves all other EEPROM words erased. It does not change the
blank `--nvram` behavior:

```sh
./courier run IDSDL302.ROM --instructions 60000000 \
  --tick-ms 10 --nvram-fixture idsl302 --at AT --summary
```

The 20 MHz 302/403 ROM serial adapter runs these parts of the firmware: the
attention detector, the parser and the UART transmit path. For the tested board
settings, the captured 403 command and the autobaud limits, see
[ROM serial execution](rom-serial-adapter.md).

The fixture reverses all three byte encodings that each redundant record uses.
You cannot use it together with a persistent `--nvram` image.

`nvram` in the result reports these items: reads, writes, erases, the
write-enable latch, the programmed words and a command trace.

### Why the EEPROM stays untouched at boot

`reads` and `writes` stay at zero through boot and plain command mode. This is
the behavior of the firmware itself, not a gap in the device model. Three
separate findings explain it.

**There is no boot-time NVRAM profile load.** All eleven call sites for the two
driver entries are in banked segment `0x81b8` (`0x8374x`, `0x8386x`, `0x838b9`,
`0x84de8`). They are command handlers:

- A word-by-word diagnostic dump that prints through the resident
  character-output helpers
- A six-word store in which the last word is a CRC-8 over the four words before
  it
- A config write at `0x84dc7` that parses a literal `=PW` and programs word 0
  to `0x4000` or `0x0000`

None of them is on the reset path. At boot, the firmware fills the working
profile at `0x08de..0x095b` from a 77-byte flash default table, which it copies
at `0x63b72`. The saved profile at `0x095c..0x09d9` is a plain RAM shadow
(`81b8:35ee` saves, `81b8:3601` restores and applies again).

**The diagnostic and store paths are gated on `[0x0a02] bit 3.`** That byte is
the board capability code from the strap scan at `0x5bfc6`. The scan drives four
lines low, one at a time (latch 1 bit `0x02`, latch 2 bits `0x40`, `0x10`,
`0x20`). It shifts input port `0x14` bit `0x08` into a four-bit index. Then it
finds the index in the table at `0x5c06b`. When that input floats high, the
index is `15`, the table entry is `0x00` and `0x5c064` stores `[0x0a02] = 0`.
Codes `2`, `9`, `12` and `14` give `0x29`, `0x28`, `0x28` and `0x48`. All of
these have bit 3. The boot gate at `0x5bbb5` branches on the same bit.

**The persistent configuration is in a separate parameter flash, not in the
XMF image.** The harness gets to the routine at `0x7e07c` at its `startup-crc`
milestone. The routine does these steps:

1. It scans four 4 KiB blocks from segment `0xf800` (physical
   `0xf8000..0xfbfff`).
2. It calculates the checksum of bytes `0x000..0xffd` into `[0x06fc]`.
3. It compares the checksum with the word at `0xffe`.
4. It keeps the block with the highest 32-bit version at `0xffa`.

`main211.xmf` maps at `0x40000..0xb7fff`. Thus, that region is empty here, `ES`
comes back zero, and `0x7dffa` skips the full unpack. Bytes 0..4 of a valid
block become `[0x0a06..0x0a0a]`. Byte 4 becomes **`[0x0a03]`**. This is the
capability byte that gates the profile restore at `0x6014f`. It also selects
whether `0x63b6d` loads defaults into the stored profile at `0x095d` or into the
working copy at `0x08df`.

A synthesized block confirms the mechanism. If you write a 4 KiB record at
`0xf8000` with a matching checksum, the search returns `es = 0xf800` and loads
`[0x0a03]`. To get to command mode from there, more of the parameter block must
be filled than a stub gives. Thus, the harness does not supply a stub. That
path needs a real parameter sector, recovered from hardware.
