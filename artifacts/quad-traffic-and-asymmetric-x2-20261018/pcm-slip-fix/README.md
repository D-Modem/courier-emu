# High-rate V.34 PCM slip: cause and correction

## Before: one inserted sample, not a DSP receive arithmetic defect

`before-*-pcm.json.gz` contain the read/write traces of the DSP PCM rings
between requested snapshots at media frames 230 and 270. Each bounded trace
retains its latest 200,000 accesses, including the corruption boundary.
`before-*-snapshots.json` record live CPU/serial/codec registers.
`before-quad-tx.g711.gz` retains the native transmitter output: all 28,572
captured Quad TX-ring samples match it, ruling out a transmitter-side slip.

Both rings have correct read/write ordering, with no stale TX reads or
unconsumed RX samples overwritten. Comparing transmitted and received octets
instead reveals:

* **Quad → I-modem:** one extra **`ff`** at received sample 6225 in the retained
  trace, equivalent to offset **198750** in Quad's complete `tx.g711`. All
  22,223 actual source samples in the overlapping capture remain in order.
* **I-modem → Quad:** all **20,972** overlapping samples match exactly.
* The caller's AM79C30 records an RX underrun at bearer frame **199200**;
  its C5x receive-FIFO underrun counter remains zero. The MUX inserted silence,
  shifting the waveform by one sample and corrupting subsequent HDLC frames.
  The later underrun at 240001 is after peer shutdown, not the original fault.

Reproduce the analysis without executing firmware:

```sh
PYTHONPATH=. .venv/bin/python tools/inspect_quad_pcm_ring.py \
  artifacts/quad-traffic-and-asymmetric-x2-20261018/pcm-slip-fix/before-quad-pcm.json.gz \
  --peer-trace artifacts/quad-traffic-and-asymmetric-x2-20261018/pcm-slip-fix/before-imodem-pcm.json.gz
```

The expected report has `transport.quad_to_imodem.ok: false` and one `insert`.
`before-analysis.json` also records the uncompressed trace SHA-256 hashes.
The original `v34-stall/` captures have not been changed.

## Correction

`G711Peer.requires_frame_service` requests per-PCM-frame media servicing from
`IsdnMachine`, even for offline calls. Completed output blocks reach the
synchronous peer and its replies reach the MUX before the next RX clock;
waiting until the next supervisor timer poll could empty the receive queue
at a packet boundary. This fixes the scheduling error rather than adding
receive padding, changing DSP clocks, forcing carrier or modifying guest
callbacks, payloads or LAPM acknowledgements.

Traffic health now checks AM79C30 bearer underruns as well as the C5x FIFO.
`tests/test_g711_peer_pacing.py` reproduces the original insertion with
poll-only service and verifies continuous sample identity with per-frame
service, using both Python and native bearer queues.

Separately, the investigation corrected interrupt-shadow handling of XF and
RETI's INTM preservation against TI SPRU056D. Focused tests cover the pin and interrupt mask.
Those corrections alone did **not** fix the corruption: their Quad waveform
and both DSP host traces were byte-identical to the original failing run.

## After: default-rate 30-second connected control

`30s-summary.json` passes genuine CONNECT and numbered duplex traffic checks:

* Caller **31200/ARQ/V34/LAPM**, Quad **33600/ARQ**; no rate cap.
* Both complete **30 connected seconds** with retained carrier.
* **12 complete records / 996 bytes** drained in each direction, no parser
  errors, UART loss, native FIFO underruns or AM79C30 MUX underruns.
* Default 64-cycle DSP service and 100000-instruction online byte spacing.

This is a paced stability control, not a full-rate application-throughput
benchmark. The archived endpoint reports retain independent measured windows
and actual UART-drain accounting.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --traffic-seconds 30 --traffic-size 64 --trace-data-lanes --check-connect \
  --output /tmp/quad-v34-pcm-fixed

PYTHONPATH=. .venv/bin/python tools/quad_traffic.py \
  artifacts/quad-traffic-and-asymmetric-x2-20261018/pcm-slip-fix/30s-imodem.json \
  artifacts/quad-traffic-and-asymmetric-x2-20261018/pcm-slip-fix/30s-quad.json
```

## After: faster 60-second connected control

`60s-summary.json` and `60s-replay.json` pass **60 connected seconds** on both
endpoints at the same uncapped 31200/33600 rates. With 256-character bodies,
10000-instruction online spacing and 512-cycle runtime batches:

* **53 intact records / 14575 bytes** arrive at the caller and **52 / 14300**
  at Quad, matching the actual far-end sends after UART drain.
* Both retain carrier; there are no parser errors, UART losses, CPU/DSP errors,
  MUX underruns or native FIFO underruns. MUX health is explicitly included
  in the measured snapshot, not inferred from the C5x FIFO counter.
* Maximum receive gaps are 3.0/1.7 seconds, including initial latency.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --traffic-seconds 60 --traffic-size 256 --quad-online-byte-interval 10000 \
  --quad-dsp-slice-cycles 512 --trace-data-lanes --check-connect \
  --output /tmp/quad-v34-pcm-fixed-60s

PYTHONPATH=. .venv/bin/python tools/quad_traffic.py \
  artifacts/quad-traffic-and-asymmetric-x2-20261018/pcm-slip-fix/60s-imodem.json \
  artifacts/quad-traffic-and-asymmetric-x2-20261018/pcm-slip-fix/60s-quad.json
```

This is roughly 240 application bytes/s, still not line-rate throughput or a
three-minute high-rate soak.

## After: 20-ms packet control

The original 20-ms-frame long-marker control failed to connect at the caller.
`20ms-summary.json` now passes with **33600/ARQ at both ends** and both full
**630-byte** distinct marker strings intact. The wire runs for 2325 frames
(46.5 seconds including training). The I-modem's first MUX underrun is at
frame 372000, exactly after the peer closes (2325 × 160 samples); the later
post-shutdown silence is not a connected traffic-window claim.

```sh
COURIER_LINE_FRAME_MS=20 PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --quad-instructions 160000000 --imodem-instructions 1000000000 \
  --quad-dsp-slice-cycles 512 \
  --imodem-send "$(printf 'I%03dabcde' {1..70})" \
  --quad-send "$(printf 'Q%03dzyxwv' {1..70})" \
  --check-data --output /tmp/quad-v34-pcm-fixed-20ms
```

## Asymmetric x2 regression control

`asymmetric-summary.json` passes the unchanged strict analog-client control:
**52000/ARQ/x2/LAPM** at the analog Courier and **33333/ARQ/x2/LAPM** at
Quad, both distinct payloads intact, both retaining carrier at the shared
3000 × 20-ms-frame boundary. This is 60 seconds including training, not a
connected x2 soak. Endpoint reports are `asymmetric-analog.json` and
`asymmetric-quad.json`.

The final targeted DSP/Quad/media regression suite passes **369 tests**.

## Revalidation — 2026-10-19

Replaying the original caller host capture again finds 273 valid frames
before the first bad FCS at media frame 250. Replaying the PCM traces finds
exactly one inserted `ff` toward the caller (22,223 source samples matched),
and no reverse-direction slip (20,972 samples matched). The archived
60-connected-second high-rate reports still pass the current traffic verifier.

The pacing regression now exercises the actual `G711Peer` default, rather
than setting its frame-service flag explicitly in the positive control.
It covers 160- and 800-octet production packets as well as the four-octet
minimal reproduction, with both Python and native bearer queues. Each case
crosses three packet boundaries in one offline DSP catch-up pass. The
poll-only negative control still inserts idle while the native C5x FIFO
underrun counter stays zero; the default path preserves every sample.

Pacing, packet sizing and PCM inspection tests pass **22 tests**; the broader
targeted media, native-port, handoff and traffic selection passes **101 tests**.
This revalidation uses saved firmware captures and a fresh deterministic
scheduler probe, without claiming a new live firmware soak.
