# Result: the boot word is 0x0083, and it selects neither loader

We read this value from the live 20.16 MHz Courier (ID_SDL v4.03d, supervisor 7.4.16, DSP
3.1.2) on 2026-09-07. The DTE port was at 57600 8N1.

```
CDRP1 START
CDRP1 DATA 0010
0083008300830083008300830083008300830083008300830083008300830083
SUM:0830
CDRP1 DONE
```

We did sixteen reads of DSP data `0xffff`, and all gave `0x0083`. The checksum is the sum of
them, and it agrees. First, we verified the placement byte for byte: 4240 of 4240
bytes, zero mismatches. All 2120 `ATGLK2W` writes returned `OK`.

## What 0x0083 does

This is the dispatch of the ROM, with the measured value put in:

```
0686  lacl *-          ; acc = [0xffff] = 0083
0688  lacc @60, 8      ; 8300
0689  and  #fc00       ; 8000
068b  sacl @65
068d  and  #0003       ; 0083 & 3 = 3
068f  bcnd 06c6, eq    ; not taken
0691  sub  #02         ; 1
0692  bcnd 06ab, lt    ; not taken
0694  bcnd 069b, eq    ; not taken
0696  dmov @65         ; @66 = 8000
0699  lacc @66
069a  bacc             ; -> program 8000
```

Thus, when the low two bits are `3`, this is a **fourth mode that transfers nothing**. It
branches to an entry address that is in bits 7:2 of the boot word, shifted
up ten places. `0x83 >> 2 = 0x20`, `0x20 << 10 = 0x8000`. This is exactly the origin of the resident,
and the address that the download of the supervisor goes to.

We confirmed this when we ran the recovered ROM in the emulator with each candidate:

| boot word | outcome |
|---|---|
| `0x0083` (measured) | gets to program `0x8000` |
| `0x0004` (harness assumption) | stops at `0x06dc`, the wait of the serial loader |
| `0x000c` (parallel hypothesis) | stops at `0x0779`, the XF/BIO wait |

## What that means

No ROM loader runs on this board. The ROM of the DSP does a bare warm start.
This means that **the ASIC itself puts the resident into the external RAM of the DSP**
(the two `CY7C199` at program `0x8000`-`0xffff`) while the DSP is held in reset.
The release of the reset is the "go".

This also answers a question that `dsp-map-302.md` raised from the download order:
there is no "go" command after the transfer, because it is not necessary.

## The caveat

We read this value while the modem operated normally, after the download of the supervisor.
Strictly, the measurement shows that **the ASIC holds `0x0083` at DSP
data `0xffff` during normal operation**. That it holds the same value during the
reset window is an inference. Two facts support it. First, all sixteen reads are
identical, thus it is a held level and not traffic. Second, it decodes to exactly
`0x8000`, and an old mailbox word would not do this by chance.
