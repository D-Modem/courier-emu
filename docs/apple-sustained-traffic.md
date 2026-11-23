# Apple/SIP sustained binary traffic: validator implemented, link still fails

The firmware-hook seizure fix remains valid. The two earlier exact 180-byte
V.32/LAPM exchanges did **not** establish sustained reliability. Longer tests
now reproduce long, asymmetric stalls with substantial real firmware LAPM block
errors/retransmissions. There is no passing 60-second binary soak or BER claim.

## Harness

`tools/probe_apple_sip_traffic.py` makes **one** bounded call to the established
2903 receiver. It waits for real setup `OK`, PBX reachability and both firmware
`CONNECT` results. It never writes carrier/results, decoded bytes, ACKs, RAM or
PC state, and never redials. Modulation is V.32/9600 with required LAPM and no
compression; the separate RTP deadline and bearer reserve are both 200 ms.

Each direction is paced independently by observing its actual far-end DTE:
only one application record per direction may be outstanding. Binary records
have a role/sequence/length header, 256 payload bytes, and CRC32. Every body
contains **all 256 octets**, with a changing permutation. This is bounded record
traffic, not a maximum-throughput benchmark. The ASCII control uses deterministic
hexadecimal bodies of the same payload size.

The measured interval is parent monotonic wall time, starting 0.5 seconds after
both CONNECT results. New sends stop at its deadline; outstanding records have
at most five further seconds to drain. Passing requires:

- the complete requested interval (1..120 seconds);
- at least ten complete records each way, with no inter-record/initial/final gap
  over five seconds in the measured interval;
- exact regeneration of both saved sent streams and byte-for-byte equality of
  each complete received stream, including its tail;
- event-log agreement with timing, counts, and one-outstanding-record pacing;
- successful process exits, no CPU/DSP/line errors, 8N1, no UART overruns/output
  drops, no active USB sample loss, and no reported RTP playout discontinuities;
- independent final on-hook and enabled-protection readback.

These are acceptance gates, not proof of a particular root cause when they fail.
The full-run RTP counters include post-window diagnostics/teardown; a nonzero
counter conservatively fails the run but cannot, alone, locate its time within
the measured interval. Captured RTP continuity also does not prove reception at
an uncaptured ATA endpoint, nor physical analogue signal quality.

### Binary-safe console

`isdn-run --terminal --terminal-binary` is an explicit raw pipe mode. It disables
local echo, LF-to-CR translation, ASCII replacement and Ctrl-] detach. The
firmware must use 8N1 for eight-bit transparency. EOF stops the run. Ordinary
interactive/text terminal behavior is unchanged. Firmware escape/flow-control
semantics remain firmware behavior: the test explicitly sets `&I0` and standard
`S2=43`, rather than treating control characters as terminal escapes.

The ordinary 403 AT command buffer is bounded. Combining every setting and
dial into a 66-character line produced real firmware `ERROR` before any seizure.
The harness now uses a short binary-control setup followed by the same complete
modulation-plus-dial transaction as the successful short-call control. All AT
lines are checked to remain below 64 characters. Offline tests run the actual
403 AT parser against an explicitly silent PCM peer, without USB or a phone line.

### Diagnostics and safety

After freezing the traffic/drain outcome, the harness may use guarded `+++`
and then `ATI6`, **only after observing the real firmware escape `OK`**. Diagnostic
output, including any late data, is saved separately; it cannot repair a failed
window or missing tail. This also works after a failed drain, when counters are
most useful. A post-carrier-loss query is attempted separately; this was not
reliable on the I-modem and is not used to claim success.

Known sibling Apple modem processes are checked before opening USB; no other
process is stopped or detached. This is advisory, not a cross-project lock.
Exclusive libusb interface claiming is the remaining race-safe gate. The native
helper now identifies configuration/claim failures instead of returning a silent
status failure. Arrange exclusive device use for a measurement series.

## Running and independently checking a test

Use a **new private output directory**. Start with a 20-second control; do not
promote a failed control into a nominal 60-second result:

```sh
.venv/bin/python tools/capture_apple_sip.py \
  --run-call --traffic-seconds 20 --traffic-binary \
  --remote-peer <actual-ATA-media-IPv4> \
  --output .artifact-archives/apple-binary-NEW
```

Omit `--traffic-binary` for the ASCII control. Once the control genuinely passes,
use `--traffic-seconds 60`. With no traffic option, the capture runner keeps its
previous short-call behavior. The standalone traffic launcher uses `--seconds`
and `--binary` but does not itself take dual packet captures.

`--remote-peer` broadens **only the PBX capture** to include the actual ATA media
leg; it is repeatable. Local capture remains limited to PBX traffic. Do not infer
the media endpoint from an old README or unrelated SIP contact. In this series,
the received INVITE identified AudioCodes **6314**, and the correct peer was
`10.69.70.221`. An initial attempt using historical 6004's address captured the
wrong extra leg and is **not** evidence of actual ATA-leg coverage.

Independently replay payload and timing checks, without hardware:

```sh
.venv/bin/python tools/apple_traffic.py .artifact-archives/apple-binary-NEW/call
```

This checks only saved payload/timing evidence, not all USB/UART/process/capture
health gates. The full runner result is `call/traffic-verification.json`;
`outcome.json` contains capture-drop and independent cleanup evidence.
`traffic.json`, `events.jsonl`, `*-sent.bin`, `*-received.bin`, raw `*-dte.bin`,
firmware diagnostics and PCM/G.711 traces are retained privately.

Extract both pcaps with `../v90modem/tools/eicon_rtp_pcap_check.py`, compare common
streams with `tools/compare_rtp_captures.py`, and audit forwarding/DSP TX using
`tools/audit_apple_rtp.py`. Check zero kernel capture drops before attributing
absence. A PBX egress capture is **not** a capture at the remote ATA's receiver.

## Live findings

All evidence below is private under `.artifact-archives/`:

| Run | Actual outcome |
| --- | --- |
| `apple-binary-traffic-20s-20261024` | 66-character AT line rejected; no dialing or payload. |
| `apple-binary-traffic-20s-split-20261024` / `...split-recheck...` | USB ownership/status gate blocked; no call. |
| `apple-binary-traffic-20s-ready-20261024` | Setup accepted, genuine NO CARRIER; no sustained result. |
| `apple-binary-traffic-20s-canonical-dial-20261024` | Real V.32/LAPM; Apple → I-modem delivered 420/542 record bytes, exact prefix, then failed drain. Reverse delivered all 3794 queued bytes; measured gaps still failed. Zero USB loss and RTP missing/late counters. |
| `apple-ascii-traffic-20s-control-20261024` | Other modem experiment owned USB; no call. |
| `apple-ascii-traffic-20s-both-legs-20261024` | Genuine NO CARRIER. Extra-peer filter selected the wrong historical ATA; not actual ATA-leg coverage. |
| `apple-ascii-traffic-20s-audiocodes-leg-20261024` | Both CONNECT; measured Apple → I-modem only 3 records and 6.8-s maximum gap. All 1100/6875 queued record bytes eventually delivered exactly. Timing/record-count gates failed; no binary-specific explanation. Actual AudioCodes leg captured. |
| `apple-binary-traffic-20s-link-diagnostics-20261024` | Failed final drain. At this stage pre-hangup diagnostics were skipped on drain failure. Both local/PBX RTP streams matched, zero USB loss and RTP missing/late counters. |
| `apple-binary-traffic-20s-failed-window-diagnostics-20261024` | Failed final drain; actual guarded diagnostics obtained on both modems, separately from traffic evidence. |

In the last run, real `ATI6` reported:

| Counter | Apple/Courier | I-modem |
| --- | ---: | ---: |
| Blocks resent | 52 | 1 |
| BLERs | 16 | 74 |
| Link timeouts | 2 | 1 |
| Retrains requested / granted | 0 / 1 | 1 / 0 |

These are firmware diagnostic counters, **not** an independently measured BER.
They support substantial error recovery/retraining, rather than a terminal
normalization explanation. Their octet/character counters are not substituted
for the separately captured exact DTE streams.

For that last run, 2770 local → PBX and 2776 PBX → local packets matched exactly
at both zero-drop capture points. Both directions were also forwarded unchanged
on the AudioCodes leg at the PBX. The DSP TX source matched captured outgoing
payloads. USB active input-overflow/output-gap counters remained zero. Final
full-run RTP counters additionally showed 12 late packets / 1920 missing samples;
their position relative to traffic/diagnostic/teardown phases was not separately
traced, so do not claim zero playout loss for this run. Earlier stalled binary
and ASCII controls had zero full-run playout loss.

Independent release/protection readback after the last owned call was
`hook=8, status=64, auxiliary=2, protection_register=12, termination_register=0`.
No OPD protection, current threshold, gateway/PBX configuration or line gain was
changed. No automatic retry loop was added.

## Follow-up: phase telemetry and PCM scheduling

The receiver now runs through `tools/apple_traffic_telemetry.py`. A separate
inherited socket requests read-only snapshots at readiness, pre-dial,
pre-traffic, traffic end, pre-diagnostics, after each modem's diagnostics and
post-hangup. No request/response uses the DTE, SIP or RTP. Snapshot IDs, monotonic
request/response bounds, counter monotonicity and bounded message sizes are
checked; telemetry failure fails the run, not silently supplies zero counters.
`media-telemetry.json` and the verification report contain interval deltas.
The pre-traffic snapshot precedes the 0.5-s warmup, so that interval is a
conservative superset of measured traffic, not an exact sample-level boundary.
The drain status is now frozen **before** diagnostics, rather than accidentally
including their elapsed time in its open-gap statistic.

The new `apple-binary-traffic-phased-20261024` control still stalled with real
block errors, but all observed playout intervals were clean, including traffic,
drain, diagnostics and teardown. Snapshot RPC round trips were 0.11–0.38 ms.
Thus the previous run's 12 late packets are not a necessary explanation for
these stalls. This does not retroactively locate those older packets.

Exploratory fits of saved PCM found a stable local TX-echo delay around
**217.75 ms** with 512-frame HAL buffers. A 128-frame experiment reduced the
observed delay to **65.625 ms**. These are offline waveform-alignment results,
not calibrated SNR, BER, or proof that echo delay causes the stalls. Constant
clock-offset fitting also materially improved the Apple-TX/ATA waveform fit;
no clock correction or gain change was applied to live audio.

### Experimental asynchronous status monitoring

The low-buffer experiment exposed a separate, concrete scheduling defect:
`apple-binary-traffic-buffer128-repeat-20261024` recorded a **55.252-ms USB status
poll**, longer than its approximately 25-ms output cushion. The existing strict
underrun guard correctly stopped the call; independent readback verified release
and protection. The silence/retune probe alone had not exposed this load case.

`APPLE_LINE_ASYNC_STATUS=1` now explicitly selects an experimental native status
worker. Ordinary status reads are requested/coalesced without blocking the PCM
producer. The same USB mutex serializes whole status polls and hook transitions.
Seizure/priming checks remain synchronous and mandatory. Bad status/OPD sets the
fatal flag, mutes output, and immediately requests physical release; cleanup
joins the worker before closing USB. The memory-only selftest deliberately
blocks a mocked USB read, exercises the actual producer dispatcher and HAL
callback, then injects an OPD sample and checks release, retained protection and
silence. This is not a live overload experiment.

The monitor remains **opt-in**. The default HAL size remains unchanged. Smaller
buffers are **not recommended as a proven reliability fix**: even with async
monitoring, 128-frame calls still had high BLERs and occasional active underruns.
The `...buffer128...`, `...buffer128-async...` and `...explicit-finish...` archives
retain those failures. Native buffer sizes and monitor selection are recorded
in `transport-settings.json`; the 320-second frame backstop is now scaled to the
5-ms service cadence instead of unintentionally shrinking to 80 seconds.

### Explicit physical finish before reporting

A stopped CPU previously stopped supplying PCM before DSP snapshots and JSON
reporting, but left the helper off-hook until later cleanup. With a small
cushion this could produce a teardown underrun. `AppleLine.finish_stream()` now
sends an actual zero-length release/reset control after final native IO flushing
and **before** slow reporting. It does not patch guest state or forgive an
existing underrun. The helper also mutes on explicit stream end, and physical
release precedes HAL teardown/restoring buffer size. Unit and offline CPU tests
verify release ordering and propagation of previously recorded callback failures.

A final 20-second control, `apple-binary-traffic-default-buffer-finish-20261024`,
used the unchanged **512-frame buffer with the experimental monitor enabled**:

- both processes exited 0, no CPU/line errors;
- 385 asynchronous status polls completed; zero active output gaps/input overflow;
- native log: `PCM stream ended: failed=0 active output gaps=0`;
- all measured playout phase deltas remained zero;
- physical line was already on-hook in the caller report, before process cleanup;
- independent final readback: hook 8, protection 12.

It **still failed traffic acceptance**: Apple → I-modem completed only 3 records
in the window with an 8.86-s maximum gap, and its final tail did not drain.
The reverse direction completed 27 records with a 0.85-s maximum gap. This is
verified transport/lifecycle progress, **not** a passing sustained modem call.
No 60-second or BER certification is implied, and the original failure gates
remain unchanged. The two zero-drop captures matched all 2627/2633 common RTP
packets; the matching AudioCodes forwarding streams were unchanged, and captured
outgoing RTP matched the saved DSP TX source.

A final isolated level control, `apple-binary-traffic-postdial-half-20261024`,
kept the 512-frame buffer/monitor setup and reduced **only post-dial** TX gain to
0.5 (DTMF remained unity). It also failed: one complete Apple → I-modem record
in the measured window, an 11.15-s gap, and 135 I-modem BLERs. This is not evidence
that simple attenuation fixes the link; unity remains the default. Future
`transport-settings.json` files also record/validate the selected post-dial gain.
The earlier `...explicit-finish...` low-buffer run failed with a genuine active
underrun before its traffic window; it was not reclassified as shutdown success.

A separate software-only direct-PCM isolation attempt is retained under
`apple-v32-direct-pcm-isolation-path-20261024`. It did not CONNECT, so it provides
no passing comparison that would isolate USB/ATA from native DSP behavior. The
preceding `...direct-pcm-isolation...` attempt failed a Python import before
starting the control. Neither attempt opened USB or made a PBX call; no
conclusion about the physical link is inferred from them.

The final focused regression selection passed **178 tests**, including the
memory-only native monitor/OPD tests, binary transport, phase RPC, physical
finish error propagation and existing RTP/SIP/media-clock controls. This is not
a claim that the entire repository test suite was run.

## Endpoint-delivery follow-up

The separate [7910 training investigation](apple-7910-training.md) found actual
**ATA-reported incoming RTP loss**, corroborated by packet-sized corruption in
Apple hardware RX. Clean PBX forwarding and clean USB/local receiver playout
counters did not establish delivery to the ATA. One instrumented 7910 call
reached 177 packets reported lost by the last endpoint RTCP report, with interval
loss typically 6–8%. These are endpoint loss reports, not BER.

Use `tools/analyze_rtcp.py` on each saved capture, scoped to the actual ATA RTCP
port and reported RTP SSRC. Missing reports mean **unknown**, not zero loss.
Historical traffic captures also contain positive ATA loss reports; the
`ata-rtcp-inventory.json` files retain those observations, but multi-call captures
must first be scoped to the selected call before drawing conclusions. The loss
rates differ between attempts; the 7910 rate must not be assigned to older runs.
This finding does not prove packet loss was the sole cause of every stall.

A subsequent user-authorized switch repair restored IGMP querying on VLAN 70,
stopping unrequested IPTV multicast from flooding the ATA's shared branch.
One unchanged automatic 7910 verification call now reaches **CONNECT
19200/ARQ/V34/LAPM/V42BIS**, with **eight actual ATA RTCP reports showing zero
loss**, zero USB active gaps/overflows and verified physical release. The switch
configuration was saved after checking that no unrelated functional changes
would be saved. Details and the IOS per-VLAN guard ordering caveat are in the
linked diagnosis. This is one connection plus a ten-second receive listen,
**not** a passing 20-second arbitrary-binary duplex gate or V.90 qualification.

Future acceptance must include endpoint delivery evidence, not merely PBX
payload equality. If loss recurs, capture ingress at the ATA before attributing
remaining failures to the emulator's datapump.

## Next investigation

Resolve the analogue/datapump/link-error path and localize any new playout
anomalies by phase, using firmware diagnostics and both correctly selected media
legs. Captures so far clear the observed forwarding paths, not the entire
network or analogue channel. Only after the 20-second gates pass should the
60/120-second binary, drift and throughput series be claimed validated.
