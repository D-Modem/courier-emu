# Failed independent bidirectional 60-second traffic gate

The call holds carrier, but fails sustained traffic: 2 complete upstream and
14 downstream records, with long gaps and incomplete outstanding records.
It negotiates 52000 downstream / 33333 upstream. Full-window 53333 controls
also fail. The three-minute extension was not run.

`verification.json` independently replays all captured traffic prefixes from
`result.json`: 7,553 analog-received bytes and 1,390 I-modem-received bytes.
Complete-record hashes and partial prefixes match. Verification still fails
because traffic stalls and too few upstream records arrive.

Post-window ATI6 reports 623 BLERs, 63 resent blocks and 10 link timeouts.
The measured health snapshot has no UART drops, PCM underruns, occupied-bank
writes or changing unacknowledged read pairs. These observations do not yet
locate the first bad bit or establish the block errors' underlying cause.

Recheck without placing a call (expected exit status 1):

```sh
PYTHONPATH=. .venv/bin/python artifacts/imodem-analog-x2-native-traffic-independent-60s-20261018/verify.py
```

See [the diagnosis, controls and reproduction command](../../docs/imodem-analog-x2-traffic-20261018.md).
