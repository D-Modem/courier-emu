# The Courier's signal after the x2 marker

`analysis.json` is the output of `tools/analyze_v34_training.py` on the line
output of the Courier (`analog-tx.wav`, 8 kHz) from 30.43 s to 32.72 s of the
analog clock. This is the burst that starts about 60 ms after the 7-bit marker
frame. To reproduce it, use these commands:

```
.venv/bin/python tools/probe_imodem_analog_pair.py --analog-settings 'X1S27=1S54=0S58=48&A3&B1Q0&U26&N39' --imodem-settings 'S54=0S58=48&A3&B1Q0' --imodem-nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav --instructions 600000000 --analog-instructions 450000000 --analog-send ANALOG-X2-53333 --imodem-send IMODEM-X2-53333 --output out
.venv/bin/python tools/analyze_v34_training.py out/analog-tx.wav 30.43 32.72
```

The analog recording starts about 25.02 s before the bearer capture. Thus the
burst starts at bearer second 5.41. The tool must have numpy.
