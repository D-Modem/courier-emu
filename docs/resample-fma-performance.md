# Runtime-selected x86 hardware FMA for the compensated resampler

## Change

`native/resample.hpp` retains CPython-compatible triple-length dot-product
accumulation. On generic x86-64 builds, however, the explicit `std::fma` used
for each tap's multiplication residual called `fma@plt`: the baseline ISA
does not guarantee hardware FMA even when the running CPU supports it.

The dot product now has a `target("fma")` specialization selected once by
`__builtin_cpu_supports("fma")`. Its loop and compensated operation order are
identical to the portable implementation. Unsupported x86 CPUs and non-x86
platforms retain the portable path. The candidate's x86 disassembly contains
hardware `vfmsub213sd` rather than a per-tap libm call in the selected dot loop.

There is no global `-march=native`, fast-math, reassociation, reduced precision,
changed FIR/kernel, new batching, altered clock, buffer increase, sample loss
or relaxed acceptance check. The optimized routine only replaces the explicit
correctly rounded fused operation; other floating-point code is not compiled
with extra target features. ARM builds retain their existing implementation.

## Matched vmhost measurements

Four unprofiled, socket-free **300-million-instruction** offline replays ran in
ABBA order on CT127 during one boot. Only each benchmark subprocess was pinned
to CPU0 (reported 4.4 GHz maximum). Container affinity was `[0,6,7,8]`; no
container/host scheduling policy changed. CPU6/7/8 reported 3.3 GHz maximum.
The CPU pin is a measurement control, not a recommended stability fix.

Both libraries were freshly built with Debian **Clang 19.1.7** and identical
`-std=c++17 -O3 -fno-semantic-interposition -shared -fPIC` options. The candidate
used the new header; the control retained the old header. Python source,
firmware, saved receive PCM, replay command and native core/CAPI sources were
identical within this comparison. No profiling instrumentation was enabled.

| Run | Library | Wall seconds | Child CPU seconds |
| --- | --- | ---: | ---: |
| A1 | Portable control | 30.008 | 29.932 |
| B1 | Runtime FMA | 29.154 | 29.105 |
| B2 | Runtime FMA | 28.751 | 28.693 |
| A2 | Portable control | 29.558 | 29.544 |

Median wall time fell from **29.783 s to 28.953 s**, approximately **2.8%**.
Median child CPU time fell by approximately **2.8%** as well. This is a modest
end-to-end execution-cost improvement in this replay, not a universal speed
claim. The small sample set does not eliminate all host/frequency variation.

All four complete parsed JSON reports matched. Both RX and TX WAV SHA-256
hashes matched across all runs. This includes the complete report rather than
only CONNECT/result text or selected counters.

## Regression coverage and deployment boundary

`tests/test_resample_dot_dispatch.py` compares the portable routine, runtime
dispatch, hardware specialization when available, and Python `math.sumprod`
when available. Cases include PCM/kernel inputs, zero and signed zero,
cancellation, multiplication residuals, wide exponent ranges, and lengths on
either side of the 128-tap boundary. Comparisons are bit-exact, not tolerance
or SNR checks. Local ARM testing exercises the non-x86 path; vmhost testing
executes the x86 hardware path.

**85 focused tests passed on vmhost**, including the new dot-product cases,
resampler retunes/preparation, SIP packet recovery/media clock and native
scheduler reentry. **289 focused local tests passed** across the resampler,
C5x, G.711, native scheduler, SIP media/recovery, codec batching and worker-arm
parity suites. These are not full-suite claims.

Candidate/control libraries and replay results remain isolated under
`/root/courier-perf-followup/perf-fma-followup/`; the existing deployment's
source and default native library were not replaced. Local copies, test logs,
compiler/host metadata, source hashes and the scratch benchmark launcher are
under `tmp/tx-timing-followup/vmhost-fma/` and
`tmp/tx-timing-followup/benchmark_remote_fma.py`. The development snapshot was
already dirty; these measurements do not describe a clean git revision.

CT127 was returned to its original **stopped** state. No live modem calls,
credentials, PBX settings, shared accounts or unrelated calls were involved.
A claim about long-call stability still requires the matched live V.34 gate in
[the timing investigation](tx-timing-investigation.md).

A subsequent [cold window-construction optimization](resample-window-performance.md)
reduces immutable table setup time; its startup-only benefit must not be counted
as a further steady-state throughput improvement.

## Other experiments in this follow-up

A local profile-guided library showed only a small tentative gain; it was not
selected or deployed. Skipping rollback snapshots for a subset of native x86
register instructions and unrolling the compensated dot-product loop did not
improve complete replay performance; both source changes were removed. Their
correctness comparisons passed, but correctness alone was not the speed gate.
Only runtime-selected x86 FMA is retained as the measured optimization.
