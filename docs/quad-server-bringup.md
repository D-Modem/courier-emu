# Quad server answer bring-up (2026-09-11, remeasured 2026-09-17)

The QF server is **not yet a negotiation peer**. A fresh controller boot, a
DSP resident streamed by the CPU, and `ATQ0V1` / `ATA` do not abort the answer now. But
no runtime overlay request occurs, and the transmitted timeslot is a DC
rail that does not change. This does not test V.8 interoperability. The sections below have dates.
The blocker of 2026-09-11 does not occur again. Refer to the 2026-09-17 section.

Run this command from the root of the repository:

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_c50_live.py \
  --archive docs/x2/Qf060003.zip --digital-call --law mu \
  --command ATA --instructions 12000000 \
  --output /tmp/quad-server
```

The report includes the command input, the terminal output, the traces of the call setup and the abort,
the writes to the call flags, the DSP boot/PCM state and the overlay counters.
`current-dsp-tx.g711` contains only the output of the current DSP instance. A CPU
reset discards the previous samples. Thus, an empty final capture is not proof that
no earlier frames occurred. The byte-terminal autobaud adapter and the existing
Courier NVRAM seed are still assumptions of the harness. `--law` selects the idle fill on the wire.
It does not program the companding-law setting of the firmware.

## Corrected startup ordering

Before, `connect_digital_call` enabled DS0 framing immediately when it made
the core, while the recovered ROM still downloaded 16-bit words through
DRR. The endpoint now keeps the incoming octets in a buffer until the boot queue is empty
and the execution has got to the resident program space. Then it enables the digital
frame clock. A reset clears the active PCM state and the I/O cursor of the old core.

The regression executes the real ROM against a padded test resident. It verifies
that no frames occur during the download, and it checks the transmitted codeword
after the handoff. This fixes the boot/PCM boundary. It does **not** show that
the stock resident has all overlays and interrupt targets that a call needs.
(The escape into low program addresses that we recorded here does not occur now. The
2026-09-17 section has the measurement.)

## The answer abort is gone; the call now stalls silent (2026-09-17)

We measured this again with the same command line above, 12M instructions, against
`artifacts/quad-server-bringup-20260911/fresh-ata.json`:

| | 2026-09-11 | 2026-09-17 |
| --- | --- | --- |
| terminal | `OK` / `NO CARRIER` | `OK`, then ATA still up at the limit |
| DSP downloads / reboots | 23 / 22 | 2 / 1 |
| `[82fe]` bit 7 | set at `f35a3` | never set; two writes, both zeroing |
| DSP exchanges | none | 7 commands sent and acked, 1 reply posted |
| PCM | inactive, 0 bytes TX | active, 49,194 G.711 bytes |
| DSP pc at the limit | low program space | `0x82eb`, in the resident, IDLE |

`ATA` still gets to `c7cfc` and `c7d3f`. But the three checks at
`c0b69` that nothing services do not occur now. Thus, nothing sets `[82fe]` bit 7, and the answer path at
`efc84` does not exit through `efc9c` now. The resident also stays in program space,
and it does not escape to low addresses. That escape was the signature of the delay-slot interrupt bug that we fixed
in 20133c6. The orphaned stack pushes of that bug caused `RETD` to pop a stale address.

The attribution is joint, and it is not certain. Four quad-side commits came after the
baseline (`19313a0` C51 boot ROM and split SARAM, `6369173` deferring PCM to
boot completion, `c8b4195`, `df5d709`). Also, the old report has no
`commands_sent` / `replies_posted` fields. Thus, a part of the exchange is
new code, and not a path that is now free. To separate the causes, a run with 20133c6
reverted is necessary.

## What still blocks a connection

`runtime_bursts` is 0. No runtime overlay is requested. Thus, no answer overlay is
selected.

**It produces no audio.** 49,166 of the 49,194 captured bytes are codeword
`0x00`. In mu-law, this is full-scale negative (-8031), not silence. It is a DC
rail that does not change, for 6.15 s. `dxr_writes` is 24,606, while DXR reads back 0 and
`line_tx_nonzero` is 0. The timeslot is clocked, and the same word goes out in each
frame. The part runs and is framed, but nothing modulates.

The next question is why the resident stays at `0x82eb` and does not request an
overlay, because it now answers the CPU exchange.

## The DSP is running the test mode, and it is a loopback (2026-09-17)

`AT&T1` is the lever, exactly as 4772fbe found on the 302. It gets to the
datapump through the test flag, and not through the call gate. Against `ATA`:

| | `ATA` | `AT&T1` |
| --- | ---: | ---: |
| runtime overlay bursts | 0 | 2,547 (2,545 pulled) |
| DSP commands sent / acked | 7 / 7 | 39 / 37 |

The 39 exchanges are the programming of a datapump: six indexed `0x50` loads
(`0c1`, `145`, `211`, `310`, `40d`, `500`), plus `0x48`/`0x49`/`0x51`/`0x52`
with 16-bit values.

The frame handler is five instructions over circular buffer 1. The ARAU
confirms this, and not only the pointer: `CBSR1 0bd0`, `CBER1 0bdf`,
`CBCR 00ef`, that is, CB1 on AR7, enabled. (CB2 is `0058..005d` on AR6, the window of the host lanes.
It is not audio.)

    83eb  lamm @20      ; ACC = DRR
    83ec  sacl *+       ; store it into the buffer
    83ed  lamm @6b
    83ee  or   *+       ; OR with the next cell
    83ef  samm @21      ; DXR = that

Thus, it is a delay-line loopback. It stores the received word and transmits the next
cell. For ALB, this is the correct behaviour. `@6b` is 0. Thus, the
transmitted word is only the buffer cell.

**There are two handlers, and they are phases of one chain.** `PMST 00b0` puts
IPTR at 0. Thus, the vectors are in the mask ROM at program `0000`, and each ROM
vector is indirect: `lamm @NN`, then a branch, with XINT on `@65`. This is the
same ROM of the part as on the 302, and the same mechanism that
[fsk-modulation.md](fsk-modulation.md) already records there. The vector of `INTR 17`
at ROM `0x0022` is `lamm @69 ; bacc`. It dispatches through the block at
data `0x60`-`0x6a` that the cold start fills. We measured this on `main2205.XMF` after
its cold start. `@60`-`@6a` contain resident code addresses (`@64`/`@65` at
`81a3`, next to the `81a6` handler), while `@6b` is `0001` and `@72`/`@73` are
`0000`. **Thus, a cell number is not a vector because of its position.** `@72`/`@73` are the
mark and space increments. They are not handlers, exactly as that document says. In this session,
we suggested that the four FSK bands of 23b72eb are different
because of the installed handlers, and not because of the coefficients. This is wrong for
`@72`/`@73`/`@6b`, and it is correct only for `@69`. The firmware
steers when it writes that cell again (`samm @65` at `83fc` and `8404`). Thus, `83e6` and
`8406` are consecutive phases. They are not alternatives. The second shifts DRR right by eight
before it stores the word. The first stores the full word.

The phase that runs follows the mode. We measured this with a trace of the writes to `0bd4`:

| run | dominant writer | value |
| --- | --- | --- |
| idle on the default source | `83ec` x3,009 | `ffff` |
| `&T1` on the default source | `840c` x1,881 | `0000` |
| `%D1` (either test rejected) | `840c` x2,430-2,895 | `0000` |

These items are excluded as causes of the zero: destructive DRR reads (the read of the model is
non-destructive), the AC01 secondary frame (gated on `m_rom_codec`, which this
endpoint does not enable), the boot download (all writes occur after the PCM
activation, instrumented in the run), `bsar` (shift 8, the implementation is
correct), and an entry in the middle of the handler (a PC trace shows clean entries at `8406`).

`&T3` is rejected on the default source and on the `%D1` source. The `&Tn` list in the
help strings is generic Courier text. It is not the command surface of this card.

**Method note.** `CourierMachine.run()` builds the CPU again, and it starts again at the
image entry on each call. It cannot continue a previous run. Thus, take the before/after windows
from inside one run. Make a subclass of the endpoint. Do not use chunked `run()` calls.

## How a digital call reaches the card (2026-09-17)

The call does not come with a ring. `S62`/`S63` are ANI and DNIS *digit counts*. The strings contain
`INCOMING CALL` and `COMMAND DENIED - MODEM IN USE BY TOTAL CONTROL`. The
`ATA` path is gated on four RAM cells, and not on a line state:

    c7d06  mov al, [0xa88c] ; and al, 3
    c7d12  cmp byte [0xa895], 6
    c7d19  cmp byte [0xa897], 0
    c7d2a  cmp byte [0x878a], 0
    c7d3f  (accepted)

`[0xa895]` has 116 readers and two direct writers: a constant `4` at `c840f`,
and `f7c93`, which takes its byte from the request stream of the chassis:

    f7c81  lodsb                  ; from the request buffer
    f7c82  mov [0x9c2c], si       ; advance the cursor
    f7c86  cmp al,1 ; jbe f7c93   ; 0,1 stored as-is
    f7c8a  cmp al,5 ; jbe f7c91   ; 2..5 stored +2
    f7c8e  jmp f795c              ; >5 rejected

`[0x9c2c]` is the request cursor that `quad-bringup-blockers.md` already identified.
**Corrected 2026-09-17:** it was too strong to call `f7c93` a parser of chassis messages.
Its handler block has two front-ends. The table at
`f7428`, indexed by `letter - 'A'` from the AT `&` parser at `ef1d1`, goes to
the same routines. Each of them parses binary TLV (`cmp al,1` on a
length byte, then a value) from the shared cursor. Thus, `[0x9c2c]` is a common
back-end. It is not only for the chassis.
`[0xa897]` is set in the same way, and it controls hardware: `>1` sets bit `0x40` in
`[0xff64]`, and `<=1` clears it. A third writer at `ee474` initialises `a895`,
`a896` and `a897` together from the profile at ~1.3M instructions. This is
the source of the `04 / 00 / 01` that the gates read. A displacement scan does not find
it, because it writes through a pointer.

### The frame format

    f3ba2  lodsw ; sub ax,2 ; mov [0x9c72], ax   ; +4 length word, minus 2
    f3ba9  lodsw ; mov [0x9c70], ax              ; +6 type word
    f3bad  add bx,8 ; mov [0x9c2c], bx           ; body at +8

The delivery is `f4975`. It copies the bytes to `0x9bac` and the length to `[0x9cbf]`. Then it sets
`[0x9bab] = 1`, which `f43ce` polls. `f3d24` seeds the cursor from that buffer
and calls the dispatcher `f4672`. The dispatcher switches on the low nibble of the type
word through a table at `cs:0xb95` (segment base `0xf3b20`).

### Why a delivered frame does nothing

A correct frame written to `0x9bac` with its length and ready bit is not
consumed. The flag is still set at the end of the run. The gate is one cell:

    f7b62  test byte [0x9d1e], 3   ; -> 00, so retf, every time
    f7b69  dec  word [0x9d1c]

We measured `[0x862c] = 14` (bit 4 set). Thus, the periodic block runs, and `c0b3c`
makes a far call to the interpreter service **64 times** in 12M instructions. Each call
returns immediately, because `[0x9d1e]` is `00`, and `[0x9d1c]` still contains its
`0x2ee0` reload. This entry is a session watchdog, not the receive path: it arms,
counts down, and tears down. The arm site `f7b13` never runs. It is in a sparse
handler table at `f75a2`, next to its disarm twin `f7b34`, and `f470e` fills
each unused slot. Thus, the arm operation itself is a dispatched command.

`f4975` has no near caller and no table reference in the image. Thus, the
receive path starts from machinery that nothing here controls. Also,
`[0xbdea..0xbdfe]` reads `00..00 ff ff ff ff ff ff`. The config block is
erased, and the card is not provisioned. This is the same memory family as the `0xbae1` slot
identity that the controller stamps for each channel.

Thus, the chain is: provision the card, open a session (`f7b13`), deliver a frame
(`f4975` / `[0x9bab]`), seed (`f3d24`), dispatch (`f4672`), write `a895`
(`f7c93`). Then the gate of `ATA` at `c7d12` takes the other branch. We decoded each link
except the first two, and the two are on the chassis side, not
in this image. An earlier guess here said that a chassis-presence strap
gates the interpreter. That is wrong. The service is called on schedule, and it
declines because there is no session.

## The transport, exercised (2026-09-17)

The receive path is accessible. An earlier note here said that no caller
exists for `f4975`. That was an artifact of the static scan. The delivery comes through
a function pointer. The periodic handler makes a far call to `[0x8b4a]` on each tick, and this
is `ed4d0`:

    ed4d0  test [0xb4b0], 0x10 ; je out     ; the window's status byte
    ed4da  test al, 4          ; je out
    ed4de  test al, 0x80       ; jne other
    ed4e2  si = 0xb6de ; di = 0x8d3d
    ed4eb  cx = [0xb6e2] + 6                ; the length word
    ed4f8  rep movsb                        ; copy the frame in
    ed4fa  or [0x9575], 2                   ; raise the state machine's gate

`0xb4b0` and `0xb6de` are in the same card RAM window as the `0xbae1` slot
identity that the controller stamps. Thus, the chassis writes them.
`[0x8b3e]` also contains the next step of the state machine (`f3b2:000f` at rest).
The machine advances when it writes that pointer again. `f43d5` sets it to `0x1d6`
(`f3cf6`, which continues into the cursor seed) when the `[0x9bab]` doorbell is set.

### The frame header

From `f3b2f`:

| offset | field | rule |
| --- | --- | --- |
| +0 | word, stashed at `[0x9d28]` | low byte bits 3-4 must be clear, else dropped at `f3b7f` |
| +4 | length word | used as length - 2, covering type + body |
| +6 | type word | low nibble selects the handler; **bit 14 is the sequence bit** |
| +8 | body | a first byte of `0xAB` bypasses the sequence check |

The sequence bit must agree with `[0x9c50]` bit 1 (`f3b4c` selects the polarity).
When a frame is accepted, the code does `xor [0x9c50], 2`, and this inverts the expectation. If the bit does not agree,
the code goes to `f3b61` and drops the frame, unless `[0x9c76]` bit 3 is set.

We measured this when we stamped twelve frames into the window with the type low nibbles `0..b`:

| | frames copied | state advanced | dispatched |
| --- | ---: | ---: | ---: |
| fixed sequence bit | 64 | 12 | **1** |
| bit read from `[0x9c50]` each time | 64 | 12 | **12** |

That is the first time that the transport operates end to end: stamp, copy,
sequence check, header decode, dispatch.

### Why the session still does not arm

`[0x9d1e]` stays `00`. The type table at `f46b5` has twelve entries. Seven
of them are live (`0,1,3,4,5,6,8`). The others are the `f46cd` invalid stub. None
gets to the resolver that controls the arm parameter:

* Type 0 (`f4728`) resolves ids through a table at `f49c0`, with 205 live entries of 256.
  Entry `0xE6` there is the `0x0bee` filler.
* Types 3 and 4 use `f470f` against their own tables at `0x50e6` and `0x57ae`.
* The arm handler `f7b13` is entry 230 (id `0xE6`) in a *third* table at
  `f73d6` (546 entries, 293 filler). Only `f4895` reads that table, and `f4895`
  has no near caller, no far caller and no vector in the image.

Thus, the arm is dispatched by id, but in an id space that nothing in the decoded path
selects. Either a different front-end gets to `f4895`, or the selecting code is
outside this window. That is the open question. The remaining chain
(provision, deliver, sequence, decode, dispatch, arm, service, `a895`, the gate of `ATA`
at `c7d12`) is mapped, and we exercised all links except that one.

### Method

`CourierMachine.run()` cannot continue a previous run. A `_code_observer` does the window stamp and the
sequence-bit read. The endpoint is a subclass that installs traces when the core is made.
Thus, each measurement above comes
from inside a single run.
