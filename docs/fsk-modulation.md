# A modulation, not a tone: V.21 and Bell 103 from the firmware's own modulator

[answer-tone.md](answer-tone.md) made the datapump send a 2100 Hz answer
tone. That is a signalling tone: one oscillator, no data. This document makes
the same firmware run an actual **modulation** - FSK, keyed by a data bit.
Then it makes the firmware **demodulate its own transmitter through analogue
loopback**, which is what the `&T` self-test does. All four 300 bps bands
recover a 511-bit sequence without error.

To get there, we had to correct four opcodes in the C5x core. Those opcodes
are the reason that none of this worked before. They are the most portable
result here.

## The four bands, found by arithmetic

We searched the resident bank for 16-bit constants that are phase increments
at the 7200 Hz of the dial path. We found four adjacent pairs, in six setup
routines at `d790`-`d7d7`:

| setup | `@72` | `@73` | frequencies | modulation |
|---|---|---|---|---|
| `d790` | `22d8` | `29f5` | 980 / 1180 Hz | V.21 channel 1 (originate) |
| `d79a` | `2d28` | `260b` | 1270 / 1070 Hz | Bell 103 originate |
| `d7b4` | `3aab` | `41c7` | 1650 / 1850 Hz | V.21 channel 2 (answer) |
| `d7be` | `4f1c` | `4800` | 2225 / 2025 Hz | Bell 103 answer |

Four more routines set a receive carrier: `d7c8` 1080 Hz, `d7d0` 1170 Hz,
`d7a4` 1750 Hz, `d7ac` 2125 Hz. These are the band centres of the four
transmit pairs.

Each of these eight numbers is a standard 300 bps frequency only if the sample
rate is 7200 Hz. With `0x4aab` and `0x0ca7` from the answer tone, there are
now three independent confirmations of the rate that
[audio-312-path.md](audio-312-path.md) first inferred from DTMF alone.

## The modulator

Program `d95f`, installed in the first callback slot of the mixer:

```text
d95f  bit    7, @50     ; the data bit - bit 8 of the cell
d960  lacc16 @72        ; mark increment
d961  xc     1, ntc
d962  lacc16 @73        ; ...or space
d963  add16  @63        ; frequency offset
d964  add16  @40        ; phase accumulator
d965  sach   @40
d966  calld  8b0f       ; sine
d96a  bit    11, @70    ; transmit enable
d96c  xc     1, tc      ; ...else feed the filter a zero
d96d  lacc   @42
d970  calld  8a88       ; shaping filter, coefficients addressed by @5f
d975  mpy    @67        ; amplitude
d977  sach   @47, 1     ; the transmit sample
```

`courier_emu.fsk` calls the own setup routine of the ROM, installs `d95f`, and
runs the same mixer and serial ISR as `audio312` and `answer_tone`. **This
harness supplies the data bit from outside, one time in each 24 samples.** On
that basis, a 511-bit maximal-length sequence modulates and demodulates with
zero bit errors in three of the four bands:

| mode | mark | space | bit errors over 511 |
|---|---:|---:|---:|
| `v21-originate` | 980 | 1180 | 0 |
| `v21-answer` | 1650 | 1850 | 0 |
| `bell103-answer` | 2225 | 2025 | 0 |
| `bell103-originate` | 1270 | 1070 | 34 |

The last row is a limit of the **demodulator in this tool**, not of the
firmware. Its two tones are 200 Hz apart at one bit for each 24 samples. This
is closer than non-coherent energy detection can separate. A real Bell 103
receiver uses a discriminator, not two matched filters. The modulator itself
is exact - when the bit stays constant, we measure 1270.0 Hz and 1070.0 Hz.

> **Withdrawn: the 300 baud figure was this harness's, not the firmware's.**
> An earlier version of this document called 24 samples for each bit "exactly
> 300 baud", because 7200/24 is 300. That is arithmetic about a number that
> this harness selected. It is not a measurement of the ROM. The firmware has
> its own transmit bit clock, and it tells something different: `@50` is a
> shift register that `d978`-`d983` shifts right **one time for each
> modulator invocation**. It reloads when the marker bit falls out. Thus it
> gives one data bit for each invocation. The same invocation advances the
> carrier phase by an increment that is a V.21 frequency only at 7200 Hz. If
> we accept the two items as they are, the result is 7200 bps, which is not a
> 300 bps modulation. Thus we still do not know how often the callback of this
> datapump actually runs. Until we know it, no baud value here belongs to the
> firmware. The increments show the **identity of the modulation** - the
> frequencies are exact - but not its bit rate.

```sh
.venv/bin/python -m courier_emu.fsk \
  --rom artifacts/courier-board-21210-capture-403/courier-board.rom \
  --output /tmp/fsk --mode v21-answer
```

The saved runs for all four modes are in `artifacts/fsk-01/`.

## The loopback table

Eight dispatch entries at `d7d8`-`d812` each call one transmit setup and one
receive setup. If we sort them by whether the receiver is in the own band of
the transmitter, they divide exactly in half:

| entry | transmitter | receive carrier | |
|---|---|---:|---|
| `d7d8` | Bell 103 answer 2225/2025 | 2125 | **own band** |
| `d7e3` | Bell 103 answer 2225/2025 | 1170 | normal |
| `d7e9` | Bell 103 originate 1270/1070 | 1170 | **own band** |
| `d7f4` | Bell 103 originate 1270/1070 | 2125 | normal |
| `d7fc` | V.21 answer 1650/1850 | 1750 | **own band** |
| `d802` | V.21 answer 1650/1850 | 1080 | normal |
| `d808` | V.21 originate 980/1180 | 1080 | **own band** |
| `d80e` | V.21 originate 980/1180 | 1750 | normal |

A modem in a call never listens to its own transmit band - that is the main
purpose of the division of the band in two. A configuration that does this is
a modem that listens to itself, and analogue loopback needs this. Thus four of
these eight entries are the datapump configuration of the loopback self-test,
one for each 300 bps modulation.

That started as an argument from the structure of the table. The next section
runs it.

## The loopback, closed

The loop closes, but not through this module. **`courier_emu.fsk --loopback`
does not run now** - each mode raises `loopback did not reach 80c3`. It also
does this at `32faa8e`. Thus the zero-error table that this section had before
could not be reproduced before anyone examined it. Use
[`courier_emu.fsk_loopback`](../courier_emu/fsk_loopback.py). It runs the part
and does not drive it, and it measures against the words that the firmware
itself delivers, not against its own slicer.

We keep the record of the errors of this module, because three harnesses in
this family have the same errors - `answer_tone`, `audio312` and `v34` all
enter the mixer in the same way:

* **The on-chip mask ROM was absent.** Here, `load_rom()` installs the own
  five-instruction driver of the harness in that window. Thus the part has no
  interrupt vector table. `INTR 17` is a software trap at fifteen sites, armed
  by the receiver at `d879`. Its vector at ROM `0x0022` is `lamm @69 ; bacc`.
  This dispatches through B2 RAM at data `0x60`-`0x6a`, which the cold start of
  the resident fills from program `812d`. Its handler is `0x81a6` - the
  routine that packs two scaled receiver outputs into TDXR. The bare `RETE`
  that this section described was a substitute for all of that.
* **The harness entered the frame ISR when it forced the PC.** Thus `rete`
  pops a stack that was never pushed. Raise irq 5, and let the part vector
  through `0x000c` -> `@65` -> `0x8178`.
* **The buffer pointer was pinned.** `0x390` is the consumer side of a
  producer/consumer pair over a 32-word circular buffer on AR7
  (`CBSR1`/`CBER1`/`CBCR` = `0bc0`/`0bdf`/`00ef`). It advances by two words for
  each codec frame - one receive slot and one transmit slot, interleaved. If
  you pin it, the code skips the service block for each buffer at `0x80bb`.
  Thus the message-ring drain at `0x83bf` never runs, and the bring-up state
  machine never completes.

If you run the part correctly, it completes, to `@6f = 008c`, and the loop
recovers data:

| mode | alignment | raw bit error | polarity | symbol errors |
|---|---:|---:|---|---:|
| `bell103-answer` | 323 | 0.101 | direct | 1 in 165 |
| `v21-originate` | 323 | 0.113 | direct | 1 in 165 |
| `v21-answer` | 132 | 0.176 | inverted | 2 in 169 |
| `bell103-originate` | 130 | 0.186 | inverted | 1 in 169 |

The four modes are in a factor of two of each other on raw error, and in one
symbol error of each other. This is the expected result: the four bands run
the *same* DSP code, and are different only in `@72`/`@73`, `@6b`, `@69` and
`@0b`. A much wider spread would be evidence of a band-dependent item in the
model, not in the signal. An earlier pass gave `bell103-originate` 22 in 169.
That was exactly such an item - an alignment search that locked on the
incorrect offset. It was not a property of the band.

The four modes divide clearly into two groups by alignment and polarity,
`{bell103-answer, v21-originate}` against `{v21-answer, bell103-originate}`.
That pairing does **not** follow mark above the centre against mark below the
centre. We do not know what it follows.

```sh
.venv/bin/python -m courier_emu.fsk --loopback \
  --rom artifacts/courier-board-21210-capture-403/courier-board.rom \
  --output /tmp/loopback --mode v21-answer   # BROKEN, see above
```

The saved runs are in `artifacts/fsk-loopback-01/`. Note that this is the
demodulator of the **firmware**, not the simple two-tone detector above: it
recovers Bell 103 originate without error. That detector could not.

### Two properties of the receiver, measured rather than assumed

**The sampling offset is the group delay of the receiver.** It is not a free
parameter fitted for each run. For each mode, it is stable across patterns and
seeds, at 41 to 44 samples. The tests assert that it is in that range. They do
not accept the value with the best score.

**The decision polarity belongs to the modulation, not to the harness.** `@6a`
is an integrate-and-dump on the signal mixed against the band centre. Thus its
sign tells whether the tone is above or below that centre - not which bit it
is. V.21 puts mark *below* the centre (1650 against 1750), and Bell 103 puts it
*above* (2225 against 2125). Thus the two families decode with opposite sign.
`slice_bits` takes that from the frequency table. When this was incorrect,
V.21 appeared to fail and Bell 103 passed, on a run that was otherwise
identical.

### What is still open

**48 samples for each bit is measured, not derived.** We found it when we
scanned the symbol period for the minimum error, and the minimum is sharp - 48
gives zero errors, but 40 and 36 give seventeen. But it does not agree with
the transmit shift register above, which gives one bit for each invocation.
This harness overrides that register and does not let it run. Thus the natural
symbol period of the receiver is 48 modulator invocations. Its value in real
time still depends on the callback rate, which this document could not find.
If the callback runs at 7200 Hz, it is 150 baud. The 300 baud of V.21 would
need 14400. **This document does not settle the baud rate or the callback
rate.**

## Which band a receive setup hears, measured

The loopback argument above depends on the receive setup that selects the
band of the receiver. We read that from the constants. This section measures
it.

One signal, four receivers. The modulator of the firmware makes a **V.21
answer** signal at 1650/1850. The transmitter stays on the originate band and
is gated off. The same signal goes to the receiver with each of the four
receive setups installed, one after the other:

| receive setup | carrier | bit errors over 120 |
|---|---:|---:|
| `d7a4` | 1750, the answer band centre | **0** |
| `d7ac` | 2125 | 56 |
| `d7c8` | 1080 | 64 |
| `d7d0` | 1170 | 64 |

Only the setup whose carrier is the band centre of the signal recovers
anything. The other three are at chance. Thus the receive setup selects the
band. The four dispatch entries that pair a transmitter with its own band
centre really are the modem that hears itself. Whatever their other purposes
are, they cannot be a configuration for a call: no V.21 or Bell 103 modem in a
call listens to the band that it transmits in.

```sh
.venv/bin/python -m courier_emu.fsk --band-scan --mode v21-answer \
  --rom artifacts/courier-board-21210-capture-403/courier-board.rom \
  --bits 111111111000000000... --output /tmp/band
```

The run above is in `artifacts/fsk-band-01/`, with the dispatch tables and
mode flags read from the same image. Use `--bits`: here, the default 511-bit
sequence takes four receiver runs.

## Where those entries are dispatched from

Mailbox commands **`10`** and **`11`** in the table at `83e9` enter at `9b34`
and `9b38`. Each loads a table base into `@7c`. Then the two take an index from
the mode flags and jump:

```text
9b34  splk   @7c, #9b48     ; one table
9b38  splk   @7c, #9b51     ; the other
...
9b3e  call   9b5a           ; the index, from the mode flags
9b40  retc   ntc            ; no flag set, nothing to start
9b42  opl    @6f, #4040
9b44  add    @7c
9b45  tblr   @7d
9b47  bacc
```

The selector at `9b5a` is a sequence of `bit n, @cell ; lacl #index ; retc tc`.
Thus the flag that a modulation sets fixes the slot of that modulation. Nine
slots:

> **Bit codes are not bit numbers.** The C5x `BIT` instruction shifts by
> `~code & 0xf`, so `bit 14, @27` tests **bit 1**. The table below gives bit
> numbers; the instructions give the codes.

| slot | flag | table `9b48` | table `9b51` | |
|---:|---|---|---|---|
| 0 | `@27` bit 1 | `9d00` | `9d00` | **overlay 6's entry** |
| 1 | `@26` bit 4 | `b000` | `b000` | **overlay 7's entry** |
| 2 | `@27` bit 3 | `b052` | `b052` | resident |
| 3 | `@26` bit 5 | `c533` | `c7fd` | resident |
| 4 | `@26` bit 3 | `cd61` | `cce0` | resident |
| 5 | `@26` bit 2 | `cd79` | `ccfa` | resident |
| 6 | `@27` bit 10 | `da31` | `d9bc` | resident |
| 7 | `@27` bit 12 | `d808` | `d7fc` | V.21, own band |
| 8 | `@26` bit 6 | `d7e9` | `d7d8` | Bell 103, own band |

`courier_emu.fsk.mode_tables` and `mode_flags` read the two tables from the
image. They do not repeat them. [datapump-slots.md](datapump-slots.md) names
all nine slots. It also explains the two items that the table does not carry:
the PCM downstream layer and the fax modulations.

A second dispatcher on the **same flag bits** - `9da6`, `a00d`, `9dc1`, `a054`
- branches to different entries. It goes to the four cross-band FSK entries
`d7f4`, `d7e3`, `d802`, `d80e`, and for slots 4 and 5 to `cd13`/`cd42` and
`cc9e`/`ccc6`, which are adjacent to `cd61`/`cd79` and `cce0`/`ccfa` of the
table. Thus these modulations each have two entry points. For the two that we
can read, the two entries are different only in the band of the receiver.

The path leaves a marker. `9b42` sets `@6f` bit 14, and each entry that it
dispatches to sets it again - `9d00` of overlay 6 writes `#4042`, `b010` of
overlay 7 and the resident `b052` write `#4841`. Entries that the code gets to
in a different way write `#0040` or `#0043`. Five resident sites test that bit
and configure differently. At `8d6f`, it swaps the transmit carrier between
`#2000` and `#4000`. At 9600 Hz, these are 1200 and 2400 Hz, the V.22
originate and answer carriers - again a transmitter moved onto the band of its
own receiver.

## The overlays carry no loopback entries of their own

Nothing in overlays 6, 7 or 8 sets up an FSK band. A scan of each image for
`splk @72` and `splk @73` - the mark and space increment cells - finds the
eight resident writes and nothing in overlay 6 or 7. The nine hits in overlay
8 are loop counters on a different data page (`splk @73, #0005`, `#001f`,
`#0004`). The four 300 bps bands, all eight transmit/receive pairings, and the
two dispatchers are resident.

But the overlays have a place in the table: slots 0 and 1 are their entry
addresses - V.34 and V.FC, as [datapump-slots.md](datapump-slots.md) tells.
Their loopback behaviour is **not** established here, and two facts tell us to
leave it like that. No overlay tests `@6f` bit 14, and none of them calls one
of the five resident routines that test it - their entries set the bit and
continue. Also, the meaning of that bit is not known: the `8d6f`
interpretation above agrees as much with an answer-side flag as with a
self-test flag. Only the two FSK slots are shown to listen to themselves.

## The core bug that hid all of this

`MAC`, `MACD`, `MADD` and `MADS` are the FIR instructions of the C5x: each
moves through a coefficient table in **program** memory together with a data
window. Two items were incorrect in `native/c5x_ops.ipp`. Together, they made
each filter in the firmware return zero or meaningless values:

* **The coefficient address did not advance under `RPT`.** These four
  instructions used the outer repeat loop, which executes the instruction
  again with the program address reset. Thus a `rpt #0e ; macd *-` convolved a
  15-sample window against one constant coefficient, not fifteen different
  coefficients.
* **`MADD` and `MADS` read their coefficient from data memory** at BMAR. They
  address program memory. Each coefficient table that this firmware uses -
  `d9a3`, `d9b2`, `d98f`, `872f` - is a program address immediately after the
  code that scans it. Thus the data-memory read returned zero for all of them.

The two items are corrected in the same form that the file already uses for
`TBLR` and `BLPD`: the instruction consumes the repeat internally and
increments a local `pfc`. All four instructions now also load `TREG0` with the
data operand, as SPRU056D specifies.

`tests/test_c5x_anchoring.py` pins the correction with a four-tap `MADS`. The
test compares its answer with hand arithmetic. If you revert either half of
the correction, the test fails.

The correction made this document possible. It also removes a limit that
[answer-tone.md](answer-tone.md) recorded: the `8712` and `8716` variants of
ANSam were silent only because their shaping filter returned zero. Now they
render. The 15 Hz modulation is visible as a symmetric sideband pair at 2085
and 2115 Hz, each about 10% of the carrier.

## Two traps for anyone extending this

The two traps caused a loss of time here, and the two are silent - the code
runs and gives a plausible incorrect answer.

1. **ARP, not the register name.** `BANZ *-`, `MADS *+` and similar
   instructions index through the register that `ARP` points at. `LAR AR1, ...`
   does not change `ARP`. The mixer of the firmware sets `ARP` to 1 at `80c9`.
   Thus a harness that enters below that line uses `AR0`, without a warning.
2. **Data page 0 is the memory-mapped registers.** `SPLK @1f, #x` writes BMAR
   only with `DP` at 0. On all other pages, it writes a usual variable.
