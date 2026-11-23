# B/C Bell-103: exact bidirectional terminal payload

Two unchanged B/C supervisors (2.2.09, DSP 2.0.34), opposite dedicated-line
DIP presets, `AT&M0&N1&U1`, `AT&L1`, and a **PCM-only** peer connection deliver
these distinct 32-byte terminal payloads exactly:

- A sends `A0a1b2c3d4e5f6g7A0a1b2c3d4e5f6g7`; B receives exactly that.
- B sends `B9z8y7x6w5v4u3t2B9z8y7x6w5v4u3t2`; A receives exactly that.

Both print their own original `CONNECT`. `result.json` records the selected
terminal results and zero original outbound-ring drops. This control types
payload at instruction 28,000,000, after both peers settle, and runs to
35,000,000 instructions / 95 requested common frames. It does **not** prove
lossless typing immediately after one local CONNECT, binary transfer,
long-run throughput, dialed ringing, or complete electrical UART fidelity.

The harness's online TX counter starts at the CONNECT keyword and includes its
trailing CR/LF: 34 counted writes in the steady control are 32 payload bytes
plus that terminator, not duplicated payload. Assertions compare the actual
UART tail after `CONNECT\r\n`, not this coarse counter.

The input delay is an explicit external DTE stimulus, not an emulator change
to readiness, carrier, calibration, or training. Immediate local-CONNECT
stimulus can still lose initial characters. CLI controls
`--a-send-delay-ms` / `--b-send-delay-ms` independently delay terminal typing;
the public-image regression uses 1500 ms on each side.

## First unmet conditions and fixes

Independent decoding recovered both full payloads from receiver input PCM,
DSP hard decisions, ASIC holding words, and the words actually passed to the
original CPU receiver. Nevertheless its live output was corrupted. Replaying
those **same words** through original `6EBD9` and original ring sink `6878A`,
in both CPU engines without interrupts, recovered all 32 bytes.

The missing condition was interrupt ownership:

- The byte-front-end UART request entered INT2 (`0E`) without joining the
  controller EOI stack. Its EOI therefore removed the interrupted INT0.
- The periodic mailbox request also bypassed INT0's shared in-service state.
- Another data ISR could enter while the original, non-reentrant CPU framer
  was updating `1ECC..1ED3`. Correct word delivery was not enough.

All request paths now record their actual controller interrupt. INT0 requests
share its in-service state; UART EOI no longer releases an interrupted data
ISR. Selected before/after call-pair and state-continuity counts are in
`result.json`; raw register/stack context is deliberately not published.

This removed corruption but left one terminal byte missing in each direction.
The original foreground transmitter kick writes that byte to **EB S0TBUF
`FF6A`** (B/C `5C943`). The old printf-PC capture missed the online kick;
later byte-front-end interrupts use `OUT 0A`. The 2.x capture now observes the
actual S0TBUF register instead of the printf PC, preserving byte order and
7-bit/parity handling without double-capturing command replies.

No guest callback, program, receive ring, or modem decision is replaced in the
real peer calls. No decoded byte crosses the line connection. Offline decoding
and isolated original-code replay are controls only.

## Reproduce with public captures and erased synthetic settings

The paired regression assembles the captured public B/C normal/recovery images
with an erased settings area; it does not need the private whole-flash image.
From the repository root:

```sh
.venv/bin/python -m pytest -q tests/test_3453c_call_delays.py \
  tests/test_3453c_uart_framer.py tests/test_3453c_irq_ownership.py \
  tests/test_3453c_dtr_monitor.py tests/test_cli_link.py
```

[Final validation](VALIDATION.md): **199 tests passed**, including both real
public-image peer regressions.

Full probe output belongs under `/tmp` or the private archive, not in this
selected-evidence directory.

## Selected controls

- `a-receiver-input.wav`, `b-receiver-input.wav`: receiver-input samples at
  original DSP `4538`, data `038F`, nominal 7200 Hz. These precede the IRQ fix;
  both already contain their complete far-end payload. They are not an
  electrical ADC-pin capture. A receives 1270/1070 Hz; B receives 2225/2025 Hz.
- `carrier-loss-control.json`, `carrier-loss-word-control.json`: selected
  public-image loss timing and original-framer NUL replay; no raw CPU context.
- `received-word-controls.json`: run-length-encoded three-sample words actually
  presented to the original CPU framer before the fix. Only known synthetic
  payload/idle bit words (0..7) are retained, not board settings or CPU context.
- `tests/test_3453c_uart_framer.py`: ideal phase controls and both captured-word
  replays, using both CPU engines and the original byte-ring sink.
- `tests/test_3453c_irq_ownership.py`: nested UART/data EOI ownership controls.
- `tests/test_3453c_uart_status.py`: actual register writes, parity, external
  terminal timing, and DTR-pin controls.
- `tests/test_3453c_dtr_monitor.py`: original DTR-lost predicate in both CPU
  engines, checking both active-low inputs without inventing a response.
- `tests/test_3453c_call_delays.py`: unchanged public-image peers with erased
  synthetic settings; asserts exact far-end terminal output, not just ingress.

## Genuine DTR disconnect

`dtr-disconnect.json` records a separate call with `AT&D2&M0&N1&U1` and the
physical DTR-override DIP open. Both exact 32-byte payloads arrive first. Only
**A's external DTR** drops, 5000 ms after its own CONNECT (instruction
40,943,424). B's terminal remains attached and its DTR stays asserted.

Both original supervisors then print `NO CARRIER`; both native codec/DAA hook
states finish on hook, with no errors or outbound queue drops. B therefore
responds to far-end loss, not a second artificial DTR drop. The control runs
to 55 million instructions / 145 requested common frames. No hangup command,
carrier flag, guest callback, or codec hook state is forced.

### Carrier-loss bytes and leased-line retry are preserved

The public erased-settings control (`carrier-loss-control.json`) verifies
**all 32 terminal bytes exactly before A's DTR edge**. B subsequently emits a
NUL during loss, about 432 ms after that edge, before `NO CARRIER`. The NUL is
already present at the original CPU ring sink; replaying the captured words
through the original framer and sink reproduces it in **both CPU engines**.
`carrier-loss-word-control.json` and the framer tests retain this control.
It is not UART corruption and is not filtered out to make a test pass.

B also releases its hook and later seizes again to retry the dedicated line.
A, whose DTR remains deasserted, stays on hook. The paired test checks exact
**pre-drop** payload, original post-drop bytes, both `NO CARRIER` results and
hook-release transitions—not a byte-clean carrier-loss interval or permanent
far-end on-hook state. The clean 55-million-instruction ending above is one
control, not a guarantee for every carrier-loss phase/settings combination.

The first DTR control exposed missing input transport: the original kind<6
monitor at `5AC91/5ACC4` samples **EB P1.6 (`FF5A`, bit 40)** as well as
selector `0104` (ASIC port `14`, bit 0, queried through `5A91D`). Set means
DTR lost. Driving only port `12`, or driving port `14` with the older front
end's opposite polarity, did not satisfy the original predicate. The 2.x
pin model now drives both actual inputs; the original `&D2` handler stores
its option at `0979`, not the legacy `094E` cell.

Full flash/settings and full register/stack traces stay private. The audio
and bit-word controls retained here contain only explicitly selected synthetic
payload diagnostics. No hardware was accessed for these runs.
