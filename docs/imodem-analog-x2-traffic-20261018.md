# Analog x2 sustained traffic: 60-second gate fails

The analog Courier / I-modem pair can report x2 and exchange short markers,
but **does not yet pass sustained bidirectional traffic**. Full 60-second
native wallclock controls fail with compression enabled and disabled. The
three-minute soak was therefore not started.

The final test uses independently paced directions, one actual outstanding
record per sender, 512 deterministic payload characters plus a numbered
19-byte header/terminator. Every received character is checked. Complete
record streams also retain SHA-256 digests. Duration is measured in 100-ms
ticks derived from the actual 8-kHz line samples, starting at each complete
CONNECT result; instruction limits are ceilings, not duration measurements.

## Final independent-direction capture

[Verification](../artifacts/imodem-analog-x2-native-traffic-independent-60s-20261018/verification.json)
replays the original saved terminal bytes independently of the live traffic
checker. It confirms the declared complete-record counts, partial lengths
and complete-record hashes, then fails the sustained-traffic acceptance checks.

This final call's analog terminal reports 52000 and its I-modem terminal
reports 33333, both `x2/LAPM/V42BIS`. Those CONNECT labels do not by
themselves identify the directional rates; the
[Quad directional audit](quad-x2-v34-directional.md) demonstrates why the
server's 33333 must not be treated as a V.34 upstream speed.
Earlier full-window controls report 53333 at the analog terminal and
also fail. The 53333 target is consequently not established for sustained
traffic by this work.

| Direction | Complete records in 60 s | Verified payload bytes/s | Longest completed-record gap | Open receive gap at window end |
|---|---:|---:|---:|---:|
| Analog to I-modem | 2 | 17.07 | 27.4 s | 24.3 s |
| I-modem to analog | 14 | 119.47 | 0.8 s | 49.0 s |

Record-byte rates, including headers, are 17.7 and 123.9 bytes/s respectively.
The receivers also retain matching partial prefixes of 328 upstream bytes
and 119 downstream bytes. There is one incomplete outstanding record in
each direction. No captured complete record or partial prefix is corrupt,
but missing tails and long gaps fail the test. These are observed rates for
this bounded record test, not estimates of maximum application throughput.

Both calls remain answered and the analog peer remains off hook at the
measured boundary. There are no CPU/DSP errors, receive underruns, active
idle-fill samples, UART overruns or terminal output drops. Native counters
record zero writes into occupied DSP-to-host receive banks and zero changing
holding words across unacknowledged byte-read pairs. Peak native wall-clock
debt is about 48.05 ms over the call, including training; it is not a
traffic-window-only maximum.

After freezing the measured window and drain state, the probe escapes to
local command mode and reads the original firmware's ATI6:

```text
Blocks sent                 152      Blocks Received             180
Blocks resent                63
Blers                       623
Link Timeouts                10      Link Naks                     0
```

This is evidence of firmware-reported block errors, retransmission and
timeouts despite retained carrier. It does not identify the first bad bit,
or prove whether its cause is DSP execution, bitstream timing or supervisor
service. ATI6's `Current Call` is 33 seconds after the 60-second measured
media window; that discrepancy remains unexplained. The line-sample window,
not this legacy diagnostics field, determines the test duration.

## Focused implementation and controls

`tools/probe_imodem_analog_pair.py --traffic-seconds N` now attaches a live
serial descriptor to the existing analog worker and verifies both ordinary
DTE streams. No carrier, decoded bytes, firmware ACKs or guest state are
injected. The analog worker's UART status is included in its report.
Future captures also save `analog-dte.bin` and `imodem-terminal.txt`, so a
bounded diagnostic prefix does not limit live traffic or its saved evidence.

The traffic driver freezes each endpoint's health window independently,
allows two seconds to drain, records complete and open receive gaps, and
exits nonzero when verification fails. A gap over five seconds is recorded
immediately, but does not shorten the requested 60-second observation.
`--link-diagnostics` with traffic runs ATI6 only after freezing the window.

The parent knows both receivers' progress, so each sender now waits for its
own remote receiver. Earlier exploratory captures used the shared digital
pair helper's local receive count as a pacing proxy. On this asymmetric
call that coupled the directions and could permit two outstanding records.
Their byte-integrity and stall observations remain useful, but their rates
are not the final independent-direction benchmark.

Native observability now includes the peak wall-clock deficit, the number
of bounded advances, data posts, receive ACKs, byte reads, occupied-bank
writes and changed holding-word read pairs. Live data-window reads no longer
advance the DSP as a side effect: status reads and scheduler polls pace it.
A native regression shows why a large owed wall target must not execute a
later DSP send while reading an earlier held word. This removes an
independently reproducible read-side scheduling hazard, but **does not fix
the sustained-transfer stall**.

The initial read-pair observer in the exploratory `word-audit` capture did
not reset its pairing state at receive ACKs. Its nonzero count can include
pairs from different acknowledged words and must not be interpreted as a
strict count of corrupted CPU words. The final observer resets at each ACK.

Useful directories under `artifacts/`:

- `imodem-analog-x2-native-traffic-full-60s-20261018`: full 60-second,
  compression-enabled 53333 control; two upstream and one downstream records.
- `imodem-analog-x2-native-traffic-full-60s-k0-20261018`: full 60-second,
  compression-disabled 53333 control; one upstream record and a partial
  downstream record. Disabling compression does not resolve the failure.
- `imodem-analog-x2-traffic-offline-control-20261018`: instruction-clocked
  control also stalls, so the symptom is not exclusive to wallclock mode.
- `imodem-analog-x2-native-traffic-ati6-20261018`: short diagnostic control
  reports 149 BLERs before the final longer measurement.
- `imodem-analog-x2-native-traffic-independent-60s-20261018`: final independent
  streams, frozen health boundary, post-window ATI6 and replay verification.

## Reproduction

```sh
COURIER_LINE_FRAME_MS=20 PYTHONPATH=. .venv/bin/python tools/probe_imodem_analog_pair.py \
  --wallclock --traffic-seconds 60 --link-diagnostics \
  --analog-settings 'X1S27=1S54=0S58=48&A3&B1Q0&U26&N39' \
  --imodem-settings 'S54=0S58=48&A3&B1Q0' \
  --imodem-nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --instructions 2000000000 --analog-instructions 1000000000 \
  --output artifacts/imodem-analog-x2-native-traffic-new
```

Expected current outcome: a nonzero exit and an explicit failure in
`traffic-verification.json`. Keep the same five-second gap threshold when
repeating the test. Add `&K0` to both settings for the compression-disabled
control. The final capture's `verify.py` regenerates its failed
`verification.json` from saved bytes without running a call.

The focused native port, bearer/lookahead, serial, peripheral clock, traffic
and pair-probe selection passes **101 tests**. The next debugging boundary
is the first firmware-reported block error/ARQ stall, correlating the DSP
bit lanes with supervisor service and timer progress; increasing the soak
duration would not resolve the current failure.

The [26 October first-gap controls](imodem-x2-first-stall-20261026.md) add a
passive `first-stall.json` snapshot and three bounded local runs. Both 512-byte
controls deliver no complete upstream record in 20 seconds; disabling compression
and reducing records to 32 bytes do not pass the gate. Supervisor/timer progress
continues at the first five-second record-gap boundary, with no observed torn
words or occupied-bank writes. This captures a record gap, not the timestamp of
the first firmware BLER; the receive-error/CRC rejection path remains to locate.
