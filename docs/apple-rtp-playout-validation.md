# RTP playout validation and dual-capture live test

## Resolved: original-driver firmware hook operation

The seizure blocker below is now **fixed and verified in two captured V.32/LAPM
calls**, including a repeat on the final default build with no override. The
original Windows driver uses a dedicated interface-0 firmware hook command,
not the raw-register sequence we had reproduced on the host. Both calls deliver
all 180 payload bytes exactly each way, with zero active USB losses and zero
RTP playout loss/late samples. All RTP identities and payloads match between
local/PBX captures, with zero capture-kernel drops. The old intermittent network
loss did not recur in these calls; it is not claimed permanently repaired.

See [the firmware hook fix and original-driver evidence](apple-firmware-hook-fix.md)
for the corrected default, exact USB request, regression coverage and evidence.
The phase-isolation results below are retained as historical investigation,
not the current causal explanation or a recommendation to reorder HAL startup.

## HAL phase isolation follow-up (2026-10-23)

The diagnostic now supports `none`, `initialized`, `running` and `stopped`
HAL phases, with an explicit supported hardware rate (default 10286 Hz):

```sh
.build/apple_line --seizure-test initialized 10286
# Other explicit modes: running, stopped, none. Each makes at most one seizure.
```

`initialized` calls `AudioUnitInitialize` but does not start callbacks. `running`
requires actual duplex callbacks before seizure. `stopped` starts duplex,
requires real callbacks and stops the unit before seizure without disposing it.
The regular PCM helper still uses its existing startup path; no lifecycle
workaround has been applied. All modes retain OPE, current thresholds, normal
termination, bounded settling and fail-closed release. No mode dials.

One hardware attempt in each phase, all at **10286 Hz / 512-frame HAL blocks**:

| Phase | Callback totals (input / output) | Result | Last status / aux | Transition elapsed / re-arm |
| --- | ---: | --- | --- | --- |
| Initialized, never started | 0 / 0 | Pass, all ten settling polls | 47 / 00 | 630.013 / 53.140 ms |
| Running | 7168 / 7168 | Pass, all ten settling polls | 47 / 00 | 623.968 / 46.567 ms |
| Started, then stopped | 512 / 512 | OPD at first settling poll | 45 / 01 | 102.117 / 40.233 ms |

Every attempt released the hook and restored protection; independent final
readbacks confirmed on-hook/protection **0c**. Initial termination **00** and
counter **20** were unchanged. Evidence:
`.artifact-archives/apple-hal-seizure-20261023-215611/`.

**This falsifies the simple explanation that running CoreAudio alone always
causes OPD.** It does not establish that stopping audio causes OPD either:
there was only one observation per phase, and phase changes also affect USB
traffic, scheduling and device history. No automatic retry loop was run and
no failure was normalized into a pass.

Diagnostics additionally record completion timestamps for the hook write and
hook readback, separately from the protection re-arm completion time. These
were added **after** the three observations above; the saved reports are not
claimed to contain them. They permit the next comparison to measure actual
barrier-to-re-arm timing rather than infer it from total elapsed time.
JSON distinguishes `audio_started` from `audio_running_at_seizure`. Unknown
modes and unsupported/nonfinite rates are rejected before USB/HAL access.

At this stage the proposed next comparison was the normal PCM path versus the
running-HAL diagnostic. A later repeat failed in both paths despite at least
25 ms between hook readback and re-arm. The original-driver investigation above
then identified the different firmware hook protocol. No protection threshold
or HAL lifecycle workaround was needed.

## Control-only diagnostic and matched audio probe (2026-10-23)

Added `.build/apple_line --seizure-test`. Its default (`none`) never starts CoreAudio,
executes guest firmware or dials. It verifies initial on-hook/valid status and
requires OPE enabled, uses the unchanged ordinary protected seizure sequence,
then releases immediately after the ten guarded settling polls. No extra hold
is added. JSON records initial/final registers, the seizure stage and timing,
and hook/protection verification. A 15-second cooperative alarm and SIGINT/
SIGTERM handling request release; existing USB request timeouts still apply,
so this is not a hard real-time 15-second cutoff. Ordinary cleanup independently
attempts release again. Always use a separate `--status` process afterward.

The first hardware control-only attempt **passed**:

- Full ten-poll settling interval completed in **609.220 ms** from transition
  precheck; protection re-arm write completed at **44.666 ms**.
- Last off-hook status **47**, auxiliary **00**, no overload notification.
- Hook released; original protection **0c**, termination **00** and counter
  **20** retained. Independent readback confirmed on-hook/protection enabled.

A subsequent matched, one-second silence-only CoreAudio probe at fixed
**10286 Hz**, codec **7200 Hz**, **failed** at the first settling poll:

- Status **45**, auxiliary **01**, notification=0.
- Failure at **114.863 ms**, re-arm write completed at **44.640 ms**.
- Immediate release/protection restoration both verified. Independent final
  readback again confirmed on-hook and protection **0c**.

Private evidence: `.artifact-archives/apple-control-seizure-20261023-203512/`.
Neither test dialed digits. This single paired observation makes audio startup/
streaming interaction worth investigating; it does **not** prove causality,
exclude intermittency or establish that the physical line is fault-free.
The next comparison should isolate HAL initialization from running callbacks,
with protection and rate settings unchanged—not ignore OPD.

Memory-only self-tests now cover a successful complete control trial, OPD,
refusal with OPE disabled, cancellation after hook assertion, and the existing
write/readback failure paths. Cancellation requests release before further
control work. No real hardware is accessed by `--selftest`.

To reproduce **one** control-only attempt, saving stderr and its exit status:

```sh
.build/apple_line --seizure-test > /tmp/control-only-NEW.json 2> /tmp/control-only-NEW.log
# Record the command's exit status: zero requires seizure, release and protection checks.
.build/apple_line --status > /tmp/independent-status-NEW.json
```

Do not loop this command automatically following an overload indication.

## Earlier hardware follow-up (2026-10-23)

The Apple modem was reconnected. One bounded dual-capture V.32/LAPM test was
attempted, but **no digits were sent**: seizure settling tripped the native
OPD guard (`status=45`, `aux=01`, notification=0). Neither endpoint reached
CONNECT and no RTP media was available to evaluate. Both capture processes
reported zero kernel drops. Independent final readback confirmed on-hook.
Private evidence: `.artifact-archives/apple-rtp-live-20261023-181924/`.

A separate one-second, silence-only off-hook probe reproduced the same trip
before its active stage. This isolates the observed failure from SIP, RTP,
dialing and guest modem execution. It does not identify an electrical cause,
or rule out host/control timing. The helper already contains the documented
post-hook readback and 25-ms protection re-arm sequence; that earlier known
fix was not missing. No termination/current-limit setting was changed and
OPD was not ignored. No automatic dial retries were made.

Inspection found that failed hook transitions previously deferred hook release
to general cleanup, after audio shutdown. `native/apple_line.m` now attempts
the release write **before diagnostic register reads and audio teardown**, then
restores and verifies protection. General cleanup remains an independent
second release attempt. Failure logs include the stage, last status/auxiliary,
settling poll, elapsed/re-arm timing and release/protection verification.
This improves fail-closed behavior; it is **not a claimed fix for the OPD trip**.

The rebuilt helper's memory-only self-test covers four failed-seizure cases:
failed disarm verification, a hook write taking effect despite a reported
error, failed hook readback and OPD during settling. Each must release before
any post-failure diagnostic reads and restore the original protection value.
The 130-test focused suite passes, and a read-only hardware check of the final
helper confirms on-hook with protection register `0c`. No additional seizure
was performed after this change. Diagnostics/build/self-test evidence:
`.artifact-archives/apple-seizure-followup-20261023/`.

The next live step is a controlled check of the line/feed and seizure behavior,
not bypassing OPD or retrying modem negotiation through it.

## Initial preflight status (historical)

**The initial live modem test was blocked by missing Apple hardware.** The native helper
reports zero selected `05ac:1401` devices. A different USB modem is attached;
it was not used as a substitute. No extension was dialed. PBX SSH and local
BPF access are available. Evidence: `artifacts/apple-rtp-playout-validation/preflight/`.

The new receive playout has been exercised with actual archived RTP arrival
times, not merely synthetic packet-order tests. These are **capture-timing
replays**, not local kernel timestamps, USB measurements or modem BER results.

## Replay results

All use the production `RtpPlayout` implementation. The 5-ms poll model batches
capture arrivals at 5-ms intervals; it is not a measurement of emulator polling.

| Capture / model | RTP delay | Missing in capture | Missing during replay | Result |
| --- | ---: | ---: | ---: | --- |
| Latest emulator → PBX, 5-ms polling | 60 ms | 640 samples | 640 samples | All captured samples preserved; the actual hole remains |
| Latest PBX → emulator, 5-ms polling | 60 ms | 0 | 0 | All samples preserved |
| Earlier reordered emulator → PBX, 5-ms polling | 60 ms | 0 | 320 samples | Two packets miss their deadlines |
| Same earlier reordered stream | 200 ms | 0 | 0 | All samples preserved |
| Latest PBX → emulator, simulated 100-ms polling | 60 ms | 0 | 22560 samples | Delay is insufficient for this batching model |
| Same stream and 100-ms polling | 200 ms | 0 | 0 | All samples preserved |

JSON evidence is in `artifacts/apple-rtp-playout-validation/`. Missing counts
exclude idle output generated after the final capture timestamp. A preserved
capture with real holes is **not** called a continuous, reliable audio path.

**Conclusion:** the original fixed 60-ms deadline is not adequate for every
saved arrival pattern. `SipConfig.receive_delay_samples` and the ISDN CLI option
`--bri-sip-rtp-delay-ms` now expose this delay explicitly. The default remains
60 ms; the planned hardware control requests 200 ms. This is **additional to**
the separate 200-ms bearer queue reserve. The resulting negotiation latency
and sustained transfer behavior have not been hardware-validated. A larger
reserve cannot reconstruct the four packets absent from the latest capture.

Reproduce one of the failure controls (exit status 2 is expected):

```sh
.venv/bin/python tools/replay_rtp_playout.py \
  artifacts/apple-courier-sip/bell103-packet-audit-retry/rtp/10.69.220.8_62620--192.168.88.122_14366--a4496513.json \
  --delay-ms 60 --output /tmp/reordered-NEW.json
```

Repeat with `--delay-ms 200` and a different output filename. Output files are
created exclusively; existing evidence is never overwritten.

The final focused regression selection passes **130 tests**, including capture
preflight gating, explicit drop-counter validation, paired-capture comparison,
recorded/synthetic timing replay, CLI bounds and existing SIP/Apple/native paths.
`git diff --check` passes. The full suite was not rerun for this follow-up.

## Live test once the Apple modem is reconnected

The launcher checks for the original device and verified on-hook state. It
starts local and PBX tcpdump processes, waits for both to report readiness,
rechecks the hook, and invokes **one** bounded V.32/9600 LAPM call to the existing
2903 receiver, using the original 180-byte duplex payload control. No PBX
configuration, line gain, or modem firmware is changed. It does not retry.

Preflight only (no call):

```sh
.venv/bin/python tools/capture_apple_sip.py \
  --output .artifact-archives/apple-rtp-preflight-NEW
```

Explicitly allow the single call:

```sh
.venv/bin/python tools/capture_apple_sip.py --run-call \
  --output .artifact-archives/apple-rtp-live-NEW
```

Captures contain SIP metadata and audio and should stay private. The tool sets
0700/0600 permissions. `--output` must be new. It saves:

- `preflight.json`: Apple status, route, local address, local UDP and PBX link/
  UDP counters. A missing modem fails closed before any call or capture.
- `local.pcap`, `pbx.pcap`: concurrent captures filtered to the local/PBX UDP
  path. Local capture uses the routed interface (currently `utun8`); this does
  **not** separately observe the tunnel's encrypted underlay.
- `*-tcpdump.log`: readiness and kernel-drop counts. A capture with missing
  counters, no packets or nonzero kernel drops does not pass.
- `call/`: existing native modem/USB diagnostics, both terminal streams,
  payload verification and final hardware hook readback. Requested RTP delay
  is recorded separately from the bearer reserve in `run-settings.json`.
- `outcome.json`: caller/capture exit status, final hook verification and final
  network counters. Remote tcpdump has an independent 420-second backstop and
  is stopped by its own unique PID, never a blanket kill.

The capture runner's live branch has not been hardware-tested. Its missing-
modem gate and capture-counter checks have offline regression coverage.

## Compare the two capture points

Extract each pcap with the existing companion repository's parser:

```sh
.venv/bin/python ../v90modem/tools/eicon_rtp_pcap_check.py \
  .artifact-archives/apple-rtp-live-NEW/local.pcap /tmp/local-rtp-NEW
.venv/bin/python ../v90modem/tools/eicon_rtp_pcap_check.py \
  .artifact-archives/apple-rtp-live-NEW/pbx.pcap /tmp/pbx-rtp-NEW
```

Choose the complete emulator-to-PBX stream name from those outputs, then:

```sh
.venv/bin/python tools/compare_rtp_captures.py /tmp/local-rtp-NEW /tmp/pbx-rtp-NEW \
  --stream 'LOCAL_IP_PORT--PBX_IP_PORT--SSRC' --output /tmp/comparison-NEW.json
```

For PBX-to-emulator packets, reverse the directory order and select the reverse
stream. The comparison uses sequence/timestamp identities within the selected
SSRC, checks payload identity, and separates interior absences from unmatched
capture boundaries. No shared boundaries means no defensible interior-loss
estimate. Nonzero payload mismatches, interior absences, downstream-only packets
or no shared packets return status 2. One-way delays are deliberately not claimed
without synchronized clocks. NAT changing the endpoint names requires explicit
stream reconciliation; the tool does not silently guess a match.

Only a missing packet present in the local capture but absent at PBX ingress,
with verified capture coverage/drop counters, narrows loss to that segment.
If packets are already absent locally, correlate sender API counts and local
UDP/capture counters. Neither result alone separates tunnel and underlay loss.
