# TX producer timing: next measurement and qualification

## Status

The known live stability defect is not fixed. Existing matched offline replays
validated scheduler reentry correctness and reduced execution cost, but did not
establish live reliability. Rejected SIP/native batching and CPU-affinity
experiments must not be represented as fixes. See
[disconnect investigation](analog-disconnect-investigation.md) and
[V.90 repeated tests](v90-7930-repeated-tests.md).

## Low-overhead measurement

`AnalogClockAudit.sample(now)` now records SIP/line phase, current RTP TX queue
occupancy, and cumulative line pacing observations alongside its existing wall,
thread/process CPU, production, send and codec counters. RTP counters and queue
occupancy are copied under the existing media lock. Rebuffer history is copied
so later worker updates cannot mutate a saved snapshot. There are no new
per-instruction, per-sample or native-call timing hooks.

Use the existing opt-in diagnostic launcher with `COURIER_CLOCK_AUDIT=1` to
collect `clock-audit.jsonl` at its normal checkpoint cadence. The scratch
integration is in `tmp/vmhost-disconnect/timed-ppp-probe/sitecustomize.py`;
this is not a new public CLI switch. Deploy the updated audit module with the
snapshot. Old captures without SIP phase are skipped by default rather than
assumed connected. If the same call's CONNECT/end observations independently
verify the data window, `--verified-legacy-connected-window` permits filling
missing SIP phase **only** inside explicit finite `--start`/`--end` bounds.
It never overrides an observed offline or non-connected state, and every
inferred interval is labeled `externally_verified_window`.

Analyze offline, restricting to the actual connected data-test window:

```sh
.venv/bin/python -m tools.analyze_tx_timing /path/to/clock-audit.jsonl \
  --start MONOTONIC_DATA_START --end MONOTONIC_DATA_END > tx-timing.json
```

The analyzer emits adjacent intervals, not a guessed causal classification:

- `production_deficit_ms`: wall time minus newly produced 8-kHz sample time.
- `send_deficit_ms`: wall time minus sent sample time. Negative values retain
  genuine catch-up rather than clipping it away.
- Thread/process CPU deltas, thread CPU fraction and non-thread-CPU wall time.
- Requested pacing sleep delta, queue endpoints and send sample-clock change.

A production deficit with high thread CPU utilization suggests execution-cost
pressure. A deficit with low utilization needs further separation of pacing,
scheduling and other waits. Requested sleep is **not actual slept duration**;
non-CPU time is **not proof of GIL contention or scheduler delay**. Production
without corresponding sends, especially with a nonempty queue, suggests
investigating media-worker service. These are leads, not automatic diagnoses.
Snapshots are block-quantized; compare several intervals, not individual tiny
deltas. There is no interpolation of event times. Intervals crossing observed
SIP/offline transitions, DSP reset epochs or codec changes are excluded. An
unobserved transition between snapshots cannot be detected by this analyzer.
Use one run-thread audit stream per call; do not concatenate unrelated calls.

## Candidate gate

1. Obtain phase-specific evidence of the remaining timing cost before changing
   another hot path. Do not use cProfile as live reliability evidence.
2. Make one narrowly targeted change; preserve firmware, clocks, PCM, queues,
   recognition boundaries and protocol acceptance.
3. Compare complete offline replay reports and alternating-order unprofiled
   execution times. Retain source/native/firmware hashes and host metadata.
4. Run connected matched V.34 controls using the same boot/deployment/network
   path. Keep sender, PBX ingress and gateway-facing captures plus gateway RTCP
   and bounded post-window ATI diagnostics. Exclude the diagnostic tail.
5. Require a genuine 600-second V.34/LAPM connection, authenticated PPP, all
   bounded echoes complete and exact, zero PPP FCS errors, complete DTE capture,
   clean worker exit and SIP/carrier/PPP all still up. Report retrains/resends
   even for a pass. Do not weaken backlog guards or add a final-echo grace.
6. Only then resume V.90 acquisition and long-duration qualification. V.34
   fallback is not V.90 success; a target duration is not completed duration.

Gateway discard counters or post-playout PCM would strengthen causal evidence;
zero RTCP sequence loss alone does not demonstrate clean gateway playout.

No new live calls or performance/stability improvement are claimed by this
instrumentation change.

## Follow-up: existing LAN evidence analyzed, two candidates rejected

The existing `hardware-7930-vmhost-gateway-v34-600s` capture was retrieved
read-only from the isolated remote snapshot. CT127 was temporarily started
for retrieval and returned to **stopped**; no live call or PBX change was made.
The source timestamps and result report identify the connected data window;
10 ms was trimmed from each reported boundary to avoid rounded timestamp
ambiguity. No diagnostic tail was included. Legacy phase inference is explicit,
not newly measured SIP state.

The analyzer retained **593 intervals / 599.290 seconds**:

- Weighted run-thread CPU utilization: **90.37%**; median interval utilization:
  **97.69%**. Weighted and median figures answer different questions.
- Largest production deficit: **211.46 ms** over **1.01146 s**, with **98.71%**
  run-thread CPU utilization, 6,400 samples produced and 6,720 sent. Sending
  consumed existing reserve while production fell behind.
- That interval's send sample-clock lateness grew **183.98 ms**. This is not
  a measured 184-ms individual packet gap.
- Across the full retained window, production approximately caught up:
  4,794,080 samples versus 599.290 s of elapsed wall time. Aggregate throughput
  alone therefore hides the excursions relevant to far-end playout.

This supports execution-cost pressure in this run's worst intervals, rather
than attributing those intervals to a mostly off-CPU worker. It does not prove
CPU cost is the only modem defect, identify a particular expensive DSP opcode,
or measure gateway concealment/discard. Legacy captures lack pacing and actual
queue snapshots; those are reported as unknown, not reconstructed from counters.

Two narrowly bounded experiments did **not** pass an execution-cost gate:

| Candidate | 300M-instruction control wall s | Candidate wall s | Decision |
| --- | --- | --- | --- |
| Timer no-wrap branch before `divmod` | 16.961 / 16.792 | 17.201 / 17.325 | Rejected; source reverted |
| Native library ThinLTO, same compiler/options otherwise | 16.847 / 17.300 | 16.888 / 17.210 | No measurable benefit; not enabled |

Both comparisons were local macOS arm64, unprofiled socket-free replay, ABBA
order. These are not vmhost measurements. Every complete parsed report matched
within each comparison, and no timing/buffer/firmware/acceptance parameter was
changed. The timer experiment additionally matched the old implementation
across all 65,536 control words at six elapsed values and randomized writes,
wraps and single-shot cases. An isolated long-period timer microbenchmark was
about 8% faster, but the full replay did not benefit; the microbenchmark did not
justify retaining the runtime change. ThinLTO was built only into an explicitly
selected scratch library, never the default native library.

Private/scratch evidence is retained under `tmp/tx-timing-followup/`: the original
captures/results, `legacy-analysis-command.json`, `legacy-analysis.json`, replay
reports/times, rejected timer patch and differential tests, library variants,
and `manifest.json` with source/firmware/fixture/library hashes and host/compiler
metadata. The snapshot was already dirty; this is not a clean-revision claim.

A subsequent [runtime-selected x86 FMA optimization](resample-fma-performance.md)
reduced matched vmhost offline replay time by approximately **2.8%**, with
identical complete reports and RX/TX audio hashes. It is retained as an
execution-cost improvement, not a validated carrier-stability fix.

The remaining implementation target is still reducing connected-phase execution
cost without changing clocks or audio. The short saved connected-phase profile
puts DSP stepping and supervisor/scheduler service ahead of the resampler;
use that to select the next candidate, but require an unprofiled replay win
before another live qualification call. Neither rejected experiment is a
carrier-stability fix.
