# x2 upstream E continuation

5 October 2026. Refer to `../../docs/x2-courier-mp-fields.md`.

- `receiver.asm`, `transmitter.asm`: the original E paths of Ie030002/Courier 403.
  AE83 is script data, a triplet AF2E/0/5. The generic listing shows its
  words as instructions. In this call, AF2E/AF38 supplies four ones for each symbol.
- `verification.json`: nine original A881/AABF execution contexts, after
  accepted MP. Twenty ones without interruption go into A891. Shorter
  prefixes or prefixes with an interruption do not. An interruption returns to the record receiver.
- `courier-upstream.g711`, `capture.json`: the kept PCMU recording of the peer,
  the provenance/hash, and the E detector timestamps at three block sizes.
- `session-tests.log`: mapper checks with firmware vectors, MP/E regressions, and
  E detection on the full capture at all three block sizes.
- `default-replay.log`: receive E and downstream PAYLOAD. The state stays at TRAINING.
- `acquisition-replay.log`: the existing V.34 B1 acquisition probe, which is opt-in.
  It does not acquire and it never releases CONNECT.

To do the work again:

```
.venv/bin/python tools/verify_x2_upstream_e.py
../v90modem/x2_session_test artifacts/x2-upstream-e-20261005/courier-upstream.g711
ME_MODE=x2 ME_X2_UPSTREAM_ACQUIRE=1 ../v90modem/v90_engine_replay artifacts/x2-upstream-e-20261005/courier-upstream.g711 ulaw --fast --from 0
```

The standalone E sample is 100074. This value includes the latency of the detector filter.
The time of the engine MP receiver is relative to its TRAIN_C initialization. Do not read it
as the absolute bearer clock. Acquisition is diagnostic and it is off
by default. As the next step, compare the Courier AF99/AFC9/B006 initialization and mapping
with the B1 reference of the receiver. We do not claim a carrier lock or a payload lock.

The failed acquisition above is the initial minimum-shaping probe.
`../x2-upstream-b1-20261005` replaces it: the expanded/64-state B1 now acquires
at 99.9% fit by default. The upstream payload/CONNECT are not yet verified.
