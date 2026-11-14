# Courier XMF emulator harness

The AT interface of the I-modem now answers. `isdn-run` now models the receive
side of the 386EX SIO: RBR, IIR, MSR and the IRQ3 line that its own ISR at
`0xb2aa2` names. Thus, you can type commands at the firmware and read back its
replies. `--send ATI3` returns `USRobotics Courier I-Modem with ISDN/V.34`, and
`--terminal` attaches a live console. For usual interactive use, run this
command:

```sh
./courier isdn-run Ie030002.nac --terminal
```

Type AT commands and push Return. To exit, push Ctrl-]. Terminal mode runs
until you detach it. It does not print the diagnostic JSON report unless you
also supply `--report`. During interaction, the harness paces the guest clock
to the 5 million instructions per second of the timer model. Thus, the modem
continues to run, but it does not go hours ahead of the terminal. For the
`ATI0`-`ATI30` sweep, see [the AT interface](docs/imodem-at-interface.md).
[I-modem terminal framing](docs/imodem-terminal-framing.md) tells how the
attention receiver of the external board makes consecutive AT commands
independent.

The [I-modem/analogue Courier pair](docs/imodem-analog-pair.md) sets up native
Bell 103 carrier at 300 bps. It transfers terminal data in the two directions
with the `--protocol bell103` preset of the paired probe. The six-word ASIC data
window and the acknowledgements of the I-modem now move the payload through the
original DSP firmware. V.34 carrier is not yet solved.

The captured 20.16 MHz DSP boot ROM is now integrated for the 302/403 firmware
under `--with-dsp`. The DSP executes reset and downloads its resident through
the ROM loader. The harness now has correct PMST vector decoding and IDLE
wakeup. See
[boot-ROM integration](docs/dsp-onchip-rom.md#bridge-integration-2026-09-07).

The [DSP 3.1.2 audio trace](docs/audio-312-path.md) now runs the original tone
selector, oscillator, mixer and serial ISR. These produce all 16 DTMF pairs.
The trace repairs errors in the square, product-load and normalization
instructions that made this path silent. It also writes a WAV file that you
can listen to.

This board image has a DRR/DXR sample-buffer path, and it drives the codec
itself. The ISR implements the AC0x secondary-frame protocol. The reset
programs six of the control registers of the part. Thus, the claims below that
come from `main211` do not apply to this image. Its 7200 Hz is the rate of the
dial path, not of the board. The PCM modulations that it advertises make a rate
change necessary, and it makes one. A six-row table selects 7200, 7578.95 or
8000 Hz from the symbol rate that V.34 negotiates. See
[the codec sample rates](docs/codec-sample-rates.md). For the earlier state of
this question, see [the codec rate](docs/codec-rate-312.md).

The [DSP 3.1.2 hardware comparison](docs/mailbox-312-comparison.md) records a
new mailbox sequence from a connected board. It also records the replay of this
sequence through the original DSP dispatcher and sender. It identifies the tone
selector of the current firmware. It shows the acknowledgement behavior that is
necessary to receive replies. It also shows clearly the remaining reply
mismatch, which depends on the samples. Do not apply older assumptions about
mailbox no-ops and streams to this firmware without change.

This repository contains a dual-core firmware harness for `main211.xmf`. The
harness gives the same results each time. It validates and splits the update
image. It executes the Intel 80186 supervisor in an instrumented address space
of 1 MiB. It runs the recovered TMS320C51 program with a standalone 16-bit
fixed-point DSP core.

For the older `SV25.XMD`, `./courier recovery-run SV25.XMD` runs a separate
80188 recovery-loader harness. This harness is read-only. It runs from flash
`0x7dbc0` to the complete SDL Xmodem prompt. It reports each setup write,
mapping observation, serial byte and stop condition as JSON. For the recovered
XMD block decode, the memory map, the peripheral assumptions and the tests, see
[SV25 recovery harness](docs/sv25-recovery.md).

The [DSP ROM-read diagnostic](docs/dsp-rom-probe.md) gives a C5x kernel and a
RAM supervisor launcher for the 20.16 MHz reference. Its offline test executes
reset/download, DSP mailbox output and supervisor serial readback. The harness
still models the hardware handshakes. A physical mechanism to load RAM and
launch the kernel is not yet verified.

The same document describes the read-only `ATGLK2` serial collector for the
20.16 MHz, 512 KiB modem of the user. That board now runs supervisor 7.4.16 /
DSP 3.1.2. This is the image under
`artifacts/courier-board-21210-capture-403/`. Before, the board reported
7.3.14 / DSP 3.0.13, and the older notes below describe that version:

```sh
.venv/bin/python -m courier_emu.flash_dump \
  --device /dev/cu.usbserial-21210 --baud 115200 \
  --output artifacts/courier-board-capture
```

The command must have a new output directory. It checks the modem identity and
the known reset vector. It verifies two reads of each 256-byte page, which must
be the same, before it publishes a complete image. It keeps raw replies and
partial blocks. This procedure captures the flash that the CPU can see. The DSP
internal ROM needs a separate experiment.

[The hardware tick, the audio path, and the DSP's low program
memory](docs/hardware-timebase-and-audio-path.md) confirms three items that the
harness used as assumptions. Each item has more than one source:

- One firmware tick is 5.000 ms. The board measures 1.000031 seconds for each
  `S18` unit over twelve `&T1` runs. The two builds change S-register seconds
  to ticks by a multiplication by 200. The two builds program 80186 Timer 0 for
  exactly 5 ms on their own crystal: `0x6270` at 20.16 MHz and `0x7e00` at
  25.8048 MHz. This value also identifies `main211` as the 25.8048 MHz build.
- A port sweep during `AT&T8` analogue loopback shows that no CPU port carries
  samples. Thus, the 80186 is not in the audio path. Where the audio goes on
  the DSP side is not yet known. We withdraw an earlier claim here that it
  arrives on the C5x serial port. At run time, the DSP polls `DRR`, `TRCV` and
  the ports of the ASIC together. After reset, it never transmits on a serial
  port.
- The modem does not execute the mask ROM of the C51. The firmware supplies
  program words `0000..75d9`, which include the reset code. The firmware also
  programs the wait states of external memory. The download stream of the
  supervisor matches that segment byte for byte (`bootstrap_match`, 60,344
  bytes). The bridge checks this match, and does not assume it. Thus, those
  words are RAM that the CPU writes.

[What is actually on the board](docs/board-parts.md) identifies the parts from
a photograph. Where possible, it checks each part against the firmware. The
large NEC package is `1-016-905`. This is a USR part number on a gate array that
NEC made. It is the "interposed ASIC" that these notes model as a black box.
The mailbox, the DSP download window, the codec bring-up, the line detector and
the missing tone generator are all in that one package. The `40.320 MHz`
oscillator also confirms that CLKOUT is 20.16 MHz. This was the last item that
the tick derivation needed.

[Modelling the 20.16 MHz ASIC](docs/asic-port-map.md) reads the port space of
that gate array from the board while it runs. It uses
`python -m courier_emu.asic_probe`, which writes nothing. The ASIC decodes only
even addresses. The decode stops at `0x7f`. Above it, the bus only returns the
address. The idle default is `0x00`, but the harness returns `0xff` for each
port that it does not model. The measured map is `courier_emu.asic_ports`. It
is published, but it is not connected into the harness, and it does not repair
the ROM transmit bug.

We moved the constants that used the old calibration together with it:

- `INSTRUCTIONS_PER_MS` 1,111 -> 4,348
- `SUGGESTED_TICK_MS` 10 -> 5
- `RING_START_MS` 8,000 -> 2,000 ms, so that the first ring keeps its old
  instruction offset

At equal line time, the receive backlog of the linked pair decreases from 4.88x
to 1.25x. `codec_rx_consumed` changes from 66,267 to 271,475. The two sides
still get to `CONNECT`. Runs now cover about four times less line time for each
instruction. Thus, `link` needs about 156M instructions to see what 40M showed
before.

The [boot-block flash loader](docs/sdl-boot-block.md) documents the downloader
that FreeLSD and SDL.EXE talk to. `python -m courier_emu.sdl_download`
implements the host side for a raw 512 KiB image. The build and check of a
record stream occur offline. The report gives these items:

- The CRC to give to the modem
- The blocks that the download erases
- The two parameter blocks that it never erases
- The result of a replay of the stream through a model of the state machine of
  the loader

We transcribed the wire exchange from the disassembly. We did not run it
against hardware. You can get to the loader only after a reset that fails the
flash CRC or that matches the bootstrap DIP-switch combination.

For live CPU RAM, use `python -m courier_emu.ram_dump` with the same options
and a new output directory. It keeps two passes through `00000..0feff`. It
skips the peripheral registers at `0ff00..0ffff`. It reports the bytes that
change, and it extracts the known EEPROM settings cache. For the limits of the
snapshot and the layout of the cached settings, see the same diagnostic
document. To examine CPU addresses `10000..1ffff`, add `--window upper`. That
mode also makes six bracketed comparisons with lower RAM to look for possible
mirroring. It does not write test patterns.
## Recovered `main211.xmf` layout

| File range | Contents |
|---|---|
| `0x00000..0x001ff` | 512-byte product text header |
| `0x00200..0x1b5df` | 55,792 little-endian TMS320C51 words |
| `0x1b5e0..0xb7fff` | Intel 80186 supervisor plus erased flash padding |

The image is mapped at physical `0x40000`. The usual supervisor initializer is
`5b5e:0410` (physical `0x5b9f0`). The six bytes at `5b5e:0000` are not the
initializer. They are a fatal-error entry: they select error `0x0b` and jump to
the LED blinker at physical `0x5c74a`. This update payload does not contain the
fixed reset vector of the CPU. Thus, the harness starts at the recovered
supervisor initializer.

The DSP area is not one flat load. It is a program image in segments:

| File range | C51 program words | Role |
|---|---:|---|
| `0x002f0..0x0eea3` | `0000..75d9` | reset and boot block |
| `0x0eea4..0x101ff` | `de83..e830` | service overlay; entry at `de89` |
| `0x10200..0x1b5df` | `8000..d9ef` | resident high bank |

## Usage

All commands run through the `./courier` launcher. You do not install anything,
and you do not activate an environment. At the first use, the launcher makes
`.venv` adjacent to the repository and installs the project into it. After
that, it only starts the CLI.

```sh
./courier info main211.xmf
./courier extract main211.xmf extracted/main211
```

You can select the CPU execution. The non-JIT interpreter uses a guarded native
execution loop with a Python fallback. It has an 80186EB profile for analog
Courier images and a 386EX profile for I-Modem images:

```sh
./courier run main211.xmf --cpu-engine interpreter --instructions 1000 --summary
./courier isdn-run Ie030002.nac --cpu-engine interpreter --instructions 10000 --report
```

The interpreter shares the current peripheral, interrupt, flash and I/O models.
It does not need executable-memory/JIT permission. Native execution falls back
at device accesses, watched addresses and instructions outside its supported
subset. The Python reference still sets the instruction coverage. An
unsupported instruction stops the run with its opcode, profile and physical
address. `--report` enables ISDN profiling for each address. Usual runs use
bounded instruction-clock callbacks. To compare, set `COURIER_X86_NATIVE=0`.
This selects the Python reference.

To measure firmware execution, use `python tools/benchmark_x86.py Ie030002.nac`
or `python tools/benchmark_x86.py IDSDL302.ROM --with-dsp`. To identify native
fallback addresses, add `--profile-exits`. This option adds profiling overhead.
To use the reference engine, add `--python`. For measured workloads and the
remaining limits, see [interpreter performance](docs/interpreter-performance.md).

The launcher uses `uv` when `uv` is on `PATH`. If not, it falls back to `venv`
and `pip`. These settings change its behavior:

- `PYTHON=<interpreter>` selects the interpreter (3.10 or later) for the
  environment.
- `COURIER_EMU_VENV=<path>` moves the environment.
- `make clean-venv` deletes the environment.

You can run `./courier` from any directory. If you prefer to manage the
environment yourself, install the project with
`pip install -e '.[execute,disasm]'`. Then use `python3 -m courier_emu` in
place of `./courier` in all the commands below.

Execution uses the 16-bit x86 core of Unicorn and runs in an isolated child
process:

```sh
./courier run main211.xmf --instructions 250000
./courier run main211.xmf --instructions 1000000 --summary
./courier run main211.xmf --instructions 7000000 --with-dsp --at AT --summary
```

For Courier, the default DSP is C51. For a C53 image, select `--model c53`. Raw
MICA harnesses can use `NativeC5x.from_program(..., model="c53")`. For on-chip
maps and the GREG board configuration, see
[DSP memory models](docs/c5x-memory-models.md).

The C5x runner has no third-party runtime dependency. At the first use, it
builds with the C++17 compiler of the system:

```sh
./courier dsp-run main211.xmf
./courier dsp-run main211.xmf --trace 40
./courier dsp-run main211.xmf --port 0x50=0x1234
```

If you inject no supervisor events or line-side events, `main211.xmf` gets to a
deterministic 169-address service/polling cycle after 10,241 DSP instructions.
It then reports `status: stable-loop`. To make the run longer, use
`--instructions`. To examine a later instruction window, use `--trace-start`
with `--trace`. If this firmware path does not use an opcode form, that form
fails clearly with its PC. It does not silently make a guessed state.

By default, the harness accelerates these items: the known fatal-blinker
calibration loop, the initial 80186 timer-ready poll and the tick-delay helpers
of the firmware. It does this because a CPU-only core cannot supply their
hardware timing. If instruction-accurate delay counts are important, use
`--real-delays`.

To seed hardware input values, use repeatable `--port PORT=VALUE` arguments.
Port `0x40` is the first recovered board-control latch. The recovered DTE UART
model accepts `--at COMMAND` (this adds a carriage return) or literal
`--serial-input TEXT`. Its RX ISR is vector `0x0e`. Status/control is at port
`0x00`, data is at port `0x0a`, and the RX-ready bit is `0x08`. `serial_text`,
`serial_interrupts` and `serial_trace` report the terminal exchange that
results.

The modeled DTE attention detector accepts the `AT` prefix of the firmware in
all uppercase or all lowercase. It sends only the remaining command body to the
banked parser. The captured output has a limit of 64 KiB. If a diagnostic
command is larger than that limit, `serial_truncated` reports it.

The harness gives a command line to the firmware only from its
command-line-ready state. The state machine publishes that state as the
callback pointer at `0x02ac`:

1. `a8d9` collects a line, one character at a time.
2. The terminator advances the pointer to `a910`, which parses the line and
   prints the result.
3. The end-of-command path at `a8b1` clears the collector and returns to
   `a8d9`.

Bytes that arrive in the `a910` window go into a buffer that nothing parses.
The type-ahead flag of the firmware at `0x1cf2` would carry a line across. But
the DTE front-end sets this flag, and this harness replaces that front-end.
Thus, the harness waits for `a8d9`. For each line, it sets the collect flag at
`0x1cee` bit `0x40` again, exactly as it does one time at the main-loop
milestone. Because of this, a second and third command also get an answer.

## The parameter flash, and storing a profile

`AT&W` writes the working profile to the parameter store. That store is four
4 KiB sectors at physical `0xf8000`. Each sector ends in a 32-bit version at
`0xffa` and a CRC-16/CCITT at `0xffe`. The search at `0x7e07c` calculates the
checksum of all four sectors. It keeps the highest version that verifies.
`parameters.py` documents the layout, and the `parameters` subcommand builds a
sector.

The writer at `0x7dfa8` does not access the part directly. It calls the boot
block through `int 0x0a` with an ASCII service letter in `BL`:

| service | meaning |
|---|---|
| `E` (0x45) | erase the 4 KiB sector selected by `ES` |
| `W` (0x57) | program the word in `AX` at `ES:DI`, then advance `DI` |
| `S` (0x53) | firmware-update path, not modelled |
| `L` (0x4c) | block lock/select, not modelled |

An XMF update image carries only the application. Thus, in a run that you build
from one, that vector points at nothing, and `AT&W` stops at the first call.
When a part is attached, the harness answers `E` and `W`. This is what `AT&W`
needs, and no more. `S` and `L` still stop the run. The harness does not
continue on a guess.

```sh
./courier run main211.xmf --parameter-flash board.flash --at ATS0=7 --at 'AT&W'
./courier run main211.xmf --parameter-flash board.flash --at 'ATS0?'
```

The second run answers `007`. The harness makes the file in the erased state
(`0xff`). The blank check at `0x7e0e3` looks for this value. The harness
accepts a 4 KiB file as the first sector. The run reports a `flash` block with
the erase count, the program count, and the version and checksum validity of
each sector.

If you store many times, the firmware uses the sectors in sequence. To go back
to the start, it erases one sector. The writer of the firmware itself drives
all of this. `refused_bits` counts the bits that a program had to set and not
clear. It stays zero while the model and the firmware agree about the result of
an erase.

When a stored profile is attached, `ATI5` shows it, and not the page for an
empty store.

## The time base, and what waits on it

The supervisor arms countdowns and waits for them. For example, `ATI11` gives
itself 20 ticks at `0x62d68` before it prints an empty diagnostics page. But
nothing drives these countdowns. The chain that decrements them starts on
vector `0x0f`, and this firmware keeps that vector masked for the full run.
Thus, `ATI10` and `ATI11` stop before they are complete. All other firmware
timeouts wait forever.

`--tick-ms MS` lets you do experiments with that edge. But it obeys the mask.
Thus, now it delivers nothing, and the `ticks` count stays zero. This is
intentional: the board cannot accept an edge that the firmware disabled.

`--tick-source dsp` is the other candidate, and it is the useful one to run. It
paces the chain from the DSP frame interrupt, not from a period. Only this
arrangement keeps the two mutual watchdogs of the firmware quiet. These
watchdogs limit the legal ratio to between 1/25 and 3 ticks for each frame, and
1:1 is in that range. The option is still disabled by default, because 1:1 in
that range is a choice, not a measurement.

With this option, the diagnostics pages complete and the line-detector poller
runs. Also, the harness stops the forgery of the two counters that the poller
feeds. For the behavior of a linked pair in this condition, see "Two instances
on one line". `courier_firmware_analysis.md` has the evidence.

## Talking to it while it runs

`--at` queues commands before boot. `--console` attaches this terminal to the
DTE port for the full duration of the run. You can type commands and see the
answers of the modem. To detach, push `Ctrl-]`. With this option,
`--instructions` has no effective limit by default. Thus, the session ends when
you end it.

```sh
./courier run main211.xmf --console
./courier run main211.xmf --console --daa-line dial-tone --nvram board.eeprom
```

When stdout is a terminal, its bottom row shows the live lamps of the front
panel. The lit lamps are red, from `FRONT_PANEL_LEDS` in
`courier_emu/panel.py`. The output of the firmware scrolls above that row.

All data that the modem sends goes to stdout. The report of the run goes to
stderr. Thus, `--console > session.txt` captures exactly the output of the
firmware. You can also pipe the input. This is the same live path without a
terminal:

```sh
printf 'ATI3\rATI4\r' | ./courier run main211.xmf --console --instructions 9000000
```

`--serial-pty` does not attach this terminal. It makes the same port available
as a pty device, for each program that drives a serial modem:

```sh
./courier run main211.xmf --serial-pty
# serial console on /dev/ttys002
screen /dev/ttys002
```

The two options report a `console` block with these items: the count of bytes
in each direction, the bytes that a terminal dropped when it stopped to read,
and whether the far end closed. The harness polls typed bytes each 8,192
instructions. At the speed of this core, this is about a hundred times each
second. This speed is about the same as that of the real board.

Transmit bytes come from the feed of the integrated UART of the 80186. The
routine at `5b5e:184b` loads the byte in `AL`. It waits for transmit status bit
`0x08` at `0xff66`. Then it applies the framing transform at `5b5e:1913` and
writes the result to `0xff6a`. Its two wait edges (`5b5e:1874` and
`5b5e:1884`) do not loop in place. They branch back to the entry of the
routine. Thus, a byte goes through `0x5ce2b` one time for each spin, but the
routine accepts it only one time, at `0x5ce66`. Two results follow, and the
harness models the two:

- A CPU-only core never empties the transmit-holding register. Thus, status bit
  `0x08` stays clear and the routine spins forever. The modeled DTE reports
  that it is ready at the wait point. This replaces a missing device, not a
  calibrated delay. Thus, it applies with or without `--real-delays`.
- `5b5e:1913` calculates bit 7 again as an even-parity bit when `[0x26c6]` is
  zero. Then it applies the `[0x0936]` framing. In those framings, bit 7 carries
  no data. Thus, the capture reports the seven bits that a receiving DTE keeps.

With this model, the diagnostic commands show their real pages:

- `ATI` and `ATI0` return the product code.
- `ATI1` returns the ROM checksum.
- `ATI2` returns the result of the RAM test.
- `ATI3` returns the product banner.
- `ATI5` returns the stored-profile page.
- `ATI6` and `ATI11` return link diagnostics.
- `ATI7` returns the configuration profile.
- `ATI4` returns the full settings report:

```text
USRobotics Courier V.Everything Settings...

   B0  C1  E1  F1  L2  M1  Q0  V1  X1
   BAUD=9600   PARITY=E  WORDLEN=7
   DIAL=TONE   ON HOOK   TIMER
   ...
   S00=001  S01=000  S02=043  S03=013  S04=010  S05=008  S06=002  S07=060
   ...
OK
```

`ATI5` shows its "NVRAM Settings" page from the RAM shadow at `0x095c`, not
from the serial EEPROM. This agrees with the call-graph finding below. Commands
execute in the original firmware. `ATQ1` changes the quiet-mode profile byte
and suppresses the result code. `ATD123` and `ATA` go into the line-control
path. If no line is modeled, an originating call follows the `NO DIAL TONE`
path of the firmware. The DSP results keep completed `bootstraps` and
`transfer_commands` separate from runtime `mailbox_commands`. A
`mailbox_windows` histogram shows the runtime commands.

The line-audio endpoint is the external C51 I/O frame of the Courier ASIC. It
is separate from the two on-chip serial ports and from the 80186 download
window. The firmware reads the held ADC word two times from external I/O port
`0x54`, at program `0xb300` and `0xb304`. It copies the second read into the
active sample cell `0x007f`. The related `OUT` for each frame, at program
`0x8c24`, writes the DAC word to external port `0xb2e5`. The source of that
word is the output cell `0x00cb`.

`TRCV` (`0x30`) and `DRR` (`0x20`) are part of the ASIC/serial framing and the
address bookkeeping. They are not raw linear-PCM endpoints. After dial/answer
activation, supply and capture mono signed-16 little-endian words with this
command:

```sh
./courier run main211.xmf --instructions 9000000 --with-dsp \
  --dsp-rx-pcm line.s16le --dsp-tx-pcm reply.s16le --at ATDT123 --summary
```

`dsp_bridge.serial_port` reports these items: the register values, the access
counts, the last firmware PCs, the queued/consumed input frames and the
line-output counts. The board-to-DSP dial-command handoff is missing, so the
harness models it. The model recognizes the parsed `D` command of the firmware.
It drives 9.6 kHz DTMF frames through the real `OUT` instruction of the C51.
`ATDT123` makes bursts of 697+1209, 697+1336 and 697+1477 Hz. This shows
waveform transport in the two directions and tone output that you can repeat.
The internal command mailbox of the original datapump is not yet recovered.

The behavioral DAA can attach a disconnected, quiet, dial-tone or ringing line.
A dial-tone line does these steps:

1. It seizes the hook relay.
2. It supplies 350+440 Hz audio to the recovered ASIC ADC.
3. It qualifies the five-hit detector of the supervisor at RAM `0x0649`.
4. It removes the central-office tone.
5. It starts the parsed digits on the C51, which is already active.

`--daa-line` enables the DSP bridge automatically:

```sh
./courier run main211.xmf --instructions 9000000 \
  --daa-line dial-tone --at ATDT123 --summary
```

The original firmware then returns `OK`, not `NO DIAL TONE`. `dsp_bridge.daa`
reports the state of the hook, line, detector and generated samples. This DAA
model comes from the behavior of the firmware. It does not claim to identify
the physical line-interface IC. Busy/reorder tone and carrier negotiation are
not yet modeled.

To isolate the DTE online path from datapump completion, use the diagnostic
`--force-online` option. When the main loop starts, this option publishes the
modeled completion edge one time and sets the console to data mode:

```sh
./courier run main211.xmf --instructions 12000000 --with-dsp \
  --force-online --console
```

This option does not claim that modem training was successful. The result
reports `online_mode`, `data_rx_bytes` and `data_tx_bytes`. Use it to test
transparent post-CONNECT traffic while we continue to examine the real
completion callback of the ASIC.

### The silicon DAA as a register file

The harness models the line-interface chipset itself as registers, not as
behavior. This model is **on by default**, because the board has a DAA, and
without one `ATI7` reports a failure (below). `--no-daa-codec` disables it. The
model also disables itself for a flash ROM, because a flash ROM has no
separable C51 payload for the DSP bridge that the codec uses. The model adds
about 20% to the wall time of a run. This is because it starts the native C51
bridge on runs that otherwise do not need it.

The board has an Si3021 and an Si3014. `docs/SI3038.PDF` is the AC'97 relative
of that pair. It is the only published register map here. Thus, the model uses
its addresses for the shared line-side fields.

That attribution applies to the **line interface**. The part on the serial
port of the DSP is a different part: a TI `TLC320AC0x`. We identified it from
the board, and the C51 firmware confirms it. The firmware uses bit 0 of each
transmitted word to request the secondary frame that carries a control
register. This is the AC0x protocol. See
[what is actually on the board](docs/board-parts.md). Thus, `CodecBringUp`,
which runs an `SI3038` register sequence, models a part that the DSP does not
talk to. The line-side attribution does not change.

```sh
./courier run main211.xmf --instructions 20000000 \
  --daa-line dial-tone --at ATA --summary
```

`dsp_bridge.codec` then reports the full register file, the readiness byte and
the assembled line status:

```
"steps": ["register-reset", "sample-rate", "power-up", "ready",
          "gpio", "levels", "line-interface"],
"polls": 3,
"readiness": "0x0f", "link_up": true,
"loop_current_ma": 25, "loop_current_sense": 4,
"line_status": "0x0050"          FDT set, LCS[3:0] = 4
```

The seven steps are the initialization procedure of the datasheet, with its
readiness poll. Nothing in the Courier firmware does these steps. The 80186
writes ports `0x40`..`0x4e` thousands of times and never reads them. The only
external reads of the C51 are the host mailbox window and the line ADC. Thus,
neither processor can see the readiness byte that step 4 waits for. The
sequence belongs to the interposed ASIC, as AN16 section 1.3 describes.
`CodecBringUp` replaces it, with one service frame each 100 ms.

The firmware has no register-level read path. Thus, the harness drives the
model and does not poll it:

- Hook state and line state come from the behavioral DAA.
- Ring bursts come from the ring source.
- Loop-current sense, ring detect, frame lock and the country settings come
  from the registers.

`--daa-codec-line` selects the line for which the part is strapped. This sets
whether readiness reads `0x0f` or `0x33`. `--daa-codec-rate` programs register
`40h`. It rounds to the nearest rate that the PLL has.

The firmware does read one item: the identity of the DAA. `ATI7` prints it:

```sh
./courier run main211.xmf --instructions 14000000 --at ATI7
```

```
Product ID             00345302        with --no-daa-codec: XX345302
DAA rev                0004            with --no-daa-codec: 0000
```

The receive table of the supervisor stores the data word of mailbox tag `0x7b`
at `[0x287]`. `ATI7` prints that word as `DAA rev`. When the word is zero, the
self-test at `0x77eda` adds `" : DAA Failure (zero is Invalid)"`. If the word is
4, `0x8369d` branches to print product ID `00345302`, not the placeholder
`XX345302`. Before, nothing made that message. Thus, the firmware reported a DAA
that it considered invalid. This is why the codec is on by default and not
optional.

The report goes out on the first DSP download, because a real part identifies
itself at power-up, not at the dial/answer boundary. `--daa-codec-revision`
changes the value, and 0 causes the failure path again. The value 4 comes from
the product-ID branch of the firmware. We did not measure it on a part.

## Complete flash ROM images

`rom-info` describes a full flash part, not an update payload:

```sh
./courier rom-info IDSDL302.ROM
```

An XMF carries only the application. Thus, its location is a modelling choice.
A ROM ends with the 80186 reset vector. The stub there programs the chip select
that decodes the ROM before it jumps. Thus, the image sets its own location.
For the 1998 Courier V.Everything external ROM, this gives these locations:

- Flash at `0x80000..0xffc00`
- 128 KiB of RAM at `0x00000..0x20000`
- The peripheral control block, relocated into memory at `0x0ff00`. This is the
  window that this harness already hooks.

The ROM also has the ~6 KiB boot block above the application. An update image
never replaces this block. The block contains these items:

- The hardware setup tables
- The copy of itself to physical zero
- The power-on read of the settings EEPROM
- The CRC of the full flash
- A second copy of the SDL loader

`run` also accepts a ROM, and boots it from its reset vector:

```sh
./courier run IDSDL302.ROM --instructions 40000000 --int1-after 7
```

The harness models the peripheral timers from the instruction clock. The model
includes these items:

- The enable gate
- The rule that a zero compare is the full range
- Single-shot and continuous modes
- The sticky max-count bit
- The mask side of the interrupt controller

This model moves the ROM past its timer self-test at `0x80444`. The ROM then
gets to a tick wait. This firmware calibrates the period of that wait from an
external INT1 edge, not only from a timer. `--int1-after` supplies that edge.
`courier_firmware_analysis.md` has the full account. This includes where that
sequence still stops, the confirmation of the latch driver across builds, and
all the option switches.

## ISDN Courier XMP images

`Ie030002.xmp` is an ISDN Courier update payload. It is very different from an
XMF: it has no product text header, and its body is obfuscated.

```sh
./courier xmp-info Ie030002.xmp
./courier extract Ie030002.xmp extracted/Ie030002
```

| File range | Contents |
|---|---|
| `0x00000..0x0007f` | 128-byte header: `USR XMP\0` magic, three small fields, and a 0x70-byte table |
| `0x00080..0xb807f` | 0xb8000-byte payload, every byte XOR `0x45` |

You can find the key from the image without code analysis. Erased flash is
still most of the payload, and the pad byte reads `0xba`. `0xff ^ 0xba` is
`0x45`. When you decode with this key, `0xff` becomes the most common byte
again. The result contains the VRTX kernel banner
(`Copyright 1988, Ready Systems`) and the ISDN rate-adaptation strings
(`SET_V110_ENTRY`, `V110_ATO`).

The decoded payload has three programmed spans. The last span is a two-byte
word at the top of flash:

| Payload range | Size |
|---|---|
| `0x00000..0x5d320` | 381,728 |
| `0x64000..0xaab0c` | 289,548 |
| `0xb7ffe..0xb8000` | 2 |

It is an 80386 image. Payload offset `0x38` shows this: there, the code clears
`dr0..dr3` and `dr7`. The 80186 supervisor does not have these registers. The
code near this offset programs a linear address into `dr0`. It sets the local
and global enable bits in `dr7`. It installs its own INT1 (`#DB`) handler at
`4000:0148`. Thus, the firmware uses hardware breakpoints as a usual runtime
mechanism. This is vector 1. It is different from the `INT1_VECTOR = 13` pin
interrupt of the 80186 in `timers.py`.

Nothing here executes yet. The harness loads the container and the decoded
body. It does not model the board. The decode shows two important items:

- Debug registers. Unicorn does not deliver `#DB` from `dr0..3` that the guest
  programs. Thus, the harness must match breakpoints itself.
- The 0x70-byte header table at offset `0x10` is plaintext, not obfuscated. It
  has a clear structure: some 16-bit values occur many times in it. But its
  layout is not recovered. Thus, `xmp-info` reports it verbatim as
  `header_table_undecoded`. It does not invent fields for it.

The load base is a modelling choice, as it is for an XMF. `FLASH_PHYSICAL_BASE`
is `0x40000`, because the boot code installs its INT1 handler in segment
`0x4000`. The `load_hint` field of the header reads `0x40`. This agrees with
that base in units of 4 KiB, but nothing in the image confirms the unit.

The decoded payload has no protected-mode entry. It has no `lgdt`, `lidt`,
`lmsw` or `mov cr`. This is 386 code that runs in real mode. It uses 32-bit
registers, `0x66`/`0x67` prefixes and the debug registers.

## ISDN Courier NAC images

`Ie030002.nac` is the same firmware in a different container, and it is not
obfuscated. It is **Intel HEX with the ASCII removed**. Each record is a length
byte, a big-endian 16-bit address, a type byte, and that quantity of data
bytes. The big-endian address is the clue. All other data in these images is
little-endian, but Intel HEX writes its address big-endian, also on x86.

```sh
./courier nac-info Ie030002.nac
./courier extract Ie030002.nac extracted/Ie030002
```

| File range | Contents |
|---|---|
| `0x00000..0x0001f` | 32-byte header |
| `0x00020..0xcd1a6` | Binary Intel HEX record stream |
| `0xcd1a7..0xcd1a8` | Two trailing bytes, `e4 a0` |

Header fields:

| Offset | Contents |
|---|---|
| `0x03` | `u32` record-stream length — exactly file size minus header minus trailer |
| `0x08` | Version triple `03 00 02`, matching the `Ie030002` file name: 3.0.2 |
| `0x0f` | Product tag `IE(`, the same tag the `.sdl` loader carries |

The record types are the Intel HEX types:

| Type | Count | Meaning |
|---|---:|---|
| `0x00` | 42,023 | Data |
| `0x02` | 197 | Extended segment address, big-endian, scaled by 16 |
| `0x03` | 1 | Start segment address, `0ce0:0000` |
| `0x01` | 1 | End of file |

ASCII Intel HEX has a checksum byte for each record, but this format does not.
A parse without a checksum uses the stream exactly, from the end of the header
to the EOF record.

The first record of the stream is a type `0x02` that sets segment `0x4000`.
Thus, the image sets its own location at physical `0x40000`. For a NAC, the
harness does not have to assume a base, as it must for an XMF. This is an
independent confirmation of the base that the XMP section above found from the
INT1 handler of the boot code.

The two containers agree exactly. When you flatten the 42,023 data records of
the NAC, you get a `0xb8000` image at `0x40000`. This image is identical, byte
for byte, to the XOR-decoded XMP payload. The NAC never writes 82,879 bytes,
and these are exactly the bytes that read as erased flash in the XMP. Two
containers with independent encodings give the same image. This is the
strongest check that we have on the two decodes. When you validate a new
image, check this again with `nac-info` against the XMP decode.

This item is not recovered: the two trailing bytes `e4 a0`. They are not a byte
sum of the record stream. They do not match the common CRC-16s (CCITT-FALSE,
XMODEM, ARC, MODBUS, KERMIT, GENIBUS) over the stream or over the full file.
Thus, `nac-info` reports them verbatim as `trailer_undecoded`.

The start segment address `0ce0:0000` is physical `0xce00`. This is RAM far
below the flash. The entry after the boot block relocates itself. This agrees
with the code at payload `0x300`, which loads `0x0ce0` into a segment register.

## Board latches, front panel, and NVRAM

All board outputs go through one read-modify-write latch driver. We recovered
it at these physical addresses: `0x5e2b0` (set), `0x5e2e5` (clear), `0x5e335`
(read an input port) and `0x5e294` (read the shadow). Callers pass
`AX = mask << 8 | index`. The index table at `0x5e31c` and the shadow bytes
seeded at `0x5e26c` give this map:

| index | port | shadow | contents |
|---:|---|---|---|
| 0 | `0x10` | `0x064d` | hook relay, settings-EEPROM bit-bang pins |
| 1 | `0x12` | `0x064e` | indicators, error-blink code byte |
| 2 | `0x14` | `0x064f` | indicators, board-ID strap drives |
| 3 | `0x12` | `0x0650` | second `0x12` signal group |

The two entry points have special cases for `AX == 0x0408` and
`AX == [0x065c]`. The set path at `0x5e2b4` jumps into the clear body. The
clear path at `0x5e2e9` jumps into the set body. `0x0408` is latch 0 bit
`0x04`. Thus, the firmware **asserts the hook relay when it drives its latch
bit low**. The firmware sets latch 0 bit `0x01` high over exactly the same
window (`0x5db4e` on seizure, `0x5e197` on release).

Each run now reports a `panel` block with these items: the current latch
values, the asserted state of each named line, `off_hook` and a change trace:

```text
i=2191703 port=0x10 value=0xf2 pc=0x5e317 +hook-relay
i=2191740 port=0x10 value=0xf3 pc=0x5e2e0 +off-hook-aux
i=2291289 port=0x10 value=0xf2 pc=0x5e317 -off-hook-aux
i=2291366 port=0x10 value=0xf6 pc=0x5e2e0 -hook-relay
```

The harness names a bit only where the firmware shows the function of the
line. Two runtime DTE lines now also have names:

- `0x5de57` drives latch 2 bits `0x01` and `0x80` as one pair. It clears them
  together at `0x5de65`/`0x5de6b` when the `&C` setting at `[0x09e9]` is zero.
  If not, it sets them together at `0x5de7d`/`0x5de83`. `&C0` is "carrier detect
  always on". Thus, the cleared level is the asserted level, and these bits are
  the carrier-detect pair. It is not known which bit is the DTE pin and which is
  the front-panel lamp. Thus, the harness reports them as `carrier-detect-a`
  and `carrier-detect-b`.
- Input port `0x12` bit `0x40` is DTR. `0x5e375` samples it. `0x5e395` and
  `0x5e3b5` poll it again. The two transitions post supervisor events 6 and 7.
  When S14 bit 0 is set, `0x5e887` changes a low reading into event 10.

`courier_emu/panel.py` reports the remaining indicator bits on `0x12` and
`0x14` with placeholder names and the addresses of their driver wrappers. A
physical reference is necessary to map them to the legends of the front panel.

### Option switches

The option switches of the board are input bits on the same latch ports. The
firmware samples them with the same `mov ax, mask << 8 | index; call 0x2d4a`
form that the straps use. It reads six switches while it builds the profile at
`0x63d31..0x63ec2`. It reads the carrier-detect switch separately at
`0x5e3cf`. The firmware reads a **closed** switch as a low bit, so the sense is
inverted. Each switch also records itself in the shadow word at `[0x0659]`.

We confirmed each row below with a run of `ATI4` with only that input bit pulled
low. Then we compared the profile that the firmware prints. Thus, the effect
column is observed, not inferred:

| switch | port/bit | closed behaviour | observed |
|---|---|---|---|
| `result-codes` | `0x14` `0x20` | `0x63e2e` clears the quiet setting at `[0x092f]` | `Q0` |
| `quiet-answer` | `0x12` `0x08` | `0x63e54` sets `[0x092f]` to 2 | `Q2` |
| `quiet-answer-alt` | `0x12` `0x80` | `0x63e75` sets `[0x092f]` to 2 | none — gated on capability bits `0x08` and `0x20` at `0x63e40` |
| `numeric-results` | `0x10` `0x02` | `0x63e17` leaves `[0x092e]` clear | `V0` |
| `no-echo` | `0x12` `0x10` | `0x63e93` leaves `[0x092d]` clear | `E0` |
| `dtr-override` | `0x12` `0x20` | `0x63d48` leaves S14 at `[0x094e]` clear | `S14=000` |
| `carrier-detect-override` | `0x14` `0x04` | `0x5e3e1` clears `[0x09e9]` | `&C0` |
| `no-auto-answer` | `0x14` `0x10` | `0x63eb5` leaves S0 at `[0x08de]` clear | `S00=000` |

Three of these names are corrections. `[0x08de]` is S0, not a profile source.
Thus, that switch is the auto-answer switch, and its closed position stops the
modem from answering. The switches that had the names `verbose` and `echo` both
*disable* those settings when they are closed. The names now tell what the
switch does when you close it. A physical unit is necessary to map them to the
switch numbers on the case.

`--dip` closes a switch, and you can use it many times. The first use replaces
the default set. `--dip none` leaves all switches open. By default,
`result-codes` is closed, because a DTE that is directly attached needs result
codes. When this switch is open, the modem is really silent. This is the real
behavior. Before, the harness hid it with a direct write to `[0x092f]`:

```sh
./courier run main211.xmf --instructions 4000000 --at AT --dip none
```

### Dedicated-line operation

On a dedicated line, no DTE holds DTR high and no call setup occurs. Thus, the
modem must ignore DTR and keep carrier detect on. `--dip-preset
dedicated-line` closes `result-codes`, `dtr-override` and
`carrier-detect-override`. It leaves `no-auto-answer` open. Thus, S0 keeps its
flash default of 1, and the modem answers on the first ring:

```sh
./courier run main211.xmf --instructions 12000000 \
  --dip-preset dedicated-line --at ATI4
```

The firmware confirms all three settings in its own profile dump: `&C0`,
`S14=000` and `S00=001`.

### Ring detection

The answer machine at `0x70fb4` polls input port `0x14` bit `0x02` with a direct
`in al, 0x14`, and every state in it waits on an edge of that bit, so a line
that never changes level parks it in its first state forever. That bit is now
modelled: an idle line is not ringing, and `--ring` drives it with a cadence.

```sh
./courier run main211.xmf --instructions 40000000 \
  --ring --at 'AT#CID=1' --summary
```

The harness has no wall clock, so the cadence is converted from milliseconds
through the instruction count. `0x70fe0` accepts a burst once the tick counter
at `[0x1d50]` reaches the country minimum at `[0x1f5c]`, which this build loads
with 180.

That counter was once read as the calibration for the conversion: assume the
burst reaching 180 is a 2 s North American ring, and one firmware tick is 10 ms
and the instruction clock 1,111 per millisecond. Both figures are withdrawn.
The tick is 5 ms, measured from the timer 0 compare each build programs on its
own crystal, so 180 ticks is a 900 ms minimum qualification rather than a whole
burst - and the derivation was circular anyway, since `machine.py` synthesizes
the tick itself at `tick_ms * INSTRUCTIONS_PER_MS`. The instruction clock is
4,348 per millisecond, from the codec's own sample count. See [Hardware time
base and audio path](docs/hardware-timebase-and-audio-path.md).

With that cadence the answer machine qualifies bursts (`0x70fe9`), raises the
ring-indicate line (`0x70ff0`), and posts its ring message (`0x71026`) into the
supervisor event queue at `0x02e0`. Two gates matter there:

- `[0x094e]` is `#CID`, expanded from packed-config byte 11 of the parameter
  sector, and both ring message sites skip the post when it is zero. `AT#CID=1`
  enables them.
- `[0x0287]` bit `0x10` gates the second ring path, and it reads zero here.

What does **not** yet happen is the answer itself: the queued ring events are
never acted on, with or without `--with-dsp`, so no `RING` reaches the DTE and
the hook relay stays released. The consumer of that queue is the next thing to
recover.

### Answering

`ATA` reaches the same `0x5dbe7` line-detector wait that `ATD` does. Since an
answering seizure has no dial tone to find, the DAA qualifies detector byte
`[0x0649]` on a connected line for `answer` and keeps requiring dial tone for
`originate`:

```sh
./courier run main211.xmf --instructions 40000000 \
  --at ATA --daa-line quiet --summary
```

That turns `NO DIAL TONE` into `NO CARRIER`, which is the correct answer to
answering into silence: the line is seized and qualified, and training then
fails for the reason the SIP section describes. Treating `[0x0649]` as the
line-side detector rather than a dial-tone-only counter is an inference from the
shared wait, not something the image states.

### Board identification straps

The scan at `0x5bfc6` identifies the board by driving four latch lines low one
at a time (latch 1 bit `0x02`, latch 2 bits `0x40`, `0x10`, `0x20`) and shifting
input port `0x14` bit `0x08` into a four-bit code. `0x5c051` looks that code up
in the table at `0x5c06b` and `0x5c05c` stores the result as the board
capability byte at `0x0a02`. Two capability bits are pinned down: `0x08` is
"settings EEPROM fitted", tested by every NVRAM path, and `0x40` sends `0x5bb0f`
straight to the fatal blinker.

| code | capability | | code | capability |
|---:|---|---|---:|---|
| 2 | `0x29` | | 9 | `0x28` |
| 5 | `0x14` | | 12 | `0x28` |
| 7 | `0x22` | | 13 | `0x22` |

Codes 11 and 14 map to `0x42` and `0x48`, which carry the fatal bit; every other
code is an empty table entry and `0x5c064` stores zero. `--board-id` drives the
straps and rejects the codes the firmware cannot run on. It defaults to 2, the
lowest code describing a board with an EEPROM and no fatal fault; `none` leaves
the lines floating, which the firmware reads as no board at all.

Which of 2, 9, and 12 a given board revision actually straps is not recoverable
from the image — they differ only in capability bit `0x01`, whose meaning is not
established. The default is a constrained inference, not a verified board ID.

Leaving the straps floating is not a state real hardware can be in, and the
firmware treats it as a fault. Two visible consequences:

- `0x667cb` maps a zero or `0xff` capability byte straight to result code 4, so
  `ATI1`, `ATI2`, `ATI3`, `ATI7`, `ATZ` and `ATS30?` answered correctly and then
  reported `ERROR`.
- `0x82ea4` picks the product code from capability bit `0x08`: a board with an
  EEPROM answers `ATI` with `3368`, one without answers `3368A`.

The settings store is a 93C66-class Microwire EEPROM (256 x 16) bit-banged on
latch 0. The driver is at `0x5ccc0..0x5cdf9`:

| routine | role |
|---|---|
| `5b5e:16e0` | read word; `[0x8d2]` = address, result in `[0x8d3]` |
| `5b5e:1746` | write word; `[0x8cf]` = address, `[0x8d0]` = data, EWEN/EWDS bracketed |
| `5b5e:17c6` | build and clock the twelve-bit command frame |
| `5b5e:17d2` | shift bits most-significant first |
| `5b5e:1801` | presence poll; input port `0x10` bit `0x08` must read high |

`5b5e:17c6` forms `bx = ((opcode & 3) | 4) << 8 | address` and rotates it left by
four before clocking twelve bits, which is one pad bit, the start bit, two opcode
bits, and an eight-bit address. Latch bits are `0x20` chip select, `0x40` clock,
`0x10` data in on write and data out on read.

Attach a persistent image with `--nvram`; it is created blank (all ones, like an
unprogrammed part) when the file does not exist and written back after the run:

```sh
./courier run main211.xmf --instructions 7000000 \
  --at AT --nvram settings.nv --summary
```

For a deterministic `IDSDL302.ROM` boot, the recovered six-record settings
cache can instead be attached in memory, together with the `+S` register
defaults that `AT+SF` loads - without them the DSP dials at zero level, as the
board did. This leaves every other EEPROM word erased, and does not alter the
blank `--nvram` behavior:

```sh
./courier run IDSDL302.ROM --instructions 60000000 \
  --tick-ms 10 --nvram-fixture idsl302 --at AT --summary
```

The 20 MHz 302/403 ROM serial adapter runs the firmware's attention detector,
parser, and UART transmit path. See [ROM serial execution](docs/rom-serial-adapter.md)
for the tested board settings, captured 403 command, and autobaud limitations.

The fixture reverses all three byte encodings used for each redundant record;
it is mutually exclusive with a persistent `--nvram` image.

`nvram` in the result reports reads, writes, erases, the write-enable latch, the
programmed words, and a command trace.

### Why the EEPROM stays untouched at boot

`reads` and `writes` both stay at zero through boot and plain command mode. That
is the firmware's own behaviour, not a gap in the device model. Three separate
findings account for it.

**There is no boot-time NVRAM profile load.** All eleven call sites for the two
driver entries live in banked segment `0x81b8` (`0x8374x`, `0x8386x`, `0x838b9`,
`0x84de8`), and they are command handlers: a word-by-word diagnostic dump that
prints through the resident character-output helpers, a six-word store whose last
word is a CRC-8 over the previous four, and a config write at `0x84dc7` that
parses a literal `=PW` and programs word 0 to `0x4000` or `0x0000`. None of them
is on the reset path. The working profile at `0x08de..0x095b` is instead filled
at boot from a 77-byte flash default table copied at `0x63b72`, and the saved
profile at `0x095c..0x09d9` is a plain RAM shadow (`81b8:35ee` saves, `81b8:3601`
restores and re-applies).

**The diagnostic and store paths are gated on `[0x0a02] bit 3.`** That byte is the
board capability code produced by the strap scan at `0x5bfc6`, which drives four
lines (latch 1 bit `0x02`, latch 2 bits `0x40`, `0x10`, `0x20`) low one at a time
and shifts input port `0x14` bit `0x08` into a four-bit index, then looks the
index up in the table at `0x5c06b`. With that input floating high the index is
`15`, the table entry is `0x00`, and `0x5c064` stores `[0x0a02] = 0`. Codes `2`,
`9`, `12`, and `14` yield `0x29`, `0x28`, `0x28`, and `0x48`, all of which carry
bit 3. The boot gate at `0x5bbb5` branches on the same bit.

**The persistent configuration lives in a separate parameter flash, not in the
XMF image.** The routine at `0x7e07c` — reached by the harness's `startup-crc`
milestone — scans four 4 KiB blocks from segment `0xf800` (physical
`0xf8000..0xfbfff`), checksums bytes `0x000..0xffd` into `[0x06fc]`, compares
against the word at `0xffe`, and keeps the block with the highest 32-bit version
at `0xffa`. `main211.xmf` maps at `0x40000..0xb7fff`, so that region is empty
here, `ES` comes back zero, and `0x7dffa` skips the whole unpack. Bytes 0..4 of a
valid block become `[0x0a06..0x0a0a]`, and byte 4 becomes **`[0x0a03]`** — the
capability byte that gates the profile restore at `0x6014f` and selects whether
`0x63b6d` loads defaults into the stored profile at `0x095d` instead of the
working copy at `0x08df`.

Synthesising a block confirms the mechanism: writing a 4 KiB record at `0xf8000`
with a matching checksum makes the search return `es = 0xf800` and load
`[0x0a03]`. Reaching command mode from there needs more of the parameter block
filled in than a stub provides, so the harness does not ship one; recovering a
real parameter sector from hardware is what that path needs.

## Parameter sector

The persistent configuration lives in a 16 KiB parameter flash searched at
physical `0xf8000`, which the XMF update image does not carry. The search at
`0x7e07c` walks four 4 KiB sectors, checksums bytes `0x000..0xffd`, compares
against the word at `0xffe`, and keeps the sector with the highest 32-bit
version at `0xffa`. The winner is copied to `0x0a06` one byte for one, so sector
offset *i* lands at RAM `0x0a06 + i`:

| offset | RAM | role |
|---|---|---|
| `0x00` | `0x0a06` | flags; bit 3 keeps `[0x0a03]` clear |
| `0x01..0x06` | `0x0a07..0x0a0c` | country, features, type2, type1, unused2, unused1 |
| `0x11..0x1c` | `0x0a17..0x0a22` | serial number, 12 ASCII characters |
| `0x1d..0x2f` | `0x0a23..0x0a35` | packed config, expanded at `0x64044` |
| `0x30..0x61` | `0x0a36..0x0a67` | working-profile image, scattered at `0x6406f` |
| `0xffa` | | 32-bit version |
| `0xffe` | | CRC-16/CCITT over `0x000..0xffd` |

The packed config is expanded through the `(shift, mask)` table at `0x63f8d`
into the 36 profile bytes `0x0932..0x0955`; the profile image is scattered to
`0x08de` plus the 50 offsets listed at `0x63fd6`. The serial number is read as
nine characters at `0x0a17` plus three at `0x0a20` (`0x835bb`), and `0x77bb9`
treats four `0xffff` words as no serial fitted.

Dumping the real part is not practical, so `parameters` synthesises a sector the
firmware accepts. It carries the firmware's own power-on defaults for the packed
config and profile image, so only the fields you set change:

```sh
./courier parameters params.bin --serial 12345678 \
  --feature hst --feature fax --feature terbo --feature v34 --feature v90
./courier run main211.xmf --instructions 8000000 \
  --parameter-sector params.bin --at ATY14
```

That reproduces the configuration dump reported for a fully featured unit, and
`ATI7` renders the full profile including the serial number:

```text
000,000,030,007,031,000

Product type           US/Canada Internal
Product ID             XX345302
Options                HST,V32bis,Terbo,VFC,V34+,V90,V92
Clock Freq             25 Mhz
Serial Number          12345678
```

The sector's first byte gates each unpacked field, applying it when the bit is
clear, and `--flags` sets it. Bit 3 decides whether type1 reaches `[0x0a03]`,
and `0x8339f` tests bit `0x04` of that byte before the `ATY15` case is even
reachable — so the default `0x08` is why that command answers `ERROR`. A sector
with bit 3 clear and type1 carrying `0x04` makes it print the factory switch
page instead, which reports all ten option switches as the firmware reads them:

```sh
./courier parameters params.bin --serial 12345678 --flags 0
./courier run main211.xmf --instructions 9000000 \
  --parameter-sector params.bin --at ATY15
```

```text
CURRENT DIPSWITCH SETTINGS
DIPSWITCH #1   ON
DIPSWITCH #2   OFF
DIPSWITCH #3   ON
...
```

Feature bit 4 (value 16) is labelled x2 in archived notes for older Courier
firmware, but on this 2002 build it gates V.90: `0x77d47` uses it to append
`,V90` to the options list, and `0x82e7d` uses it to select the `5608` product
code instead of `3368`. The options table does hold an `x2` string at
`733c:49d6`, but nothing in the image ever loads it, so **this firmware cannot
report x2 at all**.

The board identification straps select the enclosure `ATI7` reports, which is a
useful cross-check against a physical unit:

| `--board-id` | capability | `ATI7` product type |
|---:|---|---|
| 2, 9, 12 | `0x29`, `0x28` | Internal |
| 5 | `0x14` | Rackmount |
| 7, 13 | `0x22` | External |

Note the tension with the default: codes 2/9/12 carry capability bit `0x08`, the
settings-EEPROM bit, but report Internal, while the External codes do not carry
it. Capability `0x22` is also the one value `0x667cb` special-cases as always
returning `OK`. An external unit is therefore likely `--board-id 7`, which also
changes the product code to the `A` suffixed form (`5608A`/`3368A`). Running
`ATI` on real hardware settles it.

## A modeled line: the digital ATA

`--exchange` puts a central office on the subscriber loop instead of a fixed
`--daa-line` state. It is the network side of one line, entirely in the codec
sample stream - no loop current, no hybrid, no two-wire pair, which is what
makes it digital rather than an analog terminal adapter. It watches the hook,
plays the tones the loop would carry, **decodes the dialed number out of the
audio the modem transmits**, and routes the call:

```sh
./courier run main211.xmf --exchange \
  --exchange-number 5551212=answer --at "ATDT5551212" \
  --instructions 120000000
```

```json
"exchange": {
  "state": "connected", "dialed": "5551212", "digits_decoded": "5551212",
  "outcome": "answer", "rings_delivered": 2, "calls": 2
}
```

Nothing hands it that number. The supervisor qualifies its line detector on the
exchange's 350+440 Hz dial tone, the C51 puts DTMF on the line, and a Goertzel
receiver in the exchange reads it back off the transmit stream. That is the
difference from `--daa-line dial-tone`, which supplies a line state the harness
chose and removes dial tone as soon as the model decides dialing has started -
the gap recorded in `courier_firmware_analysis.md` under "What the dial
sequencer is waiting on".

Routing the same number to `busy` instead stops the call at the tone, with no
`CONNECT`: `state=busy outcome=busy connected=false`. The firmware does not
print `BUSY` for it - call-progress tone detection is the DSP's, and no run has
reached it - so what the exchange proves here is the line, not the report.

The states and what the loop carries in each:

| state | line | leaves on |
|---|---|---|
| `idle` | silence, on hook | seizure |
| `dial-tone` | 350+440 Hz continuous | first digit, or 16 s to reorder |
| `collecting` | silence | `#`, a directory match, or 4 s interdigit |
| `routing` | silence, 500 ms | the outcome for the number |
| `ringback` | 440+480 Hz, 2 s on / 4 s off | answer after N rings |
| `busy` | 480+620 Hz, 500/500 | hang up |
| `reorder` | 480+620 Hz, 250/250 | hang up |
| `answer-tone` | 2100 Hz | 3 s, then connected |
| `connected` | whatever `peer_audio` supplies, else silence | release |
| `ringing` | ring cadence toward the modem | the modem going off hook |

`--exchange-number NUMBER=OUTCOME` routes one number to `answer`, `busy`,
`reorder` or `no-answer`; `--exchange-outcome` sets what an unrouted number
gets, `--exchange-answer-after` the ringback cycles before pickup, and
`--exchange-answer-tone` how long 2100 Hz runs before the call is handed on.
`LineExchange.ring()` offers an incoming call, which drives the codec's ring
detectors directly rather than through `--ring`.

### The firmware places this call

With `--exchange` there is no DTE-level dial stand-in left. `arm_dial_tones`
returns without reading the command, and every step below is the supervisor's
own, running against the modeled line:

| step | what the firmware does | where |
|---|---|---|
| parse | reads the dial string out of its own command buffer | `0x82652` |
| seize | drives the hook relay, board latch 0 bit `0x04`, low | `0x5e317` |
| qualify | counts its own five detector hits before accepting dial tone | `0x5dbee` |
| encode | folds each character to a keypad index | `0x6353c` |
| dial | sends `0x16:0000`, the digit on tag `0x13`, `0x16:0000` | `0x63553` |
| time | holds each tone and gap on its own `[0x161]` countdown | `0x82342` |

`--exchange` therefore implies `--tick-source dsp`: the dial-tone wait, the
tone duration and the interdigit gap all count on the supervisor's countdown
chain, and unpaced the harness has to stand in for every one of them, which is
the arrangement the exchange exists to replace. The line detector is modeled
here rather than executed because the native core does not yet run the
recovered DSP detector path end to end. The fallback answers the `0x7c` poll
with a low-band reading while the loop carries tone, and the supervisor counts
its own five hits.

**Nothing renders the digits.** `dsp_bridge.exchange.dialed` - what the line
actually heard - stays empty while `ATDT5551212` is dialed. This was recorded
here as "the tone generator is the ASIC's", and that is wrong: the three
constant lanes the dial path sends alongside each digit, `0x19`, `0x1a` and
`0x1b`, are host-write tags whose handlers store into **DSP data memory** at
`0x03ad`, `0x0392` and `0x03f1`. The tone parameters go to the C51, so the
synthesiser is the datapump's, and what is missing is the harness reaching that
code rather than an unmodelled generator elsewhere. See
[what the ASIC does](docs/what-the-asic-does.md). What the run does report is the sequence
of commands the supervisor issued:

```text
0016:0000  0013:0005  0016:0000   ...   x7   ->  commanded 5551212
```

each about 600 ms apart on the firmware's own timers. The exchange therefore
hears silence, times out, and returns reorder. That is the honest state: the
firmware places the call, and the board it is talking to cannot yet put a tone
on the line.

One bug had to be fixed for any of it to run. The receive handler at `0x6ad6e`
takes a message tag from ports `0x58`/`0x5a` and then its word from
`0x5e`/`0x5c`, and the bridge was serving the C51 status latch on those two
ports even while a reply stood queued. The detector consumer at `0x5e4c4` read
`0xffff` for a reading the bridge had already answered, counted it as
out-of-band, and hung up. Queued replies now own the data lanes.

### What the C51 puts on the line

The core has no tone generator of its own. It once carried hand-written
`sin()` in C++ - a DTMF pair generator, a 1300 Hz calling indicator and a
2100 Hz ANSam approximation - which substituted for the datapump's DAC output
and *discarded* its accumulation to make room. That stand-in is gone, along
with `set_dtmf_digits` and `set_synthetic_line`. The line now carries what the
C51 computes through its AC01, and only that: on 3.0.13 that is the firmware's
own DTMF, which the modeled exchange decodes as the dialed number
(`artifacts/dtmf-emulator-302-01`).

An answered call reaches the datapump: ring the loop, answer it, and the
recovered call overlay is entered and executes. What it writes is not audio.
The frame ISR at `0x0228` keeps a 32-bit phase accumulator in `@7c`/`@7d`
(`0xfffc`/`0xfffd` at DP `0x1ff`), and reading `0xfffd` as the DAC - which the
core did - yields a linear ramp with a constant step, which measures as
broadband noise. The word the ISR computes from it goes out through `@7a` to
`0xffff`, and that slot carries only two distinct values. Neither is a
waveform. `set_line_dac_slot` makes the choice switchable so the question can
be measured rather than assumed.

So the datapump runs, and where its PCM output goes is unresolved. The `tblr`
at `0x022e` reading a table based at `0x824d` is the thread to pull. No run has
produced V.21 at all; the harness only ever measured it.

Without `--exchange` nothing above applies: the `--daa-line`, `link` and SIP
paths keep the stand-ins they had, including the parsed `ATD`, the faked line
transition and the harness-generated digits.

## Two instances on one line

`link` runs two instances sharing a two-wire line over a UNIX socket. Each side
hands the far end one 100 ms frame of hook state and line audio and blocks for
the far end's frame, so two independently executing runs stay on the same
emulated clock without either knowing how fast the other goes. Both sides enter
leased-line mode. The opposite option-switch presets leave switch 5 on at side
A so it answers, and off at side B so it originates:

```sh
./courier link main211.xmf --instructions 40000000 --summary
```

By default both sides receive `AT&L1`. `--a-at` and `--b-at` change what each
side is told to do, and `run` takes
`--line-link PATH` plus `--line-listen` directly if you would rather drive the
two processes yourself. The link implies `--with-dsp` and supersedes
`--daa-line`: the far end's hook state is the line state.

### A dialled 403 pair that carries data

```sh
./courier link artifacts/courier-board-21210-capture-403/courier-board.rom \
  --with-dsp --nvram-fixture idsdl403 --board-id 7 --dip-preset default --tick-ms 5 \
  --a-at ATS27=1 --a-at ATX0 --a-at ATDT5551234 --b-at ATA \
  --a-send 'the quick brown fox' --b-send 'jumps over the lazy dog' \
  --instructions 900000000 --summary
```

A prints `CONNECT/ARQ` and then B's text, and B prints `CONNECT 33600/ARQ/V34/MNP/MNP5`
and then A's, byte for byte. The call holds to the end of the run (about 260 s of line
audio). `--a-send`/`--b-send` (`run --send-after-connect`) hold their data until the
modem's CONNECT line ends, as a terminal does: typed earlier, it would abort the dial.

`ATS27=1` on the caller is required. The `idsdl403` fixture carries S27=48, the real
answering unit's value. At 48 the caller goes straight to LAPM, but the answerer only
tests bit 0x20 and waits for an MNP frame. The caller retries its XID three times and
hangs up (reason `0e`), and B is left with `CONNECT 33600/V34/NONE`. The real pair failed
the same way when an `AT&W` drift put both ends at 048; the originator's own value is 001.
`--b-at ATS27=0` instead gives LAPM.

### The 211 pair

The call comes up at the line layer. Each side reports the other off hook, both
qualify the line detector, and each exchanges the same frame count:

```text
a NO CARRIER  frames=354 peer_off_hook=True
b NO CARRIER  frames=354 peer_off_hook=True
```

It gets no further, but the original all-zero-DAC diagnosis is obsolete. The
call overlay now loads at the ASIC service boundary, keeps IRQ 7 active, and
produces role-dependent candidate TDM output while consuming peer words. The
remaining issue is framing the overlay's `0xfffe/0xfffd` slots (and its native
`TRCV/TDXR` activity) into the physical codec stream correctly enough for the
caller to qualify the answer signal. See `courier_firmware_analysis.md` for the
current slot trace.

### Pacing the supervisor's countdown chain

`--tick-source dsp` takes both sides further, and is available on `run` too. It
drives the supervisor's countdown chain from the DSP frame interrupt, one tick
per frame, which is the only arrangement tried here that leaves both of the
firmware's mutual watchdogs quiet. It is off by default: the 1:1 ratio is a
choice inside the band those watchdogs allow rather than a measurement, and the
edge it delivers is one the interrupt controller has masked.

```sh
./courier link main211.xmf --instructions 40000000 --tick-source dsp --summary
```

With the chain running, the line-detector poller the chain carries runs too.
The bridge answers its `0x7c00` request with a reading in the low band, so the
firmware counts its own five hits at `[0x649]`; whenever the chain is paced the
harness stops writing that byte, and stops zeroing the `[0x289]` wait it is
counted inside. `dsp_bridge.detector_replies` reports how many requests were
answered.

Both sides then leave command mode:

```text
a OK  ticks=9141 detector_replies=44 frames=357 peer_off_hook=True
b OK  ticks=9141 detector_replies=44 frames=357 peer_off_hook=True
```

and swap the DTE callback table `acdf,1fce,a8d9` for `50ad,18e3,4cac`, which is
a different front end from the command-line collector. `OK` is not a call
result code, though, and there is still no carrier on the line behind it: this
is the supervisor acting on state the harness supplied, not two modems that
trained. The same option finishes `ATI11`, which previously stopped after
"Modulation", and takes `ATI10` to its "Strike a key when ready" pager.

The line carries no call setup, which is what a dedicated line is: both ends are
connected and each simply sees the other seize. Ring cadence is modelled
separately (`--ring`) and does not yet reach an answer, so an originate/answer
call over the link is not available.

### The window word `0x50` is not the datapump's command port

The C51 has no external `IN` for `0x50` at all. Data addresses `0x50..0x5f` are
reserved on a C5x, this core decodes them as external I/O, and the site at
program `0x8c1f` is a `BIT @50, 6` inside the per-sample service routine. Its
`TC` result is discarded by the `CLRC TC` at `0x8c3d` with no consumer in
between, so the word is read and thrown away. Three checks say the same thing
from the other side:

- Presenting each of the twelve header values the supervisor actually sends at
  window words `0x50`/`0x51` leaves a 3.4 M-instruction C51 run byte-identical
  in every counter, including where it stops.
- The C51's `IMR` is zero after boot, so no host interrupt can reach it either.
- Applying all 2,274 of a run's runtime messages as `host_write(header, data)`
  into C51 data space changes nothing.

So there is no host-to-datapump command path in the resident program, and
"recover the `0x58..0x5e` to C51 `0x50/0x51` valid/ack timing", which earlier
notes named as the next step, is not it. The supervisor's runtime traffic is a
real channel — 2,274 two-word messages with a valid/ack handshake on port
`0x1c`, and the `0x40..0x4e` window used only for the two program downloads —
but whatever consumes it on the board is not the C51 code these images run.

### What the datapump is doing instead

Taking instruction boundaries from a run rather than decoding statically, the
whole of what the C51 executes in steady state is 167 instructions, one pass is
169, and the loop head is at `0x0cb1` — inside the bank the supervisor
downloads. The datapump is resident and idle, not un-entered, and it uses about
6% of the cycles a 25 MHz part has per 9.6 kHz sample.

Every pass ends with `BIT *, 4` on `[0x00cc]` and a `CC 0xb4d4` on the result,
and `[0x00cc]` is zero on every sample of every run. `[0x00cc]` is the
datapump's own status word — the low half of a 32-bit value carried from sample
to sample through `[0x7e]:[0x7d]` and ACCB, holding `0x0555_0000` throughout —
and `0xb4d4` turns out not to be code at all but a numeric table, so that
conditional is not the way in.

Interrupts are enabled — the reset code sets `IMR = 0x002a` and clears `INTM` —
and of the sixteen, only number 7 changes anything when raised. That is not the
datapump waking up: `PMST.IPTR` is zero, so the vector is program `0x0010`,
which is inside the reset code, and driving the interrupt partially reboots the
C51. Almost 6,000 of the instructions it adds are below `0x00d0`.

There is no vector table in this image to point it anywhere better. `IPTR` can
only place one on 32 two-kiloword boundaries; the longest run of consecutive
two-word branches at any of them is a single slot, and nothing table-shaped
exists anywhere else in the image either. The area is never rewritten: across
600,000 instructions of startup the only program-memory instruction executed is
one `BLPD`, which reads rather than writes.

Nor in any other image here. All fifteen — six XMFs, four XMDs, the ISDN ROM,
`.nac`, `.sdl` and `.xmp` — scanned in both byte orders come up empty once the
handler word is required to vary; the long runs are filler or sequential `CALL`
code. Every XMF's DSP payload instead begins at file `0x2f0` with reset code,
identical across `main211`, `main2205` and `3453Bv2.1.1`, and a different
variant in the four 2.3.x builds whose first act is an external write to I/O
port `0x8057` and which programs different wait states (`PDWSR` `0x2000`
against `0x000a`). So the vector area holding reset code is a property of every
build in the tree, not a quirk of one image, and those wait-state values are
the one direct statement about the memory map available here.

The reading that fits is that the C51 is in microcomputer mode, its program
`0x0000..0x0fff` is on-chip ROM holding both the vector table and the bootstrap
that receives the download, and neither is in this image — so the assumption
that the downloaded segment begins at program `0x0000` puts the downloaded init
on top of the vectors.

### The C51 memory map, and what the wait states say

The core used to parse `MP/MC`, `OVLY` and `RAM` out of `PMST` and act on none
of them. It now decodes both spaces as the C51 actually lays them out: program
is on-chip ROM below `0x1000` when `MP/MC` is low, DARAM B0 at `0xfe00` under
`CNF`, external otherwise; data is registers below `0x0060`, DARAM at B2
`0x0060`, B0 `0x0100` (unless `CNF` moves it) and B1 `0x0300`, external from
`0x0800` up, and **reserved** in the gaps at `0x0080..0x00ff` and
`0x0500..0x07ff`. The C51 has no SARAM at all, so `PMST.RAM` and `PMST.OVLY`
are don't-cares on this part.

The wait-state registers are decoded too, and they answer the `MP/MC` question
the images could not. Both firmware families write `CWSR 0x0010`, which puts
every space on the plain 0/1/2/3 scale, and then:

```text
2.1/2.2  PDWSR 0x000a   program 0x0000..0x7fff  2 wait states
         IOWSR 0x0001   io      0x0000..0x1fff  1
2.3.x    PDWSR 0x2000   data    0x8000..0xbfff  2 wait states
         IOWSR 0x0101   io      0x0000..0x1fff  1, io 0x8000..0x9fff  1
```

Wait states only apply off-chip, so a non-zero field is the firmware saying it
expects external memory there. The 2.1/2.2 boards put program `0x0000..0x7fff`
off-chip — exactly the span of the 30,172-word segment the supervisor downloads
— which means `MP/MC` is high and there is no boot ROM under the download. The
pin now defaults to high for that reason rather than by convention. The 2.3.x
boards need no program wait states at all and put their slow external memory in
data space instead.

Every run reports `dsp_bridge.dsp_memory_map` with the mode bits, the
wait-state decode and per-region access counts. One of those counts is worth
reading on its own: **about 700,000 data accesses a run land in the C51's
reserved windows**, and they are the frame-block cells `[0x00ca]`–`[0x00cd]`,
including the line-DAC source and the gate above. On silicon those addresses
hold no storage. `courier_firmware_analysis.md` has the rest.

## Minimal SIP dial-out

`--sip-server` attaches the DAA to a small UDP SIP user agent and enables both
the DAA and DSP automatically. Parsed `ATD` digits become the destination URI;
the client supports an unauthenticated INVITE or one MD5 Digest retry after
`401`/`407`, SDP with PCMU payload 0, ACK/BYE, and bidirectional RTP. The modem's
9.6 kHz line stream is converted to/from 8 kHz PCMU. The current DTMF assist is
inserted at the recovered C51 DAC write, so it travels as ordinary in-band
audio; it is not yet evidence that the firmware datapump entered originate
mode.

Keep the password out of command history by putting it in the environment:

```sh
export COURIER_SIP_PASSWORD='your-password'
./courier run main211.xmf --instructions 12000000 \
  --sip-server pbx.example.net:5060 --sip-username 6001 \
  --sip-target 'sip:{number}@pbx.example.net' --at ATD123 --summary
```

`dsp_bridge.sip` reports the target, response status, dialog state, RTP
endpoints/counters, and a bounded event trace; it never includes the password.
This deliberately minimal client is UDP/IPv4 and PCMU-only. It does not yet
REGISTER, use SIP/TLS, negotiate other codecs, send RFC 2833 events, or turn
SIP failure responses into Courier `BUSY`/`NO ANSWER` result codes.

A live 6000-to-7800 validation completed Digest authentication, received
`200 OK`, and carried 1,152 inbound and 507 outbound RTP packets, while the
Courier still returned `NO CARRIER`. The supervisor emitted 30 two-word
runtime control messages on ports `0x58..0x5e` and none of them reached a
datapump. The blocker is below SIP rather than in its duration or RTP
transport, and it is not the host-latch timing earlier notes named: see "The
window word `0x50` is not the datapump's command port".

The result includes CPU registers, the first 128 I/O/MMIO operations, complete
per-address event counts, the hottest code addresses, and the final execution
path. It also records `supervisor-entry`, `dsp-transfer`, `startup-crc`, and
`main-loop` milestones; a run that reaches the normal dispatcher reports
`status: main-loop`. Unknown input ports return all ones. Input responses and output latches
are separate, matching hardware such as DSP command/status port `0x1e`;
`--port` sets only the input response. This intentionally makes unmodeled
hardware visible instead of silently pretending it exists.

On macOS, a native Unicorn library can be selected with
`--libunicorn /path/to/library/directory`. The worker boundary converts native
signals into a clean CLI failure rather than crashing the controlling process.

## Current boundary

The 80186 and C51 are lock-stepped at their recovered 20/25 MHz ratio. The
supervisor's DSP bootstrap is reconstructed from ports `0x40..0x4e`, verified
byte-for-byte against the XMF C51 boot segment, and published to the native DSP
through the recovered mailbox. The DTE serial path can inject commands and
capture firmware-generated result text. The ASIC line frame now transports
9.6 kHz input/output samples and captures dial tones. Remaining device work is
the original datapump command mailbox, complete 80186 peripheral timing, and
unexercised C51 opcode forms. The silicon DAA's ring, loop-current, and frame
lock state is modeled at register level under `--daa-codec`; its revision
reaches the firmware through mailbox tag `0x7b` and `ATI7`, but no read path to
the line-side status fields has been found, so those are still unconsumed. The
board latches, front-panel signal lines, and the Microwire settings EEPROM are
modeled. What remains on the settings side is a recovered parameter-flash sector
for `0xf8000` and front-panel legends for the unnamed indicator bits; there is no
boot-time NVRAM profile load in this firmware to model.

### Quad CPU AT terminal

For the current server answer attempt, see
[Quad server bring-up](docs/quad-server-bringup.md). The probe can now boot
from the QF archive and records the watchdog-induced `NO CARRIER` path.
CPU/DSP call control remains incomplete; it is not yet a negotiation peer.

The QF060003 modem now executes `AT` → `OK` with an explicit byte-terminal
adapter. Run `PYTHONPATH=. .venv/bin/python tools/probe_quad_at.py` to boot the
controller, load a modem, and verify `OK`, `ERROR`, then `OK` through its real
firmware parser. See [the measured transcript and adapter limits](docs/quad-at-terminal.md).
Raw-pin autobaud remains incomplete. The Quad C50 endpoint now boots the
resident streamed by this CPU and exposes a digital-call timeslot with one
opaque 8-bit G.711 codeword in each direction at 8 kHz. `connect_digital_call`
selects mu-law (`0xff`) or A-law (`0xd5`) idle fill; `receive_g711` and
`transmit_g711` are the byte-exact ingress and egress surfaces.

The captured QF060003 DSP's **stock** DTMF path now runs too. It executes the
QF selector at `0x8de0`, oscillators at `0x8e54`/`0x8e60`, sine helper at
`0x92da`, mixer at `0x82be`, and serial ISR at `0x83e1`; no generated DSP
program or host oscillator supplies its samples. Run
`PYTHONPATH=. .venv/bin/python -m courier_emu.quad_audio --ram
artifacts/quad-identify-20260910/ram.bin --output /tmp/qf-dtmf` to render and
measure all sixteen stock keypad tones.

The captured resident also contains QF's own G.711 expander and compressor.
The component runner executes its DTMF generator, either compressor branch,
and its byte serial ISR, producing raw 8 kHz `.g711` streams without a host
codec. The chassis call-control request that arms this path remains unfinished;
see `docs/quad-dsp-pcm-path.md`.

Its stock answer-signal family is executable as well: 2100 Hz ANS, ANS with
periodic phase reversals, ANSam with the resident's 15.05 Hz amplitude
modulator, and ANSam with phase reversals. Run
`PYTHONPATH=. .venv/bin/python tools/probe_quad_answer_g711.py` to emit every
variant through both the QF A-law and mu-law compressor branches and serial
ISR. Raw `.g711` streams and decoded WAV previews are written under
`artifacts/quad-answer-g711-20260910/`.
