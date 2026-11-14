# SV25.XMD recovery-loader harness

To run the focused 80188 experiment, use this command:

```sh
./courier recovery-run SV25.XMD > /tmp/sv25-recovery.json
```

If the existing execution extra is installed, the equivalent command is
`python -m courier_emu recovery-run SV25.XMD`. The command starts an isolated
Unicorn worker and prints a JSON report. The exit status is zero only when the
complete SDL prompt has gone through the serial transmit store of the firmware.
`--instructions N` sets a positive instruction budget (default 6,000,000).
`--no-serial-stimulus` stops at the foreground command wait and does not supply
input. To select a custom native library, use `--libunicorn DIRECTORY`.
The native JIT of Unicorn needs an environment that permits executable memory. If a native signal
kills a worker, the public CLI gives `native-error`.

The module opens the input with `Path.read_bytes()`. It has no interface for image save,
flash programming, transfer or a physical serial device. The command
`AT~X!\r` goes only to the emulated CPU. No `Y` or `T` response is sent.
Use a separate path for redirected JSON output, as in the example above.

## Observed result

For the source image in the repository, SHA-256
`43503d82caae5377d67c61f4f44d73e6a19e15c61b2cb706a70c6f1b88ef413f`,
Unicorn 2.1.4 gets to this result:

```text
status: sdl-xmodem-prompt
instructions: 5051290
setup_word_writes: 36
setup_byte_writes: 9
relocation_verified: true
flash_array_unchanged: true
source_file_unchanged: true
serial_text: "\r\n\r\nSDL Xmodem file transfer - (Y)es (N)o (T)est >"
stop: 0000:12bb (MOV [0xff6a], AX), AL=0x3e ('>')
```

The bytes written to the serial data register cause the stop. The stop does not come from a search
for a string in the image, from a shortcut in the print routine, or from a forced jump to the
prompt. The CPU executes the setup loops, the RAM copy, the software interrupt, the CRC, the
autobaud interrupt handler, the AT/token parser and the serial-output loop. The count
is the number of instruction-hook steps of Unicorn, which includes REP iterations and interrupted
foreground dispatches. It is not a measurement of cycles or bus timing.

With this decoded map, the CPU calculates the application CRC `0x1735` over flash
`0x40000..0x77ffd`, and compares it with `0xffff` at flash `0x77ffe`. That mismatch
selects the recovery path. This does **not** show that a modem programmed
by the original downloader has a corrupt application. The downloadable image, the
programming process and the installed checksum can be different. The harness does not
patch the checksum or force the conditional branch.

> **We now measured the caveat, and it is correct.** A 512 KiB capture of a 25 MHz
> board that runs this same build is different from the decoded `SV25.XMD` in exactly four
> bytes, and all of them are here:
>
> | flash | decoded `SV25.XMD` | programmed board |
> |---|---|---|
> | `0x77ffc..0x77ffd` | `ff ff` | `ec 1c` |
> | `0x77ffe..0x77fff` | `ff ff` | `59 7d` |
>
> Thus, the `0xffff` that the harness compares with is the *unprogrammed* state of
> the distributed image, and the downloader fills in the two words. The same four
> bytes are the only difference between `IDSDL302.ROM` and the decoded
> `IDSDL302.XMD` (`5e 9e bc 53` on that board). Thus, this is the normal condition of the container.
> It is not specific to SV25.
>
> Note that `0x77ffc..0x77ffd` is *in* the CRC range `0x40000..0x77ffd`,
> and `0x77ffe` holds the stored value. Thus, the CRC input of a real board is not
> the CRC input of the image. We did not yet identify the algorithm: sum-8, sum-16 and the
> IBM, MODBUS, CCITT, XMODEM and KERMIT CRC-16s over that range all do not give
> `0x7d59`. We did not run in the harness the test if the firmware of the board itself accepts its checksum.

## XMD decode, not a speculative bank transition

Remove the 128-byte header. For each 128-byte payload block:

1. XOR each byte with the current key, initially `0x55`.
2. Use the last **decoded** byte as the key of the next block.

We recovered this file transform empirically. It does not mean that the
80188 or its flash bus does an XOR at runtime. The raw and the decoded bytes are
immutable Python `bytes` objects. Only the decoded view is mapped for execution.
The report includes the two digests and all block keys of the recovery region.

These independent checks support the transform: the initial application
stub and copyright text, valid low-RAM interrupt vectors, continuous prompt
strings, all setup table entries, the relocation instruction that crosses a block
boundary, and the reset stub. Specifically:

| Flash block | XOR key | Consequence |
|---|---:|---|
| `0x7db00` | `0xa1` | Decodes the first 27 setup records into peripheral register writes. |
| `0x7db80` | `0x00` | Nine remaining word records, byte table and bootstrap already look plain. |
| `0x7dc00` | `0xf3` | Restores the second byte of `REP MOVSW`, then `XOR AX,AX; MOV DS,AX; INT 13h`. |

This block transform explains the partial XOR strings and the apparent bank break after the setup
that the earlier static analysis found. The executed recovery path does not need a runtime bank flip.
This result does not solve the full resident/overlay map of the normal
supervisor.

## Address map and assumptions

Offsets called “flash” refer to the decoded payload, without the header.
To get file offsets, add `0x80`. Thus, the requested bootstrap at flash `0x7dbc0` is
file `0x7dc40`, logical `fc00:1bc0`, physical `0xfdbc0`.

| Region or action | Model and evidence |
|---|---|
| Flash `0x80000..0xfffff` | Read/execute mapping. The decoded reset stub programs `OUT 0xffa4,0x8000` and jumps to `fc00:1bbf`. That target starts with `CLD`. The requested harness entry is the next instruction at `1bc0`, thus DF starts clear. IF also starts clear. |
| RAM `0..0x1ffff` | Zero-filled 128 KiB allocation, selected from LCS start `0x0000` and stop `0x200a`. The recovery path uses low memory. This does not resolve the earlier claim of 64 KiB RAM in the board specification. |
| Peripheral block `0xff00..0xffff` | Available as memory and I/O aliases for bootstrap access. The firmware first writes memory `0xffa8=0x00ff`, and later outputs `0xffa8=0x10ff`. These are recorded. The alias availability is simplified. The model does not enforce each relocation decode gate. |
| Loader copy | The CPU copies `0x1b14` bytes from physical `0xfc000` to zero with `REP MOVSW`. The harness verifies each byte before it dispatches `INT 13h` through the newly copied IVT to `0000:043e`. |
| Other addresses | Not mapped. An access stops with its address and PC. There is no broad identity alias or guessed flash-to-RAM mirror. |
| Chip selects and board latches | Each write is recorded, with the word width and the provenance. Candidate address fields are decoded as `(value & 0xffc0) << 4`. Wait states, upper-stop granularity and overlapping selects are not simulated. Board-latch writes do not remap memory. |

The CPU core is the 16-bit x86 engine of Unicorn. It is not a cycle-accurate Intel 80188
with a restricted instruction set. The model covers the recovered instruction path and a
small subset of peripherals. It does not execute DSP firmware, the bank dispatch of the normal supervisor,
XMODEM reception, or programming or erase routines.

## Peripheral stimuli

- `IN 0x10` returns `0x08`. The startup readiness bit is asserted, and the EEPROM
  data samples are zero. The firmware bit-bangs its own startup sequence. No
  persistent EEPROM is loaded or written.
- `IN 0x12` returns `0x40`. This selects the recovery combination if the CRC passes.
  Other input ports return all ones. Output latches are logged independently
  from input responses.
- The serial status at `0xff66` returns `0x0008` (transmit ready). Writes to
  `0xff6a` supply captured bytes. Other peripheral registers keep their
  register values, unless a listed stimulus updates them.
- At the foreground wait `0000:0875`, after the firmware installs vector `0x0d`
  and unmasks INT1, the harness supplies one edge with timer-1 count `0x0050`.
  The autobaud handler of the firmware selects its short-count path and installs
  the serial handler itself. The count is a deterministic stimulus. It is not a
  measured baud rate or a general timer model.
- At later visits to that wait, with interrupts enabled and serial RX
  unmasked, the harness supplies `AT~X!\r` through register `0xff68` and vector
  `0x14`, one byte at a time. The real ISR and parser instructions consume it.
  Parser flags, buffers, return values and PCs are not preseeded to skip them.
- The two known word stores of the flash-ID probe at `0000:0733` and `0000:0743`
  send `0x90` and `0xff` to physical `0xffff0`. These device commands do not program.
  They select a temporary Intel ID read view (`0x0089`, `0x4470`) and
  restore array reads. This chip identity is an assumption to satisfy the
  supported-device branch of the firmware. It is not a part that we identified from a board.
  Protected-write faults emulate only those MOVs outside the callback. All
  other CPU flash stores stop as `blocked-flash-write`. The array never gets
  CPU write permission. The ID view is restored also if the budget expires.

The harness makes no timer ticks or asynchronous interrupts other than those stimuli.
`--no-serial-stimulus` leaves the loader at `serial-input-wait`. This makes the
input dependency directly visible.

## Report and validation

`events` is chronological. It contains these items:

- Each I/O access and each peripheral memory write
- The setup provenance and the interpretations of the mapping registers
- The board latch writes
- The verified RAM relocation and the later IVT changes
- The CS transitions and the interrupt deliveries
- The CRC comparison, the flash commands, and each RX/TX byte

Addresses, values and PCs are numeric JSON fields. No setup events are truncated.
`memory_write_counts` aggregates all guest RAM writes by start address. This
includes copy, stack and CRC state writes. Thus, repeated RAM writes do not fill
the event log. Host device-view updates and the construction of the interrupt stack
show as their device/interrupt events, not as guest-write counts.
The final registers, the recent PCs, the hot PCs and the stop reason support incomplete runs.

The tests use the real image to verify the full output path. They compare all 45
executed table writes, and they do an independent reflected CRC calculation. Small RAM
programs test protected flash stores, budget expiry during the identifier
view, and unmapped accesses. Budget runs and runs with no input must not claim a prompt.
The CLI also tests the containment of native worker signals.

```sh
python -m pytest tests/test_recovery.py tests/test_cli.py -q
```
