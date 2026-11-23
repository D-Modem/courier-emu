# Audio-path audit: fixed ADC source clock and a missing analogue loop

## Reconnected-line retry

After the user restored the line, `reconnected/6313` passes the seizure guard
(`status=4a`, nonzero loop current), exchanges V.8 menus and independently
CRC-valid INFO0 both ways, and crosses 7200 → 8641.234462 → 9600 Hz. The ADC
empty counter remains **143 before and after retune**, instead of the previous
143 → 188 increase. There are **zero active output gaps/input overflows** over
29.99 seconds off-hook PCM. The worker exits 0 with **NO CARRIER**, and hook
release is verified. Thus the retune starvation fix now has live evidence, but
training still fails. This short retry does not rule out the earlier separate
late underrun after 44.9 seconds. See `reconnected/audio-timeline.txt`, frame
captures and read-only DSP snapshots.

## Earlier blocker: raw input is not modem audio

The final controlled A/B attempts have **zero off-hook loop current**:
`hook=09 status=40 aux=02 sense=0`. The earlier answered calls had `status=49`
(nonzero current code). A valid isolation-link bit (`40`) alone is insufficient.

Both A/B captures contain **308,000 consecutive hardware RX samples equal to
-32768**, across all 29.94 seconds off-hook. The 8-Hz DC blocker removes that
constant and makes the downstream recording look quiet; this is not evidence
of a healthy silent line. No call INVITE or RTP stream appears in the PBX capture.

The two modes send **byte-identical post-resampler/post-gain hardware TX**:
SHA-256 `0543276929ccf502fd66e9ef6a238fd1e47b4ce772e40c0aebabbfedcf5c1d6f`.
The waveform contains the firmware's four DTMF digits at the same timing and
levels as before. Switching back to the original RX path does not restore
routing. See `ab/verification.json`, each `hardware.log`, wire PCM captures,
`ab/sip.log`, and `ab/rtp-summary.txt`.

Short **on-hook, zero-output** probes at 10286 → 7200 → 10286 Hz find strong
50-Hz interference/clipping rather than a stable healthy line. Rate switching
does not clear it. No USB reset or gateway configuration changes were made.
The cause of the missing loop (lead, FXS power/port, or another physical fault)
still requires checking. SIP registration of 6004 remains available; that does
not establish analogue line power or continuity.

`native/apple_line.m` now checks for a valid, nonzero, non-overload current code
when seizing, with 250 ms for settling. It refuses a missing loop **before
dialing**, and cleanup releases the hook. The silent seizure probe in
`rail-check/seizure-guard.*` reproduces this guard in ~0.74 s, without dialing;
`after-guard-status.json` independently confirms on-hook afterward. Callback
self-tests cover the status classifier. No sample-loss checks or buffers were
relaxed.

## Separate software flaw: preconverted RX can change speed at retune

The old hardware bridge converted each returned input block to the current
codec rate, then queued it with `queue_codec_rx`. If the firmware changed its
ADC clock before consuming those samples, the queue retained the old sample
spacing but was consumed at the new rate. A 144-sample service target could
also expand to 192 samples in flight, starving the old-rate receive reserve.
The preceding live diagnostic recorded **45 additional empty ADC frames**
around the 7200 → transient 8641.234462 → 9600 Hz transition.

The corrected physical path:

- keeps RX queued on the fixed hardware clock (normally 10286 Hz);
- reconstructs input at each actual native ADC edge, retaining source time
  through arbitrary codec clock changes;
- generalizes the existing native clocked-input converter's source rate,
  **without an 8-kHz hop or double resampling**;
- inserts **zero extra receive-cushion samples**;
- prewarms immutable native FIR tables before hardware startup and fails closed
  on unknown live ratios;
- yields native polling at retunes and services the boundary instead of
  extending the outstanding batch.

The old socket path retains its 8-kHz source and original 32-sample cushion.
DSP firmware, negotiation decisions and real modem result codes are unmodified.

## Offline verification

`adc-clock-benchmark.json` / `tools/benchmark_apple_adc.py` demonstrate the
clock-label hazard: a deliberately queued 2400-Hz old-rate waveform appears at
**3200 Hz** after a 7200 → 9600 Hz ADC change. Keeping the source on the hardware
clock preserves **2400 Hz**, with zero empty ADC frames. That control uses an
intentionally long queued waveform; it is **not** a claim about live FIFO size
or proof of the exact cause of the earlier training failure.

`tests/test_apple_adc_grid.py` independently checks 1200/2400/3000-Hz waveforms
through 7200 → one transient frame → 9600 Hz. All achieve **>60 dB absolute
waveform agreement**, including transition samples, with no gain/phase fitting,
no empty ADC frames and bounded occupancy. Other tests cover unknown-ratio
rejection, source-grid immutability, hardware RX counts, retune service bounds,
and full-rail input becoming quiet after DC blocking.

The full regression selection passes **111 tests** with the optional NumPy
analysis dependency available. Native polling on/off remains equivalent in the
lossless fake-hardware test.

## Earlier live limitations (superseded by the reconnected retry above)

`call/6313` (S7=40), `retry/6313` (S7=20), and the two `ab/` attempts return
NO CARRIER with no active transport loss and verified hook release. They do
**not** validate the V.34 retune fix: none reaches V.34 in the now-faulty analogue
line state. The original late training underrun also remains unverified after
this change. The earlier answered calls had nonzero loop current; this later
physical fault does not retrospectively explain their negotiation failures.
Restore a healthy loop before another negotiation comparison.

`trace_worker.py` now records the actual helper-bound TX and raw helper-returned
RX in `codec-hardware-{tx,rx}.s16`, with `codec-hardware-frames.jsonl`. Codec-side
RX records carry their own `rx_rate`, since the new receiver stays on the
hardware grid. Both traces exclude invented carrier/audio. A diagnostic
`--rx-grid codec` restores the old receive architecture for A/B only.

```sh
# Offline: opens no hardware
../v90modem/.venv/bin/python tools/benchmark_apple_adc.py

# Analyse actual wire PCM after a deliberately requested call
../v90modem/.venv/bin/python tools/analyze_apple_call.py \
  artifacts/NEW-CAPTURE/6313 --boundary hardware
```
