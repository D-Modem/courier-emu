# Native worker call setup and empty publication cleanup

## Retained result

The native x86 worker now performs its batch-call setup in C and finishes the
empty post-run publication case without calling Python. In the saved socket-free
300-million-instruction firmware replay, eight vmhost runs against the
**pre-change Python wrapper and pre-change x86 extension** measured:

| Median across four runs per variant | Original | Native worker wrapper | Reduction |
| --- | ---: | ---: | ---: |
| Wall seconds | 44.98957 | 44.43546 | **1.23%** |
| CPU seconds | 44.85754 | 44.27542 | **1.30%** |

This is a modest **whole-replay execution-cost improvement**, not a claim of
live carrier stability or a connected-phase-only speedup. No live calls were
made. The replay includes boot/training, CONNECT and subsequent NO CARRIER.

The native-worker service, instruction, I/O and audio boundaries are unchanged.
All eight complete parsed reports and both recorded WAV hashes matched. This
is not an optimization obtained by increasing poll intervals or buffers.

## What moved

`native/x86_interpreter.cpp::run_cpu_python` performs the host/poll/MMIO argument
setup and before/after hook dispatch previously done by
`courier_emu/x86_native.py::NativeInterpreter.execute`. The existing guarded
instruction loop is reused; it still returns at the same boundaries.

The important additional reduction is the worker's empty `after_run` case:

1. `courier_worker_after_run_gate` in `native/c5x_capi.cpp` clears `armed`, just
   as the original Python hook did.
2. If neither `dirty` nor `presend_error` is present, that is all the work;
   Python is not called.
3. Otherwise the original Python hook publishes the state/error as before.

The gate is registered by `Machine.run` through `WorkerPoll`, together with the
**identity of the hook it implements**. Replacing the hook causes the native
wrapper to ignore the stale gate and call the replacement normally. The gate
uses the existing worker context/lifetime/ownership contract, not a new borrowed
DSP state view or a concurrent-observer interface.

A fresh local profile confirms the mechanism:

| Observation | Before | After |
| --- | ---: | ---: |
| Native CPU batch calls | 897,710 | 897,710 |
| Supervisor service passes | 741,423 | 741,423 |
| Python `after_run` calls | 897,710 | 156,803 |

That removes **740,907 empty Python callbacks**, about 82.5%, without removing
emulated service passes. The complete profiled reports also matched. These
profile counts explain the mechanism; profiled timings are not the speed gate.

Before-run arming, dirty/error publication, interrupt handling, event replay and
many supervisor/device decisions still run in Python. This does not move the
whole scheduler into native code.

## Compatibility and safety

- The optimized wrapper is selected for exact harness CPU/wrapper classes with
  a registered worker gate. Ordinary CPUs and custom subclasses retain the
  Python wrapper and its attribute dispatch.
- Older x86 extensions lacking `run_cpu`, or older DSP libraries lacking the
  gate API, retain the Python path.
- `COURIER_X86_NATIVE_WRAPPER=0` selects that path explicitly. It does **not**
  disable native instruction execution.
- Host/poll/MMIO metadata is captured before `native_before_run`; execution
  buffers are obtained afterwards, preserving the previous ordering.
- Buffer references remain alive through execution even if a native I/O hook
  replaces their Python attributes. No raw buffer pointers are cached between
  calls, and no new audio buffering is introduced.
- Replacement `run` callables retain their original argument shape. Hook and
  engine exceptions still stop later hook/bookkeeping work.
- The legacy extension `run` entry point and its ten-element result remain
  available. The worker wrapper uses a separate entry point/result shape.
- No new thread, GIL-release policy, emulated clock, instruction budget, sample
  precision, codec, firmware behavior or acceptance criterion is introduced.

## Measurement controls and rejected intermediate version

Both x86 extensions in the final before/after comparison were compiled with
Debian Clang 19.1.7 and identical options:

```
-std=c++17 -O3 -Wall -Wextra -shared -fPIC -I/usr/include/python3.11
```

Both variants used the same DSP library, compiled with:

```
-std=c++17 -O3 -fno-semantic-interposition -shared -fPIC
```

Each unprofiled child replay was pinned to CPU5, from the container's allowed
set `[5, 6, 8, 10]`. All four advertised a 3.3 GHz maximum frequency; these were
E-core measurements, not the earlier CPU0/P-core results. Affinity was only a
measurement control, not a deployment change or claimed timing fix.

Two alternating-order series were run:

| Series | Order | Control wall median s | Candidate wall median s | Control CPU median s | Candidate CPU median s |
| --- | --- | ---: | ---: | ---: | ---: |
| Gated A | control, candidate, candidate, control | 44.98367 | 44.28969 | 44.82414 | 44.10656 |
| Gated B | candidate, control, control, candidate | 44.98957 | 44.73060 | 44.85754 | 44.54639 |

Between these series, constructor eligibility was narrowed to CPUs with a
registered gate, keeping ordinary CPU workloads on the Python wrapper. The
replay already registers that gate, so its per-batch runtime paths and the
compiled binaries are identical. Series B tests the final constructor policy;
source hashes for both series are preserved.

An earlier **setup-only** candidate appeared about 0.5% faster against its own
disable-switch path. The stricter original-source/original-binary control
showed it was instead about 0.4–0.5% slower than the actual baseline. That
intermediate version is **not the retained result**. Adding native completion
of the empty publication case was necessary to pass the real before/after
speed gate. Intermediate artifacts remain available rather than being omitted.

## Correctness and regression evidence

- **403 focused local tests passed**, covering all native/RTP/SIP test modules,
  frame timing, XF state/IRQs, board service, G.711 and resampling.
- **116 focused vmhost tests passed with the final Clang x86 extension**, and
  the same **116 passed with the final GNU x86 build**.
- Tests compare wrapper modes for hook ordering, host/poll timestamp snapshots,
  buffer replacement before and during native execution, private/debug run
  replacements, exception paths and older-extension/library fallback.
- Gate tests check all armed/dirty/error combinations, null context, full
  state-byte preservation apart from the intended disarm, and callback identity.
- Full replay reports include the same instruction and native batch counters,
  timer/IRQ state, serial output and DSP diagnostics. WAV hashes were:
  - RX: `55a7640af4ec1d159334bb39969fbdbb0d82689e5b78959c8c11a641517013c0`
  - TX: `6f4b2418571c7bdf0abe2014e5ae1c8a7cc70e430df8be281bfa14b0de93caa1`

These are focused regression and differential results, not a full-suite or
long-call acceptance claim. The genuine 600-second V.34 gate remains open.

## Artifacts and isolation

Remote work is isolated under
`/root/courier-perf-followup/perf-native-wrapper-followup/`. Its source/library
manifest records Python/compiler versions, CPU limits, firmware and source/
library hashes; the final summary records all eight runs and equality checks.

The full snapshot was retrieved to
`tmp/tx-timing-followup/vmhost-native-wrapper/` and archived as
`vmhost-native-wrapper-results.tar`. Original wrapper/extension source snapshots,
the setup-only intermediate version, launchers, complete reports, raw timings,
tests and profiles are retained alongside. The source baseline was already
uncommitted; this is not a clean-revision claim.

Existing remote deployment sources/default libraries and PBX configuration were
not replaced. CT127 was restored to its original **stopped** state. No unrelated
call or live media transport was used.
