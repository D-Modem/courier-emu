# Live symmetric x2 GPC scrambling

SHA-256 of the original Ie030002.nac:
`3f9a7aa8033323c28eebfee950b53267a67b7ad9141ebf30271918d0babbe358`.

The two endpoints connect at 64000/ARQ/x2/LAPM and send different markers.
Eight-bit words are GPC scrambled (`1 + x^-18 + x^-23`, LSB first). Then they are
bit-reversed into bearer octets. The two histories reset to zero at the initial
setup, and when the data callbacks are selected before CONNECT.

To reproduce the result, run these commands from the repository root. You must have permission for a local Unix
socket. No external network or hardware is necessary.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_imodem_pair.py \
  --protocol x2 --settings S54=0S58=48 \
  --nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --trace-negotiation --trace-digital-path --instructions 180000000 \
  --originate-send CALLER-X2-SCRAMBLER --answer-send ANSWER-X2-SCRAMBLER \
  --check-connect --check-x2 --output artifacts/x2-scrambler-call-reset-20261004
.venv/bin/python tools/verify_x2_scrambler_trace.py \
  artifacts/x2-scrambler-call-reset-20261004
```

`digital_path_trace` in each worker result records the writes to the mode cells and
snapshots at instruction boundaries. Captures are read-only. They do not force DSP registers,
firmware instructions, mode flags, payloads or results.
The tracer samples each million supervisor instructions. For each window, it keeps a maximum of
64 most recent hits. It starts at PC e908 (after the TX/RX history
clears). At CONNECT, it changes to e984 (before the TX scramble test).
Each capture starts with the DSP instruction count, the cycles, ACC, DP and carry.
Then it has the cells in the `capture_addresses` order. The history checks use consecutive
captures only in a window. The checks do not examine gaps between windows.

`verification.json` asserts these items:

- The two connections and the payload delivery
- Clean CPU/DSP results and zero underruns
- Active flags, widths and callbacks
- Zero initialization histories
- All 12033 sampled consecutive GPC history transitions

`focused.asm` is a static listing of the applicable original instructions.
The earlier `artifacts/x2-scrambler-call-20261004` trace also sampled TX during all of the
setup, and checked 13104 transitions. The reset trace adds direct captures of the reset
and samples TX after CONNECT.

Seven-bit calls, lower-rate mappings and retrain/fallback resets are
separate work. The value 64000 is the bearer information capacity. The test does
not measure the sustained terminal throughput, and it does not remove the LAPM framing overhead.
