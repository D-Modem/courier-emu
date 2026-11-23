# Current boundary

The 80186 and the C51 run in lock-step at their recovered 20/25 MHz ratio. The
harness reconstructs the DSP bootstrap of the supervisor from ports
`0x40..0x4e`. It verifies it byte for byte against the XMF C51 boot segment. It
publishes it to the native DSP through the recovered mailbox. The DTE serial
path can inject commands and capture the result text that the firmware makes.
The ASIC line frame now transports 9.6 kHz input/output samples and captures
dial tones.

This device work remains:

- The command mailbox of the original datapump
- The full timing of the 80186 peripherals
- C51 opcode forms that no run has used yet

Under `--daa-codec`, the harness models the ring, loop-current and frame-lock
state of the silicon DAA at register level. Its revision gets to the firmware
through mailbox tag `0x7b` and `ATI7`. But we did not find a read path to the
line-side status fields. Thus, nothing uses those fields yet.

The board latches, the signal lines of the front panel and the Microwire
settings EEPROM are modeled. On the settings side, two items remain: a
recovered parameter-flash sector for `0xf8000`, and front-panel legends for the
indicator bits that have no name. This firmware has no boot-time NVRAM profile
load to model.

### Quad CPU AT terminal

For the current server answer attempt, see
[Quad server bring-up](quad-server-bringup.md). The probe can now boot from
the QF archive. It records the `NO CARRIER` path that the watchdog causes.
CPU/DSP call control is not yet complete. It is not yet a negotiation peer.

The QF060003 modem now executes `AT` → `OK` with an explicit byte-terminal
adapter. Run `PYTHONPATH=. .venv/bin/python tools/probe_quad_at.py` to boot the
controller and load a modem. The script then verifies `OK`, `ERROR`, then `OK`
through the real firmware parser. See
[the measured transcript and adapter limits](quad-at-terminal.md).
Raw-pin autobaud is not yet complete.

The Quad C50 endpoint now boots the resident that this CPU streams. It makes
available a digital-call timeslot with one opaque 8-bit G.711 codeword in each
direction at 8 kHz. `connect_digital_call` selects mu-law (`0xff`) or A-law
(`0xd5`) idle fill. `receive_g711` and `transmit_g711` are the byte-exact
ingress and egress surfaces.

The **stock** DTMF path of the captured QF060003 DSP now also runs. It executes
these parts:

- The QF selector at `0x8de0`
- The oscillators at `0x8e54`/`0x8e60`
- The sine helper at `0x92da`
- The mixer at `0x82be`
- The serial ISR at `0x83e1`

No generated DSP program or host oscillator supplies its samples. To render and
measure all sixteen stock keypad tones, run
`PYTHONPATH=. .venv/bin/python -m courier_emu.quad_audio --ram
artifacts/quad-identify-20260910/ram.bin --output /tmp/qf-dtmf`.

The captured resident also contains the G.711 expander and compressor of QF
itself. The component runner executes its DTMF generator, the two compressor
branches and its byte serial ISR. These make raw 8 kHz `.g711` streams without a
host codec. The chassis call-control request that arms this path is not yet
complete. See `docs/quad-dsp-pcm-path.md`.

Its stock answer-signal family also executes:

- 2100 Hz ANS
- ANS with periodic phase reversals
- ANSam with the 15.05 Hz amplitude modulator of the resident
- ANSam with phase reversals

Run `PYTHONPATH=. .venv/bin/python tools/probe_quad_answer_g711.py` to send
each variant through the QF A-law and mu-law compressor branches and the serial
ISR. The script writes raw `.g711` streams and decoded WAV previews under
`artifacts/quad-answer-g711-20260910/`.
