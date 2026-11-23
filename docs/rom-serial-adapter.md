# 20 MHz ROM serial execution

The CPU-only harness for 302/403 has a byte-oriented terminal adapter. It
enters the existing attention detector of the ROM, which recognizes `A` then
`T`. The detector collects the command body, calls the original parser, and
makes the response. The harness captures output only when the firmware writes
S0TBUF of the integrated UART (`ff6a`). Entry into a character-output routine
does not fabricate output.

For the bundled 302 image, use this command:

```sh
./courier run IDSDL302.ROM --instructions 60000000 \
  --tick-ms 5 --board-id 7 --nvram-fixture idsl302 --at AT --summary
```

You can use the captured 403 image with the same options:

```sh
./courier run dumps/courier-board-21210-capture-403/courier-board.rom \
  --instructions 60000000 --tick-ms 5 --board-id 7 \
  --nvram-fixture idsl302 --at AT --summary
```

The fixture is a recovered 302 settings fixture. It is not a captured 403
EEPROM. The UART output can have parity in bit 7. To read its ASCII text, mask
it with `0x7f`. The tests keep the raw bytes. They also assert that the count
of these bytes is equal to the actual count of bytes that the UART
transmitted.

## What the adapter supplies

`courier_emu/rom_serial.py` finds these items from the resident instructions:
the RX ISR of the callback table, the attention handler, the command
dispatchers, the mode byte and the output-routing flag. Before it accepts a
layout, it examines the event-1 transition of the command dispatcher. Unknown
or incomplete layouts do not enable this adapter.

| Resident item | 302 | captured 403 |
| --- | --- | --- |
| RX/TX/command table | `026a` | `0164` |
| UART RX ISR, segment `8000` | `0f23` | `0f54` |
| `A` attention detector | `f170` | `f1a0` |
| Ready command dispatcher | `931d` | `93b0` |
| Dispatcher after `A` | `93b0` | `9443` |
| Mode byte | `033e` | `0237` |
| Output-routing flag | `0ea7` | `0d93` |

At the first queued byte after the existing boot delay, the adapter selects
the command mode and the attention handler. It disables the separate buffered
output route. It supplies bytes through the integrated-UART ISR of this image.
After a command, queued input waits until the firmware goes back to its ready
state. Then the adapter selects the attention handler again. It does not
examine command text or make result strings.

This is still an explicit substitute for raw-pin autobaud in a CPU-only run.
It does not show cycle-accurate baud detection, DSP startup, or a working
telephone connection. The timing still uses the instruction-based boot and
character delays of the harness.

## Hardware-facing corrections

The terminal stays connected after its input queue is empty. Before this
correction, the last carriage return also deasserted DTR while the firmware
processed the command.

The switch wiring of the resident ROM is different from the XMF supervisor.
Specifically, its profile builder reads the result-code enable at port `12h`,
bit 0 (selector 3, mask `01h`). XMF reads port `14h`, bit 5. When we applied
the XMF wiring to these ROMs, Q1 stayed selected and valid responses were
suppressed. Now the panel selects the resident mapping for recognized ROMs.

The prior workaround forced a 302 collector and ISR into the two layouts. It
skipped the attention recognition and sent the output to a RAM buffer. We
removed that block and its capture hook for the character routine. The earlier
failure analysis in `rom-dte-path.md` describes the behavior before the
correction.

## Regression coverage

`tests/test_rom_serial.py` examines actual UART responses, the complete
consumption of queued input, repeated commands, and the Q1/Q0 behavior. The
layout tests cover the two resident builds and reject incomplete signatures.
The XMF callback regression makes sure that its existing serial path
continues to work.

Validation on 2026-09-06: the focused suite for ROM serial, serial callback,
layout and panel passed **31 tests and 8 subtests**. The two ROMs completed
`AT`, `ATI`, `ATQ1`, `ATQ0`, `AT` with four OK responses and no response to Q1.
The captured 403 returned the identification `5607A`. These tests executed
Unicorn outside the filesystem sandbox. In the sandbox, its memory mapping
crashes on this host before the firmware starts.

## UART status reconstruction (2026-10-13)

The integrated UART now exposes receive completion (`0040`), transmit
completion (`0020`) and unread-buffer overrun (`0004`). Reading `S0STS`
clears those status flags without consuming the receive byte or cancelling
the independently latched interrupt requests. Reading `S0RBUF` consumes the
byte without clearing receive completion. A subsequent unread reception
replaces the buffer with the newer byte and sets overrun. CTS (`0002`) and
transmitter-empty (`0008`) remain set across status reads.

These semantics follow Intel manual 270830-003, Figure 10-14 and section
10.4.1; the local copy is
`docs/270830-003 80C186EB,80C188EB Microprocessor Users Manual-Feb95.pdf`.
The 302 ISR at `80f23` reads the buffer and calls `[026a]`, without reading
status. The 403 ISR at `80f54` does the same through `[0164]`. Thus receive
completion and unread data must be tracked separately. The online 403
handlers at `81829` and `8189d` also test status for BREAK (`0300`) before
reading the buffer; interpreting all status reads as discarded
acknowledgements misses these paths.

Reproduce the offline disassembly and full command regressions with:

```sh
.venv/bin/python tools/verify_rom_uart_status.py
.venv/bin/python -m pytest -q tests/test_eb_serial.py tests/test_3453c_uart_status.py
```

Both ROMs execute `AT`, `ATI`, `ATQ1`, `ATQ0`, `AT` for 60M instructions
with the native interpreter, board ID 7, a 5 ms tick and their respective
EEPROM fixtures. All 20 input bytes are consumed, IDs are `5607` / `5607A`,
four OK responses are generated, Q1 is silent and neither run overruns.
Fingerprints, raw bytes and ISR listings are saved under
`artifacts/rom-uart-status-20261013/`.

The later [analog UART starvation fix](imodem-v34-uart-starvation-fix-20261026.md)
adds a baud-timed, double-buffered transmitter for internally clocked asynchronous
mode 1 in ROM runs, with TI at the stop bit and TXE only when both slots empty.
It also separates RX admission from TX requests and services RX before TX.
Other modes and standalone legacy UART instances retain synchronous completion;
console output is captured on buffer writes rather than encoded onto a wire.
CTS remains asserted by the terminal adapter when it delivers input; a physical
RTS/DTR handshake, parity/framing errors and BREAK generation remain separate work.

## Console DTE format defaults

The byte-oriented attention adapter bypasses raw-pin format discovery as well as
raw-pin baud measurement. Previously it handed AT to the parser without
publishing a format, leaving an unprovisioned modem at 9600/7E1. After CONNECT,
parity appeared as accented characters in an eight-bit GUI. Changing the GUI
view to seven bits hid that mismatch and could hide legitimate eight-bit data.

Console/pty runs now default to `--dte-framing 8N1`. The adapter publishes the
selected format when accepting AT, after boot has loaded its profile. The GUI
also explicitly defaults to 8N1 and offers stored framing and 7E1/7O1/7M1.
`--dte-framing stored` performs no setting write; batch runs retain stored
framing by default. No factory EEPROM image is installed or changed.

The active framing byte is identified by the full ATI4 WORDLEN-reader prologue,
including its alternate-format branch. ATI5's stored-profile reader must not
match. Observed active bytes are 0936 (211), 0958 (2205), 095a (2.3.33), 05e6
(IDSDL302) and 04de (captured 403). Unknown or ambiguous layouts reject an
explicit format rather than borrowing one of these addresses. Serial decoding
uses the accepted active format rather than dropping bit 7 merely because the
modem is in command mode; eight-bit data remains eight-bit data.

This is format completion at the existing CPU-only byte adapter, not a claim
that raw autobaud timing, parity-error detection or connected-call training has
been implemented. Verify the setting with firmware-produced ATI4, not a display
mask or synthetic response.
