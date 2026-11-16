# One band, four receivers

The modulator of the firmware transmits V.21 answer, 1650/1850. The transmitter
stays on the originate band and is gated off. Thus, only that signal gets to the
receiver. Each of the four receive setups gets the signal, one after the other.

| receive setup | carrier | bit errors over 120 |
|---|---:|---:|
| `d7a4` | 1750, the answer band centre | 0 |
| `d7ac` | 2125 | 56 |
| `d7c8` | 1080 | 64 |
| `d7d0` | 1170 | 64 |

Only the band centre of the signal recovers it. This measurement is the reason that we
call the four same-band dispatch entries analogue loopback. We did not only read this from the constants.
The manifest also contains the two datapump tables through which mailbox commands `10` and `11`
dispatch, and the mode flags that index these tables. Refer to `docs/fsk-modulation.md`.
