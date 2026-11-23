# Fresh x2 downstream / V.34 upstream peer verification

The 2026-10-19 run passes `--check-x2-v34`. Both original modems complete
3000 shared 20-ms line frames (60 seconds including training), deliver
their distinct payloads and retain carrier. Quad PCM/UART losses and analog
connected receive underruns are zero; no CPU/DSP error occurs.

The last original DSP reports are reciprocal: analog `6A:0B0C`, Quad
`6A:0C0B`. These resolve to **V.34 upstream index 11 (26400 bps)** and
**PCM downstream index 12 (nominal 53333)**. The active Quad callbacks are
PCM TX `c395`, common V.34 RX `a44d`. Its actual receive code matches the
stock QF060003 datapump fingerprint.

The initial CONNECT strings remain 52000/x2 at the caller and 33333/x2 at
Quad. The original rate handler/formatter disassembly in
`rate-report-path.asm` shows that the server's result selector uses the
PCM result index, not the upstream V.34 receive index. The subsequent rate
reports do not rewrite those CONNECT lines.

`summary.json` is the original live result. `directional-replay.json` is a
fresh offline check using the final verifier, including both TX/RX callback
checks. The original full endpoint reports are `analog.log` and
`quad/results.json`; full DSP images are retained under `quad/`.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_analog_pair.py \
  --check-x2-v34 --output /tmp/quad-x2-v34

.venv/bin/python tools/quad_directional_link.py \
  artifacts/quad-x2-v34-directional-20261019/analog.log \
  artifacts/quad-x2-v34-directional-20261019/quad/results.json
```

This verifies mixed modulation and short duplex data. It is not a
60-connected-second sustained-throughput test. Nominal PCM rate labels
are not measurements of usable DTE throughput.

The focused directional, asymmetric, pair, initialization and PCM inspection
regressions pass 77 tests. See [the directional audit](../../docs/quad-x2-v34-directional.md)
for the original instruction addresses and rejection cases.
