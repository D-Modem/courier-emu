# Quad V.42 receive-handler control

Original QF060003 controller/modem firmware answering an original Ie030002
I-modem over the PCMU socket. No callback, carrier, or payload injection.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --trace-dsp --output artifacts/quad-v42-current
```

The completed rerun uses the deque-backed native data-event trace. The
preceding vector-backed trace was manually interrupted for its rollover
cost; `interrupted-vector-trace.log` is not a completed call result.

## Observations

- Neither CPU reports an error; the I-modem reports NO CARRIER, not CONNECT.
- Quad PCM RX underruns: **0**.
- DSP-to-CPU bank words received: **6,294**; CPU-to-DSP words sent: **6,459**.
- `receive-callback-counts.json`: **all 6,294 bank dispatches use
  `cfdb:3210`**, physical `d2fc0`, the original `CLC; RET` no-op.
- `receive-calls.json` retains the final 96 dispatches across all six banks.
  The character callback remains `13d0` (a `RET` at `d1180`).
- Startup asynchronous initialization executes twice; both receive-callback
  reset sites execute twice. No watched asynchronous-selection, callback
  restoration, or framing-install site executes.
- The bounded 4,096-event bank-read/write prefix contains 1,966 receive words
  and 2,130 transmit words. All captured transmit words are `40ff`.
- Offline LSB-first analysis finds **235 consecutive alternating `11`/`91`
  ODP characters**, with valid 8N1 framing and nine additional mark bits
  between characters. Receive-stream offsets: 11,271 through 15,727 exclusive.
  `summary.json` contains `quad_v42_inspection`; the prior capture gives the
  same result (`prior-bitstream-analysis.json`).

`modem-flash.bin` is the controller-loaded original flash, retained for
static disassembly. The remaining `quad/` outputs are from the completed run.

## Conclusion and limit

Valid packed originator detection reaches the supervisor's data-bank
interface but is discarded by its active no-op receive handler. Investigate
why the real call leaves that handler selected, including the reset and
receive-mode initialization path. The evidence does not identify the missing
input/transition yet and does not establish LAPM or payload interoperability.
The trace-performance fix changes diagnostic storage, not firmware state.
