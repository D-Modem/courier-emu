# Active-training underrun: cold filter construction at retune

The original diagnosis below was offline. Filter preflight has since been
implemented and tested in a new live 6313 call; see the verification below.
This fixes the identified cold-retune stall, not every possible underrun.

The corrected-level 6313 call in `../apple-dtmf-gain/default/6313/` reaches and
is answered by the requested endpoint, then fails with **130 active output gap
samples** (12.64 ms at 10286 Hz). This is not a DSP-reset silence interval.

## Trace timing

The failed transaction is immediately after the original firmware retunes:

- service 1056: 43 codec samples at 7200 Hz;
- service 1057: 1 sample at transient 8641.234462 Hz;
- service 1058: 151 samples at 9600 Hz;
- service 1059: next 193 samples at 9600 Hz, transport reports EOF.

There are approximately **90.86 ms** between the starts of service 1056 and
1059, while the first three chunks represent only **21.82 ms** of codec PCM.
The helper's original priming is 1024 / 10286 = 99.55 ms, but the remaining queue
at any instant depends on callback phase and earlier delivery jitter. It is not
a guaranteed 100 ms deadline available to every transaction.

## Identified synchronous work

`BandLimitedResampler.convert` calls `_kernel_for` directly on a new rate ratio.
A cache miss constructs **1024 phases × 128 taps = 131,072 coefficients in
Python**, in the same thread that feeds hardware output. The receive resampler
needs two previously unused tables at this transition, even though the
intermediate clock carries only one input codec sample. The actual clock
boundary must not simply be rounded away.

`retune-benchmark.json` reconstructs the same rate/chunk sequence offline,
prewarming only the already-used boot/dial rates and native retune plumbing:

- transient receive kernel: **20.29 ms**;
- 9600 Hz receive kernel: **21.09 ms**;
- total cold conversion for the short sequence: **43.95 ms**;
- identical sequence with cached tables: **2.53 ms**.

This is a concrete avoidable real-time stall at exactly the observed rate
change, on top of DSP execution, USB status work and callback scheduling.
The successful 6312 call crosses the same edge without an underrun, consistent
with variable remaining FIFO headroom. These measurements identify a strong
contributor; they are not a full live per-function profile ruling out every
other scheduling delay.

## Implemented preflight and verification

`AppleLine` now prepares both resampling directions, native tables/bindings and
26 exact/common/transient 403 clocks before starting the helper. Histories and
actual clock boundaries are retained. `prepare_codec_rates()` permits additional
rates only on-hook; an unprepared active rate fails closed instead of allocating
FIR tables during the call. Reports expose `prepared_codec_rates`,
`preparation_ms` and `live_filter_misses`.

- `preflight-benchmark.json`: **44.47 ms cold → 2.65 ms prepared**, zero live
  kernel builds; benchmark opens no hardware.
- `prewarmed/6313/`: **698.48 ms** preparation before opening the line;
  **97,362** native polls; no live filter misses or active sample loss.
- Asterisk routes **6004 → 6313**, ANSWERED, **25 billed seconds**; see
  `prewarmed-6313-cdr.json`. The worker exits **0**, returns `NO CARRIER`, and
  releases the hook. There is still **no CONNECT**.
- `verification.json` retains the 130-sample failure versus the clean retry.
  FIFO sizes, priming and strict active-error policy are unchanged.

The subsequent [negotiation investigation](../apple-negotiation-6313/README.md)
independently decodes CRC-valid INFO0 in both directions in this capture. A
longer, separately attenuated call also crosses the retune without a filter
miss, but eventually suffers a **different, late 55-sample active underrun**
after 44.9 seconds off-hook. Its helper log is authoritative; the failed socket
reply leaves Python's reported gap counter stale at zero. This remains open.
