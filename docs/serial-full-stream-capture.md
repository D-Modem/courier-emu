# Full-stream serial evidence for long data tests

`courier run --serial-output PATH` streams all raw DTE output bytes to a binary
file. Parity bits are preserved. The worker owns, flushes and closes the file;
write errors propagate rather than silently dropping evidence. This is separate
from `serial_hex` / `serial_text` in the JSON report, which remain capped at
64 KiB. `serial_bytes_total` counts all emitted bytes, including those omitted
from the report, and `serial_truncated` still describes the report only.

CONNECT / NO CARRIER detection now uses an independent 12-byte rolling tail,
so protocol-state detection continues after the diagnostic report fills.

The sibling `v90modem/tools/probe_x2_host_courier.py` requests
`courier-dte.bin` automatically and validates its byte count against
`serial_bytes_total` before checking payloads. A missing or incomplete capture
sets `validation_status=invalid_capture` and exits with status 2; it must not be
reported as a modem delivery failure. Complete captures retain the existing
exact-after-CONNECT checks and parity normalization.

## Initial evidence and repeat

The original 600-second test at
`artifacts/x2-long/20261106-083851-600s/` has `serial_truncated=true` and only
65,536 serial bytes in its report. Its 65,507 captured payload bytes match the
expected prefix, but the rest of its 216,000-byte downstream transfer is
unverified. Its downstream failure flags are not valid delivery verdicts.

A same-payload repeat with full capture was launched at
`artifacts/x2-long/20261106-090114-600s-full-capture/`.
The stop condition is 30,000 line frames at 20 ms (600 emulated seconds,
including training), not an instruction target. Source pacing is 500 bytes/s
for 432 seconds, plus training and drain time. The instruction ceiling is only
a safety bound. This is sustained ASCII downstream plus a short upstream
message, not sustained duplex or arbitrary-binary qualification.

Focused regression command:

```
.venv/bin/python -m pytest -q tests/test_serial_output_capture.py \
  tests/test_rom_link_errors.py tests/test_dte_framing.py tests/test_cli_link.py
```

Result at implementation: 39 passed. A real CLI/worker 1,000-instruction smoke
also creates the stream and reports its total without error. The long repeat's
result is **PASS**: `validation_status=complete_capture`, all nine checks true,
and both processes exited zero. The call negotiated `53333/ARQ/x2/LAPM` and
completed exactly 30,000 frames / 4,800,000 samples (600 seconds). The full
capture contains 216,029 bytes: 29 bytes of result-code prefix followed by all
216,000 expected payload bytes, exactly, with no extra payload output. The short
upstream message also matches exactly. The report remains intentionally
truncated; the full capture length matches `serial_bytes_total`. No native error
or stderr output was reported. This qualifies this paced ASCII downstream test,
not line-rate throughput, sustained duplex, binary traffic, live SIP, or a
retrain/error-counter audit.
