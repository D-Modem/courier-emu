# Analog Courier V.90: preserve DTE bytes through retraining

## Result

The analog emulator now respects the modem's active-low CS/CTS output before
starting a new DTE character. With hardware flow control enabled (`&H1`), two
fresh V.90/LAPM calls deliver **38,400 bytes exactly in both directions**,
including recovery across two completed retrains. A matched negative control
with the same firmware, settings, payload and engine binary, but the old
host behavior of ignoring CTS, loses **7,680 upstream payload bytes**.

This resolves a demonstrated emulator/DTE continuity defect. It does not
remove legitimate retrains, establish a retrain-free PHY, qualify arbitrary
binary traffic, or claim a physical Courier interoperability fix.

## Subsequent PHY repair

The CTS result above remains valid. The repeated full-retrain cycle is now
separately traced to missed V.90 renegotiation and stale DATA receiver state
in v90modem; a corrected 600M-instruction call completes a short renegotiation
with exact 38400-byte duplex traffic and no full retrain. See
[analog-v90-rate-renegotiation.md](analog-v90-rate-renegotiation.md). This does
not supersede the CTS requirement during legitimate recovery.

## The earlier discontinuity diagnosis was incomplete

The original short calls logged a V.90 upstream discontinuity around the same
point. Passive observation now shows the Courier itself asks for a rate
change before that event:

* At CPU instruction 229,666,689, the original supervisor updates its requested
  internal rate from `13` to `15` (hex), writes `[0a25]=0015` at observed PC
  `9445f`, and queues runtime operation `0054:0015`.
* The automatic path reads `[0a17]`; the manual request flag at `[0a16]` is
  clear. No ATN command or synthetic state transition was injected.
* The upstream recording then has approximately 507 samples of digital
  silence followed by a strong 2400-Hz tone. For example, samples
  399256..399762 of `analog-v90-dil-duplex5000-grid5-20261103/engine-rx.g711`
  are silence. This is compatible with the analogue retrain sequence, not
  evidence that a healthy continuous data constellation spontaneously failed.
* The engine follows the peer back through training and reacquires B1.
  The passive 300M and wire-traced 480M controls report zero Courier BLERs;
  this is not a claim that every physical upstream bit was error-free.

The operational failure was that DTE input kept arriving during a period
when the modem could not drain its firmware transmit buffer. The integrated
UART can correctly receive every character, with **zero OE overruns**, while
that higher-level buffer still overflows. The probe compounded this by
explicitly using `&H0` (hardware flow control disabled).

## Correction

`CourierMachine._dte_transmit_permitted()` in `courier_emu/machine.py` gates
**new start bits** on the online ROM modem's CS output, latch `0x14` bit `02`,
active low. An in-flight character always completes. Pending source bytes
remain queued; they are not deleted, synthesized, or delivered into firmware
RAM. The UART's own `clear_to_send` input is the opposite direction (host
RTS), and cannot serve as this host transmit gate.

Evidence for this board-side signal:

* `panel.py` records the physical CS lamp on `0x14:02`, asserted low.
* The original ROM bootmodem receive-buffer flow routine at `a7aa2..a7aba`
  raises that bit at occupancy `3e00`; its drain-side routine at
  `a7a21..a7a3f` clears it at/below `2000`. This corroborates its buffer-flow
  role. This work is not a new electrical measurement of the DB-25 pin.
* The controlled full-firmware calls below demonstrate actual backpressure
  on this signal and exact end-to-end recovery.

Scope is recognized ROM DTE layouts in online mode. Command/autobaud mode,
unknown boards, and an unobserved latch retain their previous behavior.
The sibling `../v90modem/tools/probe_x2_host_courier.py` now enables `&H1`
by default **for V.90**; x2 keeps its prior settings. Explicit subsequent
AT settings still work normally.

No waveform, gain, rate ceiling, DSP arithmetic, timing loop, device buffer
capacity, CRC acceptance, LAPM sequence check or resynchronization threshold
was changed. In particular, the correction does not suppress rate changes or
resync requests to manufacture a stable-looking log.

## Matched end-to-end validation

Artifact prefix is `artifacts/analog-v90-continuity-`, suffix `-20261103`.
All three controls use 600M guest instructions, wall-clock pacing, ordinary
PTY source and sink, original 403 firmware, V.90 explicitly enabled and x2
disabled, `&M5&K0&H1`, and 38,400 ASCII source bytes each way. Downstream
injection is one byte per 16 bearer samples (500 bytes/s), beginning at sample
220000; the native source is one ordinary DTE burst, not chunk-paced.

| Middle of artifact path | Frame | Host obeys CTS | Exact downstream | Exact upstream |
| --- | ---: | --- | ---: | ---: |
| `cts600` | 20 ms | yes | 38,400 / 38,400 | 38,400 / 38,400 |
| `ignorects600` | 20 ms | **no**, negative control | 38,400 / 38,400 | **30,720 / 38,400** |
| `cts-default600-grid5` | 5 ms | yes, new probe default | 38,400 / 38,400 | 38,400 / 38,400 |

The engine SHA-256 in all three matched arms is
`90844352b126d602942da64bc99f4034b39f358a6d7ccf974867d89ebed37ad3`.
It differs from the binary in the earlier DIL investigation; that is why the
causal CTS comparison uses this matched negative control, not the earlier
unmatched runs.

Each call reports `CONNECT 52000/ARQ/V90/LAPM`. Both corrected calls pass all
10 validation checks, including the entire exact stream after CONNECT, not
substring matches. Their full DTE captures are 38,430 native wire octets
(including parity/result framing) and 38,417 engine octets. The negative
control has 30,737 engine octets: exactly 7,680 payload bytes missing.

All three have zero UART overruns, no native source bytes left queued, and
both processes exit 0. Native input pauses for 37,008,576 guest instructions
in the 20-ms corrected call (about 8.5 guest seconds), versus a largest gap
of only 3,840 instructions when CTS is ignored. The 5-ms repeat pauses for
35,942,080 instructions. This is real source backpressure, not silent
postprocessing of the received transcript.

The controls exchange 1,249,760 / 1,249,920 bearer samples (about 156.2
seconds). Each completes two retrains and starts a third near the instruction
bound. No NO CARRIER is emitted; however, the final retrain is incomplete at
that bound. These results establish exact finite delivery through two
recoveries, **not a no-gap throughput guarantee or qualification of the final
retrain**. Long retrain gaps remain visible.

`artifacts/analog-v90-continuity-summary-20261103/results.json` consolidates
the checks, hashes, byte counts, DTE gaps, process results and recovery counts.
Its `negative-control-sitecustomize.py` records the test-only override:
`CourierMachine._dte_transmit_permitted = lambda self: True`. It was loaded
through an isolated PYTHONPATH for the negative arm only; no production
recovery or data check was disabled.

## Reproduction

The current sibling driver supports the modulation selection and CTS profile.
Use a new output directory. This Python launcher preserves the payload's final
CR/LF (shell command substitution would strip trailing newlines):

```sh
X2_HOST_EMU_ROOT="$PWD" COURIER_LINE_FRAME_MS=20 .venv/bin/python - <<'PY'
from pathlib import Path
import subprocess, sys
payload = b''.join(
    f'V90-{i:05d}-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n'.encode()
    for i in range(800))
source = Path('tmp/v90-soak-source.txt')
source.parent.mkdir(exist_ok=True)
source.write_bytes(payload)
subprocess.run([
    sys.executable, '../v90modem/tools/probe_x2_host_courier.py',
    '--modulation', 'v90', '--courier-at', '&M5&K0', '--pty-source',
    '--host-pace-samples', '16', '--instructions', '600000000',
    '--host-at', '220000', '--host-message-file', str(source),
    '--message', payload.decode('ascii'),
    '--output', 'artifacts/analog-v90-continuity-new-run',
], check=True)
PY
```

Use `COURIER_LINE_FRAME_MS=5` for the other cadence. To reproduce the negative
arm, copy the retained test-only override to a separate directory as
`sitecustomize.py`, and prepend that directory plus this source root to
PYTHONPATH. Keep `&H1` and every other setting identical.

## Other controls and limitations

* `baseline600` ends without a valid native summary (the old ten-second
  shutdown allowance killed its CPU-only tail). It is not an acceptance pass.
* `wire480` and the old `&H0` burst profile expose upstream byte loss;
  UART overrun counts alone did not reveal it.
* `paced600` uses exploratory 600-byte chunks 1.5 guest seconds apart. It
  delivers an exact prefix but ends before the full upstream source drains;
  it fails acceptance and is not evidence for the CTS correction. The optional
  `--native-chunk-bytes` control remains available, but the passing matched
  CTS tests do **not** use it.
* The probe now allows 60 seconds for the guest's CPU-only tail to publish its
  summary after bearer clearance. The sibling driver classifies a missing or
  invalid JSON summary as an invalid capture, never as a successful call.
* A fresh x2 smoke call (`analog-v90-cts-x2-regression-20261103`) still passes
  all exact payload checks after the emulator change.
* **108 focused tests pass**, covering the new CTS gate, in-flight completion,
  command/unknown-board scope, source chunk preservation, native UART/port
  models, raw DTE pin timing, serial capture and V.90 transport/profile tests.

No physical call or physical endpoint configuration was changed. Hardware
interop still requires testing on the actual wired Courier rig. The fixed
host-side flow-control defect is demonstrated locally; it is not a substitute
for that hardware test.
