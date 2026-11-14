# The 20.16 MHz board's full 8K on-chip ROM

Board: ID_SDL v4.03d, supervisor 7.4.16, DSP 3.1.2, 20.16 MHz, serial
`0009540034268322`. This is the unit that `artifacts/courier-board-21210-capture-403` and
`artifacts/dsp-onchip-rom-01` came from. We read it on 2026-09-13 on
`/dev/cu.usbserial-FT4TQOFT`. The 25 MHz board also used this adapter name. The
serial number and the clock identify the unit, not the port.

The image has eight 1K windows, `c5x-onchip-rom-8k.bin`,
`sha256 d57bc46e1bcd6d4dc8872b97bba2d98ba8fb6b8661440c566b534f0b3f82fac9`.

## It is the same part, and mostly the same ROM

`memtest` is **identical word for word** to the result of the 25 MHz board
(`artifacts/dsp-memory-test-2806/run-a`): `PMST` = `00b0`, `MP/MC` = 0, `RAM`
and `OVLY` are already set, `0x0800` and `0x1800` ignore a write, and `0x2400`
follows it. The two boards have a **'C51**.

| region | 20.16 MHz | 25 MHz |
|---|---|---|
| `0000`-`077F` | boot code, 1920 words | **byte-identical** |
| `0780`-`0F7F` | array pattern | array pattern |
| `0F80`-`0FFF` | **array pattern** | **a copy of the `1F80` block** |
| `1000`-`1F7F` | array pattern | array pattern |
| `1F80`-`1FFF` | 128-word mailbox block | **byte-identical** |

In all locations where the ROM is really programmed, the two parts agree exactly. The
full difference between the two 8K images is **96 words at `0x0F9D`-`0x0FFC`**.

## The 0x0F80 block is not mask content

An earlier commit called it "a 128-word block the mask carries twice, at `0x0F80`
and `0x1F80`". That is not correct. The mask has it **once**, at `0x1F80`. The
25 MHz part also returns it from `0x0F80`. This part does not, and it returns only the
array pattern there.

No reading is an accident. We read each board through two independent
execution paths: a kernel at external `0x8000`, and a gadget staged into on-chip
SARAM. On each board, the two paths agree:

| | via `0x8000` | via SARAM |
|---|---|---|
| 25 MHz, `0F80` block | present | present |
| 20.16 MHz, `0F80` block | absent | absent |

Thus, it is a property of the part, not of the read. A mask that duplicates a block
on one die and not on another is not credible. The probable cause is thus a decode difference:
on one part, the top row of the array answers and ignores `A12`.
This is **not established**, and nothing here depends on it. The
programmed ROM is `0x0000`-`0x077F` plus `0x1F80`-`0x1FFF`, and it is identical on the two parts.

## Reproducing

Use the same runner as for the 25 MHz set:

```sh
python artifacts/dsp-onchip-rom-2806/run-board.py \
    artifacts/dsp-onchip-rom-20mhz-8k/at0c00 /dev/cu.usbserial-FT4TQOFT
```

Each run restored the board: `AT` answered and the timer-0 vector came back.
We checked this each time.
