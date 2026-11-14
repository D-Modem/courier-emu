# Quad QF060003: measured AT terminal execution

On 2026-09-10, the QF modem firmware gave `OK` for `AT`. It rejected an
unsupported command with `ERROR`, and then it accepted one more `AT`.
This is an **opt-in CPU byte-terminal adapter**. It is not a completed emulation of the physical Quad
DTE/autobaud or of the DSP.

Run this command from the root of the repository:

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_at.py
```

For a shorter sequence, run this command:

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_at.py \
  --command ATQ0V1 --command AT
```

The probe boots the original `docs/x2/Qf060003.zip` controller with `QuadBoard`
for eight million instructions. Then it flushes the memory of the selected channel, and
boots channel 0 from the reset stub that the firmware loaded. Then it runs that modem
for twelve million instructions with `tick_ms=5` and `quad_terminal=True`.
It does not depend on flash or RAM artifacts from earlier dumps. The SHA-256 of the
modem flash after the run is
`86e8d044ad162087283d5478398d59b9dbaa3df0f9dc84eb1aeab8feb635ce41`.

## Measured transcript

| Input | Firmware response |
| --- | --- |
| `ATQ0V1` | `OK` |
| `AT` | `OK` |
| `AT+NOTACOMMAND` | `ERROR` |
| `AT` | `OK` |

`ATQ0V1` configures normal word results through the command parser of the firmware.
The adapter does not change the quiet/verbose settings. The complete
28-byte input gets to these locations:

- The serial receive ISR at `0xc11b0`, exactly 28 times.
- The attention detector at `0xcfc6d`, four times.
- The call to the command dispatcher at `0xc97a9`, four times.

At the end, the dispatcher is idle (`[0x81f8]=0x91e6`),
and no input stays in the queue.

This is the raw `S0TBUF` output, with the earlier binary startup marker:

```text
55 aa 00
8d 0a cf 4b 8d 0a
8d 0a cf 4b 8d 0a
8d 0a c5 d2 d2 cf d2 8d 0a
8d 0a cf 4b 8d 0a
```

The terminal decodes seven data bits, because QF includes parity in bit 7 of these
register writes. The report keeps the raw bytes separately. It does not include the
startup marker in `terminal_text`. No emulator code makes `OK`,
`ERROR`, an AT command buffer, or a completed-command event.

Results: `artifacts/quad-at-20260910/results.json`. Regression:

```sh
.venv/bin/python -m pytest -q tests/test_quad_terminal.py
```

The regression checks these items: the full transcript from a fresh boot, the ISR and dispatch counts,
the drainage of the queue, the return to idle, and the rejection of an unknown firmware layout.

## Exact adapter boundary and remaining work

The ordinary byte harness did not exercise the raw-pin autobaud sequence of QF.
In this sequence, the initial serial receiver is disabled while the timer/INT1 handlers sample
Port 2 pin 5. A longer run without the adapter still gave only `55 aa 00`. It did not read
`AT`. It would be wrong to interpret that marker as an AT response.

`courier_emu.quad_terminal.QuadTerminal` explicitly replaces this front end with a fixed-baud
byte front end. It verifies the signatures of the recovered QF modem layout.
It waits until the real command scheduler of the firmware is idle. Then it installs the contract
that we found at QF `0xe51be` and `0xcfc5f`:

- receive vector `c041:0da0` (physical `0xc11b0`);
- attention callback `[0x81f4]=0xf85d` (physical `0xcfc6d`);
- byte-receive mode `[0x8988]=2`, `S0CON=0x21`;
- masked INT1 and disabled autobaud timers 1 and 2.

It sends the input through `EbSerial` and the interrupt
mechanism that the firmware installed. At each new command, it restores only this receive contract. It never
forces the command scheduler to idle. While the firmware processes the previous command, it waits.
The firmware does the collection, the dispatch, the command effects and the UART
output. The mode is off by default. It rejects unsupported layouts, which include
QR. Do not think that it is a verified bring-up of the hardware registers only.

These items are not complete: DSP mailbox execution, physical baud timing, the Quad DIP/DTR/NIC wiring, and
the simultaneous operation of the four modem CPUs. The existing
open-bus DSP responses and the explicit 5 ms scheduler tick are still assumptions of the harness.
The CPU gets to its command scheduler. But it downloads the
DSP code again and again, because there is no Quad DSP peer that operates. This test shows
usable AT parsing and replies at the CPU level. It does not show calls, audio,
or a complete Quad hardware model.
