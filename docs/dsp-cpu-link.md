# The CPU-DSP link

This document answers one question: how do the 80186 supervisor and the C5x
datapump communicate? We know the protocol on the two sides, and the hardware
confirms it. We do not know the *rate*. At that point, the harness is still
different from the board.

## The physical arrangement

The ASIC connects to the sixteen data pins of the DSP. `IS` also connects to
the ASIC. `IS` is the I/O-space strobe, and only an `IN`, an `OUT` or a
`PA0`-`PA15` access asserts it. Thus the ASIC decodes the I/O cycles of the DSP
on the same bus that the SRAMs use.

This answers the objection that stopped this work for a long time. A board
inspection found no traces from the address/data pins of the DSP to any part
other than its two `CY7C199` SRAMs. SPRU056D Table A-8 gives `DS`, `PS` and `IS`
as three *space-select strobes* on **one** shared address/data bus. Thus an I/O
cycle drives the same pins as a data cycle. Only the strobe that goes low shows
the difference. **No person had to look for a second, dedicated 32-wire bus.**

**The decode uses five address lines: `A0`-`A3` and `A5`. `A4` is not
connected.** We measured this on the board by its effect, not by visual
inspection. We did three runs. In each run, we put the image in memory with
`ATGLK2W` and verified that it was byte-exact:

| run | ports | payload | result |
|---|---|---|---|
| control | `0x5e`/`0x5f` | `4E00` | `CDRP1 DONE`, 8 words, `SUM:701C` |
| **A4 fold** | `0x4e`/`0x4f` | `F700` | **`CDRP1 DONE`, 8 words, `SUM:B81C`** |
| A5 control | `0x6e`/`0x6f` | `A500` | `CDRP1 START`, then `CDRP1 ERR TAG` |

A frame sent to `0x4e`/`0x4f` arrives exactly as a frame sent to `0x5e`/`0x5f`.
`0x6e`/`0x6f` delivers nothing. This removes the alternative reading, that the
ASIC ignores the address bus and answers all `IS` cycles.

**The important part is that the ASIC skips `A4` but uses `A5`.** `0x5x` and
`0x6x` are different in bit 4 and in bit 5. Thus one line is sufficient to
identify the banks, and the other line is redundant. A gate array that connects
to only one of the two shows that the designer knew that there were exactly two
banks:

| bank | `A5` | ports | what it is |
|---|---|---|---|
| `0x50`-`0x5f` | low | `PA0`-`PA15` | the memory-mapped I/O ports, aliased into data space at `0x0050`-`0x005f` |
| `0x60`-`0x6f` | high | `0x60`, `0x68`-`0x6c` | pure I/O space, no data-space alias |

Thus the register file has more than sixteen registers.
`bridge.ASIC_DSP_PORT_MASK` models this. Its known limit is that we did not do a
test of bits 6 and 7. Thus the mask can be narrower than the mask of the board,
and it will accept `0x0e` where the board possibly does not.

> **The payload pattern is important.** The first fold attempt used the `4E00`
> of the control again. Thus its frame looked the same as a second run of the
> kernel that the DSP already had. The download could fail without an
> indication and give the same output. Use a different `--fold-pattern` for each
> board run.

**The medium was never on the critical path of the emulator.** The harness
simulates the effect of `out @7c, 0x5e` on one side and the return value of
`in al, 0x5c` on the other side. The instruction streams of the two processors
see the same result, if the ASIC uses parallel taps or a shift register for
those ports.

## The protocol

### The DSP writes exactly three ports

We scanned the two images for C5x `out` instructions to the mailbox ports. The
scan finds only two sites:

| file | DSP addr | writes |
|---|---|---|
| `0x298e6` | `0x83d3` | ports `0x5e` and `0x5f` - the message sender |
| `0x29a7c` | `0x849e` | port `0x60` - the stream sender |

No part of the DSP program writes `0x58`, `0x5a`, `0x5c` or `0x1c`. **Each word
that the supervisor reads as an event or as a stream value comes from the
DSP.** The ASIC transports it and changes the port numbers.

### The receive dispatcher, DSP `0x8387`

Data in the CPU-to-DSP direction does not arrive through an `in`. The DSP
program contains no `in` from a mailbox port. The data arrives in
memory-mapped cells:

```text
8387  ldp  #000
8388  setc intm
8389  calld 80e8, *      ; the guarded host-cell read helper
838b  lar  ar1, #57      ;   @57, the status latch
838e  bit  15, @7d
838f  retc ntc           ; bit 15 clear - nothing pending
8393  lar  ar1, #5e      ;   @5e - the TAG
8399  lar  ar1, #5f      ;   @5f - the DATA word
839c  lacl #01
839d  samm @57           ; acknowledge by setting status bit 0
839f  sub  #7f
83a0  retc gt            ; tag above 0x7f - reject
83a1  add  #00008468     ; tag - 0x7f + 0x8468 = tag + 0x83e9
83a3  tblr @7c
83a5  bacc               ; branch to the handler
```

**Bit 15 of `@57` shows that a message waits. The tag is `@5e` and the word is
`@5f`. The DSP acknowledges when it writes bit 0 to `@57`.** The table base is
program `0x83e9`. The table has **121 entries**, up to `0x8468`.

The three status writes identify the directions:

| write | meaning | CPU sees |
|---|---|---|
| `lacl #01 ; samm @57` | received a message | - |
| `lacl #02 ; samm @57` at `0x83e5` | a send is complete | `0x1c` bit 1 |
| `lacl #04 ; samm @57` after the stream sender | a stream word is ready | `0x1c` bit 2 |

### The full round trip

| step | side | action |
|---|---|---|
| 1 | CPU | tag low to `0x58`, high to `0x5a` |
| 2 | CPU | word low to `0x5c`, high to `0x5e` |
| 3 | CPU | commit - write bit 0 back to `0x1c` |
| 4 | ASIC | lands tag in `@5e`, word in `@5f`, sets `@57` bit 15 |
| 5 | DSP | `0x8387` sees bit 15, reads the cells, acks with `lacl #01` |
| 6 | DSP | rejects tag > `0x7f`, else `tblr` from `0x83e9 + tag` and `bacc` |
| 7 | DSP | the handler appends its reply to the ring at `ar0 = #ff60` (`@78` write, `@79` read) |
| 8 | DSP | sender `0x83d6` writes `0x5e`/`0x5f`; `lacl #02 ; samm @57` |
| 9 | ASIC | remaps those to CPU `0x58`/`0x5a`, raises `0x1c` bit 1 |
| 10 | CPU | the ISR reads the tag and calls `[0x298]` |

The stream variant is different only after step 6. Tag `0x06` goes to `0x8470`,
which runs the coroutine at `0x8480`. Each word goes out through
`out *, 0060` with `lacl #04 ; samm @57`. The CPU collects it through the chain
vector: `[0x02d3]` under 7.3.14 and `[0x01cd]` under 7.4.16.

### Handshake polarity, corrected

For a long time, the bridge had these polarities in the opposite direction:

* **PA7 bit 1** shows that *the DSP can send*. **CPU `0x1c` bit 1** shows that
  *a reply waits*. A CPU acknowledgement sets the DSP-ready bit again.
* **CPU `0x1c` bit 0** shows that the input holding register is free. **DSP PA7
  bit 0** shows that a CPU message waits.
* The stream bit uses the same opposite polarity.

The CPU input and the DSP output are **separate holding registers**. A read of
an acknowledged output still gives the last word.

> `dsp_messages_taken` counts **CPU acknowledgements of DSP replies**. Older
> notes use it as a count of messages that the DSP consumed, but that is not
> correct. The real DSP receive acknowledgements are writes of `1` to PA7.

### A tag is a command index, not an address

A tag selects one of 121 handlers. A value above `0x7f` never gets to the
table. **Thus the `host_write(address, value)` shape is not correct.** The plan
to write DSP data `03e6` through the mailbox could never operate, with or
without a commit edge. That is why `dsp-mailbox-write-01` and the queue runs saw
nothing. A missing strobe was not the cause.

An outbound message is a 16-bit tag word on `58`/`5a` and a 16-bit value on
`5c`/`5e`, with the low byte at the lower port. The compact path at `0fddb`
sends a one-byte tag and a one-byte value, and sets the high lanes to zero. The
variant at `12cbb` sends two full words from a ring. Thus the two halves really
are 16 bits wide.

**Reads and writes use separate latches.** The interrupt writes `58`/`5a` for
outbound data and reads the same addresses for inbound data. Thus an `ATGLK2I`
of these ports sees the side of the **board**, not the side of the host.

**Twelve tags have no implementation**: `4c`, `5b`-`5d`, `64`-`6b`. Their table
entry is zero, thus `bacc` sends the DSP to program word `0000`.

### Known tags

| tag | handler | what |
|---|---|---|
| `0x06` | `0x8470` | `STREAM_TAG` |
| `0x07` | `0x84cb` | status query - replies `0031:0000`, ignores its data |
| `0x08` | `0x8212` | the resident's continuous status word |
| `0x13` | `0xee20` (3.1.2) | arm the DTMF pair from the keypad index |
| `0x1a`/`0x1b` | - | tone gain → DSP `0392`, second amplitude → `03f1` |
| `0x2d` | - | no-op; leaves the held reply unchanged |
| `0x42` | `0xb03a` | `SIMPLE_WRITE_TAG` |
| `0x45` | `0x860a` | the buffered report `ATY12` requests |
| `0x47` | - | **outbound**: the DSP asking for an overlay |
| `0x48` | - | `smmr @7a, #ffb1 ; ret` - the only completely unclamped host write |
| `0x62` | - | sums squares of `0900..098f` - replies `0069:0015` |
| `0x7b` | - | **outbound only**, the DAA identity - no inbound slot |
| `0x7c` | `0x80e8` | `DETECTOR_TAG` |

> **`0x7b` and `0x7c` are not inbound handlers.** The table has 121 entries,
> `0x00`-`0x78`. A read of `0x80` entries goes past the end into the code that
> follows. The words at the "tags" `0x79`-`0x7c` are instructions:
> `847a bc00 ldp #000`, `847b be41 setc intm`, `847c 7e80 23f0 calld 23f0`. This
> is the prologue of the stream resume poll. **No handler is below `0x8000`.**

## The rate, measured on the board

INT0 is the full DSP-to-CPU path. It is IVT vector `0x0c`, and it reads
`8f46:0000` on the 403 board. **No code in the image calls or jumps to that
address.** We searched all 512 KiB for a near call, a near jump, a far call and
the bare word `0000` with segment `8f46`, and we found no reference. Thus each
message that the two processors receive is one entry to this interrupt. "The
supervisor never pops" is a statement about an interrupt line, not about a
polling loop.

```text
8f46:0000  sti ; cld ; pushaw ; push es
           in   al, 0x1e ; mov ah, al
           in   al, 0x1c
           and  ax, 3          ; two bits, and nothing else
      test 1 -> out 0x58, 0x5a, 0x5c, 0x5e        ; host -> DSP send
      test 2 -> in al,0x5a / in al,0x58 / call [0x192]   ; DSP -> CPU receive
           out  0x1c, al       ; ack: the status written back *set*
```

We measured this with the INT0 hook on a live 403 board. The stimulus was a bare
`ATD`, held for 6 s:

    interrupts            15,868 in 6.61 s   =  2,401 / s
    0x1c = fd             1,895 of the last 1,920 entries
    0x1c = ff                25 of them
    0x1e = ff             1,920 of 1,920

**The pin runs freely at 2,401 Hz.** The ASIC does not assert it from the
mailbox state. The handler polls `0x1c` on each edge. That is why `0x1c` reads
`fd` for 98.7% of the entries: bit 0 is set, bit 1 is clear, and there is
nothing to do. Thus the harness is correct *in type* when it uses a periodic
edge as a replacement.

**The signal is bit 1, and its interval is exactly 20 ms:**

    entries between consecutive 0x1c = ff:
    48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 48 58 81

There are twenty-two consecutive intervals of 48 interrupts at 2,401 Hz. The
last two intervals are longer because the dial was aborted. This is a **50 Hz
report from the DSP, exact to the sample**. It starts with the seizure. The
earlier capture holds the first 0.8 s after arming, and it shows `0x1c` always
at `fd`, with no bit 1.

`0x1e` did not change in the two captures.

### The harness cannot yet run at that rate

When we set the edge to 2,401 Hz, **the one path that operated stops**:

| | 391 Hz (default) | 2,401 Hz (measured) |
|---|---|---|
| 302 plain | `6245`, ringback, answer | `""`, dial-tone |
| DTMF blocks | 136 | **770** |
| DSP-originated messages | 389 | 389 |

The cause is in the tail of the handler. This tail runs without condition on
each entry:

```text
00f4d8  call 0x14ff0
00f4dd  lcall 8000:0676
00f4e2  cmp  word ptr [0x134], 0
00f4e9  dec  word ptr [0x134]
```

**This interrupt is the fine timebase of the firmware.** If the rate is six
times higher, each countdown that it drives ends six times faster in emulated
time. Thus the dial sends 5.7x the tone blocks, and the exchange decodes no
digits from them.

The two numbers cannot both be correct, and the board is not the fault. The
same firmware dials on the board at 2,401 Hz, with the same `dec [0x134]`.
**Thus the harness has a second error, and the 391 Hz rate hid it.** The error
is between this countdown chain and the codec-sample clock that the exchange
uses to measure digit lengths. That is a limited question, not a guess.

`MODELLED_FRAME_HZ = 391` stays the default, because the remaining parts of the
harness agree with this rate. `--frame-hz` gives the comparison again. We keep
a number that we know is not correct as the default on purpose. The alternative
is a harness that is correct for this interrupt but cannot complete a call.

## The dial-tone wait and the datapump load are one mechanism

Two separate investigations described the same counter and did not see it.

The **datapump** side: when `[0x0b9e]` gets to 5, the firmware loads overlay 5.

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

The **dial-tone** side: the detector counter of 403 is `[0x0b9e]`. Its wait is
at `0x0b7c2`. The four-instruction routine at `0x14fdc` updates it.

`0x14fdc` and `0x94fdc` are the same routine, at the file address and at the
physical address. `0x0b7c2` is `8b7c2` above. **It is one loop.** Five
consecutive DSP replies with the correct bit set qualify dial tone. When the
code goes out of that loop, it loads the datapump overlay.

The routine:

```text
14fca  test ah, 1          ; (302; 403 is 14fdc)
14fcd  je   14fd4
14fcf  inc  byte [0cc0]    ; a qualifying hit
14fd3  ret
14fd4  mov  byte [0cc0], 0 ; reset
```

`AH` is the **high byte of the data word that comes with event `0x08`**. The
code reads it at `0x14dd8` from ports `0x5e`/`0x5c`, immediately before the
call. Thus this supervisor qualifies its detector from **bit 0 of the high byte
of the data word of event `0x08`, five consecutive times**. It does not use a
polled level.

| build | counter | wait | routine | call sites gated on |
|---|---|---|---|---|
| `IDSDL302` | `[0x0cc0]` | `0xb784` | `0x14fca` | `[0x0ea7] & 1`, `[0x0ea6] & 1` |
| 403 board | `[0x0b9e]` | `0x0b7c2` | `0x14fdc` | `[0x0d93] & 1`, `[0x0d92] & 1` |

**`main211` uses a fully different mechanism**, and it is not a model for
either build. Its wait at `0x1dbee` is `cmp byte [0649], 5 / jb`. A **level** in
`[0x0285]` drives its counter at `0x1e442`:

- `0xff` does nothing.
- `0` resets the counter.
- `1..0x60` increments the counter.
- A value above `0x60` resets the counter and increments `[0x064a]`.

The `DETECTOR_PRESENT_LEVEL = 0x30` of the bridge is correctly in that window.
`CourierDaa.detector_qualified` is a third mechanism. It uses five 100 ms frames
of accumulated audio and never examines a level. **Neither of these is a
replacement for the behaviour of the ROM builds.**

### Which leaves one thing to reconcile

The dial-tone report of the resident is tag `0x08` with **bit `0x40` of the
data word**. We measured it: `0x0002`/`0x0003` become `0x0042`/`0x0043` when the
exchange supplies a continuous tone. The detector of the supervisor does a test
of **bit 0 of the high byte** of that same word. For `0x0042`, that bit is
clear.

The two observations are reliable, but they do not clearly agree. These are the
possibilities, and we did a test of none of them:

- The emulated resident sets the wrong bit.
- The qualifying word is a different message from the one that the tag
  histogram counts.
- The high byte carries data that the emulated resident never supplies.

**This is the next item to measure, and we can measure it.** The traffic of the
board during a real dial, sampled through the INT0 hook, will show which
possibility is correct.

## Why nothing transfers in the harness yet

The addresses, cells and bits are confirmed on the two sides. The failure is
that the DSP does not get to its service loop.

The loop at `0x80bb` calls all three mailbox routines on each iteration:

```text
80bb  call 8387, *, ar1     ; the receive dispatcher
80bd  call 83bf, *, ar1     ; the message sender
80bf  call 8462, *, ar1     ; the stream resume poll
80c3  lar  ar0, @10 / cmpr eq
80c5  bcnd 80bb, tc         ; loop
```

To get to the loop, the code must go past six `call 8138` sites earlier in the
same routine. `0x8138` is a wait that ends in `idle`, until an ISR counts `@6b`
down to zero. We sampled the state of the core during a run: **`idle` is true,
and 1316 of 3999 PC samples are in that region.** The C52 waits for interrupts
that never arrive. Thus the code never calls `0x8387`.

**IRQ 5 is the interrupt that wakes it.** IRQ 4 and 6 do not wake it. This
agrees with the interrupt that the harness already arms for the XMF build. It
also agrees with the routine that waits: the ISR that clears `@6b` is at
`0x8188` and ends in `rete`. It reads `@6b`, compares it with 3, and sets it to
zero.

**But a ROM image has no low program block, and the vectors follow the base.**

| index | entry word | words (403 / 302) |
|---|---|---|
| 5 | `0x8000` | 28327 / 27710 |
| 6 | `0x9d00` | 12594 / 11510 |
| 7 | `0xb000` | 7498 / 7499 |
| 8 | `0xdc00` | 7498 / 7350 |

**No entry is at `0x0000`**, in a ROM or in an XMF.

> **Corrected 2026-09-15.** The `0x0000` origin was a constant in `courier_emu/xmf.py`, not a measurement. The download call site of the supervisor gives `8000`. Its overlay table puts the 2.1/2.2 rows at `8000`, `9d00`, `af50` and `dc00`. Thus an XMF also has no low block, and it agrees with the ROMs. Refer to [hardware-timebase-and-audio-path.md](hardware-timebase-and-audio-path.md#3-corrected-the-xmf-payload-loads-at-8000-not-0000).

When `iptr` is zero, the vectoring of the core sends IRQ 5 to `(5 + 1) << 1` =
`0x000c`. That is unloaded memory, and the woken core went out of control at
exactly that address. The same slot above a `0x8000` base is `0x800c`.
`_configure_frame_interrupt` now arms IRQ 5 at `origin + 0x0c` for each image
whose first segment has an origin that is not zero.

With that interrupt armed and the wiring in place, we sampled the cells of the
DSP through an `ATY12`:

| observation | meaning |
|---|---|
| `5e`/`5f` carry each tag and word | the CPU-to-DSP write lands |
| `@57` reaches `a000` and never changes | bit 15 **never consumed** - `0x8387` has not run |
| `@57` never shows `1`, `2` or `4` | no acknowledgement, send or stream completion |
| `io60` stays `ffff` | the stream sender has never executed |
| ring `w == r` throughout | nothing queued for the CPU |

**A transfer does not complete in either direction.** The outbound half arrives
but the DSP ignores it. The return half never has data to carry. The PC of the
DSP stays in the waits of the early routine: `0x801d`, `0x8024`, `0x8028`,
`0x8020`. Each pass has six of these waits, and each wait needs the ISR to
count three interrupts. **Thus each iteration needs eighteen frame interrupts,
but the supervisor stops after six ticks of 5 ms.** That is the shape of the
problem. The control is `m_line_frame_period`, now 258 cycles.

That is a question of rate, not of protocol. It is the same type of error as
the 2,401 Hz finding above.

## The poll rate on the DSP side

The mailbox poll of the DSP is in the block at `0x80c8`. The main loop gets to
that block only when `cmpr eq` finds that `AR7` is equal to `ARCR`. The ring is
exact: `0x802e` sets `CBCR = 0x00ef`. This selects `AR7` for circular buffer 1,
with `CBSR1 = 0x0bd0` and `CBER1 = 0x0bdf`. If `ARCR` is at any address in that
ring, the block runs once on each pass, a few hundred times each second. If
`ARCR` is zero, the block runs **once, during initialisation**. That is why a
full run shows 87 messages delivered and almost no messages consumed.

**`@10` is data `0x0390`, and `AR7` is kept in that cell.** Direct addressing
is relative to DP, and `ldp #007` is immediately before the `lar ar0, @10` at
`0x8105` and `0x810d`. Thus `@10` is *not* the memory-mapped `AR0` at data
`0x0010` that a DP-0 reading gives. That is the trap. `sar ar7, @10` at `0x808f`
and `0x81a1` stores the cell. `lar ar7, @10` at `0x80c5` and `0x8192` restores
it:

```text
80c5  lar  ar7, @10     ; AR7 <- saved ring pointer
80d0  lar  ar0, @10     ; AR0 <- the same cell, and ARCR/INDX with it
80d1  cmpr eq           ; TC = (AR7 == ARCR)
80d2  bcnd 80c8, tc     ; has AR7 moved off its saved value?
```

Thus the compare does a test of the **live ring pointer against its own saved
value**, and it needs no external input.

### The `NDX` side effect is real, and measured on the part

That reading is correct only if `lar ar0` also loads `ARCR` as a side effect.
The `LAR` page of SPRU056D and its Table 4-3 say that this occurs when `NDX` is
clear. The text of its section 3.5 says that it occurs when `NDX` is set. Thus
the document cannot decide. We did a test on the part, and we wrote new
sentinels before each load:

| | `PMST` | `lar ar0, @7b` | `lark ar0, #55` | `lar ar0, #4321` |
|---|---|---|---|---|
| **`NDX` clear** | `00b0` | `ARCR`/`INDX` = **`1234`** | = **`0055`** | = **`4321`** |
| **`NDX` set** | `00b4` | `ARCR`/`INDX` = `EEEE`/`DDDD` | - | - |

1. **The side effect is real on this part.**
2. **The `LAR` page and Table 4-3 have the correct polarity.** The text is not
   correct. This firmware clears `NDX` at `0x8012`, thus the side effect is
   **active**.
3. **The side effect does not apply only to 'C2x instructions.**
   `lar ar0, #4321` is the 'C5x long-immediate form, and it loaded the two
   registers. Any load of `AR0` causes the side effect, with all encodings.

A second capture later confirmed this. The other readings give the limits:

- **`SAMM AR0` does not** copy to `ARCR`/`INDX` with either polarity.
- **A `MAR` increment/decrement of `AR0` does** copy, with `NDX` clear.
- **A load of `AR1` does not** copy.

The core implements the `AR0` side effects of `LAR` and `ARAU`, and keeps MMR
writes independent.

> **Two faults hid each other.** The core did not have the `AR0` side effects,
> *and* PA7 writes made false download-ready status. When we corrected only
> `NDX`, the firmware went into that false ready path and downloaded `FFFF` many
> times, also into its interrupt vector area. **That was not evidence of bad
> `*0+` addressing.** It looked like that, and an earlier revision made that
> conclusion. On the measured ROM profile, PA7 writes acknowledge flags. They do
> not replace the full register. The board reads PA7 as `0002` before and after
> writes of `0200`, `0300` and `0000`.

`ARCR` is shared scratch, and this is one reason why it was difficult to read.
The only write to it in the resident is `samm @19` at `0x9644`. It calculates
`(@7e >> 10) + 0xd9fe`, a **program** address for a table walk. `0xafdf` reads
it back.

**On the board, `0x0390` reads `0x0000`** in all sixteen samples. The control is
important, because a broken probe also gives zero. The same kernel, pointed at
data `0xffff`, gave `0x0083` sixteen times. But we took the reading while the
unit was idle and on hook, and after the monitor had reset the DSP. Thus it is
the value that the resident left, not a sample of the running loop. **A sample
of `0x0390` during a call is the open measurement.** It needs a probe that runs
together with the firmware. `cooperative_probe.py` has that shape, but now it
cannot get to DSP data memory.

## The status register is PA7

Four routines in the resident read `0xff57`:

```text
839b:  bit 15, @7d   -> bit 0    host message pending
83d6:  bit 14, @7d   -> bit 1    (also requires @79 != @78)
847a:  bit 13, @7d   -> bit 2    then dispatches through data 0x039e
80f8:  and #0200     -> bit 9
```

SPRU056D sections 3.5.11 and 8.3.2 put the memory-mapped I/O ports at
`0050h-005Fh`, from `0x50` = PA0 to `0x5F` = PA15. In Figure 5-10,
`LAMM`/`SAMM`/`LMMR`/`SMMR` set the 9 MSBs of the address to zero. Thus
`lamm *` with `AR1 = 0xff57` really reads `0x57`. **`0x57` is PA7, and these four
routines poll a status word that the ASIC drives.** The ASIC sets the meanings
of the bits, and no TI document gives them.

The harness sets only `HOST_MESSAGE_PENDING` (`0x0001`). Thus `0x83d6` and
`0x847a` return immediately, and `@1a` continues to point at `0x8139`, a bare
`ret`. The code that sets the other bits of PA7 is 80186 code in an image that
this repository has, because the `PA0`-`PA7` of the DSP get their data from the
80186 window at `0x40`-`0x5e`. The path of `0x847a` through data `0x039e` and
`bacc` has the shape of "start this task".

## The readback channel, and why it cannot dump the mask ROM

The `0x60`/`0x62` window is a real bulk readback channel. We verified it end to
end on hardware: **arm with a mailbox tag, pump with `0x1c` bit 2, and read the
words.** We followed the jump table at `8401` through each handler. This shows
which tag gets to which streamer, and if its source holds program memory or
live data. `tests/test_dsp_window_stream.py` records the result.

| tag | handler | arm stub | source | words | what it exposes |
|---|---|---|---|---:|---|
| `06` | `8489` | `848d` | `0307 03ba 0385 030f 031c 0be6` | 6 | six discrete live call-state cells (a custom per-word streamer) |
| `45` | `8623` | `8627` | `ff90` **or** `ff00` | 32 / 17 | live data; `@1f` bit 10 picks the variant at runtime |
| `46` | `84d3` | `8617` | `ff80` | 16 | first four table-read from **program** `860b..8610`, rest live |
| `47` | `863e` | `8642` | `ffc0` | 12 | live data `ffc0..ffcb` |
| `57` | `8517` | `8617` | `ff80` | 16 | **program** words near `85ff`/`8611` plus derived status |
| `58` | `864e` | `8652` | `ffc0` | 25 | live data; also sets `fff8 := 0a40` |
| `73` | `865e` | `8665` | `[fff8]` = `0a40` | 103 | live DSP data RAM `0a40..0aa6` |
| `78` | `8671` | `8678` | `[fff8]` = `f993` | 5 | live DSP data `f993..f997` |

Each count was equal to the immediate of its arm stub. `ffb8` advanced by
exactly that number of cells, and `[039e]` cleared at the end. Thus the
streamer disarms correctly. Tag `46` is the reference. In the emulator it gives
`0708 0708 0960 0960 0000...`, which is identical to the physical
`dsp-window-pump-02` capture.

**A host driver must know two details:**

- The first pumped word is the **count**, not payload. The opening `bd 84b7` of
  the arm stub emits while `ar1` is still at `ffb9`. Thus pump `count + 1`
  times and discard word 0.
- The "pump me again" flag of the emit path and the poll of the resume path both
  resolve to data `0057`. Thus **`0057` bit 2 is the handshake cell**.

The resume poll does a test of **bit 13** of the status latch, not bit 2:

```text
8462  calld 80e8, * / lar ar1, #57
8469  bit  13, @7d
846a  retc ntc                          ; nothing to resume
846b  lar  ar1, #039e
846d  lacc *                            ; the vector the handler armed
846e  retc eq                           ; unarmed
846f  bacc                              ; continue the coroutine
```

The two stream handlers arm that cell. Tag `06` at `8470` writes
`splk @1e, #8474`, and tag `45` at `860a` writes `splk @1e, #860e`. `@1e` under
`ldp #007` is cell `0x039e`.

### The index cannot be widened

Tag `46` is the nearest to a dump, because its arithmetic has **no mask**.
`lacl @5b ; add #860b` can get to all 16-bit program addresses, which include
the mask ROM, and the streamer carries the result to the host. All parts that a
dump needs are present, except control of the index.

`03db` has exactly two writers. `9773` only reads it. `ae98` writes the return
value of `ae12`, and `ae12` is a **six-way priority encoder**:

```text
ae15  bit 10, @7d ; lacl #05 ; retc tc      ; TI bit 10 is bit 5
ae18  bit 11, @7d ; lacl #04 ; retc tc
ae1b  bit 12, @7d ; lacl #03 ; retc tc
ae1e  bit 13, @7d ; lacl #02 ; retc tc
ae21  bit 14, @7d ; lacl #01 ; retc tc
ae24  lacl #00 ; ret
```

**By construction, its output is `0..5`.** Thus no control of its input can make
the range larger. The shape of the encoder limits the address to `860b..8610`.
This is not a clamp that you can bypass. Thus the route is closed, whatever its
input is. A trace of the input confirms this:

- `ade8` does an AND of four cells at `ffb0..ffb3`. Of these, the host can write
  only `ffb1` (tag `48`).
- An AND can only clear bits.
- The other terms come from a call-setup routine that an idle unit has not run.

We did a direct test: tag `48` with `ffff`, then tag `46`. The index was still
`0`.

**The best remaining lead** is `ffb8`/`fff8`. A streamer has its source address
in a data cell. If a host could write that cell, the streamer would give an
arbitrary DSP *data* read. The set that the host can write includes
`fff0`-`fff3`. That is adjacent to `fff8`, but it does not include it.

### And the datapump is already in hand

The supervisor downloads the program of the DSP through the I/O ports at each
boot, and the load base is known:
`flash_offset = 0x29080 + 2 * (dsp_word - 0x8000)`. We checked this in two
ways. Flash `0x29080` holds the DSP reset code and maps to word `0x8000`. The
resident sender at words `83d6..83ff` maps to flash `0x2982c..0x2987e`. Thus
flash `0x29080..0x368fc` **is**, byte for byte, the code that the DSP executes.
If we read it out of the DSP, we would only get a copy of data that we already
have.

The mask ROM would add the **internal boot ROM** at words `0000..0fff`, which is
not in flash. A C52 has 4K words there. The ROM does not fill all of
`0000..7fff`. Thus lower addresses, for example `23f0`, `2100..2593` and
`7a80`, can be external program RAM or installed program RAM, but they cannot be
part of the ROM array.

If the TI protection option is programmed, an instruction fetched from off-chip
memory reads invalid bus data for an on-chip program operand. The option also
blocks the emulator. Thus a downloaded `8000` probe and a usual JTAG dump both
fail by design. **On-chip SARAM is not on that exclusion list.** This is the one
gap.

This is the non-destructive discriminator, if you put an oscilloscope on the
board:

1. Photograph the marking.
2. **Monitor `MP/MC` at DSP reset.** Low maps the internal ROM, and high maps
   external memory. The pin is sampled only at reset, but the `PMST` bit can
   change later.
3. Monitor `PS`, `STRB` and sufficient address lines during reset.

An external program fetch at address zero supports `MP/MC = 1`. **We measured
this later: `PMST` reads `00b0`, thus `MP/MC` is 0**, microcomputer mode. Refer
to board.md.

## Which DSP

**A 'C51.** We measured this on 2026-09-13. We wrote through the data space of
the DSP and read back through program space. `0x0800` and `0x1800` ignore the
write, and `0x2400` follows it. This shows 8K of on-chip ROM at
`0x0000`-`0x1FFF`, with writable memory above it. It is not the 9K SARAM of a
'C50. `native/c5x_core.h` models a 'C52, which was already excluded. Refer to
[artifacts/dsp-memory-test-2806](../artifacts/dsp-memory-test-2806/README.md)
and [board.md](board.md#which-dsp-a-c51-measured).

An earlier reading here said that `calld 0x23f0` needs the 9K part. That is not
correct. `0x2400` is writable on this board, and that is all that the call
needs.

## What this does not establish

A scan for `out` with those port numbers finds two `out` sites. It would not
find an indirect port write, or a port write that the code makes at run time.
We call the stream packer at `0x84a3` (a normalised sum of two cells) a
**level** because of its shape. No trace connects its inputs to the line ADC.
This document does not show which DSP cell holds a call-progress state. It also
does not show that one of the two sender routines sends event `0x08`.
