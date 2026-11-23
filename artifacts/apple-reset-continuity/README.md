# Reset/hang-up continuity: fixed and tested

**Later dialing correction:** these attempts used the original 0.25 TX gain;
correct routing to the full extension was not yet established. The later
[unity-gain test](../apple-dtmf-gain/README.md) verifies full-number SIP routing
and answered CDRs for 6312/6313. The reset-continuity results below remain valid.

## Live hardware, explicit pause (no dialing)

`hardware-pause.json` / `.log` record:

1. Start duplex PCM on-hook at 10286 Hz.
2. Seize the powered line with **explicit DSP-reset silence** enabled.
3. Stop sending PCM for **350 ms**, well beyond the old ~100 ms cushion.
4. Resume one second of strict-mode PCM: no underrun or input overflow.
5. Release the hook using a **zero-sample control request**, then wait another
   200 ms without PCM. Readback and helper shutdown confirm on-hook.

The helper counts 6144 reset-silence samples and 6144 discarded reset RX
samples, separately from the zero active-gap/overflow counters. The test does
not dial any digits or alter receive/transmit gain registers.

## Real 6311 retry: clean final modem result

`6311/summary.json`, `6311/report.json` and `6311/hardware.log` capture the same
optimized 403 firmware and `ATX1S7=20DT6311` used by the earlier failed attempt.
Earlier captures were preserved in `artifacts/apple-dial-extensions/6311/`.

- Recorded codec TX independently decodes as **6311**.
- Original firmware returns **`NO CARRIER`**; worker exits **0**, no bridge error.
- **Zero active output gaps, zero input overflow**, including DSP teardown.
- 96,791 native worker polls; native lane I/O remains active.
- Seven immediate control updates; 1536 explicit reset-silence samples and
  1536 discarded reset RX samples, not counted as active-stream loss.
- Firmware requests on-hook; USB readback verifies hook clear, including an
  independent post-call `--status` snapshot.

`verification.json` summarizes these checks. This is a clean modem timeout,
**not** a successful connection or an identification of the remote extension's
state. The existing RX level/clipping problem remains separate.

## Subsequent 6312 and 6313 attempts

Both were tried separately on request after the reset fix. Each returned cleanly
with **`NO CARRIER`**, worker exit 0, zero active output gaps/input overflows, and
verified hook release. Codec TX independently decodes as **6312** and **6313**
respectively. See `extensions-6312-6313.json` and each numbered capture directory.
Neither attempt established a connection.

Reproduce only if another call to that extension is wanted:

```sh
.venv/bin/python tools/build_apple_line.py
.venv/bin/python artifacts/apple-dial-extensions/run_attempt.py 6311 \
  --output artifacts/NEW-DIRECTORY
```

## Implementation and safety

A zero-length protocol request carries hook and explicit-reset flags and is
acknowledged immediately, without needing a codec rate or ADC sample. The bridge
sends reset control **before** resetting/rebuilding a core and follows the
firmware hook relay edge immediately, even while the DSP is inactive.

The HAL continues independently: explicit reset produces silence and discards
ADC data that the reset codec cannot consume. A generation boundary discards
retired TX without letting the callback consume newly primed PCM during resume.
The first actual PCM batch returns atomically to strict streaming. An off-hook
reset has a five-second watchdog; unexpected starvation outside explicit reset
still fails closed. The FIFO was not enlarged, nor was active underrun checking
disabled.

`apple_line --selftest` checks callbacks against memory buffers without touching
USB, HAL or microphone permission: reset silence, generation flushing, strict
underrun detection, and the watchdog. Python tests additionally verify control
without PCM/rate, release when a resampler produces no output, servicing before
the inactive-DSP guard, native/non-native equivalence, and a full firmware dial
timeout returning `NO CARRIER`. The focused regression set passes **79 tests**.
