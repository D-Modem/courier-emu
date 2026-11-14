# The codec on the 3.1.2 board: DSP-driven, and not fixed at 7200 Hz

> **Resolved.** [codec-sample-rates.md](codec-sample-rates.md) solves the
> contradiction that this document builds and leaves open. The claim that is
> not true is "the divider registers are written once at reset and never
> again". A second, table-driven routine at `8140` - immediately after the
> sender at `8138` - **inlines** the handshake of the sender. It does not call
> it. It writes register 2 with one of `0214`, `0213`, `0212` (B = 20, 19, 18),
> as the negotiated symbol rate of V.34 selects. The three sample rates are
> 7200, 7578.95 and 8000 Hz. Each scan recorded below looked for *calls* to the
> sender. This is why none of them found it. All other statements here stay
> true.

This document corrects two claims. The firmware of this board *does* drive its
TLC320AC01 from the DSP. The 7200 Hz value in
[audio-312-path.md](audio-312-path.md) is the rate of the **dial path**, not
the only sample rate of the board.

## The AC0x protocol is in this image

[board-parts.md](board-parts.md) describes the protocol of the part
correctly - a TLC320AC0x connects to a TMS320 serial port and uses bit 0 of
the transmitted word to request a secondary control frame. Then it concludes
that the 20.16 MHz board "carries a TI AC01 whose own firmware never drives it
from the DSP". That conclusion is not true for this build.

The serial ISR is that protocol:

```text
818d: lamm @6b      ; the secondary-frame request
818e: or   *+       ; OR it into the sample word
818f: samm @21      ; DXR
```

`819e` sends the control word from `006c` instead of a sample. The reset
programs six control registers through the sender at `8138`. The sender puts
the word in `006c`, sets the request in `006b`, and idles until the ISR has
sent it:

| call | word |
|---|---|
| `80a2` | `010a` |
| `80a6` | `0214` |
| `80aa` | `0300` |
| `80ae` | `0409` |
| `80b2` | `0505` |
| `80b6` | `0620` |

The earlier search looked for the initialisation routine of `main211` and its
table, and correctly did not find them. This image has its own different
routine. Thus interpretation 1 in that document - "the ASIC fronts the codec"
- has no support **for this board**. The measurement `dxr_writes` is 3, which
was the reason for that interpretation, came from `main211`. The DSP of
`main211` stops to transmit after reset. Here, `DXR` is written for each sample
at `818f`.

Also note that the program addresses in that document for the 20.16 MHz build
are the addresses of this document minus `0x8000`: its `TSPC` setup "at program
`0x008a`" is the `samm @32` pair at `808a` here. The two documents read the
same instructions.

## 7200 Hz is the dial path, and the dial path only

We inferred the rate from the phase increments of the keypad. That inference
is correct, but only for the code that it comes from. The increments of digit 1
give 696.97 Hz and 1209.05 Hz at 7200, in 0.05% of the DTMF pair. At 8000,
9600, 11025 or 14400, no value is close.

It is correct *because* the DTMF tolerance is tight. At ±1.5%, the same
increments with a 9600 Hz codec would give 929 Hz and 1612 Hz, and each
detector would reject them. Also, the ISR consumes exactly one buffer word for
each codec interrupt. Thus, during dialing, the rate of the generator and the
rate of the codec are the same number. The dial path really runs at 7200.

This is why it is not safe to use the value in general. `ATI7` on this unit
advertises `x2` and `V90`. V.PCM has an 8000-baud carrier and cannot operate
below the 3600 Hz Nyquist limit of 7200 Hz sampling. V.34+ at 3429 baud goes
to about 3673 Hz, and also does not fit. Thus the codec rate **must** change
between dialing and those modulations. That follows from two facts that are
already established. It is not a hypothesis: either the firmware programs the
rate again, or this board cannot do what its own identity string says.

7200 is a sensible base rate for the original targets of this firmware family
- V.32 and V.FC, well in the 300-3400 Hz telephony passband. The later
modulations were added to the same codebase over the years after. They are the
modulations that need a different rate.

## There is a runtime path to move it

`8138` has seven call sites. Six are the reset constants above. The seventh is
tag `2c`'s handler:

```text
86de: lamm @7a      ; the host's mailbox argument
86df: b    8138     ; straight into the codec control-word sender
```

Thus one mailbox command writes an arbitrary 16-bit word to an AC01 control
register at runtime. A rate change would use that mechanism.

**Not established: that the supervisor uses it.** Refer to the sections below.

## What the senders carry

The supervisor has two enqueue paths. The second path is the reason that an
earlier enumeration missed the dial tags:

| path | routine | format |
|---|---|---|
| three-word | `f678` | `ff00`, then tag in `AX`, then argument in `BX` |
| one-word | `f64c` | a single word, `(tag << 8) \| data` |

The dial marker confirms the one-word format: sites load `AX` with `1600` and
call it. This is tag `16` with argument `0`, exactly as
`courier_firmware_analysis.md` describes the dial conversation.

The two routines have far-call thunks at `0f644` and `0f648`, and most callers
use them. To resolve those, the address mapping in
[flash-addressing.md](flash-addressing.md) was necessary. A scan for the
offset field alone finds none, because the code gets to the thunk as
`8f46:01e4`. With the mapping, the number of visible send sites increases from
23 to 137:

| path | tags observed |
|---|---|
| three-word | `02 0f 10 11 12 17 19 1a 1b 1c 1d 1e 1f 21 2a` **`2c`** `30 32 33 36 37 39 3b 3c 48 50 51 52 70 71 73 74 76 77 78` |
| one-word | `01 05 06 0a 0c 0e 15 16 2a 3d 3e 3f 40 41 43 44 4a 4b 4f 55` |

Five sites build the tag and do not load it. They are not in those lists.

## Tag `2c` is sent - but it does not carry the rate

Three sites send it, each with `mov ax, 0x2c` immediately before the far
call:

| site | argument |
|---|---|
| `4a893` | `bx = 0405` |
| `4a8c1` | `bx = 0409` |
| `49a3c` | `bh = 4`, `bl` computed as two 2-bit fields, each forced non-zero |

All three write **register 4**. None touches registers 1 or 2. In the DSP
image, only the six reset sites call `8138` - a scan of each
`lacc #0nnn ; call 8138` pair in program `8000..f000` gives exactly those six.

Thus, on this firmware, the divider registers of the codec are written **one
time, at DSP reset, and never again**. The runtime path exists and the
firmware uses it, but for register 4. The two 2-bit fields of register 4 look
like gain, not rate.

## Which leaves a real contradiction

> **Closed.** Refer to [codec-sample-rates.md](codec-sample-rates.md): point 2
> below is false. We keep the paragraph that follows as the record of the
> question before we found the rate table.
>
> **Was still open.** For a short time this was marked resolved, because the
> board appeared to read samples on the two C5x serial ports. It does not: the
> apparent `TRCV` and `DRR` reads of overlay 6 are a data table read as code,
> and nothing in any image reads `TRCV`. Refer to the retraction in
> [vpcm-datapump.md](vpcm-datapump.md). The three facts below stay. They still
> cannot all be true, and the only sample path with evidence is the AC01.

These three items cannot all be true:

1. The dial path runs at 7200 Hz. The DTMF tolerance limits this strictly, as
   above.
2. Registers 1 and 2 are set one time at reset and never changed.
3. This unit does x2 and V.90, which need at least 8000 Hz. The option list of
   `ATI7` is the *enabled* feature set, not what the build could do. Thus the
   `x2` and `V90` entries mean that this board has the license and is expected
   to run them. The label of the unit is "COURIER V.34 Fax with V.32 bis".
   Thus V.PCM came as an upgrade to it, and this puts a V.PCM datapump
   somewhere in this image.

One item in that list is incorrect, and this document does not know which.
After this, we excluded the first candidate below. This makes the problem more
exact, but it does not solve it: no payload that the supervisor downloads
programs the rate again.

* ~~**A second DSP program.**~~ **Excluded.** The download-site scan was
  limited to the first code segment and to entry `8000`. When we extend it to
  all of the image and to each entry word, it finds three call sites. `rom.py`
  already says that this board has three. All three send the **same**
  payload: entry `8000`, flash `29140..36e8e`, 28,327 words. There is no second
  download.

  But there is about 55 KB of more C5x code immediately after that payload, at
  `36e8e..~44633`, and no download call refers to it. It is real code, and its
  internal call targets are consistent. But it contains **no** host sender
  (`out *, 0060`), **no** `DXR` write, and no codec initialisation - only
  algorithm code with no I/O. This is what datapump overlays look like. A
  second, table-driven transfer routine loads it - refer to
  [dsp-overlays.md](dsp-overlays.md) - as three images at program `9d00`,
  `b000` and `dc00`. Only one of them writes the codec, and that write is
  register 4 again. Thus the dividers stay unchanged after reset.

  All three 512 KiB 20.16 MHz images - stock 7.3.14, ID_SDL 4.03, and the flat
  `IDSDL302.ROM` - have exactly one codec initialisation, with byte-identical
  values `010A 0214 0300 0409 0505 0620`. `main211` is different
  (`0203 0502 0670`, register 2 = `03` against `14` here). This agrees with
  the conclusion that it is the 25.8048 MHz build.

* **Register 4 is not only gain.** If it carries a rate or filter select, the
  three sends above are the rate change, and our interpretation of them is
  incorrect.
* **The register numbering.** All of the `(register << 8) | data`
  interpretation depends on the observation that the reset sequence looks like
  registers 1-6 in sequence. This is a suggestion, not a decode.
* **The AC01 is not the converter of the datapump.** This would make all items
  agree: the part runs at 7200 Hz for dialing, call progress and voice, and the
  samples of the datapump go to a different location. It is a modified form of
  interpretation 1 of [board-parts.md](board-parts.md). The overlay region
  above gives weak support for it - something must supply data to algorithm
  code with no I/O. The argument against it: the ISR of the resident bank
  moves a sample at each codec interrupt, and there is no second sample path
  in this image.

## What would settle it

To read the six reset words as an actual sample rate, the AC01 register map
is necessary, and the repository does not have it. `board-parts.md` already
records that a guessed bit layout did not agree with the table of `main211`.
With the natural `(register << 8) | data` interpretation, these are registers
1-6 with `A = 10` and `B = 20`. If those are the usual dividers with
`Fs = MCLK / (2 * A * B)`, that is `MCLK / 400`. This needs a 2.88 MHz master
clock to give 7200 Hz. The 20.16 MHz of the board would give 50.4 kHz, which
is out of range for the part. Thus either the register interpretation or the
assumed master clock is incorrect.

There is a method that does not need the missing datasheet. We know the
7200 Hz of the dial path independently, from the increments. Thus the register
values of a second mode, whatever they are, would give the ratio between the
two rates directly. If we assume the form `Fs = MCLK/(2AB)`, they also give
`MCLK` itself. If we find one tag `2c` send with a known modulation, all of the
question changes from a datasheet lookup into arithmetic.


## Where the V.PCM datapump is not

Two searches for it found nothing, and one of them was the incorrect search.

There is no companding table - no monotonic run of 48 words or more in the
resident bank or the three overlays. There is only one in the supervisor, and
it does not have the shape of a companding table. That is the expected result.
The Courier operates in the linear domain. Thus its datapump does not need a
mu-law table, and this result does not tell whether V.PCM code is present.

There is also no tone table for the line probe. The probe signal of V.34 is
tones at multiples of 150 Hz. Thus a table of phase increments for it would be
an arithmetic progression whose step gives the sample rate directly - 0x0555
at 7200 Hz, a round 0x0400 at 9600. No progression with a plausible step
exists in the four images. Thus the firmware synthesises the probe in a
different way, and that route to the rate is closed.

## What the tag 46 window actually streams

The table that it reads from, at program `85f2`, is the **V.34 rate and
carrier table**:

| words | meaning |
|---|---|
| `0708 0725 074b 0753 0780 07a7` | 1800, 1829, 1867, 1875, 1920, 1959 - V.34 carrier frequencies |
| `0960 0ab7 0af0 0bb8 0c80 0d65` | 2400, 2743, 2800, 3000, 3200, 3429 - all six V.34 symbol rates |

`artifacts/dsp-window-pump-02/` and `-03/` describe these as "DSP program
memory matching the flash image at addresses predicted beforehand". This is
true, and it was the purpose of that run. But it does not tell all of their
meaning. The window reports which V.34 carrier and symbol rate the datapump
uses.

They are stored as decimal Hz and baud, not as phase increments. Thus they do
not carry sample-rate information themselves.

## Every way out, and why each is shut

The contradiction stayed after much searching. This is the list of solutions
that we tried and closed, so that nobody tries one of them a fourth time.

| way out | why it is shut |
|---|---|
| A second DSP program with its own codec setup | Three download call sites, all sending the same payload. See [dsp-overlays.md](dsp-overlays.md) |
| An overlay reprogramming the dividers | Only the six reset writes call the control sender at all, and the one write an overlay makes is register 4. **This is where the answer was**: the rate selector at `8140` does not call the sender, it inlines it - see [codec-sample-rates.md](codec-sample-rates.md) |
| Tag `2c` carrying the rate at runtime | It is sent, three times, and every one writes register 4 |
| A second converter on the TDM port | Retracted. Nothing in any image reads `TRCV`; the apparent reads are a data table |
| Samples arriving over external I/O instead | With the anchoring filter applied, the overlays have **no** real `in`/`out` at all, and the resident's are mailbox, window and codec-control ports. There is no `0x50`/`0x52`/`0x54` sample loop in this image |
| An interpolator between the tone generator and the codec | The main loop at `80c3` is a producer/consumer against the ISR's own pointer - `lar ar0, @10 ; cmpr eq ; bcnd` - producing exactly one output word per callback and stopping when it catches up. One sample per interrupt, no resampling |

Thus the only sample path in this image is the AC01 on the primary serial
port. The resident ISR moves one sample for each interrupt. The DTMF of the
dial path fixes the rate at 7200 Hz. The rate is set one time at reset and
never changed.

Two candidates stay, and the image alone cannot give the answer for either:

* **The divider registers do not mean what we assume.** All of the `A = 10`,
  `B = 20`, `Fs = MCLK / (2AB)` interpretation depends on the observation that
  the reset sequence looks like registers 1-6 in sequence. That needs the
  register map of the AC01.
* **An item in the DTMF chain is incorrect.** The chain is short, and we
  examined each link - a 16-bit phase accumulator at `8743`, one sample for
  each interrupt at `80c3`, sixteen increment pairs whose ratios are the DTMF
  ratios. But it is the only item that fixes the rate.

You can test the second candidate without a datasheet, and at low cost:
**record the modem when it dials, and measure the tones.** If they are 697 and
1209 Hz, then the codec runs at 7200 during dialling, and the contradiction is
real and has no explanation. If they are not, the chain breaks at a link that
the measurement will identify. `audio-312-path.md` records that physical
recording attempt as stopped. Now it is the cheapest experiment that is left,
not only an open item.
