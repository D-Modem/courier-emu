> **2026-09-07 correction:** the recovered ROM is now integrated. The IPTR
> interpretation below was incorrect. PMST bit 7 is AVIS, and IPTR is in bits
> 15–11. These builds keep vector base zero, with timer vector `0x0008`.
> Refer to [the integration and validation](dsp-onchip-rom.md#bridge-integration-2026-09-07).

# The DSP mailbox map for IDSDL302.ROM only

**These addresses apply to `IDSDL302.ROM` (DSP 3.0.13) and to no other
image.** They are not the addresses in
[who-produces-the-events.md](who-produces-the-events.md). Those came from
`artifacts/courier-board-21210-capture-403/courier-board.rom` (DSP 3.1.2). The
two builds have more differences than offsets: they use different cells and a
different ring. Thus, if you move an address from one build to the other, you
make a probe that reads the incorrect memory and reports nothing. This file
exists to prevent exactly that mistake.

All the items below use one anchor: the one `out *, 0060` in the image, at file
`0x299ee`. `dsp_mailbox.py` identifies it as the 3.0.13 sender at DSP
`0x84b7`. The addresses are DSP program words. The linear file mapping is
`dsp = (file / 2) - 0x14CF7 + 0x84b7`.

## The map

| what | 302 (3.0.13) | 403 (3.1.2) |
|---|---|---|
| status latch, read through AR1 | **`0xFF57`** | `0x57` |
| tag cell | **`0xFF5E`** | `0x5E` |
| word cell | **`0xFF5F`** | `0x5F` |
| cell-read helper | `0x23f0` | `0x80e8` (`lamm *`) |
| service loop | `0x80c8` | `0x80bb` |
| receive dispatcher | `0x839b` | `0x8387` |
| dispatch table base | `0x8401` | `0x83e9` |
| outbound ring base | **`0x0bd0`** | `0xff60` |
| ring write / read pointers | `@78` / `@79` | `@78` / `@79` |
| message sender | `0x83d6` | `0x83d6` |
| stream resume poll | `0x847a` | `0x8462` |
| stream vector cell | `0x039e` | `0x039e` |
| tag-06 handler | `0x8489` | `0x8470` |
| stream sender | `0x84b7` | `0x849e` |
| packer | `0x84bc` | `0x84a3` |
| idle wait | `0x8149` | `0x8138` |
| frame ISR entry | `0x816b` | (not located) |

The status bits are the same in the two builds. The DSP writes `1` to
acknowledge a receive, `2` to complete a send, and `4` for a stream word.

> **Corrected: those are bit *codes*, not bit numbers.** On the C5x,
> `BIT dma, code` tests bit `15 - code` (this core calculates
> `(~op >> 8) & 0xf`). Thus the instructions that this document read as
> "bit 15", "bit 14" and "bit 13" test bits **0**, **1** and **2**:
>
> | instruction | disassembles as | tests | meaning |
> |---|---|---|---|
> | `4f7d` | `bit 15, @7d` | **bit 0** | a message is pending |
> | `4e7d` | `bit 14, @7d` | **bit 1** | the send window is free |
> | `4d7d` | `bit 13, @7d` | **bit 2** | resume the stream |
>
> This is not cosmetic. `bridge.py` raised `0x8000` for pending and `0x2000`
> for resume, thus the poll of the dispatcher never saw either. It is the
> direct cause of the symptom that this document records below: "the tag and
> word arriving and bit 15 never being consumed".

## The dispatcher, at 0x839c

```
839d  calld 23f0, * / lar ar1, #ff57   ; read the status latch
83a3  bit  15, @7d / retc ntc          ; nothing pending
83a6  calld 23f0, * / lar ar1, #ff5e   ; the TAG
83ad  calld 23f0, * / lar ar1, #ff5f   ; the WORD  -> @7a
83b3  lacl #01 / samm @57              ; acknowledge
83b6  sub  #7f / retc gt               ; reject above 0x7f
83b8  add  #00008480 / tblr @7c        ; table base 0x8480 - 0x7f = 0x8401
83bc  bacc
```

The table entries confirm the identification against constants that this
repository got from hardware. Tag `0x06` goes to `0x8489`, and tag `0x42` goes
to **`0xb05e`**. This is exactly the "Tag 42's handler at b05e" in
`dsp_mailbox.py`. Thus that comment describes 3.0.13, not 3.1.2.

## The service loop, at 0x80c8

```
80c6  call 8223, *
80c8  call 839b, *, ar1     ; the receive dispatcher
80ca  call 83d6, *, ar1     ; the message sender
80cc  call 847a, *, ar1     ; the stream resume poll
80ce  call 80f8, *
80d0  lar  ar0, @10 / cmpr eq
80d2  bcnd 80c8, tc         ; loop
```

Each iteration has the same three calls as the loop of 3.1.2 at `0x80bb`. Note
that the dispatcher entry is `0x839b`, one word before the `setc intm` that
this document quoted first. `ldp #000` comes first, as it does in 3.1.2.

**The DSP does not get to it.** When we sample the PC of the core during a
run, there is nothing at `0x80c8`, `0x839b`, `0x83d6` or `0x847a`. The `idle`
wait poll of the run at `0x814d` gets 237 samples, and `0x80ac`, in the call
sequence before the loop, gets 26.

Be careful when you read that histogram: its largest entries are an artefact.
`0x801d` gets 1617 of 3999 samples, `0x8024` 406, `0x8028` 207. But those are
the block clears of the reset prologue, `rptz #03ff` / `sach *+` and similar
instructions, where one instruction repeats 1024, 256 and 128 times. A sampler
lands there in proportion to the repeat count. This does **not** mean that the
part resets again and again: a run makes the core one time and bootstraps one
time.

> **Corrected.** The last sentence is correct about the harness and incorrect
> about the part. The harness bootstraps one time, but the *firmware* entered
> its own reset prologue again: four passes in 200k instructions, forty in 2M.
> The cause was that the helper copied into `0x23f0` was three zero words. Now
> the harness models the shared external window below, and the prologue runs
> one time. This section reads the `idle` at `0x814d` as a failure to get to
> the loop. In fact, a part that boots correctly waits there.

## Two things this map exposes

**The delivery that this harness does cannot work on 302.**
`_deliver_host_message` writes cells `0x5e`, `0x5f` and `0x57`. This is
correct for 3.1.2, where the helper is `lamm *` and masks the address to
`0x7f`. On 3.0.13, the dispatcher reads `0xFF5E`, `0xFF5F` and `0xFF57` through
a different helper. When the harness writes the low cells, the cells that the
dispatcher reads do not change. This is why each 302 run showed the tag and
word arriving and bit 15 never being consumed.

Also, 302 *writes* its acknowledgement with `samm @57`, which masks to
`0x0057`, but it *reads* the same latch at `0xFF57`. On the part, those are
probably the same register at two addresses. In a flat model they are two
locations. Thus the read path of the DSP also would not see an acknowledgement
from the DSP.

### Both halves of that are now measured, and both were wrong

A direct test of the dispatcher settles this. Run the resident from `0x8000`
only as far as the `bldp`, so that the helper is installed at `0x23f0`. Then
stage a tag, a word and a status. Then enter through the call site of the
service loop at `0x80c8`, which sets `ARP` to 1. (If you jump directly to
`0x839b`, `*` reads the `AR` that the prologue selected last, and the helper
reads the incorrect address.)

| pending flag | `@7d` | `@57` after | `@7a` | outcome |
|---|---|---|---|---|
| bit 15, as `bridge.py` raised it | `8100` | `8100` | `0000` | returns, nothing consumed |
| **bit 0**, what `bit 15, @7d` tests | `0001` | **`0001`** | **`beef`** | word arrives, acknowledged |

We staged the status as `0x0100 | flag`. Thus, when `@57` reads exactly
`0x0001` after the test, the cause is the `lacl #01 / samm @57` of the
dispatcher, which writes over the marker. This is an acknowledgement, not the
value that we supplied.

Thus there were **two** faults on this path, not one:

1. **The incorrect bit.** Bit 15 for pending, because of the bit-code
   inversion above.
2. **The incorrect storage.** In that passing run, we staged the tag and word
   in the **I/O ports**, not in data cells. `lamm` masks to `0x7f` and reads a
   memory-mapped register, and this core resolves `0x50`-`0x5f` through the I/O
   ports. `_write_host_cell` used only `set_data`, thus it wrote a cell that no
   code reads. The `lacc *` half does load the data cell, but `lamm *`
   immediately writes the register over the accumulator.

Now `_write_host_cell` writes the I/O view together with the two data views,
and `_read_host_cell` includes it.

**Some handlers are outside the loaded segment.** The one segment of the 302
image has origin `0x8000`, 27710 words, and covers `0x8000..0xec3d`. The
dispatch table points below that. Tag `0x7c`, the detector poll, goes to
`0x23f0`, and tag `0x7b`, the DAA identity, goes to `0x7e80`. The cell-read
helper that the dispatcher itself calls is that same `0x23f0`. Thus, on 302,
the mailbox path calls into program memory that no overlay in the image
supplies.

This contradicts the conclusion in the other note that a ROM needs nothing
below `0x8000`. That note used only the overlay entry words. We record the two
observations. This document does not decide which one is incorrect.

## What fills the SARAM

The prologue fills it with a block move. The three words that it copies are
the mailbox helper itself:

```
80a0  lacc #000023f0
80a2  samm @1f          ; BMAR = 0x23f0
80a3  mar  *, ar1
80a4  lar  ar1, #80f5
80a6  rpt  #02          ; three words
80a7  bldp *+           ; data 0x80f5.. -> program at BMAR
```

At `0x80f5` in the downloaded image:

```
80f5  1080  lacc *
80f6  0880  lamm *
80f7  ef00  ret
```

`lacc * / lamm * / ret` is exactly the cell-read helper that the dispatcher and
the resume poll call with `calld` at `0x23f0` on each pass. 403 does not need a
copy, because it keeps the same helper in-bank at `0x80e8`. Thus the firmware
fills SARAM: it reads its own downloaded program **through data space** and
writes it into program space.

### The external RAM answers both spaces, and the earlier retraction was wrong

`bldp` gets its source from data memory. Thus a data read of `0x80f5` must
return the value that the download put at program `0x80f5`. An earlier attempt
at this reported a regression, and we reverted it. We have now taken the
measurement that it asked for, and the measurement shows the opposite.

We logged each data access at or above `0x2c00`, with its PC, during a 2M
instruction standalone run of the 302 resident. The log has **twenty-five
sites and no more**:

| PC | addresses | direction |
|---|---|---|
| `0x8070`-`0x8081` | `0xfff0`, `0xfff3`, `0xfff4`, `0xfff6`, `0xfff7` | writes |
| `0x80ac` | `0xff51`-`0xff5f`, sixteen cells | writes |
| `0x80a7` | `0x80f5`, `0x80f6`, `0x80f7` | **reads** |
| `0x0bf7`, `0x0bf8` | `0xff60`, `0xff61` | reads |

Thus, on the boot path of the resident, the firmware does exactly **three**
data accesses in `0x8000`-`0xfeff`. All of them are reads, and all are the
`bldp` at `0x80a7`. All other accesses above `0x2c00` are at `0xff51` and
higher. That is the ASIC window that the firmware gets to through DP
`0x1fe`/`0x1ff`, and the shared window must stop there.

> **That count is the boot path only, and taking it for the whole firmware was
> a mistake.** The overlays also read data in the window. The V.34 arming path
> reads data `0xfea1` six times from `0xd668`. It walks the capability
> descriptor list that [v34-arming.md](v34-arming.md) recovered. This does not
> contradict the shared model. `0xfea1` is above `0xec3d` of the resident and
> above `0xf8b5` of the highest overlay. Thus it is free RAM that the firmware
> uses as data. This is exactly what one memory that answers in the two spaces
> predicts. But it broke the *harness*. `set_data` put the descriptor into the
> data array, and the running program now read the program array: two arrays
> for one RAM. Now the two accessors both follow the window.

When the program storage supplies `0x8000`-`0xfeff` in the two spaces, the
`bldp` reads `1080 0880 ef00`. This is `lacc * / lamm * / ret`, the helper that
this document predicted, and not three zero words. The behaviour of the part
then changes completely:

| | prologue passes in 200k instructions | ending PC | SARAM fetches | external program fetches |
|---|---|---|---|---|
| before | 4 | `0x814d` | 1,373,184 | 16,281,745 |
| after | **1** | `0x814d` | 7,155 | 67,128 |

The "before" column is a runaway. When zeros go into `0x23f0`, the
`calld 23f0` of the dispatcher executes nothing. The part then continues into
unloaded low memory (the 20M-instruction bridge run ends with its PC at
`0x0115`), and it enters its own reset prologue again and again. The earlier
note recorded this as "running across its prologue", but it was not a healthy
run. The `idle` at `0x814d` was the improvement, and the earlier note thought
that it was a regression.

After the change, the 302 resident boots **one time**, executes its real
helper from SARAM, and stops in the `idle` at `0x814d` to wait for an
interrupt. This is the correct place for a part whose service loop starts from
a frame ISR, because the harness does not yet supply that interrupt.

The change has no effect on 403 in either direction. Its `data_shared` count
is zero, and its run is the same in the two cases, because it keeps the same
helper in-bank at `0x80e8` and never reads program space as data. This
document already made that prediction, and now we have measured it.

### The window applies to the ROM images, not to every image

> **Corrected 2026-09-15.** `main211.xmf` has no segment below `0x8000`. The
> overlay table of its supervisor puts each row at `8000`, `9d00`, `af50` and
> `dc00`. The `0x0000` origin was a harness constant. Thus the question below
> does not apply to the 2.1/2.2 images, and the window stays on for them. The
> 2.3.x XMFs load low (resident at `1000`, one overlay at `0000`) and switch
> the window off. Refer to
> [hardware-timebase-and-audio-path.md](hardware-timebase-and-audio-path.md#3-corrected-the-xmf-payload-loads-at-8000-not-0000).

We read `main211.xmf` as an image with a first segment at origin `0x0000`
*and* one at `0x8000`. Which of those was its real payload is the unresolved
question at the end of this document. For an image like that, the harness
cannot tell where the RAM of the board is. Thus `NativeC5x` switches the window
off when any program segment origin is below `0x8000`, and the data space of
that image then operates exactly as it did before the window existed. When we
switched the window on for `main211`, its call-overlay run became worse, and it
never armed `IMR`.

Thus the window is a fact for the 20.16 MHz ROM downloads, whose segments are
all at `0x8000` or above. For all other images, it is an open question.

**What is still not settled** is the exact edges of the window. The evidence
puts them only between `0x80f7` and `0xff50`. We selected `0xfeff` because the
ASIC pages of the firmware are `0x1fe`/`0x1ff`, not because a read
distinguishes `0xfeff` from `0xfe00` or `0xff00`. No code in either build reads
or writes data between `0x8100` and `0xff50`. Thus no run that this harness can
do will make the range smaller. That needs the board.

## The 0x8000 in these addresses is not independently established

`0x8000` is also where the flash of the *CPU* is (physical `0x80000`, segment
`0x8000`), and the documents did not keep the two uses separate.

* `CourierRom.dsp_download` **filters** on `DSP_ENTRY_WORD = 0x8000` and
  discards each candidate with a different entry word. Thus the origin of the
  ROM path is an assumption that the scan enforces, not a measurement.
* The segments of `main211.xmf` are worse. The harness loads its first segment
  at origin `0x0000`, but the code in it is linked for `0x8000`. The stream
  sender is at word offset `0x05d5`, and the instructions near it read

```
05cb  bd    85d5, *
05cf  calld 85da, *
05d1  splk  *, #85c9
05d5  out   *, 0060
```

  The branch targets are `0x85d5`, `0x85da` and `0x85c9`, but the offsets are
  `0x05xx`. The third segment, which has the label origin `0x8000`, has
  different content and no sender at all. In the first 4096 words, the two
  agree in 11 places.

Thus the segment origins of the harness do not agree with the link addresses
in the code, in both directions. Either an origin is incorrect, or the program
space of the DSP ignores A15 and each label here has a meaning only modulo
`0x8000`.

### The firmware never chooses the mode, and reset lands on the image

Two measurements make this narrower.

**The firmware never writes MP/MC.** We disassembled all four overlays of the
two images and kept only the writes to `@07` with `DP=0` (the memory-mapped
`PMST`). We found **exactly two in each image, both in the resident, none in an
overlay**:

```
8012  apl  @07, #07f8     ; keep bits 3-10, clear the rest
8014  opl  @07, #00b0     ; set RAM (4), OVLY (5), IPTR bit 0 (7)
```

The mask of `apl` keeps bit 3, and `opl` does not touch it. Bit 3 is MP/MC.
Thus the firmware sets `RAM` and `OVLY`, and then **fully accepts the value
that the pin latched at reset**. It never selects microprocessor or
microcomputer mode, in either build. (The name of the pin has a bar over `MC`
because it is one pin with two polarities: high is microprocessor mode, low is
microcomputer mode. There is no second pin.)

Thus, in each run in this repository, the harness sets `MP/MC`, and the
firmware does not. No path gets to microcomputer mode with `PMST.RAM` set. The
probe kernels that force the pin low write `PMST` as `0x0000`, thus `RAM` is
clear there.

**No download goes below `0x8000`.** All four overlay origins in the two
images are `0x8000`, `0x9d00`, `0xb000` and `0xdc00`. But after reset, a C5x
fetches from program `0x0000`. `bridge.py` closes that gap by hand: it calls
`set_pc(entry_word)` to put the part at `0x8000`. Thus the harness does not
model how the real part gets there.

The image shows how. Program `0x8000` is not a branch and not a vector table:

```
8000  ldp   #000
8001  splk  @57, #ffff
8003  setc  intm
8004  ldp   #000
8005  splk  @2a, #0010
```

This is straight-line initialisation. It is exactly what reset must go *to*,
not what a reset vector points *with*. And reset does go to it if external
program space ignores A15. A 32K-word RAM that is wired across a 64K space
gives this result, unless another part decodes the top bit. We aliased external
program fetches to `address | 0x8000` and started the part at `0x0000`, not at
`0x8000`. This gives exactly the same boot: the same single prologue pass, the
same `rptz` repeat counts at the aliased `0x001d`/`0x0024`/`0x0028`, and the
same `idle` at `0x814d` after a branch to an absolute `0x8xxx` label takes it
up.

That reading (**`0x8000` and `0x0000` are the same cell**) is the second of the
two possibilities that this section gave. We offered it as a solution to the
`main211.xmf` problem: on a board that decodes fifteen address lines, a segment
at origin `0x0000` with code linked for `0x8000` is not a contradiction. But
the problem had a different solution. The segment is at `0x8000`, the code is
linked for `0x8000`, and no alias is necessary to make them agree. Thus this is
no longer evidence for an alias.

### The vector base is what argues against it, not the RAM

An earlier revision of this section said that the alias was disproved, because
program `0x23f0` would then be the same cell as `0xa3f0`, which is live code in
the two builds. **That argument is incorrect.** `program_region` tests SARAM
before external memory, and `PMST.RAM` is set. Thus `0x23f0` is on-chip in each
decode of A15, and the firmware never uses an aliased external RAM there. The
alias passes that test.

The sizing objection also fails. Two 32Kx8 SRAMs are 32K **words**, and the
C5x addresses 64K words. Thus the RAM covers *half* the space in each decode.
The bottom half is empty unless something aliases into it. Thus a 2K on-chip
ROM at `0x0000`-`0x07FF` hides nothing and wastes nothing.

The vector base is the item that argues against the alias. It comes from the
same `opl` that this document reads:

* The PMST layout of the core is confirmed **by behaviour**, not only from the
  guide. `RAM` must be bit 4 and `OVLY` bit 5, because `opl #00b0` must map
  SARAM for the `bldp` into `0x23f0` to make a helper. The 302 boot completes
  only when it does. A layout with those bits at other positions leaves SARAM
  unmapped and gives the broken run.
* That same layout makes bit 7 the LSB of `IPTR`. `opl #00b0` sets it, thus
  `IPTR = 1` and the vector base is `0x0080`. The frame interrupt, IRQ 5, would
  go to `0x0080 + (5 + 1) * 2` = `0x008c`.
* With the alias, `0x008c` is image `0x808c`, which is

```
808b  b9f8       lacl  #f8
808c  8832       samm  @32      ; TSPC - live prologue code
```

  and the prologue enables interrupts at `0x809f`, approximately thirty words
  later. Thus the part would enable interrupts whose vectors are on top of the
  instructions that it executes.

Thus `0x0080`-`0x00bf` must be memory that is *not* the aliased RAM. The C5x
puts on-chip ROM there, in microcomputer mode. A ROM vector table that
dispatches to fixed addresses in the downloaded bank would explain the frame
ISR entry at `0x816b`. This document could only infer that entry from its
position.

In principle, there is one way to save the alias, and measurement excludes it.
The prologue at `0x8080`-`0x80bf` runs one time, thus the firmware could
install a vector table over it after that. It does not. We logged each
`PM_WRITE16` during a 20M-instruction bridge run of 302. The log has **three
writes in total**, all of them the `bldp` at `0x80a7` into `0x23f0`-`0x23f2`.
No code ever writes a vector, at any address, in any space.

### The supervisor's own download code settles the order, and the order decides it

This argument does not use a reading of `PMST`, the board, or an item that the
emulator models. It is the download path of the 80186, disassembled from
`IDSDL302.ROM`.

The call site passes the destination and the length:

```
0046f  mov  ax, 0x8000        ; the destination
00472  call 0xe3aa            ; the launch routine  <- before the data
00475  mov  ax, 0
00478  mov  cx, 0xd87c        ; 55420 bytes, the payload
0047b  call 0xe47b            ; the block transfer  <- the data
```

The launch routine at `0xe3aa`, in sequence:

```
0e3ad  mov  dx, 0x40 / out dx, al ... out 0x42   ; destination 0x8000 into the window
0e3c4  out  0x18/0x1a <- ffff ; out 0x1c/0x1e <- ffff
0e3e1  mov  cx, 0x1f4 / loop                     ; a delay
0e3f9  mov  bx, 0xff56                           ; a PCB register
0e3fc  mov  ax, [bx] / or ax, 2
0e403  mov  cx, ax   / and cx, 0xfff7            ; the same word with bit 3 clear
0e406  mov  [bx], ax / nop / nop
0e40a  mov  [bx], cx                             ; bit 3 low
0e40d  or   ax, 8    / mov cx, 5 / loop
0e415  mov  [0xff56], ax                         ; bit 3 high again
0e41a  test [0xff46], 0x20 / in 0x18 / in 0x1c   ; wait for the far side
0e438  mov  al, 2 / out 0x1c, al                 ; then a command
0e43d  ret
```

A line that goes low and then high again after a delay has the shape of a
reset, and this occurs **before the supervisor sends one byte of the
program**. Then the routine waits for the far side to answer before it
returns.

Also, the transfer routine at `0xe47b` ends and never starts anything:

```
0e54c  mov  ax, [0xe39] / out 0x40, al / out 0x42, al   ; the checksum
0e55d  mov  al, 4 / out 0x18, al                        ; submit it
0e569  in   al, 0x18 / test al, 4                       ; wait for the ack
0e56f  pop  es / clc / ret
```

**The supervisor writes no entry address after the block, and it sends no
"go" command.** The only entry address in the full path is the `0x8000` that
it writes into the window *before* the reset pulse.

That sequence forces the conclusion. The part comes out of reset first, and
the program arrives after that. Thus the part executes some code while the
supervisor sends the block to it. Also, some code must transfer control when
the block ends, because the supervisor never does. At that time, external
program memory is the RAM that this download will fill. With A15 not wired,
program `0x0000` is that same empty RAM. Thus the DSP cannot execute external
memory at reset. **It executes on-chip ROM. Thus MP/MC = 0, microcomputer
mode.**

### The on-chip boot loader is what it is executing

The C5x on-chip ROM has an optional boot loader that "can be used to transfer a
program automatically from data memory or the serial port to anywhere in
program memory". The source can be on any 1K-word boundary in data memory.
After the transfer, the loader "releases control to the program for
execution". This is exactly the missing "go".

This is the item that the microcomputer-mode reading did not have. It agrees
with what this repository already measured, and it needs nothing new:

* **It explains the entry.** Program `0x8000` is `ldp #000` and straight-line
  initialisation, with no branch and no vector table. A boot loader that
  transfers a block and then jumps to it lands on exactly that.
* **It explains the origin.** `CourierRom.dsp_download` filters candidates on
  `entry_word == 0x8000` and discards the others. This document identified
  that as an assumption that the scan enforces, not a measurement. With the
  boot loader, it is neither of these. It is the destination address in the
  boot table that the supervisor supplies. This is why each overlay in the two
  images has one.
* **It explains why no download goes below `0x8000`.** The transfer is a block
  copy to one destination, not a link map.
* **It puts the vector base at a legal address.** `IPTR = 1` gives `0x0080`,
  inside the 2K on-chip ROM at `0x0000`-`0x07FF`. The firmware does not own or
  write this memory. This agrees with the measurement above, which found no
  vector writes at all.

### The map, as it now stands

| program | what answers | how it is known |
|---|---|---|
| `0000`-`07ff` | **on-chip ROM**: boot loader, and the vector table `IPTR = 1` selects at `0x0080` | forced by the download order; contents not recovered |
| `0800`-`2bff` | on-chip SARAM, mapped by `PMST.RAM` | `opl @07, #00b0`; the `bldp` helper at `0x23f0` runs |
| `2c00`-`7fff` | external RAM, the same cells as `ac00`-`ffff` | A15 unwired |
| `8000`-`ffff` | external RAM, 32K words, where every download lands | overlay origins; `bootstrap_match` |

| data | what answers |
|---|---|
| `0000`-`005f` | memory-mapped registers; `0x50`-`0x5f` are the ASIC's host window |
| `0060`-`007f`, `0100`-`04ff` | on-chip DARAM B2, B0, B1 |
| `0800`-`2bff` | the same SARAM, mapped by `PMST.OVLY` |
| `2c00`-`feff` | external RAM, the same memory as program space; unreferenced below `0x8000` |
| `ff00`-`ffff` | the ASIC window |

**What the harness does instead.** `bridge.py` runs the part with `MP/MC = 1`
and calls `set_pc(entry_word)` to put it at `0x8000` by hand. This is a
stand-in for the boot loader. It is also why the timer runs away at `0x0088`:
there is no ROM under the vector table. A ROM image would replace the forced PC
and also stop that runaway. `tools/rom_dump_gadget.py` is the attempt to get
one.

### A15 is not wired, and that decides the decode without deciding the mode

From the board: **the A15 of the DSP is not connected.** It cannot be an
address input to a 32Kx8 part in any case, because those parts have fifteen
address pins. It is also not in the chip-select decode. Thus nothing
distinguishes external `0x0000`-`0x7fff` from `0x8000`-`0xffff`. The 32K-word
RAM answers both as the same cells, in the spaces that its `/CE` admits. The
alias is a fact about the board, not a hypothesis.

This does **not** settle `MP/MC`. The reason is that the alias has no visible
effect at almost all addresses that the firmware uses. In a 20M instruction
bridge run of 302, and in the V.34, FSK and VPCM probe runs, there are **no
data accesses at all in `0x2c00`-`0x7fff`**. That is the range where a
data-side alias would show. Thus the firmware does not reference the full low
half of data space, and the shared window that this core models at
`0x8000`-`0xfeff` covers all the accesses that occur.

### Where the alias is not invisible: the vectors, and the part runs away there

The same instrumentation counts external *program* fetches below `0x8000`. It
finds 2,524 of them, contiguous, **starting at `0x0088`**.

`0x0088` is not a random address. With `IPTR = 1`, the vector base is
`0x0080`, and the C5x puts its vectors two words apart from there:

| IFR bit | interrupt | vector |
|---|---|---|
| 3 | `TINT`, the timer | **`0x0088`** |
| 5 | `XINT` | `0x008c` |

Thus the part **takes the timer interrupt, and the hardware vectors it to
`0x0088`**. There is nothing there. The part then runs contiguously through
empty program memory until it gets to `0x8000`, and it enters its own reset
prologue again. This is the mechanism for a discrepancy that this document had
not explained. In a bridge run, the `bldp` at `0x80a7` executes **40 times**,
but in the standalone run it executes one time. The DSP starts again forty
times, and the timer vector is the cause.

Also, `XINT` at `0x008c` is the same slot that `_configure_frame_interrupt`
arms by hand at `origin + 0x0c` = `0x800c`. The harness installs an explicit
vector for the one interrupt that it needs and leaves the others to hardware
vectoring. This is why only the timer runs away.

This corrects a claim from earlier in this section. Hardware-vectored
interrupts **do** occur on this firmware. We do not only read `0x0080` from
`PMST`. It also makes clearer what the vector table must be, now that we know
about A15. With the alias, `0x0088` is image `0x8088`, which is

```
8088  7718  dmov @18
```

This is live prologue code, not a vector. Thus `0x0080`-`0x00bf` cannot be the
aliased RAM in either case. The only item that the C5x can put there is
**on-chip ROM, in microcomputer mode**. The boot loader is also there, and this
agrees with `MP/MC` not being wired.

This gives one coherent account of the full board:

* `MP/MC` is not wired, thus the part is in microcomputer mode. On-chip ROM at
  `0x0000`-`0x07ff` holds the boot loader **and** the vector table that the
  firmware selects with `IPTR = 1`.
* The boot loader transfers the block of the supervisor from data memory to
  program `0x8000` and releases control to it. This is why `0x8000` is
  straight-line init with no branch, and why no download ever goes below it.
* `PMST.RAM` maps SARAM at `0x0800`-`0x2bff`. The SARAM holds the mailbox
  helper that the `bldp` of the prologue writes to `0x23f0`.
* The external RAM is 32K words, with A15 not wired. Thus it answers
  `0x2c00`-`0x7fff` and `0x8000`-`0xffff` as one memory, in the two spaces. The
  firmware references only `0x8000` and higher, thus the aliasing never shows.

**What still keeps this open.** The boot loader is optional, and its ROM is
mask programmed. Thus this document does not show that a USR-marked part has
it, and this repository has no image of it. This paragraph had a caution about
the vector base: that nobody had observed a hardware-vectored interrupt. We
withdraw that caution above: the hardware vectors the timer to `0x0088` on each
bridge run.

The two readings still disagree about one item only: what answers program
`0x0000`-`0x07ff`. The board settles this. Note that A15 cannot be an
*address* input to a 32Kx8 part at all. Those parts have fifteen address pins.
Thus A0-A14 go to the two RAMs in parallel, with the data split D0-D7 /
D8-D15, and A15 can occur only in the chip-select decode. Thus the question is
not "does A15 get to the RAMs". The question is **what drives their `/CE`**.
If `/CE` is tied low, the RAMs answer each external cycle in the two spaces.
This gives the shared window and the alias together. If A15 gates `/CE`, they
answer one half. If `/PS` and `/DS` gate it, they answer the spaces that the
glue admits. The `74VHC32` and `74VHC04` in [board-parts.md](board-parts.md)
are the parts that would do that gating.

Only the shared *data* window is in the core. We reverted the alias.

The one item that does not depend on the harness is the set of constants in
`dsp_mailbox.py`: the sender at `84b7`/`849e`, the table at `8401`, and the
handler of tag `0x42` at `b05e`. These came through the `ATGLK2` monitor on a
physical modem. They agree with the addresses in this document. It is not
recorded if somebody read them back by address from the part, or calculated
them with the same origin assumption. If we knew this, it would settle the
rest.

## What this does not establish

The map is static. We read each address from the image. Only the sender at
`0x84b7`, the tag-`0x06` handler and tag `0x42` have corroboration from
constants that came from hardware. We executed none of this. We infer the
frame ISR entry at `0x816b` from its position after a `ret` and from its `smmr`
context save. We did not see an interrupt get to it. We could not disassemble
the helper at `0x23f0`. It is outside the segment, thus the linear file mapping
does not get to it. We assume its function from its callers.
