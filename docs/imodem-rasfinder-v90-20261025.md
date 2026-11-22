# I-modem to RasFinder: V.90 login at 49333, 25 October 2026

## Latest status

The [live timing correction](imodem-v90-live-timing-fix-20261025.md) fixes the
identified IRQ13-watchdog path. Its exact final build completes **60-second
V.90/LAPM idle/banner holds on both 6312 and 6313**, with zero missing RX
samples or TX rebuffers through the holds. The later
[UART service correction](imodem-v90-uart-starvation-fix-20261025.md) repeats
both 60-second holds at 49333/V90/LAPM and adds ten ATI6 queries per call,
with zero TX rebuffers or RX loss across the complete sessions. Sustained
payload is not certified. The later [receive-latency tuning](imodem-v90-faster-return-path-20261025.md)
qualifies **31200/49333 on 6312 and 28800/49333 on 6313**, also with clean
60-second holds and ten ATI6 queries. Those are I-modem receive/transmit
rates: its PCM direction is outgoing, not the returning login-banner direction.
The sections below retain the chronological initial results and diagnosis.

## Demonstrated result

One outbound call from the emulated I-modem in vmhost **CT 127** to **6312**
reported:

```
CONNECT 49333/ARQ/V90/LAPM

MULTITECH SOFTWARE SYSTEMS
USA
login:
```

An ordinary guarded `+++` escape followed by `ATI6` returned:

```
Octets sent                   3      Octets Received              51
Blocks sent                   2      Blocks Received               2
Blocks resent                 0
Retrains Requested            0      Retrains Granted              0
Blers                         0
Link Timeouts                 0      Link Naks                     0
Data Compression       NONE
Protocol               LAPM
Speed                  12000/49333
Current Call           00:00:06
Online
OK
```

This establishes **a real V.90 connection with readable login data**, with
reported upstream/downstream rates of **12000/49333 bit/s**. It is not an
error-free sustained-payload or throughput certification. No credentials were
submitted. ATI6 counts only 51 received octets; do not generalize its zero
errors to a substantial traffic test.

## What changed

The preceding calls used erased/ephemeral settings and showed **BAUD=9600**,
**S54=64**. They negotiated V.34; two reached CONNECT then disconnected, and a
later verbose control delivered the MULTITECH login prompt and stayed up to
the instruction limit.

The successful V.90 run instead loaded a fresh private copy of:

```
artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav
```

and issued:

```
AT*V2=3
AT&W
AT&A3&M5&K0S54=0S58=0&B1&N0&U0
ATI4
ATI7
ATDT6312
```

ATI4 confirmed **BAUD=230400 PARITY=N WORDLEN=8**, **S54=0**, **S58=0**, and
automatic line speed. ATI7 reported the external I-modem, supervisor 3.0.2,
DSP 3.0.5, with V.90 among its options.

This is a **successful configuration**, not an isolated causal A/B of one
register: the saved profile also supplies the factory capability header,
National ISDN-1 configuration, framing, and other settings. For example,
S67/S68 differ from the erased-profile control. The documented DTE eligibility
restrictions make the original 9600-bps setup unsuitable as an unrestricted
PCM test; see [the earlier DTE investigation](imodem-x2-pair.md#caller-dte-restriction-identified).
Do not claim S54 alone, or the DTE rate alone, explains this result.

## Execution and media conditions

- `root@vmhost.net.cryan.nz`, unprivileged Debian CT **127**,
  `courier-imodem-test`, `192.168.88.127` at test time.
- `/root/courier-emu`, copied local working tree; firmware `Ie030002.nac`
  and captured C5x on-chip ROM. This is not a clean-revision build.
- CPU 1 affinity via `taskset`, Clang 19 native DSP build.
- **Opt-in** `COURIER_LIVE_POLL_ELISION=1` and the paced experimental library
  `/root/courier-emu/.build/libcourier_c5x-paced.so`.
- Both bearer reserve and RTP receive deadline **200 ms**, PCMU, account 2903.
- The port and account were idle before dialing. Other calls were untouched.
- One instruction-bounded call, with private container/PBX captures. Password
  supplied on stdin into the environment, not saved or placed in argv.
- No answering modem, ATA, or PBX configuration change.

Full-call counters:

| Metric | Result |
|---|---:|
| RX sequence gaps, timestamp jumps, late packets | 0 |
| Missing receive playout samples | 0 |
| Active bearer silence filling | 0 |
| TX rebuffer events | 0 |
| Maximum TX packet gap | 24.99 ms |
| Native data torn words | 0 |
| Native busy-bank writes | 0 |

The native peak DSP lag counter still reaches about 327 ms somewhere in the
run; clean socket counters do not certify all internal clock alignment.

The observer waited ten host-wall seconds after recognizing CONNECT, sent
`+++`, waited for firmware OK, then requested ATI6. ATI6's own call-time field
reported six seconds; the relation of firmware call-time accounting to host
wall time is not qualified. A subsequent ATI11 was sent but produced no report
before the firmware cleared the call normally. The planned ATH was not sent.
The call had ended and PBX channels were clear at the final check.

## Evidence and remaining work

Private archive:

```
.artifact-archives/imodem-rasfinder-fullrate-20261025-153905/
```

It contains the complete report/transcript, both G.711 directions, heard-audio
recording, scoped captures, launch scripts and `verification.json` (including
the input profile SHA-256). Remote outputs are in
`/root/courier-emu/artifacts/imodem-rasfinder-fullrate-20261025-153905/`.

The preceding erased-profile diagnostic control is in
`.artifact-archives/imodem-rasfinder-diagnostics-20261025-153559/`.
The scheduling investigation and 6312/6313 V.34 controls are described in
[the vmhost investigation](imodem-vmhost-rasfinder-20261025.md).

## Follow-up repeatability and hold attempts

**Later update:** the [failure investigation](imodem-v90-failure-analysis-20261025.md)
below supersedes the unresolved diagnosis and absence of a completed
60-second hold in this chronological section. It identifies a reproduced
IRQ13-watchdog abort, a separate XID timeout, and ATI6's half-scale accounting.


Three more user-requested calls used fresh copies of the same profile, the
same modem/media settings and core, and a passive hold observer. No credentials
or application test payloads were submitted.

| Port | Intended hold after CONNECT | Result | RX missing samples | TX rebuffer events |
|---|---:|---|---:|---:|
| 6313 | 20 s | CONNECT 49333/V90/LAPM; readable login; completed 20.0006 s hold | 0 | 0 |
| 6312 | 60 s | No CONNECT; NO CARRIER during training | 320 | 0 |
| 6313 | 60 s | No CONNECT; NO CARRIER during training | 0 | 0 |

The successful 6313 repeat's ATI6 reports **14400/49333**, LAPM, 51 received
octets, two received blocks, and zero retrains, resends, BLERs, NAKs or link
timeouts. Its firmware call-time field says eleven seconds, versus the
observer's measured twenty-second host-wall hold. Both are retained as distinct
clocks; no firmware timer-calibration claim is made. The observer then escaped
normally, read ATI6, and sent ATH. No unsolicited carrier loss was observed
during the hold.

On the failed 6312 run, the same two-packet gap is visible at both the PBX and
the container at about 11.402 seconds into incoming RTP: sequence 34025 ->
34028, timestamp delta 480 samples. Both tcpdump captures report zero kernel
drops. This supports an upstream/PBX-side gap rather than a loss introduced
only at the container; it does not prove that gap caused the negotiation
failure. Its post-loss ATI6 command got no response and the observer stopped
at its 165-second wall bound.

The subsequent failed 6313 run has no RTP sequence gaps, missing samples, late
packets, or transmit rebuffer events. ATI6 after the failure reports protocol
NONE, zero received octets, no established-call duration, and "Normal call
clearing". Its displayed speed 14400/49333 is **not** evidence of a connection:
there was no CONNECT, login, or accepted payload. Thus packet loss alone does
not explain the remaining failures. This observer ended after normal hangup.

With the successful configuration there are now two demonstrated V.90 login
connections (one per port) and two additional training failures. These four
calls are not a statistically controlled success-rate study. In particular,
**neither 60-second hold attempt reached its hold phase**; there is no passing
60-second idle or payload soak.

Private follow-up evidence:

- `.artifact-archives/imodem-v90-repeat-20261025/` — both initial repeat
  captures, complete reports/audio, observer events, `verification.json`, and
  the PBX/container packet-gap comparison.
- `.artifact-archives/imodem-v90-hold60-20261025-161306/` — clean-media 6313
  training failure and post-call diagnostics.

All test calls are finished, with no emulator left active. Next checks are
comparing successful/failed training captures, a genuinely completed longer
hold, a bounded exact-payload test, and separating profile effects. The live
scheduler remains disabled by default; the existing 44 targeted regression
tests do not replace these hardware checks.

## Instrumented failure investigation and completed longer hold

See [V.90 failure analysis](imodem-v90-failure-analysis-20261025.md) for five
further bounded calls. Three connect, including one completed 60.000591-second
idle/banner hold (with one full-capture TX rebuffer). Two fail: one with an
explicit LAPM XID timeout, and one with clean RTP whose firmware IRQ13 watchdog
sets the general abort flag at `bc0f6` on service entry 50. The latter explains
how a late-training call can clear without a modem-specific cause; the
underlying interrupt-scheduling defect is not yet fixed. ATI6's half-speed
call duration is independently reproduced from its original counter arithmetic.
No sustained-payload qualification is claimed.
