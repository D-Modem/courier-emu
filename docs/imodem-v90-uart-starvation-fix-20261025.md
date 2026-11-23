# I-modem: clean V.90 holds and repeated ATI6 output

Follow-up to the [live timing/watchdog correction](imodem-v90-live-timing-fix-20261025.md).
The remaining **post-hold ATI6 TX starvation** is now corrected in the
opt-in live path. The final tests include ten diagnostic queries after each
60-second hold, rather than qualifying only the hold window.

## Later rate improvement

The [independent transmit-reserve follow-up](imodem-v90-faster-return-path-20261025.md)
keeps this native build and 200-ms TX margin, but lowers receive latency.
It qualifies **31200/49333 on 6312 and 28800/49333 on 6313**, including clean
60-second holds and ten ATI6 queries. Rates below describe the earlier
conservative-buffer qualification, not the best demonstrated receive rates.

## Final-build results

Both calls used CT 127, SIP account 2903, the existing full-rate profile,
S54=0, 200-ms media reserves, and `COURIER_LIVE_POLL_ELISION=1`.

| Destination | CONNECT | Host-wall hold | Sample-counted hold | ATI6 queries | ATI6 speed | Full-session maximum TX gap |
|---|---|---:|---:|---:|---|---:|
| 6312 | 49333/ARQ/V90/LAPM | 60.000371 s | 60.000375 s | 10 | 12000/49333 | 24.04 ms |
| 6313 | 49333/ARQ/V90/LAPM | 60.000082 s | 60.000125 s | 10 | 16800/49333 | 23.66 ms |

For **both complete sessions**, including training, hold, guarded escape,
all ten ATI6 replies, and deliberate ATH clearing:

- **Zero TX rebuffers**, not merely zero through the hold.
- Zero RX missing/late samples, sequence gaps, timestamp jumps, duplicates,
  reordering, invalid packets or SSRC changes.
- Readable MULTITECH login banner; all ten ATI6 replies report Online/LAPM,
  zero block resends, retrains, BLERs, link timeouts and NAKs.
- No observed watchdog abort at `bc0f6` or XID-timeout recorder at `ab33b`.
- Zero native torn data words and busy-bank writes.
- Complete PBX and container captures have zero kernel drops. Both RTP
  streams have contiguous sequence numbers and 160-sample timestamp steps;
  their packet-byte hashes agree between the two capture points.

The exact tested library is
`/root/courier-emu/.build/libcourier_c5x-live-uart-final.so`. Matching Python
sources and a native rebuild are required; the earlier `-live-final.so`
implements the watchdog fix but not this UART optimization.

```sh
clang++-19 -std=c++17 -O3 -fno-semantic-interposition -shared -fPIC \
  native/c5x_core.cpp native/c5x_capi.cpp -o .build/libcourier_c5x-live-uart-final.so
```

## Why serial output starved media

The supervisor has a bounded independent-DSP recovery allowance: at most one
DS0 frame, 5,040 cycles, per genuine 512-instruction scheduler turn. Sustaining
40.32 MHz consequently requires at least 8,000 such turns per second
(4.096 million supervisor instructions per second), even before other limits.

Printing diagnostics forced repeated full Python service: UART shifting,
unread terminal output, and THR writes all prevented native elision. Full
service re-polled SIP sockets and did bearer bookkeeping for almost every
printed character. On the test host the supervisor slowed below the required
rate. The independent DSP target remained owed, but growing lag eventually
exhausted the 200-ms outgoing reserve. A passing short query could merely
consume reserve; repeated queries were necessary to expose accumulation.

## Corrections without changing clocks or budgets

1. **Known UART quiet windows.** A running transmitter cannot change until its
   byte-completion deadline, even with THR full. `SerialChannel.quiet_until()`
   exposes that bound. Staged receive bytes and a holding byte waiting to start
   still require ordinary service; their arrival/start semantics are unchanged.
2. **Pure native status reads.** Cache LSR and stable MSR snapshots. MSR is
   eligible only after Python has acknowledged all delta bits, and never in
   loopback mode. Publishing status does not read/clear pending modem deltas.
   Other UART accesses invalidate the snapshots before falling back; Python
   republishes after UART accesses and advances. Native reads are included in
   the normal I/O counts.
3. **UART-only native resume.** `PollState.serial_until` separates a serial
   deadline from full socket/device deadlines. Native code does the normal
   bounded DSP/bearer work, then returns resume code **5** before its PIC/timer
   tail. Python completes serial and the ordinary tail once, without repeating
   DSP/mailbox work or polling sockets for every byte.
4. **UART writes are not whole-machine dirtiness.** THR writes and side-effecting
   UART reads request that serial-only resume. They never clear dirtiness from
   another device. This distinction was essential: the resume path alone still
   fell back to full service after every THR write.
5. **Socket service cannot slide indefinitely.** Its one-millisecond deadline
   is renewed by actual full network service, not by serial-only anchor refreshes.

The scheduler still polls every **512 instructions**. CPU/DSP clock rates,
wall-clock pacing, the one-frame recovery cap, ordinary port budgets, holding
words, timer expiries, PIC priorities and firmware watchdog remain intact.
The new native capability is detected explicitly; older libraries retain full
UART fallback. The shared Python/C++ state gained a matching deadline field.

## Rejected candidates and scope

Quiet windows or status caching alone improved short tests but still produced
rebuffers during ten-query tests after long holds. Broad status-refresh callbacks
without cached MSR reads made training worse. A 256-instruction cadence changed
boot behavior and retriggered the original watchdog during diagnostics, including
an attempted split-tail version. **None of those cadence changes remain.** The
final fix removes redundant Python work rather than accelerating interrupts,
enlarging DSP grants, or patching the firmware.

This result is **not sustained application/binary throughput certification**.
Each call receives only the 51-octet login banner; no login credentials or
application payload were submitted. Two final-build calls are not a long-run
connection-success-rate study. The earlier independent XID timeout is not
retrospectively explained by these successes. ATI6's half-scale time field is
still the original, separately verified firmware arithmetic.

## Tests and private evidence

- **128 targeted tests pass on macOS.**
- **126 pass, two optional-firmware tests skip on Linux**, using the exact
  final live library. New regressions cover UART deadlines, pure-status cache
  invalidation/counting, first-read MSR acknowledgement, native/fallback register
  transitions, UART-only resume, unrelated-device dirtiness, and non-sliding
  socket deadlines, alongside the existing clock/watchdog/media tests.
- Final complete captures, recordings, observers and reports:
  `.artifact-archives/imodem-v90-uart-fast-final-{6312,6313}-20261025-204108/`.
- Read-only assertion script and source/library/report/capture hashes:
  `.artifact-archives/imodem-v90-uart-verification-20261025/{verify.py,verification.json}`.
  Local and remote runtime-source hashes agree exactly.
- Intermediate `uart-*`, `serial-*`, `live256-*` and `split-clock-*` archives
  preserve failed experiments; their names containing `final` are not claims
  that they passed. Use the **uart-fast-final** archives above.

Every call was individually idle-gated; account/destination safety checks and
owned captures were retained. No PBX, ATA, answering-modem or sibling-call
settings were changed. All test calls and captures have ended.
