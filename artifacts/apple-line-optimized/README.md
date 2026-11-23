# Apple line on the optimized 403 worker

**Passing live hardware run**, no digits dialed:

- Original captured 403 firmware (`courier-board-21210-capture-403/courier-board.rom`).
- Same board/settings/scheduling as the optimized paired benchmark:
  `idsdl403`, board 7, default DIP, 5 ms tick, default tick source,
  256-instruction DSP batch, terminal input scheduled after 5M instructions.
- Firmware command `ATH1` returns `OK` and physically seizes the attached line.
- 1600 hardware exchanges, **329,529 PCM samples** in each direction at 10286 Hz
  (32.04 s total PCM, including on-hook startup).
- **22.619 s off-hook PCM**, **zero active output gaps**, **zero input overflow**.
- Native host lane I/O active; **48,074 native worker polls** executed.
- 114,308,095 supervisor instructions; 33.18 s wall including startup/cleanup.
- Helper shutdown readback verifies on-hook. Independent `final-line-status.json`
  confirms register 5 = 8 (monitor enabled, hook bit clear), line status = 64.

`verification.json` contains the exact worker command, timing and counters.
`403-hold-30s.json` is the full run report; `.log` captures hardware diagnostics.
The filename denotes the approximate total PCM budget, **not** 30 seconds
exclusively off-hook. `403-hold.json`/`.log` are the shorter initial success.

## What changed

The physical backend keeps audio-only semantics (no synthesized training,
carrier, call engine or dial tone), but no longer inherits the blanket exclusion
of audio-only socket links from native DSP polling. The poll may advance the DSP
between physical codec batches, then must yield to Python for real hardware
I/O. It is explicitly barred from the existing native 8 kHz socket resampler.
Hook/IRQ/mailbox/hybrid guards are retained. CPU fast-path exclusions specific
to the different B/C supervisor were not relaxed.

The Apple CLI also no longer replaces the optimized scheduling defaults with a
4096-instruction batch and DSP tick source. The previous 403 attempt additionally
used the older `idsdl302` settings fixture. That was not a valid run of the
optimized 403 configuration.

## Reproduce

See [backend instructions](../../docs/apple-usb-line.md). Build the helper, then:

```sh
./courier run dumps/courier-board-21210-capture-403/courier-board.rom \
  --apple-modem --nvram-fixture idsdl403 --board-id 7 --tick-ms 5 \
  --at ATH1 --serial-input-after 5000000 \
  --instructions 180000000 --line-frames 1600 --summary
```

This seizes a powered FXS/PBX line; it does not dial. Hardware input paces the
worker, so this run should take real time, not the unpaced benchmark's 4x speed.

`tests/test_apple_native_poll.py` also compares native polling enabled/disabled
against a hardware-free PCM peer. It requires identical emitted PCM SHA-256,
sample counts, hook transitions, CPU instruction boundary/registers, AT output,
supervisor call cells and codec serial state. It verifies a positive native poll
counter in the optimized case and zero when `COURIER_WORKER_POLL=0`.

30 focused Apple/CLI/bridge regressions and 44 native interpreter/port/clock/line
regressions pass. This does **not** establish CONNECT, data transfer, ring
answering, trained-datapump throughput or long-duration clock-drift performance.
The line's off-hook audio contains near-rail samples, so line level calibration
is also still needed before attributing training failures to the firmware.
