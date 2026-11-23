# Analog Courier / v90modem: premature DIL cutoff

**Continuity follow-up:** [CTS/DTE backpressure](analog-v90-cts-continuity.md)
now preserves 38,400 bytes exactly in both directions across two completed
retrains, with a matched CTS-ignored control losing 7,680 bytes. The original
firmware requests a rate change before the earlier discontinuity; those logs
alone did not establish spontaneous decoder failure. Retrain gaps remain.

## Finding and scoped correction

The failed V.90 calls in [the interop report](analog-v90modem-interop.md) were
not blocked at INFO1a or Ja. v90modem's default one-cycle DIL interop fallback
sent Ri before this original Courier 403 endpoint was ready.

With the existing `ME_V90_DIL_AUTOTERMINATE_CYCLES=0` control, the digital
endpoint repeats DIL and observes the Courier's next S event near the end of
cycle two, then receives strict CPt/CP' and validates upstream B1. The original
Courier reports:

```
CONNECT 52000/ARQ/V90/LAPM
```

`tools/probe_v90modem_closed_loop.py` now selects that existing repeat-until-
completion profile **only when its engine mode is v90**. Explicit environment
overrides remain honored, and x2 is unchanged. The sibling payload driver's
`--modulation v90` uses this same profile. No engine-wide or physical-hardware
profile default, original firmware, DSP arithmetic, codec gain, rate, queue
capacity, carrier acceptance, CRC, or exact-payload check was changed.

V.90 (09/98) section 9.3.1.6 requires DIL to continue until a subsequent
S-to-S-bar transition is received, completing the current segment before
Phase 4. This motivates removing the blind one-cycle cutoff. The engine's
existing detector still approximates the transition using its S event and a
minimum-duration guard; this work does **not** claim that detector is a fully
conformant S-to-S-bar implementation.

## Controlled evidence

All runs below use wall-clock pacing, original 403 firmware, S39=8, S54=0,
S58=1 (x2 disabled / V.90 allowed), automatic rate selection, &M5&K0,
240 million instructions, and source injection from bearer sample 220000.
Engine SHA-256:
`fcd8e5c2f0c4408120206bb51352f600d97b0bce90fb4931c0d18d31eb499f73`.

Artifact paths use prefix `artifacts/analog-v90-dil-` and suffix
`-20261103`:

| Middle of path | Frame | DIL setting | Exact into Courier | Exact return | Outcome |
| --- | ---: | ---: | ---: | ---: | --- |
| `repeat` | 20 ms | 0 (repeat) | 20 bytes | 28 bytes | V90/LAPM PASS; read-only receiver capture |
| `two` | 20 ms | 2-cycle cutoff | 20 bytes | 28 bytes | V90/LAPM PASS; diagnostic only |
| `fixed5000` | 20 ms | 0 (new probe default) | 5,000 bytes | 28 bytes | V90/LAPM PASS, no receiver capture |
| `negative1` | 20 ms | 1-cycle cutoff | 0 bytes | 0 bytes | No CONNECT, FAIL |
| `duplex5000-grid5` | 5 ms | 0 (new probe default) | 5,000 bytes | 5,000 bytes | V90/LAPM PASS, no receiver capture |

All emulator and engine processes exited 0. A failed acceptance result is not
inferred from process status: `negative1` fails the negotiated-mode and exact
payload gates and the probe exits 1. All ten checks pass in each positive
`call.json`, including requested V.90 modulation, engine V.90 selection,
complete PTY source queuing, and exact streams after CONNECT in both
 directions. Captured DTE lengths in the 5,000-byte duplex case are 5,030
Courier wire octets and 5,017 engine octets (including result framing).

The 0/2-cycle short-payload calls had the same upstream S event at receive
sample 87680, RMS 1218.3:

* Repeat mode accepts it (`count=3 accepted=1`), terminates at the next segment
  boundary, and then acquires valid CPt.
* The 2-cycle diagnostic rejects it at segment 388/197 (its floor is two
  complete cycles), then auto-terminates a few segments later. That also
  connects but is **not** the adopted correction.
* The old 1-cycle profile has already left DIL before that response. It never
  connects in the matched negative control.

The initial S during Jd remains necessary and unchanged. A second event at
DIL segment 5/197 is ignored in all profiles as too early; the correction does
not simply accept the first post-J'd event.

## Remaining failure: sustained upstream synchronization

At this earlier checkpoint, each successful run later logged one
`V90 upstream discontinuity resync` and
enters a training-and-B1 resynchronization attempt. The original short-payload
repeat call logs it at approximately 53.8 seconds on the engine trace clock.
Therefore these are genuine initial CONNECT and finite exact-payload passes,
**not** stable 60-second traffic, validated retrain recovery, or hardware
interoperability qualifications. The initial upstream B1 has 100% template
fit with an independent out-of-sample check; that does not certify later
clock/decoder continuity.

The hardware Courier's reported x2 failure and partial V.90 success remain
separate evidence. No physical call was made or physical endpoint changed.
The digital one-cycle cutoff is a plausible hardware interop contributor,
but that must be tested on the actual wired rig before calling it a hardware
fix.

## Reproduction

Use the payload generation in the linked report. Short/5,000-byte downstream
control (unique output path required):

```sh
X2_HOST_EMU_ROOT="$PWD" COURIER_LINE_FRAME_MS=20 \
  .venv/bin/python ../v90modem/tools/probe_x2_host_courier.py \
  --modulation v90 --courier-at '&M5&K0' \
  --pty-source --host-pace-samples 16 \
  --instructions 240000000 --host-at 220000 \
  --host-message-file tmp/analog-interop-payload.txt \
  --output artifacts/analog-v90-dil-new-run
```

For the negative control, prepend
`ME_V90_DIL_AUTOTERMINATE_CYCLES=1`; do not change other settings. For duplex
traffic, pass the same ASCII payload as `--message` as well as using
`--host-message-file`; the latter is only the digital-to-Courier direction.

## Regression coverage

The previously documented focused selection now passes **43 tests**.
`tests/test_v90modem_closed_loop.py` explicitly checks that v90 starts with
DIL-repeat mode, x2 receives no such override, and explicit values 1 and 2
survive unchanged. These subprocess unit tests test configuration and
transport, not signal-level acceptance; the real closed-loop controls above
provide the interop evidence.
