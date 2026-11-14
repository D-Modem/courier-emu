# The I-modem's ISDN side, from the code

We recovered this when we ran the 386 harness and watched what it programs.
Two parts identify themselves directly: the CPU and the ISDN chip.

## The CPU is an Intel 386EX

It is not a generic 386. The boot sequence writes the on-chip peripheral
register file of the 386EX, at the addresses that this part fixes:

| window | what it is |
|---|---|
| `f400`-`f438` | chip-select unit, seven channels programmed at init |
| `f020`/`f021`, `f0a0`/`f0a1` | the two 8259s - ICW1 `11`, master ICW2 `20`/ICW3 `04`, slave ICW2 `28`/ICW3 `02`, ICW4 `11`/`01` |
| `f040`-`f043` | the 8254 |
| `f8f8`, `f4f8` | SIO0 and SIO1, each opened LCR=`80`, divisor `0002`, LCR=`03`, IER=`0b` |
| `f820`/`f822`/`f824`/`f826` | P1CFG, P2CFG, P3CFG, PINCFG - `00`, `75`, `bc`, `3f` |
| `f864`/`f86c`/`f874` | the matching port latches |
| `f092` | port A |

`courier_emu/isdn.py` already models the 8254, the 8259s and the two UARTs. It
calls them "PC-AT furniture". This is correct for their behaviour, but
incorrect for their name. They are the own peripherals of the 386EX.

## The ISDN front end is an AMD Am79C30A

It is at I/O `0300`/`0301`, as a command/data pair: write the register number
to `0300`, then write or read the bytes of that register through `0301`. Each
block that the firmware writes agrees with the register map of the Am79C30A,
**including its block sizes**. This makes the identification certain, not
only possible:

| reg | name | bytes written | value |
|---|---|---:|---|
| `21` | INIT | 1 | `00` |
| `a5` | LIU_2_4 | 3 | `00 00 00` |
| `a6` | LIU_MF | 1 | `00` |
| `a8` | LIU_MFQB | 1 | `00` |
| `88` | DLC_1_7 | **7** | zeros |
| `89` | DLC_DRCR | **2** | `00 00` |
| `8c` `8d` `8e` | DLC_FRAR4, SRAR4, DMR3 | 1 each | `00` |
| `6b` | MAP_1_10 | **46** | filter coefficients |
| `41`-`44` | MCR1-MCR4 | 1 each | `00` |
| `84` | DLC_DRLR | 6 | `10 01 10 01 10 01` |
| `86` `87` `8f` | DLC_DMR1, DMR2, DMR4 | 1 each | `0b`, `84`, `0a` |
| `92` | DLC_EFCR | 1 | `01` |
| `81` `82` | DLC_FRAR_1_2_3, SRAR_1_2_3 | 3 each | `01 01 01` |
| `a3` `a4` | LIU_LMR1, LMR2 | 1 each | `00`, `78` |
| `69` `6a` | MAP_MMR1, MMR2 | 1 each | `00`, `40` |

Seven bytes to `88` and two to `89` are not a coincidence: `DLC_1_7` is a
block of seven registers, and `DRCR` is two. The 46 bytes to `6b` are also
not a coincidence: they are all of the `MAP_1_10` group. The payload is
visibly a pair of symmetric FIR sets:

```
31 b1 | 1b 62 | 26 a2 | bb 16 | bb 16 | 26 a2 | 1b 62 | 31 b1
21 d1 | 12 42 | eb b1 | 61 12 | 61 12 | eb b1 | 12 42 | 21 d1
```

They are palindromic in 16-bit pairs, two times - the transmit and receive
filters of the audio processor.

## What that says about the architecture

The Am79C30A is three devices in one package, and the firmware uses all three:

* **LIU** - the S/T transceiver. Layer 1 is in the chip. The 386 touches only
  `LMR1`/`LMR2` and the multiframe registers.
* **DLC** - the D-channel HDLC controller. `DRLR` is set to `0110` three
  times: **272 bytes**, the LAPD maximum frame. `FRAR_1_2_3` and `SRAR_1_2_3`
  are the frame-address recognition registers - the hardware does the TEI and
  SAPI matching. This is exactly the service that a Q.921 stack needs below
  it. Thus the chip does the layer 2 framing, and Q.921/Q.931 are 386
  software.
* **MAP** - the audio processor, with the filter coefficients above.
* **MCR1-MCR4** - the multiplexer that routes B1, B2 and the internal channels
  between the LIU, the MAP and the peripheral port. The init clears all four:
  there is no connection until a call makes one.

That answers the question that
[x2-symmetric-and-all-digital.md](x2-symmetric-and-all-digital.md) left open.
The ISDN work is not in the DSP, because it is mostly not in software: layer 1
and the D-channel framing are an Am79C30A, and the 386 adds Q.921 and Q.931
above them. The DSP only sees B-channel PCM. This is why its seven images are
four modulations and a codec and nothing more.

## For the emulator

The next item to model is the `0300`/`0301` pair: a register file with the
block sizes above, an `LSR` that reports the line status, and the frame
interface of the DLC. Until it answers, reads return zero and the boot stalls
where it waits for the LIU to start. This is where `courier-emu isdn-run` is
now: it loops at `0x3497f` and `0xa45ef`.

## Modelled

`courier_emu/am79c30.py` is the register file. It has the command/data pair at
`0300`/`0301`, the block width of each register, a cursor that moves through a
block and goes back to the start when the command port is written, and
counters for reads, writes, unknown registers and overruns. The widths are the
self-check: if one width was incorrect, the writes of the firmware would
overrun a block, and the counter would show it. Against `Ie030002.nac`, all of
the init sequence completes with **no unknown registers and no overruns**. It
reads back as:

```
INIT 11    LIU_LMR1 40   LIU_LMR2 78   LIU_2_4 00 00 00
MCR1..4 00 00 00 00      DLC_DMR1 0b   DMR2 84   DMR3 02   DMR4 0a
DLC_FRAR_1_2_3 01 01 01  DLC_SRAR_1_2_3 01 01 01  DLC_DRLR 10 01 10 01 10 01
DLC_EFCR 01              MAP_MMR1 00   MAP_MMR2 40   PP_PPCR1 07  PP_PPCR3 01
```

The firmware *reads* only a small number of registers, and we have now
recorded them: `LIU_LSR` four times, `INIT` two times, and `MAP_MMR1`,
`MAP_MMR2`, `LIU_LMR1`, `DLC_RNGR1`, `DLC_RNGR2` one time each. Nothing here
invents a line state: the LIU stays in F1 until a harness tells it to change.
Thus you must request an activated S interface intentionally - refer to
[imodem-d-channel.md](imodem-d-channel.md).

Three ports in the same window had no explanation here - `0302`, `0303` and
`0307`. They belong to the DSC: the *direct* registers of the part are above
the command/data pair, and the IRQ14 handler of the firmware names each of
them. Refer to [imodem-d-channel.md](imodem-d-channel.md). That document also
starts the S interface and makes `ATI12` report that the physical layer is
active.

## What that unblocked

The boot did not wait for the model of the DSC. When we followed it, we found
two more parts:

* **The flash** (`courier_emu/flash_device.py`). `Ie030002.nac` is an update
  image. When you enter it at its initialiser, it identifies the flash and
  then erases it. The identification is at `34970`. First it uses the Intel
  read-identifier `ff`/`90` and compares the manufacturer word with `0089`.
  If that fails, it uses the AMD unlock `aa`/`55`/`90`. With a part that
  answers, the run goes into the Intel command set - `50` clear status,
  `20`+`d0` block erase, `70` read status. The model carries those commands,
  with an array that can only lose bits and a status register that reports
  that the write state machine is ready. The block size was the only number
  that we did not recover from the image. The board gives the answer: the part
  is an AMD Am29F400AT, top boot, and the erase at `78100` is in its first
  8 KiB sector. The board also shows which command set runs - the AMD set, not
  the Intel set. Refer to [imodem-board-map.md](imodem-board-map.md).
* **The DSP block handshake** at port `18`. The loader writes `1` and loops
  until bit 0 reads back. Then it writes `2` and loops until bit 1 reads back.
  This is the DSP that acknowledges each half-block. The DSP does not execute
  here. Thus the latch answers immediately.

With the three parts in place, the update image gets past the identification,
erases flash blocks, streams 52,856 bytes to the DSP, and starts to write
progress to SIO0.


## LSR's upper bits are the handset hook

The register file above answers the low three bits of `LIU_LSR` - the F-state
- and returned zero for the other bits. Two of those bits carried data. The
firmware itself names them, and a datasheet is not necessary.

The line-state decode at `0x70e6f` reads LSR, and then does this:

```
70eb6  and al, 7 ; add al, 2         ; the F-state, as already recovered
70ebd  test byte [bp-2], 0x80        ; bit 7 gates everything below
70ec1  je 70f24
70ed2  push 0x136c                   ; "liu_stat.C : sending a LIU_STATUS"
70ef5  mov ax, [bp-2] ; and ax, 0x40 ; sar ax, 6   ; bit 6, as a 0/1 value
70f01  mov es:[bx+0x12], ax          ; into the message it posts
```

Thus bit 7 is a gate and bit 6 is a value. To find what the firmware calls
them, we answered LSR with those bits set and read the trace log of the
firmware ([imodem-firmware-trace.md](imodem-firmware-trace.md)). This gives
the two answers:

| LSR bits 7:6 | the firmware's log |
|---|---|
| `0x80` | `STAT_OFFHOOK Detected>>>` |
| `0xc0` | `STAT_ONHOOK Detected` |

**Bit 7 is a change indication and bit 6 is the handset hook state**, with 0
for off hook. This agrees with the board. The I-modem has an analogue phone
port - the ADP. `*P1` holds its directory number, and `ATI12` labels it
`ADP Directory Number`. The DSC senses the hook switch of this port.

`courier_emu/am79c30.py` models it. `set_hook` moves the switch and raises the
interrupt of the part, as a line-state change does. LSR reports the two bits.
A read of LSR acknowledges the change, because it is an indication, not a
level. The handset stays on hook by default. Thus a run that does not request
it sees exactly what it saw before we modelled the bits - only the bit-6 level
changes, and nothing reads it without bit 7. `isdn-run --offhook-at N` lifts
the handset, and the firmware answers:

```
LINE_ACTIVE Detected
STAT_OFFHOOK Detected>>>
```

This is not what stops layer 2 - the modem still transmits nothing, with the
handset on hook or off hook. It is a part of the chip that answered zero, and
now answers what the part does.
