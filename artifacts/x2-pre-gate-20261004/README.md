# Symmetric x2 call on the bearer, before the gate

`analysis.json` is the output of `tools/analyze_bearer_handshake.py` on the octets that each
I-modem received in the recorded symmetric call (`S54=0S58=48`, Ie030002,
`nvram-230400-switch2.sav`). To make a capture, use `COURIER_PAIR_WIRELOG=<prefix>` on
`tools/probe_imodem_pair.py`. We do not keep the raw logs (about 300 kB each).

```
COURIER_PAIR_WIRELOG=/tmp/gatewire .venv/bin/python tools/probe_imodem_pair.py --protocol x2 --settings S54=0S58=48 --nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav --instructions 250000000 --originate-send CALLER-X2 --answer-send ANSWER-X2 --output out
.venv/bin/python tools/analyze_bearer_handshake.py /tmp/gatewire.<pid>
```

The tool must have numpy. If a `V.21 ch1` event occurs at the same time as tone B, it is not a message.
It is the response of the FSK detector to the 1200 Hz tone. The V.8 octets are in raw form,
because the text of the recommendation is not in the repository.

`analysis-asymmetric.json` is the same analysis of the octets that the I-modem received
from, and sent to, the analog Courier in the 53333/x2 call (`probe_imodem_analog_pair.py`
writes `imodem-rx.g711` and `imodem-tx.g711`). It also has the host message
timeline of the I-modem up to 16 s. For INFO0 and marker frames, the analysis gives the search window in
which it found them. It does not give an exact start time.
