# V.90 repeats: IRQ13 watchdog, XID timeout, and ATI6 accounting

**Later correction:** [live timing fix and final holds](imodem-v90-live-timing-fix-20261025.md)
resolves the identified watchdog path and completes clean 60-second hold
windows on both ports. The following is the chronological diagnosis before
that fix. The subsequent [UART service correction](imodem-v90-uart-starvation-fix-20261025.md)
also completes ten post-hold ATI6 queries on each port without TX rebuffers;
sustained application payload remains unqualified.

Follow-up to [the RasFinder V.90 trials](imodem-rasfinder-v90-20261025.md).
This investigation identifies the firmware branch aborting a reproduced
clean-media call. It does **not** yet fix the scheduler/interrupt condition
that trips that branch.

## Clean-media failure: the supervisor aborts on its IRQ watchdog

Saved successful and failed 6313 recordings both contain CRC-valid INFO
exchanges and hundreds of CRC-valid downstream Jd frames with the same decoded
words (`ffff`, `f03f`, CRC `c2e5`). Both receive these late DSP reports:

```
006e:0004
0072:1106
0035:5ffe
0036:000c
```

This narrows the divergence to the transition out of modulation training,
rather than establishing a fully successful LAPM/data connection. The saved
failure clears before CONNECT. A `000a:0001` command interleaved before the
last reply is not sufficient to explain it: that ordering also occurs in a
successful follow-up.

A new 6313 trial reproduced the same early-clear pattern with **zero RX
sequence gaps, timestamp jumps, late packets or missing samples**, no TX
rebuffer, and a 23.50-ms maximum TX packet gap. Passive firmware code probes
caught the first general-abort write:

```
wall 33.896329 s, instructions 194338816
PC bc0f6: mov byte ptr [ca57], 80h
DS = 2600h
[c8ed] = 32h (50)
[d08b] = 00h (no specific disconnect reason)
```

The original firmware immediately preceding it is:

```
bc0e9  inc byte ptr [c8ed]
bc0ed  cmp byte ptr [c8ed], 32h
bc0f2  jae bc0f6
bc0f4  jmp bc0fb
bc0f6  mov byte ptr [ca57], 80h
```

The system-timer path resets `[c8ed]` at `a468b`. Related mailbox service
handlers at `b3d90` and `b7d21` have the same 50-entry watchdog. Thus **50
mailbox-service entries occur without an intervening executed system-timer
reset**, and the firmware deliberately aborts. The usual system tick is
100 Hz. The probe does not establish whether this instance arises from
excess/bunched IRQ13 delivery, delayed IRQ10 service, or their combination.

The subsequent trace enters the ordinary hangup routine `c5519` at wall
33.903209 s with no specific cause. The ISDN stack then writes cause `6ah`
at `75a85`, after the abort. This is what later prints as **Normal call
clearing**; it is a consequence, not a modulation-training diagnosis.

The DSP mailbox timeline corroborates the transition:

```
28.5328 reply 006e:0004
28.5330 reply 0072:1106
28.5335 reply 0035:5ffe
28.5340 reply 0036:000c
28.5343 cmd   000a:0001
28.5741 cmd   0057:003f
28.5778 reply 0002:0000
28.5807 cmd   0001:003f
```

These are DSP timeline offsets, **not** observer wall offsets. Do not compare
the two axes without their origins. The older clean-media failure has the
same early-clear pattern, but it was not instrumented: its exact abort write
cannot be retroactively proven from the original report.

### What remains to fix

Investigate TOUT/IRQ13 delivery against PIT/IRQ10 service at this transition,
including DSP catch-up and the live-poll time anchors. Present code raises
IRQ13 from newly observed DSP timer expiries in both Python and native poll
paths. The firmware watchdog must not be patched out, and IRQ13 must not be
arbitrarily capped to make a call appear successful. Clean RTP counters do
not certify this internal interrupt ordering.

## A different failure: LAPM XID timeout

The immediately preceding instrumented trial reached the late modulation
reports, received DSP `0002:0000`, and continued into error-control startup,
but never printed CONNECT. At wall 48.5047 s the cause recorder at `ab33b`
recorded **0eh**, called at `ae77e`. ATI6 explicitly returned:

```
Protocol               LAPM
Speed                  16800/41333
Last Call              00:00:00
Disconnect Reason is XID Timeout
```

This is distinct from the watchdog abort. That trial also has one missing
160-sample RTP packet; this does not prove the packet caused the XID timeout.
Neither trial is a successful data connection simply because ATI6 displays
rates. Zero ATI6 BLER/timeout counters before CONNECT do not certify the
startup exchange.

## ATI6's half-speed time is explained by firmware arithmetic

ATI6's formatter at `ccd88` prints hours/minutes/seconds from
`[c8ca]`, `[c8c9]`, `[c8c8]`. The fractional countdown `[c8c7]`:

- decrements at `a46fe` on the system-timer path;
- invokes the seconds increment at `a478b` when it reaches **100**;
- reloads **200**, not 100, at `a470e` when it reaches zero;
- skips the seconds increment on that reload (`a475e -> a47ab`).

Consequently steady-state displayed seconds advance once per **200 system
ticks**, while the Hayes S-register conversions use 100 ticks per second
(see the derivation in `courier_emu/pit.py`). That explains the approximately
half-scale ATI6 field without concluding that the media clock is half-speed.
Do not double the PIT clock to "correct" this display.

`tools/probe_imodem_firmware_accounting.py` executes the original arithmetic
in isolation, without calls or firmware patches. It stops before unrelated
timer housekeeping/mailbox I/O and validates the instruction bytes first.
With an initial fractional count of 200, ticks 100/200/300/400/500 display
1/1/2/2/3 seconds. The original watchdog sets no abort at entry 49, sets 80h at
entry 50, and its count resets on the original system-timer reset instruction.
This is evidence for the arithmetic, not a full-board scheduler regression.

## Completed 60-second hold, with qualifications

Three diagnostic repeats connected at 49333/V90/LAPM: two completed measured
five-second holds, and one completed **60.000591 seconds after CONNECT**.
The latter delivered the MULTITECH login prompt, remained online through the
hold and ATI6, and was deliberately ended with ATH. ATI6 reported:

- **16800/49333**, LAPM, 51 received octets;
- zero block resends, retrains, BLERs, link timeouts and NAKs;
- Current Call **31 seconds**, consistent with the arithmetic above.

This run has clean RX counters but **one TX rebuffer and a 124.07-ms maximum
TX packet gap somewhere in the full capture**. Its timing relative to the
hold has not been isolated. The link survived, but the run is not certified
as a clean-media soak. No login credentials or test payload were submitted.
It is an idle/banner hold, **not sustained-payload or throughput evidence**.
The next two instrumented calls failed as described above, so repeatability
is not solved. Instrumentation and host scheduling can affect outcomes.

## Evidence and safety

Private archives under `.artifact-archives/`:

- `imodem-v90-failure-analysis-20261025/`: decoded saved recordings and isolated
  `firmware-accounting.json` verification.
- `imodem-v90-cause-20261025-165858/`: first five-second repeat. Its probes were
  mistakenly installed after `emu_start` had cached the hook list, so this
  run supplies connection evidence, **not valid firmware-probe coverage**.
- `imodem-v90-cause-static-20261025-170251/`: constructor-installed probes,
  second five-second hold; intentional ATH entries confirm probe operation.
- `imodem-v90-cause-all-20261025-170825/`: completed 60-second hold.
- `imodem-v90-abort-probe-20261025-1/`: explicit XID timeout.
- `imodem-v90-abort-probe-20261025-2/`: clean-media IRQ watchdog abort.

The last five archives include complete reports, observer/probe events,
G.711 audio, scoped PBX/container captures, and launch scripts. Every call
used a fresh private saved-profile copy and checked account 2903/destination
6313 idle first. No PBX, ATA, or answering-modem settings were changed.
Captures and calls have ended. The experimental live scheduler remains
opt-in; no timing fix is claimed by this investigation.
