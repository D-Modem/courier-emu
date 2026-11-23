# The layout of main211.xmf

| File range | Contents |
|---|---|
| `0x00000..0x001ff` | 512-byte product text header |
| `0x00200..0x1b5df` | 55,792 little-endian TMS320C51 words |
| `0x1b5e0..0xb7fff` | Intel 80186 supervisor plus erased flash padding |

The image is mapped at physical `0x40000`. The usual supervisor initializer is
`5b5e:0410` (physical `0x5b9f0`). The six bytes at `5b5e:0000` are not the
initializer. They are a fatal-error entry: they select error `0x0b` and jump to
the LED blinker at physical `0x5c74a`. This update payload does not contain the
fixed reset vector of the CPU. Thus, the harness starts at the recovered
supervisor initializer.

The DSP area is not one flat load. It is a program image in segments:

| File range | C51 program words | Role |
|---|---:|---|
| `0x002f0..0x0eea3` | `0000..75d9` | reset and boot block |
| `0x0eea4..0x101ff` | `de83..e830` | service overlay; entry at `de89` |
| `0x10200..0x1b5df` | `8000..d9ef` | resident high bank |
