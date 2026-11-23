# Isolated vmhost I-modem investigation, 25 October 2026

## Status

**Superseded by a successful V.90 follow-up:** a high-rate saved profile plus
S54=0 reaches **CONNECT 49333/ARQ/V90/LAPM**, delivers the MULTITECH login
prompt, and returns ATI6 speed **12000/49333**. See the
[V.90 result and qualifications](imodem-rasfinder-v90-20261025.md).
The subsequent [instrumented failure analysis](imodem-v90-failure-analysis-20261025.md)
identifies a clean-media IRQ13-watchdog abort, a distinct LAPM XID timeout,
and firmware half-scale ATI6 time accounting. The later
[live timing correction](imodem-v90-live-timing-fix-20261025.md) fixes the
identified watchdog path and completes clean 60-second hold windows on both
ports. The subsequent [UART service correction](imodem-v90-uart-starvation-fix-20261025.md)
also completes ten diagnostic queries after each 60-second hold with zero
full-session TX rebuffers or RX loss; application payload remains unqualified.
The following records the earlier investigation, before that configuration
change; it must not be read as the current V.90 status.

At this earlier stage, no V.90 connection was demonstrated. Follow-up calls to **6312 and 6313** both
reached `CONNECT 9600/ARQ`, then `NO CARRIER`. Offline CRC-checked INFO1a
selects **V.34** on both calls; this conclusion does not depend on interpreting
the numeric CONNECT rate with fixed DTE (`&B1`). Both had zero receive missing
samples/late packets and zero transmit rebuffer events. These are real modem
training-path timing results, unlike the earlier 6311 fallback calls.

The original Linux run could not maintain transmit pacing, and some later
6311 calls did not reach a modem answer. Do not count those fallback calls as
V.90 failures or as successful training-path timing tests.

## Isolated deployment

- Host: `root@vmhost.net.cryan.nz`, Proxmox LXC **127**.
- Container: `courier-imodem-test`, DHCP address `192.168.88.127` at test time.
- Debian 12, 4 cores, 2048 MiB RAM, 8 GiB root disk on `satadir`, unprivileged,
  no automatic startup. Existing containers were not changed.
- Source: `/root/courier-emu`, copied from the local working tree, including
  existing uncommitted changes; **not** a clean Git revision.
- Firmware: `Ie030002.nac`, with the captured C5x on-chip ROM.
- Calls used account 2903, PCMU, `AT*V2=3`, `AT&W` (ephemeral NVRAM only),
  `AT&M5&K0S58=0&B1`, and `ATDT6311`. Both media reserve and receive deadline
  were 200 ms. No answering-modem or PBX settings were changed.
- Password was supplied over SSH/stdin into the process environment, not
  written to disk or put in process arguments. Each attempt checked that the
  destination and account were idle. Calls were single instruction-bounded
  runs, not an automatic redial loop.

## Timing findings

The first container call had no late receive packets or missing receive
samples, but 20 transmit rebuffer events and a maximum transmit gap of 344 ms.
Its peak DSP clock debt was 235,214,772 cycles, about 11.7 seconds at 20.16 MHz.
The receive recording contains a roughly 5.4-second 2100-Hz answer stretch,
then a 2250-Hz stretch; it is an actual modem-answer recording, unlike the
later fallback recordings. This spectral finding alone does not decode V.8
or establish the identity of the physical answering modem.

Clang 14 plus pinning to allowed CPU 1 did not fix the timing failure. Clang
19 was also built. A cProfile run showed extensive Python scheduling overhead
(781,250 full timer polls for 400 million supervisor instructions). Profiler
results perturb timing and are not clean call-performance measurements.

An experimental change granting a larger DSP advance per supervisor turn did
not fix the problem and was **reverted**. Existing port-read/holding-word
budget protections remain intact.

## Opt-in native live polling experiment

`COURIER_LIVE_POLL_ELISION=1` allows a connected B1 SIP call to run bounded
native polling windows, up to 1 ms, while preserving the existing gates for
pending Q.931, serial activity, device writes, and receive lookahead.

The experiment publishes monotonic anchors for both DSP and peripheral time;
native polls extrapolate those clocks rather than using guest instruction
throughput. A supervisor pacing anchor also prevents instruction-based
firmware delays from racing ahead while native polling makes the CPU faster.
This is **disabled by default** and not certified for payload traffic or all
firmware modes. It has not demonstrated V.90 interoperability.

The paced attempts had zero transmit rebuffer events, with maximum packet
gaps of 24–25 ms. **Their transmitted PCMU was silence**, however, so these
are idle-stream pacing results, not proof of correct modem training output.
The unpaced version cleared very early; it is not a successful control.

Regression command:

```
.venv/bin/python -m pytest -q \
  tests/test_imodem_live_poll.py tests/test_native_port_models.py \
  tests/test_native_machine.py tests/test_imodem_pair_keepalive.py \
  tests/test_bearer_sip_playout.py tests/test_sip_media_clock.py
```

Result: **44 passed**. This includes guards on wall-target extrapolation and
BRI quiet-window gating, but does not certify the complete experimental
scheduler or replace an active training/data-mode hardware regression.

## Earlier 6311 calls: endpoint/fallback gating is required

The captured repeat had 1059 outgoing PCMU packets over 21.16 seconds, with
no arrival gaps exceeding 100 ms. The incoming stream had 561 packets and a
10.012-second gap: sequence number 60974 -> 60975, timestamp 84474 -> 164562.
Thus the gap was already present on the wire, not a lost network packet or
our RTP receiver dropping intervening packets. It does not by itself prove
an ATA impairment; intentional endpoint/fallback silence is possible.

Offline analysis of that repeat finds no V.8/INFO exchange; transmitted
codewords are mu-law silence (0xff/0x7f), while the received waveform has
speech-like spectral variation and a 700-Hz stretch, rather than a modem
answer tone. The PBX CDR for those recent calls has no outgoing destination
channel and ends with `Dial` arguments `,20,tT`, unlike earlier calls that
show `PJSIP/6311-...` as their actual destination channel. This is consistent
with dialplan fallback, not a confirmed RasFinder answer.

Current read-only PBX checks find:

- 6311/6312/6313 registered to AudioCodes `10.69.70.221`.
- Historical RasFinder hunt group 3999 tries 8416, 8423, and 8409.
- 8416 currently has no registered contact and is unavailable.

These facts alone did not identify which physical ATA port reached the
RasFinder. Subsequent user-requested 6312/6313 calls established actual modem
answers and V.34 selection on those ports, as recorded below. Physical modem
identity is still not independently inspected. Do not infer physical wiring
from an extension label. No forwarding, registration, or peer setting changed.

## User-requested follow-up: 6312 and 6313

One call per port ran sequentially from CT 127, with 200-ms reserve/deadline,
CPU 1 affinity, the opt-in paced live poller, and the same modem settings.

| Port | Terminal result | INFO1a selection | RX missing / late | TX rebuffer | Maximum TX gap |
|---|---|---|---|---|---|
| 6312 | CONNECT 9600/ARQ, then NO CARRIER | V.34, selector 5 | 0 / 0 | 0 | 23.6 ms |
| 6313 | CONNECT 9600/ARQ, then NO CARRIER | V.34, selector 5 | 0 / 0 | 0 | 24.1 ms |

The outgoing V.8 CM candidate is `c1 45 13 10 8d`; the incoming JM candidate
is `c1 45 13 10 0d`. Both directions subsequently carry CRC-accepted 17-bit
INFO0. The incoming 38-bit INFO1a has protocol selector 5 (V.34), not selector
6 (V.90). Thus these are V.34 negotiations, not V.90 training failures.

Both reports have zero native data torn words and zero busy-bank writes,
with thousands of data-bank posts and ACKs. This is stronger active-path
pacing evidence than transmitting silence, but it does not establish stable
payload transfer: both calls disconnect shortly after reporting CONNECT,
and no application payload or login prompt was verified.

Private follow-up archive:
`.artifact-archives/imodem-rasfinder-6312-6313-20261025-145850/`.
It contains scoped container/PBX captures, reports, both audio directions,
and offline decoder timelines. No firmware or scheduler change was made
between these two calls.

## Evidence

Private local archive: `.artifact-archives/imodem-vmhost-20261025/`.
Remote per-run outputs: `/root/courier-emu/artifacts/rasfinder-*` in CT 127.
The archive includes run scripts, summaries, firmware reports and audio,
profile data, scoped container/PBX captures, current routing checks, and
selected PBX CDRs. Packet captures and SIP logs are private.
