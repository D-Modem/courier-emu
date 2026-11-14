# 3453C codec and hook-control audit

The 2.3.33 firmware uses the Si3034 for much more than PCM. It also
controls the line-side power, the external hook-pin enable, the country termination,
the calibration/current limits, the DTMF headroom, the gain/mute and the diagnostic loopback.
The GPIO path of the supervisor and the serial codec path of the DSP are separate.

This audit uses the unmodified `2_3_33.XMF`. Where the emulator uses measurements from a different board,
the conclusions about the hardware wiring below are qualified.
The register definitions come from [the local Si3034 revision-2.02
datasheet](../../docs/SI3034.PDF), registers 1–19. The addresses below are physical
80186 byte addresses or C52 program-word addresses, as shown.

## DSP command decoder

[codec-control.asm](codec-control.asm) contains the original resident and
low-overlay instructions. The standard dispatcher `12B1` uses the table at `130D`.
The capabilities below are recovered statically. This dial attempt did not
use all of them.

| Host tag | DSP handler | Codec action |
| --- | --- | --- |
| `7D` | `1275` | `(data & 00EF) + 1000`: write register 16, and force IIRE clear |
| `82` | `127C` | `(data & 00FF) + 1100`: write register 17 |
| `83` | `1283` | `(data & 00FF) + 1200`: write register 18 |
| `84` | `126D` | Send the supplied raw secondary control. Bit 13 selects read |
| `7F` | `0042` | Data 1 sends `0610` (line-side power down). Other values send `0502`, and conditional execution selects `0102` isolation loopback or `0201` RX/hybrid configuration |
| `81` | `005C` | Send `31FF`, a register-17 read, and mark a pending reply |
| `80` | `1292` | Poll the pending identity/register-read result. The related replies use `7B`–`7E` |

Thus, **tag 82 is not the start/hold register of the ASIC of the older family**. Register-17
bit 6 is MCAL (manual calibration). The emulator now records this command
and does not make the synthetic `02`/`03` replies of the older call engine. On this board, it reports its
older `line_enable`, `engine_hold`, `start_strobe` and `ring_indicate`
interpretations as null, with
`command_protocol: si3034`.

The DSP serial helper at `112B` queues a control word in data cell `006C` and
sets `006B`. The primary ISR requests the secondary frame. The secondary ISR
writes the control word and samples its reply before it returns to the primary
PCM. These are actual DSP instructions. They are not a codec setup by the host.

## What the firmware programs

The resident initialization sends `0100, 0203, 0502, 0670, 0704, 083F, 0911,
0A00, 0D00, 0660` through the serial helper. These are the important effects:

- `0502` enables the **external off-hook pin** (OHE), with software OH clear.
  The codec can also assert hook independently through register-5 OH, but
  this attempt does not do that.
- `0670 -> 0660` clears PDL after the clock setup. Registers 7–10 set the PLL.
  With these values, the existing nominal 2.88 MHz MCLK gives 7,200 Hz.
- `0203` enables the receive path and the transmit hybrid. Register 1 gives access to the
  isolation digital loopback. Register 2 gives access to the analog loopback. Register
  15 has separate gain and mute controls. These are codec capabilities.
  This run does not test all the modes.
- The country commands that we saw on the host bus are `7D:002C`, `82:00B8` and
  `83:0002`. They become registers 16=`2C`, 17=`B8`, 18=`02`.
  The documented bits select complex AC termination, TBR21 DC termination,
  automatic-calibration disable, TBR21 current limiting and full-wave ring
  detection. Register-18 DIAL can increase the DTMF headroom, but it is clear
  in this run. The register-17 `80` bit is reserved in this datasheet.
  Keep the value of the firmware, and do not invent its purpose.
- The raw commands `84:1468` and `84:1408` access register 20, which this
  datasheet does not document. Their physical effect is not known.
- The initialization also writes the DSP-side ASIC ports `8068..806C` with
  `000F,0002,0000,0078,0901`. This establishes a different external setup path.
  The register names and the electrical effects are still not verified.

The ring status is in register 5. The isolation-link/frame detect and the loop
current are in register 12. The revision IDs are in 11/13. **No native
codec register read occurs in the failing pair run**. Thus, the missing Si3034
status readback is not the immediate cause that we see here. The calibration timing,
the loopback behavior, the electrical termination and the sticky ring state still need
a more complete emulation.

## GPIO hook sequence and watchdog abort

[supervisor-control.asm](supervisor-control.asm) and the limited
[dial-hook-trace.txt](dial-hook-trace.txt) recover the supervisor side.

The generic latch routines at `5A8B9` and `5A8EE` select ports `10`, `12` and
`14` through CS table `2D75`. They keep shadow bytes at `0675` onward.
They have inverted set/clear operation for the selected hook descriptor in
`[0684]`, and for descriptor `0408`. In this run, `[0684] = 0108`:

1. `5A130` clears port-10 bit `04` through descriptor `0408`.
2. `5A139` clears logical descriptor `0108`. Because of the inversion, this **sets physical
   port-10 bit `01`**: `F2 -> F3`.
3. During the qualification wait, the INT0 handler `67700` increments `[0176]`.
   At 25 or more interrupts, it writes `[0694] = 80` at `67711`.
4. The wait at `5A186` finds that abort flag, branches to `5A246`, and
   returns with carry set. The dial caller then uses its error path.
5. The cleanup at `5FAC4 -> 5A79D` clears physical bit `01`: `F3 -> F2`. Then it
   restores bit `04`: `F2 -> F6`.

The emulator uses port-10 bit `01` as the hook relay. We
measured this mapping on an older Courier board. This trace confirms that the 3453C firmware
uses it as the selected hook signal. It does **not confirm the exact physical 3453C relay
wiring**. Bit `04` is a separate paired line-control signal. Its
physical function is still not verified. With this evidence, do not call it a second relay.

The tick handler resets `[0176]` at `58750`. The initial audit said that
the missing resets came from the delivery of the internal CPU timer. The later
[watchdog investigation](../3453c-watchdog-20261003/README.md) checks the
installed vectors. The reset comes through external vector 0F at `58693`.
The actual blockers were the legacy interrupt-mask layout and a 2.3.x mailbox ISR return
that the emulator did not recognize. We corrected the two blockers. The timer experiments
below are historical diagnostics. They are not the fix that we selected.

Two diagnostic runs enable timer interrupts and do not change the guest RAM:

- `timer-interrupt-experiment.json`: with the old timer-read behavior, the run
  gets to an overlay attempt. Then it fails with `3453C overlay did not acknowledge
  at 00B4, PC=1134`.
- `timer-full-experiment.json`: when the modeled timer reads are also enabled,
  the bootstrap path changes. At 3 million instructions, the resident has not started the
  codec setup. This is not a validated timer fix.

These are optional experiments in `trace_call.py`. They are not changes to the default
machine profile. They show why it is not sufficient to enable a different clock and then claim
that the call-control path is repaired.

## Corrections and pair result

The abort path also waits for UART transmit-empty at `593E2..59403`.
Before, only one specific printf polling address supplied that bit.
The synchronous payload transmitter now returns TX-empty at the actual
read of the `FF66` status register, and it keeps all other bits. This lets the
error path complete and release the hook.

- Before: 6 million instructions, **353,736 hits** on the UART wait,
  `FF66=00`, hook still asserted.
- After: 10 million instructions, **one hit**, `FF66=08`, hook released.
- Pair retest: 150 million analog and 400 million I-modem instructions.
  The native codec clocks **243,925 frames**, does **39 writes and zero
  reads**, and stays at 7,200 Hz. The two TX audio captures are silent.
  **No CONNECT, no incoming call and no payload delivery.**

The pair directory keeps the raw results and the audio. That run occurred before the
correction of the command-82 interpretation. Thus, its `engine-held-enabled` label is
obsolete. It did not use MCAL/start bit 6. Thus, that correction does not
change the call result that we saw.

Validation: 140 tests passed across native C5x execution, audio rates and
acquisition, UART status, native machine execution, recovered 3453C boot,
pair probe and ASIC mappings. We tried a
Unicorn variant, but it got SIGILL in `mem_map` of the installed Unicorn library.
Thus, the new guest-MMIO regression uses the
normal native interpreter of the project. It includes byte/word reads and the preservation of
unrelated status bits.

## Reproduce

Run these commands from the repository root. Each command uses a temporary copy of the
parameter flash. No source sector is changed or copied into this bundle.

```sh
.venv/bin/python artifacts/3453c-codec-call-audit-20261003/trace_call.py \
  --parameters artifacts/3453c-parameter-sector-20261003/f8000-fbfff.bin \
  --output /tmp/3453c-hook-trace.txt

# Diagnostic only; use 'full' to also enable modeled timer reads.
.venv/bin/python artifacts/3453c-codec-call-audit-20261003/trace_call.py \
  --parameters artifacts/3453c-parameter-sector-20261003/f8000-fbfff.bin \
  --output /tmp/3453c-timer-experiment.txt --hardware-timers interrupts

.venv/bin/python -m tools.probe_imodem_analog_pair \
  --analog-board 3453c \
  --analog-parameter-flash artifacts/3453c-parameter-sector-20261003/f8000-fbfff.bin \
  --protocol v90 --instructions 400000000 --analog-instructions 150000000 \
  --analog-send '3453C-TO-IMODEM-12345' --imodem-send 'IMODEM-TO-3453C-67890' \
  --output /tmp/imodem-3453c-pair
```
