# Independent SIP RTP receive servicing

## Change

When `SipSession.enable_media_clock()` is used, its existing media worker now
services **both receive playout and transmit packet deadlines**, at a maximum
nominal sleep of 5 ms. Previously only TX ran independently; RTP reception
and playout ran inside the emulator's `poll()`. A CPU service stall could leave
on-time datagrams in the socket until their RTP deadlines had passed.

Only the worker consumes RTP when enabled. SIP signalling stays on the calling
thread. Sessions without a media worker retain synchronous RTP polling. The
same reentrant lock protects receive socket/playout state, queue handoff,
stream reset and media status snapshots. Close stops/wakes and joins the
worker before closing sockets.

No change was made to the 60-ms RTP playout delay, packet timestamp handling,
missing-sample filling, carrier detection, firmware, codec, gains or PBX.
Independent servicing is still subject to OS scheduling and Python/GIL stalls;
this is not a hard real-time receiver or a separate native process.

## Bounded queues and errors

The worker-to-emulator receive queue is limited to 16000 samples (two seconds).
It fails explicitly rather than silently discarding old audio. The analog
`SipLine` handoff queue is also bounded: normally two seconds at its line rate,
or enough for a larger explicitly configured reserve plus one second. This
second bound matters because draining the worker queue into an unbounded
adapter queue would merely relocate the latency/backlog.

Socket/playout/capacity failures stop the media worker, set the session error,
and propagate on subsequent poll/send/receive calls. They are not reported as
clean audio. New status fields include:

- `rtp_rx_queued_samples`, `rtp_rx_capacity_samples`;
- `rtp_rx_max_service_gap_ms`: largest local receive-service interval during
  active/setup media states, cumulative across calls (idle time excluded);
- `rtp_media_error`;
- adapter `receive_capacity_samples` and `receive_error`.

Service-gap timing is not kernel packet-arrival timing and does not alone
prove whether an individual late datagram was delayed by the network or host.

## Tests

105 focused tests pass:

```
.venv/bin/python -m pytest -q \
  tests/test_sip*.py tests/test_rtp*.py \
  tests/test_analog_sip_receive_reserve.py tests/test_bearer_sip_playout.py \
  tests/test_line_presend.py tests/test_bridge_acquisition.py \
  tests/test_resample_rate_changes.py
```

New local UDP tests exercise exact codeword and decoded-audio reception with
no emulator polls/consumption and no queued TX. They also exercise ownership,
queue overflow/error propagation, socket failure, stream reset, worker close,
and service-gap telemetry. The analog queue-limit test retains already queued
samples and requires explicit failure. These are not modem throughput tests.

## Live Asterisk checks: no sustained-connect qualification

Calls used the original captured 403 ROM, the analog `SipLine` path, account
6000, factory S39=8, and automatic modulation selection to 7900/7910. Preflight
checks avoided the shared trunk/test account when occupied. PBX configuration
was not modified, and unrelated calls were not interrupted. The peer behind
each route was not independently instrumented in these checks.

The initial pre-worker bounded checks are retained at
`.artifact-archives/analog-sip-7900-7910-20261102-083639/`. An intermediate
worker-enabled pair is at `...-084339/`. The intermediate 7910 run accumulated
100315 samples in the then-unbounded adapter queue, motivating the adapter
capacity check. That run was not clean and is not a passing result.

Final-source bounded checks are at
`.artifact-archives/analog-sip-7900-7910-20261102-084822/`, including raw reports,
TX/RX WAV files, commands, process timing, channel snapshots and `summary.json`:

| Final-source observation | 7900 | 7910 |
| --- | ---: | ---: |
| Total process wall time, including startup/dial | 43.92 s | 43.92 s |
| SIP answer | 200 OK | 200 OK |
| Modem carrier / online mode at end | off / false | off / false |
| Received/transmitted DTE data bytes | 0 / 0 | 0 / 0 |
| RTP late packets | 14 | 17 |
| RTP missing samples | 2240 | 2720 |
| RTP sequence-gap events | 0 | 0 |
| Maximum local receive-service gap | 28.53 ms | 27.55 ms |
| Adapter active silence-fill samples | 420 | 6922 |
| Adapter rebuffer events | 6 | 66 |
| TX rebuffer events | 1 | 0 |
| Adapter backlog peak | 2190 | 8080 |

Both processes exited 0, without reported CPU/DSP/media errors. Neither reached
observed modem carrier or transferred data **within the bounded window**.
Serial result text was empty; no final NO CARRIER result was captured, so this
is not a completed modem-timeout measurement. Process duration is not connected
modem duration. Postflight checks showed no test-account/trunk channels left
active, while unrelated channels were preserved.

The pre-worker late counts were 13/144; final-source counts were 14/17.
These are separate, nonidentical calls, not a controlled A/B or proof of a
reliable live improvement. In particular, the 7910 adapter underruns remain
substantial. Local receive-service intervals below 30 ms also do not exclude
network/remote bursts or prove endpoint delivery. No 60-second continuous
payload gate, BER claim, or longer-connect success is established.

The subsequent [exchange-block priming investigation](sip-exchange-block-priming.md)
reproduces and corrects a full-block versus render-slice mismatch. Its latest
live checks still do not demonstrate modem CONNECT, but one 7900 call has zero
adapter active underruns. See that note for exact outcomes and limitations.
Remaining work includes actual packet-arrival timing, host/TX stalls and
training/peer evidence. Do not simply increase buffers or carrier timeouts to
reclassify these runs as success.
