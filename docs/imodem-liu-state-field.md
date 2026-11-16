# LSR's state field, and the one value the whole stack hangs on

The layer-1 decode in [imodem-d-channel.md](imodem-d-channel.md) read the
low three bits of `LSR` as an I.430 F-state with a bias of one. It concluded that
`LSR & 7 = 6` is the activated line.  **The correct value is 5**, and this difference controls
all of layer 2.

## How the firmware settles it

The firmware stores `(LSR & 7) + 2` in one byte for each interface at `ce0:a458`.
Then it compares that byte in seven locations.  Six of them look for **7**:

```
6590c  cmp byte [bx-0x5ba8], 7
67d76  cmp byte [bx-0x5ba8], 7
67e15  cmp byte [bx-0x5ba8], 7
6a932  cmp byte [bx-0x5ba8], 7      ; the TEI entity
71c9b  cmp byte [bx-0x5ba8], 7      ; the D-channel transmit gate
70f50  cmp byte [bx-0x5ba8], 4      ; the resting state
71da4  cmp byte [bx-0x5ba8], 2      ; the reset state
```

The transmit gate is the important one
([imodem-d-channel-transmit.md](imodem-d-channel-transmit.md)). A queued
frame goes out only when the byte is 7, or when a permission flag is set. No run
ever sets that flag.  If the stored value is 8, the firmware drops each frame.
That is exactly what occurred before.

Thus, the chip uses its own numbering for the LIU states, not the I.430 numbering, and the activated
value is 5.

## The proof is the stack running

When the harness drives the line to `LSR & 7 = 5` and not 6, nothing else in the
harness changes. A run that asks for an incoming call then gives this result:

```
20029952  ID_REQUEST ref 11883: assigning TEI 64
20035072  SABME from TEI 64, answering UA
          layer 2: multiple-frame-established
```

The modem transmits three frames. In all runs before this one, it transmitted no frames.  `ATI12` agrees, in the words of the firmware:

```
   Physical Interface:  Active
   Data Link Layer   :  Active
```

The trace log of the firmware shows that it takes the call:

```
LINE_ACTIVE Detected | --SETUP | SETUP with result= | START_ALERT Detected
```

`RING` comes on the AT interface.

## What the old value was

`LSR & 7 = 6` stores 8, and the firmware thinks that this value is **not** activated. Its
log prints `LINE_ACTIVE Detected` and then `LINE_NOT_ACTIVE Detected` for the
same line.
[imodem-firmware-trace.md](imodem-firmware-trace.md) recorded this as a teardown with no known cause,
and for a short time it blamed the peer of this repository.  The cause was not the
peer and not the frame. The cause was that the harness drove the line to a state that the
part does not use for an active interface.

## The table

`courier_emu/am79c30.py` has it as a table and not as a formula. The reason is that
the chip has fewer LIU states than the I.430 F-states. A formula would
invent the gaps:

| state | `LSR & 7` | firmware stores | evidence |
|---|---:|---:|---|
| F1 | 0 | 2 | shown - the reset state tested at `0x71da4` |
| F2 | 1 | 3 | shown - the state that the machine at `0x62a27` polls out of |
| F3 | 2 | 4 | assumed - the resting state that the dispatch ignores |
| F6 | 4 | 6 | assumed - one below activated |
| F7 | 5 | 7 | **shown** - and all of the stack depends on it |
| F8 | 6 | 8 | shown to be a state that the firmware calls not active |

## What it leaves

Layer 2 starts and a call is delivered. Thus, the main blocker is gone.
What the firmware says about the call itself is a smaller, later question:

```
SETUP not compatible INTL, release call
```

The modem rings, and then it releases the call because it is not compatible. This is a question about the bearer
capability or the progress indicator in the SETUP that the peer of this repository
builds. It is not a layer-2 question.
