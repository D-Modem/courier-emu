# vmhost performance follow-up: XF observations and native scheduler reentry

## Change

The cooperative frame-IRQ check previously crossed ctypes twice to read the
DSP XF falling-edge count and reset generation. A captured 100-million-
instruction offline SIP replay called that check 582,001 times under cProfile.

`NativeC5x.xf_frame_state()` now reads both values through one native call,
using a reusable per-core two-word buffer. `CourierMachine._frame_irq_due()`
uses it when available. The old getters remain supported, including fallback
for explicitly selected prebuilt libraries without the new symbol and for
lightweight test cores.

This is an observation at an existing cooperative scheduler boundary, not a
concurrent/atomic observer API. No instruction stepping, clocks, IRQ recognition
intervals, buffers, audio samples, modem firmware or acceptance checks change.
Reset generation is retained even when the post-reset edge count has caught up
to the previous count.

## Local evidence (not a vmhost measurement)

Host: macOS arm64, Python 3.13.6. The reproducible synthetic benchmark:

```sh
.venv/bin/python -m tools.benchmark_xf_frame_state
```

Six alternating-order pairs, 500,000 calls per sample, after warmup:

| Getter | Median seconds |
| --- | ---: |
| Separate calls | 0.183866 |
| Combined call | 0.145745 |

That is 1.26x getter throughput, approximately 21% less getter wall time.
An earlier measurement observed 1.23x. Neither is an end-to-end speed claim.

The existing archived offline replay was adapted under `tmp/vmhost-perf/`
to use local fixture paths, disable network access via its fake SIP session,
and compare the old/new getter path. Complete parsed JSON reports matched.
Warm 100-million-instruction process observations were 10.526 s for the old
path versus 10.603/10.572 s for the new path. An initial old-path run took
17.228 s and is not a credible steady-state comparison. **There is no
measurable end-to-end speedup in these observations.** cProfile runtime must
not be compared against unprofiled runtime.

102 focused tests passed across combined-getter behavior, native/Python XF
parity, reset epochs, frame cadence, worker-arm parity, SIP quiet scheduling,
codec batching, RTP recovery/producer telemetry and native machine/port models.
This is not a full-suite claim.

Local measurement outputs are in `tmp/vmhost-perf/`; these are scratch outputs,
not archived hardware qualification artifacts.

## vmhost follow-up: native scheduler reentry

CT127 was stopped at the beginning of this follow-up. It was started for the
measurements, and a separate `/root/courier-perf-followup` copy was made from
`/root/courier-hardware-timed-20261106-092949`. Current source was overlaid only
in that new copy, and its C5x library rebuilt with Clang 19. This snapshot
includes pre-existing local uncommitted work, not a clean revision; the matched
controls toggle only the new reentry setting. Existing snapshots,
PBX configuration and host/container scheduler policy were not changed.
CT127 was returned to its original **stopped** state after all tests finished.

### Larger hot path

The fresh vmhost offline profile showed substantial supervisor execution and
scheduler overhead, rather than just DSP cost. After every cooperative clock
callback, `Uc.emu_start()` decoded one instruction in Python before returning
to the guarded native engine. It now resumes directly in native execution when
the callback leaves CS:IP unchanged and no deferred instruction action or free
redirect remains pending. Code, memory and device guards still apply, and
unsupported instructions fall back without repeating the clock callback.

Boundary port I/O and prefixed instructions intentionally retain the old path.
An initial broader experiment changed native boot-strobe counts and approximate
lamp diagnostic stamps, despite unchanged machine results. The final restriction
preserves the **complete** offline reports, including those diagnostics.

The change is enabled by default with native execution; set
`COURIER_X86_SERVICE_REENTRY=0` to retain the original boundary path for controls.
No clocks, batch sizes, interrupt-recognition intervals, audio samples, queues,
firmware, PPP checks or protocol timeouts were changed.

### Unprofiled offline results on vmhost

The fake SIP session replays saved PCM without sockets or wall pacing. This is
an execution-cost comparison, **not a live-modem or sustained-throughput test**.
Only the benchmark subprocess was pinned to CPU1 to remove P/E-core migration
from this comparison. CT127's allowed CPUs on this boot were **1,7,12,14**, with
no CPU quota or recorded CFS throttling. No container-wide affinity changed.

| Replay | Original median wall time | Reentry median wall time | Reduction |
| --- | ---: | ---: | ---: |
| 100 million instructions, six alternating runs | 21.621 s | 18.418 s | 14.8% |
| 300 million instructions, four ABBA runs | 36.941 s | 34.782 s | **5.8%** |

All complete parsed reports matched within both comparisons. The corresponding
100-million median child CPU times were 21.567 s and 18.366 s. There is material
run-to-run frequency/host variation; these small sample sets do not establish a
universal speedup. The longer control is the more conservative headline result.

The separate, unpinned cProfile 300-million runs took 69.464 s before and
71.792 s after. These instrumented observations are **not evidence of a speedup**;
profiler overhead and host variation must not be substituted for the matched
unprofiled controls. Their complete parsed reports also matched.

### Regression checks

- **51 new differential cases** cover clock periods 1/4/64, both CPU profiles,
  stop/redirection/free-redirection semantics, deferred work, self-modifying
  code, ranged code hooks, memory watchpoints, native-unsupported instructions,
  prefixed instructions and boundary port-I/O accounting.
- **265 focused local tests passed** across the boundary/native/scheduler/media
  suites and additional board-service, SIP data-bank, I-modem live-poll and UART
  quiet-service controls.
- **172 passed, three optional-fixture skips on vmhost** in the primary focused
  suite. The additional 90 local tests were not rerun remotely.
- No full-suite claim.

### Live hardware control: reliability still fails

Two bounded hardware calls used the same isolated source, explicit Clang
library, original 403/DSP firmware, S58=33 V.34 selection, required LAPM with
compression disabled, PCMA, 20-ms bridge blocks, existing media reserves,
extra legal PPP quoting and stop-and-wait exact 512-byte ICMP payload checks.
CPU affinity was **normal** for both live runs; neither was profiled.
Preflight checks refused busy account 2905/destination 7930, and no unrelated
call was cleared.

| Control | Actual result | Exact replies | Outcome |
| --- | --- | ---: | --- |
| Reentry enabled | 31200/V34/LAPM, authenticated and IPCP opened | 16/17 | NO CARRIER at 380.086 connected seconds |
| Reentry disabled | No CONNECT | 0/0 | NO CARRIER after about 91 s acquisition |

**Neither passed the 600-second target.** The disabled control did not reach the
same modulation/data phase, so the live results cannot establish a causal
stability improvement or regression. Both complete serial captures validated;
the enabled capture had 9,982 bytes. Neither had a native error or watchdog
expiration. The enabled call had zero PPP FCS errors, zero reported active RX
underruns, zero RTP sequence gaps and zero missing/late playout samples, but
pre-hangup peak TX sample-clock lateness reached **619.7 ms** and the maximum TX
packet gap was **43.1 ms**. Its 8,260 recovery transitions are not 8,260 long
packet gaps. Raw physical BLER reached 33; final reset-epoch receive-empty
counters must not be attributed to the preceding data connection.

Artifacts, reports, manifests, captures and control scripts are retained privately
under `.artifact-archives/vmhost-service-reentry-followup/`. The source change
is a measured offline CPU-cost improvement, **not a solved modem-stability or
sustained-binary-throughput problem**. Further work needs a successfully
connected matched control and phase-specific measurement of the remaining
producer lateness and modem errors.
