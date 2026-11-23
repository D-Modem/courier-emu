# Hardware 7930: media timing investigation

## Baseline: PPP recovery is not sufficient

`hardware-7930-stopwait-600s` negotiated 48000/V90/LAPM, authenticated and
completed IPCP. Ten of eleven 512-byte peer pings returned exactly, with no bad
replies or PPP FCS errors, before NO CARRIER at 187.6 connected seconds. RTTs
included 31.3 and 45.5 seconds. This is not a completed ten-minute test.

Full baseline results:
`artifacts/sip-hardware-timed/courier-hardware-timed-20261106-092949-7930-stopwait/`.

The final SIP media report records four TX rebuffers and a 193.35-ms maximum
transmit packet gap. RX had zero sequence gaps and no late packets, but 62
missing playout samples across the session. These aggregate observations do not
prove which outage caused which PPP stall. The remote peer sent SIP BYE.

## Bounded timing telemetry

`RtpTransmitStats` now separately records producer sample totals and maximum
producer gap, and a bounded 32-entry rebuffer history containing monotonic time,
queued samples and the age of the last nonempty producer submission. This
separates production outages from sender scheduling jitter. Empty producer
calls do not reset that age. The telemetry neither fills nor discards audio.
The PPP instrument reports its monotonic origin for time correlation.

Focused local tests: 61 passed across RTP producer/media-clock, SIP scheduling,
receive reserve, receive-clock and playout regressions. The isolated remote
snapshot passed 38 existing focused media tests after instrumentation.

## 20-ms block control (not yet a promoted default)

The analog exchange/line bridge defaults to 100-ms blocks; RTP packets are
20 ms. The existing COURIER_LINE_FRAME_MS override allows a matched control at
20 ms without changing firmware, clock frequencies, six-bank ASIC capacity,
receive queue capacity, 150-ms TX reserve, 40-ms receive reserve, CRC handling,
PPP keepalives or acceptance checks. The smaller block reduces the audio
producer's burst quantum. Whether it cures the observed outages requires the
live measurement; it is not assumed.

This control retains the prior no-compression/required-LAPM settings, extra PPP
control quoting and one outstanding ping. The target is 600 live seconds after
genuine CONNECT, with the last 20 seconds reserved for drain. Modulation is not
forced and must be reported from the actual result.

Remote snapshot: `/root/courier-hardware-timed-20261106-092949` in vmhost CT127.
Output: `hardware-7930-frame20-600s/`.
Local collection:
`artifacts/sip-hardware-timed/courier-hardware-timed-20261106-092949-7930-frame20/`.
The 20-ms block control also failed: 40000/V90/LAPM, eight of nine exact
512-byte replies, NO CARRIER at 177.2 connected seconds. RX had zero missing or
late packets and no adapter underruns. TX recorded six rebuffers and a maximum
248.8-ms packet gap, despite a maximum nonempty producer gap of only 95.8 ms.
Several rebuffer events had producer ages of only 20–36 ms. Smaller blocks
alone do not solve the problem and are not promoted as a default policy.

## Sender grace correction

The independent media sender previously treated any empty packet slot as a
sustained production outage, immediately rebuilding the entire 150-ms startup
reserve. That amplifies small producer deadline jitter into a large media hole.
It now waits up to one 20-ms packet interval before re-priming. A packet that
arrives during that interval is sent with its original sample timestamp; no
samples are fabricated, discarded, stretched or duplicated. A longer outage
still increments the rebuffer counter and rebuilds the original reserve.
Receive buffers, capacities and PPP timeouts are unchanged.

Regression tests prove that a five-millisecond-late packet is transmitted
without re-priming, with exact payload and timestamp progression, while partial
packets are retained and a sustained outage still re-primes. Local focused
suite: 63 passed. Isolated remote focused suite: 44 passed.

A matched repeat retaining the 20-ms block and all other control settings is
running as `hardware-7930-grace-600s/`; local collection suffix `-7930-grace/`.
This is a targeted sender correction, not yet proof that PPP stays up for ten
minutes. The grace repeat failed at 90.9 connected seconds: 41333/V90/LAPM,
five of six exact replies, two TX rebuffers, a 204-ms TX gap, and 360 active
adapter receive-underrun samples. The network receive report had zero missing
or late playout samples. Grace alone does not fix stability.

## Pre-reset clock audit

Final reports are captured after the guest resets the DSP at hangup. The core
in those reports therefore cannot establish whether the *previous* data-mode
ADC underflowed. `courier_emu.analog_clock_audit.AnalogClockAudit` now samples
live codec cycles, primary/empty-frame counters, FIFO occupancy, serial sample
counts, bridge TX totals, adapter pending/underruns, RTP counters and the raw
403 BLER cell once per instrument checkpoint. It verifies the CPU ROM signatures
before interpreting the low-RAM address, marks core-replacement/cycle-reset
epochs, and never writes firmware or core state. The instrument skips sampling
after the native core closes. Samples are retained in `clock-audit.jsonl`.

The raw BLER cell is explicitly a physical-RAM snapshot, not an ISR-context
interpretation. Resets must not be treated as negative counter deltas. Tests
cover retained pre-reset values, signature rejection, and epoch separation.
Thirteen audit/media tests passed locally and in the isolated remote snapshot.

The audit repeat negotiated 31200/V34/LAPM and completed 22 of 23 exact
512-byte replies before NO CARRIER at 197.018 connected seconds. PPP FCS errors
were zero. In the pre-reset data epoch, the DSP receive-empty counter stayed
constant and the FIFO stayed populated. The final reset epoch (7200 Hz, 149
empty frames) must not be attributed to the preceding data connection. Raw
physical BLER rose from 0 to 10. TX recorded seven rebuffers and a 241.467-ms
maximum packet gap.

Several approximately one-second intervals produced only 5500–6700 RTP samples
per wall second, against the required 8000, while guest instruction throughput
fell to about 2.3–2.9 million/s. Adapter receive backlog grew during these
intervals and could subsequently shrink again. An uninterrupted sequence of
producer calls is therefore not evidence of sufficient production *rate*.
This identifies real-time headroom/accounting as an investigation target; it
does not prove that every BLER increment came from an RTP rebuffer.

## Worker profiling and execution overhead

Sampling used py-spy 0.4.3 from vmhost's PID namespace, without changing ptrace
policy or injecting code into the emulator. Native unwinding failed with
`UNW_EBADREG`; the usable profiles are Python-stack samples at 49 Hz for 60
seconds, with 2939 main-thread samples each. A later attempted timeline profile
of the UART control lost its target at process exit and is not usable evidence.

Indicative main-thread wall-time shares:

| Path | Profile control | Extraction/timer-cache change |
| --- | ---: | ---: |
| Native DSP execution | 27.7% | 27.8% |
| Native-poll preparation | 9.5% | 8.0% |
| Codec extraction/resampling | 6.9% | 2.3% |
| Pacing wait | 12.7% | 21.3% |

The profile control negotiated 29333/V90/LAPM; the changed run negotiated
31200/V34/LAPM. These are not a same-modulation controlled CPU benchmark.
They locate substantial Python/FFI overhead, but do not establish a stability
improvement. The initial profile attempt did not reach CONNECT.

Implemented changes:

- Bounded memoization of exact timer-tick inversion, keyed by both absolute
  deadline and clock ratio, so boot-time clock discovery cannot reuse a stale
  conversion. The original float-to-integer boundary semantics are retained.
- Avoid copying unused DSP debt/CPI fields when arming a quiet SIP poll.
- **Opt-in** `COURIER_SIP_CODEC_BATCH=1`: amortize codec PCM extraction over
  sixteen samples, without batching DSP execution. The original ROM's minimum
  7200-Hz codec rate bounds the added extraction delay to about 2.23 ms.
  Stalled short tails are drained on the next pass. Tests compare exact output
  samples and retained tails, including retunes inside undrained batches.
- Online UART transmit work can be elided only until its next stop/end event,
  and never over a pending interrupt. MMIO accesses still advance the UART at
  the access instruction. The native poll is explicitly bounded by that event.
  Double-buffer and interrupt timing are regression-tested against advancing
  the UART on every scheduler poll.

All controls retain the same original firmware, real negotiation, required
LAPM/no compression, extra outbound PPP control quoting, stop-and-wait 512-byte
pings, 20-ms bridge blocks, and the 600-connected-wall-second target.

| Run suffix | Actual CONNECT | Connected seconds | Exact/sent | TX rebuffers | Maximum TX gap |
| --- | --- | ---: | ---: | ---: | ---: |
| `profile2` | 29333/V90/LAPM | 187.618 | 22/23 | 7 | 260.4 ms |
| `perf` | 31200/V34/LAPM | 165.885 | 18/19 | 5 | 230.5 ms |
| `uart` | 31200/V34/LAPM | 193.470 | 29/30 | 5 | 222.5 ms |

All ended in NO CARRIER, with complete serial captures verified against the
reported byte count. These are failures, not ten-minute qualifications.
Artifacts use the corresponding `-7930-<suffix>/hardware-7930-<suffix>-600s/`
paths under `artifacts/sip-hardware-timed/`.

## Byte-event receive deadline

Further inspection found a needlessly restrictive online receive deadline:
Python was re-entered at every DTE data-bit edge. Such edges do not update
state that requires service. `DteTransmitLine.level()` derives the pin from the
instruction count, and the actual FF5A MMIO read hook calls `sync_device_time()`
before observing it. It is not a cached input requiring per-bit refresh.

The online quiet deadline now extends to byte completion, still bounded by any
earlier transmit event, DSP/exchange batch deadline, timer deadline, board tick,
new scheduled input, and run end. Unmasked start edges and pending UART requests
remain cooperative. Command/autobaud modes are not relaxed. The masked INT1
start-edge latch is preserved. This does not accelerate the DTE baud rate or
change any character, sample, firmware instruction, or interrupt deadline.

A native-machine regression executes 150 real FF5A reads across multiple data
bits, all before the first scheduler service, and checks every returned pin
against its access instruction. Constant-0, constant-1 and mixed data patterns
pass with the captured 403 ROM on both local and isolated Linux runtimes.
Other tests retain byte-completion, full-duplex TX-deadline, pending-interrupt
and masked-edge guards. Local focused suite: 185 passed. Remote focused suite:
110 passed plus the three native FF5A tests (initially skipped due to an
optional older ROM path, then rerun successfully with the captured 403 image).

The byte-event control `hardware-7930-byte-600s/` ran without a sampling
profiler and retained the opt-in extraction batch. It negotiated
37333/V90/LAPM but lost carrier after about 24.6 connected seconds, before PAP/
IPCP completed. There were no binary pings and **zero TX rebuffers**; the maximum
TX packet gap was 35.2 ms. LCP repeatedly restarted with new peer magic numbers.
This run cannot qualify binary performance or attribute all carrier failures
to TX queue depletion. Its complete serial capture passed length validation.
Runtime source copies and native-binary SHA256 hashes were retained; no
process environment or SIP password was saved.

The V.34-only control `hardware-7930-byte-v34-600s/` used the firmware's
S58=33 setting (disable x2 and V.90), rather than altering a DSP payload or
negotiation result. It negotiated 31200/V34/LAPM, authenticated and transferred
142 exact replies out of 143 requests, with zero PPP FCS errors, before NO
CARRIER at **487.809 connected seconds**. Seven TX rebuffers remained, with a
209.740-ms maximum gap. It did not pass the ten-minute test. The forced-V.34
setting is an additional variable, so this alone does not isolate the benefit
of the byte deadline from negotiation-path differences.

## First-packet recovery control (opt-in)

A sustained TX underflow still forced the sender to rebuild its full 150-ms
startup reserve. The production gaps in these controls were at most about
100 ms, whereas actual outbound gaps reached 180–260 ms. Requiring a new full
reserve is an avoidable extra hold, not a missing-sample requirement.

`COURIER_RTP_PACKET_RECOVERY=1` retains the original startup reserve and 20-ms
underflow grace, but after starvation resumes with the first complete packet.
It re-anchors the wall-clock deadline at recovery, just as full re-priming did,
without adding a fresh startup-reserve wait. Queued partial packets are retained;
no source samples are padded, removed, repeated, or retimed, and sequence/
sample-timestamp progression is unchanged. The existing rebuffer counter/history
still records every recovery event, so this does not hide underflows. SIP status
reports the enabled mode and whether recovery is pending. Disconnect/hangup
restores normal startup priming.

Tests cover both PCM scheduling and raw codewords: unchanged initial reserve,
exact partial-packet concatenation, exact sequence/timestamp progression,
no artificial catch-up burst, retained underflow telemetry, and recovery reset
on disconnect. Local focused suite: **188 passed**. Isolated remote focused
suite: **116 passed**. This mode is experimental and off by default.

`hardware-7930-packet-v34-600s/` tested this initial recovery policy against
the same V.34-only setting, without a sampling profiler. It still failed at
468.105 connected seconds: 31200/V34/LAPM, 121 of 122 exact replies and one
outstanding, with 59 recovery events but only a **34.99-ms** maximum packet gap.
Small individual packet gaps did not establish a healthy sample clock.

## Accumulated RTP clock slip

`setup/analyze_clock_slip.py` compares PCAP arrival time with the RTP timestamp
clock, separately by SSRC and direction. For the completed captures:

| Run | TX wall span | TX RTP sample span | Final TX slip | Maximum TX gap |
| --- | ---: | ---: | ---: | ---: |
| `audit` | 213.365 s | 211.900 s | 1465.2 ms | 241.5 ms |
| `byte-v34` | 465.902 s | 464.620 s | 1281.7 ms | 209.7 ms |
| `packet-v34` | 446.809 s | 445.480 s | 1328.5 ms | 35.0 ms |

RX final phase offsets were only about -12 to -28 ms over these captures.
These spans are the SIP media streams, not connected-time test durations.
The 59 small recovery resets accumulated about as much permanent TX delay as
seven large resets. Resetting `_next_rtp_at` on each recovery also concealed
this in the per-packet deadline-lateness metric.

The experimental packet-recovery implementation now preserves the **original
wall-clock deadline** as well as the RTP sample timestamp. Only initial startup
anchors the clock. After a temporary underflow, genuinely overdue queued
packets may catch up, but packets whose deadlines have not arrived are never
sent early. No source samples are fabricated, discarded, repeated, or stretched.
Existing underflow telemetry remains active. This supersedes the re-anchoring
policy tested by `packet-v34`; its original runtime source is retained in that
capture directory.

`RtpTransmitStats` additionally tracks sent sample totals and current/maximum
sample-clock lateness against an independent initial reference. A regression
shows that 101 packets spaced 21 ms apart can have zero per-packet deadline
lateness yet accumulate 100 ms of sample slip if the deadlines are reset.
Other tests prove real catch-up returns to the original clock phase and never
sends future-deadline packets. Local focused suite: **190 passed**; isolated
remote suite: **118 passed**.

`hardware-7930-clock-v34-600s/` is the matched live control for preserved-clock
recovery. Test completion now also snapshots SIP-connected, modem-online and
PPP-up state **before** intentional shutdown, so a delayed NO CARRIER after
an earlier SIP BYE cannot accidentally qualify a completed timer. Whitelisted
settings and runtime sources/native-binary hashes are retained.

This control reached **600.012 connected seconds**, with SIP connected,
modem-online and PPP-up state all true before intentional shutdown. It
negotiated 31200/V34/LAPM, with zero PPP FCS errors and 86 exact replies out of
87 requests. **One remained outstanding**, so this is a connected-time
milestone, not a clean binary-data qualification. A late reply took 35.29 s.
The complete 49,147-byte serial file matched the native count; no native error
or watchdog expiration occurred.

The pre-stop audit showed current sample-clock lateness of about 0.3 ms and a
maximum of 507.8 ms. Unlike the earlier reset policy, lateness could return to
the original phase. Full PCAP TX phase ended 36.6 ms late rather than 1.3 s.
The full capture's maximum packet gap was 145.1 ms, versus 45.2 ms in the last
pre-stop audit; these measurements have different boundaries and must not be
substituted for each other. Subsequent controls record an explicit wall-time
end marker to separate the test window from shutdown packets. The 3484 counted
recovery transitions are not 3484 long network packet gaps: repeated packet
starvation while behind the retained clock can increment this counter until
production catches up.

## Remaining real-time headroom: compiler control

A separate 180-connected-second profiling run uses buffered 20-ms DTE activity
snapshots and a 60-s, 49-Hz Python-stack timeline. This is an instrumented
performance investigation, not a 600-second qualification. It associates
samples with receive-active, transmit-active or quiet UART intervals rather
than attributing the entire profile to serial traffic. DSP execution accounted
for roughly 36–42% of main-thread samples; native-poll preparation about 9–10%.
Pacing wait was approximately 10% in quiet intervals and 4% in serial-active
intervals. The short TX-only group had only 79 samples and is not a precise
benchmark.

ELF metadata confirmed the deployed C5x library used GCC 12, whereas its hot
threaded dispatch contains Clang-specific call-site inlining/tail-call
attributes. A separately named **Clang 19** build of the same native sources
passed **183 C5x/native-scheduler tests**. Synthetic kernels measured for five
wall seconds each gave about 14% faster NOP/branch throughput and 8% faster
162-tap MACD throughput. These kernel results are not a real-modem speed claim.
The existing runtime library was not overwritten.

`hardware-7930-clang-clock-v34-600s/` compares the explicit Clang library with
the preceding preserved-clock control, using identical firmware, S58=33,
traffic, buffers and protocol checks, without a sampling profiler. The chosen
prebuilt-library path is recorded in the whitelisted settings and its SHA256
is retained. It completed **600.003 connected seconds** at 31200/V34/LAPM,
with connection-valid-at-end true, zero PPP FCS errors and **103/104 exact**
replies (one outstanding). No native error/watchdog expiration; complete
58,521-byte serial capture validated. This is still **not a clean data pass**.
Pre-stop peak sample-clock lateness fell to 271.1 ms; recovery transitions were
3013. PCAP through the explicit test-end marker independently measured a
270.8-ms peak, **0.091-ms final TX phase**, and 39.47-ms maximum TX packet gap.
The entire capture, including shutdown, instead had a 128.27-ms maximum gap.
The difference demonstrates why the qualification boundary must be retained.

For reproducible builds, C5x runner/library builders now honor `CXX` (including
compiler wrappers), retaining `c++` as the unchanged default. For example,
`CXX=clang++-19` with `build_library(force=True)` explicitly rebuilds with that
compiler; an existing `COURIER_C5X_LIBRARY` override still takes precedence.
Compiler selection uses an argument vector, not a shell. Local focused suite,
including compiler selection, DSP operations and native scheduling: **379
passed locally; 373 passed, six optional-fixture/driver skips on vmhost**.
Prebuilt-library overrides were used for these full suites to avoid redundant
forced recompilations in individual DSP tests.

## Poll preparation and bounded DSP-coupling control

Native poll preparation now initializes eight run-invariant configuration
fields once rather than on every arm, and declines to copy a snapshot when
the very first native poll would already reach the cooperative-service
boundary. Dynamic timer deadlines, clock discovery/cadence, core identity,
interrupt stack, codec activity and clock debt remain live. A regression test
uses the captured CPU firmware and a **synthetic, local-only idle DSP loop**
(no SIP network) to compare native versus cooperative CPU registers/RAM,
interrupt counts/stack, DSP register state and bridge clock/debt counters.
This synthetic test is not hardware/audio qualification evidence.

The `arm-clock-v34` hardware follow-up ran **660.015 connected seconds** at
31200/V34/LAPM, 122/123 exact replies, zero PPP FCS errors, connection valid at
the intentional endpoint, peak sample-clock lateness 247.4 ms. It still had
one outstanding request and **did not pass clean data**. Replies continued
past 600 connected seconds, ruling out a universal hard 600-second data cutoff
on the peer. A modest peak reduction versus the preceding run is not a
controlled CPU-performance measurement.

The next isolated control, `batch1024-clock-v34`, uses the existing diagnostic
`--dsp-batch 1024`, instead of default 256, retaining Clang, preserved RTP phase,
all samples, clocks, checks, buffers and genuine negotiation. This changes
**CPU/DSP coupling granularity**, not either processor's clock or codec-sample
content; it remains an explicit diagnostic, not a new default. The receiver
already clamps larger diagnostic batches to 1024 on streaming-mode entry to
avoid publishing more than six ASIC-bank bytes between CPU acknowledgments.
1024 CPU instructions bound coupling to approximately a quarter millisecond;
this experiment tests reducing Python bridge/poll preparation frequency
without increasing queues or inserting audio. Configured and effective batch,
pre-reset serial/FIFO counters, full serial data and PCAP must be checked.

**This control failed**: NO CARRIER at approximately 502 connected seconds,
114/115 exact replies, one outstanding. The first 129 connected seconds had
zero TX recovery transitions and raw BLER zero, but later peak sample-clock
lateness reached 275.1 ms, recovery transitions 777 and raw BLER eight. The
receive-empty counter stayed 149 through the online epoch; the final reset
raised it to 151 and must not be confused with a preceding data-mode underrun.
The diagnostic batch remains opt-in; no default was raised. Reduced Python
callback frequency alone did not solve the stall.

A short `capi-clock-v34-180s` diagnostic restores default coupling (256), keeps
the explicit Clang library and samples one in 128 DSP-step/native-CPU calls.
It records wall time **and main-thread CPU time**. Python stack time inside a
ctypes call need not all be native computation: it can include waiting to
reacquire the GIL. The audit now also records thread/process CPU clocks. These
measurements distinguish real computation from scheduling/GIL waits before
choosing another performance change. CT127 has four CPUs, no CPU quota
(`cpu.max=max 100000`), and zero recorded CFS throttling. This diagnostic is
not a 600-second qualification.

## Native dispatch improvement and remaining failures

The C-API timing control completed **180.001 connected seconds**, with 43/43
exact replies. Its sampled DSP calls used 0.482 s of thread CPU for 0.485 s of
wall time. This does **not** support GIL reacquisition as the dominant DSP-call
cost; no GIL-holding runtime mode was introduced.

A separate native CPU-IP profile (`perf-native-v34-180s`) collected about 11k
user-space samples at 199 Hz for 60 wall seconds, with zero lost samples.
It required no ptrace/perf-policy changes and recorded no stack contents or
process environments. Debian perf and dependencies were extracted privately
rather than installed system-wide. Python frame evaluation accounted for
30.9% of samples, the native x86 run loop 4.0%, and threaded DSP handlers made
up numerous leading entries (SACH 2.27%, MAC 2.21%, SACL 2.05%). This diagnostic
subsequently failed PPP echo recovery at **142.223 connected seconds**, 49/50
exact; it did not complete its intended 180 seconds. Host-owned perf recordings
were assigned to the container output directory's owner before recollection;
complete artifacts, including `perf.data`, were recovered.

Disassembly exposed four sequential front-flag byte-test branches in each
threaded instruction, followed by unconditional interrupt/repeat-state work.
`native/c5x_core.cpp::step_is_rare()` now uses an alias-safe, bounded four-byte
`memcpy` test plus the fifth entry flag, and returns immediately when no enabled
interrupt is pending. It retains the existing NMI, IDLE, **IDLE2**, diagnostic,
entry, INTM, repeat and BRAF decision. A layout assertion protects the packed
read. No opcode behavior, cycle accounting, firmware, sample content, queue
capacity or PPP timer was changed. New tests explicitly check IDLE2 stopping
fetch and waking on a masked peripheral edge, in both stepping paths.

Pinned five-wall-second ABBA microbenchmarks on a performance core measured
about **10% faster NOP/branch** and **17% faster scalar-memory** throughput.
The long MACD kernel was approximately flat apart from frequency noise. These
are CPU-specific kernel measurements, **not an end-to-end modem speedup**:
a second check showed smaller gains with a masked pending IRQ, and about a
5.5% regression for that case on an efficiency core. Latest focused regression
suite: **384 passed locally; 378 passed and six optional-fixture/driver skips
on vmhost**, using the revised native library. The same remote suite passed
with both GCC 12 and Clang 19 builds.

The host is an i5-1240P. CT127 allows CPUs **1,3,6,12**; 1/3/6 advertise a
4.4-GHz maximum, while efficiency-core CPU12 advertises 3.3 GHz. The same
scalar kernel on CPU12 was roughly 25–30% slower than CPU1. Read-only 50-ms
`/proc/<worker>/stat` observations confirmed actual worker migrations to CPU12.
This establishes a real host-capacity variable, not proof of the sole cause.

| Control | Connected duration | Exact replies | Result |
|---|---:|---:|---|
| `frontguard-v34-600s`, normal affinity | 582.485 s | 42/43 | PPP echo timeout; peak sample-clock lateness 562.2 ms |
| `pcore-frontguard-v34-600s`, worker-only affinity 1,3,6 | 87.489 s | 0/1 | IPCP stopped receiving Configure-Request responses; peak lateness 208.5 ms |

Both negotiated genuine 31200/V34/LAPM. Their complete serial files validated
at 24,772 and 1,540 bytes respectively; no native error or watchdog timeout.
**Neither passed the requested test.** P-core-only placement did not cure the
failure. Only the test process and inherited threads were restricted; no
container-wide affinity, scheduler priority or host power policy changed.
The test runner validates requested CPUs against its existing allowed mask
and records the explicit taskset command and mask. The software hot-path gain
must not be described as a solved hardware-modem stability problem.
