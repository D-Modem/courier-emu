# x2 byte loss at 54666 bit/s: frame interrupt timing

In emulated x2 calls against D-Modem, the Courier loses whole bytes from
frames it receives at the high x2 rates. At 32000 bit/s it loses none. This
note gives the evidence that the cause is how the emulator times INT0 (the
coprocessor frame edge), and describes two partial fixes that are on this branch,
both switched off by default.

All of this is black-box work: captures of the emulator's own ports and of the
line, with no change to the firmware.

## What is lost, and where

- Each frame D-Modem sends was decoded back from the line recording
  (`engine-tx.g711`) and checked with its FCS. Every frame leaves D-Modem
  intact.
- The DSP's receive path hands data to the CPU through 6 banks on CPU ports
  0x40–0x56 (a hi byte of 0 means a data byte; ff00 means idle). Capturing
  every CPU read of those ports (`COURIER_LANE_CAPTURE`) and pairing each hi
  port with its lo port gives the byte stream the CPU sees.
- Aligning the two streams shows 1–4-byte deletions, roughly one every 30
  bytes at 54666 bit/s. There are no bit errors and no inserted bytes.
- A log of every DSP write to the banks (0x58–0x5d) found 475,316 writes, all
  acknowledged by the CPU before the next write. So no bank is overwritten:
  the bytes are lost inside the DSP before they reach the banks.

## Why: INT0 is only delivered on timer polls

- The CPU services the banks from its INT0 handler. The live board measured
  INT0 at 2401 Hz, which is about 1416 CPU instructions per frame
  (`FRAME_INSTRUCTIONS`).
- The emulator only checks for a due INT0 at a timer poll, every
  `TIMER_POLL_INSTRUCTIONS` (1024). This is true of both the Python
  `fast_service_rest` and the native worker (`courier_worker_poll` in
  `native/c5x_capi.cpp`).
- So edges arrive up to 1023 instructions late, and two edges can collapse
  into one. In the baseline capture the gaps between bank services fall on
  multiples of 1024 instructions: 896, 1920, 2944 and 3968 (128-wide bins).
  Roughly a third are 2 frames or longer.
- The deletions follow those long gaps. The median gap before a deleted byte
  is about 2800 instructions (2 frames or more), against a median of 50
  between bytes overall.
- At 54666 bit/s the DSP has about 2.8 bytes for each frame. When a frame's
  service is missed, its small internal queue overflows and bytes are dropped.
  At 32000 bit/s there is enough slack.

## The fix on this branch

`COURIER_INT0_EXACT=1` delivers INT0 at the first service step at which it is
due, not only at a timer poll:

- `courier_emu/machine.py`: a branch in `fast_service_rest` that dispatches
  INT0 when it is due (IF set, vector installed, not already in service). It
  uses the same catch-up rule as the timer poll path.
- `native/c5x_capi.cpp`: the same in the native worker. The frame edge
  bookkeeping no longer sits only under the timer poll branch.
- `COURIER_NATIVE_SERVICE=<n>` sets the native service step. The default stays
  at `TIMER_POLL_INSTRUCTIONS`. The fix only works with a shorter step, because
  the worker runs once per step. 256 works. 128 makes the Courier clear down.

Both settings are off by default, and the default paths behave as before. The
native, bearer and interpreter tests give the same result with and without the
change (55 passed, 1 failed; that failure is in
`test_rom_console_polls_and_closes_without_global_hook` and fails on a clean
`main` too).

## Results

Calls against D-Modem (`tools/probe_v90modem_closed_loop.py analog`,
`AT+MS=X2`), sending text lines. "Whole" counts the FCS-good frames from
D-Modem that reached the CPU without loss.

| Call | Line loss | Rates | Frames whole | Lines through | End |
|---|---|---|---|---|---|
| Baseline | 0 dB | 54666 | 166 / 306 (54%) | 30 | Courier cleared down at 94 s |
| `INT0_EXACT` only | 0 dB | 54666 | same as baseline | 30 | same as baseline |
| `INT0_EXACT`, service 256 | 0 dB | 54666 | 334 / 560 (60%) | 35 | held to hangup |
| Baseline | 6 dB | 52000, 53333, 54666 | 258 / 460 (56%) at 54666 | 29 | held |
| `INT0_EXACT`, service 256 | 6 dB | 52000, 53333, 54666 | 169 / 244 (69%) at 54666; 14 / 17 at 53333 | 78 | held |
| `INT0_EXACT`, service 128 | 0 dB | 54666 | — | — | Courier cleared down at 57 s |

With the fix, the service gaps cluster near one frame (1152 and 1408 bins)
instead of on the 1024 grid. About a quarter are still 2 frames long (the 2688
bin), and the bytes that are still lost follow those gaps.

## The frame edge's source: the DSP's timer

The CPU-side counter above is a stand-in. On the hardware, the edge has a
source:

- `docs/asic-pinout.md` traces DSP pin 122, `TOUT` (the C5x on-chip timer
  output), back into the ASIC, the part that drives the CPU's interrupt lines.
- The ISDN machine in this repository already raises its frame interrupt
  (IRQ13) from `timer_expiries()`, one edge per TOUT pulse. The Quad routes its
  C50's timer to its INT0 the same way.
- Sampling the emulated C52's timer during an x2 call (`COURIER_TOUT_LOG`)
  gives 3,526 pulses per 5,000,000 harness instructions all through the call.
  At the 20.16 MHz board's 3,399,663 instructions a second that is 2,397 Hz.
  8,400 CLKOUT cycles at 20.16 MHz is exactly 2,400 Hz. The live board's INT0
  was counted at 2,401 Hz.

So INT0 is very likely TOUT. `COURIER_INT0_TOUT=1` models it that way:

- Each new TOUT pulse latches one request, as the 80186's edge-triggered
  request bit does. It is latched whether or not IF is set or INT0 is in
  service, and a second pulse before it is taken merges with the first.
- The request is taken at the first service step where IF is set and INT0 is
  not in service. This happens in the Python paths
  (`Machine._int0_frame_due` / `_int0_frame_taken`) and in the native worker,
  which gains `int0_tout`, `tout_seen` and `int0_request` fields.
- Without the setting, the edge free-runs on the instruction count as before.

The old model also lost edges in a way the hardware does not: it only latched
an edge while IF was set, and the catch-up rule then threw the debt away.

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

At 0 dB and a step of 256, 207 of 290 frames arrived whole. Fewer frames were
sent than in the baseline because fewer had to be resent. A step of 128 now
works, where with the counter it made the Courier clear down.

### A second effect: the Courier's own transmitter

The losses at 6 dB and 9 dB are not on the downstream side. D-Modem's
receiver reports the Courier's upstream V.34 signal quality as its
equalizer's MSE at the start of data:

| Run | Upstream MSE |
|---|---|
| Baseline, 0 dB and 6 dB | 0.025 |
| `INT0_TOUT`, step 512 | 0.025 |
| `INT0_EXACT` or `INT0_TOUT`, steps 128–1024 | 0.11–0.14 |

The MSE is already high during training, before any user data flows. So the
more frame edges the CPU actually takes, the worse the Courier's transmitted
signal is. The baseline takes about two thirds of them. That is most likely a
second timing fault, between the DSP and its codec or the line resampler,
which a full-rate INT0 exposes. It is probably also the cause of the error
bursts seen upstream. With 6 dB of loss the worse signal no longer trains.

## What is still open

- Why a full-rate INT0 degrades the Courier's upstream signal. Next to check:
  whether the codec and line timing are clocked from CPU instructions rather
  than DSP cycles (`DspBridge.clock_x86_fast`, `codec_instructions`), and
  whether the DSP's cycle debt moves with each CPU access to its ports.

- Delivery still waits for the next service step (256 instructions at best).
  The real CPU takes a latched request at the next instruction boundary after
  IRET, EOI or STI.
- The error bursts on the Courier's sending side, which may have a similar
  cause on the transmit banks.

## Other test settings on this branch

These are only for experiments and are all off by default:

- `COURIER_TIMER_POLL`: the timer poll stride (default 1024).
- `COURIER_TOUT_LOG=<file>`: appends the DSP timer's pulse count every
  200,000 instructions.
- `COURIER_CPI`: the 186 boards' cycles per instruction (default 5.93).
- `COURIER_BEARER_ALAW`: an A-law line.
- `COURIER_BEARER_DOWN_LOSS_DB`, `COURIER_BEARER_UP_LOSS_DB`,
  `COURIER_BEARER_DOWN_NOISE`, `COURIER_BEARER_UP_NOISE` and
  `COURIER_BEARER_SEED`: line loss and noise in each direction. These are also
  applied in the closed-loop probe.
- `COURIER_EXTRA_ARGS`: extra arguments for the closed-loop probe's Courier
  command.
