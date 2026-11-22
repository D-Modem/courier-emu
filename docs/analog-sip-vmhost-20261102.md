# Analog SIP host comparison: vmhost, 2 November 2026

## Scope

User-requested host comparison for the analog 403 `SipLine` path to Asterisk
7900/7910. This is not the previously qualified I-modem live bearer path.

- Host: `root@vmhost.net.cryan.nz`, existing running Debian 12 CT 127,
  `courier-imodem-test`, address 192.168.88.127.
- Isolated snapshot: `/root/courier-sip-20261102-113720`; existing
  `/root/courier-emu` left untouched.
- Snapshot tar SHA256:
  `a6d2fc1e0600a98568bcb5e8049293ffb2c37da38bfffe5fd8926776b7f75eb6`.
  Includes current uncommitted Python/native source, tests/tools, captured
  403 ROM and on-chip DSP ROM. Not a clean Git revision.
- Own venv: Python 3.11, Unicorn 2.1.4, pytest. The CLI's default CPU remains
  the native-accelerated **interpreter**, not Unicorn; installing Unicorn is
  not a claim that these calls used the Unicorn engine.
- Native C5x/x86 libraries built in the snapshot. Initial build used default
  GCC; a controlled repeat rebuilt both using Clang 19 at the same O3 flags.
- Same 150-million-instruction 403 calls as the local tests, account 6000,
  `ATX4S39=8DT7900` / `...7910`, board 7, idsdl403 fixture, tick 5 ms,
  `--exchange`, default 40-ms adapter reserve, 60-ms RTP delay, 150-ms TX
  reserve. No gain, firmware, PBX, endpoint or container allocation changes.
- SIP credential obtained read-only and forwarded over SSH/stdin into the
  process environment, not saved in scripts, arguments or result files.
- Each call preflight-checked the shared trunk and account. No competing call
  was stopped. Clang 7910 repeat was skipped when the shared route was busy.
- 36 focused receive/pacing tests and an offline 403 boot smoke test passed
  before the first live call. This is not a full Linux suite qualification.

## Results: moving hosts did not cure the slowdown

| Build / destination | Process wall time including boot/dial | Result |
| --- | ---: | --- |
| GCC / 7900 | 45.53 s | Analog RX backlog capacity exception |
| GCC / 7910 | 34.86 s | Analog RX backlog capacity exception |
| Clang 19 / 7900 | 35.38 s | Same backlog capacity exception |
| Clang 19 / 7910 | — | Skipped: route still busy at preflight |

All three attempted calls exited 2 rather than timing out. The two-second
analog handoff bound correctly refused to accumulate more delayed audio.
The CLI worker exception means there is no final JSON modem/status report;
no modem CONNECT or sustained payload result is established. WAVs, pcaps and
tracebacks were retained. These are not successful connects or hold tests.

## Capture observations

Scoped CT tcpdump captures (`udp and host 192.168.88.122`) reported zero kernel
capture drops. Linux SLL2 originals were retained; offline IPv4-only copies
strip the 20-byte cooked header while preserving packet timestamps/IPv4 data
for the existing pcap decoder. `packet-summary.json` retains stream counts,
intervals and sequence-gap diagnostics.

| Build / destination | RX packets | TX packets | Max inbound interval | Max outbound interval |
| --- | ---: | ---: | ---: | ---: |
| GCC / 7900 | 1282 | 1194 | 38.61 ms | 154.40 ms |
| GCC / 7910 | 660 | 563 | 31.60 ms | 170.17 ms |
| Clang 19 / 7900 | 770 | 680 | 42.19 ms | 162.19 ms |

No captured stream has a forward RTP sequence gap. Each outgoing stream has
14 packet intervals exceeding 40 ms. Inbound GCC streams have none; the Clang
incoming stream has one. Counts differ partly because of startup/teardown,
but the timestamps and explicit backlog exception support inadequate local
production/consumption headroom, not a simple missing inbound-packet story.
The capture does not independently observe delivery to the far modem.

The 7910 Clang preflight briefly saw the preceding 7900 test leg still active
following its worker exception, so that attempt was skipped rather than
redialled over it. A later final check showed no Asterisk channels at all and
no test process/tcpdump remained in CT 127. No manual PBX channel termination
or configuration change was made. Exception-path SIP cleanup deserves a
separate regression: immediate release was not established here.

## Evidence and next target

Local archives:

- `.artifact-archives/analog-sip-vmhost-20261102-113720/`
- `.artifact-archives/analog-sip-vmhost-clang-20261102-113720/`

Remote snapshot retains `gcc-results/` and `vmhost-results/` (Clang) separately.
The source, environment and native builds remain available for reproduction;
no persistent job or auto-redial service was installed.

The subsequent [quiet-pass headroom correction](analog-sip-headroom-20261102.md)
profiles the offline equivalent, reduces its observed wall time from 32.19 to
17.58 seconds with identical parsed reports, and completes bounded vmhost
calls on both destinations with no reported RX loss or TX/adapter rebuffering.
Neither reaches observed modem carrier within the window; training and payload
remain unqualified. Switching compiler alone did not demonstrate a cure;
larger receive queues would merely allow more audio delay.
