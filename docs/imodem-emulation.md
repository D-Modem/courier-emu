# Emulating the I-modem

The command interface answers: `isdn-run --send ATI3` gets
`USRobotics Courier I-Modem with ISDN/V.34` back out of SIO0, and
`--terminal` attaches a live console. [The AT interface](imodem-at-interface.md) describes the 16550 model, the evidence for the
port decode and IRQ3, the `ATI0`-`ATI30` sweep, and why a bare `AT` answers
`NO CARRIER`. All the text below is older than the
receive path. It describes a harness that could only transmit.

Current runtime transport: [mailbox service and acknowledgment](imodem-mailbox-service.md).
IRQ13 now services the command ring of the supervisor, and this removes the drain timeouts
that we saw. `isdn-run --with-dsp` now executes the downloaded resident and
overlays on the native C5x, with mailbox acknowledgments in the two directions. The
default endpoint still captures commands for comparison. The VRTX trace supersedes the historical
startup interpretations below.

Most of it already exists, and the DSP half is the same part.

## What runs today

`courier_emu.isdn.IsdnMachine` is a 386 real-mode harness on Unicorn:
`courier-emu isdn-run Ie030002.nac`.  It enters at `4030:0000`, the recovered
initializer. It models the PC-AT devices that the firmware actually touches: an
8254 and a pair of 8259s, two 16550s at `f8f8` and `f4f8`, the board status
port `1e`, and the download ports `40`-`56`.

It goes far enough to load the DSP, and we can now check that and do not assume it.
In a 3,000,000-instruction run, the harness captures 47,088 bytes on
the download ports. We compared them with the images read from the overlay table
([x2-symmetric-and-all-digital.md](x2-symmetric-and-all-digital.md)):

```
stream[16      : 15088] == image 10   (15,072 bytes, byte for byte)
stream[15088   : 47082] == image 11   (31,994 bytes, byte for byte)
```

The two images are complete, in that sequence, after a 16-byte preamble.  That is exactly
the pair that the routine at `b1655` requests (`mov [e738],0a` then `mov
[e738],0b`). Thus, a live boot confirms the table derivation (`cs = a400`, rows at `d682`, segment
table at `d6ca`), not only a static read.  It
also gives information about the board: the image that the I-modem loads first is the
PCM image.

## The DSP is the same part

The images decode with `tools/c5x_disasm.py` without changes. The resident loads at
`8000`, the same as on the analog Courier. The sample paths use the same memory-mapped
`@20`/`@21` (DRR/DXR). The download handshake has the same shape: status
bits polled on port `1e`, and words streamed out of `40` upward. The analog
board uses `40`-`4e`.

Thus, `courier_emu.dsp.NativeC5x` must run these directly.  Its `load_program`
already takes raw bytes and an origin. The only problem is that its
constructor is typed to `XmfImage`.  To widen that type, and to connect the download ports of the ISDN
harness to the core and not to a `bytearray`, is all the work of the
join. The analog side already has that pattern in `dsp_mailbox` and
`probe_transport`.

## Memory: more on the CPU side, not on the DSP's

| | analog Courier | I-modem |
|---|---|---|
| CPU | 80C186EB | 386, real mode |
| flash payload | `b8000` bytes at `40000` | `b8000` bytes at `40000` |
| RAM cleared at entry | - | 256 KiB, then `41c0` bytes relocated to `0ce00` |
| DSP program space used | `8000`-`f5d9` | `8000`-`ee6f` |
| DSP images | 4, 48,344 words | 7, 52,936 words |

The CPU side is clearly larger: a 386 with a flat megabyte, and not
an 80186, and a quarter of a megabyte cleared before anything starts.  The
DSP side is not larger. The images of the I-modem go to a **lower** address than those of the analog Courier, to
`ee6f` against `f5d9`. Thus, the same 32K-word external RAM
([dsp-map-302.md](dsp-map-302.md)) covers it.  It has more images, not
more space: seven images, loaded in and out of the same space, including the PCM pair
that needs two loads to fit.

## What is missing

* The C5x is downloaded but not executed. The harness records the stream.
* The ISDN settings store.  The S/T transceiver and the D-channel HDLC are
  now modelled, and the line starts
  ([imodem-d-channel.md](imodem-d-channel.md)). But each ISDN setting reads
  back invalid or empty, thus Q.921 never starts.  The I-modem keeps them
  in flash sector SA8 at `0xf8000`, which holds two copies of the record
  ([imodem-config-sector.md](imodem-config-sector.md)). It does not use the 93C66 that the
  other Couriers have.  `--flash-overlay` carries a sector into a run. The open item
  is to write a record that the firmware accepts, because we did not recover the
  checksum of the trailer.  B-channel routing is still not modelled. The MCRs are
  recorded, but the model does not act on them.
* Which device raises the system tick.  The harness drives IRQ10 from 8254
  counter 0, because the tick-delay routine at `a45df` needs that line.
  We did not recover the physical wiring.

## The payload is the firmware, at its final addresses

The `0xb8000` payload divides at `0x80000`, the base of the flash window:

| region | size | erased | what |
|---|---:|---:|---|
| `40000`-`80000` | 256 KiB | 3.8% | the updater; holds the entry `4030:0000` |
| `80000`-`f8000` | 480 KiB | 18.5% | the runtime firmware |

The upper half is not only *present*. It is **already at its final
addresses**.  Payload offset X is at `0x40000+X`. Flash offset X-`0x40000`
is at `0x80000+X-0x40000`, which is the same address.  All the code that executes in a
run (`a45ef`, `a543b`, `b1269`) and each DSP image (`d0d60`-`eab0c`) is above
`0x80000`.  Thus, the image is the full firmware, at the correct location. What a board
has and this image does not have is the top **32 KiB**, `f8000`-`fffff`: the boot block
with the reset vector.  The updater never supplies it. It erases at `f8100`
and programs nothing above, because it does not replace the block that it boots
from.

`courier_emu/imodem_rom.py` fills that gap synthetically.  The boot block that it
writes contains a reset vector and a far jump and **nothing else**. The 386EX
bring-up is left to the initializer of the payload itself. We see that initializer do
all of it (chip selects, the two 8259s, the 8254, the two SIOs, the port configuration),
and we do not invent it here.  Two items are manufactured, and you must
know this. The contents of the real block are unknown, and **we did not recover the
entry point of the application itself**. Thus, the jump goes to the
initializer of the updater. The result boots like a board, and then it runs the updater.

It does run.  When it is entered at `f000:fff0` with the assembled 512 KiB part:

```
entry f000:fff0     autoselects 5   erases 3   programs 4096
DSC registers written 28            DSP bytes downloaded 49,736
```

The programming is new. Each earlier run reported `programs 0` and never went past
the identification.  Then it stops at the same location as before. It spins in the ring
wait at `a543b` for `[c9ae] == [c9b0]`, which only the serial ISR at `b7dcc`
advances.  The interrupts from the SIOs are the next part.

## The application's entry point is not in the payload

**Superseded interpretation:** the later
[VRTX startup trace](imodem-vrtx-startup.md) shows the kernel initialization,
the successful creation of nine named firmware tasks and the execution of all nine.
`a400:0008` is explicitly registered as `TID_MODEM`. The historical reasoning
below does not establish that the application startup is absent, or that the
full lower payload is only updater code. The real reset handoff is still
not confirmed.

We looked for it and did not find it. There is a structural reason, not a search
failure.

A cold start on this board must bring up the 386EX: chip selects, the two
8259s, the 8254, the two SIOs and the port configuration.  The firmware does that
from a **table of three-byte records** (port word, then value), read by a
loop at `4040b`.  The table is at `40434`-`4046a`, and the runs in it are
recognizable:

```
43 f0 34 | 43 f0 74 | 43 f0 b4        the 8254
20 f0 11 | 21 f0 20 | 21 f0 04 | …    ICW1..ICW4, master then slave
fb f8 80 | f9 f8 00 | f8 f8 02 | …    SIO0, then the same for SIO1
```

A search of the full payload for those runs finds **one copy of each, all in the
updater half**.  The flash half has none.  Thus, the application does not bring up
its own hardware. The boot block does, and the boot block is exactly the
32 KiB that the payload never supplies.  An update image does not need to name
the cold entry of the application, and this one does not name it.

Two results are important:

* **What we modelled as "the firmware's init" is the init of the updater.**  The 386EX
  sequence runs at `403af`, `403cf` and `4040b`. The Am79C30A setup in
  [imodem-isdn-front-end.md](imodem-isdn-front-end.md) runs at `40b3a`.  All
  three are below `0x80000`.  The register semantics that we recovered there do not change
  (the chip is the same chip), but the code that drives them is the update
  program, not the application.
* **The flash half is entered through gates, and we do have those.**  These are the
  vectors that the updater installs into it:

| vector | target | |
|---|---|---|
| INT `02` | `c774:0300` = `c7a40` | |
| INT `20` | `a400:ef1a` = `b2f1a` | a real ISR - `pusha ; push ds ; push es ; mov ax,2600 ; …` |
| INT `23` | `b2aa2` | |
| INT `25` | `cfdb0` | |
| INT `26` | `a400:120a` = `a520a` | |
| INT `2c` | `c774:0502` = `c7c42` | |
| INT `30` | `7360:0000` = `73600` | the updater's own gate, 2,085 calls in 3M instructions |
| INT `31` | `98d1:0000` = `98d10` | data, not code - the relocation descriptor for the `41c0` bytes moved from `98d50` to `0ce00` |

Those are real entry points into the flash half, and they are useful.  None of
them is the cold entry.

32 KiB from a board (`f8000`-`fffff`) would give the answer.  Without that,
the next thing to try is a scan of the flash half for a routine that installs
the full interrupt table. This assumes that the application points again the
vectors that the updater now owns.

### Found: `a400:0008`

The previous section said that the cold entry was not in the payload.  That was
correct about the *bring-up* but wrong about the entry. We can recover the entry
from the code that installs interrupt vectors.

Three sites in the flash half write vectors, and two of them name the segment:

```
c7d85  mov ax,0 ; mov es,ax ; mov bx,008c        ; vector 23
       mov word es:[bx], d86e
       mov word es:[bx+2], a400                  ; <- the segment
c5479  mov ax,0 ; mov es,ax ; mov di,0080        ; vectors 20..2f
       mov cx,0010 ; mov ax,00bd
       stosw ; add ax,0006 ; mov word es:[di],3497 ; add di,2 ; loop
```

Thus, the code segment of the firmware is **`a400`**. This independently agrees with the
DSP overlay loader, whose table at `cs:d682` resolves only with `cs = a400`.
The hardware vectors `20`-`2f` point to a sixteen-entry stub table in
**RAM at `34970`**, six bytes apart. That is exactly the RAM block that we saw
execute the flash identification.

Segment `a400` is physical `a4000`, and it starts with:

```
a4000  bd 0b 00        mov bp, 000b        ; the same signature the analog
a4003  e9 05 0c        jmp  a4c0b          ; flash carries at its own base
a4006  eb fe           jmp $
a4008  fc              cld                 ; <- the cold start
a4009  b8 00 26        mov ax, 2600
a400c  8e d8 8e c0     mov ds, ax ; mov es, ax
a4010  e8 30 d2        call …
a4013  b8 00 80        mov ax, 8000
a4016  e8 64 d2        call …
a4019  b8 00 00        mov ax, 0000
a401c  b9 7c 24        mov cx, 247c        ; the resident DSP image, to the byte
a401f  e8 3c d3        call …              ; the download
```

`0x247c` is exactly the length of image 5. Thus, this is the sequence that loads the
DSP resident: a cold start, not a service routine.  When we boot the assembled ROM
at `a400:0000`, it runs two instructions and traps on the `int3` at `a4c0b`.
When we boot at **`a400:0008`**, it runs 30,000,000 instructions without a fault,
relocates code into RAM, and starts the DSP download.  Then it stalls at
`7f98c`, in the relocated block, after it sent 24 bytes. That is the same type
of wall as before: nothing yet answers on the DSP or on the interrupt lines.

`imodem_rom.DEFAULT_ENTRY` is now `a400:0008`. `UPDATER_ENTRY` is kept to
boot the update program instead.

### What it stops on, exactly

There are two different items, and neither is a device.

**When we boot the ROM alone, it does not stall. It goes off the correct path.**  When we trace it from the
reset vector, the cold start runs:

```
a4008  cld ; mov ax,2600 ; mov ds,ax ; mov es,ax
a4010  call b1243          ; DSP download
a4016  call b127d          ; and again
a401c  mov cx,247c         ; the resident image's length
a401f  call b1503          ; the download proper
a4022  xor bp,bp ; pushf ; push ds ; push es ; push ax
a4028  push 0ce0 ; pop ax ; mov es,ax ; mov ds,ax ; pop ax
a4031  call far 7561:443e  -> 0x79a4e
```

`0x79a4e` is **below the flash window**.  In a ROM-only boot, nothing is mapped
there. Thus, it executes a field of zeros (`add [bx+si],al`) and continues until it
wraps.  That call shows that the application expects RAM that is already
populated when it starts: code at segment `7561` and data at `0ce0`. The data location is
exactly where the initializer of the update image itself puts the `41c0` bytes that it
moves from `98d50`.  To populate RAM is part of the job of the boot block, and the
boot block is the part that we do not have.

**When we boot with the lower half of the payload mapped, thus with RAM content, the
cold start completes.**  It sends **47,096 bytes** to the DSP (against 24 in
the ROM-only boot). Then it stays in a two-instruction loop at
`a45df`/`a45e3`.  That is the tick-delay routine that `courier_emu/isdn.py` already
names, and `hardware_interrupts` is **0**. The synthetic boot block never
programs the 8259s or the 8254, and the application does not do it itself.

Thus, the two results have the same missing part.  A real boot block brings up the 386EX and fills RAM.
Our boot block only jumps.  The bring-up half does not need a guess:
the table of the board itself is in the image at `40434`, three-byte records, in sequence:

```
f043 34 / f043 74 / f043 b4                       the 8254
f020 11 / f021 20 / f021 04 / f021 11 / f021 ff   master ICW1..ICW4
f020 c2 / f020 48                                 OCW
f0a0 11 / f0a1 28 / f0a1 02 / f0a1 01 / f0a1 ff   slave
f8fb 80 / f8f9 00 / f8f8 02 / f8fb 03 / f8f9 0b   SIO0
f4fb 80 / f4f9 00 / f4f8 02 / f4fb 03 / f4f9 0b   SIO1
```

The next step is to replay those from the boot block, and to copy the RAM half into place.
Both are transcription, not discovery.

### The bring-up, replayed - and where that ends

`imodem_rom.bring_up_code()` now reads the initialization table of the firmware itself
from the image, and writes it as straight-line `mov dx / mov al|ax / out`, in
sequence, before the jump.  It finds the table by its 8254 anchor
(`43 f0 34 / 43 f0 74 / 43 f0 b4`) and parses it in two sections: **35 three-byte
records** (port word, byte value) that end in a zero, then **24 four-byte
records** (port word, word value) for the chip-select unit.  This gives 379 bytes of boot
block, and we composed none of them.

It works up to a point.  The 8254 is programmed and counts. The run
reports **12,935 timer ticks**, where before it reported none. SIO0 sends its
first byte.  But no interrupt occurs: `hardware_interrupts` stays
**0**, and the cold start still stays in:

```
a45d8  push ax
a45d9  mov ah, [c8cb]      ; the tick counter
a45dd  add ah, al          ; al = how many ticks to wait
a45df  cmp ah, [c8cb]
a45e3  jne a45df           ; spin until the ISR gets there
```

This is a delay routine that waits for a counter that only a timer ISR advances.  The ISR
cannot advance it here, because **IF is clear** on this path.  When we unmask the
cascade and IRQ10 manually and set IF in the boot block, nothing changes
(still `irq 0`), because the code that got us here clears the flag again.

That is the useful negative result: it is not a masked line or a missing
vector.  A real cold start would not call a tick delay with interrupts off. Thus,
**the path that the code takes is not the real one**. That is the expected result,
because the far call at `a4031` goes into the update program and not into
the code that the boot block puts at segment `7561`.  To follow the cold start
correctly, we need that RAM image, and the image does not have it.

The base that this gives is still useful: the reset vector, the board bring-up from
the table of the board itself, the DSP loaded with 47,096 bytes, the flash command set and the
DSC register file.  But it cannot start the application in the same way as a board.

### The analog Courier's boot block, and what it says about the I-modem's

The analog side has what the I-modem does not have: a full flash. Thus, we can
read its boot path directly.  From the reset stub at `ffff0`:

```
ffff0  cli ; mov dx,ffa4 ; mov ax,8000 ; out dx,ax   ; the 80186's UMCS
       jmp far fc00:1a21                              -> fda21

fda21  cld ; xor ax,ax ; mov ds,ax ; mov es,ax ; mov ss,ax ; mov sp,00f8
       mov word [ffa8], 00ff                          ; LMCS
       mov si,1976 ; mov cx,0024                      ; 36 word records
       lods cs:[si] ; xchg dx,ax ; lods cs:[si] ; out dx,ax ; loop
       mov si,1a06 ; mov cx,0009                      ; 9 byte records
       lods cs:[si] ; xchg dx,ax ; lods cs:[si] ; out dx,al ; loop
       xor ax,ax ; mov si,ax ; mov di,ax ; mov es,ax
       mov ax,cs ; mov ds,ax ; mov cx,1975 ; shr cx,1 ; inc cx
fda61  rep movsw                                      ; cs:0 -> 0000:0
       xor ax,ax ; mov ds,ax
fda67  int 13
```

Three facts come from this, and all three apply to the I-modem.

* **The table-driven init is the same design.**  Word records, then byte
  records, read by `lods`/`out`. The tables of the I-modem at `40434`/`4049e` are
  the 386EX version of the same idea.  Thus, to replay them from a synthetic block
  is the correct shape, not a workaround.
* **The boot block has a low-RAM image and copies it down**: `0x1976`
  bytes from the start of its own segment to `0000:0`.  The missing 32 KiB of the I-modem
  must also have that part. It explains what the
  code of the I-modem expects to find at segments `0ce0`, `3497` and `7561`.
* **The application is entered through a vector, not an address.**  The last
  instruction is `int 13`, dispatched through the table that was just copied in.  Thus,
  there is no far reference to a cold entry in the flash, and there
  is none in the payload of the I-modem either. This is now explained, and not only
  observed.

**Correction.**  This document reported `a400:0008` as the cold start of the I-modem.  It
is not.  A normal update run executes it exactly once, called by the updater,
and it returns through `call far 7561:443e`, into the update program.  The
sequence is real and does load the DSP resident (`mov cx,247c`), but it is a
routine that the updater calls, not a boot entry.  `imodem_rom.DEFAULT_ENTRY` is
`UPDATER_ENTRY` again, and `DSP_LOAD_ENTRY` is kept with its own name.

The low-RAM image of the I-modem would let it boot correctly. It is not in
the payload. The code at `79a4e` that the cold path calls is **nowhere**
in the flash half. Thus, the boot block is the only location for it.

### Can the missing piece be inferred?  Not the code - but there is less missing than it looked

There are two separate answers, because we called two different items "missing".

**The routine at `7561:443e` is not missing.**  It is update-program
code, and it is specific to the version. The region at `75610` is only **1.4%-1.9%**
byte-identical between `Ie030002` and the four other releases at the same
address, and the reference block is in none of them.  Its own first
bytes give the answer:

```
75610  popa ; pop ds ; pop es ; mov ax,0011 ; int 30 ; iret
```

`int 30` is the service gate of the updater itself.  Thus, `a400:0008` is a flash-half
routine **linked against the update program**. The updater calls it, it loads
the DSP resident, and it calls back through code of the `int 30` period.  None of
that is a boot path. This is the last confirmation that it is not the
cold start of the application.

**The low-RAM image of the boot block is missing, and we cannot infer it.**  It is not in these four
locations:

* not in the flash half: the code at `79a4e` that the path calls is
  nowhere in `80000`-`f8000`;
* not compressed there either: across all 480 KiB there are **zero**
  4 KiB windows above 7.2 bits of entropy, and the full region is at
  6.7;
* not in the sibling releases: the same address is almost fully different
  across all nine;
* not written by the updater: it erases the block at `f8100`, but sends **no
  program setup** at or above `78000` in any path that we ran.

43 KiB of compiled code cannot be reconstructed from its call sites.  The call sites
give only the interface: the code is entered by a far call with
`ds = es = 0ce0`, and the body is compiled C (`push bp ; mov bp,sp ; sub sp,18`)
that touches data at `ds:a63f`.

**We can infer, and have now recovered**, all the items around it: the structure of the boot
block from the analog boot block (segments and stack, the word and byte
port tables, `rep movsw` of a low-RAM image into `0000:0`, dispatch by `int`),
the equivalents of those tables in the I-modem itself at `40434` and `4049e`, and the
convention that the application is entered through a vector and not an
address.  That is sufficient to build a boot block with the correct shape.  It is
not sufficient to make one with the correct content.
