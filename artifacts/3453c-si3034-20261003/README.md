# Native Si3034 correction and pair retest

Refer to the [implementation notes](../../docs/3453c-si3034-emulation.md).

`boot-control-fixed.json` confirms that the firmware makes ATI0 = 5608A. This occurs after
we enabled the native Si3034 serial codec and corrected the priority of the mailbox output latch.
The guest programs PLL registers 7–9 and gets to 7,200 Hz.
`boot-control.json` keeps the intermediate diagnostic failure of the mailbox output.

`v90-pair/` is the longer run (150M analogue / 400M I-modem) after the correction of the serial
protocol and the PLL. It clocks 244,305 primary codec frames and
does 36 register writes. It still stays in the dialing state, with no incoming
call, no carrier and no delivered payload. The two PCM captures stay silent.
`v90-final-control/` repeats the same failure before training with the final
implementation. This implementation includes the external line status and the gain/mute function.
The run uses 30M analogue / 150M I-modem instructions. Its native codec clocks
45,756 primary frames at 7,200 Hz. No run reports a CPU/DSP error.

The two directories keep the verification JSONs, the complete machine reports, the checkpoints and the raw audio.
For each run, we copy the parameter flash of the source hardware
to temporary storage. We never change it, and it is not included here.

The final applicable regression suite passes 132 tests. These include ten new
Si3034 cases, the existing C5x instructions/interrupts, the AC01 behavior, the board
bootstrap, the audio rates, the ASIC registers and the pair probe. `git diff --check`
also passes.

To repeat the run, use a new output directory:

```sh
.venv/bin/python -m tools.probe_imodem_analog_pair \
  --analog-board 3453c \
  --analog-parameter-flash artifacts/3453c-parameter-sector-20261003/f8000-fbfff.bin \
  --protocol v90 --instructions 150000000 --analog-instructions 30000000 \
  --analog-send '3453C-TO-IMODEM-12345' \
  --imodem-send 'IMODEM-TO-3453C-67890' \
  --output artifacts/3453c-si3034-repeat
```

This proves the codec setup of the guest and the service of the PCM clock/queue. It does not
prove the complete electrical behavior of the Si3034 or the modem interoperability. The
remaining 3453C call-control/ASIC path does not yet get to training.
