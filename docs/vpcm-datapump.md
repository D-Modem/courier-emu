# Where V.PCM lives, and why 7200 Hz was never the whole story

Overlay 8 is the V.PCM datapump - x2 first, with V.90 on top of it. Its own
DIL descriptor identifies it. This finding also explains how a board whose
codec has one fixed rate runs a modulation that needs a different rate: there
are two serial converters, not one.

## The identification

In the digital impairment learning of V.90, the analog modem sends a Ja
descriptor. The standard fixes its sign and training patterns. Thus they are a
signature. The two patterns are in the flash, packed LSB-first, and the two
agree bit for bit across 66 bits:

```text
4234c  55 4b 2d b5 b4 d2 4a 2b 01   SP  101010101101001010110100101011010010110101001011010100101101010010
42356  00 21 84 10 22 84 10 42 00   TP  000000001000010000100001000010000100010000100001000010000100001000
42360  0a 0a 0a 0a 0a 0a 0a 0a      H1-8 = 10, 10, 10, 10, 10, 10, 10, 10
42368  00 00 00 00 00 00 00 00      REF all zero
```

The reference values are the notes of the user for the descriptor. The flash
contents above are what this image holds. H1-8 and REF follow immediately, in
the sequence that the notes give. This changes two pattern hits into a
descriptor block.

That block is in **overlay 8**, at DSP program `e7d6`. The 3.0.13 board and
`IDSDL302.ROM` have the same block in their own overlay 8, at `e599`.

The descriptor is stable across each image here. The signature of the
assembler - `splk *+, #00c5` then `splk *+, #4141`, so N = 197 and LSP = LTP =
66 - occurs in all four images, including `main211` from 2003, and the SP and
TP patterns are identical with it. Thus this descriptor did not change between
the oldest build in this repository and the newest build.

**An earlier version of this document concluded more than the evidence
supports.** It said that the 3.0.13 DSP has the stamp `03/13/98`, about six
months before the approval of V.90, and thus the descriptor must belong to x2,
with V.90 on top. Two facts weaken that argument:

* The `ATI7` date is a stamp in the image. We do not know what it actually
  records - when the code was written, built, or released to users. The
  argument needs it to mean the first of those.
* x2 and V.90 have much in common, and the work of USR went into the
  recommendation. If the two use the same descriptor, then this image cannot
  answer "x2's or V.90's", because there is no difference to find.

The images support a narrower statement that is still useful: **one page
carries the V.PCM datapump, its descriptor did not change across five years of
builds, and nothing here separates an x2 descriptor from a V.90 descriptor.**
Whether x2 and K56flex had an equivalent impairment-learning phase is a
question about those specifications, not about this ROM. This document does
not answer it.

The training UCode sequence is not stored in any image, in bytes or in either
word order. The firmware generates it and does not keep it in a table - and a
run of the generator confirms it, below.

## The assembler, and the descriptor it produced on the wire

Immediately after the field block, at program `e7e8`, is the code that builds
the descriptor:

```text
e7e8: ldp  #006
e7e9: lar  ar1, #0940      ; the build buffer
e7eb: splk *+, #00c5       ; N = 197
e7ed: splk *+, #4141       ; LSP-1 = 65 and LTP-1 = 65, packed as two bytes
e7f0: blpd *+, #e7d6       ; 5 words of SP
e7f3: blpd *+, #e7db       ; 5 words of TP
e7f6: blpd *+, #e7e0       ; 4 words of H1-8
```

Thus `N = 197`, `LSP = 66`, `LTP = 66`, and the patterns come directly from
the block above.

We can examine this against the wire. It does not have to stay only an
interpretation. The V.90 DIL lab of the user has `COURIER_JA_HEX`, a 2058-bit Ja
recovered from a capture of the transmission of this modem, with a valid CRC.
We parsed it with the field framing of that tool and compared each field with
this image:

| field | transmitted Ja | overlay 8 | |
|---|---|---|---|
| N / LSP / LTP | 197 / 66 / 66 | 197 / 66 / 66 | match |
| SP | 66 bits | `e7d6` | match |
| TP | 66 bits | `e7db` | match |
| H1-8 | 10 x8 | `e7e0` | match |
| REF | 0 x8 | `e7e4` | match |

Each field agrees, from the ROM to the signal.

The raw recovered hex does **not** occur in the flash. That is the expected
result, not a contradiction. The wire format has framing: a zero bit before
each chunk of up to 16 payload bits, and the H and REF entries as 7-bit values
between framing bits. The ROM stores the patterns without framing and
LSB-packed. The firmware adds the framing, the training Ucodes and the CRC when
it assembles the descriptor - this is the purpose of the CRC below.

## The four images, and which ones do I/O

| image | loads at | span | serial-port access |
|---|---|---|---|
| resident | `8000` | `8000..eea7` | `TSPC` setup x2, `DXR` write x4, `DRR` read x1 (the ISR) |
| overlay 6 | `9d00` | `9d00..ce32` | **none** |
| overlay 7 | `b000` | `b000..cd4a` | none |
| overlay 8 | `dc00` | `dc00..f94a` | none |

Overlay 8 does not touch a converter. It is only algorithm, and it does not
overlap overlay 6. Thus the two are loaded together: 6 is the datapump, and 8
runs V.PCM on the output of 6. Overlay 7 is in the range of overlay 6. Thus
those two are alternatives.

## Retracted: there is no second converter here

> An earlier version of this document said that the board takes samples on the
> two C5x serial ports. It used that to solve the 7200 Hz problem in
> [codec-rate-312.md](codec-rate-312.md). **That was incorrect.** It was based
> on the observation that overlay 6 appeared to read `DRR` 32 times and `TRCV`
> four times. Each of those 36 sites is in a data table that disassembles into
> plausible instructions. They are in two contiguous blobs at `c019..c207` and
> `ca64..cbf2`. None of them has a control-flow target in 48 words, but each
> site in the resident bank has one. `tools/c5x_disasm.anchored` now makes that
> test easy, and `tests/test_c5x_anchoring.py` pins these exact addresses. Thus
> the mistake cannot come back without notice.
>
> Only this fact stays: the resident bank sets up `TSPC`, the control register
> of the TDM serial port, at `808a`. **None of the four images ever reads
> `TRCV`.** Thus the port is configured and then not used. This is a much
> weaker fact than "the two converters are in use", and it does not solve
> anything.
>
> Thus the 7200 Hz contradiction is **open again**, and more difficult than
> before: the only sample path that has evidence is the AC01 on the primary
> port.

## The far end sent exactly the ladder this ROM generated

`artifacts/dil-alaw-01/` is a DIL that a digital modem sent downstream as the
answer to the own Ja of this Courier. It is 13,002 bytes of G.711 A-law, which
is `197 x 66` - N segments of LSP symbols, and the two numbers come from the
descriptor. Thus the length of the capture alone confirms the request that it
answers. Compared with the ROM:

| | result |
|---|---|
| signs | all 13,002 follow the descriptor's `SP` |
| `TP` = 0 slots | every one carries Ucode 0's level, magnitude 8 |
| `TP` = 1 slots | each segment holds one level across its twelve |
| that level | is the level of the Ucode this firmware generates for that segment |
| overall | 117 distinct Ucodes to 117 distinct levels, one to one, no exceptions |

Thus the generated ladder is not only plausible - the far end answered it
symbol for symbol. `tests/test_vpcm.py` pins all four results.

The levels also identify the law. A Ucode is a G.711 chord decomposition. The
two laws are different by the 132 bias of mu-law and by the first chord of
A-law: Ucode 100 is 10496 in A-law and 10364 in mu-law. Each segment agrees
exactly with the A-law form. This is what the name of the capture says was
requested. `vpcm.ucode_level` has the two laws. A-law is verified here, and
mu-law is only the arithmetic of the standard.

## Scoring an impaired one

`artifacts/dil-ulaw-impaired-01/` is the same DIL with impairments applied
intentionally, and in mu-law. The clean DIL is A-law. `vpcm.score_dil` compares
either DIL with the ladder:

| | clean (A-law) | impaired (mu-law) |
|---|---|---|
| signs wrong | 0 | 0 |
| training symbols exact | 2364 / 2364 | 66 / 2364 |
| gain | 1.0000, 0.00 dB | 0.4986, **-6.04 dB** |
| reference slots disturbed | 0 / 10638 | 5139 / 10638, worst 244 |

There are three interpretations, and these are the facts that separate them:

* **A 6 dB digital pad.** The gain is flat across all six data-frame intervals,
  -6.05 to -6.08 dB, and the modal Ucode error is **-16** - one mu-law chord.
  One chord is 6 dB.
* **Additive noise on top.** A pad scales, so it keeps a silent slot silent.
  Almost half of the reference slots are not silent, and a pad cannot explain
  this. After we remove the pad, the residual has a standard deviation of about
  79. With the pad removed, a quarter of the training symbols are on the exact
  Ucode, and the others are one to three away on each side. That is the noise.
* **Not robbed-bit signalling.** RBS occurs on specific data-frame intervals.
  This impairment is flat across all six. Thus, it is not RBS. The signs are
  all still correct, and this shows the same thing from a different direction:
  the impairment is on the amplitude only.

A DIL exists to make this comparison, and the own matcher of the datapump
makes the same comparison. When we run it here, we do not find that routine -
refer to the section below. But it shows that the ladder that the firmware
generates is sufficient to characterise a channel. The descriptor depends on
this claim.

## The matcher itself has not been found

To score a DIL, you compare what arrives with the level that each training
Ucode must produce. The levels are linear: chord `u >> 4`, step `u & 15`,
magnitude `(2 * step + 33) << chord`. This puts Ucode 100 at 10496 in a 16-bit
sample. `vpcm.ucode_level` writes that out for comparison with a capture. It
is the arithmetic of the standard, not a recovered routine.

We have **not found** the routine that does it. What we know is narrower, and
we keep it separate from the expectation:

* There is **no companding table** in the four images - not the mu-law chord
  ladder (33, 99, 231, 495, 1023, 2079, 4191) in either direction, and no
  monotonic run of levels. Thus the firmware calculates the conversion. That
  agrees with a Courier that operates in linear levels, and with V.90, which
  needs A-law and mu-law. A table is not useful for either law if the chord
  arithmetic is a small number of instructions.
* **Overlay 8 cannot receive the DIL.** It has no serial-port access. The
  samples exist only in overlay 6. The two are co-resident, so a matcher goes
  across them. This is why a search of overlay 8 alone would not find it.

We record two searches that failed, so that nobody repeats them. A trace of
the readers of the descriptor buffer at `0940` gives mostly false leads,
because overlay 8 uses that address again as a bit-field (`bit 8, *`,
`opl *, #1000`). Also, the variable-shift instructions that would implement a
chord expansion - `lact`, `addt`, `subt` - are not a usable filter. The
apparent cluster in overlay 6 is a data table read as code. The real cluster in
overlay 8 at `ea91` is a mask generator, `samm @0d` then `lact @7b` then
`sub #01`, which is `2^n - 1`.

### What the last search turned up instead

Overlay 6 at `a650` is a variable-width bit-field extractor over the same
`0940` buffer. It normalises to find a bit position (`rpt #0e ; norm *-`),
builds a mask of that width, and extracts fields of 2 and 6 bits. A flag
selects between `0340`/`0341` and `0940`/`0941`. That is descriptor framing,
not DIL scoring. Its mask generator has the same shape as the generator of
overlay 8 at `ea91` - `samm @0d`, then `lact`, then `sub #01`. Thus the two
pages share that helper.

To find the matcher, use a dynamic trace, not cross-references: run the
datapump in the core and watch which addresses are read back after the
descriptor is assembled. `vpcm.assemble` already sets up a working entry,
including the ARP detail above. What is missing is a plausible state from which
to enter the receive path.
