# V.FC: V.32's start-up, then six symbol rates

V.FC is datapump slot 1 (refer to [datapump-slots.md](datapump-slots.md)). It is
in overlay 7 (`b000`-`cd49`). This overlay has a collision with overlay 6 of V.34 and with
the resident code of HST. The same entry, `b000`, serves the two sides. Overlay 7 does not
change, word for word, from 1996 onward
([imodem-firmware-timeline.md](imodem-firmware-timeline.md)). The addresses are
from the 403 image (`courier-board-21210-capture-403`).

This is the important comparison. HST and V.32 (with the 19200 of V.32terbo and the
21600 of USR) always stay at **2400 baud**. They get higher rates with larger
constellations ([hst.md](hst.md)). V.FC gets to 28800 because it **changes the symbol
rate**. It uses the start-up machinery of V.32, and nothing else above it.

## Rates

The `AT*C` menu (token-decoded, refer to datapump-slots.md) lists V.FC at 9600,
12000, 14400, 16800, 19200, 21600, 24000, 26400 and 28800 bps, originate and
answer. The `CONNECT` strings contain `/VFC` up to 28800.

## Symbol rates

A table at `b049`, indexed by the word at data `0x870`, reads
`0078 0089 008c 0096 00a0 00ab`. That is 120, 137, 140, 150, 160, 171: **2400,
2743, 2800, 3000, 3200 and 3429 baud, divided by 20**. These are the same six symbol rates
that V.34 uses. `b03d` changes the entry into `@6e` (`(v + 16) >> 5`). As the overlay of V.34 does,
V.FC writes the second symbol-rate index at data `0x35b` (`b155`,
`b4c7`). [codec-sample-rates.md](codec-sample-rates.md) identifies that as the
outgoing-INFO index of V.34. Neither overlay itself calls the codec rate selector `8151`.

Six-entry tables use the same index:

| table | values | read |
|---|---|---|
| `cb35` | 40, 35, 48, 32, 30, 28 | not read |
| `cb3b` | 5, 5, 7, 5, 5, 5 | not read |
| `cb41` | `1999`, `1999`, `1249`, `1999`, `1999`, `1999` | not read |
| `cb47` | 3, 4, 4, 5, 5, 6 | not read |
| `cb6d` | 2, 2, 2, 1, 1, 0 | not read |
| `cb73` | `5d71`, `4986`, `3071`, `4496`, `320e`, `5951` | not read |

`cc81` is a six-column table, that is, one column for each symbol rate. `cc2d` contains 16
symmetric 5-tap filters (`0044 ff18 2148 ff18 0044`, ...). Their shape suggests
pre-emphasis. We did not confirm the function of these two tables.

## Start-up is V.32's

* **Bits.** V.FC calls the V.32 scrambler `8cb7` of the resident (GPC or GPA by
  bit 0 of `0x6f`, as V.32 does) and the V.32 4800 differential encoder `8cd7`.
  At `c690`-`c6a3`, it sends scrambled 2-bit symbols onto the V.32 4800 points
  (`0x0240 + 8`, mask ROM). The receive side (`b89f`-`b8ac`) decodes the same
  set, through `0x0450` and `0x0248`.
* **Signal.** We ran the overlay alone. We loaded it over the resident after the
  cold start and went into it at `b000`. The originator transmits for about 125 ms
  and then waits. The signal repeats each 12 samples, and the second half is the
  negative of the first. It decomposes into three equal tones at fs/12, fs/4
  and 5fs/12: **600, 1800 and 3000 Hz at 7200**. That is an 1800 Hz carrier
  with ±1200 Hz sidebands, a short repeating pattern at 2400 baud. After
  sample ~900, the content changes. Then the signal stops while the originator waits for the far
  end.

V.FC uses nothing else from the V.32 family. V.FC does not use the mask-ROM
constellations above 4800 (`0x250`+), the quadrant mapper `bc00` /
`c280` of the resident, or the `bee6` receive selector.

## Data mode is V.34's structure

The mapper for each symbol is `c723`-`c78b`. It writes I/Q to the transmit buffer at
`0x04b6`.

* **An 8-symbol mapping frame.** `@35` counts 0-7. Each symbol uses one byte
  of the frame buffer (`ar2`), with high and low bytes in alternation. `c1bf`, `c20e`
  and the six-entry tables set the size of the frame for each symbol rate (there is a 16-step
  `subc` division at `c229`).
* **Quadrant differential coding.** `@5a = (@5a + 2 bits) & 3`.
* **Point.** The remaining part of the byte is masked by `@3e = (1 << @25) - 1` and
  combined with the high bits of the frame shifted by `@25`. A rotation-code
  offset from `cb2d` (`0 5 6 1 2 7 4 3`) is added. The result indexes a **one-quadrant point table
  at `aeab`** (packed I/Q bytes). Then one of four routines through `c804`
  turns the point: 0, (Q, -I), (-I, -Q), (-Q, I).
* **Trellis: 2D, V.32-style, not V.34's 4D.** The state advances on *each*
  symbol, from the 2 quadrant-differential bits. That is different from V.34, which
  advances one time for each 4D symbol (two 2D symbols) on 4 bits. The step (`c76f`-`c788`)
  XORs one tap word for each set bit of `u = @36 | (@5a << 5)` into `B`, and keeps
  `(B ^ ((B >> 7) & (B >> 5) & 3)) & 0x1f`. The AND term makes it nonlinear,
  as the code of V.32 is. State bit 0 and the 2 quadrant bits select one of 8
  subsets through `cb2d`. Bit 1 of `0x873` selects one of the two tap tables:
  * `cb5e` (`0064 0101 0002 0000 0000 0082 0103`) gets to 8 states and **is
    the 8-state code of V.32**. Its redundant bit agrees with the V.32 encoder of SpanDSP
    (`v17_convolutional_encoder`) on 2000 of 2000 random symbols, with a
    fixed state mapping.
  * `cb57` (`0070 0101 0002 0004 000a 008a 0103`) gets to all **32 states**.
    It agrees with the code of V.32 only at the level of chance (1068 of 2000). Thus, it is
    a different, stronger code.
* **Precoding** (`c9c4`, after each point). A 3-tap complex FIR over the past
  output, with coefficients at program `2056`/`2059`. These are not in the mask ROM. Thus,
  probably the training sets them. Its output is rounded onto a coarse lattice
  (`+ 0x400`, `& 0xf800`), and the rounding error is added to the point. This
  is the shape of the precoder of V.34 (9.6.4/V.34).
* **Nonlinear encoding** (`c9f7`, when bit 10 of `0x879` is set). ζ comes from
  |x|² (scale `0x28f6`), and the point is multiplied by
  1 + `0aab`·ζ + `0089`·ζ² + `0003`·ζ³. At Q14, those are 1/6, 1/120 and
  1/5040. Thus, **Φ = 1 + ζ/6 + ζ²/120 + ζ³/5040**. V.34 9.7 stops at ζ²/120
  (the `v34tx.c` of SpanDSP also stops there). V.FC has one more term of
  the same series.

**The point table is V.34's superconstellation, ordered differently.** `aeab`
is in the *resident*, in the range that overlay 6 overwrites. It is on the
one-even-one-odd lattice. If you rotate it 45 degrees, `(x + y, x - y)`, it falls on the
odd lattice of V.34. We compared it with the `v34_superconstellation` of SpanDSP
(Figure 5/V.34), with all four rotations applied:

| quarter entries | points | same set as V.34 |
|---|---|---|
| 4, 8 | 16, 32 | yes |
| 16, 32 | 64, 128 | no (8 and 16 points differ) |
| 48, 64, 96 | 192, 256, 384 | yes |
| 128-192 | 512-768 | no (8-24 differ) |
| 240 | 960 | yes |
| 256 | 1024 | no (8 differ) |
| **320** | **1280** | end of V.FC's table (`afeb` breaks the lattice) |

Each energy shell that V.FC completes contains exactly the points of V.34. The sizes that
are different are those that cut through a shell, where the two tables complete the
ring in a different order. Also, the table of V.FC is not monotonic in energy, but
the table of V.34 is. V.FC stops at 1280 points. The table of V.34 goes to 1664, for 33600. **Same
lattice and shells, different index-to-point order**: on a scope, the two look
the same, but a V.34 mapper cannot replace this table.

## Open

* the frame arithmetic in `c1bf`/`c20e` (how the bits for each 8-symbol frame come
  from the symbol rate and the data rate), and how it compares with the shell mapping
  of V.34;
* the distance properties of the 32-state code, and the source of the precoder taps;
* the function of the tables for each symbol rate and of the `cc2d` filter bank;
* `cb65` (`aaaa aaab aaaf aabf aaff abff afff bfff`): eight 16-bit patterns,
  possibly rate signals;
* the codec rate that V.FC programs for each symbol rate;
* what the far end must send to get past the first 125 ms.
