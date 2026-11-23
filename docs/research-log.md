# Research notes

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
`ATI0`-`ATI30` sweep, see [the AT interface](imodem-at-interface.md).
[I-modem terminal framing](imodem-terminal-framing.md) tells how the
attention receiver of the external board makes consecutive AT commands
independent.

The [I-modem/analogue Courier pair](imodem-analog-pair.md) sets up native
Bell 103 carrier at 300 bps. It transfers terminal data in the two directions
with the `--protocol bell103` preset of the paired probe. The six-word ASIC data
window and the acknowledgements of the I-modem now move the payload through the
original DSP firmware. V.34 carrier is not yet solved.

The captured 20.16 MHz DSP boot ROM is now integrated for the 302/403 firmware
under `--with-dsp`. The DSP executes reset and downloads its resident through
the ROM loader. The harness now has correct PMST vector decoding and IDLE
wakeup. See
[boot-ROM integration](dsp-onchip-rom.md#bridge-integration-2026-09-07).

The [DSP 3.1.2 audio trace](audio-312-path.md) now runs the original tone
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
[the codec sample rates](codec-sample-rates.md). For the earlier state of
this question, see [the codec rate](codec-rate-312.md).

The [DSP 3.1.2 hardware comparison](mailbox-312-comparison.md) records a
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
[SV25 recovery harness](sv25-recovery.md).

The [DSP ROM-read diagnostic](dsp-rom-probe.md) gives a C5x kernel and a
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
memory](hardware-timebase-and-audio-path.md) confirms three items that the
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

[What is actually on the board](board-parts.md) identifies the parts from
a photograph. Where possible, it checks each part against the firmware. The
large NEC package is `1-016-905`. This is a USR part number on a gate array that
NEC made. It is the "interposed ASIC" that these notes model as a black box.
The mailbox, the DSP download window, the codec bring-up, the line detector and
the missing tone generator are all in that one package. The `40.320 MHz`
oscillator also confirms that CLKOUT is 20.16 MHz. This was the last item that
the tick derivation needed.

[Modelling the 20.16 MHz ASIC](asic-port-map.md) reads the port space of
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

The [boot-block flash loader](sdl-boot-block.md) documents the downloader
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
