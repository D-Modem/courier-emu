# Modelling the 20.16 MHz ASIC through the serial monitor

The NEC gate array is the part that the harness models as a black box (refer
to [board-parts.md](board-parts.md)). It is also the only device on the I/O
bus of the 80186. The peripheral block of the CPU is in *memory* at
`0xff00`-`0xffff`, and flash and SRAM are also memory. Thus the device that
answers an `IN` is the ASIC.

The ID_SDL monitor can read those ports on a running board.
`courier_emu.asic_probe` does that, in three states, and writes nothing:

```sh
.venv/bin/python -m courier_emu.asic_probe \
  --device /dev/cu.usbserial-21210 --baud 115200 \
  --output artifacts/asic-ports-01
```

It sweeps `0x00`-`0xff` four times at idle, four times during `AT&T8`, and four
times after. `AT&T8` makes an active state visible. `&T1` loops the DTE through
the modem, so the serial port stops to accept commands. `&T8` runs the same
analogue loopback against the pattern generator of the modem, and keeps the
DTE in command mode. It needs no phone line and never goes off hook.

## The shape of the space

| finding | evidence |
|---|---|
| **Only even addresses are decoded** | all 64 odd ports in `0x00`-`0x7f` read `0x00` |
| **The decode stops at `0x7f`** | above it, all 64 even ports read back their own address and all 64 odd ports read `0x00` |
| **The idle default is `0x00`** | 96 of the 128 ports below `0x80` read zero |

The ASIC has 16-bit registers. The monitor reads a byte. Thus the odd half is
a high byte that nothing drives.

> **A possible explanation, from a different board.** On the **25 MHz Courier
> 2806**, `AD8`-`AD15` do not go to the ASIC - they go to the SRAMs of the CPU
> and are not on the package ([asic-pinout.md](asic-pinout.md)).
> If this board has the same wiring, the odd ports read `0x00` because nothing
> is there, and the 16-bit-register interpretation above is incorrect.
>
> That is not established. We did this sweep on the **20.16 MHz** board. The
> CPU-side interface is the half that is different between the two boards -
> their supervisors are different, but their DSP payloads are not. Nobody has
> traced the `AD8`-`AD15` of this board. One trace of them gives the answer.
> Above `0x7f` there is no device - the value that comes back is the bus that
> holds the last address. This is why a sweep there looks like a ramp.

**The third row is a discrepancy with the harness.** For each port that it
does not model, `machine.py` returns `mask` - `0xff` for a byte:

```python
value = self.port_values.get(port, bridged if bridged is not None else mask)
```

The answer of the board is `0x00` for three quarters of its decoded space. The
measured map is in `courier_emu.asic_ports`, and `asic_ports.seed()` gives it
in the form that `port_values` accepts.

## What is there

Thirty-two ports have a non-zero idle value. All are even, and all are below
`0x80`:

| ports | idle | what they are |
|---|---|---|
| `0a` `0c` `0e` | `f7` `60` `07` | `0e` is a panel latch driver; `0a` and `0c` unattributed |
| `10` `12` `14` | `86` `8a` `7e` | the board latches: hook relay, NVRAM strobe, carrier-detect pair |
| `18` `1a` `1c` `1e` | `ff` `ff` `fd` `ff` | the four that move under load |
| `42` `46` `4a` `4e` `52` `56` | `ff` | the DSP download window, written in thousands and never read |
| `58` `5c` `60` | `20` `0e` `4b` | mailbox tag, data, stream window |
| `64`-`7e` | `78 09 8f a7 e8 aa b6 97 51 51 06 4f b3` | looks like fixed configuration |

That last block is the interesting one. Ten of its thirteen values -
`64 66 6c 72 74 76 78 7a 7c 7e` - are **identical** to the sweep in
`artifacts/io-port-map/hardware-2016mhz/atglk2b.txt`. That sweep came from this
unit when it ran stock 7.3.14, not ID_SDL 4.03. The same values across two
firmware versions and two sessions are what identity or strapping looks like.
The other three (`68` `6a` `70`, and also `58` and `60`) are different between
the captures. Thus they are state.

### The panel rows here are thinner than the ones already recorded

The "board latches" row above is older than
[dsp-rom-probe.md](dsp-rom-probe.md). That document maps these ports bit by
bit: it drove single bits on a physical unit and watched the front of the
modem. `0x14` is active-low and carries CD, CS, AA, ARQ, HS and SYN. `0x12`
bit 1 is MR. `0x10` bit 0 is OH and the relay. `0x0e` is a panel latch driver.
`courier_emu/panel.py` models all of the latch driver and holds the lamp list.
Read that pair, not the one-line summary of this table.

This file adds the physical location of those latches:
[asic-pinout.md](asic-pinout.md) measures that the **ASIC** is the part that
drives the panel. No document had said this before.

## What moves

Only four ports are different between idle and active audio:

| port | idle | `&T8` | bits |
|---|---|---|---|
| `18` | `ff` | `c0`, `c6`, `c7` | `3f` |
| `1a` | `ff` | `c0` | `3f` |
| `1c` | `fd` | `f9` | `04` |
| `1e` | `ff` | `fb` | `04` |

`1c` and `1e` are the mailbox status pair, and the two change on bit 2 - the
bit that the mailbox interrupt of the supervisor acknowledges. `18` also
changed *during* the active state. Thus it carries a live signal, not a stable
level.

This is the main limit of the run: with the loop on hook and no call, most of
the ASIC does nothing. `&T8` gets to only four ports out of thirty-two.

## The reset sweep: a clean negative

`--reset` sweeps on each side of an `ATZ`, not on each side of a loopback. The
theory was that a restart would strobe the DSP download window at
`0x40`-`0x56`.

```sh
.venv/bin/python -m courier_emu.asic_probe \
  --device /dev/cu.usbserial-21210 --baud 115200 \
  --reset --output artifacts/asic-reset-01
```

It does not work. The reason is structural, and faster sampling does not help:
**the monitor is firmware**. The board stops to answer at the moment that it
restarts. It is readable again only when the supervisor is back at its command
loop. At that time, all effects of a reset on the download window are
complete.

The probe still races the reset. It does not wait for the `OK` of `ATZ`,
because that would make sure that it misses the event. It writes the command
without a wait, and then reads one port continuously with a 0.45 s timeout:

```
t=0.000  port 40 -> (no answer)
t=0.375  port 40 -> 00
t=0.540  port 40 -> 00        ... steady thereafter
```

Thus the outage is less than 375 ms, and the board answers immediately after.
The resolution limit is the reply latency of the modem, about 165 ms. Thus a
shorter timeout does not help much.

The result across the reset:

| | |
|---|---|
| ports differing before vs after | **0** of 256 |
| non-zero ports, before vs after | all 32 identical |
| watched ports still moving while settling | none |
| `ATZ` round trip | 0.375 s |

The download window reads `00`/`FF` in the same alternating pattern on each
side. Nothing in the port space records that a reset occurred.

That is a real limit of this method. It is not a tuning problem. To make the
download window change, a transition is necessary that the monitor can
survive. There are only two: power-on, which you cannot see through the
monitor of the firmware, and a call setup. `bridge.py` notes that a call setup
enters the download routine again, but that needs the loop off hook.

## What this does not settle

When we seed the measured map into the ROM harness, it does **not** correct the
open bug where a board ROM accepts input and transmits nothing (commit
`229ef5b`). We ran the captured 7.3.14 ROM with `ATI\r` for 60M instructions:

| | transmitted | received | ticks |
|---|---:|---:|---:|
| harness default (`0xff`) | 0 | 4 | 2,732 |
| measured map | 0 | 4 | 2,730 |

The tick count changes. Thus the map has an effect on the execution, but the
transmit path does not depend on it. That bug is in a different location.
(Those two tests are pytest-style functions. Thus `make test`, which runs
unittest, does not collect them. They fail when you run them directly under
pytest.)

Thus we publish the map, but it is **not wired in by default**. There are two
reasons. First, it is the idle, on-hook state. If a run goes off hook and those
values stay static, the result can be worse than the current `0xff`. Second, it
is the ASIC of the 20.16 MHz board, and the usual image of the harness,
`main211.xmf`, is a fully different generation.

We did not try two things. Both decisions were intentional:

**No port writes.** The response to a write separates a latch from a read-only
status register, and it is the obvious next experiment. But an unknown ASIC
register is not a safe write target - on this board, three ports drive the
hook relay, the NVRAM strobe and the carrier-detect pair. That needs its own
decision. It is not part of a characterization sweep.

**Reads are not always free.** The supervisor collects a reply through the
mailbox data registers at `0x5c`/`0x5e`, and `0x1c` carries the status that
its interrupt acknowledges. Thus a sample of them can consume data that the
firmware needs. `--skip-mailbox` does not read that group. If a result is
important, take it in the two ways.
