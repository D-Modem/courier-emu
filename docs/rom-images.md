# Flash ROM images

## Complete images

`rom-info` describes a full flash part, not an update payload:

```sh
./courier rom-info IDSDL302.ROM
```

An XMF carries only the application. Thus, its location is a modelling choice.
A ROM ends with the 80186 reset vector. The stub there programs the chip select
that decodes the ROM before it jumps. Thus, the image sets its own location.
For the 1998 Courier V.Everything external ROM, this gives these locations:

- Flash at `0x80000..0xffc00`
- 128 KiB of RAM at `0x00000..0x20000`
- The peripheral control block, relocated into memory at `0x0ff00`. This is the
  window that this harness already hooks.

The ROM also has the ~6 KiB boot block above the application. An update image
never replaces this block. The block contains these items:

- The hardware setup tables
- The copy of itself to physical zero
- The power-on read of the settings EEPROM
- The CRC of the full flash
- A second copy of the SDL loader

`run` also accepts a ROM, and boots it from its reset vector:

```sh
./courier run IDSDL302.ROM --instructions 40000000 --int1-after 7
```

The harness models the peripheral timers from the instruction clock. The model
includes these items:

- The enable gate
- The rule that a zero compare is the full range
- Single-shot and continuous modes
- The sticky max-count bit
- The mask side of the interrupt controller

This model moves the ROM past its timer self-test at `0x80444`. The ROM then
gets to a tick wait. This firmware calibrates the period of that wait from an
external INT1 edge, not only from a timer. `--int1-after` supplies that edge.
`courier_firmware_analysis.md` has the full account. This includes where that
sequence still stops, the confirmation of the latch driver across builds, and
all the option switches.

## ISDN Courier XMP images

`Ie030002.xmp` is an ISDN Courier update payload. It is very different from an
XMF: it has no product text header, and its body is obfuscated.

```sh
./courier xmp-info Ie030002.xmp
./courier extract Ie030002.xmp extracted/Ie030002
```

| File range | Contents |
|---|---|
| `0x00000..0x0007f` | 128-byte header: `USR XMP\0` magic, three small fields, and a 0x70-byte table |
| `0x00080..0xb807f` | 0xb8000-byte payload, every byte XOR `0x45` |

You can find the key from the image without code analysis. Erased flash is
still most of the payload, and the pad byte reads `0xba`. `0xff ^ 0xba` is
`0x45`. When you decode with this key, `0xff` becomes the most common byte
again. The result contains the VRTX kernel banner
(`Copyright 1988, Ready Systems`) and the ISDN rate-adaptation strings
(`SET_V110_ENTRY`, `V110_ATO`).

The decoded payload has three programmed spans. The last span is a two-byte
word at the top of flash:

| Payload range | Size |
|---|---|
| `0x00000..0x5d320` | 381,728 |
| `0x64000..0xaab0c` | 289,548 |
| `0xb7ffe..0xb8000` | 2 |

It is an 80386 image. Payload offset `0x38` shows this: there, the code clears
`dr0..dr3` and `dr7`. The 80186 supervisor does not have these registers. The
code near this offset programs a linear address into `dr0`. It sets the local
and global enable bits in `dr7`. It installs its own INT1 (`#DB`) handler at
`4000:0148`. Thus, the firmware uses hardware breakpoints as a usual runtime
mechanism. This is vector 1. It is different from the `INT1_VECTOR = 13` pin
interrupt of the 80186 in `timers.py`.

Nothing here executes yet. The harness loads the container and the decoded
body. It does not model the board. The decode shows two important items:

- Debug registers. Unicorn does not deliver `#DB` from `dr0..3` that the guest
  programs. Thus, the harness must match breakpoints itself.
- The 0x70-byte header table at offset `0x10` is plaintext, not obfuscated. It
  has a clear structure: some 16-bit values occur many times in it. But its
  layout is not recovered. Thus, `xmp-info` reports it verbatim as
  `header_table_undecoded`. It does not invent fields for it.

The load base is a modelling choice, as it is for an XMF. `FLASH_PHYSICAL_BASE`
is `0x40000`, because the boot code installs its INT1 handler in segment
`0x4000`. The `load_hint` field of the header reads `0x40`. This agrees with
that base in units of 4 KiB, but nothing in the image confirms the unit.

The decoded payload has no protected-mode entry. It has no `lgdt`, `lidt`,
`lmsw` or `mov cr`. This is 386 code that runs in real mode. It uses 32-bit
registers, `0x66`/`0x67` prefixes and the debug registers.

## ISDN Courier NAC images

`Ie030002.nac` is the same firmware in a different container, and it is not
obfuscated. It is **Intel HEX with the ASCII removed**. Each record is a length
byte, a big-endian 16-bit address, a type byte, and that quantity of data
bytes. The big-endian address is the clue. All other data in these images is
little-endian, but Intel HEX writes its address big-endian, also on x86.

```sh
./courier nac-info Ie030002.nac
./courier extract Ie030002.nac extracted/Ie030002
```

| File range | Contents |
|---|---|
| `0x00000..0x0001f` | 32-byte header |
| `0x00020..0xcd1a6` | Binary Intel HEX record stream |
| `0xcd1a7..0xcd1a8` | Two trailing bytes, `e4 a0` |

Header fields:

| Offset | Contents |
|---|---|
| `0x03` | `u32` record-stream length — exactly file size minus header minus trailer |
| `0x08` | Version triple `03 00 02`, matching the `Ie030002` file name: 3.0.2 |
| `0x0f` | Product tag `IE(`, the same tag the `.sdl` loader carries |

The record types are the Intel HEX types:

| Type | Count | Meaning |
|---|---:|---|
| `0x00` | 42,023 | Data |
| `0x02` | 197 | Extended segment address, big-endian, scaled by 16 |
| `0x03` | 1 | Start segment address, `0ce0:0000` |
| `0x01` | 1 | End of file |

ASCII Intel HEX has a checksum byte for each record, but this format does not.
A parse without a checksum uses the stream exactly, from the end of the header
to the EOF record.

The first record of the stream is a type `0x02` that sets segment `0x4000`.
Thus, the image sets its own location at physical `0x40000`. For a NAC, the
harness does not have to assume a base, as it must for an XMF. This is an
independent confirmation of the base that the XMP section above found from the
INT1 handler of the boot code.

The two containers agree exactly. When you flatten the 42,023 data records of
the NAC, you get a `0xb8000` image at `0x40000`. This image is identical, byte
for byte, to the XOR-decoded XMP payload. The NAC never writes 82,879 bytes,
and these are exactly the bytes that read as erased flash in the XMP. Two
containers with independent encodings give the same image. This is the
strongest check that we have on the two decodes. When you validate a new
image, check this again with `nac-info` against the XMP decode.

This item is not recovered: the two trailing bytes `e4 a0`. They are not a byte
sum of the record stream. They do not match the common CRC-16s (CCITT-FALSE,
XMODEM, ARC, MODBUS, KERMIT, GENIBUS) over the stream or over the full file.
Thus, `nac-info` reports them verbatim as `trailer_undecoded`.

The start segment address `0ce0:0000` is physical `0xce00`. This is RAM far
below the flash. The entry after the boot block relocates itself. This agrees
with the code at payload `0x300`, which loads `0x0ce0` into a segment register.
