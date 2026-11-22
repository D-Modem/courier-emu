# Working Quad symmetric x2 / LAPM

The original QF060003 Quad answers the original Ie030002 I-modem across a
byte-exact PCMU B-channel. Both firmware transcripts report
`CONNECT 64000/ARQ/x2/LAPM`, and both distinct 24-character ASCII payloads
arrive intact at the opposite terminal.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --settings 'S54=0S58=50&M5&K0' \
  --quad-terminal-init 'Q0V1&A3S76=131S81=32' \
  --quad-feature-mask 0x20 --trace-dsp --trace-negotiation \
  --post-call-diagnostics \
  --imodem-send X2-IMODEM-TO-QUAD-482619 \
  --quad-send X2-QUAD-TO-IMODEM-731954 \
  --check-x2 --check-data --output /tmp/quad-x2-symmetric
```

Default instruction limits are 100M Quad / 500M caller. S76 bits are disables:
131 enables high-power constellations (128), disables client/server (1+2),
and leaves symmetric mode available. Caller S58=50 disables V.90 and the
asymmetric server role, enables high-power constellations, and leaves x2 and
symmetric mode available. Quad S81=32 disables V.90 server mode.

## Genuine provisioning and setup fixes

- Chassis `003f=2` selects firmware operating mode 4 (normal/error control).
- The probe waits for the original AT parser's complete OK and idle receiver
  before posting chassis requests. This setup completes at instruction
  4,884,067; previously the longer initialization line was interrupted by
  the old fixed 4M-instruction arming deadline.
- **Chassis parameter `01f2`, value `20`, enables local x2 availability.**
  The original dispatcher at `f4889` selects handler `f3b2:4dbb` (`f88db`).
  Its own code at `f8967..f896b` sets `8838 & 20`. No direct guest write to
  that flag, receive callbacks, DSP program or carrier state is made.
  An unprovisioned setup audit has `8838=cf`; the original x2-status routine
  at `e273b..e2745` exits at its first availability check. Provisioning gives
  `8838=ef`; the actual call then advertises x2 and selects symmetric mode.
- The Quad genuinely sends DSP configuration `0070:69fd`; the original
  call descriptor ends with `8954=04`, `895f=00ff`.
- The caller's data receiver is already ready at CONNECT in this run;
  the read-only handoff check introduces no fixed send delay.

The explicit byte-terminal adapter remains a substitute for raw-pin autobaud.
Online payload goes through the original UART handler and the native DSPs;
no carrier, LAPM completion, receive callback or received payload is injected.

## Strict result and limits

The current independent checker passes carrier, x2 modulation and data:

- Quad carrier still asserted (`8311=04`) at its instruction limit.
- Zero CPU/DSP errors, PCM receive underruns, UART overruns or caller output drops.
- Both payload checks true; `data_verified=true`, `x2_verified=true`.
- 288 100-ms bearer frames exchanged in each direction.
- Caller ATI6 after bounded-peer termination: 24 characters sent/received,
  zero lost, retransmitted blocks, retrains, link timeouts or link NAKs;
  one bler. Disconnect reason is Loss of Carrier after the Quad worker exits.

ATI6's **speed display is inconsistent** (`02400/64000`) despite both genuine
CONNECT results identifying 64000/x2 and successful bidirectional data. This
is retained as evidence, not corrected or used to claim measured throughput.
This verifies a short symmetric-x2 payload control, not a sustained 64-kbps
application soak, error-free physical line, binary DTE framing, asymmetric
x2 client/server operation, or V.90.
