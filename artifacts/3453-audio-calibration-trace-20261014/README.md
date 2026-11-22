# Native serial controls and audio-buffer tracing (offline)

No attached hardware was accessed. The private B/C whole-flash capture is
executed unchanged, with modeled External straps, a quiet DAA and exchange.
No settings/RAM dump or credentials are included in these evidence files.

## Corrected native hook-pin wiring

The original runs below omitted `CodecBringUp`, exposing a bridge bug: only
that optional Python model updated the native Si3034 external hook input.
The DAA was seized, but the native line-side pin remained at its reset value.
`CourierDspBridge._service_exchange()` now updates the real modeled board
inputs independently of that optional model. No guest reply or RAM is forced.

`bc-blind-dial-hook-fixed.json` repeats the blind probe without `CodecBringUp`
after this correction. It ends in **NO CARRIER**, not NO DIAL TONE. Accepted
register-17 writes include `1160`, `1120`, then `1100`: the guest really pulses
MCAL one/zero and re-enables automatic calibration. The prior absence of that
pulse was not evidence that the unchanged guest cannot initiate calibration.
ADC offset estimation and calibration intervals are still not modeled.

Transmit peak remains zero, with no decoded digits or overlay downloads.
The exchange analyzed 301 DTMF blocks; this is not a working call. Six
resident readback cases verify connected/disconnected and on/off-hook inputs,
both directly and through the board path without a Python codec.
Post-fix aggregate: **105 tests passed** (`test_3453*`, `test_machine_map.py`,
`test_cli_link.py`, `test_native_machine.py`); compilation and diff checks passed.

## Transmit-path and tone-library follow-up

[Independent PCM / original-library diagnosis](../../docs/3453-audio-path-diagnosis.md)
now validates nonzero DSP DXR -> Si3034 DIN/DAC -> line-resampler output.
In a separate DSP test, the unchanged tone library produces a decoded **5**.
The historical supervisor trace `bc-output-processing.json` shows an
incomplete low-program library: tag-13 handler `0413` contains zero and
output callback `039A` remains idle. The cause is now identified and fixed:
a relocated delay hook was firing on B/C's timer ISR and corrupting CX.
`bc-library-transfer-before-fix.json` shows 101 groups instead of 1023;
`bc-hot-hook-fixed-dial.json` shows the complete guest transfer and **5551212**
decoded from real guest audio, peak 32331. It still ends in `NO CARRIER`.
No library is preinstalled into calls; see the linked diagnosis for details.
Post-delay-hook-fix aggregate: **108 tests passed** (3453/map/CLI/native).

## Historical findings (before hook-pin correction)

`bc-dial-serial-and-rings.json` runs `ATX3S7=3` then `ATD5551212` for 24 million
instructions with DSP-paced ticks. It ends in `NO DIAL TONE`, with 4550 ticks,
one line seizure/release, no digits, no overlays, and zero transmitted audio.

The new native trace records words **accepted as secondary codec controls**,
not guesses based on mailbox messages or DXR values. Register-17 writes are
`11A0` (CALD set, MCAL clear). There is no accepted MCAL one/zero pulse in the
recorded run. Trace capacity is 4096 and this run records 298 words. DSP cycles
restart at guest DSP resets; do not treat them as one monotonic timebase.
`event_pc` identifies the frame acceptance context, not the DXR writer.

The receive path is not entirely silent:

* Native codec receive peak reaches 5656.
* Before the reset at CPU instruction 15799899, the original DSP serial ISR
  writes 21920 words to its audio-ring range at PC `1185`; 21144 are nonzero,
  peak 5656. The code at `1184..1185` reads DRR and stores it into the ring.
* Input processing writes at `11C4` and `11DF` also become nonzero.
* Output-ring operations at `1194` and `111E` remain zero in that epoch.
  The resulting line audio also stays zero. This is not just a final
  post-hangup sample count: cumulative line-service peaks remain zero too.

This narrows the investigation to guest DSP processing / supervisor dial
state and their board handshakes. Missing electrical calibration is still a
model gap, but this trace does **not** establish it as the cause of silence.

## Controls and limitations

`bc-blind-dial.json` puts `ATX0D5551212` in the dial command itself. It still
ends in `NO DIAL TONE`, zero output and no digits. The native receive peak is
5656; serial DRR reads and frame interrupts occur. Why the guest behaves this
way remains unresolved; no reply code is changed to hide it.

`bc-real-delays-40m.json` disables accelerated waits. At 40 million CPU
instructions it has emitted no AT reply, delivered no CPU codec-control
messages, seized no line and delivered zero supervisor ticks. It is an
unfinished startup control, **not** a realistic-timing call result.

The native tracing feature is diagnostic-only: `trace_codec_controls()` uses
the existing register-trace buffer exclusively with selector -2. Disabled
tracing leaves codec behavior unchanged. The original resident's register-12
readback test now verifies that its accepted secondary word is `2CFF`.

Reproduce:

```
.venv/bin/python tools/probe_3453_calibration.py "$PRIVATE_BC_FLASH"
.venv/bin/python tools/probe_3453_calibration.py "$PRIVATE_BC_FLASH" --dial-command ATX0D5551212
.venv/bin/python tools/probe_3453_calibration.py "$PRIVATE_BC_FLASH" --real-delays --instructions 40000000
```

Validation: 56 focused tests passed (`test_3453_product_ids.py`,
`test_3453c*`, `test_native_machine.py`); compilation and diff checks passed.
No working call or full calibration fidelity is claimed.
