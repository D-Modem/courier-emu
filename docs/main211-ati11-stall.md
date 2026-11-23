# main211.xmf ATI11: board tick was masked by the wrong controller model

Status: **the command-completion hang is fixed**. This is an idle-command
regression, not a qualification of connected-call diagnostic values or training.

## Reproduction

```sh
./courier run main211.xmf --with-dsp --instructions 12000000 --at ATI11 --summary
```

Before the fix the serial output stopped indefinitely at:

```text
USRobotics Courier V.Everything Link Diagnostics...

Modulation
```

The failure also occurred directly through the CLI, independently of the GUI.

## Root cause

The main211 supervisor targets the 80C186EB. Only the newer XMF families were
selecting `EbInterruptController`; main211 and main2205 inherited the legacy
DMA-equipped 80186 controller instead.

The two controllers assign different IMASK bits:

| Source | legacy 80186 | 80C186EB |
|---|---:|---:|
| INT2 | 5 | 6 |
| INT3 / board tick | 6 | 7 |

The firmware masks INT2 while leaving INT3 enabled. The legacy map misread that
as a masked INT3 and suppressed every board tick. The run reported `ticks: 0`.

ATI11's receive wait at CPU `62d6d` tests countdown byte `[032d]` and completion
flag `[0328]`. The tick handler owns the countdown. Without ticks, even the
firmware's timeout path never runs, so an unavailable DSP stream hangs the
entire command interpreter instead of producing an idle/unavailable report.
The DSP state observed during investigation was not sufficient to identify the
cause of this infinite wait; treating its memory map as the required fix was a
false lead.

## Fix and validation

All `XmfImage` machines now select the EB interrupt controller. The board-tick
mask check remains in place: this does not bypass interrupt masking or force a
DSP reply. Speculative DSP/mask-ROM changes were discarded.

The follow-up session test also exposed a separate DTE hand-off issue. The
original main211 supervisor can return to the on-hook event dispatcher `A252`
after a command, while the UART stand-in has already collected the next line.
At the command service boundary, a completed line with an `AT` attention prefix
is now handed to the firmware parser `A910`. This is restricted to the older
supervisor ABI, offline operation, the known on-hook dispatcher, and a completed
collector state; it does not replace an online or call-negotiation callback.
The firmware still parses and answers the command.

The same CLI invocation now advances the board tick, prints the complete
report through `V.90 Status`, and terminates with `OK`. At idle, unavailable
measurements remain zero/blank and modulation is reported as unknown by the
original supervisor firmware; the emulator does not fabricate a report or
inject a serial `OK`.

`tests/test_xmf_dsp_transport.py` checks:

- EB mask selection for 2.1, 2.2 and 2.3 XMF families;
- bit 6 masking INT2 without suppressing INT3, and bit 7 masking INT3;
- complete ATI11 reports followed by successful AT, ATI3, and repeated ATI11
  commands in the same live console session.

`--tick-ms 0` deliberately disables the board time base and can still leave
firmware countdown waits blocked. The default GUI/CLI configuration enables it.

The XMF DSP execution/diagnostic-data fidelity still needs separate work. A
completed idle ATI11 report does not demonstrate a functioning DSP call path.
