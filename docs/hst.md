# HST: two channels, one each way

HST is datapump slot 3 (refer to [datapump-slots.md](datapump-slots.md)). All of it
is in the resident DSP bank of the 403 and in the C52 mask ROM. This note gives
what the code and a run of it establish. It is written as the specification that a reimplementation
needs. The addresses are those of the 20.16 MHz resident (`courier-board-21210-capture-403`)
and of the mask ROM dump `boot_rom.MASK_ROM`.

HST is the only slot in which the two sides send *different signals*. V.23 is also
asymmetric, but its two channels are FSK. Here, each side installs its own
transmitter, and the two share only the symbol-script engine.

## Call roles and the loopback entries

The slot-3 entries in the `10`/`11` tables, `c533` (`9b48`) and `c7fd`
(`9b51`), are configurations for an **analogue-loopback self-test**, the same as the FSK
own-band entries in [fsk-modulation.md](fsk-modulation.md). Each one pairs a
transmitter with a receiver for the *same* channel. A call uses the tags of HST itself
instead:

| role | entry | transmits | receives |
|---|---|---|---|
| forward-channel sender | tag `33`, `c51f` | forward (`c992`) | back channel (script `c4f7`) |
| back-channel sender | tag `32`, `c7ed` | back channel (`c967`) | forward (script `c7a4`) |
| loopback | `c533` | back channel | back channel |
| loopback | `c7fd` | forward | forward |

We established this when we ran two cores in lockstep, with the `DXR` of each core
fed into the codec input of the other core. Results:

* **`c533` x `c7fd`:** no receiver ever passes its first script step,
  because each one receives the other channel.
* **`c533` x `c533` and `c7fd` x `c7fd`:** the two receivers detect carrier.
* **`c51f` x `c7ed`:** a full start-up on the two sides, with host messages
  logged at `83b1`:

| frame (7200 Hz) | tag `33` side | tag `32` side |
|---|---|---|
| 341 | | `2f` + rate `0`: forward carrier detected |
| 649 | `2f` + rate `0`: back-channel carrier detected | |
| 701 | | `04` |
| 820 | `03`: forward transmit data enabled | |
| 965 | | `02` |
| 1441 | | `03`: back-channel transmit data enabled |
| 2089 | `04` | |
| 2437 | `02` | |

We did not read what `04` and `02` mean. The sequence on the two sides (carrier, `04`,
`02`) suggests receiver training stages.

### Data across the pair

**The two channels are bit-exact.** We fed each transmitter a counting byte
sequence, and compared the output of its partner after HDLC destuffing:

| direction | measured at | result over 30000 frames |
|---|---|---|
| forward, 4800 | words delivered to the host window (`832f`) | **2380 of 2380** bytes exact (10 more still in flight) |
| back, 300 | the receiver's decoded value per data symbol (`@20` at `c5d6`) | **142 of 142** bytes exact |

* **Framing.** The framer of the datapump (`@56` = `8264`) is synchronous and
  **HDLC bit-stuffed**: a 0 after each five 1s, with the flag `0x7e` at
  `8278`. There are no start/stop bits. The forward sender takes a byte each
  12 frames (4800 bps). The receive side delivers the raw stuffed bits, LSB
  first, n for each symbol (`@26` = `8320`).
* **Back channel: 3 bits on every second symbol.** In data mode, the handler for each symbol
  alternates between `cab5` (fetch, scramble, 8-DPSK step) and
  `cae0`/`cae2`, which sends **I = Q = 0**. That is 100 data symbols/s x 3 =
  **300 bps** (150 x 3 = **450** with `0x6f` bit 12). It is the half-baud line
  that the squared signal showed, and the byte fetches of the sender alternate 144 and
  216 frames apart.
* **Back-channel receiver** (`c57a` for each sample, `c5c4` for each symbol). It has an equalizer
  (`8968`, `89cf`), then a derotation by `@04`/`@05`. The octant decision
  (`c6eb`-`c6fc`) uses the signs and |I| against |Q|, with the reference point from
  `cbb1`. Differential decode (`c703`-`c710`): `d = k - k_prev`, data = nibble
  `d` of `0x51376204`. This is the exact inverse of the
  `0x43705261` of the transmitter (we checked all eight entries). The descrambling (`c740`) is
  1 + x^-14 + x^-17, shift `@22` = 3, the mirror of `cba2`. The delivery is through
  `8304`. The decoded values agree with the values of the transmitter before the scrambler on
  96% of symbols at a fixed lag. The misses are the symbols of the receiver before it locks.
* **Harness trap.** The window slots are C5x I/O ports in data `0x50`-`0x5f`.
  The DSP reads them with `lamm *` in `80e8` (transmit) and writes them in
  `8320` (receive). On the board, those are separate CPU-side registers. A
  harness that keeps one value for each port lets the received data of each side
  overwrite its own transmit bytes. That caused 49 zeroed forward bytes, and
  back-channel bytes with only bits 0 and 7, until the byte was supplied at
  the time of the `80e8` read. Also, the `832f` store operates only when the
  window has space. Thus, a harness that never drains the receive side sees it
  skip symbols.

The `10`/`11` dispatchers have a call-mode twin (`9da6`, `a00d`, `9dc1`,
`a054`), but it branches only for V.22/V.22bis, Bell 103, V.21 and V.23.
The flag of HST (`@26` bit 5) is not tested there. HST gets to its call roles only
through tags `32` and `33`.

## Measured

We ran the loopback entries in the same way as `fsk_loopback`, with `@26` kept at
`8320` (refer to the text below), and recorded `DXR` at the codec rate of the resident, 7200 Hz.
The transmitters are the ones that the call roles install:

| entry | transmitter | carrier | baud | -20 dB span | rate |
|---|---|---|---|---|---|
| `c533` | `c967` -> `c9d2`/`ca05` | **350 Hz** | **200** | 258-444 Hz | 300 bps back channel |
| same, `0x6f` bit 12 set | | **375 Hz** | **300** | 258-480 Hz | 450 bps back channel |
| `c7fd` | `c992` -> `c9a5` | **1800 Hz** | **2400** | 556-3078 Hz | forward channel |

The baud is counted, not inferred: the symbol boundary `ca1b` runs 83 times in 3000
frames at 300 bps, 124 times at 450, and 999 times on the forward channel, with
one modulator call for each frame. No host data was fed and the codec input was
silent. Thus, the transmitters sent their start-up pattern. The squared back
channel shows its strongest line at *half* the baud (100 / 150 Hz). That is the
pattern that repeats each two symbols, not the symbol rate, and it caused an error in
the first interpretation.

## The symbol-script engine

The two transmitters take their symbols from a script. At each symbol boundary,
`ca1b` checks `@4a`. When it gets to zero, the engine copies the next three
words from the script at `@4d` into `@48` (the handler), `@49` (an argument)
and `@4a` (a duration in symbols). Then it jumps to `@48`. A zero handler ends
the script. Thus, a training schedule is data, and you can read it directly.

## Forward channel

**Modulator.** `c9a5` is a 20-tap pulse shaper that runs at three samples for each
symbol (`@4c` steps `0x14` up to `0x3c`). There is no carrier multiply, because
1800 Hz is fs/4. `@45` is decremented each sample, bit 0 selects the I or Q half
of the pulse table (`+0x14`), and bit 1 negates. That cycles I, Q, -I, -Q. The
codec stays at index 0, 7200 Hz.

**Mapping** (`cb4e`). The symbol index `@50` is looked up in mask ROM at
program `0x0240 + @50`: high byte I, low byte Q, both signed. The tables there
are the **V.17/V.32bis constellations, point for point, at scale x8**. We checked each
entry against `v17_v32bis_tx_constellation_maps.h` of SpanDSP:

| ROM | points | SpanDSP table | rate (2400 baud) |
|---|---|---|---|
| `0x0248` | 4 | `v17_v32bis_4800_constellation` | 4800, uncoded |
| `0x0250` | 16 | `..._7200_constellation` | 7200 |
| `0x0260` | 32 | `..._9600_constellation` | 9600 |
| `0x0280` | 64 | `..._12000_constellation` | 12000 |
| `0x02c0` | 128 | `..._14400_constellation` | 14400 |
| `0x0340` | 256 | none (odd multiples of 4) | 16800 |
| `0x0244` | 4 | not SpanDSP's ABCD order | training |

**Interpret this as shared tables, not as an HST that is derived from V.32bis.** HST shipped
before V.32 products, and long before V.32bis. The ROM shows that this
1990s firmware runs HST on one table set that the V.32 family and V.17 fax also
use. Other users of the same tables: the resident V.32 path (`bc8a`, `bcd2`,
`bff0`) and the fax datapumps (`e689`, `e6a3`). One firmware cannot tell if the HST of 1986 coded its
symbols in this way. **The 16800 table of HST is its own. It is not the table of V.32terbo.** The resident has two
large-constellation schemes, and only HST uses `0x340`.

*Receive selector.* A jump table at `bee6`, indexed by `@2a`, loads the slicer
base `@28` for each rate:

| index | n | `@28` | rate |
|---|---|---|---|
| 0 | 2 | - | 4800 |
| 1 | 3 | `0x250` | 7200 |
| 2 | 4 | `0x260` | 9600 trellis |
| 3 | 4 | - (slicer `bfc1`, table `0x440`) | 9600 uncoded |
| 4 | 5 | `0x280` | 12000 |
| 5 | 6 | `0x2c0` | 14400 |
| 6 | 7 | **`0x340`** | **16800** |
| 7-13 | 3-9 | none (slicer `c009`) | 7200-21600 |

*V.32 transmit* (`bbbd`, rate code `@49`). Codes 1-4 go through `bbf1`, the
same `index + (2 << n)` path that HST uses, for n = 3-6 only. Codes 5 and higher go
through `bc00`, with n = code - 3, up to 9. That path takes the trellis subset
(3 bits) to `c22a` for flags (bit 0: column, bit 1: negate Q, bit 2: negate I,
bit 3: swap). The uncoded bits index a 256-entry one-quadrant table at
**`c280` in the resident**. The table is sorted by increasing energy, in integer coordinates with one even and one odd value.
Then the point is scaled by `@67` and **warped** by a polynomial
in r² (`bc2c`-`bc48`: `1566e000`, `1928`, `019f`, `000c`). `c009` is the
inverse of the receiver: unwarp (`dcb3`, `15f9`, `1355`, `03c2`), rotate by
`@48`/`@49`, and fold into one quadrant. 256 entries x 4 rotations is 1024
points, that is, the 9 + 1 bits of 21600. Half the table is the 512 of 19200. Nothing here
needs a 512-point table, and the `0x7e0` mask of the V.32 re-encoder is one bit
wider than the `0x3e0` of HST.

No V.32 transmit path gets to `0x340`. V.32 16800 is code 10 through `c280`.
The two 256-point sets are on the same lattice (45 degrees apart, the inner
energies 2, 10, ... are identical), but they have different boundaries. `0x340` is
more square and gets to energy 450. The inner 256 points of `c280` are a circle that gets to
314. HST 16800 is a constellation of HST itself.

**V.32 and HST share the `bee6` selector.** The code enters it from the
receive-script step `bec4`. That step waits for `@20 == @21` on eight
consecutive symbols (`@29` counts down from 8), clears the state, sends host
message `22` through `83b1`, and dispatches on `@2a`. `bec4` is in the receive script of V.32
(`b35a`) and in the forward-channel receive script `c7a4` of HST, at
`c7c2`. `c7c2` is the script tail that tag `37` starts, and tag `38` is `bebe`,
which cancels the wait. Thus, the forward channel of HST is received on the same QAM
receiver that V.32 uses, and index 6 / `0x340` is reached from there.

Each image here has a limit of 16800 for HST: the `CONNECT` strings are
4800/7200/9600/12000/14400/16800`/HST`. 21600 exists only as `/V32` and
`/VFC`, and 24000 only as `/VFC` and `/V34`. The `CONNECT` text says
`12000/HST`. Thus, the `12200` of the menu is a spelling error in a label. "HST" is also a link
protocol name together with `SYNC`, `NONE`, `MNP` and `LAPM` (`0x1b056`,
`0x1be6e`).

The offset is calculated, not tabulated. For n bits for each symbol, `cb3f`
adds `2 << n` to the encoder output. This gives `0x250`, `0x260`, `0x280`,
`0x2c0` and `0x340` for n = 3 to 7. n = 2 goes through `cb34` and adds 8
instead. The 256-point table is the only one with no V.32bis equivalent.
16800 at 2400 baud is 7 data bits plus 1 trellis bit, which needs 256 points.

**Coding.**

* n = 2 is differentially encoded through mask-ROM `0x0450`
  (`(@50 << 2 | @5a) & 0xf`). It is identical, entry for entry, to the
  `v32bis_4800_differential_encoder` of SpanDSP, transposed: `T[q << 2 | prev]` equals
  `enc[prev][q]`.
* n >= 3 goes through a 32-entry table at `0x0460`, indexed by
  `(@50 << 3) + @5a` mod 32. The 5-bit state packs the two differential bits
  (bits 3-4, thus the addition of the data mod 4 is the differential encoder) and the
  convolutional state. The top bit of that state is the redundant bit. The output index is
  `((@50 << 3) & 0x3e0 | state) >> 2`.
* **This is exactly the encoder of V.32.** When we drive the ROM path and
  `diff_and_convolutional_encode` of SpanDSP with the same 3000 random symbols, they give
  identical index streams at each n from 3 to 7. All 32 ROM states map one to
  one onto the (diff, convolution) pairs of SpanDSP. For n = 7, the uncoded
  mask `(q << 1) & 0x78` of SpanDSP must increase to `0xf8`, because 16800 has one more
  uncoded bit than 14400. Nothing else changes.

**Scrambler** (`cb92`). `@58:@59` is a 32-bit register. The n scrambled bits
are `(R >> 5) ^ R ^ data`, masked to n bits. They are inserted at bit 23, and
the register is shifted right by n (`SATL`, which is a right shift; refer to
`op_satl`). Thus, output bit j sees delays 23 and 18, and the polynomial is
**1 + x^-18 + x^-23**, the GPC of V.32. HST uses it in the direction that carries
the forward channel. Seeds: `0x001f7310` at the start of training (`cb09`).

**Training** (rate scripts `ca34`, `ca41`, ... `ca75`, selected by `0x32a`):

| step | handler | argument | symbols | what it sends |
|---|---|---|---|---|
| 1 | `cafa` | 0 | 180 | index 0, the point (0,0): silence |
| 2 | `cafe` | `0202` | 72 | nibbles of the argument, one per symbol, + 8: alternating `0x24a`/`0x248` |
| 3 | `cb09` | 2 | 200, or `0c18` = 3096 at rates 3-5 | scrambled 2-bit symbols on the 4800 points; the input is the previous output |
| 4 | `cb1b` | n = 2..7 | 16, or 24 at rates 3-5 | data-rate symbols |
| - | `cb6e` | `@5c` | 37 at a time | data mode; `825f` refills every 37 symbols |

The second table (`c52d`: `ca37`, `ca44`, ...) starts each script one entry later,
and skips the silence. Tag `33`, the call role of the forward-channel sender,
uses it. The 3096-symbol step 3 (1.29 s) at rate indices 3-5
agrees with a longer equalizer training for 12000 and higher. We did not find why the tag `36` value is
stored as index + 8 in `@5c`.

## Back channel

**Modulator.** `c9d2` and `ca05` alternate for each sample, and each one writes the other
into `@1a`. The pulse shaping comes from a 36-entry table (`cbc1` at 300 bps,
`cbe5` at 450). A 32-bit phase in `@40`/`@41` increases by `@6c << 14` each
second sample: `0x638e` gives 349.97 Hz and `0x6aaa` gives 375.0 Hz. `0x6f`
bit 12 selects the pair, together with `@70` = 3 or 5. `ca05` adds `@70 + 1` to
`@4c` and ends the symbol at 72. Thus, a symbol is 18 or 12 `ca05` calls, that is, 36
or 24 samples: **200 or 300 baud**, as counted above. The entry also sets
`@04` to `0x038e` / `0x0555`, which is 100.0 / 150.0 Hz at 7200, half the
baud. We did not read what `@04` clocks.

**Mapping** (`caba`-`cace`). This is **differential 8-PSK**. The script
gives it 3 bits for each symbol. At 200 / 300 baud, this is 600 / 900 bit/s on the
line, two times the 300 / 450 of the menu. Data mode halves it with a zero symbol
between data symbols (refer to *Data across the pair*). The 3 scrambled bits select a nibble of the packed constant
`0x43705261`:

| bits | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| phase step (x45 degrees) | 1 | 6 | 2 | 5 | 0 | 7 | 3 | 4 |

`@71 = (@71 + step) & 7`, and `cbb1 + 2 x @71` gives (cos, sin). The eight
points are at 22.5 + 45k degrees, amplitude 12945 (`2eb8`/`135a` = 11960/4954).

**Scrambler** (`cba2`). It uses the same register layout, but new bits are inserted at
bit 17 and the shift is a fixed 3. The taps are at R and R >> 3, thus the delays
are 17 and 14: **1 + x^-14 + x^-17**, the polynomial of V.22bis. Seed
`0x0001fd28` (`caa1`).

**Script** `ca82`: `caa1` with argument 3 for 17 symbols (the scrambler seed,
then 8-DPSK), then `caaf` with argument 0 for 1 symbol. `caaf` sets
`0x6f` bit 2 (the transmit-data enable) and sends the host message `03`
through `83b1`. After that, `cab5` runs for each symbol on host data that
`825f` fetches. At 300 bps (bit 12 clear), `cad5` first sets `@4a` = 10.

## Mailbox tags

HST has a block of tags that no other modulation has:

| tag | handler | what it does |
|---|---|---|
| `32` | `c7ed` | call role: **back-channel** transmitter `c967` + forward receiver (joins `c805`, script `c7a4`) |
| `33` | `c51f` | call role: **forward** transmitter `c992` + back-channel receiver (joins `c537`, script `c4f7`) |
| `34` | `c506` | keeps only `0x6f` bit 12; picks a receiver rate script from `c519` by `@2a` |
| `37`, `39` | `c7d3`, `c7cd` | store a rate index below 6 into `0x32a` (37 also starts script `c7c2`) |
| `36` | `c7df` | `@5c` = index + 8 |
| `35`, `3a`, `3b` | `c963`, `c95f`, `c7e9` | park a script in `@4d`, or clear `@6f` bit 3 and rejoin `c805` |

Tags `32` and `33` are the call roles (above). Because the high-speed direction
follows the data, a channel reversal is probably the supervisor that sends
the other tag again. We did not read that, or what makes the supervisor send either tag.

## Receivers

**Back channel, script `c4f7`** (tag `33` side). It steps one time for each back-channel
symbol: 200 each second at 300 bps.

* `c5e8` x1 and `c5f0` x4 are the carrier detect. The energy `@00:@02` must be more than `@0b`
  (`0x41e8`), then four times it. Any miss restarts at `c4f7`. On success, it
  sends `2f` and the rate index from `0x32a`.
* `c611` x16 initializes: `@06` = `0x90`, `@04` = `0xe4`, loop steps
  `@28`/`@29`/`@2c` = `0x800`/`0x200`/`0x40`, 16 words cleared at `0x240` and
  `0x400`. It uses the resident receiver routines that the V.32 path also uses
  (`87fd`, `88b3`, `bd3d`, `bd43`).
* `c637` x5, `c640` x13, `c646` x37 and `c649` x400 settle the loops. The gains
  `@10`/`@11`/`@12` start at `1800`/`3000`/`1000`, then `@2c` = `0x78`, then
  `@10` decreases to `0x800` for 400 symbols.

**Forward channel, script `c7a4`** (tag `32` side). Its handler for each sample,
`c821`, counts `@2b` down from 3. Thus, the script steps 2400 times each second.

* `c83e` x16 (two times) and `c84c` x16 are energy tests: `@00 + @02` against
  `0x2a54`, with a sign test on `@34`.
* `c866` arms the path for each symbol, `c88d` (demodulator `8a8c` with table
  `c950`).
* `c8d7` x19 sets the loop gains and `@0b` = `0x3aaf`, and sends `2f` plus the
  rate.
* `c8f8` x192: rate index 0 goes to `bef3` (4800). Indices 1-2 go through the
  shared `bee6` selector. For higher indices, it changes to script `c7b9`.
* The `bec4` tail at `c7c2` is the decision-directed lock that is described above.

## Running it

* `@26` (data `0x326`) must stay at the `8320` of the cold start. `fsk_loopback`
  clears it for FSK. If you do that here, the `bacc` of 8304 goes to zero, and the slot
  runs for one sixth of the time and delivers nothing.
* All the code of HST, `c4f7` to about `ccdf`, is in overlay 6
  (`9d00`-`ce31`) and in overlay 7 (`b000`-`cd49`). Thus, HST runs only from a
  newly downloaded resident.
* The constellation, encoder and Gray tables are in the **mask ROM**, not in the
  download. A harness without `boot_rom.install` transmits garbage points.

## Open

These items are necessary before an interoperable reimplementation:

* host messages `04` and `02`;
* how a call selects HST, that is, the answer and detection sequence, and how the
  supervisor uses tags `32`-`3b`;
* the link layer in the HDLC frames: the datapump only stuffs bits and
  sends flags. The frame format, the addressing, and how the "HST" link
  protocol of the supervisor (next to `MNP` and `LAPM` at `0x1b056`) uses the two channels.
