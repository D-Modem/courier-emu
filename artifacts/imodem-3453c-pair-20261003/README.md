# I-modem against the emulated 3453C, 2026-10-03

The pair does not establish a call. The last run, with V.90 selected, executes
150 million 3453C supervisor instructions and 400 million I-modem
instructions. The two modems exchange 66.6 seconds of line samples. The 3453C
consumes all of its `ATX1S27=1S58=1DT5551234` command and goes off hook, but it
stays in `dialing`. The I-modem does not get an incoming call. It returns OK to
the configuration and does not report CONNECT. Neither of the queued payload
markers arrives.

The two captured analogue directions are fully zero (532,800 samples each).
The native codec reports no register writes, no programmed sample rate and
sample_rate 0. The separate behavioral codec reports a successful bring-up.
That does not show native datapump audio operation. These observations
identify a failure before training. They do not show a V.90 interoperability
failure or a measured data corruption. The last run reports no CPU/DSP error.

The recovered mask ROM downloads a resident that agrees, and 4,096 overlay
words are verified. An independent ATI0 control with initial input returns
5608A, with no queued bytes left (`ati0-control.json`). Each run copies the
parameter flash to a temporary private file. The runs do not change the
source capture.

Final evidence: `v90-full/result.json`, `v90-full/summary.json`,
`v90-full/verification.json`, checkpoints, and WAV/G.711 captures.
The control with 30 million instructions and initial input is in
`v90-boot-command/`. The earlier control with scheduled input
(`v90-local-socket/`) leaves all 24 dial bytes in the queue. Thus it is not a
valid negotiation test. `v90/` and `v90-retry/` record socket startup failures
in the sandbox. The dial preflight without parameters fails during the overlay
acknowledgement. It is not the last test.

The pair probe now supports `--analog-board 3453c`. This option selects stock
2_3_33.XMF, the worker boot configuration for the recovered ROM, and an
optional private parameter flash. The probe does not inject a carrier, rate,
training waveform or received payload. The regressions of the 3453C
boot/monitor and the pair probe pass: 37 tests.

To repeat the run, use a new output directory:

```sh
.venv/bin/python -m tools.probe_imodem_analog_pair \
  --analog-board 3453c \
  --analog-parameter-flash artifacts/3453c-parameter-sector-20261003/f8000-fbfff.bin \
  --protocol v90 --instructions 400000000 --analog-instructions 150000000 \
  --analog-send '3453C-TO-IMODEM-12345' \
  --imodem-send 'IMODEM-TO-3453C-67890' \
  --output artifacts/imodem-3453c-pair-repeat
```

The next investigation is the runtime Si3034/serial audio and call control
path of the 3453C. More protocol coverage cannot show interoperability while
the originating call stays in dialing with silent output.
