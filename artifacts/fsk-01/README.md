# The modulator alone

The `v21-*` and `bell103-*` files come from the modulator of the firmware.
An external harness keyed it at 24 samples for each bit. The two-tone
detector of this repository demodulated the signal.
The value `harness_keying_rate` in each manifest is the choice of this harness.
It is not the bit clock of the firmware. Refer to `docs/fsk-modulation.md`.

For the firmware when it demodulates its own transmitter, refer to `../fsk-loopback-01/`.
