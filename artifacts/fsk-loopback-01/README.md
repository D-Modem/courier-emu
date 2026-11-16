# Analogue loopback: the firmware demodulating its own transmitter

Each run does the bring-up of the ROM again for one of the four 300 bps bands:
transmit setup, receive setup, then `d94e`, `d895`, `d879`. The run installs nothing
manually. It sends each transmitted word back as the next received word. The
bits come out of the receiver of the firmware at `d8aa`.

| mode | sampling offset | bit errors over 511 |
|---|---:|---:|
| `v21-originate` | 41 | 0 |
| `v21-answer` | 43 | 0 |
| `bell103-originate` | 44 | 0 |
| `bell103-answer` | 42 | 0 |

The offset is the group delay of the receiver. It is stable for each mode. We measured the
symbol period of 48 samples. We did not derive it. It does not yet agree with the one bit for
each invocation of the transmit shift register. Refer to `docs/fsk-modulation.md`.
