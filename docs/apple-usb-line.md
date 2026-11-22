# Apple USB Modem line backend (experimental)

The A1082 (`05ac:1401`) can now provide **hardware PCM, hook control and ring
readback** to Courier-emu. It is an **FXO**: connect to a powered FXS/PBX line,
not directly to another unpowered modem. No v90modem datapump is used.

**Latest seizure fix:** normal hook transitions now use the original Windows
stack's interface-0 firmware hook command, not raw DAA register writes with
host-timed OPE re-arming. Two captured V.32/9600 LAPM calls deliver complete
180-byte payloads exactly both ways; zero active USB losses, zero RTP playout
missing/late samples, and byte-identical RTP at local/PBX capture points.
Protection remains enabled and final on-hook is independently verified. See
[firmware hook fix](apple-firmware-hook-fix.md). These short calls do not certify
sustained throughput or resolve the historical intermittent network loss.

**Sustained follow-up:** the new [exact binary/ASCII traffic validator](apple-sustained-traffic.md)
reproduces long asymmetric stalls in 20-second controls. Actual `ATI6` diagnostics
show substantial LAPM block errors/retransmissions and a retrain, while observed
local/PBX/AudioCodes forwarding remains byte-identical. This is an unresolved
link-reliability failure, not a passing binary soak.

**Status:** hardware PCM, reset/hang-up continuity and real digit collection
are verified. The old quarter-scale output was too quiet: a 6312 attempt reached
Asterisk as `6` and was rejected. With the corrected **unity-gain default**,
Asterisk routes the full **6312** and **6313** and records both **ANSWERED**.
No PBX/gateway configuration or digit timing changed. This is **not** a trained
modem connection. Prewarming resampler filters removes the identified cold
training-retune stall: a fresh answered 6313 call exits cleanly with `NO CARRIER`
and zero active sample loss. Offline decoding verifies V.8 menus and CRC-valid
V.34 INFO0 in both directions, but negotiation then repeats without CONNECT.
A longer diagnostic call encounters a separate late underrun after 44.9 seconds
off-hook; see [negotiation evidence](../artifacts/apple-negotiation-6313/README.md).
A subsequent [audio-path audit](../artifacts/apple-adc-grid/README.md) fixes
preconverted RX being consumed at a changed ADC clock. After restoring a missing
analogue loop, a live 6313 retry crosses the training retune with **no new empty
ADC frames**, zero active transport loss, valid V.8/INFO0, and clean NO CARRIER.
V.34 training remains unresolved. A new seizure guard rejects missing loop current
before dialing, rather than accepting full-rail input as DC-blocked silence.
A subsequent [call to a SIP-backed Courier-emu I-modem](../artifacts/apple-courier-sip/README.md)
answers and records modem audio in both directions. Its default negotiation
returned NO CARRIER. The [repaired 300-bps Bell 103 control](../artifacts/apple-courier-sip/bell103-fair-clock-180-buffer200/README.md)
now gets firmware **CONNECT and exact 180-byte payload delivery both ways**.
Independent audio decoding recovers both complete messages at all captured
boundaries. Fixes remove redundant terminal throttling and interleave native
DSP catch-up with actual CPU progress; the verified setup explicitly uses
`--bri-sip-buffer-ms 200`. The entire 48000-sample receive payload interval
matches from SIP RX to the DSP-facing capture, with zero active Apple transport
loss and verified hang-up. Two calls pass the full payload and independent
audio checks; other retries still expose occasional return-path corruption or
host output underruns, so reliable end-to-end operation remains unresolved.
This is a short working Bell 103 exchange, not a sustained BER or high-speed
training result. Earlier corrupt captures retain their original failure verdicts.
[Advanced controls](../artifacts/apple-advanced-sip/README.md) now reach
**CONNECT 9600/ARQ/V32/LAPM** on the Apple caller and **CONNECT 9600/ARQ** on the
SIP I-modem, with exact 180-byte messages both ways. Normal V.22bis/2400 and
V.32/9600 also train and deliver the full return message, but the forward payloads
corrupt. An automatic attempt reports 19200/**V32**, not confirmed V.34. The
9600/LAPM result is a short usable error-corrected exchange, not sustained BER or
throughput validation; the underlying RTP/audio faults are not declared fixed.
The separate B/C firmware path still has its existing fast-path exclusions.

## Build / inspect

macOS, microphone permission for the launching terminal, clang, pkg-config and
libusb are required. The build reuses the sibling v90modem checkout's
`tools/apple_usb_modem_audio.m` utilities and `apple_modem_line.h`. It links
CoreAudio/AudioToolbox/AVFoundation and libusb, **not** the software modem engine.
The resulting helper has no runtime dependency on that checkout.

```sh
.venv/bin/python tools/build_apple_line.py
# Alternatively: --v90modem /path/to/v90modem
.build/apple_line --status
.build/apple_line --devices
.build/apple_line --selftest  # memory-only callback checks; no USB/HAL startup
```

Rebuild the helper after updating the backend: zero-length control requests and
explicit reset-silence flags must be supported by both Python and the helper.

`--status` configures an unconfigured USB device if necessary and enables its
on-hook monitor; it never seizes the line. `--devices` lists existing CoreAudio
modems and their rates. With multiple Apple devices, set both selections:

```sh
export APPLE_MODEM_ADDR=BUS:ADDRESS
export APPLE_MODEM_AUDIO_UID='unique substring of the corresponding audio UID'
```

USB selection refuses ambiguity. Audio and USB selections are separate; ensure
they refer to the same device. Existing off-hook devices are refused, not taken
over. Configuration and the hardware sample rate are not restored at exit.

## Hardware-only tests (no numbers dialed)

```sh
# On-hook by default; tests the known Courier rate ladder.
.venv/bin/python tools/probe_apple_line.py

# Exact native rate: briefly seizes the line and sends only silence.
.venv/bin/python tools/probe_apple_line.py --codec-rate 7200 --seconds 2 --off-hook

# Keep the device at a higher rate while the Courier grid retunes.
.venv/bin/python tools/probe_apple_line.py --hardware-rate 10286 \
  --codec-rate 7200 --codec-rate 7578.947368 --codec-rate 8000 \
  --codec-rate 9600 --off-hook
```

Exit/EOF/SIGINT/SIGTERM releases the hook; the helper prints readback confirmation.
Failures of that confirmation require checking/unplugging the device. A process
or host crash cannot provide a software guarantee of hook release.

## Firmware entry point

Use the **same 403 board/settings as the optimized paired benchmark**. This
command briefly seizes the powered line without dialing:

```sh
./courier run dumps/courier-board-21210-capture-403/courier-board.rom \
  --apple-modem --nvram-fixture idsdl403 --board-id 7 --tick-ms 5 \
  --at ATH1 --serial-input-after 5000000 \
  --instructions 180000000 --line-frames 1600 --summary
```

Keep the normal 256-instruction DSP batch and default tick source. Forcing the
B/C setup's DSP tick source or using the older `idsdl302` fixture does **not**
reproduce the optimized 403 configuration. `--apple-modem` no longer overrides
those scheduling defaults. The codec-direct path retains `audio_only` to disable
synthetic call engines, but explicitly permits safe native DSP polling between
hardware exchanges; it yields at codec-based ~20 ms service thresholds. The native
fixed-8-kHz socket FIR/frame exchange is deliberately never used.

`--apple-modem /path/to/helper` selects a different helper binary.
`--line-frames` counts actual hardware exchanges, normally around 20 ms each,
not the socket line's 100 ms frames. It is a test budget, not a precise duration.
Inspect `dsp_bridge.line.native_worker_polls`, `native_lane_io` and
`off_hook_pcm_seconds` in the report. The 1600-exchange run included startup:
32.0 s total PCM, 22.6 s off-hook PCM, 33.2 s wall time including startup/cleanup.
Hardware pacing intentionally prevents running faster than real time.

Earlier B/C tests underrun; an earlier 403 test used the wrong EEPROM fixture
and tick source and left its AT command queued. Neither was a valid test of the
optimized benchmark configuration. An established modem connection is still a
separate test: `ATH1` demonstrates audio pacing, not training/datapump throughput.

The backend excludes socket/SIP/exchange lines, synthetic ring/RX input,
forced-online mode and acquisition assistance. Real audio is not substituted
with generated dial tone or successful-carrier events.

## Rates and timing

- Codec output is taken directly from `line_tx_samples` with its clock-event
  boundaries. RX stays on the fixed Apple hardware clock in the native input
  FIFO and is reconstructed at each actual ADC edge. Already buffered samples
  therefore cannot accelerate when firmware retunes. This generalizes the
  clocked input converter's source rate; it does **not** add an 8 kHz hop or
  double resampling. No extra receive cushion is inserted.
- Native polling yields on a physical codec retune, rather than extending an
  in-flight 144-sample batch to 192 samples and starving the ADC. Both native
  and Python scheduling use the same boundary.
- Apple supports 7200, 8000, 8229, 8400, 9000, 9600 and 10286 Hz. Set
  `--apple-rate 7200` for an exact-rate experiment that stays at 7200 Hz.
- Firmware can retune during calibration or training. The default hardware rate
  is therefore fixed at **10286 Hz**, covering known Courier rates without
  reopening CoreAudio or resetting stream phase. Stateful band-limited
  resamplers handle unsupported grids such as 7578.947 Hz.
- Before starting the helper, both resampler directions and native bindings are
  prepared for 26 known/common/transient clocks at the default hardware rate.
  This includes the one-sample 8641.234462 Hz PLL transition; it is not rounded
  away. The verified live preparation took 698.48 ms. Inspect
  `prepared_codec_rates`, `preparation_ms` and `live_filter_misses`.
  `prepare_codec_rates()` accepts additional clocks only on-hook; an unknown
  unprepared active ratio fails closed rather than constructing tables live.
  The native ADC's hardware-grid FIRs are also prewarmed; an unknown live
  native ratio fails closed, rather than allocating a table on an ADC edge.
  `tools/benchmark_apple_retune.py` reproduces the host transition without
  hardware: 44.47 ms cold versus 2.65 ms prepared, with zero live kernel builds.
- A selected hardware rate below a later codec rate fails rather than silently
  narrowing its bandwidth. No undocumented 48 kHz mode is assumed.
- The helper discovers the actual HAL buffer size and primes two output
  callbacks. Input/output queues are bounded (8192 samples); callbacks do no
  socket, USB, allocation or Python work. Hardware capture paces replies.
  `APPLE_LINE_ASYNC_STATUS=1` experimentally moves ordinary status reads off
  the PCM producer, with serialized USB access and fail-closed OPD handling.
  It remains opt-in; smaller buffers still expose underruns/link errors and are
  not an adopted reliability fix. See the [scheduling follow-up](apple-sustained-traffic.md#follow-up-phase-telemetry-and-pcm-scheduling).
- The helper seizes/releases using the device firmware operation recovered
  from `USmSerial.sys` IOCTL `0x22009c` and `utlamot.sys`: class/interface OUT
  `21 11`, value 0/1, index 0, no data. It does not clear OPE on the host.
  Hook, loop-current, OPD/notification, full settling and enabled-protection
  readbacks must pass. A failed firmware command never falls back to raw hook
  assertion. Raw-register mode remains an explicit diagnostic control only.
- Before accepting seizure, the helper allows 250 ms for a valid, nonzero
  loop-current code. A valid isolation link alone does not prove a powered
  analogue line: a missing/unpowered loop can produce full-rail input that
  looks silent after DC blocking. Failure releases the hook and reports an
  error before dialing. This is not an absolute calibrated current threshold.
- Hook and DSP-reset control use **zero-length, immediately acknowledged
  requests**, independent of codec rate, sample production or ADC availability.
  Reset is notified before core reset/rebuild; hook release follows the board
  relay edge rather than waiting for the next PCM batch. When CPU execution
  ends, the physical line is explicitly released before slow DSP/JSON reporting;
  existing active-stream failures remain fatal, rather than being reclassified
  as expected shutdown silence.
- During **explicit DSP reset**, HAL callbacks keep producing silence and
  discard RX that the reset codec cannot consume. Retired-generation TX and
  converter history are flushed. The first real PCM batch re-primes output and
  atomically returns to strict streaming. An off-hook reset is bounded to
  **five seconds**; a stalled parent cannot leave an indefinite silent seizure.
- On-hook pauses may discard stale monitor input, but retain ordinary callback
  bursts. Outside explicit reset, any active RX overflow or TX underrun still
  fails closed and releases the line. Reset silence and discarded reset RX are
  counted separately in helper stderr; they are not hidden active underruns.
- Both directions use the Apple hardware clock. The 403 off-hook hold establishes
  sustained idle PCM service for 22.6 s, not trained datapump throughput or
  long-duration ADC queue stability. Explicit reset/hang-up continuity now passes
  a 350 ms hardware pause and a complete dial timeout, but trained in-call
  renegotiation/rebuilds still require validation.

`--apple-tx-gain` now defaults to **1.0**, preserving firmware output levels.
The former 0.25 default added **12.04 dB** of unjustified attenuation. Its DTMF
components measured approximately -20/-22.5 dBFS, and the ATA collected only `6`
from `6312`. Changing **only** gain to unity made the full number routable and
answered; a subsequent 6313 call confirms the fix. Explicit attenuation remains
available, but a loopback/test level is not a physical-line calibration.
Absolute AC01/Si3034-to-Apple dBm calibration is still open.

RX uses an 8 Hz DC blocker, not AGC or an equalizer. Diagnostics expose raw
peak/mean and near-rail samples. The attached line's off-hook capture at 10286 Hz
showed clipping; near-rail counts alone do not identify all codec clipping.

## Full-path audit

The [full audio-path audit](apple-audio-path-audit.md) now separates the remaining
faults. Nine codec-to-helper TX replays are sample-exact; payload audio is not
clipping, and active native ADC empty counters stay flat. A new 180-byte call
passes both ways, but packet capture still finds four missing outgoing RTP
packets after the payload. RTP framing/duplicate/truncation handling, silent TX
queue eviction, USB status-poll ordering, reset publication and terminal failure
counter reporting have been hardened. Timestamp-aware RTP playout and bounded
USB control deadlines remain open; a larger FIFO is not a repair for lost audio.

## Listening to a captured call

The offline exporter needs no NumPy and does not open the modem:

```sh
.venv/bin/python tools/render_apple_audio.py artifacts/CAPTURE/EXTENSION
afplay artifacts/CAPTURE/EXTENSION/apple-stereo.wav
```

It reads the diagnostic `codec-hardware-*` captures: left is post-gain hardware
TX, right is raw hardware RX before DC blocking. Levels are not normalized;
turn playback volume down first. Channels share exchange boundaries, not an
independently measured analog delay. Reset/on-hook gaps are omitted.

## Evidence

[Optimized 403 evidence](../artifacts/apple-line-optimized/README.md) records the
passing native-poll hardware run. [Earlier bring-up captures](../artifacts/apple-line-bringup/README.md)
retain the original failed configurations. [Reset continuity evidence](../artifacts/apple-reset-continuity/README.md)
adds the 350 ms pause and a real 6311 dial returning cleanly with `NO CARRIER`.
Those earlier dial attempts used the old output level and did not establish
correct PBX routing. [DTMF gain evidence](../artifacts/apple-dtmf-gain/README.md)
records the controlled level comparison, SIP routing and answered CDRs.
[Preflight verification](../artifacts/apple-training-underrun/README.md) records
removal of the cold retune stall. [Negotiation evidence](../artifacts/apple-negotiation-6313/README.md)
adds passive RTP capture, independently decoded menus/INFO0, a longer wait and a
diagnostic post-dial attenuation test. Attenuation did not establish CONNECT;
no automatic per-modulation gain policy has been added to the backend.
The expanded regression selection passes **111 tests**, including four optional
NumPy offline-analysis tests (NumPy is available in the sibling v90modem venv).
Software regressions include native-poll on/off comparison with identical PCM,
hook transitions, CPU registers, AT output and codec state, a complete firmware
dial timeout, and memory-only HAL checks for reset silence, stale-generation
flush, strict underrun detection and the reset watchdog:

```sh
.venv/bin/python -m pytest -q tests/test_apple_native_poll.py tests/test_apple_line.py tests/test_cli_link.py \
  tests/test_native_machine.py tests/test_bearer_line_levels.py \
  tests/test_3453c_pcm_path.py
```
