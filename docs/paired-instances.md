# Two instances on one line

`link` runs two instances that share a two-wire line over a UNIX socket. Each
side gives the far end one 100 ms frame of hook state and line audio. Then it
blocks until it gets the frame of the far end. Thus, two runs that execute
independently stay on the same emulated clock, and neither run must know the
speed of the other. The two sides go into leased-line mode. The opposite
option-switch presets leave switch 5 on at side A, so that it answers. They
leave it off at side B, so that it originates:

```sh
./courier link main211.xmf --instructions 40000000 --summary
```

By default, the two sides receive `AT&L1`. `--a-at` and `--b-at` change the
commands that each side gets. If you prefer to drive the two processes
yourself, `run` accepts `--line-link PATH` and `--line-listen` directly. The
link implies `--with-dsp` and replaces `--daa-line`: the hook state of the far
end is the line state.

### A dialled 403 pair that carries data

```sh
./courier link dumps/courier-board-21210-capture-403/courier-board.rom \
  --with-dsp --nvram-fixture idsdl403 --board-id 7 --dip-preset default --tick-ms 5 \
  --a-at ATS27=1 --a-at ATX0 --a-at ATDT5551234 --b-at ATA \
  --a-send 'the quick brown fox' --b-send 'jumps over the lazy dog' \
  --instructions 900000000 --summary
```

A prints `CONNECT/ARQ` and then the text of B. B prints
`CONNECT 33600/ARQ/V34/MNP/MNP5` and then the text of A, byte for byte. The
call stays connected until the end of the run (about 260 s of line audio).
`--a-send`/`--b-send` (`run --send-after-connect`) hold their data until the
CONNECT line of the modem ends, as a terminal does. If you type the data
before that, it stops the dial.

`ATS27=1` on the caller is necessary. The `idsdl403` fixture has S27=48. This
is the value of the real answering unit. At 48, the caller goes directly to
LAPM, but the answerer tests only bit 0x20 and waits for an MNP frame. The
caller tries its XID again three times and hangs up (reason `0e`). B then has
`CONNECT 33600/V34/NONE`. The real pair failed in the same way when an `AT&W`
drift set the two ends to 048. The value of the originator itself is 001. With
`--b-at ATS27=0`, you get LAPM.

### The 211 pair

The call starts at the line layer. Each side reports that the other is off
hook. The two sides qualify the line detector, and each side exchanges the same
frame count:

```text
a NO CARRIER  frames=354 peer_off_hook=True
b NO CARRIER  frames=354 peer_off_hook=True
```

It goes no further, but the original all-zero-DAC diagnosis is now not correct.
The call overlay now loads at the service boundary of the ASIC. It keeps IRQ 7
active. It makes candidate TDM output that depends on the role, while it uses
the words of the peer. One problem remains. The `0xfffe/0xfffd` slots of the
overlay (and its native `TRCV/TDXR` activity) must go into the physical codec
stream with sufficiently correct framing. Then the caller can qualify the
answer signal. For the current slot trace, see `courier_firmware_analysis.md`.

### Pacing the supervisor's countdown chain

`--tick-source dsp` takes the two sides further. You can also use it with
`run`. It drives the countdown chain of the supervisor from the DSP frame
interrupt, with one tick for each frame. Of the arrangements that we tried,
only this one keeps the two mutual watchdogs of the firmware quiet. It is
disabled by default. The 1:1 ratio is a choice in the range that those
watchdogs permit, not a measurement. Also, the interrupt controller masks the
edge that it delivers.

```sh
./courier link main211.xmf --instructions 40000000 --tick-source dsp --summary
```

When the chain runs, the line-detector poller that the chain carries also runs.
The bridge answers its `0x7c00` request with a reading in the low band. Thus,
the firmware counts its own five hits at `[0x649]`. When the chain is paced, the
harness stops writes to that byte. It also stops the reset to zero of the
`[0x289]` wait in which the firmware counts. `dsp_bridge.detector_replies`
reports how many requests got an answer.

The two sides then leave command mode:

```text
a OK  ticks=9141 detector_replies=44 frames=357 peer_off_hook=True
b OK  ticks=9141 detector_replies=44 frames=357 peer_off_hook=True
```

They also replace the DTE callback table `acdf,1fce,a8d9` with
`50ad,18e3,4cac`. This is a different front end from the command-line
collector. But `OK` is not a call result code, and the line still has no
carrier behind it. This is the supervisor that acts on a state that the harness
supplied. It is not two modems that trained. The same option completes `ATI11`,
which stopped after "Modulation" before. It also takes `ATI10` to its "Strike a
key when ready" pager.

The line carries no call setup, as on a dedicated line: the two ends are
connected, and each end only sees the other seize. The harness models ring
cadence separately (`--ring`), and it does not yet get to an answer. Thus, an
originate/answer call over the link is not available.

### The window word `0x50` is not the datapump's command port

The C51 has no external `IN` for `0x50`. On a C5x, data addresses `0x50..0x5f`
are reserved. This core decodes them as external I/O. The site at program
`0x8c1f` is a `BIT @50, 6` in the service routine for each sample. The
`CLRC TC` at `0x8c3d` discards its `TC` result, and nothing between them uses
it. Thus, the firmware reads the word and discards it. Three checks give the
same result from the other side:

- We presented each of the twelve header values that the supervisor really
  sends at window words `0x50`/`0x51`. A 3.4 M-instruction C51 run stays
  byte-identical in all counters, and it stops at the same location.
- The `IMR` of the C51 is zero after boot. Thus, no host interrupt can get to
  it.
- We applied all 2,274 runtime messages of a run as
  `host_write(header, data)` into C51 data space. This changes nothing.

Thus, the resident program has no host-to-datapump command path. Earlier notes
named this next step: "recover the `0x58..0x5e` to C51 `0x50/0x51` valid/ack
timing". That is not the solution. The runtime traffic of the supervisor is a
real channel. It has 2,274 two-word messages with a valid/ack handshake on port
`0x1c`. The `0x40..0x4e` window is used only for the two program downloads. But
the component on the board that uses this traffic is not the C51 code that
these images run.

### What the datapump is doing instead

We took instruction boundaries from a run, and did not decode statically. In
steady state, the C51 executes 167 instructions in total. One pass is 169
instructions. The loop head is at `0x0cb1`, in the bank that the supervisor
downloads. The datapump is resident and idle. It is not "not entered". It uses
about 6% of the cycles that a 25 MHz part has for each 9.6 kHz sample.

Each pass ends with `BIT *, 4` on `[0x00cc]` and a `CC 0xb4d4` on the result.
`[0x00cc]` is zero on each sample of each run. `[0x00cc]` is the status word of
the datapump itself. It is the low half of a 32-bit value that goes from sample
to sample through `[0x7e]:[0x7d]` and ACCB. This value is `0x0555_0000` for the
full run. `0xb4d4` is not code. It is a numeric table. Thus, that conditional is
not the entry.

Interrupts are enabled: the reset code sets `IMR = 0x002a` and clears `INTM`.
Of the sixteen interrupts, only number 7 changes anything when it is raised.
This is not the datapump that starts. `PMST.IPTR` is zero, so the vector is
program `0x0010`, which is in the reset code. Thus, when you drive the
interrupt, the C51 partially boots again. Almost 6,000 of the instructions
that it adds are below `0x00d0`.

This image has no vector table that can point it to a better location. `IPTR`
can put a table only on 32 two-kiloword boundaries. At each of them, the
longest run of consecutive two-word branches is a single slot. Nothing with
the shape of a table is in other locations in the image. The firmware never
writes this area again. Across 600,000 instructions of startup, the only
program-memory instruction that executes is one `BLPD`, which reads and does
not write.

The other images here also have no vector table. We scanned all fifteen in the
two byte orders: six XMFs, four XMDs, the ISDN ROM, `.nac`, `.sdl` and `.xmp`.
When the handler word must vary, the scan finds nothing. The long runs are
filler or sequential `CALL` code. The DSP payload of each XMF starts at file
`0x2f0` with reset code. This code is identical across `main211`, `main2205` and
`3453Bv2.1.1`. The four 2.3.x builds have a different variant. Its first action
is an external write to I/O port `0x8057`, and it programs different wait states
(`PDWSR` `0x2000` against `0x000a`).

Thus, reset code in the vector area is a property of each build in the tree. It
is not a special property of one image. Those wait-state values are the only
direct statement about the memory map that is available here.

The interpretation that agrees with these facts is this. The C51 is in
microcomputer mode. Its program `0x0000..0x0fff` is on-chip ROM. This ROM holds
the vector table and the bootstrap that receives the download, and this image
contains neither. Thus, the assumption that the downloaded segment starts at
program `0x0000` puts the downloaded init on top of the vectors.

### The C51 memory map, and what the wait states say

Before, the core parsed `MP/MC`, `OVLY` and `RAM` from `PMST`, but it did not
act on them. Now it decodes the two spaces with the real layout of the C51:

- Program: on-chip ROM below `0x1000` when `MP/MC` is low, DARAM B0 at `0xfe00`
  under `CNF`, and external in all other areas.
- Data: registers below `0x0060`, DARAM at B2 `0x0060`, B0 `0x0100` (unless
  `CNF` moves it) and B1 `0x0300`, and external from `0x0800` up. The gaps at
  `0x0080..0x00ff` and `0x0500..0x07ff` are **reserved**.

The C51 has no SARAM. Thus, `PMST.RAM` and `PMST.OVLY` have no effect on this
part.

The core also decodes the wait-state registers. These registers answer the
`MP/MC` question that the images could not answer. The two firmware families
write `CWSR 0x0010`, which puts each space on the plain 0/1/2/3 scale, and then:

```text
2.1/2.2  PDWSR 0x000a   program 0x0000..0x7fff  2 wait states
         IOWSR 0x0001   io      0x0000..0x1fff  1
2.3.x    PDWSR 0x2000   data    0x8000..0xbfff  2 wait states
         IOWSR 0x0101   io      0x0000..0x1fff  1, io 0x8000..0x9fff  1
```

Wait states apply only off-chip. Thus, a field that is not zero tells that the
firmware expects external memory there. The 2.1/2.2 boards put program
`0x0000..0x7fff` off-chip. This is exactly the span of the 30,172-word segment
that the supervisor downloads. Thus, `MP/MC` is high, and no boot ROM is below
the download. For this reason, the pin now has the default high, and not by
convention. The 2.3.x boards need no program wait states. They put their slow
external memory in data space.

Each run reports `dsp_bridge.dsp_memory_map` with the mode bits, the wait-state
decode and the access counts for each region. One of those counts is important:
**in each run, about 700,000 data accesses go to the reserved windows of the
C51**. They are the frame-block cells `[0x00ca]`–`[0x00cd]`, which include the
line-DAC source and the gate above. On silicon, those addresses have no
storage. `courier_firmware_analysis.md` has the rest.
