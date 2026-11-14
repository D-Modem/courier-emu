# The ATY diagnostic commands and the missing line-measurement path

`ATY<n>` is a command family with a numeric argument. It starts the line diagnostics
of the firmware. The harness answers all of them. But each display that gets its
data from the measurement hardware of the modem shows no data. This
document records why: one input path is not modelled, and it is the same path
for all of them.

## What the commands do

We measured these offline against `IDSDL302.ROM` (supervisor 7.3.14), board id 7,
`tick_ms=5`, the mostly erased `idsl302` EEPROM fixture, no line and no
external serial device. `artifacts/rom-at-smoke-20260906/probe.py` operates the
DTE.

| Command | Response | Data source |
|---|---|---|
| `ATY11` | `Freq     Level` header, no rows | measurement (empty) |
| `ATY12` | `Recv     Xmit` + 16 rows of `0000     0000` | measurement (empty) |
| `ATY14` | `000,000,030,007,030,000` | CPU-side, partly populated |
| `ATY15` | `CURRENT DIPSWITCH SETTINGS` + all ten switches | modelled front panel |
| `ATY16` | `OK` | - |
| `ATY17` | 8x8 grid of `0000` | measurement (empty) |
| `ATY13`, `ATY18`, `ATY19`, `ATY20` | `ERROR` | - |
| `ATY0`-`ATY9`, bare `ATY` | `OK` | - |

`ATY4` is a mode, not a display. It stores 4 at `[0x0608]`, and this value stays
across commands. A later dial prints `\r\nCALL PROGRESS\r\n`, and then it must
print level rows. Six sites test `cmp byte [0x608], 4`:

| Site | On Y4 |
|---|---|
| `0xbf2d` | print the `CALL PROGRESS` banner |
| `0x14f13` | emit CRLF and a two-space row indent |
| `0x2917` | print `LLOSS` when `[0x032c] & 0x80` |
| `0x48e32`, `0x491a5`, `0x491b9` | echo a character / a value and a space, in the `ATG` monitor extension |

Offline, only `0xbf2d` is reached. `ATY4` is *not* limited to nine values.
The `cmp al, 0x0a / jae reject` at `0x26248` is the tail of a dispatch chain
that compares `0x0c`, `0x0e`, `0x0f`, `0x10` and `0x11` before it.

## How ATY12 fetches its data

`ATY12` is a buffered fetch. It is not a live sample. Its handler at `0x6eb2`:

```
mov ah, 0x45                  ; operation
mov byte [0x942], 0x20        ; request 32 words
mov word [0x2d3], 0x20fa      ; the collector step for this reply
call 0x6ede                   ; AL=0x3f, lcall 0x8f43:0228, [0x2e3]=1,
                              ; [0x2e8]=6, spin until the flag clears
mov si, 0x20
mov dx, 2
call 0x6fbb                   ; print the reply buffer
```

`0x8f43:0228` (file `0xf658`) is an enqueue into a ring buffer. It stores AX into the
queue at `[0x29e..0x2ce)`, with the head `[0x29c]` and the tail `[0x29a]`.

`[0x2d3]` is a state-machine vector. Each incoming 16-bit word runs the step
to which it points, and the step writes the next step into it. The collector for
this reply, at `0x20fa`, sets the write pointer `[0x944] = 0x946` and the index
`[0x943] = 0`. It discards two words. Then it stores each subsequent word at `[0x944]`,
and increments by two, until `[0x943] == [0x942]`. At that point, it jumps to
`0x2000`: the vector goes back to idle, and `mov byte [0x2e3], 0` completes the
handshake. Each word is read in the same way: `in al, 0x62` for the high byte,
then `in al, 0x60` for the low byte.

The printer at `0x6fbb` then gives the buffer layout:

| Location | Meaning |
|---|---|
| `DS:0x0942` | reply word count; `CL = count >> 1` rows |
| `DS:0x0946` | **Recv** column, stride `DX` = 2 |
| `DS:0x0966` | **Xmit** column, reached as `[bx+si]` with `SI` = 0x20 |
| `0x9d7e` | prints AX as four hex digits |

Thus, there are 32 words: sixteen Recv at `0x0946` and sixteen Xmit at `0x0966`.

## The interrupt that feeds everything, and its three channels

One ISR, at file `0x12d3c`, supplies each consumer in this document. It reads a
status word from ports `0x1E` (high) and `0x1C` (low), and it acts on the low
three bits:

| Status bit | Channel | Data ports | Consumer |
|---|---|---|---|
| 0 | transmit ready | `out 0x5c`/`0x5e`, `out 0x58`/`0x5a` | drains the ring at `[0x29e]` |
| 1 | event word ready | `in 0x5a`/`0x58` | `call [0x298]`, the modem state machine |
| 2 | **DSP word ready** | `in 0x62`/`0x60` | `lcall 0x8000:0674` -> `call [0x2d3]` |

After the bit-1 dispatch, it calls `[0x27d]`. Then it reads the status again and
tests bit 2:

```
in  al, 0x1e / in al, 0x1c
and ax, 4
jz  skip
mov [0x285], ax
lcall 0x8000:0674          ; -> call word ptr [0x2d3]
```

### Channel 2 is the DSP's outbound window, not a diagnostic side-channel

`dsp_mailbox.py` already identifies the producer, against hardware. The
sender of the DSP (`84b7` in DSP 3.0.13, `849e` in 3.1.2) is `out *, 0060` followed by
`lacl #04 ; samm @57`, and that 4 is the status bit that the CPU reads as `0x1c`
bit 2. Thus, the producer of the window is **the DSP, one word for each interrupt**. The
ASIC only connects CPU I/O ports to DSP data cells. When the CPU acknowledges bit 2, the
DSP continues and sends the next word.

`ATY12` is related to the stream that the tool already operates. The documented
trigger at `0x6d08` arms `[0x2d3] = 0x1fdb` and enqueues `AL=0x3f, AH=0x06`,
that is, tag `0x063f`, which agrees with `STREAM_TAG`/`STREAM_DATA`. `ATY12` at `0x6eb2` arms
`[0x2d3] = 0x20fa`, sets the count to 32, and enqueues `AH=0x45` with the same
`0x3f`: tag `0x453f`, a longer collector on the same window.

**These addresses are those of supervisor 7.3.14.** In 7.4.16, the chain vector is
`[0x01cd]`, not `[0x02d3]`. The 403 board image confirms the full shape at its
own addresses: the trampoline `call word ptr [0x01cd]` at `0x0067b`, the tag-06
trigger at `0x06d52`, and `ATY12` at `0x06efe`, which arms `[0x01cd] = 0x212c`, with
the count cell at `[0x0836]` and not at `[0x0942]`.

## Why the measurement displays are empty

**Only channel 2 is dead.** A count of the port traffic during an `ATY12` run
shows this clearly:

| Port | Traffic |
|---|---|
| `0x1C`, `0x1E` | 2882 reads each - the ISR runs |
| `0x58`, `0x5A` | 2878 reads, 3469 writes - channel 1 and the transmit path are live |
| `0x5C`, `0x5E` | 3469 writes - live |
| `0x60`, `0x62` | **0 reads** |

Thus, the modem event machine runs normally. Specifically, the
diagnostic channel never gives a signal. Port `0x1C` bit 2 never asserts. The
port returns `0x01` on all 2882 reads. This is the echo of the output latch from the
`out 0x1c, 1` that the ISR itself does.

You can see the result directly on the `[0x2d3]` side. A sample of that
vector during a run shows three different producers that arm a sequence
(`0x1fdb`, `0x20fa`, `0x4420`), and the vector never advances after the armed
entry, because no step ever runs. A sample of the `ATY12` handshake shows that the
request is issued, and then the timeout occurs:

```
flag=00 retry=00 count=00   (idle)
flag=01 retry=06 count=20   (request issued, 32 words asked for)
flag=01 retry=05 count=20
...
flag=01 retry=00 count=20   (retries exhausted, flag still set)
```

The buffer at `0x0946` stays zero all the time. `0x6eb2` ignores the carry flag
that `0x6ede` returns. Thus, it prints sixteen rows of `0000` in all cases. The zeros
are a **timeout, not an empty reply**.

## What ATY4 actually arms

The banner site at `0xbf28` is the full call-progress entry. A trace of its
memory writes shows the sequence:

```
mov byte [0be0], 0
cmp byte [0608], 4 / jne ...      ; print "\r\nCALL PROGRESS\r\n"
mov word [0298], 0x5782           ; the call-progress state handler
xor bx, bx / mov ax, 0x1500
lcall 0x8f43:0228                 ; enqueue command 0x1500
mov byte [0aef], 0
mov byte [0bd4], 5                ; blanking guard
mov di, 0bd6 / mov cx, 10 / rep stosb   ; clear the cadence counters
```

The code segment of the module is **`0x8f43`**, not a round `0x9000`. Thus,
`[0x298] = 0x5782` resolves to physical `0x94bb2` (file `0x14bb2`). That
handler is a table dispatch through the generic matcher at `0xf78a`
(`repne scasb`, then `jmp word ptr cs:[bx+di]`), over a **36-entry
call-progress event table**: match bytes at file `0x14b40`, handler words at
file `0x14b64`.

```
83 07 3a 21 08 3d 3a 28 29 2a 2b 2c 2d 2f 47 0b 2e 23
45 46 48 30 34 35 36 37 6a 6c 6d 70 71 73 74 6b 6e 44
```

`ATY4` reports these event codes. Offline, the arming occurs six
times (`[0x0bd4] = 5` is written six times, one time for each dial retry), and the code
goes into the state at `0x94bb2` only one time. Thus, the counters at `[0x0bd6..0x0bdf]`
stay zero, and no row is ever made.

## What would have to be modelled

For the `ATY11`/`ATY12`/`ATY17` displays, only channel 2:

1. Port `0x1C` bit 2 asserted when a reply word is available.
2. Ports `0x62` (high byte) and `0x60` (low byte) returning that word.
3. Whatever advances 1 and 2 once per word until `[0x942]` is satisfied.

`ATY12` is the easiest probe for it. It prints its sixteen rows at the
command prompt without a dial and without a timeout. Thus, a source with data is
visible immediately.

`ATY4` needs something different. It does not need channel 2. It needs a source of
call-progress events on channel 1, which already operates. The events must come from the 36
codes above, and they must be values below `0x76`, not the `0xff` that the port
now returns.

## What ATY4 prints, established by forging events

**The events below are fabricated.** When we force `AL` at `0xf492`, we write a value that the
hardware never made. It exercises the display path of the firmware and says
nothing about the line. Read this section as a test of the printer, not as a
model of a real condition.


Channel 1 is live, but it carries no usable data. The active `in al, 0x58` site is
file `0xf490`. During a full `ATY4` dial, it reads `0xff` on all 5596
invocations. The next instruction is the rejection:

```
in  al, 0x58
cmp al, 0x76
jb  dispatch
jmp skip            ; 0xff is discarded here
```

Event codes must be below `0x76`. Thus, the code rejects a floating `0xff` bus before
`call [0x298]` ever runs. This is the reason why nothing prints. A missing display is not the reason.

If we force `AL` to a table event code at `0xf492` (and only while
`[0x298] == 0x5782`, because at other times the vector is the idle state `0x0150`),
we get this row:

```
\r\nCALL PROGRESS\r\n00  
```

The execution hook shows that `0x94f13` runs, with `AL = 0x00`. **`0x14f13`
is the `ATY4` row printer**, and it is reachable. An earlier revision of this
document said incorrectly that it was dead, because a static scan found no
caller. Its body prints the event byte through `0x8000:0x9da6`. This goes to
`aam 0x0a` at `0x9dbd` and sends **two decimal digits**, then two spaces.

Thus, an `ATY4` row is a sequence of call-progress **event codes in decimal**, two
digits each. This is the shape of a reported hardware line such as
`00 00 02 08 07`, with the values as codes `0, 0, 2, 8, 7`, not as signal levels.

Only one row occurs for each injection run, because the first table event, `0x83`,
dispatches to file `0x14bbe`. This sets `[0x298] = 0x150` and returns the
machine to idle. A sequence without `0x83` keeps the vector out of
`0x5782` fully, and it prints nothing. Thus, a model must supply a plausible ordered event sequence,
not a random one.

## The gates are unreached, not dead

We hooked the execution across `0x14dd0..0x14fc0` while we injected events. This records
the full path, and it explains why the static scans found nothing:

```
14dd8 -> 14dde (lcall c800:0008) -> 14de3 ... 14e08 -> 14e30 (cadence detector)
      -> 14e40 -> 14ef7 ... 14f0e -> 14f13 (gate taken) -> 14f1b -> prints
```

The code gets to `0x14f13` through ordinary sequential flow in the detector, not through a
call. The scans looked for a caller, and there is no caller.
The routine is only downstream of an event. The stack at the gate confirms that
the frame is part of the `call word ptr [0x298]` at `0xf4e2` (the event
dispatch), with the near return address `0x8f4e6`.

Thus, the answer to "is it dead because the line modelling is dead" is **yes for
this gate, and we showed it**. No part of it is vestigial. It prints the first
time that a valid event gets to the detector.

The same run gets to extension entry 8 (`lcall 0xc800:0008` -> `0x48e3f`). This
entry had also never executed before. Entry 8 is the second-word consumer for event
`0x08`. The handler reads the data word that comes with the event from ports `0x5e`/`0x5c`
before it calls it.

`0x48e32` and `0x491b9` still did not execute, also with events.
They are separate routines, not fallthrough targets (`0x48e32` ends in a
`ret` immediately before the body of entry 8). Thus, each needs an actual caller, and
we could not find one. The most probable interpretation is the same one that we proved for
`0x14f13`, because the routines near them in this family are all on paths that the line controls:
`0x491a5` is called from `0x49202`, which waits on `[0x02cf]` for a received
DTMF digit. But that is an inference from the position, not a proof.

## Running it against the real bridge instead

The project does model the line. `CourierDspBridge` controls exactly the event
ports (`DSP_RUNTIME_PORTS = (0x58, 0x5A, 0x5C, 0x5E)`, plus `0x1C`), and it contains
a `CourierDaa`, `LineLink`, `LineExchange` and the `NativeC5x` core. Until now, each run
in this document used none of it. The probe builds a CPU-only
`CourierMachine`, which its own manifest calls an "offline CPU-only ROM
AT-command smoke test".

When we run the `ATY4` dial again with `with_dsp=True` and a `CourierDaa`, the
execution changes: the dial gets to 68.8M instructions, not 43.7M. But the
display stays empty. The event port is read **one time**, and it gives `0xff`,
which `cmp al, 0x76` rejects. Thus, the bridge does not synthesize a
call-progress event stream for the supervisor, and if we enable it, this does not replace
such a stream.

There are two related gaps near this. `asic_ports.IDLE` records the hardware idle
values for these ports (`0x58: 0x20`, `0x1C: 0xFD`, `0x60: 0x4B`), and
`machine.py` does not import `asic_ports`. Thus, a CPU-only run answers
`0xff` and the `0x1C` latch echo. If we seeded those values, this would also not make
events. A constant idle level is not an event stream, and `0x20` is not
one of the 36 codes.

## How the detector qualifies, and why the DAA model does not fit this image

Two different things have the name "qualified", and they do not measure the same
quantity.

`CourierDaa.detector_qualified` is a sample count: `qualified_samples >= 5 *
DAA_FRAME_SAMPLES`, that is, five 100 ms frames of audio that accrue while `detector_present`
is true. `seize()` and `release()` set it to zero. It never examines a level.

`main211.xmf` counts something different. The wait at `0x1dbee` is
`cmp byte [0649], 5 / jb`. The reply
value in `[0x0285]` controls the counter at `0x1e442`:

| `[0x0285]` | Effect on `[0x0649]` |
|---|---|
| `0xff` | nothing - the "no reply pending" sentinel |
| `0` | reset |
| `1..0x60` | increment - one qualifying hit |
| `> 0x60` | reset, and increment `[0x064a]` instead |

Then `mov word [0285], 0xff` consumes it. Thus, it needs five consecutive polled replies
with a level in `1..0x60`. The `DETECTOR_PRESENT_LEVEL = 0x30` of the bridge
is correctly in that window. But the poll never occurs, and
`detector_replies: 0` reports this.

**`IDSDL302.ROM` does not use that path.** It has no access to `[0x0649]`
and no level comparison of `[0x0285]`. In this image, `[0x0285]` is the status
word of the ISR. Its detector counter is `[0x0cc0]`, and its wait is at `0xb784`
(`cmp byte [0cc0], 5 / jb 0xb76f`, with `mov byte [0cc0], 0` that arms it at
`0xb76a`). The routine of four instructions at
`0x14fca` updates the counter:

```
14fca  test ah, 1
14fcd  je   14fd4
14fcf  inc  byte [0cc0]      ; a qualifying hit
14fd3  ret
14fd4  mov  byte [0cc0], 0   ; reset
```

There, `AH` is the high byte of the **data word that comes with event `0x08`**.
It is read at `0x14dd8` from ports `0x5e`/`0x5c`, immediately before the call to
extension entry 8. The two call sites, `0x14df1` and `0x14e05`, are gated on
`[0x0ea7] & 1` and `[0x0ea6] & 1`.

Thus, this supervisor qualifies its detector from **bit 0 of the high byte of
the data word of event `0x08`** (five consecutive sets), and not from a polled level.
The 403 board image is the same design with different addresses: counter
`[0x0b9e]`, the identical `test ah, 1` routine at `0x14fdc`, and the wait at
`0x0b7c2`.

Thus, the requirement is again on the channel that now carries
nothing. For these images, the bridge would have to send event `0x08` with a
data word that has bit 0 set in its high byte, five consecutive times, before the dial
can continue. The sample-count model of the DAA cannot replace this,
because it models the mechanism of a different supervisor.

## What this does not establish

We read the 36 event codes from the dispatch table. Their meanings are not
known, and we did not show a mapping from a line condition to a code.
The injection proves that the display path operates when it gets data. It does not show that any
of those values is what hardware would send, in which order, or with which
timing. No run in this document has made a single real
call-progress event. Nothing here identifies the
`AH=0x45` / `AL=0x3f` operation behind the `ATY12` queue, or the units of the
values in its buffer.

`0x491a5`, the third extension gate, is called from `0x49202`. This is a helper that
waits on `[0x02cf]` and translates a nibble through the DTMF table
`"0123456789#*ABCD"` at `0x49209`. Thus, under `ATY4`, the extension also shows the
received DTMF digits.

We measured the command table on `IDSDL302.ROM`. The 403 board image has the
same six gates against `[0x0500]` and not `[0x0608]` (`0x02984`, `0x0bf79`,
`0x14f25`, `0x4960a`, `0x4a1c4`, `0x4a1d8`), with the mode byte stored at
`0x262d1`. Thus, the two builds have a similar structure, but their addresses are not compatible.
