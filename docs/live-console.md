# The live console

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
[what is actually on the board](board-parts.md). Thus, `CodecBringUp`,
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
