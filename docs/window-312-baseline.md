# The DSP 3.1.2 readback window: baseline, and what it cannot see

The `0x60`/`0x62` window is the only channel that carries DSP state to the
host. This document records what the window holds on an idle 3.1.2 board. It
corrects two profile constants that we used across firmware revisions without
change. It also tells which questions about the audio path the window cannot
answer.

Evidence: `artifacts/dsp-window-pump-312-01/`, a run of 24 pumps on the
20.16 MHz board on `/dev/cu.usbserial-21210`, supervisor 7.4.16 / DSP 3.1.2.
There was no dialing and no firmware upload. The only writes were the six
mailbox registers and the bit-2 acknowledgement. After the run, the modem
answered `AT`.

## The stream is seven words, not six

`STREAM_SOURCES` gave six cells - `0307, 03ba, 0385, 030f, 031c, 0be6`. That
is one cell too few. In the two captured board images, the last step of the
streamer calls a packer. The packer reads the DP-007 cells `0381` and `0383`,
does a NORM of the sum, and puts an exponent/mantissa pair in scratch `007d`.
Then the streamer sends this pair as it sends each other source. Thus a run
carries a seventh word that is **calculated, not read**.

The hardware shows the same thing without the disassembly. Port `0x1c` bit 2
is the "another word is ready" flag of the DSP. Across 24 pumps, it stayed set
for exactly seven pumps. Then it cleared and stayed clear:

| pumps | `1C` | meaning |
|---|---|---|
| 1-7 | `FD` | bit 2 set: a further word pending |
| 8-24 | `F9` | bit 2 clear: the sequence is finished |

The handler moved between revisions, but its shape did not change:

| | 3.0.13 | 3.1.2 |
|---|---|---|
| handler | `8489` | `8470` |
| streamer (`out *, 0060`) | `84b7` | `849e` |
| packer | `84bc` | `84a3` |
| sources | the same six | the same six |

## Every word is zero on an idle unit

All 24 pumps read `0000`. The window held `004b` before the arming. Thus it
did change: it changed to zero and stayed there. This is a more exact form of
the note in `artifacts/dsp-window-pump-01/` - the sources are not only quiet
on an idle unit, they read as zero. It is a clean baseline: a non-zero word
after a command is a signal.

This run does not separate two possibilities: seven cells with a value of
zero, or a stream that ran its full length while its sources were empty by
chance. The bit-2 sequence shows the length. It does not show the origin of
the values.

## The supervisor chain moved, and was re-derived rather than assumed

The pump does not run unless the chain vector that it finds is an address
where the chain of the supervisor parks or steps. This is because the mailbox
interrupt dispatches through that vector. On this board, the check stopped the
pump: the vector cell `[0x02d3]` read `0000`.

That cell belongs to 7.3.14. In 7.4.16, the chain vector is **`[0x01cd]`**. The
derivation is structural, not a guess. The `mov [cell], imm` writes whose
immediate is a nearby code address identify the self-chaining vector uniquely.
There are exactly 14 of them on `02d3` in 7.3.14, and 14 on `01cd` in 7.4.16.
The chain code moves by a constant `+0x32`, and the arm site moves from
`6d08` -> `6d52`. Each of the 18 steps maps at that shift. This includes the
bare `ret` where the chain parks (`200c` -> `203e`). The countdown and the
header keep their positions on each side of the vector. The code in the chain
region refers to them the same number of times. The four buffers map at the
same instruction offsets, a constant `-0x10c`, with the length/count/pointer
trio intact at `-4/-3/-2`.

Then the board confirmed it: `[0x01cd]` reads `200d`. This is exactly the value
that the arm site of 7.4.16 writes there, and the run continued.

## What the window cannot see

No cell of the audio path is a source of either window:

| cell | what it is | streamed? |
|---|---|---|
| `0390`/`0391` | the ISR's sample-buffer pointer | no |
| `0399` | decremented once per codec interrupt | no |
| `039a` | the installed tone callback | no |
| `03c0`/`03c1` | the two oscillator phases | no |
| `03f2`-`03f5` | phase increments and amplitudes | no |

This has two results. Each of them changes work that we already recorded.

**The tone-diff experiment in [driving-the-tones.md](driving-the-tones.md)
cannot see the tone state on this firmware.** If you arm `06`, send the tone
sequence and compare the window, you test whether the tone path disturbs six
datapump cells that it does not write. A null result there would mean "not
visible here". That document already expected this as its second blocker. This
result makes the blocker specific and certain, not only a risk.

**The 7200 Hz sample rate in [audio-312-path.md](audio-312-path.md) is still an
inference.** `0399` is the natural measurement - read it two times across a
known interval, against the 5.000 ms tick that
[hardware-timebase-and-audio-path.md](hardware-timebase-and-audio-path.md)
established. But the host cannot get to it. A static walk of all 128 dispatch
entries at `83e9` looked for handlers that get to the `out *, 0060` site. It
found only `07`, `46` and `57`. Tag `4a` agreed only because
`opl @6f, #0060` is an OR with a constant, not an output. That walk has a
bounded instruction budget. Thus it is evidence that no arbitrary read of DSP
data exists. It is not a proof.

## Is `0399` mirrored in host RAM? No

We asked this question in two ways, and the two answers are no.

**Statically, the DSP never sends it.** Each word from the DSP to the host
goes out through the sender at `83bf`. A walk of all 128 dispatch entries gets
to none of the sites that touch `0399`. Of the sites that a linear scan finds,
only two are real code: the ISR at `8179`/`817b`, and a block at `d035`/`d038`
that three control-flow sites target under `ldp #007`. The other three
candidates are data read as code, and have zero control-flow sites - `8d04` is
a fourteen-word table of `0011`-`001f`, and the `a2e0` region decodes to
out-of-range branches. Also, `samm @19` and `lamm @19` address the
memory-mapped register `0x19`, not `0399`. Thus those sites do not belong on
the list.

**Empirically, no host cell changes at an audio rate.** `artifacts/host-ram-rate-01/`
reads again the five pages that changed between the two live passes in
`courier-board-21210-ram-01`. It reads them fourteen times over 18.3 s, and
each read has a time stamp from a monotonic clock of the host. It fits a rate
to each 16-bit cell. Thirty cells change. Exactly one is a counter:

| address | rate | what it is |
|---|---:|---|
| `0x012a` | **200.00 Hz** | the 5.000 ms firmware tick |

The other twenty-nine are not monotone and have a small number of different
values. This is a scratch region that changes continuously. Their fitted
"rates" are artefacts of the unwrapping of noise. One of them, `0x00e6`, is
monotone only after unwrapping, and it goes back to its start value. This is
what that artefact looks like from the inside.

The value of 200.00 Hz at `0x012a` is a fourth independent line of evidence for
the timebase, and the most direct one. The other three in
[hardware-timebase-and-audio-path.md](hardware-timebase-and-audio-path.md)
infer 5.000 ms from the `&T1` slope, from the seconds-to-ticks multiply of the
firmware, and from the 80186 timer constant. This scan reads the tick counter
itself.

The scan had sufficient resolution to find what it looked for. A sweep takes
about 1.3 s. In that time, a 7200 Hz 16-bit counter advances by about 9,360,
which is much less than one wrap. Thus this is a negative result, not an
inconclusive one. It applies to the low 64 KiB, and in it, to the pages that
changed between two passes 69 s apart. We did not scan the relocated
peripheral block at `0xff00` and the `0x10000..0x1ffff` window.

The practical result: **to measure the codec clock, a path is necessary that
does not exist yet.** The fixed windows, a mailbox query and a mirror on the
host side do not supply it. All of the remaining candidates are builds, not
reads - a tick-hooked sampler that reads the window densely, or a route that
puts `0399` into a location that the host can already see.

## Not established here

The window of tag `46` is still decoded only for 3.0.13. In 3.1.2, its handler
moved to `84ba` and reads a different table. Thus `PROGRAM_STREAM_BASE` and the
`03db` index do not apply to 3.1.2. On this firmware, the pump refuses
`--arm 46`, and the tests pin that refusal.

Also, the two board captures carry a DSP payload of a single segment at origin
`0x8000`. The `0x0000` segment that section 3 of the timebase document uses
for its reasoning belongs to `main211`, not to a board image. Thus the
question of what this board runs below `0x8000` is open. These captures do not
answer it.
