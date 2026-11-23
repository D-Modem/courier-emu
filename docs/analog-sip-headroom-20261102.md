# Analog SIP quiet-pass scheduling and vmhost headroom

## Profile first

The user-requested follow-up to the [vmhost comparison](analog-sip-vmhost-20261102.md)
profiles an **offline replay**, not a live call. A fake SIP session replaces
sockets, disables wall pacing, and supplies saved PCM at the amount requested
by the transmit handoff. Original CPU/DSP firmware still runs. This is a
repeatable scheduling/workload comparison, not a modem interoperability test.

The initial 100-million-instruction profile had 1,562,500 Python service
passes: one every 64 CPU instructions. Native DSP stepping accounted for
about 2.1 s of the 71.8-s profiled run. Much more time was spent running
scheduler/interrupt/lane bookkeeping between the 4096-instruction DSP and
exchange batches. Profiling materially perturbs runtime; do not use the
profiled wall time as a real-time benchmark.

## Correction

`CourierDspBridge.sip_clock_waiting()` identifies a SIP adapter pass which
ends **strictly before** its next DSP batch, exchange batch and codec-service
deadline. It requires an active/launched core, no error or pending runtime-ready
transition, and no physical/socket `line` backend.

For these passes:

- The Python fast path performs the same clock-counter updates as the full
  clock's early return.
- The existing native worker can recognize timer/XF/EOI state without crossing
  back to Python for each quiet 64-instruction pass.
- Native elision stops before either the DSP or exchange batch, ordinary
  timer max-count, board tick, serial scheduling, end-of-run and probe deadlines.
- Native boot/overlay events, changed panel writes and other existing I/O/IRQ
  guards return execution to Python. Quiet native passes never run the DSP,
  resampler or socket/exchange service, or charge extra DSP cycle debt.
- Arming a quiet pass does not construct/copy a DSP/line/resampler snapshot.

The 64-instruction IRQ-recognition interval, DSP oscillator ratio, batch sizes,
modem firmware, buffer reserves, carrier detection and backlog limits are
unchanged. Automatic native XF use is limited to these **pre-batch quiet** SIP
passes. Existing native XF paths that step the DSP still require explicit
`COURIER_WORKER_POLL=1`. `COURIER_WORKER_POLL=0` disables native polling, and
`COURIER_FAST_SERVICE=0` retains the full cooperative service path for controls.

## Offline comparisons

Same 100-million-instruction offline replay, on vmhost CT 127, Clang 19 builds:

| Implementation | Unprofiled process wall time |
| --- | ---: |
| Original | 32.186942 s |
| Python quiet fast path | 30.139015 s |
| Initial native quiet path | 27.083454 s |
| Native quiet path with lean arming | **17.579498 s** |

That last observation is about 45% less wall time (1.83x work rate) than the
original. These are individual observations, not a statistical performance
qualification. Parsed **complete JSON reports were identical** to the original
at every stage, including registers, interrupt/timer counts, DSP state, audio
statistics, queues and firmware outputs. The fake session is not a real-time
source or proof of successful modem training.

## Regression evidence

- **187 focused local tests pass**, covering quiet counters/guards, actual
  native no-DSP execution, hard deadlines, overlay-event yield, XF/IF/EOI
  semantics, frame defaults/cadence, DTE timing and existing SIP/RTP/native
  machine/port/receive/resampling controls. No full-suite claim.
- **68 focused Linux tests pass** in the isolated vmhost snapshot.
- Native XF tests run both ordinary DSP-stepping and quiet modes. Quiet mode
  recognizes identical frame/EOI boundaries without executing DSP instructions
  or modifying audio/debt/line counters.
- A loopback receive test now prequeues a known 300-ms timestamped train rather
  than using repeated relative sleeps to generate it. Under host load those
  sleeps accumulated enough delay to make the *test sender* genuinely late.
  This unit test isolates receive-worker independence; live loss gates were
  not relaxed.

## Live repeat: host-side pacing fixed in these windows, carrier not established

Same bounded calls as before: original 403 ROM, factory S39=8, automatic
modulation, account 6000, 150 million instructions, unchanged adapter/RTP/TX
reserves. Isolated snapshot remains `/root/courier-sip-20261102-113720` in CT
127; existing deployment and PBX/endpoint settings are untouched.

| Observation | 7900 | 7910 |
| --- | ---: | ---: |
| Process exit / timeout | 0 / no | 0 / no |
| Total wall time including boot/dial | 43.94 s | 43.98 s |
| Adapter active silence-filled samples | **0** | **0** |
| Adapter receive rebuffer events | **0** | **0** |
| RTP late packets / missing samples | **0 / 0** | **0 / 0** |
| TX rebuffer events | **0** | **0** |
| Maximum reported TX interval | 35.04 ms | 31.97 ms |
| Maximum local receive-service interval | 24.24 ms | 23.10 ms |
| Adapter queued-audio peak | 2191 samples | 1943 samples |
| Modem CD / online mode at end | off / false | off / false |
| Received/transmitted DTE data bytes | 0 / 0 | 0 / 0 |

This contrasts with the previous vmhost calls failing the two-second backlog
limit and showing captured outgoing gaps of 154–170 ms. The new calls have no
reported CPU/DSP/media errors, no backlog exception, and captures report zero
kernel capture drops. All test channels cleared and no test processes or
captures remained active at the final check.

**Neither call demonstrates modem CONNECT within its bounded window.** Serial
result text is empty, not a captured final NO CARRIER result. Process duration
is not connected modem duration. There is no verified payload exchange,
long-connect/BER/throughput qualification, or independent far-end delivery
measurement. These results clear the observed host-side pacing problem in
two windows; they do not establish sustained reliability under arbitrary load.

## Provenance and next investigation

`.artifact-archives/analog-sip-vmhost-quiet-20261102/` contains baseline and
optimized offline reports/timings, profiles, replay script, per-peer commands,
JSON reports, PCM WAVs, pcaps, capture logs, channel snapshots, summary and
copies of the changed source/tests. Snapshot source includes existing local
uncommitted changes; it is not a clean revision.

The subsequent [600-million-instruction runs](analog-sip-long-connect-20261102.md)
reach real `CONNECT 31200/ARQ/V34/LAPM/V42BIS` on **both** destinations, deliver
the 7900 lab menu and FCS-valid PPP LCP requests from 7910, and retain carrier
through their end. CD first asserts at 188/201 million instructions—beyond
these earlier short windows. Those results establish carrier and received DTE
output, but not bidirectional payload, BER, throughput or V.90 qualification.
Do not treat SIP 200 OK or clean queues alone as modem CONNECT.
