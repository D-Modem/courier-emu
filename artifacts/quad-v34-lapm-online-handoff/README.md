# Working Quad / I-modem V.34 LAPM data

Original QF060003 supervisor and C51 answering an original Ie030002 I-modem
across a byte-exact PCMU B-channel. The controller loads the Quad firmware;
chassis requests arm/configure/answer through the real mailbox. No carrier,
LAPM completion, DSP program, receive callback, or received bytes are injected.
The explicit Quad byte-terminal adapter substitutes for raw-pin autobaud and
feeds online DTE bytes into the original UART handler without patching it.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --quad-instructions 100000000 --imodem-instructions 500000000 \
  --trace-dsp --post-call-diagnostics \
  --imodem-send IMODEM-TO-QUAD-482619 \
  --quad-send QUAD-TO-IMODEM-731954 \
  --check-data --output artifacts/quad-v34-lapm-online-handoff
```

## Result

- I-modem: `CONNECT 31200/ARQ/V34/LAPM`.
- Quad: `CONNECT 33600/ARQ`.
- Both distinct 21-character payloads arrive intact at the opposite terminal.
- `summary.json`: `data_verified=true`, both payload checks true.
- Neither CPU/DSP reports an error. Both PCM receive-underrun counters are zero.
- No host UART overruns or I-modem host-output drops.
- Quad remains connected at its 100M-instruction limit (`8311=04`).
- After the Quad process closes its socket, the I-modem reports NO CARRIER.
  Its original ATI6 identifies **Loss of Carrier**, not Keypress Abort,
  and reports 21 characters sent/received, zero lost, zero retransmitted
  blocks, retrains, link timeouts or link NAKs. It also retains **86 blers**;
  this is not a demonstrated error-free line or throughput soak.

## Two fixes

1. **Operating-mode wire enum:** chassis parameter `003f=2` selects firmware
   mode 4 (normal/error control). The previous value 4 selected firmware mode
   6 and left the receive callback at the no-op `cfdb:3210`. Both probes now
   default to wire value 2; the original firmware performs the conversion.
2. **DTE handoff:** seeing CONNECT is not yet permission to send data in this
   firmware. At instruction 112,719,872 / bearer frame 154 the caller's
   receiver is `ec8d`, callback `0e0e` (abort on keypress). At instruction
   112,720,384, still frame 154, the original firmware selects receiver
   `eca9`, callback `46cc`, which stores terminal characters in its data queue.
   The harness now waits for that read-only readiness indication, rather than
   sending into the abort handler or imposing an arbitrary five-second delay.

`imodem.json` retains this transition in `terminal_handoff`. The preceding
immediate-send failure's ATI6 reports **Keypress Abort** with zero characters
sent (`../quad-v34-lapm-disconnect-diagnostics/`). A five-second delayed
control and a fixed-9600 control also deliver both payloads, but neither delay
nor a rate restriction is required by this passing run.

## Scope

This verifies short bidirectional ASCII data over digital V.34/LAPM, not x2,
full-rate application throughput, multi-minute Quad traffic, binary DTE
framing, raw-pin autobaud, or the physical card's unspecified DRR upper-byte
behavior. ATI6 reports speed 31200/33600; neither result should be advertised
as symmetric 33600 throughput.
