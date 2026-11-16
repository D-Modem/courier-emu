# What the ROM dump proves about the host/DSP mailbox

We read the on-chip ROM from the live board. We downloaded a kernel to the DSP, and
the kernel sent 2048 words back to the 80186, which printed them. That run
**worked on hardware**. Thus, its two halves are a verified description of the
mailbox. They are not an inference. This is the only traffic through
this interface that hardware confirmed, so read it carefully.

Sources: `build_rom_dump_probe` in `courier_emu/dsp_probe.py` (the DSP half) and
`build_diagnostic` in `courier_emu/probe_transport.py` (the 80186 half).

## The DSP half

```
poll:  lar  ar2, #ff57       ; PA7, the status port
       lacc * ; lamm *       ; read it through the SARAM helper
       sacl @7d
       bit  14, @7d          ; bit 15-14 = bit 1
       bcnd poll, ntc        ; spin while bit 1 is CLEAR
       out  @7c, 005e        ; tag  -> PA14
       out  *+,  005f        ; data -> PA15
       lacl #02
       samm @57              ; write 2 to PA7
```

## The 80186 half

```
rx_wait:  e41c       in   al, 0x1c
          a802       test al, 2        ; bit 1
          75         jnz  rx_ready     ; spin while it is CLEAR
rx_ready: e45a       in   al, 0x5a     ; tag  high
          88c4       mov  ah, al
          e458       in   al, 0x58     ; tag  low
          39d8       cmp  ax, bx       ; the tag is the sequence number
          e45e       in   al, 0x5e     ; data high
          88c4       mov  ah, al
          e45c       in   al, 0x5c     ; data low
          ab         stosw
          b002 e61c  mov  al, 2 ; out 0x1c, al    ; acknowledge
          30c0 e61e  xor  al, al ; out 0x1e, al
```

## The mapping, from the two together

| DSP side | 80186 side | carries |
|---|---|---|
| PA14, data `0x5e` | ports `0x58` low, `0x5a` high | message tag |
| PA15, data `0x5f` | ports `0x5c` low, `0x5e` high | message data |
| PA7, data `0x57` | port `0x1c` | the status flag |

The ports of the 80186 are byte-wide, and little-endian in pairs. The ports of the DSP are single
16-bit ports. Thus, four 80186 ports carry the two DSP words.

## The polarity, which is the part worth having

**The two sides both wait in a loop until bit 1 is set.** They cannot read the same
bit with the same sense. Thus, the flag is one mailbox interlock, and each side reads it with the opposite
meaning:

* bit 1 of PA7 on the DSP means **"the send window is free"**;
* bit 1 of `0x1c` on the 80186 means **"a word is waiting for you"**.

The two writes control it:

* When the DSP writes `2` to PA7, it deposits its word. This clears its own "free" and
  sets the "waiting" of the host.
* When the 80186 writes `2` to `0x1c`, it acknowledges. This clears its "waiting" and
  restores the "free" of the DSP.

`bridge.py` already suspected this. Its comment on the `0x1c` read says that the
model "commits on the `0x5e` write instead and uses the bit only to pace the
C52's next quantum; the two agree on ordering, not polarity." The dump gives the
polarity.

The result for each transparent port mapping is this: do not copy `0x1c` and PA7
to each other. A host write to `0x1c` is an acknowledgement, and it must
*set* the bit of the DSP. For this reason, `_mirror_port` uses OR and not an assignment.

## What it does not tell us

There are two limits, and the two are important.

**It only exercises DSP -> host.** The kernel sends, and the 80186 receives. Nothing
in this run carries a message in the other direction. Thus, the run does not cover bit 0, the host-to-DSP
"message pending" bit that the dispatcher of the resident polls at `0x839b`.
That direction is still an inference.

**It never ran the resident.** The dump downloads its own kernel to `0x8000`, and
that kernel is the full program: a `RPT`/`TBLR` block read and this sender.
These items of the resident had no part in the run: its main loop, its `@1a`/`@1b` dispatch, its receive ring at
`0x0bd0`, and the `ARCR` comparison that gates all of its block-level work.
Thus, this run cannot say what initialises `ARCR`. That is the
open blocker in
[what-runs-and-what-blocks.md](what-runs-and-what-blocks.md). The run proves that the
mailbox operates on hardware, but it tells us nothing about why the resident never
gets to its poll.

Keep this split clear: **the transport is confirmed, the
resident's use of it is not.**
