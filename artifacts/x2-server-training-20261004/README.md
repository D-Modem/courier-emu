# The I-modem's downstream training signal

`analysis.json` is the output of `tools/analyze_server_training.py` on the octets that the I-modem sent
to the analog Courier (`imodem-tx.g711`, written by `tools/probe_imodem_analog_pair.py`).
The octets are from 7.0 s to 12.2 s of the bearer capture, after the 7-bit marker. The tool divides the
stream where the set of codewords changes. It gives the levels and the exact period of each segment.
For two-level segments, it descrambles the sign bits. The `manual_notes` entries are
period and level counts that were measured separately on the same octets.

```
.venv/bin/python tools/analyze_server_training.py out/imodem-tx.g711 7.0 12.2
```

The command that made the capture is in `artifacts/x2-courier-phase3-20261004/README.md`.
The tool must have numpy.
