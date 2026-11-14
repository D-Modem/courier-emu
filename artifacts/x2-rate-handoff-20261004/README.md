# QF060003 PCM record and data handoff evidence

See [the detailed reconstruction](../../docs/x2-rate-and-data-handoff.md).

`verification.json` records the verified scope, the rate-selection rule and forty
integrated profiles. `57333-trace.json` contains original snapshots at instruction boundaries
for these events:

- Record acceptance
- Selected rate
- Bank construction
- Mapped output
- Later activation of the payload source

`handoff.asm` keeps the original instructions and the raw callback triplets.

To reproduce the results, use `.venv/bin/python tools/trace_x2_rate_handoff.py`. The tool
injects decoded input bits, local call state and source octets. It does not
seed the received working record, the selected rate index or the final banks. The tests
include CRC rejection and sparse local rate masks. These results do not claim a complete x2 call or
a producer of the measurement/report of the analogue client.
