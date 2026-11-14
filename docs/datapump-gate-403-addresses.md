# How the datapump gets armed

Before, the datapump never started. Now it starts, by two independent routes.
The gap that remains is after the arming. This is the full chain, in 403
addresses, with the 302 counterparts next to them.

Two later sections contain the downstream work. The first is "Overlay 8 is
loaded and never entered". It follows one overlay entry to its gate and finds
that the gate is **correct**. The second is the corrected ampersand handler
table. It corrects an indexing error of eleven entries that gave incorrect
names to commands.

## Answered: an answered call arms it from the DSP, in one message

We used a real peer: two `courier run` instances on one line socket. A
originates and B answers. With `--line-audio-only`, the bridge injects nothing
at all. On this peer, the answering side carries exactly one message:

```text
0047:0007
```

**Tag `0x47`, data `0x0007`: the DSP asks for overlay 7.** Fifty-nine
instructions later, the supervisor starts to fetch it:

```text
94d83  ovl-from-5c   @53,010,564    in al, 0x5c -> 07, force bit 7 -> [0x0d28]
8e60f  id-after-mask @53,010,610    al = 07      (after the loader's and al, 0x7f)
8e631  xfer-start    @53,010,623    ax = bx = b000, out 0x1e, 4
```

`b000` is the documented load address of overlay 7 in
[dsp-overlays.md](dsp-overlays.md):

| overlay | flash range | bytes | C52 load address |
|---|---|---|---|
| 6 | `36e90..3d0f4` | 12,594 | `9d00` |
| **7** | `3d100..40b94` | 7,498 | **`b000`** |
| 8 | `40ba0..44634` | 7,498 | `dc00` |

Thus the chain is correct and consistent from one end to the other. No part of
it needs a command, a profile setting, an NVRAM fixture or leased-line mode:

```text
peer answers
  -> the DSP sends 0047:0007
  -> 0x94d83 reads 07 off port 0x5c, forces bit 7, stores [0x0d28]
  -> loader 0x8e60a masks to 7, indexes cs:0xe741, resolves b000
  -> out 0x1e, 4 starts the transfer at 0x8e631
  -> 1874 blocks, four words each, acknowledged 1 / 2 per half-block
  -> 14,996 bytes, matching the ROM, published at b000
```

The consumer forces bit 7. This bit marks the id as a DSP request for the
`and al, 0x7f` of the loader. The DSP does not send the bit set.

The trace record of `0x94d83` has `ret_seg 0000`, `ret_off 006d`. This is not a
possible return address. It agrees with the indirect dispatch that prevented
all static searches from finding its caller. The firmware dispatches to it. It
does not call it.

## The second route: `&L1`, leased-line mode

`AT&L1` writes `[0x04f2] = 1`. When `[0x04c6]` bit 6 is clear and `[0x04f8]`
is zero, the **CF gate** at `0x8b8a1` passes. These two conditions are both
true at rest. The path then gets to `0x8bc06`, `mov byte [0x0d28], 6`, through
the branch at `0x8bbf6`. That branch does not use the three-flag discriminator
at all.

We measured this on the board. The measurement was read-only, except for the
setting itself, which we restored:

```text
before     04c6=00 04f2=00 04f8=00    CF gate fails
AT&L1      04c6=00 04f2=01 04f8=00    CF gate PASSES
AT&L0      04c6=00 04f2=00 04f8=00    CF gate fails
```

In the emulator, we used `AT&L1` together with `--exchange-hotline`. The
exchange answers on seizure, with no dial tone and no digits. This is the shape
that leased-line mode expects:

| | plain dial | `&L1` + dial | **`&L1` + hotline** |
|---|---|---|---|
| exchange | ringback | `reorder` | **`answer`, `connected`** |
| `cf-gate` `0x8b8a1` hits | 3 | 2 | 2 |
| `set-ovl-6` `0x8bc06` | 0 | 1 | 1 |
| `overlay-loader` `0x8e60a` | 0 | 1 | 1 |
| **`xfer-start` `0x8e631`** | 0 | - | **2** |
| transmit samples | 66,078 | - | **350,273** |
| **nonzero** | **3,669** (DTMF bursts) | - | **291,175** |
| peak | 22,764 | - | 15,424 |

The line output changes from isolated DTMF bursts to a continuous signal. 83%
of the samples are nonzero, against 5.5% for a dial. A Goertzel sweep of three
windows puts the energy at **1800 Hz**, with sidebands at 1600 and 2000. This
is a modulated data carrier, not a tone. (This reading uses the 7200 Hz codec
rate that this project infers in other documents. At a different rate the
figure scales, but it stays in the data-carrier band and far from DTMF.) The
first window is silent. Thus the carrier starts after some time, as a
handshake does.

## Where the three flags actually come from

The discriminator at `0x8b88d` tests three flags. The long search for the code
that sets them has an answer: **operator commands, not the dial path.**

The handler table at `0xa669b` is the **ampersand** command family, not the
bare AT letters. This is why `ATL` and `ATN` got to nothing. The shared entry
`a6780` is `stc; ret`, a real reject. The letters that it does not reject are
`A B C D F G H I J K L M N P R S T U W X Y Z`. This is exactly the ampersand
set, without `&E`, `&O`, `&Q` or `&V`. The `ATI5` switches of the board are a
subset of it.

| entry | command | what it does |
|---|---|---|
| 11 | **`&L`** - leased line | writes `[0x04f2]`, range `< 2` |
| 13 | **`&N`** | writes `[0x04f8]` |
| 19 | **`&T`** - test | the router: `AL` 0..8, **`AL=2` rejected** |

The shape of `&T` confirms itself. The USR `&T` accepts 0-8, and these modems
do not use `&T2`. The nine-entry table of the router rejects exactly `AL=2`.
We tested this on the board:

| command | board | why the model says so |
|---|---|---|
| `AT&T2` | **`ERROR`** | entry 2 of the table at `0xa6b70` is the `stc; ret` reject |
| `AT&T3` | **`ERROR`** | `a6b1a` rejects `AL` 3, 6 and 7 when `[0x0237] & 1`; the board reads `[0x0237] = 01` |
| `AT&T0` | `OK` | `AL=0` dispatches at `a6b43` before the flag tests |

Thus `&T1` sets flag C, and `&L1` opens the parallel CF gate. Both are operator
commands. **`&T1` is an analog loopback**: the modem trains against itself.
This is a full datapump exercise with no far end and no phone line.

The firmware gets to the router through a RAM function pointer, not a direct
branch. The firmware calls `[0x03ff]` at `0x90ef1` and at `0x92004`
(immediately after `out 0x1c` / `out 0x1e`, the ASIC mailbox commit).
Approximately eighty-eight installer sites write it. One of them is:

```text
910c6  cli
910c7  mov word ptr [0x3ff], 0x1cde     ; = a4e2:1cde = a6afe, the router
910cd  mov byte ptr [0x403], 0x64
910d2  mov word ptr [0x192], 0x1cca
910d8  sti
```

Also, no code branches to `0x910c6`. This is not the anomaly that it seems to
be: only 19 of the 87 installer sites have a direct branch to them. Indirect
dispatch is normal for this family.

## The 302/403 address map

We scanned the two images for the shape of the discriminator:
`test byte [imm16], 2`, then two `test byte [imm16], 1` and a `ret`. The scan
gives exactly one counterpart, at `+0x3e` from the 302 site. In the two
images, the CF gate and the overlay loader come immediately after it, in the
same order.

| role | 302 | 403 |
|---|---|---|
| discriminator | `0x8b84f` | `0x8b88d` |
| CF gate | `0x8b863` | `0x8b8a1` |
| dispatch site (`mov ax,0x10`) | `0x8bee8` | `0x8bf34` |
| overlay loader | `0x8e5da` | `0x8e60a` |
| flag A, tested `& 2` | `[0x0a96]` | `[0x098a]` |
| flag B, tested `& 1` | `[0x05a5]` | `[0x049e]` |
| flag C, tested `& 1` | `[0x0685]` | `[0x057c]` |
| CF gate cells | `[0x05cd]`, `[0x05fa]`, `[0x0600]` | `[0x04c6]`, `[0x04f2]`, `[0x04f8]` |
| overlay id | `[0x0e3c]` | `[0x0d28]` |
| dispatch data cell | `[0x0281]` | `[0x017b]` |
| thunk stubs, stride 4 | `0x875d8` | `0x87622` |
| entry 1 handler | `0x876b1` | `0x876fb` |
| the setter it reaches | `0x876c5` | `0x8770f` |
| indexed jump | `0xa6ad7` | `0xa6b69` |
| jump table, nine entries | `0xa6ade` | `0xa6b70`, CS `a4e2` |
| router entry | `0xa6a6c` | `0xa6afe` |
| decimal parser | `8000:9cbc` | `8000:9ce7` |
| handler-offset table | `0xa6615` | `0xa669b` |
| rejects `AL=1` when set | `[0x0ea7]` | `[0x0d93]` |

Flag B has an independent cross-check. The unrelated routine at 302 `0xa5602`
tests `[0x5a5] & 2`, and its 403 counterpart at `0xa562d` tests
`[0x49e] & 2`. The contents of the 403 loader also confirm the map. It reads
`[0x0d28]`, compares it with 6, writes the cell again as 8, indexes a table
with a six-byte stride at `cs:0xe741`, and starts the transfer with
`out 0x1e, 4`. Each instruction agrees with the 302 loader, with `[0x0e3c]`
and `cs:0xe711`.

## The overlay id has six writers, and three ignore the flags

| site | write | reached by |
|---|---|---|
| `0x8bc06` | `6` | the **CF gate** returning carry - not the discriminator |
| `0x8bc8d`, `0x8bc99` | `6`, `7` | inside the discriminator-gated selection block |
| `0x8b7db` | `5` | gated only on `[0x0d92] & 4`, outside both |
| `0x8e616` | `8` | the loader itself, chaining `6` to `8` |
| `0x94d87` | `al` | **`in al, 0x5c` then `or al, 0x80`** - the DSP-requested route |
| `0x8e73a` | `0` | teardown |

## The counter route exists and is disabled by default

There is a third structure. It is important to know about it, because it
seems to be the answer, but it is not. When `[0x0b9e]` gets to 5, the firmware
loads overlay 5:

```text
8b7a2  mov  word [0x134], 0x2760      ; a countdown
8b7a8  mov  byte [0xb9e], 0           ; the counter, cleared
8b7ad  cmp  word [0x134], 0
8b7b2  je   8b7cb                     ; countdown expired -> the [0x0d92] probe
8b7b4  test [0x225], 0x80  / jne 8b803    ; abort
8b7bb  test [0xa7c], 0x20  / jne 8b803    ; abort
8b7c2  cmp  byte [0xb9e], 5
8b7c7  jb   8b7ad                     ; keep waiting
8b7c9  jmp  8b7db                     ; reached 5 -> overlay 5, loader
```

`0x94fdc` supplies the counter. It does `test ah, 1`, then either
`inc byte [0xb9e]` or `mov byte [0xb9e], 0`. Thus it counts **consecutive**
successes, with `AH` from `in al, 0x5e`, the DSP mailbox. The same module has
the corroboration: `0x94dc1` writes `mov word [0x192], 0x5742`, and `5742` is
exactly the off-hook state value that we measured on the board. Thus this is
the live call-progress state machine.

**But the two call sites are both gated**: `0x94ddc` on `[0x0d93] & 1` and
`0x94e07` on `[0x0d92] & 1`. The board reads the two cells as `00`. On the
two-instance link, side A polls `0x5e`/`0x5c` 536 times at `0x94dc8` and never
calls `0x94fdc`. Thus the poll is disabled by default, and this is *a* route to
overlay 5, not the normal route. The earlier search followed the `[0x0d92]`
probe. That probe is the **timeout** branch of the countdown, a fallback.

## Measured on the board: all seven gate cells are zero at idle

We read these values on 2026-09-09 from the Courier on
`/dev/cu.usbserial-11420`, ID_SDL 4.03d, in command mode. The read was
read-only, in two passes with identical page hashes:

| `098a` | `049e` | `057c` | `04c6` | `04f2` | `04f8` | `0d28` |
|---|---|---|---|---|---|---|
| `00` | `00` | `00` | `00` | `00` | `00` | `00` |

The pages are live, not a failed read. `0400`, `0900`, `0c00` and `0d00` have
51, 54, 60 and 15 nonzero bytes, and `0cd9`/`0cdb` read `32c8`/`0c08`.

**This result rejects the provisioning hypothesis for this gate.** The
tone-gain cells had values on a board that had them, and were blank in an
emulator that did not
([datapump-dispatch-gate.md](datapump-dispatch-gate.md)). These cells are also
blank on the working board. Thus they are not stored settings that the
emulator does not supply. A command sets them, or nothing sets them.

[Capture](../artifacts/datapump-gate-403-cells/cells.json),
[script](../artifacts/datapump-gate-403-cells/read-cells.py).

## What the board itself shows

**The state pointer of the supervisor moves, and the firmware never installs
the router.** We sampled continuously during an `ATDT9099;` dial (command
mode, line seized, no handshake). There were fifteen samples in 29 s:

| phase | `[0x0192]` | `[0x03ff]` | gate cells |
|---|---|---|---|
| idle, x2 | `0110` | `0000` | all zero |
| off-hook, x13 over 20 s | **`5742`** | `0000` | all zero |
| after release | `0110` | `0000` | all zero |

This is the first direct observation of the supervisor state machine of the
board. It gives a baseline for the emulator: **a 403 dial must get to `5742`
and go back to `0110`.** `[0x03ff]` stays `0000` all the time. Thus the
firmware never installs the router on this path. This agrees with the gate
cells, which never move.

> **Resolved 2026-09-19.** The capture labelled each pointer as `a4e2:value`,
> because the installers write `a4e2` offsets. That label failed for `5742`:
> the implied `aa562` is garbage. The segment is not `a4e2`, and it does not
> change. The firmware calls `[0x192]` with `call word ptr [0x192]` at
> `0x8f4c9`. This is a **near** call, thus the firmware reads it in the
> **CS `0x8f46`** of the caller. Then the two recorded values decode as the
> same four-instruction state stub:
>
> | `[0x192]` | under `0x8f46` | |
> |---|---|---|
> | `0110` | `0x8f570` | `mov bx,0x121 / mov cx,5 / mov di,0x11c / jmp 8f77a` |
> | `5742` | `0x94ba2` | `mov bx,0x56f4 / mov cx,0x24 / mov di,0x56d0 / jmp 8f77a` |
>
> Thus you can use the `5742`/`0110` capture of the board directly as a state
> trace, and `0x94ba2` is the off-hook state. Its 36-tag dispatch table, and
> the actions of the supervisor for each event, are in
> [who-produces-the-events.md](who-produces-the-events.md#the-consumer-side-what-the-supervisor-does-with-an-event).

**`&L1` alone has no effect.** We sampled for 20 s with the setting live:

| | `[0x04f2]` | `[0x0d28]` | `[0x0192]` |
|---|---|---|---|
| before | `00` | `00` | `0110` |
| `&L1` live, x11 over 20 s | **`01`** | `00` | **`0110`** |
| after `&L0` | `00` | `00` | `0110` |

The board accepts the command and keeps it, and nothing else moves.
`[0x0192]` never leaves the idle state. This does not contradict the
emulator. `&L1` selects leased-line mode. It does not start a connection. The
two emulator runs both included a connection attempt (`ATDT6245` in one, and
the hotline exchange that answers in the other). **The firmware writes the
overlay id during a connection attempt**, in leased-line mode and also in a
normal call.

This is the limit that all bench routes here get to. The cells move only in
the window that the DTE cannot read. A connection attempt takes the serial port
out of command mode, and `+++` aborts the attempt. It does not escape to
command mode. During a real call, the seven gate cells read `00` at each
sample: idle, off-hook, dialling, ringing during 6 s, and after release.

### The hand-armed tone works end to end, and the ear was the instrument

Three eight-digit `ATG` commands, in command mode, with no call and no dial
sequencer, put the DTMF of the firmware on a live line. **The operator heard a
DTMF tone for approximately ten seconds.** This is the length of the armed
window. The tone stopped when we sent tag `16`. Thus the resident arms tag
`13` correctly outside a call, the oscillator runs, and the tone gets to the
line.

**WARNING: When you arm a tone off-hook on a connected line, you put a real
signal on a real loop. The window ends only when you send tag `16`.**

### Query 62 cannot observe the transmitter

`62` sums the squares of `0900..098f`. This seemed to be a receive-energy
reading that could possibly be a transmit-side observable. It is **pinned**:

| point | query 62 |
|---|---|
| on-hook baseline | `0069:0015` |
| off-hook, dial tone, x3 | `0069:0015` |
| off-hook, tone armed, x4 | `0069:0015` |
| off-hook, after tag 16 | `0069:0015` |

Dial tone is a large known signal in the receive path, and query 62 does not
move for it. It also does not move for a tone that is loud enough to hear. It
is not an energy detector that is quiet on hook. It always returns `0015`.

**This has a consequence for
[mailbox-312-comparison.md](mailbox-312-comparison.md).** That file records
that the emulator gives `0069:0015`, and it counts this as a match with the
board. It also treats the resolution of an earlier `0012` discrepancy as a
result about initialization. A match with an unconditional constant confirms
the mailbox transport and the dispatcher. It gives **no** information about the
sample arithmetic of the handler. The caution in that file is correct, but it
is not strong enough.

### No tag returns transmit-side state

We swept all 128 entries of the 3.1.2 dispatcher table at program `0x83e9`.
First, we had to find the reply convention, and it is not the obvious one.
Handlers do **not** call the sender at `0x83bf`. They enqueue the value: they
call or do a delayed branch to `0x83b1`, the tail of `0x83a6`, with the value
in ACC. Thus, on a delayed branch, the handler loads the value in the delay
slots *after* the branch. That routine pushes into a ring masked by
`ar0 = ff60`, with head and tail at data `0x78`/`0x79`. `0x83bf` drains the
ring, masks with `0x7fff` and writes to ports `0x5e` and `0x5f`.

Twenty tags reply: `07 14 23 24 28 29 2e 2f 32 33 34 3b 3d 4b 55 59 5a 5f 62 7f`.
Each one returns a constant tag word together with a status cell, or a value
calculated from receive-side analysis. **None replies with a value that it
reads from the transmit block.** This includes the `0390` work pointer, `0392`
gain, `039a` callback, `03c0`/`03c1` phases, `03c7` mixer accumulator,
`03f1..03f5`, the transmit slots of the buffer at `0bc0..0bde`, and `DXR`.
Many handlers *touch* transmit cells: `13`, `1a`, `1b`, `16` and the
overlay-resident tags at `20..25`, `2e`, `2f`, `32..34` all write them. But
they are setters, not readers.

Thus the transmit-side read that this project wanted **is not a tag in this
image**, and no experiment can use one. An earlier pass reported tag `01`, and
then `55`/`59`/`5a`, as candidates. Both were artefacts. The first followed a
jump into the main loop and took its references. The second read
`bit 1, @1f` incorrectly as the reply value. That is a status word at `039f`
with twenty-five writers. Those handlers reply with the constants `#06` and
`#04`.

[Sweep](../artifacts/dispatcher-tag-sweep-312/sweep.py),
[table](../artifacts/dispatcher-tag-sweep-312/replying-tags.json),
[tone capture](../artifacts/atg-tone-offhook-403/tone.json).

## Overlay 8 is loaded and never entered

The overlays download and pass verification. Overlay 8 does not run. We
measured this on a leased-line pair, 403 image, `--line-audio-only`, 400M
instructions for each side:

```text
overlay_destinations      ['9d00', 'dc00']
overlay_match             True
overlay_words_verified    20096
```

A trace of DSP program `dc00:ffff` for the full run gives **zero** entries.
The trace records each PC in the band. Thus this result means that the code
never executes. It is not a sampling miss. During this time, overlay 6 is
busy. The last 512 PCs in `9c00:dbff` cover 169 different addresses. These
include a straight-line block of approximately 130 addresses at
`0xa0e6-0xa20f`. This block runs on each pass and has the shape of a filter
kernel.

### The one door that was traced end to end

Eleven entries in the dispatch table at program `0x83e9` go into overlay 8:
tags `0x18`, `0x20`-`0x27` and `0x75`. The resident has one direct branch:

```text
8fce  481f       bit  7, @1f      ; BIT code 7 tests bit 8
8fcf  e100 9093  bcnd 9093, tc    ; set   -> overlay 8
8fd1  ...                         ; clear -> call 96af / call 9705
8fd5  7980 9d34  b    9d34        ;          ...into overlay 6
9093  ae4d ae1e  splk @4d, #ae1e
9095  7a80 90e8  call 90e8
9097  7980 dc0c  b    dc0c        ; the entry into overlay 8
```

Only one item sets bit 8 of that cell: the mailbox handler at `0x823d`,
`ldp #007 ; opl @1f, #0100`. Thus the cell is **data `0x039f`**. The
`lar ar1, #039f` at `0x9041` corroborates this. A reverse map of the table
gives its tag, and the two adjacent handlers that clear the same bit:

| handler | tag | effect on `0x039f` bit 8 |
|---|---|---|
| `0x823d` | `0x4f` | **set** |
| `0x8245` | `0x4e` | cleared |
| `0x824d` | `0x4d` | cleared |

On the supervisor side, one selector makes those three tags. It is at
`0x84749` and also at `0x8be6f`:

```text
8be5f  cmp byte [0x4e9], 5
8be64  ja   8be6f          ; >5  -> emit
8be66  cmp byte [0x4e9], 1
8be6b  je   8be6f          ; ==1 -> emit
8be6d  jmp  8be8b          ; else -> ret, nothing queued
8be6f  mov  al, byte [0x4ed]
8be72  cmp  al, 1 / je -> mov ah, 0x4e
8be76  cmp  al, 2 / je -> mov ah, 0x4f
8be7a     (else)           mov ah, 0x4d
8be84  xor  al, al
8be86  lcall 8f46:01e8     ; 0x8f648, the outbox at [0x0183]
```

`AH` = tag, `AL` = data. A live run confirmed this: the firmware entered
`0x8f648` 11 times in one run with `AX` = `1500`, `433f`, `0100`, `0400`,
`463f`, `583f`. These agree with the tags on the ports. The pump at `0x8f487`
drains `[0x0183]` with `xchg` and shifts it out to `0x58`/`0x5a`/`0x5c`/`0x5e`.

### Why it does not fire, and why that is correct

`[0x04e9]` is `&M` and `[0x04ed]` is `&X`. Refer to the corrected table below.
`[0x04e9]` reads **4**. This is the factory default that the defaults block at
`0x878b7` writes, thus **`&M4`**. The gate needs `1` or a value above `5`:
`&M1`, `&M6`, `&M7`. Those are the **synchronous** modes.

Thus tags `0x4d`/`0x4e`/`0x4f` are the synchronous transmit clock source, `&X`
selects one of them, and the firmware sends the message only in sync
operation. Overlay 8 is the synchronous datapump, and **it is correct that an
async `&M4` call does not load it.** An earlier reading of this search called
`0x4f` "the missing datapump mode message", and treated the silence of overlay
8 as the bug. That was incorrect. The cause of the error was the command
table, which was misindexed by eleven entries.

To make sure that the cause is the gate and not reachability, we traced it:
120M instructions, `--nvram-fixture idsdl403`:

```text
pc_watch_counts: {'callerB': 1, 'entry': 1}    # 0x8b723 and 0x8be5f
                                                # 0x8be6f: absent, zero hits
peek: {'4e9': '04', '4ed': '02'}
```

The caller runs, and the firmware enters the routine. `[0x04ed]` is already
`2`, which means tag `0x4f`. The `&M` gate returns before the routine reads
it.

### The `&M` and `&X` commands cannot be changed on this board anyway

The two handlers start with `test byte [0x58b], 6 / je <reject>`. `[0x058b]`
reads `0x29`, and `0x29 & 6 == 0`. Thus `AT&M1` and `AT&M2` both return
`ERROR` (measured). `AT&M0` returns `OK` only because 0 is already the value.
The `--nvram-fixture idsdl403` profile restores `[0x04ed] = 2` directly, and
does not use the command.

`[0x058b]` has one writer, `0x809ee`. A hardware-indexed lookup supplies it:

```text
809cf  mov ax, 0x200a / call 82808
809d5  mov ax, 0x0804 / call 8283e
809db  rcl bx, 1                     ; a read bit shifted into the index
809dd  mov ax, 0x200a / call 827de
809e3  add bx, 0x9fd                 ; table base
809e7  mov al, cs:[bx]
809ec  je  809f6                     ; zero -> [0x58b] = 0, stc
809ee  mov [0x58b], al
```

The table is inline at `0x809fd`. Index 2 gives `0x29`, which is the value
that this board calculates. Seven of the twenty-four entries have the
capability:

| index | value | `& 6` |
|---|---|---|
| **2** | `0x29` | **0** - this board |
| 5 | `0x14` | 4 |
| 7, 11, 13 | `0x22` | 2 |
| 17 | `0x3e` | 6 |
| 19 | `0x04` | 4 |
| 21 | `0x75` | 4 |
| 23 | `0x33` | 2 |

**Not verified:** we did not trace the three accessor calls. Thus it is not
known if index 2 is correct for this board, or if it is an artefact of the
values that the emulator returns to them. This question decides if this is a
firmware gate to satisfy or an emulator gap to correct.

### The corrected ampersand handler table

The table is indexed by letter, and its base is **`0xa6685`**, not `0xa669b`.
Entry 11 is at `0xa669b`. If you read it as entry 0, each letter moves by
eleven. Four independent anchors set the base:

* `&L` (11) writes `[0x04f2]` at `0xa6980`, in the handler at `0xa695e`;
* `&N` (13) writes `[0x04f8]` at `0xa6a71`, in the handler at `0xa6a11`;
* `&T` (19) is the router at `0xa6afe`, which the board verifies with
  `AT&T2` -> `ERROR`;
* the four `0xa6780` `stc; ret` rejects are on **E, O, Q, V**. This is exactly
  the set that this file already records. With the old base, they were on D, F
  and K.

| entry | cmd | handler | |
|---|---|---|---|
| 11 | `&L` | `a695e` | writes `[0x04f2]`, leased line |
| **12** | **`&M`** | `a6987` | writes `[0x04e9]`; accepts `al < 6`, or `< 8` when `[0x58c] & 0x10` |
| 13 | `&N` | `a6a11` | writes `[0x04f8]` |
| 19 | `&T` | `a6afe` | the test router |
| 22 | `&W` | `a6c51` | the NVRAM save sequence |
| **23** | **`&X`** | `a6c88` | writes `[0x04ed]`, range `< 3` - the sync clock source |

4, 14, 16 and 21 (`&E`, `&O`, `&Q`, `&V`) share the reject stub at `0xa6780`.

### What this does and does not settle

It explains overlay 8, and it shows that the behaviour is correct. It does
**not** explain the measured starvation in
[what-runs-and-what-blocks.md](what-runs-and-what-blocks.md). The outbound ring
at `0x0bd0` stays empty, `@78 == @79`, and the DSP sends one message for each
call while it runs overlay 6 all the time. The async event producer is in
overlay 6 or the resident. To find it is the open question. The other ten
overlay-8 tags are a distraction for the same reason as tag `0x4f`.

## What remains

Two stand-ins are below the working download. [dsp-overlays.md](dsp-overlays.md)
records both:

- the `0x1e` readiness bits answer all-ones, thus the transfer never waits;
- `load_program` bypasses the C52 code (unknown) that receives an overlay while
  the resident runs.

Also, `call_overlay_active` is still false on the `&L1` hotline run, where
`bootstraps` stays 1. That route gets to `out 0x1e, 4` two times, and no
second download completes. The DSP-requested route now completes it. It is not
settled if the two routes must use one transfer path.

## Ruled out - do not re-run these

**"Nothing indexes that table, so the gate is on a dead path."** We got this
result two times, independently, on the two images. The searches looked only
for *direct* references: an indexed `jmp`/`call` with the displacement of the
table, a far pointer, an immediate load of its address. This firmware
dispatches through RAM function pointers. Both times, the search was too
narrow. Because the negative occurred again on a second image, it seemed to be
a property of the firmware. It was a property of the method.

**Reading the `0xa669b` table as the bare AT letters.** First we identified its
entries by position as `L`, `N` and `T`, from the data that each handler
writes. Tests on the board show that the ordinary letters do not get to it.
This firmware has no `ATL` and no `ATN`, and `AT$` is HELP. The table is the
**ampersand** family. Thus entries 11, 13 and 19 are `&L`, `&N` and `&T`. The
reading by position was correct, and the family was incorrect.

**Reading `0xa669b` as the table's base.** It is entry 11. If you index from
it, each letter moves by eleven, and handlers get incorrect names with no
warning. This error once changed `&X` into `&M`. The base is `0xa6685`. Refer
to the corrected table above.

**Reading `ATN` as the arming command.** The 403 `7b`/`7c` consumers get to a
rate-index request through operation `0054`, not through these flags. The two
decimal command parsers have the same shape, but this is about method, not
about this gate.

**`0008:0885` as the overlay request.** That reading used two facts: `0x85` is
`0x80 | 5`, and the consumer does `or al, 0x80`. This correspondence is a
coincidence. The request is `0047:0007`, and the consumer sets bit 7 itself.

**A probe placed before the store.** `0x94d83` fires before its `in al, 0x5c`
executes. Thus the `al = 47` that it records is stale, and is not the id. Put
the probe at `0x8e60f`, after the `and al, 0x7f` of the loader.
