# Current boundary

**Live hardware status (10 November 2026):** the analog 403 firmware can
negotiate V.34/LAPM and real V.90/LAPM over SIP, and it carries PPP payloads
without errors. Sustained reliability is not yet solved. In the most recent V.90
series, only one 60-second call passed. No attempt with a 600-second target got
V.90. V.34 LAN tests show changes of the sample clock on the sender side,
with zero loss of RTP sequence numbers. The first task is to make the samples
at the correct time, and to do a 600-second V.34 qualification. Do not make the
buffers or the PPP checks less strict. Refer to
[the disconnect investigation](analog-disconnect-investigation.md),
[the V.90 repeated tests](v90-7930-repeated-tests.md) and
[the TX timing plan](tx-timing-investigation.md).

The 2.1.x limits below and the [minimal SIP dial-out](sip-dial-out.md) page
tell about the earlier bring-up. They do not tell the current SIP features of
the 403. They do not show that all firmware versions have the same blockers.

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

The Quad now connects to the original I-modem with **V.34/LAPM and symmetric
x2/LAPM**, and it sends ASCII data in the two directions. In the symmetric
test, the two modems report **64000/x2/LAPM**, with zero PCM underruns and
zero UART drops. Refer to [Quad server bring-up](quad-server-bringup.md) for
the commands, the feature provisioning of the chassis and the evidence.

Asymmetric **server** x2 also passes against an analog Courier client at
52000/33333. The two payloads arrive without errors, and the carrier stays
on to a 60-second media boundary. Run
`tools/probe_quad_analog_pair.py --check-x2` with an `--output` folder. A
**three-minute V.34 traffic test passes at 9600**. The default **31.2/33.6k**
pair also passes 60 connected seconds. Throughput at full rate, long x2 tests
and binary DTE data are not yet verified. The vendor documents tell that Quad
client mode is not supported.

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
host codec. Chassis arming and answer now run through the original mailbox.
Refer to [Quad server bring-up](quad-server-bringup.md) for the paired call
and to `docs/quad-dsp-pcm-path.md` for the component measurements.

Its stock answer-signal family also executes:

- 2100 Hz ANS
- ANS with periodic phase reversals
- ANSam with the 15.05 Hz amplitude modulator of the resident
- ANSam with phase reversals

Run `PYTHONPATH=. .venv/bin/python tools/probe_quad_answer_g711.py` to send
each variant through the QF A-law and mu-law compressor branches and the serial
ISR. The script writes raw `.g711` streams and decoded WAV previews under
`artifacts/quad-answer-g711-20260910/`.
