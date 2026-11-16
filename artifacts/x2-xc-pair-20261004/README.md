# Symmetric x2 regression after XC condition timing correction

The two Ie030002 endpoints report CONNECT 64000/ARQ/x2/LAPM. They deliver
CALLER-X2-XC / ANSWER-X2-XC in the opposite direction. verification.json
examines 12033 consecutive GPC state transitions and two zero-history resets
at each endpoint. The source width is eight, with mask FF and octet reversal.

To reproduce the result, you must have local socket access:

```
.venv/bin/python tools/probe_imodem_pair.py --protocol x2 --settings S54=0S58=48 --nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav --trace-negotiation --trace-digital-path --instructions 180000000 --originate-send CALLER-X2-XC --answer-send ANSWER-X2-XC --check-connect --check-x2 --output artifacts/x2-xc-pair-20261004
.venv/bin/python tools/verify_x2_scrambler_trace.py artifacts/x2-xc-pair-20261004
```

After a successful transfer, the worker closes its socket. During the
shutdown, this can cause a broken-pipe message from the peer. The saved call
results and the verification show the successful carrier and the payload in
the two directions.
