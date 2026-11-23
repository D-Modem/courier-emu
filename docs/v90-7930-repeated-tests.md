# Repeated V.90-enabled calls to hardware 7930

## Result

**V.90 negotiates and can carry exact PPP payloads, but is not reliable in this
configuration.** Fourteen live calls were placed on 9–10 November 2026 UTC.
Six negotiated genuine V.90, three fell back to V.34, four failed acquisition,
and one worker failed before CONNECT. Only one call met the full acceptance
check: 60.011 seconds at `CONNECT 37333/ARQ/V90/LAPM`, authenticated PPP,
6/6 exact 512-byte echoes, no PPP FCS errors, SIP/carrier/PPP all up at the
bound. Even this pass had one granted retrain and 15 resent LAPM blocks.

No three-minute or ten-minute-target attempt passed. **None of the four
600-second-target calls actually established V.90**, so these are not four
completed ten-minute V.90 soaks. They failed earlier or fell back.

## Configuration and controls

* Emulator: vmhost, CT127, isolated `/root/courier-perf-followup` deployment.
* Destination: hardware extension **7930**, through Asterisk and the TopRouter
  BRI gateway. SIP account 2905, PCMA; no local/VPN-host calls in this series.
* Original analog Courier 403 supervisor/DSP firmware and `idsdl403` NVRAM
  fixture; board ID 7; 115200 8N1 DTE.
* AT command: `ATQ0V1X4S39=8S54=0S58=1&U0&N0&M5&K0DT7930`.
  `S58=1` allows V.90 and disables x2; V.34 fallback remains possible and is
  explicitly **not** counted as a V.90 success. LAPM required, compression off.
* Same 20-ms line blocks, media reserves, codec batching, packet recovery,
  service reentry, legal extra PPP control quoting, and 512-byte stop-and-wait
  ICMP echoes as the preceding tests. No timing/buffer/acceptance relaxation.
* No profiler, CAPI timing sampler, CPU pinning, or rejected SIP native-batch
  experiment was enabled. Ordinary disconnect/post-window ATI6/ATI11/ATI4 and
  passive LAPM tracing remained attached.
* Success requires genuine V.90, authentication, full target connected time,
  at least one exact echo, every echo completed/exact at the bound, zero PPP
  FCS errors, SIP/carrier/PPP still valid, complete DTE capture, successful
  worker exit, no execution error, no watchdog or cleanup failure. A pending
  final echo fails; no post-bound grace was added.

The first series placed all twelve planned calls: six 60-second targets,
four 180-second targets and two 600-second targets. Since neither long target
established V.90, a second series planned four additional 600-second targets.
It placed two calls, then the next preflight found the test account/destination
busy and **placed no call**. The extension was aborted; the last planned call
was not attempted. That blocked preflight is not included in the fourteen-call
denominator. The stale call subsequently cleared; no unrelated call was hung
up to make room.

The two series used identical source/build hashes. Container CPU affinity was
`[7,10,12,13]` on the first boot and `[1,9,10,13]` on the second. No affinity was
changed during either series; do not treat different boots as a CPU-only
performance comparison. Source/firmware/native-library hashes and host metadata
are retained with the captures. This was a dirty development snapshot, not a
claim about an otherwise clean git revision.

## Call outcomes

Times are connected wall seconds; a dash means no CONNECT. Rates are negotiated
CONNECT rates, **not measured sustained throughput**. Echo columns count only
the bounded data test, not the following AT diagnostics.

| Call | Target s | CONNECT | Connected s | Exact/sent echoes | Outcome |
|---|---:|---|---:|---:|---|
| 1 | 60 | 37333 V.90/LAPM | 60.011 | 6/6 | **Pass** |
| 2 | 60 | 31200 V.34/LAPM | 60.018 | 2/3 | V.34 fallback; one pending echo |
| 3 | 60 | 46666 V.90/LAPM | 23.607 | 0/0 | NO CARRIER; ATI6 **DISC Received**; no PPP authentication |
| 4 | 60 | 40000 V.90/LAPM | 60.012 | 3/4 | One pending echo; session still up |
| 5 | 60 | none | — | 0/0 | NO CARRIER; ATI6 **Unable to Retrain** |
| 6 | 60 | none | — | 0/0 | NO CARRIER; ATI6 **XID Timeout** |
| 7 | 180 | 41333 V.90/LAPM | 180.000 | 4/5 | SIP already closed; pending echo; not a valid end-to-end hold |
| 8 | 180 | 37333 V.90/LAPM | 35.664 | 0/0 | PPP: no response to Configure-Request |
| 9 | 180 | 21600 V.34/LAPM | 180.006 | 5/6 | V.34 fallback; SIP already closed; pending echo |
| 10 | 180 | 32000 V.90/LAPM | 122.148 | 0/1 | PPP echo timeout after SIP teardown |
| 11 | 600 | 31200 V.34/LAPM | 31.644 | 0/0 | PPP Configure-Request failure; RX-backlog exception during diagnostics; incomplete capture |
| 12 | 600 | none | — | 0/0 | NO CARRIER; ATI6 **Unable to Retrain** |
| 13 | 600 | none | — | 0/0 | NO CARRIER; ATI6 **No Connection**, no detailed reason |
| 14 | 600 | none | — | 0/0 | **TX-backlog execution exception** before CONNECT; incomplete capture |

Four of the six genuine V.90 connections authenticated PPP, but only call 1
completed all bounded checks. Do not confuse an authenticated connection or an
`Online` ATI response with successful sustained traffic.

## Failure evidence

* Call 3: gateway-to-PBX SIP BYE at **22.204 connected seconds**, Q.850 cause
  16; PBX forwarded it to the emulator at 22.216 s. Firmware NO CARRIER followed
  at 23.607 s and ATI6 reported `DISC Received`. This identifies the gateway
  side as the initiator of SIP teardown in this reproduction, not the original
  reason the far-end modem/RAS decided to clear.
* Call 7: gateway BYE at **152.961 s**, before the 180-s bound. The emulator's
  modem still reported online at the bound, while SIP was closed and PPP was
  not up. This is explicitly a failed connection, not a three-minute hold.
* Call 9: gateway BYE at **173.173 s**, again before the bound. Modem/PPP state
  alone would have falsely suggested the fallback call remained usable.
* Call 10: gateway BYE at **113.791 s**, preceding the host PPP echo timeout
  at 122.148 s. A PPP timeout here is not evidence that the PPP parser initiated
  the network teardown.
* Thirteen selected gateway captures contain RTCP report blocks; none reported
  RTP sequence loss. Call 14 has no selected receiver report: **unknown**, not
  zero loss. RTCP sequence loss does not measure gateway jitter-buffer
  concealment/discard or analog bit errors, and is not an end-to-end waveform
  integrity guarantee.
* Sender-side timing excursions remain substantial. Examples from bounded-test
  audit snapshots: call 1 74.8 ms; call 7 917.0 ms; call 10 653.8 ms; fallback
  call 11 1,652.2 ms. These are sample-clock lateness, not necessarily a single
  packet gap. No unique underlying cause is inferred from these maxima alone.
* Call 11 raised `SIP analog receive backlog exceeds queue capacity; emulator
  is not keeping up with live audio` during the post-failure diagnostic phase.
  Call 14 raised `RTP audio transmit backlog exceeds queue capacity; refusing
  silent sample loss`. Both are execution failures with incomplete final
  reports; neither is a clean modem-disconnect result. Neither buffer guard
  was weakened or bypassed.

Twelve of fourteen calls have validated complete DTE captures and normal final
reports; two do not. No call watchdog expired. The subsequent busy preflight
stopped the added series rather than overlapping another call.

## Artifacts and cleanup

Private artifacts:

* `.artifact-archives/v90-series-20261109-235100/` — calls 1–12.
* `.artifact-archives/v90-long-series-20261110-004329/` — calls 13–14 and the
  blocked preflight. Labels restart at 01 in this directory.

Each directory has `summary.json`, `summary.md`, a source/host manifest and
initial/final container state. Trial directories contain the PBX captures,
RTCP analysis, SIP teardown metadata and nested remote modem/PPP artifacts.
Raw captures and diagnostics remain private; SIP credentials were passed
through environment/stdin, not argv or written launcher configuration.

Reusable scratch launch/aggregation/post-analysis scripts are in
`tmp/v90-series/`; twelve aggregation regression tests pass, covering V.34
fallback, short duration, missing authentication, pending/bad payloads, FCS
errors and missing final capture. Acceptance did not change during post-analysis.

Both runs restored CT127 to **stopped**. Test capture processes ended; final
PBX inspection found no remaining call or tcpdump process. No PBX configuration,
existing deployment or unrelated call was altered.
