# Courier and I-modem reported-rate handoff

Date: 5 October 2026. Refer to `../../docs/x2-courier-mp-fields.md` and to x2 technical
specification Draft 0.33, clauses 21 and 22.

- `verification.json`: 46 original DSP threshold cases, 45 original DSP
  report contexts, 150 supervisor mailbox-to-result contexts and 15 original
  I-modem selector contexts. It also has 210 original contexts of the I-modem source-bit consumer.
  Firmware hashes identify the two profiles.
- `live-first-ceiling.json`: the first E2DD invocation in the paired call.
  Metric 4220 becomes 3F20, and this selects index twelve.
- `live-handoff.json`: DSP 031C writes, tag-6A reports and writes to the supervisor rate
  cell. The later disconnect reset is the cause of the final peek of one.
- `live-imodem-selector.json`: the original CFF4 execution in the paired call,
  the working MP cells, index zero and allocation nineteen, with the two terminal
  results.
- `dsp-report.asm`, `supervisor-report.asm`, `imodem-selector.asm`: listings of the original
  instructions for the applicable profiles.

To reproduce the components, use this command:

```
.venv/bin/python tools/verify_courier_rate_report.py
```

The live reproduction uses the same paired-call settings as the MP audit:

```
COURIER_DSP_TRACE_LIMIT=10000 \
.venv/bin/python tools/probe_imodem_analog_pair.py \
  --analog-settings 'X1S27=1S54=0S58=48&A3&B1Q0&U26&N39' \
  --imodem-settings 'S54=0S58=48&A3&B1Q0' \
  --imodem-nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --instructions 300000000 --analog-instructions 220000000 \
  --analog-mem-watch 0a17:0a28 --analog-dsp-write-watch 031c \
  --analog-dsp-trace-range e2dd:e307 \
  --analog-dsp-peek 031c --analog-dsp-peek 0364 \
  --output /private/tmp/x2-rate-ceiling-call
```

For the I-modem selector run, use a separate output directory. Replace
the analogue trace options with `--dsp-trace-range cff4:d01c`. The harness
saves the server data and the program dumps. These are capped calls. Thus, do not
think that the later disconnect/reset is the rate state at connection time.
