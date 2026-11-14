# What the 20.16 MHz Courier's CPU sees of its line interface

The supervisor gets its information about the phone line from two different locations.
Only one of them is the ASIC. This file records the CPU-side half: what the 80186
reads and writes directly, before the ASIC or the DSP calculates anything. This is important, because
a model that puts all line signals behind the event channel makes the ring path
wrong.

The addresses below are file offsets in the board image of the user,
`artifacts/courier-board-21210-capture-403/courier-board.rom` (supervisor
7.4.16). `IDSDL302.ROM` also contains the two structures. Where its addresses are different,
we give them.

## Two CPU-visible line signals, both on port 0x14

Ports `0x10`, `0x12` and `0x14` are write-only board latches. Thus, the firmware
keeps shadow copies: `[0x011b]` is a mirror of port `0x12`, and `[0x011c]` is a mirror of port
`0x14`. Each write below ORs or ANDs a mask into the shadow,
and then sends the full byte.

### Ring sense - port 0x14 bit 1

A cadence machine that a tick controls samples this bit directly. The ticker at `0x14ff0`:

```
14ff0  dec  byte [0ae4]
14ff4  jne  15004
14ff6  inc  word [0ad8]          ; cadence accumulator
14ffa  mov  byte [0ae4], 0x0c    ; reload: 12 ticks, 60 ms at the 5 ms tick
14fff  lcall 0x8000:0xc001
15004  call word ptr [0ada]      ; the current cadence state
```

`[0x0ada]` is a state vector of the same type as `[0x0298]` and `[0x02d3]`.
Its states read the line and branch on one bit:

```
1501d  in   al, 0x14
1501f  test al, 2
15021  jne  15039
```

The debounce counters `[0x0ade]` and `[0x0adf]` are compared with a threshold
in `[0x0cd2]`, and `0x5bb5` is the reset state. Twenty-seven sites arm the
vector. The two sites that start it, `0x0bfe8` and `0x0bff2`, are in the same module
as the `CALL PROGRESS` banner. `IDSDL302.ROM` has the same machine, with six
sense sites and not ten.

`daa.py` already models this signal as "ring cadence presented to the
ring detector on input port 0x14". It is the one line signal that the CPU
measures itself.

### A four-bit part identity - port 0x14 bit 3, clocked on 0x12 and 0x14

`0x287f9` does a small serial read with bit-banging. It asserts masks on port `0x12`
(`0x09`, `0x02`) and port `0x14` (`0x70`, `0x40`, `0x20`, `0x10`). After each mask, it samples
bit 3 of port `0x14` and shifts it into `BX`:

```
2880c  out  0x14, al        ; 0x70 asserted
2880e  in   al, 0x14
28810  test al, 8
28812  jne  28817           ; present
28814  jmp  28898           ; absent -> return 0xff
...
28825  in   al, 0x14 / and al, 8 / or bl, al / shl bx, 1   (x4)
2888f  mov  al, bl / sar al, 4 / and al, 0x0f              ; the 4-bit value
```

If the part is absent, the routine returns `0xFF`. The caller at
`0x28426` stores the value at `[0x014b]`, after a table walk indexed through `[0x0156]` against `[0x014c]`.
The code tests its bits at `0x00595`, `0x005af`, `0x00751`, `0x209d7`, `0x209ea`
and `0x49b2b` (`test byte [014b], 1` and `, 2`). Thus, the identity selects
behaviour. It is not only reported. The second caller, `0x28787`,
sends the same value out of the 80186 serial port (`[0xff6a]`, with a wait loop on
`[0xff66] & 8`). `IDSDL302.ROM` contains the identical routine at `0x28765`, and
a second copy at `0x7d222` in the boot area.

## What the CPU does not see

No CPU port carries a line level. The code does not sample here the detector for which the dial path waits.
This detector comes through the ASIC event channel as event `0x08`, with a
data word read from ports `0x5e`/`0x5c`. The qualification is bit 0 of the high byte of that
word, five consecutive times. Refer to
[the ATY diagnostics](at-y-diagnostics.md). Dial tone, ringback, busy and
answer tone are all recognised on the far side of that channel.

Thus, the split is: **ring sense and part identity are the CPU's; every level and
every call-progress tone is the ASIC's.**

## What this does not establish

We inferred the bit meanings from how the code uses them. We did not use a probe.
"Port `0x14` bit 1 is ring sense" has two bases: a cadence machine that a tick controls, with
debounce counters that read that bit and nothing else, and the existing model of the harness.
No capture in this repository shows the bit change while a
line rings. The serial receive path *writes* the same bit number as CTS flow control, and `panel.py` has
`CS` measured there. Refer to
[board-verified-403.md](board-verified-403.md#the-ring-is-the-dte-receive-buffer-and-port-0x14-bit-1-is-its-cts).
That does not contradict this interpretation. On a latch with independent read and
write paths, the same address carries different signals in each direction.
Port `0x00` in this firmware is the example: `0x33` reads as strapped
inputs, while `0xc4` are outputs. `machine.py` already models the read side of `0x14`
from the panel and strap inputs, not from the latch. Thus, bit 1 is
probably CS/CTS out and ring sense in, and the two routines do not conflict. We call the four-bit read at `0x287f9`
an identity because the firmware reads it one time, stores it, and branches on it. We did not identify the device
at the other end of those clocks. It is an assumption that it is the DAA and not an option
strap or a country module. We did not execute these routines in the
emulator for this note. We read the two statically from the two images.
