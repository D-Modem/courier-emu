# I-modem: faster receive negotiation without sacrificing TX reserve

Follow-up to the [UART starvation correction](imodem-v90-uart-starvation-fix-20261025.md).
The emulated I-modem now demonstrates **31,200 bit/s receive / 49,333 bit/s
transmit** on 6312 and **28,800 / 49,333** on 6313, including clean 60-second
holds and ten ATI6 queries on each port.

These are **negotiated rates, not measured application throughput**. The
49,333-bit/s PCM direction has not demonstrated a repeatable increase.

## Direction matters

On this particular connection the I-modem is the **digital V.90 endpoint**:
its outgoing training contains INFO0d, not INFO0a. Its PCM/V.90 direction is
**I-modem → RasFinder**; the opposite direction uses V.34. ATI6's speed pair
is receive/transmit from the I-modem's perspective. Thus the improvement is
in the direction carrying the RasFinder login banner back to the I-modem.
Calling the second number the I-modem's download speed would be misleading.
ATI11 also reports V.34+/V.90 and an 8,000-symbol/s transmit direction; its
unpopulated zero-valued measurements are not usable line-quality evidence.

## What changed

Previously `--bri-sip-buffer-ms` set **both** bearer receive reserve and RTP
transmit reserve. Receive also has the separate timestamp-based RTP delay.
The qualified conservative setup used 200 ms for all three, nominally:

- 200 ms RTP receive delay + 200 ms bearer receive reserve;
- 200 ms transmit reserve.

The new `isdn-run` option **`--bri-sip-tx-buffer-ms`** overrides only the
transmit reserve. It allows a low-delay receive path while retaining the
larger margin that protects outgoing media during firmware diagnostic output.
With no override, legacy queue sizing and defaults are unchanged.

The faster qualified preset is this argument fragment for the existing
idle-gated, bounded full-rate-profile runner:

```sh
--bri-sip-buffer-ms 20 \
--bri-sip-tx-buffer-ms 200 \
--bri-sip-rtp-delay-ms 40
```

That reduces nominal receive reserves from 400 to 60 ms while preserving the
200-ms transmit reserve. These are queue settings, **not a measured RTT**.
The faster result is consistent with latency-sensitive V.34 negotiation;
the precise firmware rate-selection decision has not been traced.

No firmware, modem rate table, watchdog, 512-instruction polling cadence,
ordinary port budget, holding-word protection or DSP recovery allowance was
changed for this improvement. CPU and DSP clock settings are unchanged.
Neither PBX nor answering-modem configuration was changed.

## Controlled results

All rows below used the full-rate 230,400-bps saved DTE profile, S54=0,
S58=0, automatic line speed (`&N0&U0`), byte-exact PCMU, and the opt-in live
poller. Each call used a fresh private copy of the profile.

| Run | Destination | RX bearer / RTP delay / TX reserve (ms) | ATI6 receive/transmit | Hold | Result |
|---|---|---|---|---|---|
| Earlier conservative qualification | 6312 | 200 / 200 / 200 | 12000/49333 | 60 s | Clean; ten ATI6 queries |
| Earlier conservative qualification | 6313 | 200 / 200 / 200 | 16800/49333 | 60 s | Clean; ten ATI6 queries |
| Faster final | 6312 | 20 / 40 / 200 | **31200/49333** | **60.000021 s** | Clean; ten ATI6 queries plus ATI11 |
| Faster final | 6313 | 20 / 40 / 200 | **28800/49333** | **60.000055 s** | Clean; ten ATI6 queries plus ATI11 |
| Conservative control after faster finals | 6312 | 200 / 200 / 200 | **12000/48000** | 20.000378 s | Clean; ATI6 plus ATI11 |

Returning to the old buffers on the same port, same native library, same
profile and same idle-host CPU affinity returned the receive rate to 12,000.
The faster 6312 receive negotiation is **2.6×** that control; 6313 is about
**71% higher** than its earlier qualified 16,800. These few calls do not
establish a success-rate distribution or a guaranteed rate ceiling.

Both faster final calls:

- Reported `CONNECT 49333/ARQ/V90/LAPM` and delivered the login prompt.
- Completed a sample-counted **60.000000-second** hold, agreeing with host
  timing within 0.1 ms.
- Returned ten Online/LAPM ATI6 replies with unchanged rates and zero resends,
  retrains, BLERs, link timeouts and NAKs, followed by ATI11 and deliberate ATH.
- Had **zero TX rebuffers across the complete session**. Maximum local TX gaps
  were **23.12 ms** (6312) and **24.60 ms** (6313).
- Had zero RX missing/late samples, sequence gaps, timestamp jumps, reordering,
  duplicates, invalid packets and SSRC changes.
- Had no observed watchdog/XID recorder hits, torn data words or busy-bank writes.
- Have complete PBX/container packet captures with zero kernel drops,
  contiguous RTP sequences, 160-sample timestamp steps, and matching packet-byte
  hashes at both capture points for both streams.

Only the 51-octet banner was received as application data. No login credentials
or sustained payload were submitted. This does not qualify bulk file transfer.

## Rejected trials and remaining limits

The progression is retained rather than reporting only successful calls:

- S39=8 and S54=31 (3429-symbol/s-only capability) each still negotiated
  14400/49333 with 200-ms buffers. Neither was retained.
- Symmetric 80-ms bearer reserves plus 80-ms RTP delay reached 31200/49333,
  but ATI6 output caused one TX rebuffer. Shrinking the transmit margin was
  rejected; the independent TX override fixes that trade-off.
- RX bearer 40 ms / RTP delay 60 ms / TX 200 ms completed a clean 20-second
  pilot at 28800/49333. RX 20 / delay 40 / TX 200 then reached 31200/49333.
- Concurrent host compilation invalidated several longer vmhost attempts:
  media rebuffers and DSP debt appeared. Moving to another physical core and
  trying an E-core with a `-march=native` build did not yield a clean ten-query
  full session. The successful final pair waited for the host load to end and
  used the **original portable native build**, not that experimental binary.
- A Mac pilot had a 268.88-ms receive arrival gap, five late packets and 800
  missing samples, and did not CONNECT. The PBX capture had smooth outbound
  RTP while incoming Mac RTP had a 253.65-ms gap, despite the Mac sender's
  local maximum gap being 44.74 ms. The low-delay preset is **not qualified
  for that jittery network path**.
- The first idle-host 6312 attempt connected at 31200/49333 but disconnected
  after 52.09 seconds. Its incoming stream has **nine sequence-gap events,
  twelve missing packets / 1,920 samples**, identical at the PBX and container,
  with zero capture kernel drops. The loss origin before those capture points
  is unknown; this call is excluded from qualification. A separately gated
  repeat produced the clean final 6312 session above.

Enough host execution headroom and a low-jitter network remain prerequisites.
Do not select smaller receive buffers merely to request a higher number on an
unmeasured path. The conservative preset remains useful when those conditions
are not met; no global default was changed.

## Reproduction and evidence

The qualified final pair ran in CT 127, pinned to CPU 1 after the competing
compilation ended, with `COURIER_LIVE_POLL_ELISION=1` and:

```sh
COURIER_C5X_LIBRARY=/root/courier-emu/.build/libcourier_c5x-live-uart-final.so
```

The library build is unchanged from the UART correction:

```sh
clang++-19 -std=c++17 -O3 -fno-semantic-interposition -shared -fPIC \
  native/c5x_core.cpp native/c5x_capi.cpp \
  -o .build/libcourier_c5x-live-uart-final.so
```

Use the saved-profile initialization described in the
[original V.90 report](imodem-rasfinder-v90-20261025.md), not an erased NVRAM
profile. Check account 2903 and the individual destination for idleness before
**each** bounded call. Keep credentials out of logs/files/argv. Captures must
be bounded, owned and cleaned up; do not stop sibling calls.

Private evidence:

- `.artifact-archives/imodem-v90-faster-idle-repeat-6312-20261025-221957/`
- `.artifact-archives/imodem-v90-faster-idle-final-6313-20261025-221232/`
- `.artifact-archives/imodem-v90-faster-buffer-control-6312-20261025-222303/`
- `.artifact-archives/imodem-v90-faster-verification-20261025/`

The read-only verifier checks local/remote runtime-source hashes (including
CLI buffer resolution), exact library hash, phase/sample timing, all ten ATI6
replies, ATI11, native/media counters, and complete two-ended RTP captures.
The excluded packet-loss session has a separate capture comparison.

Regressions: **157 passed on macOS**; **154 passed, 3 skipped on Linux** using
the exact final portable library. Linux skips are two optional-firmware cases
and one optional saved-hardware-capture case. New buffer tests cover defaults,
legacy inheritance, TX-only overrides in both directions, minimum validation,
and independent RTP delay. Final safety checks found no owned call processes,
owned capture PID files or account-2903 channels.
