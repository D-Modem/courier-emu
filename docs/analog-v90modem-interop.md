# Analog Courier interop with v90modem

**Follow-up:** [the DIL handoff correction](analog-v90-dil-handoff.md) now
establishes 52000/V90/LAPM and exact 5,000-byte duplex transfer. The V.90
failures below describe the earlier one-cycle DIL profile; the analog V.90
probe now defaults to repeat-until-peer-completion. The later
[CTS/DTE correction](analog-v90-cts-continuity.md) passes exact 38,400-byte
duplex transfers across two completed retrains, with a matched negative
control proving the prior byte loss. Retrain gaps and physical-hardware
qualification remain open.

## Scope

The original analog Courier 403 ROM was tested against the sibling
`../v90modem/v90_engine_peer` executable, using fresh closed-loop samples and
its real PTY data interface. These are **x2/LAPM calls**, not a claim of V.90
modulation, physical hardware qualification, or sustained arbitrary-binary
throughput. Runs used accelerated (`--fast`) media, not wall-clock pacing.
Existing firmware, DSP, codec calibration, frame-source defaults, and exact
payload checks were preserved.

## Improvements

`tools/probe_v90modem_closed_loop.py` now:

* Uses `LINE_FRAME_SAMPLES` and `LINE_FRAME_INSTRUCTIONS` for the analog
  endpoint. Previously its silence frames always contained 160 samples, and
  timestamps advanced by a hard-coded 400,000 instructions, regardless of
  `COURIER_LINE_FRAME_MS` or the actual line instruction grid. The default
  remains 20 ms, but explicit shorter/longer frames are now respected.
* Reads engine replies directly from the pipe descriptor with a single
  per-frame deadline. `select()` followed by buffered `read(n)` could hang
  indefinitely after receiving only part of a frame. Fragmented replies are
  accepted; timeout/EOF diagnostics include received and expected lengths.
* Closes the engine stdout pipe at shutdown and explicitly rejects oversized
  frames rather than relying on an assertion that optimized Python removes.

These are analog interop transport/harness corrections, not a new DSP or PHY
repair. The existing 20-ms baseline already passed short exact transfers.

## Fresh results

Artifacts are relative to the repository root:

| Directory under `artifacts/` | Frame | Courier CONNECT report | Exact downstream | Exact upstream |
| --- | ---: | --- | ---: | ---: |
| `analog-v90modem-baseline-20261103` | 20 ms | `53333/ARQ/x2/LAPM` | 20 bytes | 28 bytes |
| `analog-v90modem-fixed20-20261103` | 20 ms | `53333/ARQ/x2/LAPM` | 5,000 bytes | 28 bytes |
| `analog-v90modem-fixed5-20261103` | 5 ms | `52000/ARQ/x2/LAPM` | 5,000 bytes | 28 bytes |

All nine checks in each `call.json` pass, including marker 4d, both CONNECT
checks, complete source queuing, clean engine exit, and **exact** payloads
following CONNECT in both directions (not just substring matches).
`courier-dte.bin` is the complete untouched serial stream; validation masks
its 7E1 parity bit. `engine-dte.bin`, the raw G.711 streams, WAVs, engine hash,
command line, environment and logs are retained alongside it.

The 5,000-byte payload consists of 100 ASCII lines:
`ANALOG-{i:04d}-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n`, for `i=0..99`.
The return payload is `COURIER-X2-HOST-0123456789\r\n`.

## Reproduction

From this checkout, generate the payload, then run (use a fresh output path):

```sh
.venv/bin/python -c "from pathlib import Path; Path('tmp/analog-interop-payload.txt').write_bytes(b''.join(f'ANALOG-{i:04d}-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ\\r\\n'.encode() for i in range(100)))"

X2_HOST_EMU_ROOT="$PWD" COURIER_LINE_FRAME_MS=5 \
  .venv/bin/python ../v90modem/tools/probe_x2_host_courier.py \
  --courier-at 'S39=8&M5&K0' --engine-at 'AT+MS=X2,0,0,56000' \
  --fast --pty-source --host-pace-samples 16 \
  --instructions 300000000 --host-at 220000 \
  --host-message-file tmp/analog-interop-payload.txt \
  --output artifacts/analog-v90modem-new-run
```

Use `COURIER_LINE_FRAME_MS=20` for the other framing control. No sibling source
changes are needed. Explicit S39=8 replaces the captured profile's invalid
transmit-level setting; &M5 requires error correction and &K0 disables
compression.

## Regression tests

`tests/test_v90modem_closed_loop.py` adds fragmented-reply, partial-timeout,
partial-EOF, and isolated 5/20/100-ms frame-grid tests. Its fake subprocesses
are transport unit tests only, not interop evidence.

The initial focused selection passed **39 tests** (now **43** after the
modulation and DIL-profile regressions):

```sh
.venv/bin/python -m pytest -q \
  tests/test_v90modem_closed_loop.py tests/test_line_presend.py \
  tests/test_g711_peer_frames.py tests/test_g711_peer_pacing.py \
  tests/test_courier_rom_frame_default.py tests/test_serial_output_capture.py
```

A separate earlier audio-rate selection had 11 passes and the already
 documented `test_audio_line_frames_are_paced_at_codec_rate` fixture failure
(the `__new__` fixture has no `line` attribute). It was not changed here.
No full-suite pass is claimed.

## Explicit V.90 modulation controls

The follow-up adds `--modulation v90` to the closed-loop analog probe and the
sibling `../v90modem/tools/probe_x2_host_courier.py` payload driver. The engine
now starts with `ME_MODE=v90`, not x2. Courier settings explicitly select
`S39=8S54=0S58=1` (x2 disabled, V.90 allowed), automatic rates, and `&M5&K0`
for these controls. The sibling validator checks `/V90/` in the parity-masked
Courier CONNECT report, engine V.90 selection, and both exact payloads; x2
marker acceptance is required only in x2 mode. V.34 fallback cannot pass.

**V.90 did not connect in any of three valid controls.** All ran to the
180-million-instruction bound with emulator and engine exit status 0:

| Artifact suffix (`analog-v90modem-v90-…-20261103`) | Frame | Pacing | Result |
| --- | ---: | --- | --- |
| `clean20` | 20 ms | accelerated | V.90 training, no CONNECT, zero DTE payload |
| `clean5` | 5 ms | accelerated | V.90 training, no CONNECT, zero DTE payload |
| `paced20` | 20 ms | wall-clock paced | V.90 training, no CONNECT, zero DTE payload |

All three logs independently show:

1. V.8 selected **V90**, with the Courier advertising analogue PCM capability.
2. CRC-valid **INFO1a**, U_INFO=78, downstream baud code 6 (PCM), upstream
   code 4 (3200 baud).
3. CRC-valid **Ja DIL descriptor**, N=197, LSP=66, LTP=66.
4. Digital **Sd → TRN1d → Jd → J'd → DIL → Ri** transmission.
5. No CONNECT and no queued/delivered PTY payload.

The engine labels its transition after one full DIL cycle as an **interop
fallback into Phase 4**. Reaching Ri is therefore not evidence that the
analogue endpoint completed DIL or accepted Phase 4. Both 20-ms runs later
hit the engine's no-B1 deadline and retrain; the accelerated 5-ms run ends at
its instruction bound without that wall-time deadline firing. These traces
localize the remaining investigation beyond INFO1a/Ja acquisition, but do not
yet distinguish a digital transmit defect from analogue receive/emulation
failure. Changing frame size or adding wall-clock pacing did not produce a
connection.

Reproduce a valid V.90 control (omit `--fast` for the paced control):

```sh
X2_HOST_EMU_ROOT="$PWD" COURIER_LINE_FRAME_MS=20 \
  .venv/bin/python ../v90modem/tools/probe_x2_host_courier.py \
  --modulation v90 --courier-at '&M5&K0' \
  --fast --pty-source --host-pace-samples 16 \
  --instructions 180000000 --host-at 220000 \
  --output artifacts/analog-v90modem-v90-new-run
```

The existing payload labels contain `X2`; these are literal ASCII test data,
not a modulation assertion. The negotiated-mode checks above decide that.

To reproduce these historical one-cycle failures with the current probe,
explicitly set `ME_V90_DIL_AUTOTERMINATE_CYCLES=1`; without it the corrected
probe uses repeat-until-peer-completion instead.

Three preliminary attempts (`v90-initial`, `v90-native`, `v90-auto`) are **not
valid V.90 acceptance controls**: the first command was rejected, and the
other two appended a second `--at` rather than replacing the first dial
command. `--at` is repeatable, so those calls still dialled with the original
V.90-disabled settings. They selected V.34 and were terminated before their
summary finished. They motivated the explicit modulation option and are not
counted in the table.

After these changes, **41 focused regressions pass**, including power-on
engine mode selection. A fresh x2 compatibility smoke call
(`artifacts/analog-v90modem-mode-regression-20261103`) still passes all exact
payload checks. None of the emulator x2 passes establishes interoperability
with a physical Courier; the user's physical x2 failure and partial V.90
success remain distinct evidence that these controls do not supersede.
