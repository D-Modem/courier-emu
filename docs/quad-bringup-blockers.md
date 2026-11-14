# Quad bring-up blockers (2026-09-10)

> AT execution update: [QF CPU byte-terminal mode](quad-at-terminal.md) now
> shows `AT` → `OK`, an invalid command → `ERROR`, and recovery.
> This uses an explicit autobaud adapter. The physical DTE/DSP blockers are still present.
>
> Receive integration update: the subsequent
> [measured QF receive test](nmc-sdl-protocol.md#verification-status--measured-2026-09-10)
> now consumes a finite CRC-framed packet through DUART INT0 with zero empty
> reads. It accepts its CRC, and it rejects a corrupted CRC. The original diagnostic
> results below describe the earlier harness. `tests/test_quad_receive.py` now covers
> the receive fix that it needed. The remaining board/AT blockers still apply.

The Quad needs a board model, not only a replacement of the Courier image. But
**we did not show that an NMC handshake is necessary for AT operation**.
The hardware supports local RS-232 AT commands, and the current harness can
make misleading chassis receive activity.

## Hardware evidence: local AT and switches really exist

The original 3Com **Quad Modem NAC Product Reference, version 6.0/6.1**
(P/N 1.024.1865-00) agrees with the QF/QR release family:
https://files.serialport.org/network/USR_3Com_Total_Control/docs/QMODEM/24186500.PDF

Its overview describes RS-232 through the rear Quad NIC, and also data routing
to a gateway card. Pages 3-8/3-9 document ten DIP switches. The older USR
hardware install guide explicitly describes AT configuration in an unmanaged
chassis (printed pages 3 and 17):
https://files.serialport.org/network/USR_3Com_Total_Control/1996_docs/pdfdocs/qdmodem/qdinstal.pdf

The 1998 Getting Started Guide independently confirms the switch functions
(page 2-2):
https://files.serialport.org/network/USR_3Com_Total_Control/docs/QMODEM/24131600.PDF

For a diagnostic local AT configuration:

| Switch | Setting | Reason |
| --- | --- | --- |
| 1 | ON, or assert real DTR with it OFF | OFF requires DTR before accepting commands |
| 2 | OFF | Word result codes |
| 3 | ON | Enable results; factory default is quiet |
| 4 | OFF | Echo commands; factory default suppresses echo |
| 8 | ON | Enable AT recognition |
| 10 | ON for initial bring-up | Load ROM defaults rather than unknown NVRAM |

These are documented logical switch positions. They are **not recovered port
masks of the emulator**. The CourierPanel DIP wiring is specific to the Courier. Do not assume
that it controls these Quad inputs. We did not find a physical jumper designator or an undocumented
strap setting. Do not confuse the engine identity at port 0x260
with the user DIP switches.

The reference also documents `%D0` (analog), `%D1` (T1/DS0), and `%D2` (PRI).
The line source and the DTE routing are separate choices. A digital line source does
not itself remove the local RS-232 interface.

## Confirmed harness defect: wrong interrupt source and incomplete DUART

A fresh reproduction is in `artifacts/quad-blockers-20260910/probe.py` and
`results.json`. Run it from the root of the repository with:

```
PYTHONPATH=. .venv/bin/python artifacts/quad-blockers-20260910/probe.py
```

It flattens QF060003, starts at 8000:0000, enables interrupt emulation, uses
`tick_ms=5`, puts `AT\r` in the local queue and `22 STX` on QuadUsart, and runs 8 million
instructions for each identity setting. It does not patch firmware or force a
successful handshake. The tick and the other automatic sources stay those of
CourierMachine. Thus, this is a harness diagnostic, not a hardware validation.

| Identity field | Service-loop entries | Chassis RX entries | AT bytes left | Result |
| --- | ---: | ---: | ---: | --- |
| 0 | 92,774 | 2,239 | 3 | No serial output; chassis queue drained |
| 1 | 4 | 0 | 3 | No serial output; USART initialized three times |

For identity 0, there are 2,239 reads of 0x22a and of 0x226, but **zero reads
of status 0x222**. Thus, the older statement that the code never gets to receive is
false for the current harness. The final parser vector is 0x1afc. But this
is not evidence of a valid frame: after the three bytes in the queue, the device
supplies zeros on each empty read.

The cause is specific:

- The initial vector of the Quad, **0x0c, points to 8000:19ac**, its chassis ISR.
- CourierMachine automatically supplies periodic INT0 frame events. The
  Quad has assigned that vector to a different device.
- The ISR reads **0x22a**. It tests bit 1 for receive and bit 0 for transmit.
  If the two bits are zero, its branch still goes into receive. QuadUsart returns
  a constant zero for that register. Thus, each spurious interrupt consumes
  one more byte (or a fabricated zero).
- QuadUsart is connected only to I/O reads/writes. Its queue does not cause
  a device interrupt. Also, it records the command enables,
  the reset operations and the interrupt mask, but it does not implement them.

The layout agrees with the semantics of **channel A of a DUART of the 2681/68681 family**:

| Address | Read | Write |
| --- | --- | --- |
| 0x220 | MR1/MR2 | MR1/MR2 |
| 0x222 | status (RX bit 0, TX bit 2) | clock select |
| 0x224 | device-specific/test | command |
| 0x226 | receive holding | transmit holding |
| 0x228 | input-change register | auxiliary control |
| 0x22a | interrupt status (RX bit 1, TX bit 0) | interrupt mask |

Primary device reference: https://www.nxp.com/docs/en/data-sheet/SCC2681.pdf
(register addressing and ISR/IMR definitions). This identifies a compatible
register family. It does not identify an exact physical chip marking. The SCC2691 agrees
less well, because its receive interrupt bit is 2, but the firmware tests bit 1.

Necessary fix: separate the Quad IRQ routing from the Courier frame/tick sources.
Implement ISR/IMR, the command enables and the interrupts that the queue causes, before you think that
the chassis framing tests have a meaning.

## Confirmed missing mechanism: channel-selected memory and chip selects

The QF code at 0x813b4 selects a target with the high byte of AX, and it writes it to
**port 0x280**. Then it accesses memory through **DS=0x4000**, and then it deselects the target.
The callers use the masks 0x80, 0x40, 0x20 and 0x10. For example, at 0x80b58 they write the same offset
0xbae1 for each selected target. On hardware, these are different selected targets.
The flat RAM of CourierMachine aliases all of them to one location.

The image-copy routine 0x80730 clears 0x40000..0x7ffff, and it copies the executable
and DSP payloads into that window. The routines 0x8032e and 0x8034e exchange
chip-select configurations at 0xff88/0xff8a and 0xff94/0xff96. If we treat those
as register storage and do not change the selected memory, we cannot reproduce
this transport. We must still decode the exact RAM ownership and arbitration.

The identity field at 0x260 bits 4-5 is live, but identity 1 initializes again and again
in this harness. It is not a special switch that enables AT.
The other fields at 0x260, and the input at 0x280, are not yet fully decoded.

One more startup input: 0x8048f samples port 0 bit 3 as a serial bit stream.
It returns 0xffff if no qualifying sequence occurs. Its periodic caller keeps
AL at 0x214. The routine 0x806f6 enables a different service path only for the values
0x40..0x47 or 0x6f. This is evidence of one more missing board input/protocol.
It is **not yet identified as DIP switches**. Do not force one of those values
and then call the run a board emulation.

## Later blockers: actual modem execution and DSP transport

The fresh runs never go into the watched QF DSP load setup at 0x93804. An AT
parser in the image does not prove that the selected modem instance
runs it. Trace the entry of the copied application, its memory for each channel,
the DTE status and the switch acquisition, before you use more instructions to wait
for `--at` to operate.

Then the DSP needs the Quad transport that we already recovered in
`quad-c50-overlay-loader.md`: CPU ports 0xc0/0xc2 and 0x98/0x9a, with DSP I/O
0x57/0x58 for runtime transfers. The ordinary Courier bridge does not supply
this board interface. The overlay placement is already decoded. This replaces older claims that
it is not known or that it uses ordinary global data memory.
Digital audio also needs the correct PCM frame clock and byte
transfers. This comes after the executable loading and the host commands operate.

## The C50 endpoint: where it actually stands (2026-09-10)

The card uses its full run in the C50 overlay download. Over 12M
instructions, the last 6M are one loop. The transport is fully decoded, but
the endpoint does not operate. This section records the decode, the hypotheses that we
tested and excluded, and the one gap that remains. Thus, nobody must find these items again.

### What is solid

**The CPU side.** There are eight 16-bit lanes at `0xc0, 0xc4 ... 0xdc`, with the low byte at the
port and the high byte at the port + 2. `[0x9d38]` selects the lane group: `0xc0`
for the path at `0xced05`, `0xd0` for the path at `0xced12`. `[0x9d37]` is
the strobe of that group, 1 or 2. The code writes it to `0x98` after each four-word burst and
waits for it at `0xced9e`. The final word comes from `[0x9d3a]`. It is strobed with 4 and
acknowledged on bit 2 at `0xcee12`. `0xcec72` writes `0xffff` to `0x98`/`0x9a`
and `0x9c`/`0x9e`, and it polls the two pairs back as a reset presence check.

**What it streams.** Five complete copies of the resident in four million
instructions, byte for byte: 62,544 bytes at a stride of 62,560 bytes. Eight
`0x0083` lane-init words come before each copy. That is row one of the load table in
[quad-c50-overlay-loader.md](quad-c50-overlay-loader.md): source paragraph
`0x2000`, length `0xf450`, destination `0x8000`, across `0x8000..0xfa28`.

**The DSP side.** When we run the captured resident alone, we get one cycle repeated
1,768 times in 200,000 steps: it writes `0x57 = 0x0300` at `0x8313`, then reads
`0x57`, `0x58`, `0x59`, `0x5a`, `0x5b`. Each read is at `0x23f1`, the
`lamm *` of the fetch stub, with `ar1` auto-incrementing. Thus, it is a **five-word window**
from `0x57`: a status word and four data words. This agrees with the burst size of the CPU,
lane for lane (`0xc0`→`0x58`, `0xc4`→`0x59`, `0xc8`→`0x5a`, `0xcc`→`0x5b`).
The code never uses `0x5c`..`0x5f`. Thus, the second lane group of the CPU addresses a
second device, and not a second window.

**It does not fail because a transfer is missing.** With `0x98` not modelled and
floating high, each readiness poll passes, and `0xced12` returns carry-clear on
23 of 24 loads. Then a supervisor at `0xede01`/`0xeddb1` starts the load again.
The missing direction is DSP to CPU.

### Hypotheses tested and killed

We measured each one. We did not only argue it. The counters are from runs of six million instructions.

| Hypothesis | Result |
| --- | --- |
| Acknowledge means "the DSP pulled the queued words", one word at `0x58` | 0 pulls, 0 acks, 0 loads succeeded. Wrong shape: the DSP takes four words at four addresses. |
| Four-word window, `0x57` write is the acknowledge | 3,216 pulls, 590 acks, 1 success against 177 failures. Engages, does not pace. |
| CPU `0x98` and DSP MMR `0x57` are two faces of one register, CPU sees the high byte (`0x0300 >> 8 = 0x03`, the two bits the CPU waits for) | Regression: 590 acks → 16, `0x57` ends at `0x1`. Publishing the strobe into the low byte clobbers the high byte the DSP works with. |
| A hardware "fresh burst" flag raised by the lane latches and dropped when the DSP reads, needing no supervisor write | Killed cleanly: flag raised 532 times, **cleared 2,337 times**. The DSP reads the window regardless. It does not gate on the status word at all. |

The failure profile did not change for any of them: 1 success against 177
failures, three times. **The pacing is not the problem.**

Also, there is no port to which a status word could be written. The lane stride puts
MMR `0x57` at CPU port `0xbc`, and the image contains no `out 0xbc`, no
`out 0xbe`, and no `in` from either. It never loads `dx` with `0xbc`/`0xbe`.

### The real gap: the resident must be booted, not planted

The endpoint loads the captured image before the run and then runs it. Thus, the CPU
streams the resident to a DSP that already has the resident. That situation
never occurs on the board, and no handshake model can make it coherent.
`bridge.py` states the rule clearly, in the 302/403 path that operates:

```
# The boot loader must write the resident, not execute a preloaded copy.
self.core.load_program(bytes(len(resident)), origin)
```

**This is the same part.** [board-parts.md](board-parts.md) identifies the DSP
as a TMS320C50/LC50, not the `'C52` that gives the core its name, and
[firmware-lineage.md](firmware-lineage.md) lists the Quad as 80186 + TMS320C50.
The 55 stale `C52` references in `bridge.py` are a wrong name, and that wrong name
is a live source of error. It suggests that the DSP of the Quad is a different
device that needs a new boot model, but the model that operates already applies.

If we use that path again directly, it does **not** operate, and the reason is specific.
`configure_rom_codec` is the mode of the Courier ASIC, and it changes two items
that the Quad needs unchanged. In `c5x_core.cpp`, `IO_WRITE16` makes port `0x57` an
acknowledgement register whose writes *clear* bits (`m_io[port] &= ~value`). Thus,
the `0x0300` of the resident clears bits 8 and 9, and it does not set them. This
is exactly why `0x57` read back `0x0000` and the host link looked dead. It also
gates `XRDY` on a codec frame clock that this board does not supply. Thus, the reset handshake of the loader
stays in a loop.

**The boot words never needed that mode.** The loader takes them from `DRR`,
gated by `RRDY`. The ordinary path serves the two from the codec receive
queue, and it answers `XRDY` optimistically from `XRST`. Thus, the sequence is:
the recovered mask ROM, MP/MC low, `host_write(0xFFFF, 4)` for the boot strap
(that one is the mode selector of the ROM, not a codec detail, and without it the ROM
gets to an invalid opcode at program `0x3f`), `set_pc(0)`, and the words
given with `queue_codec_rx([origin, len, *words, 0])`.

**Measured working.** From a *zeroed* program space with only the ROM loaded,
512 PCs execute in the span of the resident `0x8000..0xfa28`, and `0x57` reads
`0xfffc`, the value that the resident writes at its own `0x8033`. Code can be
in that span only because the boot loader put it there. Then, in the full endpoint, the
host link runs: 3,979 pulls and 413 acknowledgements.

An earlier revision of this section said that the gap was that "the Quad model has
no codec" to clock the loader. That was wrong. The clocking was always present.
The ASIC mode overwrote the status register of the Quad.

**What remains is the handshake, not the boot.** With a correct boot of the resident,
the load still fails in the same way as before: 1 success against
177 failures and 59 give-ups. This is the identical profile that we saw with each handshake
model that we tried. Also, that number did not change with the boot fix. This is
more evidence that the remaining fault is in how a burst is acknowledged, and that it is
independent of all other corrections here.

### Why the card reloads the DSP for ever

It is a watchdog, and it fires because the card has no work.

`0xc0b38` is a periodic tick. We measured it at 21,779 instructions, stable to
better than one percent:

```
c0b45  test [0x9d3e], 1      ; a DSP transfer in progress?
c0b4a  jne  c0b73            ;   yes -> clear the strike count
c0b4c  cmp  [0x81cd], 0      ; a DSP exchange in progress?
c0b51  jne  c0b73            ;   yes -> clear the strike count
c0b53  inc  [0x81ce]         ; strike
c0b57  cmp  [0x81ce], 3
c0b5c  jb   c0b78            ;   under three -> wait
c0b6e  or   [0x9d3e], 2      ; three strikes: request a reload
```

Then the idle loop services that request at `0xc93e0`. This is the source of the
repeated loads: `test [0x9d3e], 2`, clear it, and call the download
path. `[0x81cd]` is **not** a heartbeat that the DSP sets. Seven sites increment it,
and each is a DSP command/response wait that stops at `0x64` or `0x19`. Thus,
the test means "is an exchange with the DSP in progress".

We measured this over six million instructions: 217 ticks, `[0x81cd]` nonzero at **zero**
of them, **zero** entries into any of the seven wait sites, and 54 strikes. Thus,
no code ever sends a command to the DSP. The arithmetic of the period agrees: three idle
ticks arm a reload. The load itself runs for about seventeen ticks, while the
transfer flag holds the strikes at zero. This gives a cycle of about twenty ticks,
435,600 instructions. This is the measured spacing between successive loads.

**Thus, the reload is not a fault in the DSP path.** It is what this card does when
it is idle. There is no call, no link traffic, and nothing to operate the datapump. Thus, no
exchange ever starts, and the watchdog loads the part again each ~128 ms. A
real card in a chassis with no work would do the same.

That closes the question, and it gives the question back to the link. Parameter `0x1f2`
comes through the message interpreter. The interpreter needs a message, and
nothing has yet delivered one. More examination of the DSP will not give it.

### Reproduce

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_c50.py           # capture the stream
PYTHONPATH=. .venv/bin/python tools/probe_quad_c50_resident.py  # the DSP-side cycle
PYTHONPATH=. .venv/bin/python tools/probe_quad_c50_live.py      # the endpoint, needs the machine wiring
```

`probe_quad_c50_live.py` needs the `quad_c50` read/write/service
hooks of `CourierMachine`, which are not committed.

## What the controller-to-card transport actually is (2026-09-10)

We measured this before we built the concurrency that the section above requests, and it
changes what we must build.

We gave the controller a valid SDL frame and monitored each write into its
memory aperture at `0x40000`. This separates two types of traffic. The bulk clear and
the image copy at `0x80751`, `0x807f4`, `0x8082f` and `0x80842` are the source of all writes except
a small number. The only **targeted** write is at `0x813f0`. There are twenty of them, one byte
of `0x11` to the aperture offset `0xbae1`. This is exactly the offset that this
document already noted is written "for each selected target" through the
port `0x280` selection.

On the card side, that byte has exactly one reader, `0xf64ec`, and it is in
the segment of the message interpreter. It is not a doorbell. It is a response
builder:

```
f64df  di = [0x9c36]          ; reply buffer
f64e3  ax = 0x00f3 ; stosw    ; parameter id
f64e7  al = 2      ; stosb    ; length
f64ec  al = [0xbae1] ; stosb  ; the byte the controller stamped
f64f2..f6518                  ; a second byte derived from [0x82ed]
```

Thus, `0xbae1` is a **slot identity** that the chassis stamps into the memory of each channel.
The card reports it back as parameter `0x00f3`. The interpreter is a
request/response agent. It assembles its replies at `[0x9c36]`, and it parses requests
from `[0x9c2c]`. The two buffers are in card RAM that the
controller can get to through the aperture that it already has.

**Thus, true concurrency is possibly not necessary.** Nothing here shows that
the two processors must run at the same time. It shows that they take
turns over shared channel memory: the controller writes a request, and the card
answers into a different buffer. A harness that runs one side, gives the channel
memory to the other side, runs the other side, and gives the memory back would exercise the same paths. It
is much smaller to build than lock-stepped execution, and we can test it
against a known good result: the card must answer parameter `0x00f3` with the
slot byte that the controller stamped.

These items are not yet decoded: the buffer into which the controller writes a *request*,
and how it signals one. The twenty writes above are provisioning, not a
request, because a bare frame contains no request. To recover that, we need a frame whose
body is an actual parameter request, and the body format is not yet known.

## Recommended order

1. Implement a separate Quad board profile with channel-selected memory and
   IRQ routing. Stop the use of the Courier assumptions for periodic interrupts.
2. Model the interrupt/status/mask behavior of the DUART. Verify the reception of a finite number of queued bytes,
   and make sure that empty reads do not cause incoming characters.
3. Trace the modem startup and recover the Quad DIP/DTR/NIC input wiring. Use the
   documented diagnostic switch configuration, and prove that `AT` returns `OK`.
4. Connect the Quad DSP resident/overlay transport. Then connect the PCM framing and the call setup.
   The transport itself is decoded (refer to the C50 endpoint section above). It is blocked
   because the resident must come through the mask-ROM loader,
   and that loader needs the serial clocking that the Quad model does not yet have.

This examination identifies blockers and corrects the earlier diagnosis.
It does not claim that the Quad now boots or answers AT.
