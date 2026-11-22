# Courier ROM DSP frame-service default, 31 October 2026

## Correction

`CourierMachine` now selects the existing DSP-XF INT0 source by default when
`with_dsp=True` and the image is a `CourierRom` (302/403). This also selects
the existing per-instance 64-instruction cooperative IRQ recognition profile.
CPU-only ROM runs and XMF supervisors retain their previous defaults.
`--frame-source periodic`, `--frame-hz`, explicit polling intervals and
`COURIER_ROM_XF_INT0=0` retain their override behavior.

The fixed legacy clock services approximately 2400 frame IRQs/s. The x2
resident generates approximately 3200 XF edges/s after selecting its 9600 Hz
codec cadence. The earlier measured discrepancy, finite six-lane exhaustion,
and valid-input/shortened-output captures are documented in
[the clock-phase investigation](imodem-x2-clock-phase-20261027.md) and
[the first-full-bank investigation](imodem-x2-first-full-bank-20261027.md).
This change promotes the already implemented source/latency profile; it does
not isolate source selection from recognition latency. It is not a new ASIC
wiring measurement or proof that every past rejection has the same cause.

No firmware, DSP arithmetic, oscillator ratio, bearer sample accounting,
receive-bank capacity, idle tokens or acceptance threshold was changed.
For the x2 rate handoff context, see Technical Specification Draft 0.33,
clause 22; the emulator's interrupt policy is based on the observations above,
not a claim that clause 22 specifies the board's wiring.

## Fresh tests against v90modem

A same-source snapshot A/B at `AT+MS=X2,0,0,56000`, Courier
`S39=8&M5&K0`, selected index 14 (actual downstream **54666 bit/s**, upstream
**31200 bit/s**):

- Explicit periodic source: incomplete downstream payload, exact return message.
- Explicit DSP-XF source: **5200/5200 downstream bytes and 28/28 upstream bytes**,
  both exact-after-CONNECT checks passing.

With the patched default and **no source/environment selector**:

| Rate cap | Selected downstream | Exact downstream / upstream | Result |
| ---: | ---: | ---: | --- |
| 56000, first call | 54666 | 5200 / 28 bytes | PASS |
| 48000 | 48000 | 5200 / 28 bytes | PASS |
| 56000, separate repeat | 54666 | 5200 / 28 bytes | PASS |
| 40000 control | 40000 | 5200 / 28 bytes | PASS |

The 40000 control requested the v90modem silence hook, but no retrain completion
was observed; count it as payload delivery only, **not a passed retrain test**.

An offline, original I-modem/Courier **14400 V.34** 20-second gate also passes:
46 downstream / 27 upstream complete records inside the window, maximum gaps
0.5 / 0.8 seconds, last receives at 19.7 / 19.3 seconds. Final drain is 47 / 29.

**61 focused tests pass**, including new 302/403 defaults, XMF/CPU-only scope,
overrides, XF reset/coalescing, native dispatch, periodic cadence, native
machine/port semantics, interrupt pins and DTE timing. No full-suite,
sustained arbitrary-binary, wall-clock/SIP or hardware qualification is claimed.

## Reproduction and provenance

Fresh x2 calls use `../v90modem/tools/probe_x2_host_courier.py` with
`X2_HOST_EMU_ROOT` pointing at this source tree and:

```
--courier-at 'S39=8&M5&K0' --engine-at 'AT+MS=X2,0,0,56000'
--fast --pty-source --host-pace-samples 16 --instructions 300000000
--host-at 220000 --host-message-file PAYLOAD --output UNIQUE_OUTPUT
```

PAYLOAD has 100 ASCII lines of
`X2-SPEED-{i:04d}-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n`, `i=0..99`.
All original exact checks remain active. Output basenames must differ between
concurrent calls because the engine's PTY link uses that basename.

Provenance is `../v90modem/artifacts/x2-speed-20261031/irq` for the A/B and
`../v90modem/artifacts/x2-speed-20261031/fixed` for default tests and V.34.
The old clean `f1ccd92` export does **not** contain this default correction or
the earlier XF-source support; tests explicitly pinned there still use legacy
servicing. This work was made on top of the existing local emulator changes.
