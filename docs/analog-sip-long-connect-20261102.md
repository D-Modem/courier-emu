# Longer vmhost runs: real 31200 V.34 carrier on 7900 and 7910

Follow-up: [explicit V.90 negotiation tests](analog-sip-v90-20261102.md)
confirm V.90 requests followed by V.34 fallback; V.90 is not yet connected.

## Result

The user correctly suggested increasing the instruction budget. Both original
403 firmware calls now report:

```
CONNECT 31200/ARQ/V34/LAPM/V42BIS
```

Both retain CD and ARQ, and `online_mode=true`, at the end of **600 million
instructions**. The previous 150-million-instruction runs ended too early:
carrier first appears at instruction **187543296** on 7900 and **201280963**
on 7910. The earlier empty result output must not be treated as evidence of
broken result reporting or a completed carrier failure.

This follows the [quiet-pass scheduling correction](analog-sip-headroom-20261102.md),
which removed the previously observed vmhost receive-backlog failures.
Increasing the budget alone was not tested against the old, slower scheduler.

## Test conditions

Same isolated vmhost CT 127 snapshot, captured 403/on-chip ROMs, account 6000,
`ATX4S39=8DT7900` / `...7910`, factory S39=8, automatic modulation, board ID 7,
idsdl403 fixture and 5-ms board tick. The source and native libraries are the
same as the successful short pacing controls. No firmware, gains, PBX, peer,
codec, buffer, interrupt-poll or oscillator settings changed.

Only the instruction budget increased from 150 million to 600 million. The
old `--line-frames 450` argument was removed so it could not independently
truncate the extended run. Each call has a 300-second external wall deadline;
both finish normally without reaching it. Password is forwarded over SSH/stdin
into the environment, not arguments or saved files. Each destination/account
is checked for occupancy before the single call; no automatic redial.

## Observations

| Observation | 7900 | 7910 |
| --- | ---: | ---: |
| Completed instructions | 600000000 | 600000000 |
| Process wall time, including boot/dial | 176.75 s | 176.85 s |
| Process exit / timeout | 0 / no | 0 / no |
| First CD assertion, guest instruction | 187543296 | 201280963 |
| Final CD / ARQ / online mode | on / on / true | on / on / true |
| Carrier deassertion after first assertion | none recorded | none recorded |
| Adapter active silence-fill / RX rebuffers | 0 / 0 | 0 / 0 |
| RTP late packets / missing samples | 0 / 0 | 0 / 0 |
| TX rebuffer events | 2 | 1 |
| Maximum reported TX interval | 87.77 ms | 69.81 ms |
| UART RX/TX overruns | 0 / 0 | 0 / 0 |

No CPU/DSP/media error is reported. The CD event remains asserted through the
end of each run, providing roughly two minutes of post-carrier execution by
the configured guest clock. Exact CONNECT-to-end monotonic timestamps were
not recorded, so process runtime must not be labelled connected duration.
There are real TX production shortages; this is not a zero-discontinuity or
zero-firmware-error claim. No ATI6 BLER/retrain counters were queried.

7900 delivers the actual far-end application text:

```
BRI MODEM TEST LAB

1 Text echo
2 Upload test
3 Download test
4 Telnet to a host
5 SSH to a host
6 Timed binary stream
7 PPP lab link
Q Hang up
Select:
```

7910 delivers **ten FCS-valid PPP LCP Configure-Request frames** at the DTE.
Offline verification unescapes RFC 1662 octets and checks the PPP CRC residue
`f0b8`. Each unescaped frame is 30 bytes including FCS, with prefix
`ff 03 c0 21 01 28 00 18`: PPP LCP, Configure-Request. The frames are repeated
requests, not ten completed PPP negotiations. Their saved verification is
`7910-ppp-verification.json`.

The generic `data_rx_bytes`/`data_tx_bytes` counters remain zero on this ROM
path; actual serial hex/text and UART transmitted counts carry the observable
DTE output (201 bytes on 7900, 547 on 7910). Do not substitute those generic
counters for captured serial data.

## Qualifications and cleanup

This establishes genuine firmware CONNECT, real carrier and received
application/protocol bytes, not merely SIP 200 OK. It does **not** qualify
bidirectional payload equality, throughput/BER, PPP session establishment,
V.90/x2, zero retransmissions, or reliability under arbitrary host load. No
application data was transmitted after CONNECT in these calls.

Scoped CT packet captures report zero kernel capture drops. This does not
independently prove delivery at the remote modem. Both test channels clear
at teardown, and final checks find no test process or tcpdump left running.
No PBX or answering-modem configuration was modified.

## Evidence

Local archive:
`.artifact-archives/analog-sip-vmhost-long-20261102-124846/`.

Includes commands, 600-million-instruction reports, process timing, both PCM
directions, pcaps and capture statistics, pre/post/final channel checks,
`summary.json`, and independent PPP FCS verification. Remote originals remain
under `/root/courier-sip-20261102-113720/vmhost-long-results-20261102-124846/`.

The next useful qualification is a bounded echo/application exchange after
CONNECT, followed by a longer payload gate and firmware diagnostics. We no
longer need to speculate that these two calls cannot establish carrier.
