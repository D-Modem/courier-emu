# Validation

Final aggregate, including the public erased-settings PCM-only payload and
single-sided DTR-loss regressions:

```sh
.venv/bin/python -m pytest -q tests/test_3453* tests/test_machine_map.py \
  tests/test_cli_link.py tests/test_native_machine.py tests/test_c5x_disasm_moves.py
```

**199 passed in 618.13 s.**

Focused IRQ ownership, UART register/status/scheduling, original DTR predicate,
original framer (including carrier-loss NUL), and CLI forwarding controls:
**64 passed in 0.68 s.** Python compilation and scoped diff checks passed.

The DTR regression checks exact terminal output before the external drop,
original post-drop receiver bytes, both original `NO CARRIER` results, and
native hook-release transitions. An initially stricter ending assertion exposed
B's native loss-period NUL and later leased-line retry. Timed traces and
original-code replay in both engines established those behaviors; neither is
filtered out or disabled to obtain a pass.

This does not establish immediate-local-CONNECT losslessness, long-run/binary
transfer, dialed ringing, or complete startup/electrical fidelity. All runs were
offline. Raw traces and full flash/settings remain outside these selected
public diagnostics.
