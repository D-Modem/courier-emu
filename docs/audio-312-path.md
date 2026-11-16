# DSP 3.1.2 audio path: original firmware now produces samples

The connected 20.16 MHz Courier runs supervisor 7.4.16 / DSP 3.1.2.
In the component harness, its own code generates all 16 DTMF pairs and sends
the samples to the standard DSP serial transmitter. The harness does not
synthesize a sine wave. It does not insert PCM into the output buffer of the
firmware.

We read five flash pages from the modem. These pages contain the tone
selector, the oscillator, the mixer and the serial ISR. They agreed with the
captured 3.1.2 ROM. Refer to
`artifacts/audio-312-01/hardware-firmware-check.json`.

## The path in this firmware

```text
host tag 13, digit index
    -> ee20: select phase increments, install callback 8743
    -> 80d3: call current callback, clear output accumulator in delay slots
    -> 8743/874f: advance two oscillators using sine helper 8b6a
    -> DSP data 03c7: combined tone sample
    -> 80da..80e7: apply gain, clear low codec bits, store interleaved buffer
    -> 8178 ISR: read DRR into input slot, read next (output) buffer slot
    -> 818f: SAMM @21 writes DXR, the standard serial transmit register
```

Tag `13` masks the index to four bits and reads two phase increments from
`ee34 + 2*index`. The phases are data `03c0`/`03c1`. The increments are
`03f2`/`03f4`. The amplitudes are `03f3`/`03f5`. Its callback address is in
`039a`. Tag `16` replaces that callback with the bare return at `8128`.

The main loop writes an output word next to an input word in the circular
sample area, which is initialized at `0bc0..0bdf`. The serial ISR reads `DRR`
at `8182` and writes the input slot. Then it loads the adjacent output word,
before it writes `DXR` at `818f`. It ORs in the secondary-frame request at
`006b`. The control sender at `819e` sends the control word from `006c`
instead of a sample.

This is evidence for a serial-codec audio path in **this image**. It does not
prove which board pins carry that serial stream. The external-I/O audio path
of `main211` and its runtime counters describe a different image. Do not use
them to exclude this one. Also, the interpretation that an ASIC is in front
of the codec here has no support now: the ISR at `818d` implements the AC0x
secondary-frame protocol, and the reset programs six of the control registers
of the part. Refer to [codec-rate-312.md](codec-rate-312.md).

## Why the emulator was silent

When we single-stepped the sine helper, we found three instruction errors. We
corrected them against TI's [TMS320C5x User's Guide, SPRU056D](https://www.ti.com/lit/ug/spru056d/spru056d.pdf):

* `SQRA` and `SQRS` ignored the memory operand and squared the old TREG0.
  Now they read the operand, and update the temporary registers as the TRM
  specifies. They calculate the square after they accumulate the previous
  product (sections 6-253 and 6-255).
* `PAC` added the product to ACC instead of a replacement of ACC. It also
  changed the arithmetic flags incorrectly (6-193).
* `NORM` did not update TC, and did not handle zero as complete. The sine
  helper uses that flag to select the sign of the result (6-181).

The disassembler also incorrectly decoded `NORM` as two words. Thus it
consumed the `SQRA` instruction after it. We corrected that decoding
separately.

## Reproducing and listening

```sh
.venv/bin/python -m courier_emu.audio312 \
  --rom artifacts/courier-board-21210-capture-403/courier-board.rom \
  --output /tmp/courier-audio-reproduction
```

The output is `firmware-dtmf.wav` and a JSON manifest with spectra for each
digit, PCM hashes, and serial counters. The saved run in
`artifacts/audio-312-01` contains `123456789*0#ABCD`, with 200 ms for each
digit and 100 ms of silence between digits. Each digit has the expected
row/column spectral pair. Each 1440-sample tone executes 1440 DRR reads and
1440 DXR writes at the original firmware sites. The runner compares each
serial output word with the word that the original mixer put in the buffer.

The WAV uses **7200 samples/second**. We inferred this from the labelled phase
increments of the keypad: digit 1 uses `18c8` and `2afd`, which agree with
approximately 697 and 1209 Hz at that rate. This is not yet a measurement of
the physical codec clock.

That value is the rate of the **dial path**. Do not read it as the only sample
rate of the board. For this code, it has a good basis: the tight tolerance of
DTMF means that no other possible rate agrees. Also, the ISR takes one buffer
word for each codec interrupt. Thus, during dialing, the generator and the
codec run at the same rate. But this unit advertises `x2` and `V90`. Their
8000-baud carrier cannot operate below the 3600 Hz Nyquist limit of 7200 Hz
sampling. V.34+ at 3429 baud also does not fit. Thus the codec rate must
change for those modulations. Tag `2c` is a mailbox command that writes an
arbitrary AC01 control register at runtime. Refer to
[codec-rate-312.md](codec-rate-312.md).

The component harness supplies idle RAM, the gain/amplitude values of the
dial path, a dummy second callback, and one reusable pair of input/output
buffers. It calls the selector, the original mixer of the main loop and the
body of the serial ISR. It stops before RETE, because it did not enter through
a real interrupt. Thus the result proves the sample computation and the
transport through the firmware. It does not prove the full boot, the interrupt
scheduling, the analog levels or a completed modem negotiation.

## Physical recording attempt

Asterisk at `root@asterisk.net.cryan.nz` has the local echo test `9099`.
We made two attempts from serial `21210`. The first attempt had delayed
digits at the end. The second attempt used only `ATDT9099;`. Neither attempt
made a `9099` channel on Asterisk before the bounded timeout. We stopped the
two attempts, then sent `ATH`, and then a successful `AT`. We did not start a
recording, we did not change the PBX configuration, and we did not record a
different call. The transcripts are in `artifacts/audio-312-hardware-01` and
`-02`. Before we can compare a physical waveform, we must map the Courier to
its actual gateway port.

## Validation limits

The focused arithmetic tests, the all-digit audio tests, and the prior DSP
audio/readback/stream and mailbox tests pass (54 tests). The full suite did not
complete: two existing modules import the removed names `FIRST`/`RESET`, and
the CPU/CLI paths get a Unicorn SIGILL in this environment. An isolated
bridge/CLI run passed 29 tests before it stopped on three CLI worker SIGILL
failures. Because of these failures, we cannot claim that the full-supervisor
behavior has a regression test.

The earlier difference in the `62` query stays after the arithmetic
corrections: hardware `0069:0015`, fixture-state emulator `0069:0012`. We did
not use the audio progress to hide that difference.
