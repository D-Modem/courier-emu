# Native worker rejection and remaining resampler loops

This follows the [native worker wrapper](native-worker-wrapper-performance.md).
It moves two more bounded kinds of work out of Python, without altering clocks,
service deadlines, RTP packet sizes, media reserves, or acceptance criteria.
It is **not a live-call stability qualification**. The rejection gate saves most
work in boot/command mode with queued AT input; successful data-mode arming is
unchanged. Connected-only speedup is not established by the whole-replay result.

## Worker arming rejection

The native x86 wrapper can skip the internal `before_run` callback when:

- No worker arming request exists. The original callback does nothing here.
- `_serial_started` is exactly `True`: `fast_service_static` must reject.
- Input is queued in an exact ordinary `deque` and `online_mode` is exactly
  `False`: `_serial_receive_quiet_until` must return `None`, so
  `timer_poll_static` must reject.

Rejected requests are cleared, just as `arm()` clears them before checking
eligibility. No worker snapshot is modified. All other cases still run the
**complete original Python arming checks**, including every device/deadline
boundary. This does not move successful arming, device ownership, or nonempty
post-run publication into C++; those remain further work.

The gate is bound to callback identity. Replacing the callback cannot bypass
it. Registration is restricted to exact `CourierMachine`/`CourierDspBridge`
classes; custom queue types keep their truth callbacks. This is an optional CPU
attribute, not a change to the existing extension argument tuple. Older x86
extensions simply call the original callback. `COURIER_NATIVE_ARM_GATE=0`
disables registration without disabling native execution or empty cleanup.

## Native fixed-rate FIR and polyphase blocks

Two optional C API exports, `courier_resample_fixed` and
`courier_resample_polyphase`, execute the previously Python output loops.

- **Fixed-rate FIR:** retains the original 128-tap/1024-phase coefficients,
  floating position additions, nearest phase, history trim, saturation, and
  ties-to-even integer rounding. CPython with `math.sumprod` uses the existing
  compensated native dot; CPython 3.10/3.11 without it uses separate binary64
  products and sequential additions, matching its original `sum(map(mul, ...))`.
  Newer CPython without standard `math.sumprod` retains Python's compensated
  `sum` fallback; import-time replacement functions are never bypassed.
  Volatile product temporaries prohibit accidental FMA contraction in that
  latter mode. Non-CPython interpreters and custom `_dot` callbacks keep Python.
- **Rational polyphase:** retains the original tap order, reverse history
  indexing, integer phase/output counters, padding, trim, flush, and equal-rate
  passthrough. Separate multiply/add semantics are required even on FMA hosts.
  Cached native coefficients are checked against the current Python table;
  changed tables are rebuilt, and custom numeric taps use Python. More than
  1024 phases, more than 4096 taps/phase, or unusually large counters/rate ratios
  conservatively use Python, **not different rates or reduced precision**.
- Small blocks keep Python to amortize marshalling and table validation. These
  eligibility heuristics do not change sample readiness or output counts.
- Both use an **already-loaded** core library. Neither implicitly builds or
  loads the DSP library; missing optional exports preserve Python-only and
  older-library operation.
- C calls retain the GIL so a short packet kernel does not surrender it to a
  busy emulator thread and wait a switch interval to return. Output scratch is
  bounded to 1024 samples/call; larger blocks resume and append **all** output.
  This is interop scratch, not an emulated queue or a media-buffer change.
- Input/coefficient arrays have strong Python owners throughout each call.
  There are no persistent raw stream-buffer pointers or native stream objects.
  Results commit only after successful completion. Nonfinite/unsupported data
  declines to the original Python loop, preserving exceptions and partial
  stream-state changes. No failures become missing PCM.

Disable independently with `COURIER_NATIVE_FIXED_RESAMPLE=0` and
`COURIER_NATIVE_POLYPHASE=0`. The existing `COURIER_NATIVE_RESAMPLE=0` process
switch also disables these new kernels.

## Measurement method

The actual pre-change source was saved from `d138dc2`. The final control uses
an original-source Python package (including the old CPU constructor), the
separately compiled original x86 binary, and the separately compiled original
DSP C API/resampler header. Unchanged package files are shared by symlink;
bytecode compilation is outside timing. Both libraries use matching compiler
options. Neither candidate-disable controls nor a common newly modified DSP
library alone serve as the final baseline.

The socket-free 300M-instruction replay includes boot, training, CONNECT, and
subsequent NO CARRIER. Every complete report and both recorded WAV hashes must
match. These are whole-replay costs, not connected-only costs.

`tools/benchmark_resample_pipeline.py` measures a **complete offline audio
pipeline**, not just a native dot-product microbenchmark:

```
PCM -> TX resampler -> 160-sample SIP queue/G.711 encode
    -> G.711 decode -> RX resampler -> PCM
```

The fixed pipeline runs 48 kHz -> 8 kHz -> 48 kHz; polyphase runs
7200 Hz -> 8 kHz -> 7200 Hz. Each sample processes 30 simulated seconds.
Filter design, compilation, and a one-block warm-up are outside timing.
Wire/PCM hashes, packet/sample counts, pending TX contents, and final counters
and floating stream-state hashes must all match the actual reference source.
For example, after saving the old `resample.py` and `sip.py`:

```sh
python tools/benchmark_resample_pipeline.py --kind fixed --seconds 30 \
  --reference-dir /path/to/pre-change/courier_emu
python tools/benchmark_resample_pipeline.py --kind fixed --seconds 30
```

Use alternating pinned child processes (ABBA then BAAB), not these two commands
alone, for a performance decision. The replay intentionally bypasses real RTP;
the separate pipeline exercises resamplers/codecs/queues but not sockets or
real-time scheduling.

### Vmhost replay and pipeline results

Debian CPython 3.11.2, Clang 19.1.7, pinned CPU3 (advertised 4.4 GHz);
allowed CPUs were `[3, 6, 7, 11]`. Do not compare absolute times with the prior
wrapper experiment's CPU5/E-core runs. Compiler options:

- DSP: `-std=c++17 -O3 -fno-semantic-interposition -shared -fPIC`.
- x86: `-std=c++17 -O3 -Wall -Wextra -shared -fPIC -I/usr/include/python3.11`.

Eight complete replay children, ABBA then BAAB, using the full original source
package and both original libraries as the control:

| Median seconds | Actual pre-change | Candidate | Reduction |
| --- | ---: | ---: | ---: |
| Wall | 28.82496 | 28.39733 | 1.48% |
| Process CPU | 28.77712 | 28.34570 | 1.50% |

An earlier eight-run series sharing the candidate DSP library showed 1.87%
lower CPU cost; the stricter full-original comparison above is the headline
result. All alternating series were positive, but the modest gain is
workload/host-specific.

Every full report and both WAVs match, including the canonical hashes:

- RX: `55a7640af4ec1d159334bb39969fbdbb0d82689e5b78959c8c11a641517013c0`
- TX: `6f4b2418571c7bdf0abe2014e5ae1c8a7cc70e430df8be281bfa14b0de93caa1`

A separate rejection-only Clang 14.0.6 ABBA check kept the old resampler/SIP
source in both variants: median CPU 28.89690 -> 28.46931 seconds (**1.48%**).
The replay is dominated by supervisor/retuned-native paths, not the two new
steady-state block kernels. Their benefit is measured separately below.

Separate profiles retain identical full reports and 897,710 native CPU batches
and 741,423 service passes. Python `before_run` calls fall from 897,710 to
271,762 (**625,948 fewer**); `arm` calls fall from 741,423 to 271,762
(**469,661 fewer**). Nonempty `after_run` publication remains at 156,803.
These counts explain the boundary reduction; only the unprofiled paired runs
above establish the execution-cost benefit.

Eight children per pipeline, median process CPU seconds for 30 simulated
seconds, including both directions, marshalling, codec/queue work and hashing:

| Pipeline | Actual pre-change | Native | Speedup |
| --- | ---: | ---: | ---: |
| Fixed FIR | 4.19025 | 0.35149 | 11.92x |
| Polyphase | 0.76958 | 0.12486 | 6.16x |

Every wire/PCM hash and final stream/queue state matches. These are **pipeline
speedups**, not whole-emulator speedups or live-call results.

### Local pipeline result

macOS arm64, CPython 3.13.6, existing Clang build; eight children per pipeline.
Median process CPU seconds (30 simulated seconds, both directions):

| Pipeline | Actual pre-change | Native | Speedup |
| --- | ---: | ---: | ---: |
| Fixed FIR | 1.37950 | 0.52973 | 2.60x |
| Polyphase | 0.63434 | 0.08276 | 7.66x |

The CPython 3.11 reference lacks `math.sumprod`, so its fixed-FIR reference is
substantially more costly. Do not generalize its speedup to newer Python or to
the whole emulator. Equal-rate polyphase passthrough and already-native retuned
FIR loops are not accelerated by these new block kernels.

## Validation and evidence

Differential tests cover fragmented/empty input, fixed rates, phase rounding,
flush, equal-rate passthrough, saturation/ties, large multi-scratch output,
nonfinite exceptions/partial state, coefficient mutations, custom dot/queue
callbacks, unloaded/old libraries, GIL binding, and cancellation vectors which
explicitly distinguish sequential, fused, and compensated arithmetic. Captured
CPU firmware with a synthetic idle DSP is compared against cooperative service
both with and without queued AT input.

491 focused local tests passed, plus 85 tests with the native wrapper and
arming gate explicitly disabled, and 22 timing-analysis/clock-audit tests. Vmhost passed **489 tests with each of the
Clang and GNU builds**, with two skips per compiler: the macOS-only CoreAudio
helper and an optional saved hardware capture. Tests use the existing project
venv (also CPython 3.11.2); benchmark children use distro CPython 3.11.2. A further
300M-instruction compatibility replay using the new Python package with **both
original libraries** retains the complete report and canonical audio too.

Artifacts are under `tmp/tx-timing-followup/service-resample-local-final/` and
the isolated vmhost `perf-service-resample-followup/` directory:
`results-actual-baseline/` holds the final replay comparison; `results-release/`
holds pipeline comparisons, profiles, tests, and source/library manifests. The remote work uses
no real SIP session, PBX changes, or deployment library replacement. After
retrieving the artifacts, CT127 was restored to its original **stopped** state.
