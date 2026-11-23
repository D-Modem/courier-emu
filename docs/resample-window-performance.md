# Faster cold Kaiser window construction

## Retained change

The immutable 1024-phase, 128-tap Kaiser window table was constructed entirely
in Python, including 131,072 Bessel-function calculations. When a native core
is already loaded, `courier_emu/resample.py` can now construct that table through
`courier_resample_windows` in `native/c5x_capi.cpp` / `native/resample.hpp`.

The native implementation preserves Python's arithmetic, including the libm
square in the Bessel series. It also avoids computing both halves of the table:
phase `p`, tap `k` and phase `1024-p`, tap `127-k` have opposite offsets and the
same squared Kaiser argument. On this power-of-two grid the offsets and ratio
are exact binary fractions, so symmetry is **bit-exact**, not an approximation.
Phase zero is computed independently; it has no phase-1024 partner in this table.

`dsp.loaded_library()` is a read-only accessor. The window optimization never
compiles or loads a core just to speed up a standalone Python resampler. With
no loaded core, `COURIER_NATIVE_RESAMPLE=0`, or an older prebuilt library lacking
the optional symbol, the original Python loop remains available. The global
window cache is unchanged. A native API rejection raises rather than silently
accepting an incomplete table. Short buffers, null pointers and invalid norms
are rejected before any native output writes.

## Measurements

On vmhost, alternating cold table builds with an already loaded/prebuilt native
library gave median times:

| Path | Median seconds |
| --- | ---: |
| Original Python loop | 0.2781 |
| Native construction, including conversion to Python tuples | 0.0323 |

This is approximately **8.6x faster table construction**, saving about **246 ms**
on that cold operation. Every table's SHA-256 hash matched. An earlier local ARM
measurement of the native implementation before symmetry was approximately 8x;
do not substitute that for a full-application or connected-phase speedup.

This optimization runs once per process/table-cache lifetime. It does **not**
claim a steady-state DSP or audio-production throughput improvement. The earlier
[runtime FMA optimization](resample-fma-performance.md) remains separate.

## Correctness and full replay checks

`tests/test_resample_windows.py` compares all **131,072 double coefficients**
bit-for-bit against the unchanged Python implementation, exercises cache reuse,
old-library fallback, native disablement, no implicit native loading, API
buffer/norm guards, and failed-construction handling. Retune tests continue to
compare native audio against the Python reference.

On vmhost, **28 focused tests passed** with the symmetric implementation across
window construction, resampler retunes/preparation and SIP media/recovery.
**296 focused local tests passed** across resampling, C5x, G.711, native
scheduler, SIP media/recovery, batching and worker-arm parity, including the
no-implicit-loading checks. These are not full-suite claims. The final
symmetric candidate's complete 300-million-instruction replay report matched
the saved control report; RX and TX WAV hashes also matched exactly.

Before symmetry, a four-run ABBA replay comparison had control wall times
45.228 / 46.374 s and candidate times 44.828 / 45.127 s. Complete JSON reports and
both audio hashes matched throughout. Host variation is large relative to the
startup saving, so these timings are **not** used to claim a stable overall
percentage improvement. The symmetric candidate was replayed after the full
coefficient parity checks, not assumed correct from the earlier version.

Both control and candidate libraries already included hardware FMA and the
original opcode dispatch. Builds used Clang 19.1.7 and identical optimization
options. Subprocesses were pinned within one container boot for the comparisons;
no host/container affinity policy changed. Raw sources, libraries, manifests,
reports and hashes are retained under `tmp/tx-timing-followup/vmhost-windows/`,
with scratch launchers alongside it. This was an existing dirty development
snapshot, not a clean-revision qualification.

CT127 is restored to **stopped**. The existing deployment and its default native
library were not replaced; all remote candidates remain isolated. No live calls,
PBX changes, clock changes, larger buffers or acceptance relaxations occurred.

## Rejected experiments

- A specialized panel strap-sense path improved its isolated microbenchmark but
  not the full local replay; reverted.
- Extending threaded C5x dispatch through the BE/BF sub-opcode tables preserved
  all opcode mappings, passed focused repeat/interrupt tests, and produced
  identical full vmhost reports/audio. But the ABBA replay was effectively flat:
  controls 45.269 / 45.271 s; candidates 45.020 / 45.276 s. Reverted, including
  the experimental table rewrite. The three affected files were checked
  byte-for-byte against their pre-experiment snapshots, preserving pre-existing
  work. Only the window-construction optimization is retained from this pass.
