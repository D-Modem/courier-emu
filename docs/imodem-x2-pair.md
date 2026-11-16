# Two I-modems with x2 enabled, 2026-10-02

Two original `Ie030002.nac` supervisors and native C51 datapumps now connect
at **64000/64000 bps, x2/LAPM**, over a byte-exact PCMU digital B-channel.
The two different terminal payloads arrive at the opposite DTE. The settings are
`S54=0S58=48`, with the server and symmetric modes enabled, and a 230400-bps DTE
profile. The controls below document the earlier tests with a restricted rate.

The pair harness now accepts `--protocol x2`. It sets `S58=32` on the two ends.
This disables V.90, and the x2 server and symmetric modes stay enabled. The harness selects detailed
result codes (`&A3`) and terminal operation at the line rate (`&B0`).
The caller uses `*V2=3` and `ATD`. The answerer uses `ATA`. The harness does not inject a carrier result,
a DSP completion, or a received payload.

All of these controls return `CONNECT 9600/ARQ/V34/LAPM` on the two ends,
and they send the two markers:

| Settings | Evidence |
|---|---|
| `S58=32` | [detailed result](../artifacts/imodem-pair-x2-diagnostics-20261002/summary.json) |
| `S58=34`, asymmetric server disabled | [symmetric-only result](../artifacts/imodem-pair-x2-symmetric-only-20261002/summary.json) |
| `S54=0S58=34`, V.8 Call Indicate enabled | [V.8 result](../artifacts/imodem-pair-x2-v8-enabled-20261002/summary.json) |
| `S54=0S58=34&N0`, automatic line speed | [automatic-speed result](../artifacts/imodem-pair-x2-auto-speed-20261002/summary.json) |

The last control reads the live S-register file and confirms S54=0, S56=0,
and S58=34 on the two ends. The two ISDN calls stay active, the two DSPs report no
error, and the two PCM receivers report zero underruns. Its compact
[verification](../artifacts/imodem-pair-x2-auto-speed-20261002/verification.json)
records these observations, and it explicitly sets `x2_verified` to false.

`--link-diagnostics` waits after CONNECT, escapes with `+++`, and sends the
`ATI6` query to the guest. Then it continues with `ATO`. The two diagnostics report LAPM and
9600/9600, with zero retransmitted blocks, zero retrains, and zero link timeouts at the
time of the query. The queries run after the two different markers are sent.

To do the automatic-speed control again:

```sh
.venv/bin/python tools/probe_imodem_pair.py \
  --protocol x2 --settings 'S54=0S58=34&N0' \
  --instructions 200000000 --link-diagnostics \
  --originate-send X2-CALLER-123456789 \
  --answer-send X2-ANSWER-987654321 \
  --check-x2 --output artifacts/imodem-pair-x2-new
```

The command must have a local Unix socket. It saves the two firmware reports and
the summary before it fails the x2 check on the observed V.34 result.
`--check-connect` checks only the modem carrier. `--check-x2` also requires
that the CONNECT result names x2. Thus, a V.34 connection that operates cannot pass it.

The ten pair regression tests pass. These tests include the rejection of partial CONNECT
lines and of embedded `DISCONNECT` text. The remaining problem is the x2
capability negotiation and the modulation selection between two digital
datapumps. These controls do not find its cause.

## Caller DTE restriction identified

The 9600-bps result is not the expected limit of two digital I-modems.
The target is still x2 symmetric at 64000 bps. A later observer of the parameter sends
found a configuration restriction in the original harness:
the external DTE starts at 9600 bps (supervisor rate index 6).

The x2 eligibility function of the shipped supervisor at `b27ef..b27f4` rejects
the originating modem when bit 0 of `2600:e496` is set and the DTE rate index
at `2600:d1db` is below 8 (38400 bps). The answerer does not do that rate test.
The live trace confirms that the caller has flag 1/index 6 and sends no command
70. The answerer has flag 0/index 6 and sends `0070:39ff`. Thus,
in the original runs, the two sides never could both try x2.

The rate-mask routine at `b291c..b293c` adds one more restriction. On the
originating path, it intersects the PCM mask with `0003` for indices through
9 (57600), and with `0fff` for index 10 (115200). With index 11 (230400), the
full mask stays available. The observed masks agree:

| Interface | Caller DTE index | Caller x2 command | Caller PCM mask | Answerer PCM mask |
|---|---:|---|---|---|
| External, 9600 | 6 | absent | `0003` | `ffff` |
| Internal, 57600 | 9 | `0070:39ff` | `0003` | `ffff` |
| Internal, 115200 | 10 | `0070:39ff` | `0fff` | `ffff` |

The [comparison](../artifacts/imodem-pair-x2-eligibility-20261002/eligibility-comparison.json)
comes from the live mailbox observer, not from injected configuration
commands. The two runs with the internal interface pass the initial x2 eligibility
check, but they stop without modem carrier. Thus, they show the
configuration defect, not a successful symmetric connection.

The harness now gives `--trace-negotiation`, `--product-type`,
`--internal-baud`, `--nvram`, and `--establish` for these controls. The host UART
selection changes the divisor register of the emulated host. The original
firmware reads it and uses it. The saved-profile controls change the packed DTE
setting and seal its CRC again.

## Full-rate test, 2026-10-02

The saved NET3 profile rejects the mu-law bearer of the harness. The actual
NET3 validation branch at `5cb4e..5cb6d` requires A-law (`a3` or `23`).
If you select National ISDN-1 (`*W=2`) in the sealed profile, the profile accepts the
mu-law SETUP and establishes the two B channels. This removes the problem with the setup of the saved profile,
and it does not change firmware or inject carrier results.

The full-rate pair test boots the two external units at 230400 bps, disables
V.90 with S58=32, and exchanges PCMU octets directly. The two sides send
`0070:39ff` (x2 capabilities) and `0071:ffff` (unrestricted PCM rate mask),
with the live DTE index equal to 11. They exchange 170 frames, or 136000
octets in each direction. Then the caller clears normally and reports `NO CARRIER`.
Neither side reports modem CONNECT, and no application payload arrives.

[Full-rate evidence](../artifacts/imodem-pair-x2-full-rate-ni1-20261002/verification.json).
This is a valid full-rate negotiation attempt, but it does not give a
64000-bps symmetric connection. The DTE configuration restricted the earlier 9600 result.
When we remove that restriction, a training failure with the initial S54=64 configuration becomes visible. The additional
controls below establish x2 after V.8 is enabled.

The same saved profile and PCMU link are successful with x2 disabled (S58=43).
The two units report `CONNECT 31200/ARQ/V34/LAPM`, and the two application
markers arrive at the opposite DTE. This control isolates the current
failure to the negotiation/training path that is enabled for x2. The cause is not the
call setup of the saved profile or the basic bidirectional transport.
[Control results](../artifacts/imodem-pair-full-rate-v34-control-20261002/summary.json).

## V.8 and constellation controls

The two controls use the National ISDN-1 saved profile that operates, with a live
DTE rate index of 11 and the full `ffff` PCM rate mask. The server and symmetric
modes stay enabled in the two runs.

| Live settings | Carrier | Data markers |
|---|---|---|
| S54=0, S58=32 | Both report 64000/x2/LAPM, then NO CARRIER | Neither delivered |
| S54=0, S58=48 | Both report 64000/x2/LAPM | Both delivered exactly |

S54=0 enables V.8 Call Indicate and V.8 mode. S58=48 disables V.90 and
adds the -6 dBm constellation. Its server-disable and symmetric-disable
bits stay clear. The successful run sends `0070:3dff` and `0071:ffff`
on the two sides. It exchanges 252 complete 100 ms bearer frames, and it records
zero PCM receive underruns and no CPU or DSP error. The short marker test
shows symmetric carrier and bidirectional data. It does not show sustained
64-kbit/s application throughput.

[Successful verification](../artifacts/imodem-pair-x2-full-rate-high-power-20261002/verification.json)
and [normal-constellation comparison](../artifacts/imodem-pair-x2-full-rate-v8-server-20261002/verification.json).

```sh
PYTHONPATH=. .venv/bin/python tools/probe_imodem_pair.py \
  --protocol x2 --settings 'S54=0S58=48' \
  --nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --trace-negotiation --instructions 180000000 \
  --originate-send CALLER-X2-S58-48 --answer-send ANSWER-X2-S58-48 \
  --check-connect --check-x2 --output artifacts/imodem-pair-x2-repeat
```
