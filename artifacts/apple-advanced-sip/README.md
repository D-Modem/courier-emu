# Advanced Apple physical-line / SIP modem controls

## Best verified result: 9600 bps with LAPM

The Apple-backed 403 caller reports **`CONNECT 9600/ARQ/V32/LAPM`** and the
Courier-emu I-modem SIP receiver reports **`CONNECT 9600/ARQ`**.
Both recover the other endpoint's **complete 180-byte ASCII message exactly**.
This is a short, genuine native modem data exchange with negotiated error
correction, **32 times the Bell 103 link rate**; it is not a measured throughput
benchmark or sustained reliability result.

Evidence: `v32-9600-lapm/payload-verification.json`, receiver terminal/report
logs, caller raw serial hex and independently verified physical hook release.
Both firmware images and modulation decisions remain unmodified. No synthetic
carrier/result or decoded receive payload is injected. Compression is disabled.

Listen at low volume (actual helper-bound TX left / raw hardware RX right):

```sh
afplay artifacts/apple-advanced-sip/v32-9600-lapm/caller/2903/apple-stereo.wav
```

## Five explicit attempts

All tests use SIP extension 2903, a 200-ms media reserve, distinct deterministic
180-byte messages and fresh capture directories. `NONE` is normal mode without
error correction. The payload columns mean **the entire expected message**, not
whether some recognizable bytes arrived.

| Control | Caller result | Receiver result | Apple → SIP exact | SIP → Apple exact |
| --- | --- | --- | --- | --- |
| `v22-1200` | CONNECT 1200/NONE | CONNECT 1200 | No | No |
| `v22bis-2400` | CONNECT 2400/NONE | CONNECT 2400 | No | **Yes** |
| `v32-9600` | CONNECT 9600/V32/NONE | CONNECT 9600 | No | **Yes** |
| `v34-auto` | CONNECT 19200/V32/NONE | CONNECT 19200 | No | No |
| `v32-9600-lapm` | **CONNECT 9600/ARQ/V32/LAPM** | **CONNECT 9600/ARQ** | **Yes** | **Yes** |

**The automatic 19200 result is not claimed as V.34.** The request enabled V.34
but left fallback available, and the actual caller result explicitly says V32.
It is a V.32-family/terbo indication, not proof of V.34 or usable 19200-bps data.
The five results are collected in `summary.json`.

Every call reports zero active Apple output gaps/input overflows and final
on-hook readback. Complete codec-to-helper TX replay is sample-exact for all
five captures (`tx-replay.json`). That replay is not an independent QAM receiver:
advanced-mode payload verdicts come from the actual firmware UARTs, with local
echo disabled, not from the Bell 103 audio decoder.

## Audio/network limitations remain

- V.22 at 1200 records 1393 active silence-fill samples and a 316-ms maximum
  polled RTP arrival gap. The 200-ms reserve cannot absorb that entire gap.
- V.22bis records an incoming RTP sequence/timestamp gap of 480 samples, although
  the FIFO does not run empty. A nonempty FIFO does not prove a continuous RTP
  sample timeline: timestamp-aware playout remains required.
- The raw 9600 control has no recorded incoming RTP discontinuity or active
  silence fill, yet some caller-to-I-modem characters corrupt. Network loss
  alone is not a complete explanation for all earlier failures.
- The successful LAPM call still records a 160-sample RTP timestamp gap. This
  does not establish when ARQ retransmissions occurred or prove that a specific
  missing packet was recovered during payload transfer. It does establish both
  negotiated LAPM and correct delivery of these complete messages. This preset
  changes both `&M0` to `&M5` **and** `&B0` to `&B1`; the trial does not isolate
  error correction from the fixed-DTE policy as the sole reason for improvement.

No gateway/PBX configuration, line gain, modem firmware or forced-online
assistance was changed. Each protocol is an ordinary volatile AT preset.
The established NVRAM is copied per receiver run; the original is not modified.

## Reproduce the usable control

One bounded real call, no automatic retry; use a new directory:

```sh
.venv/bin/python artifacts/apple-courier-sip/run.py \
  --protocol v32-lapm --payload-test --payload-size 180 \
  --carrier-wait 45 --frames 4500 --instructions 550000000 --timeout 115 \
  --output artifacts/NEW-APPLE-V32-LAPM
```

Both firmwares receive:

```text
S54=192S56=192S58=33B0&M5&B1&U6&N6&K0
```

This disables V.8, V.34/V.FC and PCM, fixes both limits at 9600, requires error
correction (`&M5`), fixes the DTE rate (`&B1`), and disables compression. The
caller also uses `S27=1`, the receiver autoanswers, and payloads are sent only
after real firmware CONNECT. `&M5` requires error correction; the **observed
result string**, rather than the preset's name, establishes LAPM specifically.

The launcher now accepts explicit `v22`, `v22bis`, `v32`, `v34` and `v32-lapm`
profiles through `tools/apple_sip_profiles.py`, records requested settings and
actual CONNECT lines, and writes failure verdicts even when a caller exits
without receiver CONNECT. Existing captures are never overwritten.

The final focused suite passes **177 tests**, including six new profile controls.
Independent final USB status confirms on-hook after all five attempts.
