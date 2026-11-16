# Analog Courier to I-modem x2, 2026-10-03

The original analog Courier firmware now reports **53333/x2/LAPM/V42BIS**
when it is connected to the I-modem. The two different terminal markers arrive correctly.
The I-modem reports 33333 at its own terminal. These are separate endpoint
results. Server mode stays enabled (live I-modem S58=48, bit 1 clear).

The [production repeat](../artifacts/imodem-analog-x2-53333-production-20261003/verification.json)
and the [read-only diagnostic capture](../artifacts/imodem-analog-x2-fullband-highpower-20ms-20261003/verification.json)
record the higher rate. The native receiver reconstruction filter now goes to
the lower Nyquist frequency. Before, it cut 2 percent more.
Its 128 taps, delay and sample clocks did not change. At 3.8 kHz, an independent
tone check improves from 39.36 to 61.90 dB SNR. This value includes the amplitude and phase
error, and does not fit either of them away. A native regression requires more than 60 dB.

The working higher-rate configuration uses S58=48 on the two ends. V.90 is
disabled and the higher-power constellation is selected. The server and
symmetric capabilities stay. With ordinary S58=32 settings, the same
full-bandwidth reconstruction gets to 52000 bps and delivers the two markers.
We do not inject firmware training, a carrier, a negotiated rate or a payload.
The two 53333 runs finish with correct messages in the two directions, no guest
NO CARRIER, no CPU/DSP error and no connected receive underruns. The analog
CPU limit is 450 million instructions, and the I-modem limit is 600 million.
The short message exchange verifies the negotiated rate and the data delivery.
It is not a measurement of a sustained application throughput of 53333 bps.

The later [56000-bps controls](imodem-analog-x2-56000-20261003.md) do not
establish a stable connection at a higher rate. 53333 is still the verified result.

## Previous 41333 baseline

The [native results and verification](../artifacts/imodem-analog-x2-normal-power-x1-20261003/verification.json),
the [independent repeat](../artifacts/imodem-analog-x2-41333-repeat-20261003/verification.json),
and the [original high-power settings with X1](../artifacts/imodem-analog-x2-matched-x1-20261003/verification.json)
all report 41333 at the analog end. They exchange the two markers, and they have no CPU
or DSP error and no guest NO CARRIER during the 400-million-instruction runs.
We do not inject firmware training, a carrier or a rate. The high-power repeat
also shows that the original 33333 value was the I-modem result,
not the analog receiver result: X0 had hidden the analog rate.

## Higher-rate acceptance target

For the clean modeled analog downstream, the acceptance target is
**a minimum of 53333 bps**, with correct payloads in the two directions and a retained carrier.
The higher-rate runs above meet it. The earlier 41333 result was a working
baseline. It did not establish the maximum rate of an ideal analog line.
The requested PCM mask already included 53333 and the higher analog x2 rates.

More controls on 2026-10-03:

| Control | Analog result | Payloads | Evidence |
|---|---|---|---|
| 10 ms exchange, normal x2 settings | NO CARRIER, no CONNECT | None | [Summary](../artifacts/imodem-analog-x2-ideal-10ms-20261003/summary.json) |
| 20 ms exchange, V.90 only | No CONNECT in 300 million instructions | None | [Summary](../artifacts/imodem-analog-v90-ideal-20ms-20261003/summary.json) |
| 20 ms exchange, downstream level -3 dB | 41333/x2/LAPM/V42BIS | Both | [Summary](../artifacts/imodem-analog-x2-ideal-rx-minus3-20261003/summary.json) |
| 20 ms exchange, downstream level +3 dB | NO CARRIER, no CONNECT | None | [Summary](../artifacts/imodem-analog-x2-ideal-rx-plus3-20261003/summary.json) |

A separate diagnostic native build changes only the analog receive
reconstruction kernel from 128 to 512 taps, and its cutoff from 0.49 to 0.5
cycles for each 8-kHz input sample. It falls back to V.34 during the run.
The longer FIR also adds 24 ms of group delay. Thus, this experiment does not
isolate the bandwidth from the training timing. We did not use the longer kernel.
The [diagnostic patch](../artifacts/imodem-analog-x2-ideal-filter512-20261003/diagnostic-filter.patch)
records the exact experiment. It is not a fix that we use.

Two initial timestamp-observer runs (`fullband-soak` and `fullband-highpower`)
imported the transport before the paired CLI selected its default. Thus, one side had
100 ms and the other side had 20 ms. They are not valid controls, and we
exclude them. The successful captured run explicitly sets
`COURIER_LINE_FRAME_MS=20`. The production repeat uses the ordinary paired CLI
without the observer.

## Changes and evidence

The analog pair CLI now uses 20 ms socket exchanges by default. The general
line default stays at 100 ms. `COURIER_LINE_FRAME_MS` selects a common exchange
size for the two processes and keeps their 8 kHz sample clock. The I-modem
still has a complete receive reserve. Its size follows the exchange size.
The lower transit delay lets the original training scripts continue into
x2. Before, they timed out and then connected in V.34.

The carrier parser of the probe now accepts lowercase `/x2` modulation names. The
old case-sensitive expression did not report the I-modem marker after a real
x2 CONNECT. A regression tests the complete lowercase result line.
`--imodem-nvram` selects the working NI1 profile. `--link-diagnostics` queries
native ATI6 after carrier. The checkpoints keep the terminal text.

The earlier table below records the I-modem result. In these runs, X0 did not show the analog
rate.

| Exchange | I-modem result | Payloads | Evidence |
|---|---|---|---|
| 100 ms | 21600/V34/LAPM | Both arrived | [Control](../artifacts/imodem-analog-pair-x2-high-power-ni1-20261003/verification.json) |
| 20 ms | 33333/x2/LAPM | Both arrived | [Working x2](../artifacts/imodem-analog-pair-x2-20ms-default-filter-20261003/verification.json) |
| 5 ms | 33333/x2/LAPM, then guest NO CARRIER | Both arrived before the call cleared | [Lower-delay control](../artifacts/imodem-analog-pair-x2-5ms-20261003/verification.json) |

The 20 ms run uses the original 128-tap Kaiser reconstruction filter. It has
zero connected analog receive underruns and zero I-modem PCM receive
underruns, and it reports no CPU or DSP error. The foreground overlay assistance is
disabled. We do not inject a guest carrier, a training decision, a rate or a payload.
An earlier full-Nyquist reconstruction experiment used a different setup and
fell back to V.34. When we repeated it with the working 20 ms configuration, we got
the higher rates that this document reports above.

## Reproduction

```sh
PYTHONPATH=. .venv/bin/python tools/probe_imodem_analog_pair.py \
  --analog-settings 'X1S27=1S54=0S58=48&A3&B1Q0&U26&N39' \
  --imodem-settings 'S54=0S58=48&A3&B1Q0' \
  --imodem-nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --instructions 600000000 --analog-instructions 450000000 \
  --analog-send ANALOG-X2-53333 \
  --imodem-send IMODEM-X2-53333 \
  --output artifacts/imodem-analog-x2-repeat
```

To reproduce the old transport delay, set `COURIER_LINE_FRAME_MS=100`.
The I-modem keeps the server and symmetric capabilities. S58=48 disables
V.90 and selects the higher-power constellation. The analog &U26/&N39 request selects
40000..57333. The firmware still includes its lowest fallback bit. X1
reports the analog rate, and dial-tone detection is not necessary. The fixed DTE rates and Q0 keep the
terminal operation and the visible result codes during the carrier establishment.

## Earlier rate investigation

The reported bitmap `0275` of the analog native DSP confirms these items: local x2, completed
V.8, remote x2, channel qualification, normal high-frequency rolloff and
recognition of the remote x2 server. Thus, the recognition works.

A control with 6 dB receive attenuation still reports 33333/x2 and delivers the two
markers. A +6 dB gain control does not increase the reported rate, and it loses part
of the upstream marker. Neither control establishes the requested higher speed.

The help of the analog firmware maps &N27 to 41333 and &N39 to 57333.
`&U27&N39` sends the PCM mask `7ffd`, but it still reports 33333/x2 and delivers
the two markers. The original supervisor at `88fc9..89047` intentionally ORs
bit 0 into its PCM rate mask. Thus, it includes the lowest x2 rate also when a higher
minimum is requested. Thus, the minimum command alone cannot prove
or enforce a connection above 40 kbps.

[Rate request and native diagnostics](../artifacts/imodem-analog-pair-x2-rate27-20261003/verification.json).
ATI6 reports legacy Speed 24000/32000, although the result is x2. Thus, interpret those fields
against the PCM reporting path. Do not use them as
independent evidence of a higher PCM rate. The earlier X0 result did not show
the analog speed. Thus, the 33333 result of the I-modem was not sufficient to
characterize the two directions. The pair CLI now uses X1 by default and records
`connect_rate_bps` separately for each terminal. `--analog-result-mode 0`
reproduces the old bare CONNECT behavior.

A native read-only capture at overlay-6 PC a688 records the direction masks
and the descriptor words. In the control run, no capture gets to overlay-8 PC ece8.
These observations are still diagnostic evidence. They do not replace
the native CONNECT result of the modem. A separate X3 control reports 37333
at the analog end and then loses the carrier. An asymmetric 20 ms control
delivers the two markers, but it also loses the analog carrier. Neither is the working
41333 configuration above.
