# ATG's eight-hex-digit DSP command form

We confirmed this form on the attached Courier on 2026-09-09: ID_SDL 4.03d,
supervisor 7.4.16, DSP 3.1.2, at `/dev/cu.usbserial-11420`, 115200 baud.

```text
ATGccccdddd
   │   └── 16-bit data/argument, four hexadecimal digits
   └────── 16-bit DSP command/tag, four hexadecimal digits
```

Use eight uppercase hex digits, with the leading zeroes, and no comma.
Forms with four digits or fewer select different handlers. The command numbers
select firmware operations. They are not arbitrary DSP program addresses.

## Fresh board measurement

| Sent through ATG | Mailbox reply tag:data | Interpretation |
|---|---|---|
| `ATG00620000` | `0069:0015` | Known sample-processing query |
| `ATG00070000` | `0031:0000` | Known status-word query |
| `ATG002D0000` | still `0031:0000` | No-op. The held reply does not change |
| `ATG00620000` | `0069:0015` | The repeated query changes the reply again |
| `ATG0007A55A` | `0031:0000` | Query 07 ignores its supplied data |

All five returned serial `OK`. Each time, the queue head of the supervisor moved six
bytes, and the tail then moved to the same position. The RAM kept the exact
frames, which include `ff00 0007 a55a` for the last request. The alternating
reply tags show that each response is new, and is not a read of an old holding register.
The `0015` value is the result of this capture. It is not a universal constant for tag 62.

We sent only those queries and the no-op, which were already characterized. We did not use direct
mailbox writes, memory writes, reset, flash operations or dialing.
AT answered after the sequence. The experiment does not prove that all possible
16-bit commands are valid, or that each handler uses its data argument.

## Reply retrieval

The G command queues the request. It does **not** print the DSP reply as
part of its serial response. Read the holding registers separately:

```text
ATGLK2I0058    reply tag, low byte
ATGLK2I005A    reply tag, high byte
ATGLK2I005C    reply data, low byte
ATGLK2I005E    reply data, high byte
```

During this test, the supervisor operated the mailbox automatically. We did
not write the commit or acknowledgement ports. The idle CPU status was `fffd`
after each transaction that we saw. The supervisor had consumed the readiness
event while the reply bytes stayed held. These byte reads are not an atomic
snapshot. When other DSP traffic is active, they do not by themselves connect a reply to a request.

## Exact firmware path

The captured 403 G handler at file `0x25c5b` selects the eight-character
case. It parses the first four hex digits into AX and the second four into
BX. Then it calls `8f46:01e4` (file `0xf644`). Its helper at `0xf678` queues:

```text
ff00, command, data
```

The `ff00` marker selects a paired transfer. It is not sent to the DSP.
The drainer at `0xf511` writes the command low/high to `58/5a`, then the data
low/high to `5c/5e`. Thus, the text `A55A` becomes the bytes `5a` then `a5` on
the data ports. The queue words are in supervisor RAM `0198..01c7`, with the
tail at `0194` and the head at `0196`.

If there is not sufficient space, the queue helper returns and does not enqueue,
and the G handler still clears carry. Thus, **serial OK alone does not
prove the delivery**. Our empty/idle test confirms the delivery through changed
DSP replies and drained queue pointers. We did not measure the operation with a saturated queue or
the concurrency with a connected call.

This gives us a shorter way to start known DSP operations through the normal
supervisor path. It does not add a DSP memory reader or an arbitrary subroutine
caller. Those still need a suitable DSP handler or a RAM probe.

## Evidence

[Hardware capture](../artifacts/g-eight-hex-board/hardware.json),
[raw command transcript](../artifacts/g-eight-hex-board/transcript.json),
[capture script](../artifacts/g-eight-hex-board/capture.py), and
[drainer disassembly](../artifacts/g-eight-hex-board/drainer-disassembly.txt).
The earlier [isolated queue test](../artifacts/undocumented-atn-analysis/g-queue-results.json)
independently checks the parsing/order without hardware.

The [normally booted DSP replay](../artifacts/g-eight-hex-board/booted-emulator.json)
now agrees with all five board results. This shows that the query-62 mismatch (`0012` against `0015`) that we reported before
was a difference in the test initialization.
Refer to [the comparison analysis](mailbox-312-comparison.md).

## The same command on 7.6.7, and what it costs online

We measured this on 2026-09-15 on the leased-line unit at `/dev/cu.usbserial-FT4TQOFT`,
supervisor 7.6.7 / DSP 3.1.2, serial `21OWZ849PS95`. This is the board with the flash
`artifacts/courier-board-11430-flash-20260914-unit2-02/courier-board.rom`.

**`LK2` is mandatory on this build.** Bare `ATG00070000` answers `ERROR`, and
bare `ATG` also answers `ERROR`. The handler itself is byte-equivalent to the handler of 4.03d. It is relocated to
file `0x26794`, with the queue helper at `8f51:01e4`. Only the prefix check
is different. At `0x2673b`, the two builds compare `word [si]` with `'LK'` and
`[si+2]` with `'2'`. On a mismatch, 4.03d continues into the subcommand
dispatch, but 7.6.7 jumps to `stc; ret`. Thus, each form below has the
prefix: `ATGLK200070000` queues the same item that `ATG00070000` queues on 4.03d.

These are the subcommand letters, disassembled from the same image:

| Form | Handler | Action |
|---|---|---|
| `ATGLK2Iport` | `0x267d7` | one `in al, dx` |
| `ATGLK2Bport` | `0x27af4` | 16 consecutive ports, `in`/`inc dx` |
| `ATGLK2Oport,val` | `0x267f7` | one `out dx, al`; the comma is required |
| `ATGLK2=[seg:]off` | `0x27a28` | 16 memory bytes from `es:[bx]` |
| `ATGLK2R[seg:]off` | `0x27a93` | 8 memory words |
| `ATGLK2N` | `0x267cf` | sets bit 0 of `[0x158]` |

`I` reads ports, not memory. Thus, you cannot read the queue pointers with it.
`ATGLK2I0194` returns `94` and `I0196` returns `96`, because those ports are
not mapped and float the low byte of the address. `R` reads them correctly.

**Query 07 is delivered and answered during a live V.34 call.** With the pair
connected at 33600/33600, `ATGLK2R0190` showed the tail and the head at `0x019E`
before and at `0x01A4` after. The six bytes at `0x0198` held the expected
`ff00 0007 0000` frame, and port `0x58` changed from `0x20` to `0x31`. That is reply tag
`0x0031`, the same value that the idle 4.03d board gave. For that query, this answers the
concurrency question that was open above.

**Query 62 dropped the call and stopped the supervisor.** We sent it next on the same
connection. After `ATGLK200620000`, `NO CARRIER` came, and then the modem
did not answer `AT` until we did a power cycle.

> **CAUTION: DO NOT SEND TAG `0x62` WHILE A CALL IS CONNECTED.** It can drop the call and stop the supervisor until a power cycle.

We do not know if the cause is the query or the concurrency. It occurred one time, and we did not repeat it.

[Online capture](../artifacts/leased-pair/dsp-queue-online.json),
[prefix comparison](../artifacts/leased-pair/dsp-lk2-prefixed.json), and the
[refusals before the prefix was known](../artifacts/leased-pair/dsp-online.json).

## Idle and online on one board, the same afternoon

We measured this on 2026-09-15 on the 4.03d board, which was then on `/dev/cu.usbserial-FT4TQOFT`.
DTR was held for the full run, thus the hook state did not change during the run.
We read the port block with `ATGLK2B0050` and the queue with `ATGLK2R0190`.

Idle, after `ATH0`, the reply path operates as the board did on 2026-09-09:

| after | port `0x58` | port `0x5c` | tail = head |
|---|---|---|---|
| - | `44` | `00` | `019e` |
| `ATG00070000` | `31` | `00` | `01a4` |
| `ATG00620000` | `69` | `15` | `01aa` |
| `ATG00070000` | `31` | `00` | `01b0` |

Tag `0031:0000` and `0069:0015` reproduce exactly. The alternation shows that each
reply is new, and not an old holding register. The ring carries the two
frames, `ff00 0007 0000` and `ff00 0062 0000`, six bytes for each request, and it is drained
each time.

Online, on the same board some minutes earlier, the request path is the same, but the
reply path is not. The pointers moved from `01b6` to `01bc`, with the frame in the ring.
But ports `0x50` through `0x7f` were byte-identical before and after. They were also
identical across three samples, some seconds apart. Two ports clearly identify the
states: `0x58` reads `20` during a call and `44` in idle, and `0x60`
reads `61` during a call and `0a` in idle. Thus, a queued request is delivered
during a call, but its reply does not go to the holding registers.

Read these as 16-bit latches, with the low byte at the even address. Each odd byte in
the block reads `00`.

[Idle A/B](../artifacts/leased-pair/dsp-403-idle.json),
[online sweep](../artifacts/leased-pair/dsp-403-online-sweep.json),
[repeated online samples](../artifacts/leased-pair/dsp-403-port-timeseries.json).

`courier_emu.mailbox_compare` replays the two states through a booted DSP.
The idle capture agrees step for step, with the alternation
([capture](../artifacts/leased-pair/g-idle-capture.json),
[report](../artifacts/leased-pair/g-idle-emulated.json)). The online capture does
not agree, and it cannot agree yet: the harness has no call. Thus, it publishes `0031` where
the board holds its `0020` latch
([capture](../artifacts/leased-pair/g-online-capture.json),
[report](../artifacts/leased-pair/g-online-emulated.json)). The measured values
for the two states are in `courier_emu.asic_ports`.
