# Sustained I-modem x2 traffic

**Three minutes of traffic pass**: both modems report 64000/x2/LAPM and
deliver all 340 records (180,540 bytes) each way, with zero corruption,
UART drops, overruns, CPU/DSP errors or PCM underruns. Maximum receive gaps
are 4.5/4.6 seconds. Both calls remain active for over six minutes after
CONNECT, including the idle tail after traffic stops. See the
[three-minute evidence](../artifacts/imodem-pair-x2-traffic-180s-20261013/README.md)
and the earlier
[two-minute control](../artifacts/imodem-pair-x2-traffic-120s-k0-20261013/README.md).

`tools/probe_imodem_pair.py --traffic-seconds N` exercises the original
supervisors and native DSPs across a byte-exact PCMU B channel. Duration is
measured in 100-ms bearer frames **after modem CONNECT**, not wall time or
ISDN SETUP. Both endpoints send direction-specific numbered records, with
512 deterministic ASCII payload characters by default. Each receiver checks
every character and the sequence number; neither carrier nor received data
is injected.

Only one record per direction is outstanding. This bounds the input queue
and tests sustained bidirectional delivery, not saturation of the advertised
64-kbit/s line rate. The terminal profile must permit x2: use the existing
230400-bps National ISDN-1 profile, V.8 enabled and the working constellation.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_imodem_pair.py \
  --protocol x2 --settings 'S54=0S58=48&K0' \
  --nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --instructions 2000000000 --traffic-seconds 180 \
  --check-connect --check-x2 --output artifacts/imodem-pair-x2-traffic-new
```

`&K0` disables compression; LAPM remains enabled. The instruction limit must
leave enough bearer time for training, traffic and draining. An insufficient
limit fails rather than extending or fabricating a call. Traffic cannot be
mixed with marker sends or escaped ATI6 diagnostics.

Reports contain sent/received record and byte counts, partial-record length,
corruption details, post-CONNECT elapsed frames, last completed receive frame
and the largest receive gap. Verification requires at least ten good records,
requested duration, no gap over five seconds, recent traffic near the target,
active calls, no CPU/DSP errors, no PCM underruns, no UART overruns and no
host output drops.
One final in-flight record per direction is permitted and reported. Long-call
serial transcripts coalesce adjacent received chunks to avoid per-byte logs.

New reports also retain the ten largest receive gaps, with record sequence
numbers and start/end frames relative to CONNECT, plus the mean completion
gap (including the initial wait). `target_received_bytes` and
`target_receive_bytes_per_second` count complete records received during the
requested traffic window, excluding later draining and the idle tail. These
are verified record-byte rates, including headers, not application payload
rates or proof of line-rate throughput. Gap diagnostics stay bounded during
long soaks and do not change the five-second verification threshold.

## Terminal data handoff

The shared pair pump now waits for the original supervisor's data receiver
before queueing markers or traffic. In a Quad/I-modem V.34 control, CONNECT
text arrived 512 CPU instructions before callback `0e0e` (keypress abort)
changed to data-queue callback `46cc`. Typing immediately caused a genuine
Keypress Abort; reading the handoff fixes that race without any guest writes
or a fixed wait. `terminal_handoff` records the receiver/callback at CONNECT
and at readiness. The five-second x2 traffic regression still passes after
this change (`artifacts/imodem-pair-x2-handoff-control/`). See
[the Quad data evidence](../artifacts/quad-v34-lapm-online-handoff/README.md).

## 64-KB live-output bug

The first two-minute control held carrier but stopped delivering terminal
traffic after 65,495 payload bytes per receiver. `SerialChannel.advance()`
used the bounded 65,536-byte diagnostic capture as the live output queue;
when it filled, subsequent transmitted bytes were discarded and counted as
overruns. The Hayes result and setup replies occupied the preceding 41 bytes.
This was an emulator output-capture limit, not a demonstrated firmware
counter rollover.

`courier_emu/sio.py` now keeps a separate drainable live queue. The report
capture remains a bounded prefix, physical transmissions keep counting, and
host queue drops have their own explicit counter. Console deadlines and
native poll-elision readiness check live pending output, not capture length.
Regression tests cover both small captures and the actual 65,536-byte boundary.

The fixed default-compression control delivered all 222 records (117,882 bytes)
in each direction through 120 seconds, with no corruption, underruns or UART
drops. It still failed the strict five-second gap check: the largest gaps
were 7.1/7.0 seconds. The `&K0` control passes the same five-second gap threshold without changing
it. This is a useful compression-disabled control, not a complete diagnosis
of the default-profile latency; the long-gap observation alone does not
establish its cause.

Evidence directories:

- `artifacts/imodem-pair-x2-traffic-20261013/`: initial five-second control.
- `artifacts/imodem-pair-x2-traffic-120s-20261013/`: reproduced capture-limit stall.
- `artifacts/imodem-pair-x2-traffic-120s-fixed-20261013/`: capture fixed, long gaps retained.
- `artifacts/imodem-pair-x2-traffic-k0-smoke-20261013/`: five-second compression-disabled smoke test.
- `artifacts/imodem-pair-x2-traffic-120s-k0-20261013/`: passing two-minute traffic control.
- `artifacts/imodem-pair-x2-traffic-180s-20261013/`: passing three-minute traffic and six-minute carrier control.

These are **digital symmetric x2** calls between two I-modems. They do not
establish analogue Courier/server interoperability, a complete proprietary
PCM constellation reconstruction or full-rate application throughput.
