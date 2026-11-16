# DSP training audit, 2026-10-02

V.32/V.32bis and V.34 still do not establish native carrier in the
I-modem/analogue-Courier pair. The CPU corrections below are verified defects.
But we did not show that either of them causes the connection failure.

## Corrected CPU behavior

These corrections are against the `spru056d-c5x-users-guide.pdf` of the repository:

- `DMOV` and `LTD` now limit their copy of the delay line to on-chip data RAM.
  They still read external memory and memory-mapped registers. `LTD`
  still does its multiply-accumulate and its TREG loads. They do not now
  make an extra write to the next external word (6-104 and 6-142).
- A taken `BANZD`, `BCNDD`, `CALAD`, `CALLD`, and `RETCD` now costs two cycles
  for the transfer itself, plus the costs of the delay slots, which execute separately.
  Before, they cost four plus the slots (6-56, 6-60, 6-82, 6-86, 6-205).
- Long-immediate `LACC`, `OR`, and `XOR` now cost two cycles, not one.

The serial diagnostic includes `delay_move_ignored`, `delay_move_last_pc`,
and `delay_move_last_address`. A reset of the DSP resets them. The two ends report zero
ignored moves in the corrected V.32bis and V.34 pair runs. Thus, those runs do not exercise the
external-write defect.

## Verification

The regression selection of C5x, I-modem, bridge audio-rate, and resampler tests passes
117 tests. These include the new cases for the instruction costs and the delay line:

```sh
.venv/bin/python -m pytest -q tests/test_c5x*.py tests/test_imodem*.py \
  tests/test_bridge_audio_rates.py tests/test_resample_rate_changes.py
```

The Bell 103 control keeps CONNECT and the delivery of the two different payloads:
[summary](../artifacts/imodem-analog-pair-bell103-cpu-audit-20261002/summary.json).

The corrected V.34 run gets to image 6. It reports symbol-rate index 5 at
7.8246 seconds and `0006:0000` at 15.8402 seconds. Then it repeats the
symbol-rate/retrain sequence. Neither DTE reports CONNECT:
[summary](../artifacts/imodem-analog-pair-v34-cycle-fix-20261002/summary.json).

The V.32bis control sets `&N8` (14400), disables V.34/V.FC with `S56=192`,
and disables PCM with `S58=33`. It gets to repeated `0020:0004` reports,
followed by `0006:0000` and `0038:0000`. Neither DTE reports CONNECT:
[summary](../artifacts/imodem-analog-pair-v32-cycle-fix-20261002/summary.json).

A separate plain V.32 control sets `&N6` (9600). It also disables V.8
with `S54=192`, and it selects `&M0&B0` on the two ends. The two ends return NO CARRIER:
[summary](../artifacts/imodem-analog-pair-v32-no-v8-20261002/summary.json).
The file name `v32` on the 14400-bps controls identifies the family. Those
specific runs are V.32bis controls. They are not a verification of the plain V.32 carrier.

## Further native tracing

In the V.34 image, `9316..931b` increments data `0337` and puts report tag
6 in the queue through the original sender at `85f5`. The
[retrain-producer trace](../artifacts/imodem-analog-pair-v34-retrain-caller-20261002/result.json)
shows that this code executes. Do not interpret tag 6 here as CONNECT.

The
[condition trace](../artifacts/imodem-analog-pair-v34-retrain-condition-20261002/result.json)
captures the counter comparison at `96be..96c6` and the writes to data `031a`.
This routine compares the counter with `bb80`. Then it returns, or it
pops the return address of its caller and advances it by two words. This is the native
control flow of the firmware. It is not a carrier indication that the supervisor injected. To
name the complete failed training transition, it is still necessary to trace the receive
state changes and the path into `92e2`/`9316`.

The byte-exact overlay transfer and the kept Bell 103 payload path do not
prove the remaining DSP arithmetic, the training waveforms, or the phase transitions.

## Live overlay publication audit

`tools/probe_imodem_analog_pair.py --audit-overlays` now captures each two-word
holding-register commit of the CPU. It reads the installed program words immediately
before the final completion strobe. At that boundary, the supervisor has already polled the two
half-block acknowledgements. This is an observer. It does not
install code, and it does not change DSP registers or acknowledgements.

The V.34 run of 230M instructions verifies these I-modem transfers:

| Image | Destination | Transferred words | Mismatches |
|---|---|---:|---:|
| 10 | `d100` | 7536 | 0 |
| 11 | `9260` | 16000 | 0 |
| 6 | `a000` | 13912 | 0 |

The supervisor rounds images 11 and 6 up by three words. The transferred
bytes, with those extra words, agree with the related flash source
spans in `Ie030002.nac`. The DSP destination advances by exactly the
transferred length. PA7 is `0002` at all three boundaries, and the two pending
half-block bits are clear. The DSP PC is in the resident loader `82b1..82b7`.
The analogue side independently verifies 20,096 words across its images 6
and 8, at `9d00` and `dc00`, with no unreadable words.

The plain V.32 control verifies seven I-modem transfers: startup images
10/11, image 8 at `9260`, then two startup reload pairs. All of them have zero
program mismatches, an exact advance of the destination, clear pending bits, and
agreement with the flash source. The analogue side requests no overlay in this control.
Neither protocol establishes carrier.

Evidence:

- [V.34 boundary checks](../artifacts/imodem-analog-pair-overlay-audit-20261002/overlay-verification.json)
- [V.32 boundary checks](../artifacts/imodem-analog-pair-v32-overlay-audit-20261002/overlay-verification.json)
- [V.34 native write trace](../artifacts/imodem-analog-pair-overlay-write-audit-20261002/result.json)

The final V.34 program dump is different from image 6 in 2,133 words, which start
at `ce00`. The resident image 5 stays identical. The trace identifies the writer of the first
address as the native `BLDD` at `b4ea` (reported PC `b4eb`, its
immediate word). At `b4e2`, the firmware explicitly loads AR0 with `ce00`,
adds that base to a circular-buffer index, and copies a sample from data
`04b6` into that buffer. The observed values at `ce00` are `2000`/`e000`
(+8192/-8192). No PC events occur in `cdfe..ce10` during the traced run.
This explains the first changed address as the use of a buffer by the firmware. It does
not show that each later write or each training phase is safe.

To do the V.34 boundary and write audit again:

```sh
.venv/bin/python -m tools.probe_imodem_analog_pair --protocol v34 \
  --instructions 230000000 --audit-overlays --dsp-data-trace ce00 \
  --dsp-trace-range cdfe:ce10 --output artifacts/overlay-audit-new
```

The focused probe and the overlay-handshake tests pass 11 cases. These include
an observer check that finds a corrupted word and does not repair it.

## Remove the foreground host bypass

At first, the transfer checks above ran with a hidden command-2
acknowledgement on the host side. That was a patch of the RAM/status of the guest. It was not a physical ASIC
handshake. `ImodemDsp` now uses `foreground_overlay_assist=False` by default.
The pair probe gives the old bypass only through `--assist-overlay-command`.
The host publishes the incoming command ports and a pending bit. The native firmware
must consume the command, update its destination and acknowledge it.

The current core without the assist still completes all three V.34 transfers with
zero program mismatches. It gets to the symbol-rate selection, and later it retrains.
Its endpoint records zero host assists. Thus, the older bypass is not
necessary with the current core. No bisection has yet related that difference
to a specific CPU correction between the two versions.

The Bell 103 control without the assist connects and sends the two payloads:
[summary](../artifacts/imodem-analog-pair-bell103-unassisted-20261002/summary.json).
The longer V.34 evidence without the assist is
[here](../artifacts/imodem-analog-pair-v34-unassisted-training-20261002/result.json).
The acquisition/training failure continues after we removed this host patch.

## Sustained scrambled-sounding training section

The finer checkpoints put the sustained output in the native transmit state
`b391`, with the sequence pointer `b2d9`, from line frame 338 through 378.
The short transmit countdown goes through the values 0..7 in a cycle. At the same time, data `031a`
counts down from 14565 through 11137, 7708, 4279 and 850 at one-second
intervals. At frame 388, the transmit state has changed to `9e49`, the
sequence pointer has changed to `9e10`, and the retrain count `0337` has increased to one.
This is a live training state with counters that change. The DSP has not stopped.

The native PC trace executes `b391..b3ce` again and again. Its call at `b3ca`
goes to the original scrambler `9053`. The data trace records 4096 writes of the kept
scrambler state at `03d8`, from the instructions `9069` and `9071`, with
511 different values. The captured five-second waveform has 50 different
100 ms blocks and 178 different mu-law codewords. Thus, the sustained sound does not come from a held final
sample or from repeated 100 ms socket audio.

Evidence:

- [State/counter checkpoints](../artifacts/imodem-analog-pair-v34-sustained-training-20261002/sustained-state.json)
- [Native scrambler execution and state writes](../artifacts/imodem-analog-pair-v34-scrambler-progress-20261002/result.json)

The generator identifies this as sequence J. `b391` extracts two-bit groups
from `@49`, scrambles them through `9053`, and encodes them differentially
through `b533`. The word is `89b0`. (It is not `8990`: the receivers compare with bit 5 masked,
and `8990` came from this.) Its representation with the least significant bit first is
`0000110110010001`, the **16-point** J pattern in ITU-T V.34 Table 18. The four-point pattern is
`0000100110010001`, `8990`. Refer to `docs/x2-v90-protocol-selection.md` (J bit 5).
Section 11.3.1.2.4 says that the answering modem sends J while it waits for the
S of the caller and the S-to-S-bar transition.

## What the sustained state is waiting for

The receive callback stays at `a0f9`. Its qualification helper `a194` checks
the signed timeout at `031a`, the holdoff at `032c`, and a threshold on
`03d0:03d2`. Then it requires that the signed `03b4` is negative. The holdoff is zero
and the threshold passes, but the final metric stays nonnegative. In the
last kept trace, it is +2. The next expired timeout is -19. It takes
the native `92a9` recovery path, and at the end it reports retrain.

Thus, the answering modem waits for the training response of the caller
to qualify. We call that response S because of the J generator and the
sequence of the standard. More tracing is necessary to find the precise signal-processing meaning
of the native metric. In the capture with the clock correction, the received PCM of the answering
modem is fully zero from 6.985375 through 13.505750 seconds.
Those samples agree with the recorded transmit silence of the analogue Courier. Thus,
the captured transport did not discard a response during that interval.
It is still not known why the calling Courier does not recognize/respond to J.

Evidence:

- [Receive qualification and timeout trace](../artifacts/imodem-analog-pair-v34-receive-wait-20261002/result.json)
- [ITU-T V.34 (1996), Table 18 and section 11.3.1.2.4](https://www.itu.int/rec/dologin_pub.asp?id=T-REC-V.34-199610-S!!PDF-E&lang=e&type=items)
