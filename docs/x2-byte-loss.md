# x2 byte loss at 54666 bit/s: frame interrupt timing

In emulated x2 calls against D-Modem, the Courier loses whole bytes from
frames it receives at the high x2 rates. At 32000 bit/s it loses none. This
note gives the evidence that the cause is how the emulator times INT0 (the
coprocessor frame edge), and describes a partial fix that is on this branch,
switched off by default.

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

## What is still open

- Why some edges are still missed with the fix. The likely causes are an
  edge that falls due while the previous INT0 is still in service, or while
  IF is clear, and is then only taken after the next service step. The real
  CPU latches the edge and takes it straight after the IRET or STI.
- Why a 128-instruction service step breaks the call, since a correct model
  should not depend on it.
- The error bursts on the Courier's sending side, which may have a similar
  cause on the transmit banks.

## Other test settings on this branch

These are only for experiments and are all off by default:

- `COURIER_TIMER_POLL`: the timer poll stride (default 1024).
- `COURIER_CPI`: the 186 boards' cycles per instruction (default 5.93).
- `COURIER_BEARER_ALAW`: an A-law line.
- `COURIER_BEARER_DOWN_LOSS_DB`, `COURIER_BEARER_UP_LOSS_DB`,
  `COURIER_BEARER_DOWN_NOISE`, `COURIER_BEARER_UP_NOISE` and
  `COURIER_BEARER_SEED`: line loss and noise in each direction. These are also
  applied in the closed-loop probe.
- `COURIER_EXTRA_ARGS`: extra arguments for the closed-loop probe's Courier
  command.
