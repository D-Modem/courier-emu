# The Quad x2 Modem NAC images

> Bring-up update (2026-09-10): refer to [Quad blockers](quad-bringup-blockers.md).
> That report records local RS-232 AT operation. It does not show that an NMC
> handshake is a necessary condition. New probes show false receive interrupts
> and missing channel-selected memory. If the historical execution conclusions
> below do not agree with that report, the report is correct.

`QF060003.NAC` (6.0.3) and `QR060103.NAC` (6.1.3) have the date 1998-09-22.
They are in `docs/x2/Qf060003.zip` and `docs/x2/Qr060103.zip`. This document
records the direct measurements from these images. The platform classification
is in a different document, [`docs/x2/README.md`](x2/README.md).

## Shared lineage with the analog Courier

We flattened the images with `courier-emu extract`. Then we compared them with
hashes of 32-byte blocks and a greedy extension of the identical runs:

| Pair | Shared 32 B blocks | Longest identical run |
| --- | --- | --- |
| QF 6.0.3 ~ QR 6.1.3 | 178,191 | 7,500 B |
| QF 6.0.3 ~ `IDSDL302.ROM` | 43,468 | 3,618 B |
| QR 6.1.3 ~ `IDSDL302.ROM` | 30,444 | 2,050 B |
| `main211` supervisor ~ `IDSDL302.ROM` | 21,010 | 2,777 B |
| QF 6.0.3 ~ `main211` C52 payload | 14,026 | 1,039 B |

The Quad NAC shares more with the standalone analog Courier SDL 3.02 ROM than
`main211` does. But `main211` is a known later Courier release. Thus the Quad
NAC and the Courier have a shared source lineage, not only a shared architecture.

This test has a limit. On *both* the QF↔ROM side and the main211↔ROM side, data
tables make up most of the long runs. These tables are help screens, S-register
text, result codes and the `/ARQ/V32`…`/ARQ/V90` rate tables. `QF+0x572c0`, the
3,618-byte run, is a pointer table. This test does not show byte-identical
*executable* code.

`Do DS0` also occurs in `IDSDL302.ROM`. But there it is a fragment of the help
token dictionary for the `&` commands. It is more lineage evidence. It is not
evidence of DS0 support in the analog Courier.

## Analog and digital in one image

The images are a combined build. The firmware selects the line side at runtime.

The AT help table at `QF+0x233db` contains a three-way mode command. No
standalone analog Courier image has this command:

```
%D0  Standard Analog (POTS)
%D1  T1 Mode (DS0)
%D2  ISDN PRI Mode
```

These are the counts of the mode strings: `IDSDL302.ROM` 0, `main211`
supervisor 0, QF 6.0.3 five, QR 6.1.3 five.

The Courier product-name table at `QF+0x020331` has the usual
`Dual Standard` / `HST` / `V.32bis` / `14400` … `Fax` list. The table also has
`Analog/Digital Quad`, `Analogue/Digital Quad`, `Digital Quad`,
`Analog Quad` and `Analogue Quad`.

The images implement the two plants. They do not only name them:

- Analog: `OFF HOOK` / `ON HOOK`, `PHONE OFF HOOK`, `OFF HOOK RESTRICTED`,
  `Loop loss disconnect`, blacklist, pulse dialling and DTMF dialling with the
  full `DTMF "0"`…`DTMF "D"` digit table, and `Analogue Loopback (ALB)`.
- Digital: the `S47` bitmap (`Disable Call Signaling`, `Dial using DTMF, not
  MF`, `Disable KP & ST MF Xmit`, `Config based on ANI`, `Force Gateway NAC
  Routing`), `S62 Number of ANI digits`, `S63 Number of DNIS digits`,
  `S71 T1 Idle Disconnect Pattern`, `S73 Default Dialout PRI Slot`,
  `ISDN Universal Connect` and `LLC IE for ISDN HDLC`.

The digital support is at the DS0 level, not at the T1 framer level. The two
images have no `ESF`, `B8ZS`, `AMI`, `D4`, alarm or slip strings. This agrees
with `Change DS0 state on Quad Modem NAC` in `DP030105`. The framer is on the
PRI/gateway NAC. The Quad card runs one Courier modem engine for each DS0 that
it gets. On the analog variant of the card, the card operates a real DAA.

## Execution

Current results: we now have measurements of
[interrupt-driven chassis reception](nmc-sdl-protocol.md) and of
[QF CPU byte-terminal AT/OK execution](quad-at-terminal.md). The historical
probe of the flat image below is older than the selected modem memory and the
terminal adapter. Its conclusion, that a chassis handshake is necessary, is not
proved.


The two NACs do not contain a reset vector. Their start record is a null
`0000:0000`. Their highest painted span is two bytes at `0xfbfee`, not
`0xffff0`. Thus, as with the I-modem NAC, these images are operational code
without the boot block of the card. The first painted word at the `0x80000`
load base is `e9 30 01`. This is a near jump to `0x80133`. The PCB
initialisation table follows it (`0xffa0`/`0xffa2` = `LCSST`/`LCSSP` and
`0xffa4`/`0xffa6` = `UCSST`/`UCSSP` on the 80C186EB, refer to the note about
the peripheral map below). The boot block of the card enters the operational
image at that point. Thus the model must use that entry.

We entered the two images at `0x80000` under `CourierMachine`. Each image
executes 8,000,000 instructions without a fault. The images program the PCB
chip selects and timers and write the interrupt vector table. Then they send
their DSP queue initialisation (35 writes, `QF` at `pc=8016a`, `QR` at
`pc=80176`). The two images do not get to their AT layer. `serial_text` is
empty, and `ticks` and `timer_interrupts` are both zero.

The two images stop in the same routine (`QF+0x819e6`, `QR+0x81908`):

```
push dx
mov  dx, 0x226
in   al, dx
pop  dx
mov  byte [0x467], 0x64
call word [0x45c]
retf
```

A state machine follows this routine. It compares `al` with `0x32` (`'2'`) and
`0x02`, and it writes a new dispatch vector at `[0x45c]`. Here the card waits
for its host interface. This is the SDL detection that the NETServer release
notes describe for operational code. `QF` also polls `in 0x0200` 96,170 times
and does `out 0x0042` 96,151 times. `QR` loops on memory with almost no I/O
(283 events).

Thus the images stop at the same point as real hardware: they wait for the
Total Control chassis to talk to them. To continue, we must model the NAC host
interface at `0x0220`–`0x022a` and `0x0200`. A stub for the poll is not
sufficient.

## Would the Courier boot block match?

No. The two use exactly the same conventions as the boot block. But they are
different in each value that describes the board.

### The table format is an exact match

The Courier 3.02 boot block enters at `fc00:1a21` (`0xfda21`). It processes a
table of `(port, value)` word pairs at `cs:0x1976` (`0xfd976`) with this code:

```
lodsw ax, cs:[si]   ; port
xchg  dx, ax
lodsw ax, cs:[si]   ; value
out   dx, ax
loop
```

The table has `0x24` (36) entries. The `e9 30 01` near jump at the `0x80000`
load base goes to the Quad application header at `0x80003`. This header is a
table with the *same* encoding and the *same* 36 entries. It writes the same
`0xffa4 = 0x8000` as the Courier reset stub at `0xffff0`. But the two chips do
not agree about the function of `0xffa4`, refer to the text below. The Quad
operational image uses the same initialisation convention as the Courier boot
block.

### The values describe a different board

Nineteen ports occur in the two tables. Only six of them have identical values
(`0xff80`, `0xff84`, `0xff88`, `0xff94`, `0xffa0`, `0xffa4`).

The two parts are **80C186EB**. The comparison below uses the map of that part
(Table 4-1 of the manual in this tree). We decoded the boot table of the 302
with this map. The result agrees with the hardware-derived model of this
repository. `courier_emu/uart.py` documents the serial unit of the board as
`B0CMP` "written `0x8015`" and `S0CON` "written `0x21`", in a "relocated
peripheral control block". The table writes exactly `0xff60 = 0x8015`,
`0xff64 = 0x0021` and `0xffa8 RELREG = 0x10ff`. These are three independent
agreements, thus the decoding is correct.

| EB register | 302 boot block | Quad init table |
| --- | --- | --- |
| `LCSST` / `LCSSP` | `0x0000` / `0x200a` | `0x0000` / **`0x400a`** |
| `UCSST` / `UCSSP` | `0x8000` / `0xffce` | `0x8000` / `0xffcf` |
| `RELREG` | `0x10ff` — PCB relocated | **not written** |
| `B0CMP`/`B0CNT`/`S0CON` | `0x8015`/`0x0000`/`0x0021` | not in the table |
| `B1CMP`/`B1CNT`/`S1CON` | not written | **written** |
| `GCS` pairs | 0, 1, 2, 4, 5, 6 | **all eight, 0-7** |
| `T0CMPA` / `T0CON` | `0x6270` / `0xc001` | `0x04ec` / `0xc000` |
| `T1CMPA`/`T1CMPB`/`T1CON`, `T2CNT`/`T2CMPA`/`T2CON` | not in the table | **written** |
| `P1DIR`/`P1CON`/`P1LTCH`, `P2DIR`/`P2CON`/`P2LTCH` | written | not in the table |
| `IMASK`, `PRIMSK`, `INSERV`, `REQST`, `INSTS`, `SCUCON`, `I3CON`, `PWRCON` | written | `I1CON`-`I4CON`, `IOCON` instead |

The silicon is the same, but the board is different. These are the important
differences:

- `LCSSP` is `0x200a` on the 302 and `0x400a` on the Quad. This is a different
  extent of the lower chip select, thus a different RAM size.
- The Quad uses all eight general chip selects. The 302 uses six.
- The Quad programs all three timers. The boot table of the 302 programs only
  `T0`.
- The 302 relocates its peripheral block. The Quad does not.
- The two configure *different* on-chip serial channels: the 302 uses channel 0
  and the Quad uses channel 1.

Thus the Courier boot block would give the Quad application a card with these
faults: the wrong RAM extent, two chip selects not configured, the peripheral
block relocated away from its expected address, and the wrong serial channel
in operation.

### Grafting it on

We copied the Courier boot block (`0xfc000..0xfffff` of `IDSDL302.ROM`) onto
the Quad flash and entered at the reset vector `0xffff0`. The boot block
executes normally on the Quad flash. It does 36 word writes and 9 byte writes
from its two tables. Then it does a `rep movsw` of `0x1975` bytes of itself to
`0000:0000` (the hot address is `0xfda61`, 3,260 iterations). Then it executes
`int 0x13`, its dispatch. The harness stops there with
`status: software-interrupt`.

The Quad cannot use that path either. `recovery.py:178` accepts `int 0x13` only
at `BANK_PHYSICAL + 0x1c05`, the SV25 bank address.

Thus the graft shows that the Courier boot block *executes* on the Quad flash.
It does not get to a handoff. Also, the table comparison above shows that it
must not get one.

### The word at `0xfbfee` is the image CRC

`recovery.py` shows that the Courier loader calculates an application CRC. The
loader compares this CRC with a stored word before entry (its
`application-crc` event at `0x10a3`). The Quad images do not paint
`0xfbff0..0xfffff`. This area is 16 KiB, the size of a boot block. The images
paint exactly two bytes at `0xfbfee`, immediately below that area:
`QF 6.0.3 = 0xf40a`, `QR 6.1.3 = 0xc29d`.

**CRC-16/X.25** gives the two values exactly. Its parameters are the reflected
polynomial `0x8408`, init `0xffff` and final XOR `0xffff`. The range is
`0x80000..0xfbfee`, and unpainted flash counts as erased `0xff`:

```
QF 6.0.3 -> 0xf40a   (stored 0xf40a)
QR 6.1.3 -> 0xc29d   (stored 0xc29d)
```

Two independent images match the first algorithm that we tried after we
identified the table. This is proof, not coincidence. The two Quad images
contain the 256-entry `0x8408` table (`QF+0x1cae`, `QR+0x1bd0`). The chassis
NMC image `NM040103.NAC` also contains it (`+0x20d0`). The three copies are
byte-identical and little-endian. The `msg_head.crc1`/`crc2` framing of the NMC
uses the same CRC. Refer to [nmc-sdl-protocol.md](nmc-sdl-protocol.md).

Thus the boot block of the card verifies the operational image with the same
CRC that the chassis uses on the wire. The covered range also confirms that
`0xfbff0..0xfffff` is reserved for the boot block and is not in the check.

Also, on the Courier, `0xf8000..0xfbfff` is the area of the parameter sectors
(`courier rom-info` lists sectors from `0xf8000`). It is not application space.
The Quad does not paint this area either. Thus the two agree about the shape of
the reserved top of flash. But they do not agree about its contents.


## A note on the peripheral map

The DSP-interface routine of the Quad at `0x93864` writes `0xff56`. It sets
bit 1. Later it clears bit 1 and pulses bit 3. Table 4-1 of the 80C186EB manual
in this tree gives the name **`P1LTCH`** to `0xff56`. This is the Port 1 output
latch. Thus these writes are GPIO strobes around the DSP access.

This finding caused us to use the map above. We withdraw two claims that this
document made before:

- **"The Quad leaves the Courier's timer setup alone."** This is not correct.
  Its table contains `T0CON`, `T1CON` and `T2CON`. The error occurred because
  we read `0xff50`-`0xff66` as the timer block. That is the map of the classic
  80186, not the map of this part.
- **"The two program different silicon, so the tables are not comparable."**
  This is also not correct. We committed it here for a short time. It came from
  a read of `0xffa8 = 0x10ff` as an `MPCS` value, which implies a classic part.
  On the EB, `0xffa8` is `RELREG`. Also, `uart.py` independently describes how
  this board relocates its peripheral control block. The two parts are
  80C186EB, thus the tables compare directly, as shown above.

The Quad also programs an on-chip serial channel. At runtime it uses
**channel 0** much: `S0CON` at 38 sites, `S0STS` 30, `S0RBUF` 20, `S0TBUF` 39.
`uart.py` models this same channel as the DTE path of the analog board. The
Quad uses channel 1 very little (it never reads `S1RBUF`). The external `0x220`
block that [nmc-sdl-protocol.md](nmc-sdl-protocol.md) identifies is a separate
device. The SDL state machine polls this block. Thus that identification is
still correct.

## What the NAC changes for x2 and V.90: it can be the digital modem

We measured these findings on `QF060003.NAC` and `QR060103.NAC`. We compared
them with `T-REC-V.90-199809` and with the analog Courier baseline in
[`x2-v90-protocol-selection.md`](x2-v90-protocol-selection.md).

### The INFO machinery is shared, not reimplemented

The two NACs contain the same C5x INFO serializer as the analog Courier. We
found it by signature, not by address:

| signature | Courier 4.03 | `IDSDL302` | QF 6.0.3 | QR 6.1.3 |
|---|---|---|---|---|
| bit-field writer prologue | `8769` | present | `9948` | present |
| bit-field reader prologue | `877a` | present | `9959` | present |
| DPSK symbol `+/-21fc` | `99ed` | present | `a03c` | `9e3c` |
| CRC poly `8408` | `99e6` | present | `a035` | `9e5f` |

The code loads the fill constant `04ef` with `lacc`/`sacl`, not with `splk`.
Thus a simple byte search for `splk @50,#04ef` does not find it. The fill is
not different. The script tables have the same structure as the tables of the
Courier. They have the same `12 / body / 16 / 4` framing, the same idle-42
steps and reference-symbol steps, and the same three `ff1a` body lengths 77, 38
and 7. Only the symbol output cell has a different location (`01fa` on the
Courier, `0218` on QF, `0426` on QR).

### The one protocol difference: a 17-or-30 bit INFO0

On the Courier, the INFO0 script step has a fixed 17-bit body. On the two NACs,
the nominal length of the step is 17. But its handler writes a new count before
it sends the body:

```text
a01f  bit   0, @1f
a020  lacl  #1e              ; 30
a021  xc    1, tc
a022  sacl  @4a              ; @1f bit 0 set -> body becomes 30 bits
a023  splk  @48, #a025       ; then hand off to the ff18 emitter
a025  bd    a02b, *
a027  lar   ar0, #ff18
```

17 and 30 are exactly the two V.90 INFO0 body lengths:

| sequence | ITU table | info bits | frame |
|---|---|---|---|
| INFO0a - analogue modem | Table 8/V.90 | `12:28` = 17 | 49 |
| INFO0d - **digital modem** | Table 7/V.90 | `12:41` = 30 | 62 |

Thus the NAC selects its V.90 role at run time with one flag. The analog
Courier does not have this branch. QR 6.1.3 contains the identical construct at
`9e4f`.

### The builder proves it is really INFO0d

The same `@1f` bit 0 divides the field construction at `9535`:

```text
9535  lar   ar1, #039f
9537  bit   0, *
9538  bcnd  9540, tc          ; digital role -> skip the analogue write
953a  lar   ar0, #ff18
953c  bd    9948, *
953e  splk  @7f, #0010        ; offset 16 -> INFO0a bits 12:27
9540  ...                     ; digital path continues
```

We applied the offset rule from the Courier work (`ITU bit = 12 + (N-1-offset)`,
thus `41 - offset` when `N = 30`). The three writes on the digital path then
align with field boundaries of Table 7:

| site | offset | ITU bits | value written | Table 7/V.90 |
|---|---|---|---|---|
| `9547` | 29 | 12:27 | `[ffdb] & f1ff` | the shared capability field, with `21:23` forced to 0 |
| `9550` | 12 | 29:38 | `6 + ([ffdf] << 5)` | `29:32` nominal Phase 2 power; `33:37` maximum power |
| `955f` | 3 | 38:40 | see below | `38`, `39`, `40` |

The last write gives the clearest confirmation, because it is three single-bit
fields in a sequence:

```text
9554  lar   ar1, #ffd9
9556  bit   0, *
9557  lacl  *
9558  cmpl
9559  and   #00000800
955b  bsar  11                ; value bit 0 = NOT [ffd9] bit 11
955c  xc    1, tc
955d  add   #02               ; value bit 1 = [ffd9] bit 0
955e  add   #04               ; value bit 2 = 1
955f  calld 9948, *
9561  splk  @7f, #0003
```

Value bit `j` goes to ITU bit `38 + j`. Table 7 gives these fields:

* **38** - "the digital modem's power shall be measured at the output of the
  codec". The value comes from the complement of `[ffd9]` bit 11.
* **39** - "PCM coding in use by digital modem: 0 = mu-law, 1 = A-law". The
  value comes from `[ffd9]` bit 0.
* **40** - "ability to operate V.90 with an upstream symbol rate of 3429". The
  value is always 1.

One write gives three named V.90 digital-modem fields in the correct sequence.
This also derives the offset rule of the Courier again, independently, on the
server side.

The `29:38` write agrees in the same way, but it needs one inference. The
nominal field `29:32` gets the literal 6, and `[ffdf]` starts at ITU bit 34.
The unit of `29:32` is -1 dBm0 steps and the unit of `33:37` is -0.5 dBm0
steps. Thus a value at bit 34 and not at bit 33 is the same power multiplied by
two. This is the unit conversion between the two fields. That reading is an
interpretation. The raw fact is the expression `6 + ([ffdf] << 5)` at offset 12.

### What is *not* different

In these images, the x2 half is not a separate server protocol. The NAC has no
x2 construction on the `ff18` side that the Courier does not have. Also, the x2
diagnostic vocabulary is **client-only**:

| string | QF 6.0.3 | Courier 4.03 | `IDSDL302` |
|---|---|---|---|
| `not a Server` | 0 | 1 | 1 |
| `not x2` | 0 | 1 | 1 |
| `Multiple CODECs` | 0 | 1 | 1 |
| `Incompatible versions` | 0 | 1 | 1 |
| `V.90 Status` | 0 | 2 | 2 |
| `x2 Status` | 2 | 1 | 1 |
| `x2 Signature` | 2 | 0 | 0 |

This distribution is correct for a server. A *client* prints the failure enum
("Remote modem is not a Server", "Multiple CODECs in channel") about a peer.
Thus the NAC does not contain it. The NAC adds `x2 Signature` next to
`x2 Status` in its label block for link diagnostics. The Courier does not have
`x2 Signature`.

### What this does not establish

These are static findings from the flattened images. We did not execute any of
this code. Also, we did not trace the flag that selects the digital role (`@1f`
bit 0 in the DSP) back to the controller command or configuration that sets it.
That producer is the next step. It is the same type of question as the open
`37:39` writer on the Courier side.
