# Paired I-modem / analogue Courier: where the time goes

We measured this on the documented x2 call (53333, the two payloads), with 120 s of line time:

| Build | Wall time | Versus real time |
|---|---|---|
| Original | 485 s | 4.0x |
| After the first round of changes | 372 s | 3.1x |
| Native lanes, cheap DSP probes | 250 s | 2.1x |
| Native I-modem port model | 216 s | 1.8x |
| Batched PCM exchange | 209 s | 1.7x |

The I-modem process is the limit (about 199 s of CPU against 165 s for the
analogue worker). About one third of it is in the C5x interpreter, and the remaining part is in
Python: the 8 kHz PCM exchange with the DSC (about 960k frames), the service pass for each
chunk, and the port accesses that still leave the native engine.

## Switches

- `COURIER_NATIVE_IO=0` runs the lane ports and the DSP advance of the I-modem through
  the Python handlers, and not through the native port model. The complete state of the
  I-modem is bit-identical in the two cases. Use it to bisect a behaviour change.
- `COURIER_LINE_WINDOW=N` (with a smaller `COURIER_LINE_FRAME_MS`) lets each
  modem run N-1 line frames before the other. It did not help here, because
  neither process waits long. Also, it changes the negotiated rate (52000). Thus, it
  is off by default.

## The PCM exchange

Each 8 kHz frame that the DSP of the I-modem completes is exchanged with the DSC model
in Python. The DSP now continues through some frames between visits:

- The network side of the next frames comes only from the B-channel queues of the DSC
  (for an ordinary call). Thus, it is known before the time and given to the
  core (`Am79C30.bearer_take_ahead`), but only up to the octets that are really in the queue
  on the channel of the call. All other cases (an empty queue, a line that is down,
  a route that loops one peripheral slot to another) use the
  frame-at-a-time path.
- The native advance stops for a reply, a transmit backlog or an empty
  receive queue. It does not stop for each frame, and the completed frames are exchanged in
  bulk (`bearer_finish_batch`).
- The frames are still exchanged at the start of each poll, before the bearer
  reads what the modem sent, and near each write to the DSC, because the
  stall logic of the bearer and the MUX registers need that. For this reason, the gain
  is small: there is no later point to which the work can move without a change of the
  timing of the line. (A later point saved more CPU, but it changed the negotiated
  rate to 49333-52000.)

The state of the I-modem agrees bit for bit with the one-frame-at-a-time path, except
the receive octets that are held ahead. `COURIER_PCM_BATCH=0` disables it.
`COURIER_PCM_BATCH=1` runs the lookahead with a flush after each frame.

## What did not help

- A cache for repeated status reads: only about 10% repeat an unchanged answer.
- A service of the BRI on every second poll: no change in CPU.
- A timer poll of 1024 instructions or a read quantum of 128 instructions: both change
  the negotiated rate or the run length.

## What would

A native service of the `0x1c`/`0x1e` ports of the mailbox on the two modems, and a
faster C5x interpreter (its cost is spread over fetch, addressing and cycle
accounting, and not in one hot spot).

## C5x interpreter

The diagnostic probes for each instruction (V.8 dispatch capture, negotiation-loop
snapshot, ISR trace) are now off by default. To enable
them again, set `COURIER_DSP_PROBES=1`. `COURIER_C5X_LIBRARY` names a prebuilt library, for A/B runs.

Then we changed the structure of the interpreter itself. We checked each step for identical
results from the two processes:

- `step()` takes a short path unless a vector, IDLE,
  the overlay entry, block repeat or a diagnostic is pending.
- The timer is updated only when an expiry is due or when its registers are used, and the
  frame-rate events share one deadline.
- Byte tables classify the program and data space
  (cached for each combination of CNF/OVLY/RAM/MP-MC/GREG, because some firmware
  changes CNF in a tight loop).
- Opcodes dispatch through plain function pointers.
- The common indirect addressing modes and the on-chip RAM accesses are inlined.

On the filter-loop microbenchmark, this is 26.4 -> 13.5 ns for each DSP instruction
(247 -> about 145 host instructions each). On the full call, the interpreter is
now only about a fifth of the I-modem process (Python is two thirds). Thus, the wall
time stayed at about 214 s: Python limits the call, not the interpreter.

We tried these changes and then removed them, because alternating A/B runs showed no gain (the fast build
was 3-5% slower in wall time): a circular-buffer mask for indirect addressing,
an inline timer fast path in `step()`, and higher inline limits of the compiler.
At about 250 host instructions for each DSP instruction, the cost is spread across
`step()`, addressing, dispatch and memory access. Thus, a useful gain needs a
structural rewrite of the dispatch/fetch/memory path, and not local changes.

## Python glue

A sampling profile of the full call (each 5 ms of CPU, the two processes) gives
the I-modem at about one third native (C5x 20%, 386 engine 14%) and two thirds
Python, and the worker at about 27% native and 58% Python. The Python part is a long
flat tail: no function above 4%, and a few dozen between 0.7% and 3%.

We trimmed these items, with results that are bit-identical to before:

- One native call collects what a
  DSP service pass reads (status, reply registers, transmitted octets), in place of
  five calls.
- The PIT counters are skipped until a wrap is due.
- The console pumps frame and
  slice only when there is work to do.
- The T200 walk is skipped when no
  timer has expired.

That is 13% fewer Python calls, and the full call went from
214 s to 206 s.

The profile shows what remains, for the next person who works on real time:

* In an active call, about 80% of polls have a PCM batch to exchange. Thus,
  if we skip idle polls, we save little. The exchange itself (flush, prefeed,
  bearer routing, the line clock) is about a quarter of the time of the I-modem.
* Ports 0x1c/0x1e (the DSP host-port status and strobe) cause about half of
  the Python exits in the two processes (about 550k of 1.0M in the I-modem,
  600k of 770k in the worker, for each 250M instructions). If the native port models served them,
  those stops would not occur. But the models would then have
  to keep the diagnostic logs of the mailbox (`overlay_recent` and the related logs) exactly.
* To get to 120 s, the Python time of the I-modem must go from about 125 s to about
  55 s. Trimming alone will not do that.

### Host-port status and strobes, served natively

The two native port models now answer the DSP host-port registers 0x1c/0x1e for
the accesses that need nothing from the harness. These were about half of all
exits from the x86 engine:

* I-modem (`ImodemHostIo`): IN 0x1c (the mailbox status word, with the same
  host-pending/transmit-ready bookkeeping that `_sync` does), IN 0x1e, OUT 0x1e
  (publishing the staged window words and raising the status bits) and OUT 0x1c
  with neither bit 0 nor bit 1 set. Commits, acknowledgements and replies to
  offer still go to Python. The 0x1e accesses are logged natively, and they are replayed
  in order into the `overlay_*` logs of the mailbox, before any other code uses
  them (`ImodemDsp._drain_overlay`).
* Analog worker (`LaneHostIo`): IN 0x1c in the runtime mode of the ROM protocol
  (from the DSP status latch plus two flags that the harness publishes: a host
  message staged, a DSP message queued), IN 0x1e (the overlay status byte),
  and the writes of 0 to either port, which have no effect.

The Python calls decreased by 29% in the I-modem and by 25% in the worker. The full
call went from 206 s to 186 s, and the results of the two processes are bit-identical.

### The PCM bearer path, native

The B-channel path of the I-modem is now native (`native/bearer.hpp`): the
bearer queues of the Am79C30, the frames settled before the DSP, and the exchange of
transmitted frames. `native_bearer.py` contains the Python views of that state
(the proxies that `Am79C30` and `ImodemDsp` use in place of the old containers). The
Python methods are still the reference, and they take the frames that the native path
leaves (underruns). `tests/test_native_bearer.py` runs the two on random scripts
and compares all results.

Above it, the x86 engine can run the poll of the harness itself
(`ImodemHostIo::poll`, called from the engine at each poll boundary). With a
call up on the bearer line, it flushes and supplies PCM frames, advances the DSP, and
settles what that completes. It calls Python only when a different part of
`poll_timers` has work:

- a timer or service is due (`elide_until`);
- a device was used (`poll_dirty`, set by each Python port handler except the
  read-backs of the PIT, PIC and UART status registers);
- the line clock has a frame to send.

`IsdnMachine._update_elision` decides after each full poll
if the next polls can be skipped, and until when. The engine gives control back to
Python, partially if necessary (`resume_service`), for any work that it cannot do alone.
The skipped polls also raise the interrupt sources that stay asserted (the THRE of UART B).
Thus, `_catch_up` does that to the controller before any code reads
it. The serial pumps take part when they offer `next_due`. `COURIER_POLL_ELISION=0` and
`COURIER_NATIVE_BEARER=0` disable the two functions.

Full call: 186 s -> 169 s (I-modem 148 s of CPU, worker 134 s), with
bit-identical results. In a call, about half the polls are now skipped. The item that still sends
the engine back to Python is mostly the timers: the mailbox service
(each ~2000 instructions), the three PIT counters and the RTOS tick are each
due each few polls, and each one is a full poll and an interrupt delivery in
Python. The next step is to serve the PIC and those timers natively.

## Native PIC and timers

The interrupt controllers, the wrap bookkeeping of the 8254 and the service
deadlines are now in one ctypes structure (`courier_emu/poll_state.py`, mirrored
by `PollState` in `c5x_capi.cpp`). `Pic8259`, `Counter` and `IsdnMachine` read
and write its fields as ordinary attributes. Thus, Python and the native model
share the same memory and never copy. The host-port model serves the PIC ports (0xF020/1, 0xF0A0/1).
The native poll itself takes the timer wraps, the
RTOS and mailbox deadlines and the asserted interrupt lines. Then it starts
the interrupt in the engine (`enter_interrupt`). The dispatch of Python charges one
retired instruction for each injected interrupt. Thus, the engine does the same
(poll code 4) to stay bit-identical.
`tests/test_native_port_models.py` checks the native PIC ports against the
Python controllers.

Full call: 169 s -> 155 s (I-modem 112.6 s of CPU, worker 140.6 s), with
bit-identical results. About 208k of 244k polls in the call run natively. The I-modem is
now below the 120 s of line time. The analog worker is the limit, and it needs
the same changes (native poll, PIC and timers).

## The analog worker

The worker (one Courier board: 80186, C5x, codec model) is the longer pole after
the I-modem is native. Its C5x runs the full V.34/V.90 data pump, and its
80186 harness serviced each 1,024 instructions in Python. These are the changes, in
the order of their cost. We compared each step with the full results of the previous run
(`tools/probe_imodem_analog_pair.py`, bit for bit):

- **Glue that built more than it needed.** A read of one serial counter built a
  70-key dictionary, a port-write count went through a six-field array, the
  resampler calculated its Kaiser window again for each kernel, and the overlay and
  ROM loaders single-stepped the C5x through ctypes. They are single calls now
  (`serial_backlog`, `io_port_writes`, `step_until_data`, a shared window).
- **MMIO and port reads served by the engine.** The native x86 engine logs the end-of-interrupt
  write of the 80186 (142k in a window) (guard bit 64), and replays it in order before Python runs next.
  The harness calculates the panel latch at port 0x14 (103k
  reads in a window, a polling loop), and the native port model serves it until code writes a
  panel port. The two start only after the first
  events have been recorded verbatim, as for the lane ports.
- **A fast path for the service.** `service_chunk` is split into head, clock,
  tail and the interrupt sources. `fast_service` does the tests of the
  common service in one location and in the same order: nothing for the call state
  machines to start, the codec frame not due, the line not ready for a frame,
  the DSP silent. It declines before it changes anything when a test says that there is
  work, and it gives the remaining part of a service to the original code when a later test
  says this. The DSP step is one call that also returns what is read next
  (`service_step`). The frame interrupt of the DSP (a quarter of a million
  entries for each call) is started in the callback, and it does not leave the engine for
  the run loop and go into it again (`redirect_is_free` keeps the dispatch edge
  uncharged, as the own path of the run loop does). `COURIER_FAST_SERVICE=0` disables
  it.
- **The resampler.** Its retuned path runs for the remaining part of a call after the codec
  clock changes, and it was a quarter of the glue. The loop for each sample, which includes the
  samples at a clock edge, is native (`native/resample.hpp`). The dot products
  are the `math.sumprod` of CPython (a triple-length accumulation, ported and checked
  against it on 200k random vectors). The Kaiser series uses the `pow` of libm, as
  `float ** int` does. `tests/test_resample_rate_changes.py` runs the two on random
  streams with rate changes and compares each sample.
- **The C5x step.** One third of the DSP steps of the worker are in RPTB bodies, and they
  went through the rare path for the block-repeat edge. That edge is on the fast
  path now, and the condition sample of XC is one register.

Full call, same machine, same results: worker CPU 140.6 s -> 109 s, I-modem
97-105 s (the noise from the shared host is +-5%), wall 155 s -> 127-133 s for 120 s
of line time. Where the worker uses its time now (250M window): the C5x about 47%
(533M instructions at ~45 ns, mostly a small number of filter loops and cold
code that runs one time for each frame), the native x86 engine 13%, the harness the remaining part.

These items remain, in the order of their apparent value:

- The call set-up of the I-modem (the
  first ~35 s, where the poll elision cannot yet run because no call is up and the
  worker waits for it). We measured this: of the 245k polls in the call of 600M instructions that
  elision declines because there is no answered call, 75% are in the idle state
  (`call_state` null, waiting for the ring of the worker, about the first 100M
  instructions), and 25% are between the offer and the answer of the I-modem. Thus, the
  set-up is mostly idle polls, not Q.931 traffic. To run them natively,
  the native bearer must settle idle frames (no channels, no routes: each output
  is the idle codeword, the B1/B2 transmit queues take idle octets, the line clock
  still counts them), and `quiet_until` must cover the idle and ringing states
  (`incoming_call` reads the ring flag of the line, which changes only at a line
  frame, so the frame deadline already limits it).
- The C5x interpreter itself (a predecoded handler for each
  program address would decrease the dispatch cost).
- The remaining reads of
  the timers and the panel latch for each service.

## On an Apple Silicon Mac

The same call on a local M-series Mac runs in about 43 s of wall time (72 s of
CPU across the two processes), against the 127-133 s above, and the balance is
different: the C5x interpreter is 58% of the worker and 55% of the I-modem, and
Python only 25% and 12%. The worker is busy 96-98% of the time, and it is the
limit. The I-modem waits for it. This is the run for each value here:

```bash
PYTHONPATH=. .venv/bin/python tools/probe_imodem_analog_pair.py --analog-settings 'X1S27=1S54=0S58=48&A3&B1Q0&U26&N39' --imodem-settings 'S54=0S58=48&A3&B1Q0' --imodem-nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav --instructions 600000000 --analog-instructions 450000000 --analog-send ANALOG-X2-53333 --imodem-send IMODEM-X2-53333 --output OUT
```

Two runs of one build give identical output, except the socket and record
paths. Thus, we checked each change with a comparison of the full output directory
with a baseline, and we timed it in alternating runs against the previous library
(`COURIER_C5X_LIBRARY`). The noise from run to run is about 1.5% of CPU.

- **Slow memory paths.** The datapump of the worker reads 20% of its data from SARAM
  or the shared external window, and it fetches 7% of its code from SARAM. All
  of those went out of line. They are a counter and a cell inline now, as are
  the circular-buffer AR update (the filter loops run with one enabled) and the
  step body in the run loops.
- **Threaded dispatch.** In `run_cycles`, the handler of each opcode completes its own
  step and tail-calls the next handler (`C5xCore::threaded`), with the op body
  inlined into it. For that, the opcode tables are in the translation unit of the core
  (`c5x_optable.ipp`).

- **Per-frame sample loops in Python.** The peak meters, the encode and decode of the line frame
  and the history of the resampler went through a generator for each
  sample. They are at the C level now. A native batch of port-0x14 lamp writes
  that all repeat the latched value is replayed as its three tallies.

CPU 71-72 s -> 60.7-61.2 s, wall 43.6 s -> 37-38 s (3.2x faster than real
time). We tried these items without a measurable gain:

- folding the tables in without inlining
  the op bodies (the thunks were already a single branch);
- threading the
  0xBE/0xBF second-level tables;
- a threaded handler for each value of the
  direct/indirect bit (with `__builtin_assume` folding `GET_ADDRESS`; the code
  growth cancelled the gain);
- inlining `consume_cycles` and the condition tests;
- reading the regions of DMOV and MAC from the maps;
- `-mcpu=native`;
- starting
  the interrupts of the worker directly on the registers of the interpreter, and not
  through the accessors (cProfile shows that cost as larger than it is).

PGO gave 2-3%. This is not
sufficient for a two-stage build.

The worker is now about 56% C5x, 28% Python (a flat tail, about 200 calls for each
service of 1,024 instructions) and 12% x86 engine. The set-up polls of the I-modem
(above) would save a maximum of the few percent that the worker uses to wait.

### The worker's service loop, native

The x86 engine now runs the fast services of the worker itself
(`courier_worker_poll` in `native/c5x_capi.cpp`, mirrored by
`courier_emu/worker_poll.py`), in the same way as it runs the poll of the I-modem. At the start
of the batch after each service that Python runs, `arm` checks each test that
`fast_service` and `clock_x86_fast` make of state that only Python changes
(`fast_service_static`, `DspBridge.fast_clock_static`, `timer_poll_static`).
It copies the counters into the shared structure and sets a deadline: the next
max count of the 80186 timer, the board tick, the next scheduled input, and the last
two services of the run. Until then, each service is done natively: the
codec-frame, line-sample and probe tests, the DSP step (with the float
arithmetic of Python, `fp contract(off)`), and the INT0 frame edge. All other cases give
control back:

- A test fails, or the deadline occurs: the engine stops before the service, and
  Python runs it (`after_run` has already copied the counters back).
- There is a DSP message to collect, the call TDM starts, the C51 goes into or out of
  its loader loop, or a DSP error occurs: the native poll has done the service up to
  the DSP step, and Python completes it (`resume`, poll codes 2 and 3).

Three details keep it bit-identical:

- The 80186 timers do not tick natively.
  Each read or write of a timer register advances it first. Thus, only a max count
  needs the tick of the poll, and the deadline prevents one in a
  native stretch.
- The end-of-interrupt writes that the engine logged in the batch are
  applied to the in-service stack before the frame-edge decision, and they are marked
  (byte 7 of the log entry). Thus, the replay of the harness skips the stack for them.
- The port-0x14 lamp writes are neutral to the dirty test of the engine. The poll
  declines only if a pending write would change the latch.

Two of three services now run natively (280k of 439k in the x2 call). The others
are line services (each five or six), services with DTE bytes or an interrupt
that waits in Python, and the service after each exit to Python. Wall 37 s ->
33.6 s, CPU 60.7 s -> 56.3 s. The x2 call, a Bell 103 call and a V.34 dial are
bit-identical. `COURIER_WORKER_POLL=0` disables it. The two processes now have
an equal load, each about 62% C5x. Thus, the interpreter is again the lever for
the two.

### The I-modem's set-up, native

We sampled the CPU of the two processes each two seconds. This showed that the I-modem limits the
first ~12 s (call set-up: ~1.0 CPU-s for each second against 0.4-0.6 for the worker,
64% of it Python), and that the worker limits the call. We made four changes. Each is
bit-identical on the x2 call (the set-up changes also on a Bell 103 call and a
V.34 dial):

- **Idle frames settled natively.** With no call, nothing is supplied ahead. Thus, each
  PCM frame stopped the native advance for `ImodemDsp.service_pending`, which
  settled it through the same `Bearer::exchange`. The native service now does that
  itself when no routed channel could underrun (`ImodemHostIo::clocks`),
  and `_advance_dsp` uses advance-then-serve (`courier_imodemio_advance_serve`).
- **Elision before the call.** `quiet_until` covers each call state. It declines
  when a pass would offer an incoming call (`BearerLineLink.offers_call`; the
  ringing of the line changes only on a line frame, which is a full pass).
  `_update_elision` requests no lookahead outside an active call, in place of an
  answered peer. The native poll takes a poll with no channel when nothing is
  supplied ahead. Polls declined for the peer: 245k -> 6k.
- **SETcc, CBW, CWD in the x86 engine** (386 profile): 115k + 85k exits in a call
  at two single instructions.
- **UART status reads keep elision armed**, as `read_port` always intended.
  It marked the poll dirty before it got to the exemption. Thus, the
  modem-status loop of the firmware disarmed it 85k times. Dirty declines: 92k -> 14k.

Native I-modem polls 880k -> 1.14M. Wall 33.6 s -> 27.5 s (4.4x real time). The
worker is now the limit for the full call, and the I-modem has spare time. Thus,
the remaining gains are in the worker: its line services (~78k in a call, the
socket exchange, the resampler glue and the call state), the services with DTE input
or an interrupt that waits, and the C5x interpreter, which is still the largest
share in the two processes.

### The worker's line services, native

Of the ~68k line services in the x2 call, only ~6.5k exchange a frame with the
I-modem. The others resample the newest samples of the codec onto the exchange buffer
(`_take_line_audio`). Those now also run in `courier_worker_poll`:

- The retuned state of the resampler (the history with timestamps and the scalars next to
  it) is in native memory after it retunes (`resample::Timed`, seeded from
  the Python state. `COURIER_NATIVE_RESAMPLE=0` keeps the pure-Python path,
  which the native-versus-Python test compares against across rate changes).
- The poll does the conversion on that state as a dry run. It rolls it back if the
  buffer would get to a line frame. If not, it commits and keeps the
  statistics, buffer additions and cursors of the service in the shared structure,
  which `after_run` gives back.
- These cases stay with Python: a clock change in the batch, a rate for which the resampler is not tuned, no
  codec clock, or a resampler that is not yet retuned. The
  frame exchanges also stay with Python (the socket, the call state, the DAA).

49k of the 68k run natively (native worker polls 280k -> 330k). Wall 27.5 s ->
26.2 s, bit-identical on the x2, Bell 103 and V.34 runs.

### The worker's line frames, native

In a call that is through and steady, a line service that completes a frame
now also exchanges it in `courier_worker_poll`. The frame comes from a native
copy of the exchange buffer and goes out. The frame of the I-modem comes back on
the socket of the line, and the received audio gets to the queue of the codec with the
same peaks, in-flight copy, DAA counts and recordings. All checks occur before the
send. A socket failure gives the service back and sets `LineLink._presend`. Thus,
the redo of Python gets the same failure and does not send two times (when the I-modem closes
the line at the end of the x2 call, this path occurs). It is armed only when the
buffer is within 48 samples of a frame, because in other cases the arming costs more than
a frame saves. `COURIER_NATIVE_FRAMES=0` disables it.

About 3.5k of 6.5k frames run natively and bit-identical, and the wall time does not
change: the cost of a frame is the wait for the reply of the I-modem. With the line path
of the worker native, the remaining Python of the worker is the services with DTE input or
an interrupt that waits, the services after exits to Python, and the arming
itself. The C5x interpreter is still the largest share in the two processes.
