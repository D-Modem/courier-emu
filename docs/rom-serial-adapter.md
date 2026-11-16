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
./courier run artifacts/courier-board-21210-capture-403/courier-board.rom \
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
