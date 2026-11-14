# x2 byte loss at 54666 bit/s: frame interrupt timing

In emulated x2 calls against D-Modem, the Courier loses full bytes from frames
that it receives at the high x2 rates. At 32000 bit/s, it loses no bytes. This
note gives the evidence that the cause is the timing of INT0 (the coprocessor
frame edge) in the emulator. It also describes two partial corrections that
are on this branch. The two corrections are disabled by default.

All of this is black-box work: captures of the ports of the emulator and of the
line, with no change to the firmware.

## What is lost, and where

- We decoded each frame that D-Modem sends from the line recording
  (`engine-tx.g711`) and examined it with its FCS. Each frame leaves D-Modem
  intact.
- The receive path of the DSP gives data to the CPU through 6 banks on CPU
  ports 0x40–0x56 (a hi byte of 0 means a data byte; ff00 means idle). We
  captured each CPU read of those ports (`COURIER_LANE_CAPTURE`) and paired
  each hi port with its lo port. This gives the byte stream that the CPU sees.
- When we align the two streams, they show deletions of 1–4 bytes, about one
  in each 30 bytes at 54666 bit/s. There are no bit errors and no inserted
  bytes.
- A log of each DSP write to the banks (0x58–0x5d) found 475,316 writes. The
  CPU acknowledged each write before the next write. Thus no bank is
  overwritten: the bytes are lost in the DSP before they get to the banks.

## Why: INT0 is only delivered on timer polls

- The CPU services the banks from its INT0 handler. On the live board, we
  measured INT0 at 2401 Hz. This is about 1416 CPU instructions for each
  frame (`FRAME_INSTRUCTIONS`).
- The emulator examines a due INT0 only at a timer poll, one time in each
  `TIMER_POLL_INSTRUCTIONS` (1024). This is true for the Python
  `fast_service_rest` and for the native worker (`courier_worker_poll` in
  `native/c5x_capi.cpp`).
- Thus edges arrive up to 1023 instructions late, and two edges can become
  one. In the baseline capture, the gaps between bank services are on
  multiples of 1024 instructions: 896, 1920, 2944 and 3968 (128-wide bins).
  About a third are 2 frames or longer.
- The deletions follow those long gaps. The median gap before a deleted byte
  is about 2800 instructions (2 frames or more). The median between all bytes
  is 50.
- At 54666 bit/s, the DSP has about 2.8 bytes for each frame. When the service
  of a frame does not occur, the small internal queue of the DSP overflows and
  bytes are lost. At 32000 bit/s, there is sufficient margin.

## The fix on this branch

`COURIER_INT0_EXACT=1` delivers INT0 at the first service step at which it is
due, not only at a timer poll:

- `courier_emu/machine.py`: a branch in `fast_service_rest` that dispatches
  INT0 when it is due (IF set, vector installed, not already in service). It
  uses the same catch-up rule as the timer poll path.
- `native/c5x_capi.cpp`: the same change in the native worker. The frame edge
  bookkeeping is no longer only in the timer poll branch.
- `COURIER_NATIVE_SERVICE=<n>` sets the native service step. The default stays
  at `TIMER_POLL_INSTRUCTIONS`. The correction works only with a shorter step,
  because the worker runs one time for each step. 256 works. 128 makes the
  Courier clear the call.

The two settings are off by default, and the default paths operate as before.
The native, bearer and interpreter tests give the same result with and without
the change (55 passed, 1 failed). That failure is in
`test_rom_console_polls_and_closes_without_global_hook`, and it also fails on a
clean `main`.

## Results

These are calls against D-Modem (`tools/probe_v90modem_closed_loop.py analog`,
`AT+MS=X2`) that send text lines. "Whole" counts the FCS-good frames from
D-Modem that got to the CPU without loss.

| Call | Line loss | Rates | Frames whole | Lines through | End |
|---|---|---|---|---|---|
| Baseline | 0 dB | 54666 | 166 / 306 (54%) | 30 | Courier cleared down at 94 s |
| `INT0_EXACT` only | 0 dB | 54666 | same as baseline | 30 | same as baseline |
| `INT0_EXACT`, service 256 | 0 dB | 54666 | 334 / 560 (60%) | 35 | held to hangup |
| Baseline | 6 dB | 52000, 53333, 54666 | 258 / 460 (56%) at 54666 | 29 | held |
| `INT0_EXACT`, service 256 | 6 dB | 52000, 53333, 54666 | 169 / 244 (69%) at 54666; 14 / 17 at 53333 | 78 | held |
| `INT0_EXACT`, service 128 | 0 dB | 54666 | — | — | Courier cleared down at 57 s |

With the correction, the service gaps are near one frame (1152 and 1408
bins), not on the 1024 grid. About a quarter are still 2 frames long (the 2688
bin), and the bytes that are still lost follow those gaps.

## The frame edge's source: the DSP's timer

The CPU-side counter above is a substitute. On the hardware, the edge has a
source:

- `docs/asic-pinout.md` traces DSP pin 122, `TOUT` (the on-chip timer output
  of the C5x), back into the ASIC. The ASIC is the part that drives the
  interrupt lines of the CPU.
- The ISDN machine in this repository already raises its frame interrupt
  (IRQ13) from `timer_expiries()`, one edge for each TOUT pulse. The Quad
  routes the timer of its C50 to its INT0 in the same way.
- We sampled the timer of the emulated C52 during an x2 call
  (`COURIER_TOUT_LOG`). It gives 3,526 pulses for each 5,000,000 harness
  instructions during all of the call. At the 3,399,663 instructions each
  second of the 20.16 MHz board, that is 2,397 Hz. 8,400 CLKOUT cycles at
  20.16 MHz is exactly 2,400 Hz. We counted the INT0 of the live board at
  2,401 Hz.

Thus INT0 is very probably TOUT. `COURIER_INT0_TOUT=1` models it in that way:

- Each new TOUT pulse latches one request, as the edge-triggered request bit
  of the 80186 does. It is latched independently of IF and of whether INT0 is
  in service. If a second pulse occurs before the CPU takes the request, the
  two pulses become one request.
- The CPU takes the request at the first service step where IF is set and
  INT0 is not in service. This occurs in the Python paths
  (`Machine._int0_frame_due` / `_int0_frame_taken`) and in the native worker,
  which gets the fields `int0_tout`, `tout_seen` and `int0_request`.
- Without the setting, the edge runs freely on the instruction count as
  before.

The old model also lost edges in a way that the hardware does not: it latched
an edge only while IF was set, and then the catch-up rule discarded the
missed edges.

### Results with the DSP timer as the source

| Call | Line loss | Service step | Lines through | End |
|---|---|---|---|---|
| Baseline | 0 dB | 1024 | 30 | Courier cleared down at 94 s |
| `INT0_TOUT` | 0 dB | 1024 | 50 | held to hangup |
| `INT0_TOUT` | 0 dB | 256 | **93** | held to hangup |
| `INT0_TOUT` | 0 dB | 128 | 87 | held to hangup |
| `INT0_TOUT` | 0 dB | 512 | — | carrier lost at 34 s |
| `INT0_TOUT` | 6 dB | 256 | — | training failed (twice, two seeds) |
| `INT0_TOUT` | 9 dB | 256 | — | carrier lost at 31 s |

At 0 dB and a step of 256, 207 of 290 frames arrived whole. The modem sent
fewer frames than in the baseline, because it had to send fewer frames again.
A step of 128 now works. With the counter, it made the Courier clear the call.

### The 6 dB and 9 dB failures

An earlier version of this note said that the cause was a worse upstream
signal of the Courier with a full-rate INT0. That came from a single MSE
reading for each call, and it is not correct. Over full calls, the equalizer
MSE of D-Modem on the upstream data of the Courier is the same in each mode
(medians 0.15–0.18 for the baseline, `INT0_EXACT` and `INT0_TOUT`, at 0 dB
and 6 dB). Also, the DSP never misses a DAC sample in either mode (a counter
on `codec_frame`: 19 missed in the first 80,000 frames, all before the call,
and none after).

All of the x2 calls have a poor upstream in data mode: the MSE is about 0.0002
during V.34 training and 0.1–0.2 when data starts. D-Modem sees hundreds of
FCS errors and bit-misaligned HDLC frames. The calls that fail at 6 dB and
9 dB fail in the V.42 setup because of those errors. Whether a call completes
the setup depends on the location of the errors, and each timing change moves
them. Thus these failures are the upstream error bursts. They are not a new
effect of `INT0_TOUT`.

Two of the failures were on the side of D-Modem. From 8.5 to 10 dB, a burst
hit the E of the Courier after its renegotiation MP'. D-Modem missed E and
dropped the call 5 s later. Now D-Modem accepts E with up to 3 bits in error.
With `INT0_TOUT` and a step of 256, the calls at 8.5, 9, 9.5 and 10 dB hold to
hangup (92 to 98 lines). At 6 dB, D-Modem detects V.42, but no XID frame gets
through the upstream errors in 18 s. Then the Courier stops (its
renegotiation MP asks for downstream index 0, and it hangs up).

## The upstream error bursts come from the DSP's own output

Black-box measurements of one 0 dB call (Courier upstream at 24000 bit/s):

- The decisions of D-Modem, logged for each symbol: about 25 bursts each
  second, with a median length of 17 symbols, and the error is equal in each
  direction. Outside them, the error is 0.075 of the point spacing (clean).
  The bursts do not align with the 20 ms frames of the line.
- The raw DAC words of the Courier, recorded at 9,600 Hz in `codec_frame`,
  agree with what D-Modem receives to 31 dB after a fitted filter. Thus the
  line path (resampler, gain, mu-law) adds almost nothing. The bursts are
  already in the DAC stream.
- When we fit the DAC stream from the decided symbols, the same 5-sample click
  stays at each burst: about -6300, +5200, -10600, +5700, -7900 (DAC units,
  after the -6 dB output gain of the AC01). It has either sign (50 one way, 43
  the other) and a correlation of 0.87 with the template. At its centre, the
  DAC word is near -16,384. That is, the 16-bit word of the DSP is near full
  scale.
- Only 7% of the energy of a click is in 300-3600 Hz. Most is at DC and above
  3.6 kHz. A 300-3500 Hz channel band-pass on the upstream does not help,
  because it also cuts the 3200-baud high carrier.
- These are not the cause: accumulator overflow (none in data; refer to the
  section below), the interrupts of the DSP (the same XINT and TINT pattern
  around clicks as in other locations), AC01 phase-shift requests (6 in the
  full call), DSP speed (0.9x to 1.25x gives the same error), and missed DAC
  samples (none).

A fixed click of either sign, near full scale, is what one intermediate sample
would give after the last filter of the transmitter, if that sample saturated
to plus or minus full scale. Earlier analysis found the bursts mostly in the
quieter frames. That agrees with a normalisation or a division that becomes
very large for small energies. Thus examine the divide step (`SUBC`), `NORM`
and the shift and product modes of the emulator. To compare them with
SPRU056D in unit tests, no firmware is necessary.

### The arithmetic matches SPRU056D

`tests/test_c5x_arith_fuzz.py` compares 50 ALU, shift, store and multiply
instructions of the core (ADD, SUB, SUBC, NORM, the shifts, SACH/SACL, MPY,
MAC-style product accumulation and the PM shifts, and others) with a reference
model. We wrote the model from the Execution and Status Bits sections of
SPRU056D. Each instruction has 150 random cases, with random SXM, OVM, C and
PM, and edge operands. All agree, for ACC, ACCB, PREG, OV, C and TC. We also
read these items against the specification and found them consistent:
indirect and circular addressing, the 11 interrupt shadow registers, the
one-cycle-early condition of XC, RPT and RPTB, and the PLU and BIT
instructions.

One item is different from the wording of the specification: SPRU056D says
that a BCND or BCNDD on OV/NOV clears OV, but the core clears it only when the
branch is taken. With a switch that clears it in the two cases, an x2 call was
identical. A counter found no BCND on OV/NOV in a call. Thus it is not the
cause. The AC01 saw 22 control frames in a full call. Thus those are also not
the cause.

Thus the click is not in the plain arithmetic.

### Register write latencies

SPRU056D Table 7-10 gives 15 registers whose memory-mapped writes (SAMM,
SPLK, LMMR and similar instructions) occur one or two instruction words late.
The core applies all of them immediately. `COURIER_C5X_MMR_LATENCY` (off by
default) models them: `1` for all, or a list of hex offsets such as `0d,0e`.
A write occurs after that number of words, immediately on a branch, and
before the CPU takes an interrupt.

With TREG1/TREG2, the ARs, ARCR, BMAR, the circular buffer registers, PMST,
GREG and the wait-state registers, the x2 call is bit-for-bit the same as
without the latency. Thus the firmware never uses one of them during its
latency. With INDX, the Courier never trains. Thus the firmware needs an INDX
write to have an immediate effect, and this is what the core does. None of
them is the click. The DXR of the serial port and the AC01 path also agree
with the descriptions of the specification and the datasheet.

### The click is there against the emulated I-modem too

We did the same check against the own server of USR: the emulated Courier
calls the emulated I-modem (`tools/probe_imodem_analog_pair.py`, the 53333
setup in `docs/imodem-analog-x2-20261003.md`; it connected at 48000/x2). We
recorded the DAC words of the Courier at its codec. The click has most of its
energy above 3.9 kHz, where the upstream of the Courier has little energy.
Thus a detector on the 4.1 kHz high-passed DAC stream (6-sample power more
than 10,000 times its median) finds it. On the fitted D-Modem call, it found
116 of the 132 clicks that the fit found, with 4 extra events.

| Call | Clicks a second in data | Same shape (correlation over 0.8) | Signs |
|---|---|---|---|
| Courier to D-Modem | about 28 | 98% | 1169 + / 1172 - |
| Courier to I-modem | about 32 | 98% | 1353 + / 1369 - |

In the two calls, they start with the data. Thus the Courier sends them
independently of the device at the other end: the emulated Courier makes them.
They are not caused by an action of D-Modem. The errors of the I-modem on the
frames of the Courier in the earlier pair runs agree with this.

### No overflow lines up with the clicks

One call logged these events against the DAC sample count, with the DAC
words recorded in the same call:

- each ALU overflow (ADD/SUB and all instructions built on them, with and
  without OVM);
- each PREG shift by PM 1 or 4 that lost bits;
- each SACH or SACL with a shift that lost bits.

The results:

- The ALU overflows (74,625) and the PREG shift losses (60,638) all occur in
  the first 20 s, in training. None occurs in data, where the 1,586 clicks of
  30 to 85 s are.
- Shifted SACH stores lose bits 1.5 times for each DAC sample during all of
  the data, at exactly the same rate around a click as in other locations.

Thus the click is not an overflow or saturation in the ALU, the product
shifter or the store shifter. The firmware calculates the near-full-scale
sample without overflow, from inputs that are already incorrect.

## What is still open

- The upstream clicks: which emulated instruction makes the saturated sample
  (refer to the sections above). D-Modem asks for no precoding in x2, and its
  non-linear decoding and trellis settings are not the cause.

- The delivery still waits for the next service step (256 instructions at
  best). The real CPU takes a latched request at the next instruction
  boundary after IRET, EOI or STI.
- The error bursts on the send side of the Courier. They can have a similar
  cause on the transmit banks.

## Other test settings on this branch

These settings are only for experiments. All are off by default:

- `COURIER_TIMER_POLL`: the timer poll stride (default 1024).
- `COURIER_TOUT_LOG=<file>`: adds the pulse count of the DSP timer to the
  file one time in each 200,000 instructions.
- `COURIER_CPI`: the cycles for each instruction of the 186 boards (default
  5.93).
- `COURIER_BEARER_ALAW`: an A-law line.
- `COURIER_BEARER_DOWN_LOSS_DB`, `COURIER_BEARER_UP_LOSS_DB`,
  `COURIER_BEARER_DOWN_NOISE`, `COURIER_BEARER_UP_NOISE` and
  `COURIER_BEARER_SEED`: line loss and noise in each direction. The
  closed-loop probe also applies these.
- `COURIER_EXTRA_ARGS`: more arguments for the Courier command of the
  closed-loop probe.
