# The I-modem's D channel, and bringing its line up

[imodem-isdn-front-end.md](imodem-isdn-front-end.md) identified the Am79C30A
and modelled its indirect register file. But it did not explain three ports in the same
window, `0302`, `0303` and `0307`, and the S interface stayed
inactive. For this reason, `ATI12` answered:

```
   Physical Interface:  Inactive
   Data Link Layer   :  Inactive
```

The two problems are now closed on the layer-1 side. The line comes up, and the
firmware itself says so.

## The interrupt line is IRQ14, and its handler names every port

We did not infer any of this from the datasheet of the part. Vector `0x2e`
(slave IRQ14, because the ICW2 of the slave is `0x28`) reads back `4030:02f8`. This is a stub
that makes a far call to `71d7:000f`. That routine is a full D-channel interrupt service,
and all of it is visible:

```
71ec0  in 0300                  read IR, the interrupt register
71ed5  test al, 2f              loop while bits 0,1,2,3 or 5 are set
71d97  test [bp-4], 20          bit 5: the line state changed
71dff  test [bp-4], 1           bit 0: the transmit buffer wants more
71e48  test [bp-4], 2           bit 1: a received byte is waiting
71eaf  test [bp-4], 0c          bits 2,3: D-channel status and error
```

It reads `0304` for received bytes and `0307` for the byte-by-byte status
below it. The status handler at `72caf` reads `0302`/`0303`. That
is exactly the direct register map of the Am79C30A: CR/IR, DR, DSR1, DER,
DCTB/DCRB, the two B-channel buffers, DSR2. This identifies the three unknown
ports, and it is a second, independent confirmation of the part.

No code in the image uses `0305` and `0306`. The MCRs route the B channels
to the peripheral port, and the B channels get to the DSP. They do not go
through the host interface. This agrees with what
[isdn-vs-analog-dsp.md](isdn-vs-analog-dsp.md) found from the other end.

## What each path does

| path | where | what the firmware does |
|---|---|---|
| transmit | `71cb0` | write LPR, push bytes to DCTB while DSR2 bit 4 says there is room, then write the frame's **total length** to DTCR as two bytes.  Writing DTCR is what arms the frame. |
| receive | `71e64`, again at `72e1e` | read DCRB, then DSR2: bit 1 says another byte waits, bit 0 says the byte just read ended the frame.  Then read DER for the frame's errors and DRCR for its length, and pass the frame up only when `DER & 0x7b` is clear. |
| line state | `70e6f` | read LSR, take `(LSR & 7) + 2` as the interface state, and on a change dispatch through a six-entry table at `70f7e`. |

The line-state decode is the useful one. When you add two to a three-bit field, the
range becomes 2..9. The table covers 2..8, and one entry (the resting state)
sends no notification.

> **Correction.** Before, the remaining part of this paragraph said that the entry for
> `LSR & 7 = 6` tells layer 2 that the line came up, and that thus the
> field is the F1..F8 of I.430 with a bias of one. **The activated value is
> 5, not 6**, and the numbering is that of the chip, not that of I.430. The
> difference is all of layer 2: the transmit gate accepts a frame only
> when the stored byte is 7, and 6 stores 8. Refer to
> [imodem-liu-state-field.md](imodem-liu-state-field.md).

## Layer 1 will not take a shortcut

The firmware keeps the state as one byte for each interface at `ce0:a458`. The
interrupt handler does not write it. The handler sends a notification to the layer-1 machine
at `6296f`. This machine dispatches **on the state that it is already in** (a seven-entry
table at `62e3f`), and only then on the event. In F1, the event table at
`62e33` covers events 0 to 5, and the activation event is 6. Thus, if an interface
goes from F1 directly to F7, the machine ignores the event, and the stored state
does not change. A run that does exactly that leaves `ce0:a458` at `02`.

If the states occur in sequence (F2, then F6, then F7), the result of `ATI12` changes. (The stored
value that it gets to is `07`, not the `08` that this page recorded at first. Refer to the
correction above.)

```sh
.venv/bin/python -m courier_emu isdn-run Ie030002.nac \
    --instructions 70000000 --line-activate 3000000 \
    --send AT --send AT --send ATI12 --send-every 20000000
```

```
   Physical Interface:  Active
   Data Link Layer   :  Inactive
```

That is the diagnostic of the firmware itself, which reports the modelled line. This
is the check on the decode above: nothing in `courier_emu/am79c30.py` writes the
string, and nothing writes to `ce0:a458` directly.

## Modelled

`courier_emu/am79c30.py` now contains the direct registers together with the
register file:

* **LIU**: an F-state that the harness sets. The LSR state field reports it
  through the table in [imodem-liu-state-field.md](imodem-liu-state-field.md). The
  handset hook is in its top two bits
  ([imodem-isdn-front-end.md](imodem-isdn-front-end.md)). A change raises IR bit 5.
  `set_liu_state`, `activate`, `deactivate`, `set_hook`.
* **DLC receive**: `deliver_frame` puts a frame in a queue. The bytes come out of DCRB
  with the byte-available and last-byte bits of DSR2, the frame-end bit of DSR1, DER
  clear, and DRCR with the length. The model keeps the frame boundaries and the lengths
  for each frame. Thus, two frames in the queue do not mix.
* **DLC transmit**: the bytes written to DCTB accumulate. A write to DTCR closes
  the frame at the length that it gives. `take_sent` collects them. If a length does not
  agree with the pushed bytes, the model **counts** it and does not silently
  accept it, because this would mean that the model of the buffer is wrong.

`courier_emu/isdn.py` raises IRQ14 from `poll_timers` each time the part
asserts it. `--line-activate` takes the S interface up. The model of the transmit FIFO
always has room. We did not recover the depth, and a deep
buffer sends the full frame in one pass. Thus, we do not invent a threshold.

## What was still down, and why (superseded)

*Layer 2 comes up now. Refer to
[imodem-liu-state-field.md](imodem-liu-state-field.md). The text below gives the
state when we wrote this page. The configuration work that it
describes is still necessary. But it was not the blocker.*

Layer 2 does not come up, and the reason is not the D channel: the firmware
never sends a frame. Each line of `ATI12` says why. The switch
protocol is `Invalid Switch Type`, the multipoint and dialing mode are `Invalid
value`, the two SPIDs and the two directory numbers are empty, and the two TEIs are
`Invalid fixed TEI`. Nothing is configured. Thus, Q.921 has nothing to
start.

### The settings block, and that nothing fills it

The ISDN settings are a **91-byte block at `2600:d476`**. The firmware
calculates its checksum at `c4ecb`:

```
c4ecf  mov word ptr [cf30], 0
c4ed5  mov si, d476
c4ed8  mov cx, 5b               ; 91 bytes
c4edb  lodsb ; lcall b3d9:6aa9  ; accumulate into [cf30]
c4ee1  loop c4edb
```

Its accessors are the routines near `c3111`-`c357d`. They are in the same region as
the name table of the switch types at `c339f` (`AT&T 5ESS`, `Northern Telecom
DMS-100`, ... `Invalid Switch Type`). `ATI12` indexes this table.

In a run, the general RAM wipe at `a4051` clears the block. Then the block is
**never written again**. We monitored the memory of the block during a session that sends
`AT*W=4A`. The monitor recorded the zeroing at boot, the checksum read at boot, and
nothing else for the remaining 97 million instructions. Thus, the block is not
loaded from any location, and each field decodes from zero as invalid. This
is the full complaint of `ATI12`.

### It is not the 93C66 the other Couriers carry

We exclude this explicitly, because the board components look familiar.
The I-modem has the same abstraction of board-latch signals as the 302, 403 and
Quad: a signal id of `mask << 8 | flags | index`, a read helper at `a5e0e`,
and set/clear helpers at `a5f2b`/`a5ebf`. Also, **index 0 of its input port
table at `a5f97` is port `0x10`**. This is the same latch on which those boards bit-bang their
Microwire EEPROM ([quad-settings-eeprom.md](quad-settings-eeprom.md)).

But the transport is not there:

* A run looks as if it clocks a serial part: one signal toggles 941
  times, another 941, and a third 94. But these are the **front-panel lamps**. The
  routine at `abf4b` controls two indicators with modes 0 off, 7 on, 8 slow and
  all other values fast. It divides a tick by `0x14` or `3`. A board-revision flag
  at bit 2 of `[c8f1]` changes the two lamps between port `0x100` and the older
  latches. For this reason, they are on pins that look plausible.
* Statically, all ~100 near callers of the three signal helpers are in the
  `a400` segment, and none of them is a shift loop. There is no 12-bit command
  frame and no 16-bit read-back.
* The obfuscation of the Courier settings record (`ror(b,2)+5`, `rol(b,1)-0x0f`,
  `b xor 0x1d`) also does not occur. `xor al,1d` occurs one time in the full
  image, with no `sub al,0f` near it.

Thus, the source that fills `2600:d476` is not the 93C66 store that this repository already
models. If we used `courier_emu/nvram.py` for the I-modem, we would not
model its hardware. **The source is the flash**. The store is sector SA8 at
`0xf8000`. It holds two copies of a record, and the S-register defaults of the record identify it
clearly. The firmware loads it into this block. Refer to
[imodem-config-sector.md](imodem-config-sector.md). This file also gives
`isdn-run` the overlay and save options that carry a sector between runs.
The remaining candidates are flash. The board has **two** 4 Mbit parts, and
the chip selects put 768 KiB of them at `40000`-`fffff`
([imodem-board-map.md](imodem-board-map.md)). The harness models only the part
at `80000`, and it treats the other window as ordinary RAM. Above that, the
two boot sectors of the Am29F400AT at `7a000` and `7c000`, which are not changed, are exactly
what an update does not change. The missing 32 KiB boot block is the location of a
loader that runs before all other code. To find it
is the step that is necessary before Q.921. Note that `courier_emu/parameters.py`
is not it. That store is the store of the 211, and it does not exist on this board.
