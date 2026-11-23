# Quad traffic and asymmetric x2 — 2026-10-18

**Update:** the high-rate corruption was traced to a packet-boundary PCM
sample insertion and fixed in media scheduling. The original failed captures
below remain unchanged. See [PCM slip fix and verified high-rate traffic](pcm-slip-fix/README.md).

## Asymmetric server: verified short-data control

`asymmetric-server/summary.json` passes the strict x2/data, retained-carrier,
execution-health and shared-duration checks in `tools/probe_quad_analog_pair.py`.
Original endpoint reports are `analog-result.json` and `quad-result.json`.

| Endpoint | Original CONNECT | Result |
|---|---|---|
| Analog Courier client | `52000/ARQ/x2/LAPM` | `QUAD-TO-ANALOG-731954` intact |
| Digital Quad server | `33333/ARQ/x2/LAPM` | `ANALOG-TO-QUAD-482619` intact |

Both stop at line frame 3000, 20 ms per frame: 60 seconds **including startup
and training**, not a 60-second connected soak. Both remain online, with no
CPU/DSP errors. Quad PCM underruns/UART overruns and the analog connected
receive-underrun counter are zero. The analog aggregate codec counter retains
149 startup empty frames; these are not erased or mislabeled as connected loss.
QF selects `8954=01`, and its original DSP status changes `895f=0007 -> 00ff`.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_analog_pair.py \
  --check-x2 --output /tmp/quad-asymmetric
```

The server uses genuine chassis feature provisioning `01f2=20`, acknowledged
AT configuration `Q0V1&A3&B0S76=133S81=32`, and chassis answer after an actual
analog caller rings. The analog client uses the captured 403 ROM with
`ATX1S27=1S58=48&M5&K0DT5551234`. The media adapter reuses the existing
calibrated exchange codec and line levels, with one 20-ms transit reserve.
No modem flags, payloads, firmware instructions or receive callbacks are forced.

`digital-role-controls/` preserves failed forced-asymmetric Quad/I-modem
controls at 100 and 20 ms. Both retain `895f=013f` and fail x2/data checks.
The changed delay alone is not the fix. Vendor documentation names both as
server-family products and explicitly states the Quad does not support client
mode. The successful asymmetric test uses a real analog client; symmetric
x2 remains the proper working control for the two digital endpoints.

This is short ASCII data evidence, not sustained asymmetric throughput,
binary interoperability, or an implemented Quad client personality.

## Original sustained V.34 failure (before the PCM fix)

`v34-stall/summary.json` is deliberately **not** a passing traffic report.
The 30-second diagnostic uses 64-character bodies in 83-byte numbered
records. The 180-second attempt with 16-character bodies reproduces a stall
as well, so the default-rate multi-minute acceptance target remains unmet. The probe
fails early after five bearer seconds without a complete receive record.
The lower-rate 180-second control below does pass.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --traffic-seconds 180 --traffic-size 64 --trace-data-lanes \
  --check-connect --output /tmp/quad-soak
```

The saved 64-character control has genuine 31200/33600 V.34 CONNECT results,
retained Quad carrier, zero PCM underruns, zero UART overruns, and no CPU/DSP
errors. Nevertheless Quad receives only four complete caller records (332
bytes), and the caller receives three complete Quad records plus an 11-byte
prefix (260 bytes). UART reception remains enabled, no unread character is
stuck, all queued Quad input is consumed, and the caller's normal `46cc` data
callback remains installed. Progress snapshots retain these observations.

The compressed `quad-data-lanes.json.gz` is the bounded raw CPU/DSP bank
capture. `hdlc.json` is offline analysis, reproducible with:

```sh
PYTHONPATH=. .venv/bin/python tools/inspect_quad_hdlc.py \
  artifacts/quad-traffic-and-asymmetric-x2-20261018/v34-stall/quad-data-lanes.json.gz \
  --output /tmp/quad-hdlc.json
```

After detection, the interface carries framed octets rather than raw bits:
RX `1000` terminates bytes including received FCS; TX `10f3` terminates bytes
for which the DSP supplies flags, stuffing and FCS. The inspector verifies
279 received FCS values. It does **not** pretend to verify a TX FCS that the
host capture does not contain.

The Quad emits 275 single-character I-frames. The caller stops advancing at
N(R)=4 after sequence wrap, leaving 15 outstanding frames N(S)=4..18. RR
poll/response traffic continues. This explains the full LAPM transmit window;
it does not by itself identify why the caller ceased acknowledging. The strict
checker correctly rejects the run despite CONNECT and some intact data.

The second capture additionally records the caller's DSP output. Its Quad
bank capture is byte-identical to the first (SHA-256
`97f84e079efd872c352f9d91297378da9fb25d1204f9ce6f0359b9136ef3c5c3`).
`imodem-data-lanes.json.gz` and `imodem-hdlc.json` show **273 FCS-valid frames
(260 I, 13 RR), then corrupted frames beginning at media frame 250**. This is
already present in the caller DSP's host output, before its supervisor LAPM
receive processing. No DTE handoff reset or new DSP mode command explains the
transition. Next investigate the high-rate V.34 signal/receive path, not an
injected LAPM acknowledgement.

The I-modem uses `ff00`, rather than Quad `1000`, as its framed-RX delimiter:

```sh
PYTHONPATH=. .venv/bin/python tools/inspect_quad_hdlc.py \
  artifacts/quad-traffic-and-asymmetric-x2-20261018/v34-stall/imodem-data-lanes.json.gz \
  --rx-delimiter 0xff00 --output /tmp/imodem-hdlc.json
```

## Three-minute lower-rate traffic control

`v34-9600/180s-verification.json` passes the full **180 connected seconds**
at 9600/V.34/LAPM. Both original terminals report 9600/ARQ; the caller also
prints V34/LAPM. In-window receive counts are 70 records at the caller and
71 at Quad. After the real short drain, both receive **71 complete records
(5893 bytes) each**, with a 59-byte prefix of the next Quad record still in
flight at the caller. There are no corrupt records, UART losses, PCM
underruns or CPU/DSP errors. Maximum receive gaps are 4.1 and 2.9 seconds.
These are deliberately paced records, not a negotiated-rate throughput test.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --settings 'S54=0S58=43&M5&K0&N6' \
  --traffic-seconds 180 --traffic-size 64 --quad-dsp-slice-cycles 512 \
  --check-connect --output /tmp/quad-9600-soak
```

The 512-cycle optional runtime batch preserves cycle debt and PCM sample
yields; boot/download windows keep their existing 64-cycle batches. The
30-second control below uses the original 64-cycle runtime batches.

### Corrected end-of-window accounting

The initial checker incorrectly compared counts from two different window
ends: caller CONNECT was at frame 155, Quad at frame 170. Thus their 180-second
snapshots end at frames 1955 and 1970. Comparing Quad's 72 queued records
against the caller's earlier snapshot of 70 falsely called two records lost.
The full, untruncated caller UART capture actually contains 71 complete records
and a valid prefix of record 72; only one record is in flight. No bytes or
snapshots have been changed to produce that result.

`180s-initial-summary.json` deliberately preserves that initial false
rejection. `180s-imodem.json` and `180s-quad.json` are the original worker
reports, not rewritten results. The corrected verifier checks timing and
health from the original window snapshots, and record conservation against
the actual UART drain. Future workers stream this drain directly; for these
historical reports it replays the full captured UART output offline. The
same one-final-in-flight rule still applies; missing records, corrupt
prefixes and truncated captures have rejection regressions.

Recheck without running or modifying either modem:

```sh
PYTHONPATH=. .venv/bin/python tools/quad_traffic.py \
  artifacts/quad-traffic-and-asymmetric-x2-20261018/v34-9600/180s-imodem.json \
  artifacts/quad-traffic-and-asymmetric-x2-20261018/v34-9600/180s-quad.json \
  --output /tmp/quad-180s-verification.json
```

### Live streamed-drain regression

`10s-streamed-drain-summary.json` is a fresh successful run of the corrected
worker/checker path, not an offline reclassification. Both modems negotiate
9600, both complete the ten-second window, and streamed UART drain accounting
verifies 29 records at the caller and 28 at Quad, with no partial records or
corruption left in either parser. This uses 16-character bodies, runtime
slice 512 and online byte spacing 10000. The original reports are saved
beside the summary. It validates the new drain path and configurable online
pacing; the three-minute stability evidence above uses the original slower
100000-instruction online spacing.

### Original 30-second control

`v34-9600/30s-summary.json` passes 30 connected seconds at **9600/V.34/LAPM**,
selected by the original caller AT setting `&N6`. Quad receives 12 intact
records (996 bytes); the caller receives 11 (913 bytes), with one final
in-flight record allowed. Both retain carrier, no record corruption occurs,
and UART/PCM/CPU/DSP health checks pass. This is a deliberately paced traffic
test, not a 9600-bps application-throughput measurement.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --settings 'S54=0S58=43&M5&K0&N6' \
  --traffic-seconds 30 --traffic-size 64 --check-connect \
  --output /tmp/quad-9600-control
```

Before the PCM scheduling fix, increasing online host pacing tenfold
(`--quad-online-byte-interval 10000`) delivered more data but still stalled.
Pacing alone was not the fix; the corrected 60-second high-rate control is
archived under [pcm-slip-fix](pcm-slip-fix/README.md).
