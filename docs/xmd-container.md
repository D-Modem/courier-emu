# The XMD container: sixteen whole flash images, decoded

`firmware/legacy-usrobotics` contains sixteen `.XMD` files of 524,416 bytes each.
They are not update payloads as the XMF and XMP are. Each file is `0x80` of header plus a
**complete 512 KiB flash**, with the boot block and the 80186 reset stub. Until
now, nobody could read them.

## The obfuscation

The obfuscation is a chained XOR over 128-byte blocks. Each byte of a block is XOR'd with one
key byte. The key of a block is the **last plain byte of the block before it**.
The key of the first block is `0x55`:

```python
key = 0x55
for each 128-byte block:
    plain = block ^ key
    key = plain[-1]
```

We tested this. We did not guess it. `IDSDL302.XMD` and `IDSDL302.ROM` are the same
firmware. One is obfuscated, and one is a board dump. Thus, an XOR gives the key of each block,
and we can score each candidate rule against it:

| candidate for block *n*'s key | blocks matched |
|---|---:|
| **last plain byte of block *n*-1** | **199 / 199** |
| last cipher byte of block *n*-1 | 4 / 199 |
| sum of plain block *n*-1 | 2 / 199 |
| previous key + `0x26` | 2 / 199 |
| XOR of cipher block *n*-1 | 1 / 199 |
| sum of cipher block *n*-1 | 0 / 199 |

When we decode `IDSDL302.XMD` with this rule, we get the ROM dump in **524,284 of
524,288 bytes**. The four different bytes are in one 128-byte block at
`0x77f80`. This is the serialisation of the board, next to the distributed image.

`courier_emu/xmd.py` implements the rule, and `load_image` now recognises the
container. The decode check is the reset stub. A correct image ends with
`fa ba a4 ff b8 00 80 ef ea 21 1a 00 fc`, that is, `cli ; mov dx, ffa4 ; mov ax, 8000 ;
out dx, ax ; jmp far fc00:1a21`. `CourierRom` parses this stub to find its
base.

## What is in them

All sixteen files decode to images with these properties: the reset stub parses, the supervisor
signature is present, and the DSP overlay table reads out. All are **analog
Courier V.Everything**. The overlay sets have three shapes:

| images | resident | ov6 | ov7 | ov8 |
|---|---:|---:|---:|---:|
| `IDSDL302`, `SDL0430`, `SDL0430N`, `SV_49` | 27,710 | 11,510 | 7,499 | 7,350 |
| `ID20_401`, `ID20_402`, `ID25_401`, `ID25_402`, and the `28,350`-word `ID20_401`/`ID20_403`/`ID25_403` variants | 28,327 / 28,350 | 11,510 | 7,499 | 7,350 |
| `ID20_403`, `ID25_403` (one build each), `V90XX` | 28,327 / 27,687 | 12,594 | 7,498 | 7,498 |

The `courier-board-21210-capture-403` dump has the third shape. Thus,
we can now compare the DSP set of the 403 board with distributed images, and not
only with the capture.

## What is not in them

**No I-modem.** Each XMD is a V.Everything. The only ISDN Courier firmware
in the tree is `Ie030002`. Its two containers, `Ie030002.nac` and
`Ie030002.xmp`, contain byte-identical payloads (`sha256 0c21e933…`, 753,664
bytes each). The two are update payloads with the base `0x40000`. Thus, neither contains the
boot block or the 386 reset vector. If you run the updater in
[imodem-emulation.md](imodem-emulation.md), it will never make one, because the updater does
not replace the block from which it boots. A bootable I-modem ROM must come from a
board.
