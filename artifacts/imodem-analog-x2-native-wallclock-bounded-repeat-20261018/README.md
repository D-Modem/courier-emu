# Verified 53333 analog x2 native wallclock repeat

`verification.json` passes all checks: 53333 downstream, 33333 upstream,
both direction-specific markers intact, native wallclock I/O active,
no per-frame Python callback, no active idle fill, no CPU/DSP errors,
no receive underruns or I-modem UART drops, and both sides answered before
the harness closes the socket. The call carries 74.36 seconds of active
media, including training and the idle tail after marker delivery.

The final analog `NO CARRIER` follows socket shutdown. `bridge_at_limit`
preserves the live carrier boundary before shutdown.

Recheck the saved evidence with:

```sh
.venv/bin/python artifacts/imodem-analog-x2-native-wallclock-bounded-repeat-20261018/verify.py
```

See [the audit and reproduction command](../../docs/imodem-analog-native-wallclock-20261018.md)
for the failed unbounded controls and the focused scheduling correction.
