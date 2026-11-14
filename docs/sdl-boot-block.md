# The Courier boot-block flash loader

FreeLSD and SDL.EXE communicate with this downloader. It is in the top 16 KiB
flash block. It is a different mechanism from the `AT~X!` XMODEM
updater of the application. It accepts a raw 512 KiB flash image, not an `.XMD` container, and
it uses its own binary protocol. We disassembled all of this from
`artifacts/courier-board-21210-capture-01/courier-board.rom`, the
supervisor 7.3.14 unit of the user. The physical addresses are the file offset plus `0x80000`, and
segment `fc00` is file `0x7c000`.

`courier_emu/sdl_download.py` implements the host side.

## Reset to RAM

`0xffff0` programs the chip select that decodes the ROM, and then jumps:

```
cli ; mov dx,0xffa4 (UCSST) ; mov ax,0x8000 ; out dx,ax ; jmp far fc00:11e9
```

`fc00:11e9` sets the segment registers to zero, sets `SP=0xf8`, and writes RELREG. It replays
`0x24` word records from `fc00:113e` and 9 byte records from `fc00:11ce` as
`OUT`s. It copies `0x113d` bytes of itself to physical zero, and it dispatches `INT 13h`
through the IVT that it copied. Thus, the loader executes from RAM. For this reason,
it can erase the block from which it came.

## Which way it goes

`fc00:07ad`:

1. The word at `f7ff:000a` (`0xc000` on this board and on `IDSDL302.ROM`) sets
   the installed image type in `cs:[0x127]`: `2` for that value, `4` for other values.
2. `fc00:0702` identifies the flash: it writes `0x90` to `0xffff0`, reads the manufacturer and the
   device, and writes `0xff` to restore. `0x4470` selects the seven-block table and
   `cs:[0x126]=6`. `0x2274` selects the five-block table and `4`. All other values
   are not supported, and the loader refuses them.
3. `fc00:08a3` checks the image CRC. If the check fails, the loader goes directly to the download
   loop at `fc00:07f2`.
4. If the CRC is good, it reads `in al, 0x12`. It boots the application, unless
   `!(al & 0x14) && (al & 0x40) && !(P2PIN & 0x40)`. `0xff5a` is P2PIN. Thus, that
   last term is an input pin. The `XMODEM.TXT` of 3Com documents the same condition
   as DIP switches 1, 5 and 10 on, with 8 off (7 on internal units). We did not find here
   which switch controls which bit.
5. If not, it does `cli; RELREG=0x00ff; jmp far f7ff:0005` into the application.

## Autobaud, and the knock

`fc00:0d38` arms the receive path. `fc00:0de6` and `fc00:0f61` sample the
receive line as a **P2PIN bit under timer control**. This is software serial, not the
UART. They assemble one character, and they require `(byte & 0x5f) == 'A'`. The captured
timer value becomes B0CMP. Thus, the host selects the rate when it sends `A`. `fc00:0e52`
installs `0x802a` for the recognised case.

Then eight bytes go to `0x12d`, and `fc00:0d0c` compares them with the
constant at `0x141`:

```
02 45 07 48 6d 58 09 08
```

This is the same value that the `.XMD` header contains, inverted, in its first eight
bytes. Byte 5 is the product discriminator (`0x58` Courier, `0x59` on
`SV25.XMD`). If the first byte is `'!'`, the loader boots the application. All other values
print `MODEM FIRMWARE IS CORRUPTED. FIRMWARE DOWNLOAD IS NECESSARY.`, and the loader arms again.
Thus, it is safe to try a failed knock again.

## Entering the loader from the application

SDL.EXE must first put a running modem into the loader. The third-party flash
write-up of Gene Lowry (`README.1ST` in the Metropoli `SD960123.ZIP`) calls
this an undocumented `AT^BE^GHmX^I^H` command. It says that the modem answers
`3F`/`E3`/`E4`, the MR LED goes off, and there are ten seconds to continue.
It is not an AT command. The eight bytes are the knock above.

The application recognises them in the serial receive path, on the board ROM
(supervisor 7.3.14). `0x89a06` masks the byte with `0x7f` and calls through a
state vector, `call word ptr [0x0b7c]` at `0x89a09`. A carry return means that the
byte was not consumed, and the code continues to the normal character handling. The
vector is a chain of one-byte states at `0x8b479`:

| State | Expects | On match |
|---|---|---|
| `0xb479` (idle) | `02` | `[0xb7c] = 0xb487` |
| `0xb487` | `'E'` | `0xb49b` |
| `0xb49b` | `07` | `0xb4af` |
| `0xb4af` | `'H'` | `0xb4c3` |
| `0xb4c3` | `'m'` | `0xb4d7` |
| `0xb4d7` | `'X'` | `0xb4eb` |
| `0xb4eb` | `09` | `0xb4ff` |
| `0xb4ff` | `08` | `cli; jmp far a764:198b` |

If a byte does not agree, the vector resets to `0xb479` and returns carry. Thus, the byte is
processed as ordinary input. There is no `AT` prefix, and nothing is compared after
the eighth byte. If you send the ten bytes in the README, the `AT` has no effect. The chain hard-codes `'X'`.
Thus, it is the Courier product byte, and `0x59` would not agree.

`a764:198b` is physical `0xa8fcb`. That is the reset entry of a **copy of the
loader in the application**, with its base at physical `0xa7640` (file `0x27640`).
It does the same as `fc00:11e9`: `cli; cld`, the segment registers and `SS` set to zero,
`SP=0xf8`, `0x24` word records replayed from `cs:0x1898` and 9 byte records
from `cs:0x1928` as `OUT`s, `0x1897` bytes copied to physical zero, then
`INT 13h` through the IVT that it wrote (`[0x4c] = 0x0848`).

That copy is a different build from the copy in the boot block. It is not
byte-identical to `fc00:0000..1b13`, and the knock constant is at base
`+0x13c` (file `0x2777c`), not at `+0x141`. In the SDL images of 1994-95, the
banner text follows the constant. Thus, the data hit for the eight bytes in each
image is this loader copy. It is not a table that the state machine reads.

Not traced: the source of the `3F`/`E3`/`E4` acknowledgement and of the ten-second timeout.
The state machine sends nothing. Thus, they occur after the jump, in
the loader. The same eight bytes occur in each SDL image from 5/25/94 to
3/13/98. We found the state machine itself only in 7.3.14.

## Identify

`fc00:0992`. The application contains a byte-identical copy at file `0x28654`:

| step | who | bytes |
|---|---|---|
| 1 | modem | `0xe3` |
| 2 | modem | sets B0CMP `0x8082` |
| 3 | host | `'Q'` |
| 4 | modem | sets B0CMP `0x8102`, echoes `'Q'` |
| 5 | modem | restores the autobaud rate, sends two identity bytes and two zeros |
| 6 | host | image type (`2` or `4`), CRC high, CRC low |

The loader uses three B0CMP values: `0x802a`, `0x8082` and `0x8102`.
`baud = clock / (8 × (CMP+1))` gives 58605, 19237 and 9730 on a 20.16 MHz
part, that is, 57600, 19200 and 9600. **The host must follow the two rate changes**. It sends
its `'Q'` at 19200 and reads the echo at 9600.

## Erase

`fc00:043d` goes through the block indices from `cs:[0x108]` to `cs:[0x126]`. The start is
2 for a 256 KiB image on a 512 KiB part, and 0 for other cases. The loader skips indices 4 and 5.
From the table at `fc00:0393`:

| idx | physical | size | erased |
|---:|---|---|---|
| 0 | `0x80000` | 128K | type 4 only |
| 1 | `0xa0000` | 128K | type 4 only |
| 2 | `0xc0000` | 128K | yes |
| 3 | `0xe0000` | 96K | yes |
| 4 | `0xf8000` | 8K | **never** |
| 5 | `0xfa000` | 8K | **never** |
| 6 | `0xfc000` | 16K | yes |

Thus, the only regions with permanent protection are the two 8 KiB parameter blocks.
On this board, they contain only a far jump at `0xfbff0`. **Block 6 is the
loader itself**, and each download erases and programs it again.

## Records

`fc00:0b3c` drops the write gate of P1LTCH bit 6. It sends each received byte to the
handler in `cs:[0x10e]`, a state machine at `fc00:0b65`:

```
[len] [offset high] [offset low] [type] [data ...] [checksum]
```

The offset field loads DI. Type `2` puts two big-endian bytes into ES. Type `0`
programs `len` bytes as little-endian words at ES:DI. It advances DI by two for each
word, and it pads an odd tail with `0xff`. All other types stop the stream and
return `0x17`. The sum of all bytes, with the checksum, must be zero.

The programming primitive at `fc00:0c67` is the Intel `0x40` word write with a
status poll. A record for flash that the loader did not erase cannot succeed.

## CRC, and how the download ends

`fc00:026f` is a CRC-16 without a table, with the seed `0xffff`. The spans that it reads depend on
the image type, from `fc00:08a3`:

- type 2: `0xc0000..0xf7ffd`
- type 4: `0xc0000..0xfffff` **then** `0xc0000..0xf7ffd`, because the longer path
  continues into the shorter path. Four blocks are added two times, and the
  parameter blocks and the boot block are included. The two loops start at segment
  `c000`. This is what the ROM does.

Our new implementation gives the same word as the one stored at `0xf7ffe` in the two real images:
`0x3e73` for the board, `0x53bc` for `IDSDL302.ROM`. This confirms the algorithm.
In download mode, the loader calculates that word itself and programs it at
`fc00:0956`. Thus, a record stream must not change those two bytes.

The modem sends `0x15` before the erase and `0x16` when the erase completes. After
the records, it sends: `0x14` complete, `0x17` stream ended, `0x18` record checksum
error, `0x19` image CRC mismatch, `0x1a` program timeout, `0x1b` erase failed,
`0x1d` block erase error. Then it reboots into the application.

A CRC mismatch is not fatal. The word is never programmed. Thus, at the next reset, the check
at step 3 fails, and the modem goes back into this loader. The only period without recovery
is a failure while block 6 is erased or while it is written.

## Building a stream

```sh
.venv/bin/python -m courier_emu.sdl_download IDSDL302.ROM \
  --preserved artifacts/courier-board-21210-capture-01/courier-board.rom \
  --image-type 4 --output artifacts/sdl-download-idsdl302-type4
```

`--preserved` supplies the blocks that this download will not erase. Thus, the expected
CRC is calculated over the actual contents of the flash, and not over the
image alone. The report contains the CRC to give to the modem, the erased and
protected spans, and the result of a replay of the stream through a model of the
state machine of the loader. For `IDSDL302.ROM` at type 4, that is 507,902 bytes
programmed in a 527,803-byte stream with no mismatches, with the expected CRC `0x952d`.
At type 2, it is 245,758 bytes with the expected CRC `0x53bc`, the word that the reference ships.

Type 2 does not erase blocks 0 and 1. In these blocks, `IDSDL302.ROM` is different from this
board in 180 bytes, which include the `LK2` dispatcher at `0x25ba9`. Thus, a type 2
download would install only a part of the modified image.

## What is verified, and what is not

Verified offline: the CRC algorithm against two real images. The record format, the
checksums and the coverage, by a replay of a generated stream through a model of
`fc00:0b65`. The erase set and the protected blocks. The knock constant against
the boot block.

Not verified: all items on the wire. We transcribed the autobaud, the knock exchange, the
three-rate identify handshake and the erase and result timings
from the disassembly. We never ran them against hardware or an emulated
loader. The next step is to run the boot block under a harness of the `recovery.py` type and to operate
`Session` against it. This would close that gap without a change to the modem.

Tests:

```sh
.venv/bin/python -m pytest tests/test_sdl_download.py -q
```
