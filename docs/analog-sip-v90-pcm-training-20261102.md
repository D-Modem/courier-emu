# Analog Courier V.90: PCM training failure localization (2026-11-02)

**Latest:** the [finite-bank scheduling follow-up](analog-sip-v90-data-banks-20261103.md)
records independently confirmed **50666 V.90/LAPM/V42BIS on 7900** with a readable
menu, using the isolated level-conversion experiment. Sustained exact payload
and 7910 V.90 remain open. That report also corrects the transport-law assumption:
7910's captured digital INFO0d advertises **A-law**. The route/law observations
below are historical, not sufficient evidence of the actual law in every call.

**Earlier update: the underlying delayed-call/block-repeat defect is repaired and
verified offline**, including 143 CRC-valid MP frames through the native DSP.
See [the repair and validation report](c5x-delayed-call-repeat-v90-20261102.md).
The later [7910 PPP test series](analog-sip-7910-ppp-20261102.md) proves login
and exact peer/internet ICMP at V.34; V.90 still falls back and sustained-load
qualification remains incomplete. The observations below document the original
failure. No firmware thresholds, clocks, or PBX settings were changed.

## Answerer and transport

Read-only inspection of `eicon420.net.cryan.nz` confirmed that
`bri-test-answerer` runs `/usr/local/sbin/bri_test_answerer.py` using
`/etc/bri-test/config.json`. Current routing is:

* 7900: `/dev/ttyds1,2`, Eicon controller 2 (A-law).
* 7910: `/dev/ttyds3,4`, Eicon controller 1 (mu-law).

This identifies these current routes, not all historical calls. The service
journal corroborated the tested V.34 connections. Read-only `mantool` polling
was retained with the latency experiment; one earlier last-call diagnostic
reported 1048-ms roundtrip, -27-dBm receive level and 38-dB SNR.

The previously rejected A-law experiment used account 6000. Existing account
2905 permits A-law, so subsequent experiments used that account without
changing endpoint/PBX configuration. PBX channel inspection verified A-law on
both legs with no transcoding during the A-law controls. Credentials were
passed over SSH/stdin/environment, not embedded in commands or this document.

## Experiments, not production fixes

The following isolated 7900 experiments all fell back to 31200 V.34:

| Private archive suffix | Configuration |
| --- | --- |
| `v90-alaw-20261102-134756` | A-law transport |
| `v90-levels-20261102-135134` | A-law plus experimental level conversion |
| `v90-latency-20261102-140254` | Above, 10-ms exchange frames, 40-ms TX reserve |
| `v90-pcm-20261102-145300` | Above plus passive pre-descrambler captures |

Archive prefixes are `.artifact-archives/analog-sip-vmhost-`.

Level conversion was an opt-in `sitecustomize.py` experiment in the isolated
vmhost snapshot, **not a production change**. It used the existing assumed
AC01 full scale +8.75 dBm and DAA TX loss 11.4 dB, with G.711 A-law full scale
+3.14 dBm0: RX gain `10**((3.14-8.75)/20)`, TX gain
`10**((8.75-11.4-3.14)/20)`. These assumptions are not physical measurements
of this board. Attenuating the old mu-law recording alone did not fix its
rate-selection failure. These calls do not establish clipping as the cause.

The original mu-law-to-7900 replay exited rate selection at `e65d` with
`ACC=0`. A-law replay progressed beyond it; the live level-converted calls
returned `ACC=14`. Lower transport latency did not fix the later failure.
Those observations do not isolate companding, endpoint, levels, and timing as
independent variables.

## CPt and CP really are generated

A network-free replay of the latency recording captured payload bits at
serializer PC `b12c`, using `ACC & 1`, word index `03d4`, payload word count
`03c9`, and native CRC `03dc`. Buffer `0940` was selected by `039f` bit 14;
reading `ff38` instead would inspect the wrong buffer.

Reconstructing framing, zero separators, and reflected CRC produced strict
valid frames matching the native running CRC:

* Repeated CPt: 55 words / 972 bits, compatibility 0, DRN 16, three
  constellations, A-law, gain 8190, CRC remainder zero. CRC `e244` on frames
  0–9, `dbb3` on frame 10.
* CP from frame 11: 71 words / 1244 bits, compatibility 1, DRN 14, four
  constellations, A-law, gain 8190, CRC `3b23`, remainder zero.

This supersedes the earlier hypothesis that firmware never sends CPt or
never progresses past it. It does **not** independently certify the upstream
analog waveform. The initial 16-point waveform recovery failed; the later
QPSK decoder recovered 51 strict CPt/CP frames and established that the actual
live CPt differs from this replay CPt. See the repair report.

## Independent downstream decoding

The sibling `v90modem` Phase-4 tap decoder was compiled privately with A-law
and the observed INFO1a U_INFO of 76, rather than its hard-coded mu-law/48
default. It decoded the original latency-call downstream RTP octets using
the reconstructed CPt frame 0:

* CPt: D=24, K=19, Sr=1; three 9-point masks, DFI `010102`, codec-output
  constellations differ, L=3, a1=1, other shaping coefficients zero.
* Ri, TRN2d and MP events occurred; 213 MP frames were decoded through the
  selected interval, including acknowledgment 1, maximum DRN 13 and rate
  mask `0fff`.
* MP precoder: `(965,-95), (-634,6), (492,137)`.

This establishes recoverable MP information in the digital downstream
capture. It is **not certification of every training symbol**: the same run
reported 1676 modulus failures, zero out-of-constellation failures, and only
457 initial consecutive TRN2d one bits. Its selected interval extended past
the initial MP acquisition. Training-sequence alignment, use of replay CPt
versus the live transmitted CPt, and subsequent transitions still require
careful separation.

RTP indices and recorded exchange-WAV indices do not share an origin. The
initial DIL-window match suggested a 14,122-sample offset, but was ambiguous
within the repeating waveform. Nonperiodic windows establish **1120 samples**
and RX gain about 0.5242; see the repair report. Do not compare timestamps
without alignment.

## Live failure: inverse mapper produces a constant word

The successful live passive probe is fingerprint-gated at:

* Rate-selection return `e65d=e388`, caller anchor `e2dd=bf09`.
* Receive descrambler entry `8ce8=b16f`, `8ce9=4e80`.

Captures at `8ce8` observe `0320` **before** the descrambler overwrites it.
DP=6 and `006f=0843` select the observed V.90 path. In the 145300 live call:

* Rate selection returned 14 with `0301=14644`.
* 13,191 eight-bit pre-descrambler chunks were captured.
* The entire captured sequence was exactly `00,7e,03`, repeated **4397**
  times: the same 24-bit word `037e00`, not a varying MP bitstream.
* Equalizer/feedback-path values `0300` and `0338` were identical at these
  capture points: min -768, max -511, mean -648.4724, standard deviation
  31.3327. This is a small fluctuation about a DC operating point.

Thus the live receiver is already failing **before MP framing/CRC parsing**.
Extending its timeout, accepting a bad CRC, or manufacturing CONNECT cannot
repair that bitstream.

The call completed naturally: exit 0, 600M instructions, 177.06 s, V.34
CONNECT/menu. Adapter active RX underruns/rebuffers and RTP RX missing/late
samples were zero. TX had four rebuffers and a 103.43-ms maximum packet gap;
that maximum alone is not a chronology or complete channel qualification.
The probe is passive but its real-time overhead is not assumed negligible.

An earlier 144705 probe stopped with exit 2 because its diagnostic fingerprint
was incorrectly specified; it is retained, **not counted as a modem failure
or successful control**. The fingerprint was checked against the actual
loaded program before the successful rerun.

## Replay narrows the internal path, but is not an exact live oracle

`/tmp/replay_courier_v90_failure.py` replays the recorded exchange RX waveform
without a network. Its TX comparison diverges from sample zero; 5-ms replay
blocks also differ from the original 10-ms live blocks. It is **open loop**,
not a verified exact reproduction of the live DSP trajectory.

Nevertheless, it reproduced the same constant `00,7e,03` pre-descrambler
sequence (4386 repetitions). Its DC polarity differed from the live run:
about +681 rather than -648. A replay with modeled hybrid return disabled
still produced the same repeated chunks; this is a counterfactual diagnostic,
not a reason to remove physical echo from production.

Additional replay observations:

* At ISR PC `8182`, DRR remained a varying bipolar signal: roughly 4.2k
  standard deviation, 9600 primary samples per recorded second. Meanwhile
  `0300` collapsed to roughly +681 with decreasing variance.
* `0300` is written by receiver filter PC `e06d`, following the MAC/MACD
  chains at `e047..e078`; `0338` is the associated subsequent result.
* A snapshot near WAV sample 170000 showed a varying raw filter window
  (standard deviation 2753) but small FFE coefficients (-172..160), and
  near-constant decision-feedback history (674/698). The coefficient alias
  `data[09c2:0a36] == program[21c2:2236]` held in that snapshot.

A subsequent scheduling control used the same replay input with both
`COURIER_WORKER_POLL=0` and `COURIER_FAST_SERVICE=0` (5-ms blocks). It still
produced 13,158 eight-bit chunks: `00,7e,03` repeated 4386 times. `0300` had
mean +692.4083 and standard deviation 29.8934. Output is retained in
`cooperative-pc-8ce8-gain-1.000000/pcm-summary.json`. Disabling these
accelerations did not remove this failure; this does not certify every aspect
of scheduling or make the replay an exact live oracle.

This question is now resolved for the reproduced collapse: a delayed call
at the RPTB boundary returned past the loop, leaving invalid constellation
entries that were used as training targets. The repair report documents the
instruction regression and before/after native receiver evidence. End-to-end
live qualification remains outstanding.

## Retained analysis and next step

Private replay outputs are under
`.artifact-archives/analog-v90-offline-failure-20261102/`, especially
`cpt-pc-b12c-gain-1.000000`, `raw-rx-pc-8ce8-gain-1.000000`,
`adc-pc-8182-gain-1.000000`, and `full-pc-8dcf-gain-1.000000`.

The live PCM archive contains full reports, PCM, pcap, raw passive state and
`7900-pcm-summary.json`. `tools/analyze_courier_pcm_trace.py` reproduces the
chunk-pattern and signed equalizer statistics. It does not claim completeness
of the native 64-record capture ring. Six synthetic analysis tests pass.

The later work recovered the actual live CPt, checked the training reference,
and fixed the demonstrated C5x delayed-call defect. Next: repeat bounded
7900/7910 calls when the shared answerer is free, then qualify carrier and
duplex payload. See the repair report for the current status.

The tests used only the isolated `/root/courier-sip-20261102-113720` snapshot.
Existing deployment and PBX configuration were untouched. Test calls and
processes have ended; a later occupancy check showed an unrelated 6003/6002
call, which was not interrupted.
