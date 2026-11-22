# Local I-modem x2: first record-gap evidence, 26 October 2026

## Scope and result

The live RasFinder V.90 results still qualify connection/banner/idle holds,
not bulk transfer. The available notes document an unauthenticated login
prompt, not an authorized deterministic transfer service. No live calls,
login attempts, credentials, or remote configuration changes were made here.
Instead, three sequential local I-modem/403 controls investigate the
[known sustained x2 failure](imodem-analog-x2-traffic-20261018.md).

**All three fail the unchanged traffic gate. No datapump fix is claimed.**
Each requests 20 seconds of independent bidirectional traffic, retaining the
existing five-second maximum complete-record receive-gap criterion. Both
512-byte controls deliver no complete upstream record in the measured window.
Reducing record payload to 32 bytes permits a few complete upstream records,
but does not pass sustained traffic. Longer soaks are not the next useful test.

Directions below are **upstream = analog DTE to I-modem DTE** and
**downstream = I-modem DTE to analog DTE**.

| Control | Upstream complete records / trailing bytes at final drain | Downstream complete records / trailing bytes at final drain | Post-window BLERs | Resent blocks | Link timeouts |
| --- | --- | --- | --- | --- | --- |
| 512-byte payload, V.42bis | 0 / 419 | 23 / 0 | 239 | 0 | 1 |
| 512-byte payload, `&K0` on both | 0 / 471 | 9 / 106 | 244 | 21 | 3 |
| 32-byte payload, V.42bis | 3 / 10 | 98 / 48 | 249 | 8 | 3 |

These counts include the existing bounded post-window drain. A complete record
contains its marker/sequence/terminator as well as the payload: 531 bytes for a
512-byte payload, 51 for a 32-byte payload. Received prefixes pass the online
stream check; no corrupt/out-of-order payload was reported. A separate read-only
recheck also regenerates every complete record and measured trailing prefix
from the deterministic sender sequences, compares them with the raw DTE
captures, and checks the saved complete-record hashes. It confirms the failed
results rather than turning prefix integrity into a passing traffic gate.

The 32-byte control's maximum upstream complete-record gap is 107 100-ms ticks
(10.7 seconds), and the downstream maximum is 68 ticks. Smaller records do not
remove the underlying long gaps. Compression-disabled traffic also fails;
compression is not a sufficient explanation.

All runs initially report I-modem `CONNECT 33333/ARQ/x2/LAPM` (with V42BIS where
enabled). Post-window ATI6 reports 24000/54666 for the first run and
28800/54666 for the other two. These are firmware diagnostics, not measured
application throughput or independent directional-rate verification.

## New passive capture

`tools/probe_imodem_analog_pair.py` now saves **`first-stall.json`** once, at
the existing `AnalogTraffic.stalls` boundary. It also includes this evidence
in `result.json` under `first_stall`. No new stopping rule, acceptance
threshold, firmware write, escape command, or default setting was introduced.
Ordinary periodic traffic progress now includes the supervisor timer-tick
counter.

The snapshot contains:

- Both stream states, including incomplete-record byte counts and first-gap
  frames, without freezing the measured window or stopping data injection.
- Supervisor instruction and timer-tick counters.
- Native DSP clock/data-handshake counters, DSP state/stack, raw host-port
  values, lane read/write counters and program counters.
- UART status and bridge status.
- The preceding bounded progress history (at most 32 entries).

**A five-second complete-record gap is not the first firmware block error.**
Partial bytes can continue arriving while a record is incomplete. First error
localization still requires tracing the firmware's link-error counter or
receive/CRC rejection branch; the post-window ATI6 count does not timestamp
its first increment.

## First-gap observations

The first captured gap is upstream in each run, at 5.1 seconds after that
receiver's CONNECT. At that point the upstream receiver has received zero
complete records and respectively **79, 107, and 16 partial bytes**. The
analog receivers have already completed respectively **6, 6, and 43** records.

Between the last preceding progress sample and each first-gap snapshot,
supervisor instruction/timer counters advance by:

| Control | Instructions | Timer ticks |
| --- | ---: | ---: |
| 512-byte V.42bis | 3,330,560 | 242 |
| 512-byte `&K0` | 7,612,928 | 545 |
| 32-byte V.42bis | 7,568,896 | 605 |

This rules out a completely stopped supervisor/timer counter at those sampled
boundaries, not incorrect servicing cadence or a transient delay. Timer ticks
are the emulator's raw counter, not a new calibration of firmware call time.

At the first-gap boundary, every native occupied-bank-write counter and torn
word counter is zero. UART overrun/output-drop counters are zero. At the
measured completion boundary all three calls retain active carrier with zero
I-modem PCM underruns and zero analog connected receive-empty events. All
CPU/DSP error fields are empty. These counters do not prove correct bit values,
CRC handling, or service timing inside the firmware.

## Evidence and reproduction

Generated local evidence directories (not included in the source commit):

- `artifacts/imodem-x2-first-stall-20261026-210017/`
- `artifacts/imodem-x2-first-stall-k0-20261026-210148/`
- `artifacts/imodem-x2-first-stall-small-records-20261026-210243/`

Each contains the exact command, bounded run status, raw DTE captures,
first-gap snapshot, periodic progress/checkpoints, full results, G.711 media,
and final DSP program/data. Wall durations were 53.76, 54.80, and 49.20 seconds;
all exit 1 because traffic fails, not because a process timeout fired. The
probe closes the owned local worker and sockets after each run.

Base command:

```sh
COURIER_LINE_FRAME_MS=20 PYTHONPATH=. .venv/bin/python tools/probe_imodem_analog_pair.py \
  --wallclock --traffic-seconds 20 --link-diagnostics \
  --analog-settings 'X1S27=1S54=0S58=48&A3&B1Q0&U26&N39' \
  --imodem-settings 'S54=0S58=48&A3&B1Q0' \
  --imodem-nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --instructions 1500000000 --analog-instructions 750000000 \
  --output /tmp/imodem-x2-first-stall
```

Append `&K0` to both settings for the uncompressed control, or add
`--traffic-size 32` for the smaller-record control. Run controls sequentially
with host headroom; overlapping CPU-heavy work would confound wallclock data.

## Regression and checkpoint status

Before changes, the focused runtime/media/traffic selection passed **118 tests**.
After adding the observer and its no-core/read-only/partial-record tests, an
expanded selection including native data traces, data lanes and peripheral slots
passes **131 tests**. `git diff --check` is clean. No owned probe/worker processes
remained after the controls.

The pre-investigation tracked state is retained without modifying the working
tree under Git ref `refs/checkpoints/pre-traffic-20261026-205627`. Private
`.artifact-archives/work-checkpoint-20261026-205627/` contains the tracked patch,
138 untracked source/documentation files, baseline/final regression output, and
`verify-local-captures.py` with its successful JSON report. Generated/private
artifacts remain in their original directories. The checkpoint is not a clean
release commit; existing work was not indiscriminately staged or committed.

## Follow-up: receive rejection and V.34 controls

The [CRC-boundary investigation](imodem-x2-crc-boundary-20261026.md) now traces
the first x2 pending receive error and independently recomputes the original
firmware CRC from rejected frame bytes. It also finds a passing 20-second
32-byte V.34/LAPM control, while 512-byte V.34 controls fail with zero BLERs.
These distinguish receive corruption from a separate large-record service or
buffering problem; neither is claimed fixed.

## Next debugging boundary

Identify the original firmware's first receive-error/BLER increment or CRC
rejection, then capture its inputs with the already available DSP lane and
supervisor-service evidence. Compare the failing upstream bit stream to a
passing local V.34/Bell-103 control without rewriting firmware flags, payloads,
or acceptance criteria. The current snapshot establishes where to inspect;
it does not establish that a particular DSP lane, scheduler, or CRC routine
is wrong.
