# 20 MHz ROM serial execution

The 302/403 CPU-only harness has a byte-oriented terminal adapter. It enters
the ROM's existing attention detector, which recognizes `A` then `T`, collects
the command body, calls the original parser, and generates the response.
Output is captured only when firmware writes the integrated UART's S0TBUF
(`ff6a`); entering a character-output routine does not fabricate output.

For the bundled 302 image:

```sh
./courier run IDSDL302.ROM --instructions 60000000 \
  --tick-ms 5 --board-id 7 --nvram-fixture idsl302 --at AT --summary
```

The captured 403 image can be used with the same options:

```sh
./courier run dumps/courier-board-21210-capture-403/courier-board.rom \
  --instructions 60000000 --tick-ms 5 --board-id 7 \
  --nvram-fixture idsl302 --at AT --summary
```

The fixture is a recovered 302 settings fixture, not a captured 403 EEPROM.
UART output may carry parity in bit 7; mask with `0x7f` to interpret its ASCII
text. The tests retain raw bytes and also assert that their count equals the
UART's actual transmitted-byte count.

## What the adapter supplies

`courier_emu/rom_serial.py` locates the callback table's RX ISR, attention
handler, command dispatchers, mode byte, and output-routing flag from the
resident instructions. It checks the command dispatcher's event-1 transition
before accepting a layout. Unknown or incomplete layouts do not enable this
adapter.

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
command mode and the attention handler, and disables the separate buffered
output route. It supplies bytes through this image's integrated-UART ISR.
After a command, queued input waits until the firmware returns to its ready
state; the adapter then reselects the attention handler. It does not inspect
command text or construct result strings.

This remains an explicit substitute for raw-pin autobaud in a CPU-only run.
It does not establish cycle-accurate baud detection, DSP startup, or a working
telephone connection. Timing still uses the harness's instruction-based boot
and character delays.

## Hardware-facing corrections

The terminal remains connected after its input queue drains. Previously the
last carriage return also deasserted DTR while firmware was processing the
command.

The resident ROM switch wiring differs from the XMF supervisor. In particular,
its profile builder reads result-code enable at port `12h`, bit 0 (selector 3,
mask `01h`), whereas XMF reads port `14h`, bit 5. Applying the XMF wiring to
these ROMs left Q1 selected and suppressed otherwise valid responses. The
panel now selects the resident mapping for recognized ROMs.

The prior workaround forced a 302 collector and ISR into both layouts, skipped
attention recognition, and redirected output to a RAM buffer. That block and
its character-routine capture hook have been removed. The earlier failure
analysis in `rom-dte-path.md` describes the pre-fix behavior.

## Regression coverage

`tests/test_rom_serial.py` checks actual UART responses, complete consumption
of queued input, repeated commands, and Q1/Q0 behavior. The layout tests cover
both resident builds and reject incomplete signatures. The XMF callback
regression checks that its existing serial path still works.

Validation on 2026-09-06: the focused ROM serial, serial callback, layout, and
panel suite passed **31 tests and 8 subtests**. Both ROMs completed
`AT`, `ATI`, `ATQ1`, `ATQ0`, `AT` with four OK responses and no response to Q1.
Captured 403 returned identification `5607A`. These tests executed Unicorn
outside the filesystem sandbox because its sandboxed memory mapping crashes
on this host before firmware starts.

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
