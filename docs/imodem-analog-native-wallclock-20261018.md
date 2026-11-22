# Analog Courier / I-modem x2 through native wallclock mode

The subsequent [60-second sustained-traffic audit](imodem-analog-x2-traffic-20261018.md)
fails despite retained carrier. The successful checks below establish short
marker exchange, not reliable sustained data transfer.

Two bounded native-wallclock calls negotiate **53333/ARQ/x2/LAPM/V42BIS**
at the analog Courier and **33333/ARQ/x2/LAPM/V42BIS** at the I-modem.
Both distinct terminal markers arrive intact. The longer repeat retains
carrier at the instruction limit, with no CPU/DSP errors, receive underruns,
I-modem UART overruns or terminal output drops.

[Verified repeat](../artifacts/imodem-analog-x2-native-wallclock-bounded-repeat-20261018/verification.json)
contains the individual acceptance checks. Its adjacent `verify.py` regenerates
the report from `result.json`, without running or modifying either modem.

This extends the [saved 2026-10-03 instruction-clocked result](imodem-analog-x2-20261003.md)
using the live-call path introduced by `dbcb0a0`. These are local socket
calls using the original firmware, native DSP and modeled analog codec;
they do not measure SIP-network performance or sustained application throughput.
No carrier, training outcome, negotiated rate or received payload is injected.

## First reproduced failure and focused change

The pair probe previously had no way to select wallclock operation.
`--wallclock` now marks the socket bearer as externally clocked and fed
ahead, selecting `IsdnMachine`'s native live-call advance. Checkpoints and
the final clock report confirm native I/O is live, wallclock mode is active,
and no per-frame Python service callback is installed.

The first attempt delivered both markers at 52000 downstream, but its repeat
failed with `NO CARRIER`. The failed I-modem reached replies `0002:0000`
and `0003:0000` around 12.6/13.1 seconds of DSP call time, but never produced
a Hayes CONNECT or delivered terminal data. It cleared around 20.3 seconds.
Both DSP error reports and the I-modem PCM-underrun count were clean.

The socket bearer's fallback clock now uses wall time during an active live
call. A regression confirms that fast CPU polling cannot manufacture idle
audio samples. This is necessary clock-domain hygiene, but it did **not**
resolve the reproduced failure by itself: the failed repeat recorded zero
active idle-fill samples.

`ImodemHostIo::advance` could execute the entire wall-clock deficit in one
CPU service opportunity. After a host delay, several milliseconds of DSP
work could therefore run before the supervisor got another turn to service
its finite data lanes. The wallclock branch now advances at most 5040 DSP
cycles (125 microseconds) per invocation. The absolute wall target remains
unchanged, so subsequent advances still execute all owed cycles. The
instruction-clocked branch is unchanged. Both calls after this change
reach 53333 and exchange their markers. This identifies a scheduling hazard
and a passing correction; the captures do not directly count every internal
firmware FIFO overflow in the earlier failed calls.

## Captures

All directories below are under `artifacts/` and retain `result.json`,
`summary.json`, local audio/codeword captures and DSP checkpoints.

| Directory suffix after `imodem-analog-x2-native-wallclock` | Result |
|---|---|
| `-20261018` | Unbounded advance: 52000, both markers |
| `-instruction-idle-20261018` | Diagnostic old idle clock: NO CARRIER, no markers |
| `-repeat-20261018` | Wall-time idle clock, unbounded advance: NO CARRIER, zero active idle fill |
| `-bounded-20261018` | Bounded advance: 53333, both markers |
| `-bounded-repeat-20261018` | Bounded advance: 53333, both markers, verified pre-close carrier |

The final repeat runs 900 million I-modem instructions and 450 million analog
instructions. Its active media window is 3718 frames, or 74.36 seconds, with
594,880 G.711 octets in each direction. Native wallclock I/O remains active
at the limit. The analog peer is still off hook, its call state is answered,
and the socket is still connected in `bridge_at_limit`.

The analog worker continues after the I-modem reaches its instruction limit
and closes the socket. Its final terminal capture consequently includes
`NO CARRIER`. The new pre-close snapshot distinguishes that teardown from
the earlier genuine training failures. The older probe's `carrier_connected`
field only means a CONNECT occurred somewhere in the transcript.

## Reproduction

```sh
COURIER_LINE_FRAME_MS=20 PYTHONPATH=. .venv/bin/python tools/probe_imodem_analog_pair.py \
  --wallclock \
  --analog-settings 'X1S27=1S54=0S58=48&A3&B1Q0&U26&N39' \
  --imodem-settings 'S54=0S58=48&A3&B1Q0' \
  --imodem-nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --instructions 900000000 --analog-instructions 450000000 \
  --analog-send ANALOG-X2-53333-BOUNDED-REPEAT \
  --imodem-send IMODEM-X2-53333-BOUNDED-REPEAT \
  --output artifacts/imodem-analog-x2-native-wallclock-new
```

The relevant selection passes **69 tests**, including native port models,
native bearer and lookahead, I-modem data lanes, analog pair parsing,
wallclock peripheral timing and SIP playout. The new catch-up regression
executes a three-frame deficit across three native advances, verifies all
owed cycles retire, and verifies the core cannot run ahead of its target.
