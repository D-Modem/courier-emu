# SIP receive reserve must cover the paced exchange block

## Reproduced defect and correction

`SipLine.service()` paces a whole caller block (normally 800 samples / 100 ms
at the 8-kHz line rate). `LineExchange.service()` then renders it in 80-sample
slices to resolve DTMF and call-state transitions. Those slices are rendered
back-to-back, without waiting for another wall-clock block.

Previously `_peer_samples()` primed against its own slice size plus the
320-sample receive reserve. Just 400 queued samples could therefore start
playback inside an 800-sample service call: the waveform started and then ran
out **within that same call**. Tests that called `_peer_samples(800, ...)`
directly did not exercise this.

`SipLine` now passes the enclosing service-block size to the receive priming
check. It requires a full paced block plus reserve, not one render slice plus
reserve. The transient context is cleared in `finally`, including exceptions.
Direct helper calls still use their requested count, and explicit zero-reserve
and offline-peer behavior is unchanged.

No timer, gain, modulation setting, carrier result, PCM content, or RTP loss
accounting was changed. Startup may wait longer: preserving the beginning of
the answer waveform is preferable to starting it and inserting a hole halfway
through the first block. This does not promise uninterrupted audio under a
real shortage or long CPU/OS stall.

## Regression coverage

`tests/test_analog_sip_receive_reserve.py` now includes tests through the
**actual segmented LineExchange service**, with identity resampling and mocked
wall-clock pacing only:

- 400 samples initially queued for an 800-sample service call: retain all 400,
  return startup silence, then deliver the exact waveform once primed;
- a two-minute jitter stream through real exchange slicing, exact input/output
  accounting, no active underruns and no receive rebuffering;
- a real outage followed by a whole-block reserve rebuild;
- exception cleanup of the transient service-block context.

The existing direct-helper, capacity, offline, zero-reserve and new-call tests
remain. See the receive-clock note for the broader focused test command.

## Live checks and limitations

Evidence is private at
`.artifact-archives/analog-sip-7900-7910-20261102-111919/`:
commands, process results, full JSON reports, PCM TX/RX WAVs, pre/post channel
snapshots and `summary.json`. These use the same bounded 150-million-instruction
403/S39=8 calls as the previous checks. No PBX configuration was changed.

| Observation | 7900 | 7910 |
| --- | ---: | ---: |
| Total process time including startup/dial | 44.06 s | 45.74 s |
| Modem carrier / online mode observed at end | off / false | off / false |
| DTE bytes received/transmitted | 0 / 0 | 0 / 0 |
| Adapter active silence-fill samples | **0** | 883 |
| Adapter receive rebuffer events | **0** | 1 |
| Adapter startup silence-fill samples | 1600 | 2400 |
| Adapter pending peak | 2802 | 15547 |
| RTP late packets | 2 | 9 |
| RTP missing samples | 320 | 2400 |
| RTP sequence-gap events | 0 | 2 |
| Largest local receive-service interval | 64.64 ms | 190.19 ms |
| Largest transmitted RTP packet interval | 147.06 ms | 649.13 ms |
| TX rebuffer events | 1 | 5 |

Both processes exited normally with no reported CPU/DSP/media error and both
test calls cleared. Neither demonstrated modem CONNECT within the window;
serial result text was empty, not a captured final modem NO CARRIER result.
These are not successful sustained modem calls or throughput/BER tests.

The 7900 adapter result is encouraging, but RTP playout and TX discontinuities
remain. The 7910 adapter came close to its two-second backlog bound and had
substantial host/service/TX stalls. These are separate calls under varying
conditions, not a controlled A/B. Lower late/underrun counts must not be
extrapolated into longer-connect reliability.

Next localize the remaining host/native execution and TX production pauses
with timestamped service/codec telemetry and packet capture. Independent
packet-arrival evidence is still needed to distinguish delivery jitter from
late local servicing. More buffering alone is not a demonstrated solution.
