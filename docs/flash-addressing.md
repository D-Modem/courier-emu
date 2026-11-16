# There is no flash banking

The captures address the board as `A000:9200`, and the pointers in the image are
segmented. Thus, the flash looked banked, but it is not. The mapping is flat, and
the notation is ordinary 80186 real mode.

`physical_start` in each flash capture manifest is **`0x80000`**, and the length
is `0x80000`. Thus, the 512 KiB flash fills CPU physical `0x80000..0xfffff`
contiguously, and:

```text
physical    = (segment << 4) + offset
file offset = physical - 0x80000
```

`ATGLK2=A000:9200` reads physical `0xa9200`, which is file `0x29200`. Segment
`8000` is the base of the window. Thus, in this segment, an offset *is* a file offset.
This is why `9a ed 1e 00 80`, a far call to `8000:1eed`, goes to file `0x1eed`.

`courier_emu.flash_dump.physical` and `.file_offset` implement this. They refuse
an address outside the window. Such an address is a pointer into RAM or into the relocated
peripheral block at `ff00`.

## What it was blocking

Near calls do not need a mapping. The source and the target are in the same segment, thus an `E8`
displacement is the same in file offsets and in segment offsets, and a scan for
them works. Far calls need the mapping. A scan for only the *offset* field finds
nothing, because the same physical address has many encodings. For example, the mailbox
thunk at file `0xf644` is reached as `8f46:01e4`, not as `8000:f644`.

When we resolve them correctly, the 23 visible mailbox send sites become 137. Refer to
[codec-rate-312.md](codec-rate-312.md). There, this method found the tag `2c`
sends.

## What this does not establish

The capture manifests record the assumption for the window: "CPU addresses
`80000..fffff` expose the 512 KiB flash at runtime". They also tell that identical
repeated reads show the consistency of the capture, **not the absence of bank
aliases**. Nothing here changes that. This is established: the far pointers of the image
resolve consistently under the flat mapping (1,400 of
them), and the call graphs of the two mailbox routines close under it. A bank
register that selects between full 512 KiB images is not visible to
that capture or to this analysis.

DSP program addresses use a different mapping. The payload of this image puts
program `0x8000` at file `0x29140`, so `program = 0x8000 + (file - 0x29140) / 2`.
Note that [board-parts.md](board-parts.md) numbers the same code from a payload
origin that is `0x8000` lower.

## What the 512 KiB holds

We scored the image in 8 KiB blocks with instruction fingerprints (C5x forms against x86 forms).
Then we compared the result with the download site that the supervisor actually uses:

| range | contents |
|---|---|
| `00000..17fff` | supervisor code and data |
| `18000..19fff` | a block that looks like C5x, in the supervisor region |
| `1a000..27fff` | supervisor code and data |
| `29140..36e8e` | **the DSP payload that is downloaded**, 28,327 words at program `8000` |
| `36e90..44634` | three DSP overlay images, loaded at program `9d00`, `b000` and `dc00` - see [dsp-overlays.md](dsp-overlays.md) |
| `44634..4bfff` | blank, then a small x86 block at `48000` |
| `4c000..7bfff` | blank |
| `7c000..7dfff` | x86 code or data |
| `7e000..7ffff` | blank |

The origin of the DSP payload comes from the download: program `0x8000` is at
file `0x29140`, so `program = 0x8000 + (file - 0x29140) / 2`.
