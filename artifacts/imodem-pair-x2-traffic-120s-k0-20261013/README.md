# Two-minute symmetric x2 traffic: PASS

Two unmodified `Ie030002.nac` supervisors/native DSPs, byte-exact PCMU bearer.
Run with `S54=0S58=48&K0`, the existing 230400-bps NI-1 NVRAM profile,
`--instructions 1200000000 --traffic-seconds 120 --check-connect --check-x2`.

Both ends returned `CONNECT 64000/ARQ/x2/LAPM`. The caller received all 221
answer records (117,351 bytes); the answer received all 222 caller records
(117,882 bytes). No partial or in-flight records remained. Last receive
completion was at 119.8/120.3 seconds after CONNECT; the largest gaps were
4.5/4.6 seconds. Both ISDN calls remained active through 215.4/215.5 seconds
post-CONNECT. There were no corruption events, CPU/DSP errors, UART drops,
UART overruns or PCM underruns. `summary.json` records `traffic_verified: true`.

The 64-KB serial **report capture** is truncated by design; `serial_session`
contains the live terminal stream and the traffic verifier checked it during
execution. Legacy `data_delivery` fields in this run's summary refer to empty
marker arguments; use the `traffic` fields for numbered-record delivery.

Firmware SHA256:
`3f9a7aa8033323c28eebfee950b53267a67b7ad9141ebf30271918d0babbe358`

NVRAM (`../imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav`)
SHA256: `ddd313b85f2d57c0c157a46b2bc014a814f0cff0a853af35faa839aeca87db35`

This is sustained bidirectional delivery, not 64-kbit/s saturation or analogue
Courier interoperability. See `../../docs/imodem-x2-traffic.md` for the capture
bug, failing controls, traffic framing and reproduction command.
