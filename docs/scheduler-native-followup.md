# Scheduler/native-boundary follow-up

## Outcome

Two scheduler/boundary candidates were implemented and checked. **Neither is
retained**: neither established a reliable unprofiled end-to-end improvement
worth its complexity. Existing FMA, cold-window and bulk G.711 work remains
unchanged. No clock, buffer, firmware or acceptance setting was relaxed.

## Fresh profile

The current 300-million-instruction socket-free firmware replay produced
86.5 million profiled calls in 30.283 seconds. Its serial output includes
CONNECT and subsequently NO CARRIER; it is a differential execution fixture,
not a long-call stability test. The fake SIP port bypasses RTP codecs.

Selected cumulative costs (nested; **do not add these together**):

| Path | Calls | Profiled cumulative seconds |
| --- | ---: | ---: |
| `x86_native.execute` | 897,710 | 9.214 |
| supervisor `fast_service` | 741,423 | 8.446 |
| `bridge.clock_x86` | 233,923 | 4.741 |
| native-worker `arm` | 741,423 | 3.021 |
| `refresh_native_lanes` | 762,530 | 2.449 |
| timer `tick` | 741,423 | 2.295 |
| `_frame_irq_due` | 721,229 | 1.348 |
| `NativeC5x.xf_frame_state` | 721,229 | 0.421 |

These locate candidates, not percentages of unprofiled/live execution. Profiling
is particularly intrusive for frequent short Python calls. Unprofiled local
controls took approximately 16.6–16.8 seconds.

Raw profile: `tmp/tx-timing-followup/current-profile.pstats`, alongside its full
report and stderr. The source baseline contains pre-existing uncommitted work.

## Rejected: earlier native-arm eligibility rejection

The read-only timer/UART/interrupt eligibility check was moved ahead of the DSP
quiet/static checks. This avoids unnecessary DSP inspection when command-mode
or pending interrupt work already prevents native arming.

Local unprofiled ABBA, 300 million instructions per child:

| | Control median | Candidate median |
| --- | ---: | ---: |
| Wall seconds | 16.7290 | 16.5628 |
| CPU seconds | 16.6440 | 16.4922 |

Complete parsed reports and both audio hashes matched. The roughly 1% local
result was not enough to establish a worthwhile connected-phase gain: many
rejections are in boot/command handling. It was restored rather than adding a
new scheduling variant without stronger evidence. No vmhost speedup is claimed
for this candidate.

Snapshots and raw measurements: `tmp/tx-timing-followup/scheduler-{control,candidate}/`,
`scheduler-local/`, and `benchmark_scheduler.py`.

## Rejected: native XF state live view

A candidate optional C API returned a borrowed read-only pair of native XF edge
count/reset epoch. Native updates went directly to that storage; Python's
`xf_frame_state()` read it without a ctypes getter call. The view stayed at a
stable address across reset and was discarded before core destruction. Older
libraries and an explicit disable retained existing snapshots/getters. Ownership
remained exclusive: this was not an atomic/concurrent-observer API.

Local ABBA was effectively flat in CPU time: control median 16.6131 seconds,
candidate 16.6156 seconds. Full reports and audio matched.

Vmhost used the **same Clang 19.1.7 library and native x86 binary** for both
variants, changing only the candidate constructor's view-enable flag. Each child
was pinned to an allowed CPU selected by maximum advertised frequency. Pinning
is measurement control, not a deployed timing change.

Unprofiled vmhost results, 300 million instructions per child:

| Series/order | Wall seconds |
| --- | --- |
| A: control, candidate | 27.4022, 27.3974 |
| B: candidate, control | 29.9531, 30.4599 |
| C: control, candidate, candidate, control | 29.0540, 28.6560, 28.8023, 28.0983 |

The apparent improvement in series B did not repeat in series C. Across the
four runs of each variant, the candidate's median wall time was about **0.5%
slower**, with substantial run-to-run variation. This is no reliable speed win.
All eight complete reports matched and both WAV hashes matched:

- RX: `55a7640af4ec1d159334bb39969fbdbb0d82689e5b78959c8c11a641517013c0`
- TX: `6f4b2418571c7bdf0abe2014e5ae1c8a7cc70e430df8be281bfa14b0de93caa1`

The candidate passed **75 focused vmhost tests**, including reset/edge parity,
view lifetime, old-library fallback, frame IRQs, board service, native reentry
and SIP worker-arm parity. Initial isolated test runs lacked a test dependency
and the native x86 source; the missing files were supplied and the final run
passed. Those setup failures are not omitted from the investigation.

Candidate sources, library, test sources/results, fixture, manifests and raw
reports/timings are preserved in the isolated remote directory
`/root/courier-perf-followup/perf-xf-view-followup/` and retrieved under
`tmp/tx-timing-followup/vmhost-xf-view/`, also archived as
`vmhost-xf-view-results.tar`. Each benchmark manifest records source, fixture and
library hashes. Complete JSON reports were also compared across all three
series and matched.

## Restoration and next direction

The production DSP, native core, opcode, C API and machine files were restored
and byte-compared with pre-experiment snapshots, preserving the dirty baseline.
The original three XF snapshot tests were restored. **326 focused local tests
passed after restoration** in 90.63 seconds, covering C5x execution, XF/frame
IRQs, native reentry, SIP worker parity, resampling and G.711. `git diff --check`
passed. This is not a full-suite claim.

CT127 is again **stopped**. Existing deployment sources/default libraries and PBX
configuration were not replaced; no live calls were made.

The next substantial target is consolidating complete device-service phases
across the Python/native boundary while preserving every existing event
boundary. Removing one getter crossing at a time is not sufficient evidence of
an end-to-end gain. Native state ownership, I/O replay, timer/IRQ delivery and
SIP/audio transfer must be designed and differentially tested together; simply
increasing poll intervals or enabling restricted native modes is not a fix.
