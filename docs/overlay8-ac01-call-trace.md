# Linked AC01 call trace: blocked before overlay 8

We measured this on 2026-09-21 against the current native C51 core. This core
includes the AC01 frame-sync INT3 latch and the recognition of interrupts at
instruction boundaries. This is an incomplete routing investigation. It is
not evidence that the caller qualifies the answer signal.

## Reproduce with the settings EEPROM loaded

```sh
./courier link artifacts/courier-board-21210-capture-403/courier-board.rom \
  --with-dsp --nvram-fixture idsdl403 \
  --a-at ATX0 --a-at ATDT5551234 --b-at ATA \
  --line-frames 400 --instructions 400000000 \
  --dsp-write-watch 0xfffe --summary --socket /tmp/ac01-403.sock

./courier link IDSDL302.ROM \
  --with-dsp --nvram-fixture idsdl302 \
  --a-at ATX0 --a-at ATDT5551234 --b-at ATA \
  --line-frames 400 --instructions 400000000 \
  --dsp-write-watch 0xfffe --summary --socket /tmp/ac01-302.sock
```

For this command pair, `link` automatically holds the answering command until
the ring. The two runs use the same board model. They must have different
EEPROM fixtures: the extended-register block moves five words between
revisions. The 403 fixture is the full captured settings part. The 302 fixture
seeds the recovered settings and the extended-register defaults.

These commands keep `legacy_carrier_fallback` disabled. When you reproduce
this specific path, do not use `--line-audio-only` instead. That option also
disables the existing ASIC call-start helpers, which include the originating
overlay request. Thus it changes more than the publication of carrier events.

| Image | Failure PC | Download destination / `ff62` | PA7 | IMR | IFR |
|---|---:|---:|---:|---:|---:|
| Captured 403 | `8c37` | `a104` | `0202` | `002a` | `0014` |
| 302 with its NVRAM fixture | `06dc` | `a164` | `0202` | `0000` | `003c` |

The two runs stop with `C51 resident loader did not acknowledge overlay block`.
The transfer target of 403 is overlay **6**, not 8. When we decrease the
scheduling batch from 256 to 32, the same 403 destination and PC occur. A
diagnostic increase of the acknowledgement allowance from 20,000 to 2,000,000
DSP steps still fails at destination `a104` (PC `8c2d`). The selection of
board ID 7 also fails during overlay 6, at `a0f8`/PC `8c3c`. We did not keep
these diagnostic changes.

The 403 failure capture contains the deferred host message `(0017,505d)`.
Thus the start command was **not** released too early. The last host command
is `0002:9d00`, the download destination. PC `8c37` is in the resident FFT
routine. We do not know why the resident cannot acknowledge the next block.

## What actually reaches the serial ports

At the captured 403 failure:

| Observation | Count / last PC |
|---|---|
| DRR reads | 104,486 / `8182` |
| DXR writes | 104,515 / `818f` |
| TRCV reads | **0** |
| TDXR writes | 936 / `81b8` |

At `8182`, the resident reads the DRR of the primary port into its circular
buffer. `818f` writes DXR. Its secondary handler at `819e..81a5` writes the
control word from B2 cell `006c` to DXR and restores the primary handler. The
separate routine at `81a6..81b9` packs two scaled values into TDXR. Its TDXR
writes alone do not identify a DAC stream of the codec.

In the current AC01 implementation, each primary frame consumes one ADC sample
and clocks one DAC output. A secondary frame delivers a requested register
readback or zero. It consumes no ADC sample and adds no DAC conversion. The
two frame types latch INT3. The reset bits of the port continue to control the
receive/transmit interrupt flags of the port. In this resident, IMR `002a`
masks INT3.

`tests/test_c5x_interrupts.py` now examines the secondary frames for register
read and for register write: a new INT3 latch, the correct DRR word, no change
to the ADC consumption, and the delivery of the next queued sample on the next
primary frame. This is a **frame-boundary regression**. It is not the
requested regression for answer qualification in a linked call.

This document has no evidence from an executed overlay 8 that maps TRCV/TDXR
or `fffe/fffd` to a type of codec frame. Do not use the older observations of
the low-address TDM slots in `courier_firmware_analysis.md` as a trace of this
ROM call. We did not add a serial-port alias or an audio route through an
external data slot on that assumption.

## Diagnostic control and saved evidence

A separate, temporary Python probe suppressed the originating overlay request
of the bridge and delivered host tag `17` immediately. With the original
native core and the 403 NVRAM, the two ends completed 600 linked frames, heard
nonzero peer audio, and reported `connected_event_queued=False`. Neither end
loaded an overlay, and neither end read TRCV. This shows that the usual
resident audio path runs without the forced download. It does **not** show
native answer qualification, and it does not show that the removal of those
helpers is the correct fix. We did not keep the probe in production code.

The local evidence is in `artifacts/overlay8-ac01-trace-20260921/`: the
complete DSP program/data snapshot and the bridge state at the 403 failure,
and compact run summaries. Image SHA-256 values:

* 403: `f1c91621fbf14aad34547056feb4425e64fcf0b38ec5d57f86c9f432ca999db6`
* 302: `49f4182cc961aef983ff43468b7b7e55c03205c9dba80e9689fe20aa6ff2ccc5`

The next prerequisite is a completed native overlay transfer with the
corrected clock/interrupt model. Only after that can the slot accesses during
execution identify a correct routing change and support a positive regression
for answer qualification.
