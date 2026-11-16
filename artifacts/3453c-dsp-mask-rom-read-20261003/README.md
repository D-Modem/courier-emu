# Recovered 3453C DSP mask ROM

`dsp-mask-rom-0000-0fff.bin` contains **4,096 words / 8,192 bytes**, little-endian, at DSP program addresses **0000..0FFF**.

SHA256: `262e4baa49590bb6ca4a473dffb8a8aee67c9fae020ce92ac3f59e077314f1d6`.

Two 0000..1FFF mapped windows that we requested independently were exactly the same. Their upper half, 1000..1FFF, is the same as the patched resident downloaded from flash, with the monitor dispatcher hook. This shows that this upper region is still external RAM. The lower 4K words are different from the unmapped program RAM at 4,090 of 4,096 positions. They contain a coherent vector table that starts with `B 0F46`. The boot code at 0F46 uses I/O 8057/8058. This agrees with the first-download protocol of the 3453 board.

The live PMST was **18B8 before and after** each capture. After this, the monitor returned D541. Each individual ROM read masked interrupts, temporarily cleared only PMST.MP/MC, read one word, and restored the mapping and the status before it replied. The revision stays installed.

The image that we saw supports a 4K-word ROM that is compatible with the suspected C52-class part. This is not a wider confirmation of the exact die model. The older ROM of the 302/403 board is a different image.

`manifest.json`, `sample-verification.json` and `window-verification.json` keep the provenance and the checks. `boot-loader.asm` is the bootstrap excerpt. `mask-rom-linear.asm` is a linear decoding that also includes tables/constants.

The comparison with the older Courier in `rom-comparison.json` finds 157 word matches at the same address
in the first 4K, with large relocated blocks (which include
496 words at old 0250 / new 00D0). The layouts and the bootstrap protocols are different.
This is not a percentage of code similarity. No Cisco MICA DSP ROM is available
for a binary comparison. Its MP/MC switching alone does not establish ROM
compatibility.

The acquisition and extraction scripts keep the original procedure. They
refer to the local diagnostic monitor, the patched firmware and the unmapped program
capture from the investigation. The manifest records those prerequisites, and they
are separate from this ROM evidence bundle.

## Content map, 0030–0F45 (2026-10-04)

This is a static analysis of the dump. The table identifications are numerical (frequency
response, decoded point pairs, phasor magnitudes). The routine names are
**inferred from disassembly**, and we did not trace them in execution.

### Tables, 0030–09ED

| Range | Contents |
|---|---|
| 0030–007F | 80-tap symmetric low-pass FIR, DC gain 8 (likely ×8 interpolator). Flat to 0.02·fs, −6.7 dB at 0.04·fs, ≤ −70 dB from 0.08·fs |
| 0080–00BF | V.34 line-probing signal, one 64-sample period: flat spectrum on bins 1–25 except 6, 8, 12, 16 (150–3750 Hz at 9600 Hz, omitting 900/1200/1800/2400) |
| 00C0–00FF | Packed signed-byte (x,y) points, ±16/±48 grid |
| 0100–01BF | 192 packed points, odd multiples of 8 to ±72; consistent with V.32/V.32bis cross constellations, unproven |
| 01C0–02BF | 256 packed points: full 16×16 odd-coordinate square, scaled ×4 |
| 02C0–055F | 672 packed points on a rotated lattice in groups of four, ordered by increasing energy (V.34-style ordering) |
| 0560–058F | Small index/bitmask tables |
| 0590–068F | V.34 point-label lookup, high bits (16×16 words of byte pairs); see below |
| 0690–06AF | Point-label LSB map for 0590 (1 bit per cell); see below |
| 06B0–06B7 | Labels of the six outermost points (and sentinel); see below |
| 06C4–06DB | 12 unit-circle points at 30° steps, radius 11585 (0.707 in Q14) |
| 0700–099F | Four 168-word V.34 transmit-scale tables (0700, 07A8, 0850, 08F8); see below |
| 09A0–09ED | Unit-magnitude (16384) phasors: four full-period rotations with steps −68.57°, −72°, −80°, −90° (17/21, 4/5, 7/9, 3/4 cycle); assignment unknown |

### Code, 09EE–0F45

Only 0A4C, 0CC1, 0DAF and 0E5E are direct call targets in the ROM.

| Address | Inferred role |
|---|---|
| 09EE | sin/cos polynomial (constant 0x6488 = π·8192) |
| 0A21 | arctangent: quadrant fold, divide (0A4C), polynomial |
| 0A4C | signed division |
| 0A68 | 64-point radix-2 complex FFT (6 stages); twiddle table 0ABD–0B0C |
| 0B0D | interrupt handler: saturates two values, packs bytes into MMR `@31`, `rete` |
| 0B21–0BB6 | complex MAC / coefficient-update kernels; 0E13–0E70 wraps them for 64/32/16 taps, then jumps via `@48` |
| 0BB7 | table builder using binomial kernel 0C1E (8, −28, 56, −70, …); possibly V.34 shell-mapping tables |
| 0CEE–0DAE | V.34 receive-side inverse shell mapper and deframer (`mpyu` over data 5440/5470/54C0); 0DAF writes bits into a 128-bit ring at `@28`. Firmware equivalent: 302 overlay 6 BCAF (0D17 = BCD8) |
| 0DFF | transmit-scale table lookup (see below); firmware copy at 302 overlay 6 A7C0 |
| 0E71 | scrambler-like step, 4 bits per call |
| 0E86 | complex autocorrelation over three lags into `@68–@77` |
| 0C26 | V.34 precoder solve: three complex taps into data 4B60, zeroed on a stability-check failure. Firmware copy at 302 overlay 6 B64A writes data 0850 |
| 0ED5 | 3-tap precoding filter with modulo wrap (coefficients 4B66/4B69), quadrant table 0F24; likely V.34 precoder |
| 0F28 | clears external data buffers at FBCC and F8CC |

**The standard 2.3.33 firmware does use this library at runtime**. It
switches PMST.MP/MC. (An earlier revision of this README said that it probably
did not, because PMST read 18B8, with MP/MC set, each time that we sampled it.)
The program RAM is in the RAM capture (`../3453c-dsp-memory-read-20261003/
dsp-program-fast-0000-7fff.bin`). All of it is in the standard
`2_3_33.XMF`:

| RAM | What it does | Callers |
|---|---|---|
| 14D4 / 14DA | `apl @07,#fff7` (ROM in) / `opl @07,#8` (ROM out), saving ST0 | 9 brackets |
| 14E0 | ROM in, call 09EE (sin/cos), ROM out | 17 |
| 14EF | ROM in, call 0A21 (atan), ROM out | 6 |
| 14FE | ROM in, call 0A4C (divide), ROM out | 3 |

The nine 14D4…14DA brackets:

| RAM | ROM use |
|---|---|
| 160A | call 0A68, the 64-point FFT |
| 17DE | `tblr` 0080 + (n & 3F), the line-probe signal |
| 1BAE, 1CC5 | `macd` × 80 with coefficients at 0030, the FIR |
| 322C, 56DD, 65C6 | `tblr` 00C0 + n, the small constellation |
| 359A | `tblr` from a base held in `@28` (not traced) |
| 5310 | call 0B6A, a complex MAC kernel |

The byte-identical table copies that we found earlier are in the images of the 302 family
(`IDSDL302.ROM` and similar). Their older C51 mask has none of this. The
emulator already handles the switch: `C5xCore` selects the ROM region from the
live PMST.MPMC on each access (`native/c5x_core.cpp`).

### Transmit-scale tables, 0700–099F

There are four tables of 168 words, each with 28 rows × 6 columns. The columns are the V.34
symbol rates 2400–3429. The rows are the 14 data rates 2400–33600, two rows for each
rate. The zeros are exactly on the rate/baud combinations that V.34 does not permit. All
non-zero values are in 0x5A82–0x7FFF (1/√2 to 1.0), that is, mantissas of a
scale. The exponent of the scale is held in a different location.

The consumer is ROM 0DFF. It is identical to overlay 6 A7C0 of `IDSDL302.ROM`
(tables at A84E there, in the same sequence):

    index = base + 12·rate + baud + 6·[FF38 bit 10] + 168·[precoder on] + 336·[FF38 bit 14]

| Term | Meaning | Evidence |
|---|---|---|
| `@5b` | symbol-rate index 0–5 | same cell indexes the baud and carrier tables (`docs/codec-sample-rates.md`) |
| `@7c` | data-rate index 1–14 (base = table − 12) | caller A77B loops it over all 14 rates, writing a per-rate result to data 0836 |
| +168 | precoder taps non-zero | the six ORed words are data 0850–0855, which the precoder solve (B64A) fills or zeroes at B6F6 |
| FF38 bit 10 | auxiliary channel (MP bit 28) | A5C5 clears it locally unless the far end's MP (0340) has it |
| FF38 bit 14 | constellation shaping (MP bit 32); set = shaped tables 0850/08F8 | A74B, below |

### MP layout (302 overlay 6)

FF38–FF3F is the **outgoing** MP, built at A2F5. FF38 keeps bit 15, takes
bits 14/13/10 from the local options (0345 << 10 & 6400) and always sets bit 12.
It sets bit 0 (type 1) when it carries the local precoder taps 0850–0855
into FF3A–FF3F. FF39 is the data-rate mask from A35E. Thus, the A7C0 lookup
follows what this modem sends.

The coroutine A4D8–A522 collects the **received** MP. The bits shift
LSB-first into FF48+ with a reflected CRC-16 (poly 0x8408, init FFFF). There are 0x30
bits, or 0x90 when bit 0 (type) is set. Then 16 CRC bits are compared at A521.
On a match, A533–A552 copies FF48 → 0340 and FF49 → 0341. For type 1, it copies the six
coefficient words to the remote precoder at 0856–085B.

Each buffer word is one 16-bit block after a start bit (MP bit 18 onward):

| Word 0 bit | MP bit | Field | Evidence |
|---|---|---|---|
| 0 | 18 | type (1 = precoding coefficients) | adds 96 bits = six coefficient words |
| 2–9 | 20–27 | max rates, 4 bits each direction | `and #03fc` at A560/A565 |
| 10 | 28 | auxiliary channel | both ends required (A5C5) |
| 11–12 | 29–30 | trellis encoder select | bit 12 always set on transmit |
| 13 | 31 | nonlinear encoder | |
| 14 | 32 | constellation shaping | |
| 15 | 33 | acknowledge | A554 waits for it |

Word 1 is MP bits 34–49: the start bit, then the 15-bit data-rate mask (`& 7FFF`).

### Shaping polarity

A70E calculates the frame parameters for each direction (one time for the local MP at 0344,
one time for the remote MP at 0340). At A74B, it tests MP bit 14 and reads a packed
byte pair from the table at A7EC: the high byte when the bit is clear, the low byte when it is set.
It stores the value minus one as the ring count M of the shell mapper.

| Index | 0 | 1–7 | 8 | 12 | 15 | 18 | 20 | 24 | 28 | 31 |
|---|---|---|---|---|---|---|---|---|---|---|
| bit 14 clear | 1 | 2 | 2 | 3 | 4 | 5 | 6 | 8 | 12 | 15 |
| bit 14 set | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 10 | 14 | 18 |

When the bit is set, the result never has fewer rings, and it has up to about 1.2× more rings: the expanded
(shaped) constellation. Thus, bit 14 = 1 is shaping on, and it selects the +336
tables (0850 without precoder, 08F8 with precoder). This agrees with the scale data:
the two M values agree at low indices, where the shaped and the unshaped tables are
identical. Where they are different, the shaped scale is smaller. The agreement at low rates
is qualitative. We did not calculate again the A7EC index for each cell.

### Point-label lookup, 0590 / 0690 / 06B0

Together, these three tables map a received point to its label in the
V.34 constellation. The label is an index 0–415 into one quarter of the 1664-point
superconstellation, in the energy sequence that shell mapping uses. (An
earlier revision of this README called 0590 a Viterbi squared-distance
table. That was not correct. The labels increase approximately with energy, thus the table looked
like a distance.)

Firmware copies: C3B8, C4B8 and C4D8 in overlay 6 of `IDSDL302.ROM`. The lookup is
BAC8–BB44. It runs one time for each 2D half of a 4D symbol (inputs `@4c/@4d` and `@4e/@4f`):

    row  = bits 10–13 of x + y,  col = bits 10–13 of x − y   ; signed 4-bit, so the four corners are the origin
    d    = 0590[16·row + col]          ; byte chosen by bit 9 of x − y
    b    = (0690[row (+16 for high byte)] >> col) & 1   ; satl, TREG1 = col
    m    = 2·d + b
    if m == 0x1FE: m = 06B0[2·(row & 3) + sign(x − y)]

Evidence: across all 512 cells, the 410 non-saturated cells give **410
different values**. These cover 0–415, except 401, 404, 406, 407, 412 and 413.
Those six are exactly the 06B0 entries 191 194 196 197 19C 19D (the other
two are 1FF). Each saturated cell has b = 0, thus 0x1FE is an exact sentinel.
416 = 1664 / 4.

Consumer, BB58–BB74 (`@54` = q, `@55` = M − 1, as V.34 divides a label):

* ring = `min(m >> q, M − 1)` → data 0250 + 2n. The inverse shell
  mapper at BCAF (ROM 0CEE) reads it.
* the q low bits of each half (`@58` + `@59 << q`) are shifted left 3, ORed
  with 3 bits from the C3A8 nibble table, and stored at 0260 + n.

BD01 and BD18 read 0260. Each word gives 2q + 3 bits (`@7e =
2·@54 + 3`, BCFD) to the bit writer B542, that is, the 2q uncoded Q bits and the
three 4D-subset bits of each 4D symbol. ROM 0D17 is the same deframing code.

### C3A8: 4D subset bits (firmware only)

C3A8 (16 words before C3B8) is not in the ROM. ROM 0580–058F is different
data. BB45–BB57 indexes it with the two 3-bit 2D labels `@7c` (a) and `@7f`
(b): word `2a + (b >> 2)`, nibble `3 − (b & 3)` from the bottom (`lact`
shifted by TREG1 = `32a + 4b` mod 16, then `sach ,4`):

    a\b  0 1 2 3 4 5 6 7
    0    0 0 1 1 8 8 9 9
    1    3 2 2 3 b a a b
    2    5 5 4 4 d d c c
    3    6 7 7 6 e f f e
    4    8 8 9 9 0 0 1 1
    5    b a a b 3 2 2 3
    6    d d c c 5 5 4 4
    7    e f f e 6 7 7 6

The low three bits depend only on `(a & 3, b & 3)`: a pair of 2D subsets
maps to one of eight 4D subsets. Bit 3 is `(a >> 2) xor (b >> 2)`, and
no later code uses it.

Then the output is differenced against the previous symbol:

    Y   = (n & 1) | ((((n >> 1) − p) mod 4) << 1)    ; BB4E–BB55
    p  := (n >> 1) & 3                               ; @1d, BB56–BB57

Y goes in the low three bits of 0260 + n, under the q-bit pairs. This agrees with the
differential encoding of V.34 for the two bits above the trellis bit. But the
2D labels come from the rotation dispatch below.

### 8B16: quadrant fold (resident, overlay 5)

BAC1–BACD selects `@7c` = bit 8 of y, XOR 3 if bit 8 of x is set, and calls
`8B16[@7c]` on the point. The four targets are 90° rotations:

| `@7c` | target | operation |
|---|---|---|
| 0 | 8B53 | `ret` (0°) |
| 1 | 8B54 | (x, y) → (−y, x) |
| 2 | 8B46 | (x, y) → (−x, −y) |
| 3 | 8B4D | (x, y) → (y, −x) |

Thus, each point is folded into one quarter before the label lookup, and the
quarter number becomes the low two bits of the 2D label (bit 2 is the
half-step bit from x − y). 8B12 is the same four routines in a different sequence
(0°, −90°, 180°, +90°). Its users are below.

C3A8 does not change with rotation, in the way that the differential step needs.
When the two halves rotate one quarter, this adds 1 (mod 4) to bits 2–1 of n and does not change
bit 0 (n(0,0..3)=0,0,1,1 → n(1,1..0)=2,2,3,3 → …). The differential
decode removes exactly that. Thus, the receiver is not sensitive to the 90°
phase ambiguity, as V.34 intends.

Users: overlay 6 (V.34 core) at BACA, BB0C, BBDD and overlay 7 at BB76,
BBA5, BC6E. Overlay 8 (the PCM/V.90 layer) uses none of 8B12/8B16, C3A8,
C3B8, C4B8 or C4D8. Thus, this is the V.34 QAM receive path, not the V.90
downstream.

It is not early V.34. The label lookup covers 416 points for each quarter (1664 in
total), and the scale tables cover 31200/33600 bit/s. These two items are from the
1996 V.34 extension. The 1994 version stopped at 28800 bit/s and 960
points. B032 indexes C3A8
in the same way on a different path (`@7c` and data 0865). We did not trace this path either.

### 8B12 users: V.34 transmit mapper and training points

* **AF67–AF8F and AFC1–AFFE: transmit mapping.** The code looks up a label in
  C208 (packed odd-coordinate byte pairs in energy sequence, 01/01, FD/01,
  01/FD, FD/FD, 01/05, …: the V.34 label → point table). Then the point at 03F8
  is rotated by `8B12[quarter]`. The quarter is accumulated
  differentially: `@5a = (@5a + new) & 3` at AFD7–AFDB and in B0E5. That is
  the transmit side of the differential decode after C3A8. AF87 gets its
  bits from 8CC2 (probably the scrambler, not traced). Then AFF0 calls B146,
  the 3-tap precoder with modulo wrap (ROM 0ED5 is the same type of code).
* **B064–B083: nonlinear encoder.** It runs only when the **remote** MP
  (0340) has **bit 13** set. It scales the point by a polynomial in |p|²
  (constants 3195, 0633). This confirms that MP bit 13 is the nonlinear encoder,
  which the transmitter applies when the receiver requests it. The result goes to
  the transmit buffer at 04B6 (B0EE).
* **B5B7: 4-point training symbols.** It writes (2000, 2000) into 034C or 034E
  (`@4b` bit 0), then jumps to `8B12[@7d & 3]`.
* **B605: 16-point training symbols.** Each axis is 0E50 or −3 × 0E50, as
  bits 2 and 3 of `@7d` select. Then it is rotated by `8B12[@7d & 3]`. These agree with the
  4- and 16-point TRN sequences of V.34. They write the reference
  cells of the receiver (034C/034E). Thus, they are probably the training reference of the receiver.

Open: the transmit path at AFDC reads `0260 − @4a`. That is the same region that the
receive path writes at 0260 + n. We did not find if the two share it at different
times, or if the two directions are not what they seem.

### Relation to the 302/403 mask ROM

None of this V.34 material is in the older C51 mask ROM
(`artifacts/dsp-onchip-rom-20mhz-8k/`). No 16-word chunk of the probe
signal, the 672-point constellation, the label lookup, the scale tables, the
FFT, the precoder solve or the inverse shell mapper is in it. The
two ROMs share the vector layout, part of the V.32-family constellations
(the 496-word 0250 → 00D0 block) and the top block. The 3453C mask is a newer
image that includes the 1996 V.34 (33.6k) tables. The 3453C firmware calls
into it at runtime when it switches MP/MC (above). The firmware of the 302 family
has its own copies, because its ROM does not have them.
