# Analog DTE UART starvation fixed; large-record V.34 passes

## Qualified result

The local I-modem / analog 403 pair now passes the unchanged bidirectional
**512-byte ASCII payload** traffic gate:

- Two fresh **20-second fixed-14400 V.34/LAPM** calls.
- One **20-second automatic-rate V.34/LAPM** call (21600).
- One **60-second fixed-14400 V.34/LAPM** call.

All four retain active carrier at the measured boundary, deliver matching
complete records and partial prefixes, and show zero observed RX/TX UART
overruns, terminal drops, connected PCM underruns, pending receive-error writes,
BLERs, retransmissions, or link timeouts. No five-second record gap occurs.
A separate offline verifier reproduces the record hashes and gate outcomes
from the saved captures.

**This fixes the zero-BLER UART starvation case, not x2.** A fresh x2 control
still fails with bad-CRC receive errors and no complete upstream record. It is
not silently downgraded to V.34 or described as passing. No live RasFinder,
Apple USB, arbitrary-binary, maximum-throughput, or V.90 qualification is made.

## Cause

The [earlier controls](imodem-x2-crc-boundary-20261026.md) showed large-record
V.34 gaps despite zero BLERs. Passive online-DTE delivery telemetry now locates
the delay before the analog firmware receives its terminal data.

In `artifacts/imodem-v34-dte-blocked-20261026-215233/`, a character whose wire
frame had already completed waits as long as **2,639,872 supervisor
instructions** while `uart.pending == [21]` (TX). At the identified 3.399663-MIPS
board timebase this is about **0.78 seconds**, instead of the normal sampled
4096-instruction frame duration. Its input FIFO still contains queued bytes.
The call has 27,190 sampled `uart-pending` blocks and eventually delivers only
two upstream records. No CRC errors explain those delays.

The emulator imposed three related UART artifacts:

1. **TX requests gated RX.** `service_after_tick` required the entire UART
   interrupt deque to be empty before beginning/completing a DTE character.
   A pending TX interrupt therefore held up an unrelated incoming character.
2. **Serial requests were serviced FIFO.** TX could remain ahead of RX even
   though the EB assigns RX higher relative priority within the serial source.
3. **Every TX write completed synchronously.** The model always reported TXE
   and immediately requested another TX interrupt. Real firmware's two-byte
   transmit ISR therefore ran against an unlimited, zero-time transmitter.

The Intel **270830-003** manual supplied in `docs/` supports the correction:

- §8.1.1.2, page 8-3: serial RX/TX share a priority, with RX higher within it.
- §10.1.1.2, page 10-4: the transmitter is double buffered; TI sets at the
  beginning of the stop bit, not at the buffer write.
- §10.2.1, Figure 10-12: with internal clocking in asynchronous mode 1,
  `baud = Fcpu / (8 * (BxCMP + 1))`.

The observed `B0CMP=8015` gives 22 CPU clocks per baud tick. The emulator
converts nine bits to the stop-bit interrupt deadline and ten bits to the end
of an 8N1 frame using the identified board's cycles per instruction.

## Changes retained

### `courier_emu/uart.py`

- `receive_available` tests only RX holding/request capacity, independently of
  TX requests. Existing harness RX backpressure remains; there is no unbounded
  new receive FIFO and no hidden dropping of bytes.
- `take_interrupt()` chooses RX before a pending TX request.
- ROM runs enable a two-slot, internally clocked asynchronous-mode-1 transmitter.
  `advance()` schedules TI at the stop bit, moves the buffered byte into the
  shifter at frame end, coalesces pending requests and maintains TXE accordingly.
- Writes beyond the two-slot capacity increment `transmit_overruns`; qualified
  calls have zero. The probe rejects such overruns.
- `DteInputTiming` retains bounded first/recent deliveries, largest gaps, and
  blocked-delivery causes separately from boot logs that can already be full.

The console still captures bytes when firmware writes S0TBUF, rather than
serializing host output bit by bit. This is a completion/interrupt model, not a
complete UART wire encoder. External clocking and other serial modes retain the
legacy synchronous path. Standalone `EbSerial()` also retains that legacy mode
unless timed transmit is explicitly enabled; `CourierMachine` enables it for
its integrated UART.

### `courier_emu/machine.py`

- Uses RX capacity, rather than an empty combined RX/TX request deque, to admit
  DTE input. The original command-mode attention-adapter guards remain.
- Online reception can latch a request while CPU IF is clear; this does not
  immediately dispatch the interrupt while IF is clear.
- Advances TX timing at device accesses and periodic service. Busy transmitters
  cannot enter a native fast path that skips the needed UART service.
- Uses RX-before-TX request selection without changing the broader interrupt
  controller's existing arbitration.
- Reports bounded `dte_input_timing` and the new TX busy/overrun counters.

No original supervisor/DSP instruction, payload, CRC, ACK, CONNECT text, buffer
acceptance threshold, or timer calibration is patched to produce the result.

## Final evidence

Counts below are **complete records during the requested window**, not the
slightly larger final-drain counts. Each record has a 512-byte payload and
19-byte marker/sequence/terminator. Directions are analog to I-modem (upstream)
and I-modem to analog (downstream).

| Directory under `artifacts/` | Mode / seconds | Upstream records | Downstream records | Largest upstream/downstream record gap |
| --- | --- | ---: | ---: | --- |
| `imodem-v34-timed-rx-priority-20261026-222415` | 14400 / 20 | 14 | 12 | 1.5 / 1.7 s |
| `imodem-v34-uart-fixed-repeat-20261026-222730` | 14400 / 20 | 13 | 12 | 1.6 / 1.7 s |
| `imodem-v34-uart-fixed-auto-20261026-222843` | 21600 / 20 | 13 | 12 | 1.5 / 1.7 s |
| `imodem-v34-uart-fixed-60s-20261026-223152` | 14400 / 60 | 40 | 39 | 1.7 / 1.8 s |

The 60-second call's bounded drain completes **41 upstream and 40 downstream
records**, with no trailing partial record. Measured payload throughput is
341.3 upstream / 332.8 downstream bytes/s; this one-outstanding-record test and
its conservative DTE adapter do not measure maximum line throughput.

The new x2 control, `imodem-x2-uart-fixed-20261026-222952`, still fails: nine
complete downstream records, no complete upstream record, 173 verified upstream
prefix bytes at final drain, and final BLER count 247. Its UART overrun counters
remain zero. The receive-bit/deframing investigation is still required.

Private `.artifact-archives/imodem-dte-fix-20261026/` contains the bounded
control runner, independent `verify.py`, successful `verification.json`, and
regression reports. Verification recomputes all measured complete records and
prefixes from raw DTE captures, checks their hashes, re-runs unchanged window
and drain checks, and separately checks health including both RX and TX UART
overruns. It preserves the x2 failure.

## Reproduction

Requires the same original firmware, mask ROM and saved I-modem profile as the
earlier local probes. No network calls or credentials are involved.

```sh
COURIER_LINE_FRAME_MS=20 PYTHONPATH=. .venv/bin/python tools/probe_imodem_analog_pair.py \
  --wallclock --traffic-seconds 20 --traffic-size 512 --link-diagnostics \
  --protocol v34 --speed-index 8 --trace-link-errors \
  --analog-settings 'S27=1S54=0&A3&B1Q0&K0' \
  --imodem-settings 'S54=0&A3&B1Q0&K0' \
  --imodem-nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --instructions 1500000000 --analog-instructions 750000000 \
  --output /tmp/imodem-v34-uart-fixed
```

Select `--traffic-seconds 60` for the sustained control, or `--speed-index 0`
for automatic V.34 rate. The acceptance threshold remains five seconds and
at least ten complete records in each measured window. Run sequentially with
host headroom. The observed 60-second call takes 113.93 host seconds including
training and post-window diagnostics.

## Rejected experiments and scope

The earlier RX-only change removed the huge false TX gate, but the 20-second
window still completed only nine upstream records, failing the unchanged
minimum-ten requirement. It was not reported passing.

Removing all RX backpressure to overlap characters produced real reported UART
overruns and corrupt payload. That change was reverted. Broader INT0 mask,
priority and nesting experiments also introduced V.34 errors and were reverted;
`courier_emu/timers.py` has no changes from this investigation. The retained
serial-source RX-before-TX order is not a claim that the whole interrupt
controller is now cycle-accurate.

The PC-hook pilot `imodem-v34-dte-service-trace-20261026-214354` slowed the
supervisor enough to hit its owned 160-second wall bound before CONNECT; it is
excluded. Passive telemetry was used for the diagnosis instead. Other
exploratory controls under `artifacts/imodem-v34-*` are not qualified evidence
unless listed in the final table above.

## Regression status

**211 focused tests pass**, covering integrated-UART status, baud timing,
stop-bit TI, double buffering, RX/TX ordering, overrun reporting, bounded DTE
telemetry, native machine/port models, replay of the qualified large-record
captures, and the I-modem media/traffic/runtime selection. `git diff --check`
is clean. In addition, `tools/verify_rom_uart_status.py` executes both original
302 and 403 resident ROMs for 60 million instructions each: all 20 queued
command bytes are consumed, the expected IDs and four OK replies match, and
neither UART overruns. Fresh evidence is under
`artifacts/rom-uart-status-timed-tx-20261026/`.

A full-suite attempt was stopped by the enclosing command's time budget after
about 186 seconds of tests (30 progress dots, no completed summary). A full
suite pass is **not** claimed. No owned pytest, probe, or worker process remained
at the subsequent check.
