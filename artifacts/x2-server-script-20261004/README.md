# The I-modem's downstream training script

`script.json` is the output of `tools/decode_server_script.py` on the dump of the DSP
program of the I-modem (`dsp-program.bin`, written by `tools/probe_imodem_analog_pair.py`).
The state names and the description of the interpreter come from two sources:

- We read the original instructions.
- We made data traces of `@48`, `@49` and `@22` in a 53333/x2 call. We did not keep
  these traces because they are long run lists.

The measured stretch boundaries are those of `artifacts/x2-server-training-20261004`.
The script durations are equal to the measured stretch lengths in symbols: 363
(20 of zero, then 352 + 11), 20004, 6000, 1152.
