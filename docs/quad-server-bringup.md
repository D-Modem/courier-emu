# Quad server answer bring-up

The QF server now **connects and delivers bidirectional ASCII data over
V.34/LAPM and symmetric x2/LAPM** against the original I-modem.
Both modems report **`CONNECT 64000/ARQ/x2/LAPM`** in the symmetric control,
and both distinct payloads arrive intact, with no CPU/DSP errors, PCM
underruns or UART drops. See the [x2 evidence](../artifacts/quad-x2-symmetric-provisioned/README.md)
and [role matrix](../artifacts/quad-x2-modes/README.md).
**Asymmetric server x2 now also passes** against an analog Courier client:
52000 at the client, 33333 at Quad, both payloads intact and carrier retained
at a shared 60-second media boundary. See [the new control](#asymmetric-x2-with-an-analog-client-2026-10-18).
A **180-connected-second paced V.34 traffic soak now passes at 9600**.
The default 31.2/33.6k V.34 control still develops receive corruption and a
LAPM stall. Full-rate throughput and multi-minute x2 traffic remain unverified.
The V.34 control reports 31200/33600; its
[working evidence](../artifacts/quad-v34-lapm-online-handoff/README.md) remains valid.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --imodem-send IMODEM-TO-QUAD-482619 \
  --quad-send QUAD-TO-IMODEM-731954 --check-data --output /tmp/quad-working
```

The pair defaults now provide enough instructions to train and exchange data.
`--check-data` requires both CONNECT results, both opposite-terminal payloads,
an active Quad call at the limit, and no CPU/DSP errors, PCM underruns or
terminal byte loss. The caller can report NO CARRIER after the bounded Quad
worker exits; that is test termination, not a claimed permanent connection.
Earlier dated sections below preserve historical failures, not current blockers.

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

### Historical diagnosis: why the session did not arm

**Superseded 2026-10-13:** sparse tables were disassembled at incorrect
boundaries. Type 1 does reach `f4895` through `f4856`; parameter `80e6` arms
the session. The claim below that this resolver is unreachable is incorrect.

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

## Chassis arm, digital identity, and a real caller (2026-10-13)

`tools/probe_quad_call.py` boots the archive's controller first, then posts
frames to the chassis-owned `b6de` window and rings the `b4b0` availability
bits. The original modem firmware performs every state change:

| type | parameter | value | effect |
| --- | --- | --- | --- |
| 1 | `80e6` | no TLV | `f7b13`, session arm (`9d1e=01`) |
| 1 | `003f` | length 1, value 4 | `f7c74`, firmware sets `a895=06` |
| 1 | `0042` | length 1, value 2 | `f7ca5`, firmware sets `a897=02` |
| 3 | `8094` | no TLV | `f8f2a`, genuine chassis answer, then `c7cfc` |

Sequence is type bit 14, matching `9c50` bit 1. No guest call flags, program
words, or function pointers are patched. `--enable-v8` additionally sends
parameters `014c=0` and `015e=0`, clearing S54 bits 0 and 6 through the
firmware's normal parameter setters.

`CourierMachine(quad_line_kind=2)` supplies the chassis identity input at
`b4b5 & 3`; 1 means analog and 2 digital. Ordinary startup clears the RAM
window, so a pre-reset fixture alone is insufficient. The persistent input
is visible on CPU reads, retaining all unrelated bits. Firmware `f3691`
selects `878a=01`; the emulator does not write that personality cell. Digital
reset then uses command `6b` instead of the analog follow-up `31`, and the
DSP retains byte mode `SPC=40cc` rather than word mode `40c8`.

Other shared-core corrections:

* The bounded 8,192-event diagnostic I/O ring is no longer the live handshake
  cursor. A monotonic event total keeps replies flowing across rollover;
  lost unobserved history raises an error instead of silently freezing.
* Only status writes with `0200` acknowledge an overlay window. Unrelated
  host-mailbox acknowledgements cannot consume program data.
* Service budgets actual DSP cycles and carries overshoot debt, instead of
  counting instructions as cycles.
* An optional media peer uses the same native yield-on-frame primitive as
  the I-modem. The initial 800-octet idle reserve is line delay, not carrier
  or payload injection. Peer data refills before the next PCM frame.

### Byte receive shifter: explicit modeling assumption

SPRU056D section 9.5, page 9-32 guarantees only the **low** DRR byte in SP byte
mode; the high byte is indeterminate (unlike BSP sign extension). Zero-filling
it made the stock `8406` ISR's `bsar 8` read only zeros. The native model now
retains the preceding byte in the upper half of a 16-bit receive shifter as
the next eight bits arrive. Tests verify the documented low byte, unchanged
word mode, and execution of the original ISR consuming the delayed byte.

This is a deterministic model of unspecified upper bits, **not a measurement
of the physical card's shifter**. Hardware capture is still needed to confirm
that exact upper-byte behavior. It is not permission to shift the documented
received byte into the wrong half or fabricate demodulated data.

### Measurements and limits

* `artifacts/quad-stock-chassis-arm-20261013`: controller-loaded firmware,
  no DSP; all five type-1 setters and the chassis answer execute once.
  `9d1e=01`, `a895=06`, `a897=02`, `878a=01`, `a863=00`.
* `artifacts/quad-digital-provisioned-answer-20261013`: 20M CPU instructions,
  real resident, 42 command/ack exchanges, 42,233 TX octets, `SPC=40cc` and
  a 2100-Hz component. This standalone run intentionally has no receive peer;
  its RX underruns are not a duplex-call result.
* `artifacts/quad-imodem-v34-v8-20261013`: 60M Quad / 250M I-modem CPU
  instructions, physical B-channel socket exchange, 170 frames / 136,000
  octets each direction, **zero Quad PCM RX underruns**. The caller reports
  V.8 status and requests overlay `a000`, but **no CONNECT**. Quad has only
  three DSP replies and no runtime overlay request. The caller's broken pipe
  after the bounded Quad process exits is expected test termination, not
  evidence of an established modem call.

Reproduce the strict, currently failing negotiation check:

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --check-connect --output /tmp/quad-imodem
```

These older measurements prove chassis dispatch, digital routing, and reciprocal
PCM delivery, not completed negotiation or multi-minute traffic. The subsequent
investigation below supersedes the missing-overlay diagnosis. No carrier,
overlay request, or decoded bytes are injected.

### Mailbox reset, overlay epochs, and data banks

The stock V.8 receive code was actually constructing and sending a joint menu.
Its outgoing mailbox stalled because writing `ffff` to DSP PA7 cleared the
reply-slot-free bit. Mailbox reset now leaves that bit set (`0002` for the
Quad; the existing I-modem reset remains `0006`). Normal acknowledgements
remain write-one-clear.

Runtime download readiness is transaction-scoped: CPU strobe 4 clears the
previous epoch *before* command 2 arrives. The DSP must acknowledge download
arming before readiness is exposed. A burst is consumed only after reads of
all four window ports and a non-reset `0200` acknowledgement. Reset `ffff`
is not a burst acknowledgement. This prevents the first 44 words from being
written at the previous program destination instead of `a180`.

After boot, CPU ports `98`/`9a` and banks `c0..d6` are also the six-bank data
interface, corresponding to DSP `56` and `58..5d`. This is the analog ASIC
mapping shifted by `80`. Port `98` reports the inverse host-to-DSP pending
mask; `9a` reports the inverse DSP-to-host free mask. CPU transmit strobes
publish selected holding words and set low pending bits; receive acknowledgements
set the corresponding upper free bits. Data writes must not start boot bursts.
Tests cover both directions, independent acknowledgements, all six banks,
and reset returning to download mode.

With these fixes, original firmware requests and executes runtime overlays and
reaches modem training completion. The no-error-control diagnostic
(`--settings 'S54=0S58=43&M0&K0' --quad-modem-mode 0`) reports
`CONNECT 31200/V34/NONE` on the I-modem, but then delivers unwanted binary
output. **That is not verified data interoperability.** Default LAPM still
fails: the Quad sends idle words `40ff`, receives a repeating raw bit pattern,
and eventually commands DSP power-down; `IDLE2` at `8329` is now modeled as a clock-domain wait that wakes on a peripheral edge or NMI, while `INTM` still controls vectoring.
The same raw receive pattern occurs at 9600 and 31200 bps. Diagnose the
firmware's V.42 detection/receive framing next rather than treating these
bytes as random PCM loss. Duplex captures still show zero Quad RX underruns.

Evidence: `artifacts/quad-v34-data-lanes-20261013`,
`artifacts/quad-v34-no-arq-20261013`,
`artifacts/quad-v34-profile-clock-20261013`,
`artifacts/quad-v34-9600-data-lanes-20261013`, and
`artifacts/quad-x2-data-lanes-20261013`. The last falls back to V.34; it is not
an x2 connection. `--trace-dsp` saves program/data memory, snapshots, port
statistics, raw G.711 and bounded data-bank events.

The probe now retains parameter `0042`'s startup value 1 by default rather
than assuming value 2 means digital bearer selection. A control with value 1
has the same negotiation failure as value 2; persistent line identity, not
this parameter, selects digital personality. Multi-minute Quad traffic is
still unproven.

The subsequent [V.42 receive analysis](quad-v42-receive-decomp.md#packed-odp-reaches-the-supervisor)
identifies the repeating raw receive bytes as valid LSB-first packed ODP:
235 alternating `11`/`91` characters in the saved bank-event prefix. The
supervisor snapshots retain receive callback `3210` (`CLC; RET`), so the next
blocker to investigate is the CPU-side receive-mode transition. This is not
a demonstrated LAPM connection or permission to inject a receive handler.
That diagnosis is now resolved by the configuration correction below.

## Working V.34/LAPM: mode enum and DTE handoff

Two independent harness errors blocked the call and its input direction:

1. Parameter `003f` is a **chassis wire enum**, not an AT `&M` number. The
   original setter `f7c74..f7c96` maps `0,1,2,3,4,5` to firmware modes
   `0,1,4,5,6,7`. Sending 4 selected mode 6, not normal/error-control mode 4.
   Both probes now default to **wire value 2**. Firmware then selects its
   real detection and framing callbacks without any callback patch.
2. The caller's CONNECT text arrives while its DTE callback is still `0e0e`,
   which aborts on a keypress. Immediate application input produces genuine
   **Keypress Abort**, confirmed by ATI6 with zero characters sent. In the
   passing control, only 512 more CPU instructions are needed for the
   firmware to install callback `46cc`, the data-queue receiver. The shared
   I-modem marker/traffic pump now reads that handoff before queueing data.
   It imposes no fixed delay and does not rewrite any receive pointer.

`terminal_handoff` in the caller report records the actual transition:
`112719872: ec8d/0e0e` to `112720384: eca9/46cc`, both in bearer frame 154.
The previous five-second delayed control and a forced-9600 control also pass,
but neither workaround is required by the default-rate handoff-gated run.

The Quad byte-terminal adapter now supplies online bytes only when real
carrier is present and its UART receiver is enabled. It does not reinstall
the command/autobaud callback during data transfer. Reports include the
chassis wire value and actual working mode to make the enum distinction
visible. Regression tests execute all six values through the original setter.

The passing run exchanges 288 100-ms frames in each direction. Quad stays
connected at 100M CPU instructions. The caller's post-termination ATI6 reports
21 characters sent/received, zero lost, zero retransmitted blocks, retrains,
link timeouts and link NAKs; it also retains 86 blers. That counter is not
silently relabeled or treated as proof of an error-free line. Full-rate,
binary-DTE and multi-minute Quad traffic remain unverified. Symmetric x2 is
now verified by the later control below; asymmetric x2 remains unresolved.
The shared I-modem x2 five-second traffic control still passes after the
handoff change.

### Terminal receive backpressure

The byte-terminal adapter now waits for both a free interrupt latch and a
consumed UART receive buffer. Dispatching an interrupt clears its pending
request before the ISR necessarily reads S0RBUF; treating that as permission
to deliver another byte could overwrite unread input. This is host-adapter
backpressure, not a change to the UART's hardware overrun semantics or guest
callbacks. Regressions exercise delayed reads and all 256 octet values.

A fresh `--check-data` V.34 control with twelve distinct 19-character records
per direction delivered all **228 ASCII bytes each way**, kept Quad carrier
active through 100M instructions, and recorded zero CPU/DSP errors, UART
overruns or PCM underruns across 288 media frames. Reproduce with:

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --imodem-send "$(printf 'I%03dabcdefghijklmno' {1..12})" \
  --quad-send "$(printf 'Q%03dzyxwvutsrqponml' {1..12})" \
  --check-data --output /tmp/quad-reliability-long-payload
```

This remains a bounded ASCII call test, not binary interoperability or a
multi-minute throughput soak. The all-octet regression tests adapter delivery
only, not the complete modem link.

## Working symmetric x2: genuine feature provisioning

The Quad and I-modem now both report **`CONNECT 64000/ARQ/x2/LAPM`** and
deliver both distinct 24-character payloads. The strict carrier, x2 and data
checks all pass; neither endpoint has CPU/DSP errors, PCM underruns or UART
drops. No carrier, callback, quality flag or payload is injected.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --settings 'S54=0S58=50&M5&K0' \
  --quad-terminal-init 'Q0V1&A3S76=131S81=32' \
  --quad-feature-mask 0x20 \
  --imodem-send X2-IMODEM-TO-QUAD-482619 \
  --quad-send X2-QUAD-TO-IMODEM-731954 \
  --check-x2 --check-data --output /tmp/quad-x2-symmetric
```

Two further missing harness inputs became visible after the V.34 fix:

- The longer AT setup was interrupted by the old fixed 4M-instruction chassis
  deadline. The probe now waits for the real parser's complete OK, empty UART
  and idle receiver. `initialization_completed_at` records completion before
  the first frame. Failed/unfinished setup cannot pass the verifier.
- S76 selects available roles but does not provision the local x2 feature.
  The original diagnostic routine checks `8838 & 20` first. The actual setup
  audit reads `8838=cf`, with that gate unset. Original type-1 **parameter
  `01f2=20`**, dispatched at `f4889` to `f3b2:4dbb` (`f88db`), makes firmware
  set that gate. The provisioned call has `8838=ef`, genuinely sends DSP
  configuration `0070:69fd`, and selects symmetric descriptor `8954=04`.

S76 bits 1/2/4 are **disables**, not enables: 131 = high-power constellation
128 + disable client 1 + disable server 2, leaving symmetric mode available.
S81=32 disables V.90 server mode. The caller's S58=50 leaves symmetric x2
available with high-power constellations, but disables V.90 and its asymmetric
server availability.

The [symmetric control](../artifacts/quad-x2-symmetric-provisioned/README.md)
also passes with `&B0`. It is a negotiated 64k x2 link with short ASCII data,
not a measured 64-kbps application soak. ATI6 retains one bler and an
inconsistent speed display (`02400/64000`), despite both genuine 64000/x2
CONNECT results. Neither diagnostic is silently corrected.

### Earlier digital-to-digital asymmetric role controls

| Quad role | S76 / caller S58 | Measured result |
|---|---|---|
| symmetric | 131 / 50 | Both 64000/x2/LAPM and both payloads |
| server | 133 / 58 | V.34 fallback or no caller CONNECT; no x2 |
| client | 134 / 56 | No caller CONNECT; no x2 |

The variable-DTE captures remove the fixed-9600 limiter using normal `&B0`
(`89b2=0`). Replaying the original status routine on their saved fields gives
**Excessive high frequency attenuation** for server (`895f=013f`) and
**Incompatible x2 modes** for client (`895f=0007`). The latter test still has
an originating I-modem and answering Quad; it does not prove that a correctly
selected reverse-role client topology cannot work. Follow the asymmetric
quality/role producers next, not the already-working LAPM handoff.
See the [complete role controls](../artifacts/quad-x2-modes/README.md).

`--check-x2` rejects V.34 fallback and transparent `/DIGITAL`, requiring x2
in both original CONNECT results. `connect_verified`, `x2_verified` and
`data_verified` are independent evidence fields; any requested failure is
still fatal. `--trace-negotiation` retains the caller's capability/rate-mask
commands. The default pair remains a V.34 control; x2 provisioning is explicit.

## Three-minute 9600 control and high-rate PCM fix (2026-10-18)

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --settings 'S54=0S58=43&M5&K0&N6' \
  --traffic-seconds 180 --traffic-size 64 --quad-dsp-slice-cycles 512 \
  --check-connect --output /tmp/quad-soak-9600
```

Both original terminals report 9600/ARQ; the caller explicitly identifies
V.34/LAPM. Both complete 180 connected
bearer seconds without corrupt records, UART loss, native C5x receive-FIFO
underruns or CPU/DSP faults. The windows contain 70 complete records at the caller and 71 at Quad;
after the short drain **71 complete records (5893 bytes) arrive each way**,
with one final Quad record still partially in flight. The maximum receive
gaps are 4.1 and 2.9 seconds, including initial latency. This is a paced
stability test (about 33 application bytes/s), not a 9600-bps throughput
benchmark. The ordinary AT `&N6` setting caps the negotiated rate; no modem
state is forced. [Original reports and replayable verification](../artifacts/quad-traffic-and-asymmetric-x2-20261018/README.md).

The optional 512-cycle runtime service batch reduces native crossings while
preserving the cycle debt and yield-on-every-PCM-sample primitive. Boot and
host download windows retain their 64-cycle pacing. A separate 30-second
9600 control also passes with the default 64-cycle runtime batch.

This sends deterministic numbered records in both directions, checks every
received character, bounds outstanding input, and measures time from the
actual CONNECT at each terminal. Health is snapshotted before intentional
worker shutdown, with a short drain afterward. Since the two CONNECT results
can arrive in different media frames, record conservation is checked against
actual drained bytes, not mismatched window-end snapshots. Verification requires both
requested durations, at least ten intact records each way, no traffic gap
over five seconds, retained carrier, and no UART loss, CPU/DSP error or PCM
underrun. Failed setup and incomplete windows cannot pass. A five-second
receive stall fails early, preserving progress and Quad RAM for diagnosis.
Traffic currently requires the default 100-ms bearer frames.

**The original default-rate test failed (before the PCM fix below).** The 64-character-record control delivers
332 verified application bytes to Quad, but the caller receives only 260
bytes (three complete 83-byte records plus an 11-byte prefix). Quad carrier
and UART reception remain active; all queued DTE bytes are consumed, with
zero UART overruns and native C5x receive-FIFO underruns. A 16-character-record control also
stalls. Thus the earlier short ASCII controls are not sustained-throughput
proofs. See [the captured failure](../artifacts/quad-traffic-and-asymmetric-x2-20261018/README.md).

`--trace-data-lanes` captures both DSP host interfaces without the expensive
full DSP memory trace. `traffic-progress.json` and
`imodem-traffic-progress.json` retain bounded traffic/UART/receiver history.
The latter confirms the caller still has its normal `46cc` DTE receiver.
Analyze captures offline with:

```sh
PYTHONPATH=. .venv/bin/python tools/inspect_quad_hdlc.py \
  /tmp/quad-soak/quad/data-lanes.json --output /tmp/quad-hdlc.json
```

After V.42 detection, the bank interface changes from packed bits to framed
octets. RX `1000` terminates a frame including its received FCS; TX `10f3`
terminates host octets whose FCS the DSP generates. The inspector distinguishes
these phases and never claims to verify a TX FCS absent from the capture.
In the failure, 279 received frames have valid FCS. Quad transmits 275
single-byte I-frames; the caller's final acknowledgement is N(R)=4, leaving
15 outstanding I-frames N(S)=4..18 after sequence wrap. This identifies the
LAPM window blocking further input. A second, simultaneous caller DSP trace
shows 273 valid received frames, followed by corrupted frames beginning at
media frame 250, already before supervisor LAPM processing. Its normal DTE
receiver remains installed. This points back to the high-rate V.34 signal/
receive path, not permission to patch sequence numbers, acknowledgements or
callbacks. The I-modem capture can be inspected with `--rx-delimiter 0xff00`.
A normal `&N6` caller setting negotiates 9600 and passes a 30-second traffic
control (12/11 intact records, no corruption or health failures); see the
linked evidence. Faster host pacing alone does not cure the default-rate
receive corruption.

`--quad-online-byte-interval` makes the byte adapter's instruction spacing
explicit (default 100000). It changes online host pacing only, not command
handling, UART overruns, firmware, DSP clocks or negotiated rates. Faster
pacing is an experiment, not a claim of physical baud accuracy or a fix to
the original LAPM failure.

### Root cause and correction: an inserted PCM sample

The PCM ring ownership trace finds no stale TX slots, overwritten RX samples
or ring-order errors in either DSP. Comparing the actual octets across both
ends, however, identifies one inserted `ff` sample on **Quad → I-modem** at
Quad TX capture offset **198750**. The reverse direction is byte-exact.
The insertion aligns with the caller's AM79C30 MUX underrun at bearer frame
**199200**; its native C5x receive-FIFO underrun counter remains zero because
the MUX explicitly supplied silence. The single sample slip explains the
subsequent bad HDLC FCS and blocked LAPM window.

The synchronous packet peer now requests **per-PCM-frame media service**.
`IsdnMachine` drains completed TX blocks and delivers their replies before
advancing into the next MUX RX frame, rather than waiting for the next
supervisor timer poll. No DSP clocks, firmware negotiation, carrier flags,
acknowledgements, guest callbacks or payloads are changed. Traffic-window
health now checks MUX underruns as well as the native receive FIFO.

The default 64-cycle, uncapped 31.2/33.6k run passes **30 connected seconds**,
with **12 complete records / 996 bytes drained in each direction**. A faster
256-character-record run also passes **60 connected seconds**, draining
**53 records / 14575 bytes to the caller** and **52 / 14300 to Quad**, with
retained carrier and no parser errors, UART loss or MUX/native-FIFO underruns.
The latter uses 10000-instruction byte spacing and 512-cycle runtime batches.
Both remain paced stability controls, not full-rate DTE throughput benchmarks.
The previously failing 20-ms-frame control now negotiates **33600 at both
ends** and delivers both distinct 630-byte markers intact.
[Before/after evidence and replay](../artifacts/quad-traffic-and-asymmetric-x2-20261018/pcm-slip-fix/README.md).
The focused regression reproduces silence insertion with timer-poll-only
service and preserves every source octet with frame service, using both
Python and native bearer queues.

For deeper diagnosis, `--snapshot-frame` captures mapped program/data plus
live registers. Add `--snapshot-read-range bd0:bdf` with two frame arguments
to trace the PCM ring between them, then compare the paired traces with
`tools/inspect_quad_pcm_ring.py --peer-trace ...`.

## Asymmetric x2 with an analog client (2026-10-18)

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_analog_pair.py \
  --check-x2 --output /tmp/quad-asymmetric
```

The digital Quad server reports **33333/ARQ/x2/LAPM**; the original analog
Courier reports **52000/ARQ/x2/LAPM**. Both distinct ASCII payloads arrive
intact, both retain carrier, and both finish at frame 3000 of a shared 20-ms
line (60 seconds including startup/training, **not** 60 connected seconds).
Quad has zero PCM underruns/UART overruns; the analog endpoint has zero
connected receive underruns. No CPU/DSP error occurs. Its aggregate codec
empty-frame counter retains 149 startup events; that is not silently zeroed.
The original firmware selects descriptor `8954=01` and reports `895f=00ff`.
[Full evidence](../artifacts/quad-traffic-and-asymmetric-x2-20261018/README.md).

The new `QuadLinePeer` reuses the calibrated exchange codec/levels from
`BearerLineLink`, carries each sample over the existing analog socket line,
and reserves one frame of transit delay. Opening PCM does not answer a call:
the chassis answer is deferred until a real incoming ring, and line answer
is signalled only after QF reaches its genuine acceptance path at `c7d3f`.
Both workers stop at the same line-frame boundary, avoiding a misleading
NO CARRIER caused solely by one worker running past the other's exit.

The older forced-role tests connected two digital server-family products.
Reducing their exchange delay to 20 ms still gives `895f=013f` and no x2.
Vendor documentation identifies the Quad/I-modem as servers and explicitly
says the Quad does not support client mode; the available S76 client bit is
not proof of an implemented client personality. Use an actual analog client
for asymmetric server verification, and keep the existing digital pair for
symmetric x2. This new result is a bounded short-data asymmetric server
control, not binary interoperability, a throughput soak, or a verified Quad
client implementation.
