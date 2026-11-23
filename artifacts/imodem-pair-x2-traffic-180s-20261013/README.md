# Three-minute symmetric x2 traffic: PASS

Two unmodified `Ie030002.nac` supervisors and native C51 DSPs exchange a
byte-exact PCMU B channel. No carrier or received payload is injected.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_imodem_pair.py \
  --protocol x2 --settings 'S54=0S58=48&K0' \
  --nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --instructions 2000000000 --traffic-seconds 180 \
  --check-connect --check-x2 --output artifacts/imodem-pair-x2-traffic-repeat
```

| Observation | Caller | Answerer |
|---|---:|---:|
| CONNECT | 64000/ARQ/x2/LAPM | 64000/ARQ/x2/LAPM |
| Sent records | 340 | 340 |
| Received records | 340 | 340 |
| Verified received bytes | 180,540 | 180,540 |
| Last received record, seconds after CONNECT | 180.0 | 180.1 |
| Largest receive gap, seconds | 4.5 | 4.6 |
| Active bearer duration after CONNECT, seconds | 375.4 | 375.5 |
| Partial/in-flight records remaining | 0 | 0 |
| Corruption, UART drops/overruns, PCM underruns | 0 | 0 |
| CPU/DSP errors | none | none |

`summary.json` has `traffic_verified: true`; the strict five-second receive
gap limit is unchanged. Adjacent terminal chunks are coalesced in
`serial_session`, while verification checks each byte during execution.
The UART's 64-KB report capture is deliberately only a prefix. Legacy
`data_delivery` fields in this run refer to unused short-marker arguments;
`traffic` and `verification.json` describe the actual numbered records.

Firmware SHA256:
`3f9a7aa8033323c28eebfee950b53267a67b7ad9141ebf30271918d0babbe358`

NVRAM SHA256:
`ddd313b85f2d57c0c157a46b2bc014a814f0cff0a853af35faa839aeca87db35`

This validates **three minutes of bidirectional digital symmetric x2 traffic**
and over six minutes of carrier survival, not continuous traffic throughout
the final idle tail, full-rate application saturation or analogue Courier
interoperability. See `../../docs/imodem-x2-traffic.md` for failing controls
and the UART capture-limit fix. The full test suite passes (397 tests).
