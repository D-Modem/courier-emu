# Apple physical line → SIP → Courier-emu I-modem

Two explicit calls were made to local PBX extension **2903**, using the Apple
USB line backend and the unmodified 403 firmware. No gateway/PBX configuration
was changed. The receiver runs Courier-emu's I-modem firmware, not v90modem.

## Latest: working 180-byte exchange both ways

The [repaired control](bell103-fair-clock-180-buffer200/README.md) now reports
both firmware CONNECTs and **exact 180-byte payloads in both directions**.
Independent FSK decoding confirms each full payload at all five captured audio
boundaries. The receiver's complete **48000-sample** payload interval is
byte-identical to SIP RX. Fixes remove redundant live terminal throttling and
bound DSP catch-up by actual CPU progress; this configuration explicitly uses
**200 ms SIP buffering**. Apple reports zero active sample loss and verified
hook release. A second packet-captured trial also passes both 180-byte payloads
and all audio checks. Other retries still show occasional return-path corruption
or an Apple host output underrun: the systematic bit-pump timing fault is fixed,
but end-to-end reliability is **not yet established**. **143 regressions pass.**
Sustained BER and high-speed training remain separate tests.

```sh
.venv/bin/python artifacts/apple-courier-sip/run.py --protocol bell103 \
  --payload-test --payload-size 180 --buffer-ms 200 --output artifacts/NEW-CAPTURE
```

The sections below retain the earlier failures rather than rewriting history.

## Earlier follow-up: real Bell 103 CONNECT, but corrupt payload

The default/high-speed call below still fails. A **fixed 300-bps Bell 103**
control now returns firmware `CONNECT` on **both ends**, twice:
`bell103-control/` and `bell103-payload-ready/`. This is native modem carrier
qualification, not merely SIP answering. Both use the software-pair preset
`B1&N1S54=192S56=192&M0&B0` (caller also `S27=1`), without simulated carrier.

The payload run sends `APPLE-TO-SIP-123` after caller CONNECT and
`SIP-TO-APPLE-456` after receiver CONNECT. **Neither marker is recovered**;
both terminals receive garbled bytes. See
`bell103-payload-ready/payload-verification.json`.
A subsequent [boundary audit](bell103-payload-ready/boundary-findings.md)
independently recovers the complete caller marker in Apple hardware TX **and
SIP RX**, then identifies **30 inserted mu-law silence samples** inside that
message in the I-modem's DSP-facing stream. The reverse expected marker is
already undecodable at I-modem SIP TX. This narrows the investigation to the
SIP-backed endpoint's playout/DSP/data handling, without exonerating all other
boundaries or claiming the UART corruption is fully explained. Carrier acquisition works
at 300 bps, but successful data communication is **not established**.
Both calls report zero active Apple output gaps/input overflows and verified
physical hook release. This does not exclude distortion, receiver timing,
UART/framing faults, or SIP playout problems.

Listen to the actual connected call (TX left / RX right):

```sh
afplay artifacts/apple-courier-sip/bell103-payload-ready/caller/2903/apple-stereo.wav
```

A separate `bell103-payload/` attempt never reached the receiver. Its preflight
found a registered but **Unavail** PBX contact; the original check mistakenly
accepted registration alone. The launcher now waits for an **Avail** contact
before seizing the line, and the subsequent payload call reaches CONNECT.
No PBX configuration or qualification policy was changed.

To repeat the explicit payload control in a fresh directory:

```sh
.venv/bin/python artifacts/apple-courier-sip/run.py --protocol bell103 \
  --payload-test --output artifacts/NEW-BELL103-CAPTURE
```

The launcher now records payload verdicts from actual firmware serial output
(not local terminal echo) and exits 2 if either marker fails. The first saved
payload capture predates that exit-status check; consult its verification JSON,
not its process exit code. Current focused regressions: **41 passed**.

## Answered retry / listen

The useful capture is **`profile-retry/`**:

```sh
# Left = actual helper-bound TX; right = raw helper-returned RX.
afplay artifacts/apple-courier-sip/profile-retry/caller/2903/apple-stereo.wav

# Each direction at the remote SIP endpoint, separately:
afplay artifacts/apple-courier-sip/profile-retry/receiver/audio/caller-to-imodem.wav
afplay artifacts/apple-courier-sip/profile-retry/receiver/audio/imodem-to-caller.wav
```

The stereo recording preserves the 10286-Hz hardware grid and levels, without
AGC, normalization or DC blocking. It includes dial tone, digits, ringback and
two training attempts. Channels are paired at helper exchanges, not calibrated
to physical DAC/ADC latency; reset gaps are omitted. The independent SIP WAVs
have different time origins; do not align their starts and infer a line delay.
The existing `analysis-hardware/{tx,rx}-8000.wav` files provide separate
resampled mono Apple channels.

### Verified

- Asterisk routes the complete **2903**, from the Apple line's SIP identity
  **6004**, to the registered I-modem test account.
- Receiver transcript: configuration `OK`, `RING`, then `NO CARRIER`.
- SIP: REGISTER/401/200, INVITE, 100/180/200, ACK and caller BYE.
- RTP: **130080 received / 137760 sent octets** at the I-modem SIP endpoint.
- Apple: **29.978 seconds off-hook PCM**, zero active output gaps, zero input
  overflows, no live filter misses, and independently verified on-hook afterward.
- Actual clock transitions include 7200 → 8641.234462 → 9600 Hz, and a later
  10267.379679-Hz transition, without a transport error.
- Hardware RX contains answer-tone bands at approximately **14.8–17.2** and
  **22.8–25.6 seconds** in its off-hook capture clock; caller TX responds.
- The very high RX levels/near-rail counts are concentrated in dial tone and
  ringback. Complete 15–28-second training windows have zero near-rail samples
  in the resampled analysis; this is not an absolute analog calibration.

**Neither modem reaches CONNECT.** This establishes an audible, bidirectional
physical/SIP path, not successful training or error-free media delivery.
The I-modem reports 40434 silence-filled bearer samples, including a preanswer
period (31860 preanswer output samples). These counters have different semantics;
subtracting them is not a packet-loss measurement. The remaining receive pacing
and training behavior need investigation before calling this path lossless.
See `receiver/report.log`, `caller/2903/summary.json`, `caller-timeline.txt`, and
`pbx-cdr.log` for raw evidence.

## First attempt (root directory)

Digits reached Asterisk correctly, but a blank I-modem profile rejected Q.931
SETUP with cause **88, incompatible destination** before answering. All receiver
G.711 files are empty. This was not an Apple digit/transport failure.

The retry copied the established inbound-test NVRAM into the capture directory
and mapped the SIP extension to its directory number with
`--bri-call-to 7349195`. The original NVRAM fixture was not modified.

## Reproduce / export

`run.py` registers test account 2903, configures autoanswer, verifies its PBX
contact, makes one bounded dial attempt, and detaches the receiver afterward.
It obtains that account's password over SSH into child environment only, without
printing/persisting it. It needs the connected powered analog line and existing
SSH access to the lab PBX. Use a **new** output directory; no automatic redial:

```sh
.venv/bin/python artifacts/apple-courier-sip/run.py --output artifacts/NEW-APPLE-SIP
.venv/bin/python tools/render_apple_audio.py artifacts/NEW-APPLE-SIP/caller/2903
.venv/bin/python -m tools.analyze_bri_sip_audio \
  --from-caller artifacts/NEW-APPLE-SIP/receiver/apple-to-imodem.g711 \
  --from-imodem artifacts/NEW-APPLE-SIP/receiver/imodem-to-apple.g711 \
  --output artifacts/NEW-APPLE-SIP/receiver/audio
```

The existing one-shot Apple dial runner now accepts explicit numeric extensions
and refuses to overwrite a capture directory. `tools/render_apple_audio.py`
exports raw stereo offline with no NumPy dependency; malformed/unpairable PCM
fails rather than silently shifting channels. Focused regressions:
**46 passed, 1 skipped** (optional NumPy analysis module in the main venv).
The sibling venv supplies NumPy for the captured timeline analysis, but does not
have pytest installed.
