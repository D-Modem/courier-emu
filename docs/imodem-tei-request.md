# The modem does ask for a TEI

Two pages of this repository say that it does not ask.
[imodem-bri-network.md](imodem-bri-network.md) gives "the modem does not
request a TEI on its own" as an open question, and
[imodem-firmware-trace.md](imodem-firmware-trace.md) repeats it.  **The two pages are
not correct.**  The modem asks.  It builds the request, the request is correct, and the modem discards it
before it gets to the wire.

## Watching it happen

Send an incoming call on the broadcast data link. This is the one path that
gets to a terminal that has no TEI. Then the TEI management entity runs:

| instructions | what runs |
|---:|---|
| 20,025,601 | the broadcast SETUP is decoded and distributed |
| 20,027,632 | `0x69b70`, the TEI state machine, on event 0 |
| 20,027,667 | `0x6a755`, the Identity Request builder |
| 20,030,865 | queued through `652e:000d`, the entity returns |
| **20,036,512** | the stack raises **`LINE_NOT_ACTIVE`** |
| 20,039,663 | status `0x1a`, which has no arm in its dispatcher |

The state machine at `0x69b70` dispatches on `[bp+8]`. Event 0 is "start
assignment".  The machine checks the TEI state of the interface at `es:[bx+0x85]` and finds
0. It sets the retry counter `es:[bx+0x8e]` to 1. That counter is **N202**. When it is
exhausted, the firmware logs `N202 Cnt Exceeded - no TEI assigned!!!`.
Then the machine calls the builder.

The builder assembles the message one byte at a time:

```
6a8b0  mov byte es:[bx], 1        ; message type 1 - Identity Request
6a8ba  mov byte es:[bx], 0xff     ; Ai - TEI 127, EA set
```

When we read the assembled buffer from memory at `0x6a8d4`, the full result is:

```
00 00 00 00 00 00 | 0f 2e 6b 01 ff
                    |  |     |  `- Ai         0xff, TEI 127
                    |  |     `---- message    01, Identity Request
                    |  `---------- Ri         0x2e6b, the reference
                    `------------- MEI        0x0f
```

That is a standard Q.921 Annex D Identity Request.  It has no
error, and `courier_emu/bri.py` answers exactly this shape. The peer could
always assign a TEI, but the modem never asked it.

## Where it dies

The request is queued to a different task through `lcall 652e:000d`, and it is never transmitted:

```
frames the chip actually transmitted: 0
peer saw from the modem:              0
```

After the request is queued, no code in the D-channel transmit region `0x71a00`-`0x72000` executes.
About 5,600 instructions later, the
stack raises `LINE_NOT_ACTIVE` and stops the procedure.

That result does not come from the line.  In the same window, the firmware touches the chip exactly
three times: a write to `DLC_RNGR1`, then a select and a read of `LIU_LSR`.
The read returns `0x06`. With the formula of the firmware, `(LSR & 7) + 2`, this decodes to
**8, F7, active**.  The firmware reads the line as up, but it reports it as down.

Thus, the gap is between a queued layer-2 frame and the D-channel transmitter.
It is the same gap that the transmit path at `0x71cb0` always showed. That path
has no direct callers, and the code gets to it through a pointer. No run has yet shown a write to that pointer.

## One thing this did fix

The `Ri` above is `0x2e6b` because of this investigation.  The firmware reads
it from the **random number generator** of the Am79C30, `DLC_RNGR1`/`DLC_RNGR2`.
Before, `courier_emu/am79c30.py` answered those reads from the register file.
Thus, they returned the value that was written, which is 0.  Each Identity
Request that this harness built had `Ri 0000`.

That is legal, and it is not the cause of the failure of the request. But it is not what the
part does. Ri exists to let two terminals that ask at the same time identify their answers.
A constant value stops this.  The registers are now a generator. Each instance
has its own LCG seed, thus a run stays reproducible. A harness with frames that
change between runs is more difficult to debug than a harness with a random number that is fixed
for each seed.

## What to correct elsewhere

In all locations, read "The modem does not request a TEI" as "the TEI request of the modem
is never transmitted".  The difference is important. The
first statement says that the stack did not decide to ask. That would point to the
configuration. The second statement says that the stack asked and the frame is stuck. That
points to the transmit path.
