# Configurable frame cadence

The analog supervisor's periodic INT0 clock now supports a live codec-derived
cadence as well as a fixed-rate override. Both Python service and the native
worker use the same fractional phase model. This does **not** change CPU/DSP
clock ratios, firmware, or bank capacity. Legacy periodic polling remains the
unchanged default; explicit XF profiles have separate recognition controls.

## Selecting a mode

| Selection | Behavior |
|---|---|
| Default / `--frame-codec-samples 0` | Original legacy periodic cadence. |
| `--frame-codec-samples N` with N > 0 | One periodic frame per N live ROM codec samples. |
| `--frame-hz HZ` | Fixed periodic rate; takes precedence over codec-derived timing and XF routing. |
| `--frame-source dsp-xf` | Actual DSP XF falling edges, with per-machine 64-instruction cooperative IRQ service by default. |
| `--frame-source periodic` | Explicit periodic routing, overriding the legacy XF environment switch. |
| Existing `COURIER_ROM_XF_INT0=1` experiment | Compatibility selector for the XF profile; no longer mutates polling constants process-wide. |

For example, add `--frame-codec-samples 3` to a normal analog `run` command.
For the pair probe, use:

```sh
PYTHONPATH=. .venv/bin/python tools/probe_imodem_analog_pair.py \
  <your existing call and traffic options> --analog-frame-codec-samples 3
```

The probe also accepts `--analog-frame-hz HZ` for a fixed-rate control. These
options reach the analog worker directly: no sitecustomize, environment trick,
firmware edit, or monkeypatch is needed.

Python callers can pass `frame_codec_samples=N`, `frame_hz=HZ`, or
`frame_source='dsp-xf'` to `CourierMachine`. N must be a nonnegative integer;
HZ must be positive.

`--interrupt-poll-instructions N` controls ordinary timer/UART recognition on
one machine. `--frame-irq-poll-instructions N` independently bounds XF
recognition (default 64). The pair probe forwards these as
`--analog-interrupt-poll-instructions` and `--analog-frame-irq-poll-instructions`.
Both intervals must be positive integers. Finer recognition is not a higher
DSP edge rate, and may cost substantial host CPU time.

The cooperative XF path remains the default for that opt-in source. Native
worker XF dispatch is implemented and can be explicitly compared with
`COURIER_WORKER_POLL=1`; sustained native qualification is incomplete. It
recognizes edges between ordinary timer polls, preserves IF/EOI and vector/
stack checks, and transfers pending edges and reset epochs across handoffs.

## Live clock and phase

Codec-derived timing applies only to the ROM-backed analog frame clock, after
the codec has a programmed rate, free-run enabled, and an installed line-frame
interrupt. Other runs and unconfigured/reset codecs use the legacy fallback.
An explicit fixed rate is never replaced by a codec retune.

The interval is derived from the actual DSP codec frame period, not a table
of modem CONNECT strings or nominal rates:

```
CPU instructions per frame = N * codec_frame_period_in_DSP_cycles
                            / DSP_cycles_per_CPU_instruction
```

Thus N=3 gives 2400 Hz at a 7200-Hz codec and 3200 Hz at a 9600-Hz codec.
Other codec rates and groupings work by the same calculation. At the 403's
11.86 DSP cycles/instruction, the 9600-Hz interval is about 1062.3946 CPU
instructions, not a rounded 1062 instructions on every frame.

Retunes preserve the normalized elapsed phase rather than restarting the
clock at the current service turn. The fractional interval is retained across
successive entries and across native/Python handoffs. Fixed `--frame-hz`
intervals also retain fractional precision, including board timebase changes.
Default legacy intervals retain their original integer calculation.

Missed frames keep the pre-existing pending/coalescing policy; there is no
queue of old frame interrupts to replay. Interrupt delivery is still gated
by IF, in-service/EOI state, the installed vector, and the existing peripheral
poll interval. A requested 3200-Hz cadence does not guarantee 3200 delivered
interrupts under masking or coarse servicing.

The native worker decides codec-derived frequency after the DSP step, so a
retune during that step is observed before deciding whether to enter INT0.
Its layout-checked shared state retains the same fractional phase as Python.

## Diagnostics

`timebase` in the result includes:

- `frame_cadence`: `legacy`, `fixed`, `codec-derived`, or `dsp-xf`.
- `frame_codec_samples`: configured grouping (0 disables adaptation).
- `frame_instructions`: current periodic interval, possibly fractional.
- `frame_effective_hz`: configured periodic frequency; null for actual XF routing.
- `interrupt_poll_instructions`: ordinary timer/UART recognition granularity.
- `frame_irq_poll_instructions`: configured XF recognition bound, or the
  ordinary polling interval for a periodic source.
- XF counters distinguish observed, delivered, and coalesced edges. Reset
  generation prevents a new epoch with the same edge count being mistaken
  for an already consumed interrupt.

`dsp_bridge.line.native_worker_polls` is reported for ROM-backed line runs too,
so an experimental native selector can be checked against actual native work.

Final diagnostics may show a different codec/cadence after call clear-down;
use the clock timeline for the progression during measured traffic.

## Qualification and limits

Native/Python parity, retunes, configurable grouping, reset/fallback, explicit
fixed overrides, board clocks, coalescing, and accumulated rounding error are
covered by `tests/test_frame_cadence.py`. CLI/probe controls are covered by
`tests/test_frame_cadence_cli.py`.

Initial qualification is retained in
`artifacts/imodem-adaptive-cadence-20261027/`. Codec-derived N=3 with unchanged
1024-instruction polling passed the fixed-14400 V.34 traffic gate, but **failed
the x2 20- and 60-second traffic gates**. It is therefore opt-in, not the default
or an x2 reliability fix. Frequency-only periodic adaptation is distinct from
the previously successful actual-XF experiment; it does not reconstruct the
XF pin's phase or eliminate interrupt-recognition latency.

See [clock-phase controls](imodem-x2-clock-phase-20261027.md) for the underlying
measurements and successful experimental XF qualification runs. Subsequent
failed repetitions and the opt-in coupled virtual clock are documented in
[coupled-clock controls](imodem-x2-coupled-clocks-20261027.md). Neither selectable
frequency nor a single passing call establishes repeatable x2 reliability.
