# The B channel is silent, and the modem is the one keeping it quiet

[imodem-bri-network.md](imodem-bri-network.md) put a network on the S
interface and intentionally did not make a decision about the bearer. The peer counts the
octets that it captures and does not call `ff` silence, because on an opaque
64 kbit/s channel, `ff` is a byte the same as all other bytes.

It is silence. A full answered call of it: **156,456 captured
octets, and all of them are `ff`**. This page follows it back to
the one item that makes it.

## The call, end to end

The run is an incoming call that the modem answers:

```sh
.venv/bin/python -m courier_emu isdn-run Ie030002.nac --with-dsp \
    --no-flash-nvram --instructions 80000000 \
    --bri-network --bri-establish terminal \
    --bri-call-at 20000000 --bri-call-to 7349195 \
    --bri-rx-g711 far-end.g711 --bri-tx-g711 modem.g711 \
    --send ATA --send-after 30000000
```

It goes all the way, and this is new:

```
ID_REQUEST ref 16399: assigning TEI 64      RING on the AT interface, three times
SABME from TEI 64, answering UA             ATA
SETUP to the modem from 5551000             ALERTING, then CONNECT
```

The log of the firmware itself agrees at each step:

```
LINE_ACTIVE Detected | --SETUP | SETUP with result= | 0000 | END of INTL_TYPE
Just Sent IC SETUP | Prim = N_CONN_IN : | l4_CONNECT : modem primitive
BCH_ENABLED Detected
```

Q.931 gets to Active, the peer binds the media to B1, and the MUX of the Am79C30 is
programmed for it: `MCR1 = 16h`, which is **B1 <-> Bd**, the peripheral port
that the DSP is on.  157,047 frames are routed through that connection.  Each
one of them carries `ff` out of the modem.

## Two things had to be right before the call would happen at all

Each of these cost one run. They are both items of the configuration of the modem, not of the
peer:

* **The called number must be the number of the modem itself.**  The stored directory
  numbers are `7349195` and `7349196`, at `ce0:8e84` and `ce0:8e99`. These are the two
  entries of a block with a `0x82` stride.  A SETUP for any other number is refused at
  `0x5c292`. That code calls the comparison at `0x5bb3e`, gets a negative answer,
  sends RELEASE_COMPLETE with **cause 88, incompatible destination**, and logs
  its own result as `CDN failure`.  That is all of the refusal that
  [imodem-liu-state-field.md](imodem-liu-state-field.md) ended with. It is not
  the bearer capability.
* **The bearer must be one that the modem accepts.**  `--bri-bearer data`, an
  unrestricted 64 kbit/s call, gets `0000` and rings. That is the call that this
  page follows.  Before, `--bri-bearer speech` got `SETUP with result= FFFE`
  and `NO CARRIER`, and we thought here that the bearer class was refused.  That
  was not correct. The cause was **A-law**.  When we offer mu-law, the same modem rings on speech
  and on 3.1 kHz audio, answers as a modem and puts ANSam on the bearer. Refer to
  [imodem-audio-bearer.md](imodem-audio-bearer.md).

The peer now prints the cause that it receives. Thus, it is not necessary to
find either of those again with a disassembler:

```
RELEASE_COMPLETE call reference 1, cause 88 incompatible destination
```

## Where the silence comes from

The cause is not the chip and not the routing.  It is the DSP.

The C5x writes its serial transmit register in each 8 kHz frame (212,601 writes),
and the value is `ffff` each time.  The octet on B1 is the low byte of it.
Thus, the modem transmits the idle codeword for the full call.  The injected
network-to-terminal audio gets to the other side of the same register. The
8,000 octets of `--bri-rx-g711` are delivered, routed and consumed, but
nothing that we can see comes back out.

The cause is one command that is never taken.

[imodem-ceml4.md](imodem-ceml4.md) established that `BCH_ENABLED` ends in
DSP command **`005e`**, with the bearer selector as its argument.  The firmware
does send it. The mailbox shows `5e 0001` posted at the correct time, for
the correct channel.  It is the twentieth command of the run, and **only
nineteen are consumed**.

The DSP stops reading commands one command earlier.  Each command up to and
including `62 0004` is delivered while the resident is at IDLE, and each one is
acknowledged. The dispatcher of the resident polls port `57h` to find them, and it
polls it 239,343 times before that point.  While it operates on `62 0004`, the DSP
leaves IDLE for overlay code at `e8ba..e8de`. From that instruction to the
end of the run (about 26 seconds of call), it reads port `57h` **exactly zero
more times**.  The command byte of the mailbox is still in the latch when
the run ends.

```
0xe8ba  splk  @7d, #0000        the loop the DSP runs instead
0xe8bc  splk  @7e, #0000
0xe8be  call  ....
0xe8c0  xc    2, ntc
0xe8c1  lacl  @79
0xe8c2  sacl  @7f
0xe8c3  bcnd  ...., ntc
0xe8d7  lamm  @0e
0xe8d8  sub   @7c
0xe8d9  bitt  *
0xe8da  xc    2, eq
0xe8dd  lamm  @0e
0xe8de  retd
```

This is a called routine that is entered and returns, again and again, and tests a bit in
data memory.  It is real downloaded overlay code that does real work. But it does
not go back to the dispatcher of the resident.

## What the loop is waiting on

It is an **HDLC flag hunt**. When we read it back, it shows what it waits for and
why it can never get it.  `NativeC5x.program()` reads a downloaded overlay out
of the core (nothing on the host side keeps a second copy). Thus, we can disassemble the code that the
DSP actually runs:

```
e8ac  splk  @7d, #e8b6
e8b1  splk  @7f, #0009      ; nine flags before sync is declared
e8b6  call  e8d7            ; one bit
e8b8  bcnd  e8ac, tc        ; a 1 here is not the leading zero: start over
e8ba  splk  @7d, #e8be
e8bc  splk  @7e, #0006      ; six ones
e8be  call  e8d7
e8c3  bcnd  e8ba, ntc       ; a 0 breaks the run: start over
e8c5  lacc  @7e / sub #01 / bcnd e8be, gt
e8ca  splk  @7d, #e8cc
e8cc  call  e8d7
e8ce  bcnd  e8ac, tc        ; a seventh one is an abort, not a flag
e8d0  lacc  @7f / sub #01 / bcndd e8b6
```

Zero, six ones, zero (`01111110`), nine times.  When `@7d` holds `e8b6`,
`e8be` or `e8cc`, that value is a resume address. Thus, this is a coroutine. It is written to
be entered again one bit at a time and to give control back. It is not written to spin.

The bit source is the helper that it calls:

```
e8d7  lamm  @0e             ; TREG2, the bit pointer
e8d8  sub   @7c             ; @7c = 7
e8d9  bitt  *               ; bit TREG2 of the word at *AR1
e8da  xc    2, eq
e8db  pop / ret             ;   TREG2 == 7: the byte is spent, unwind a level
e8dd  lamm  @0e
e8de  retd / sub #01 / samm @0e   ; otherwise step the bit pointer down
```

`AR1` is `0x0889`, and `@7c` is 7. The pointer must go **from 15 down to
8**, the top half of a sixteen-bit word. When it gets to the end, it unwinds, so that
the level above can fetch the next word.

## And why it never gets it

The resident fills `0x0889` at the splitter that divides one received
serial word:

```
80d9  lacl  *, ar1          ; the received word
80da  sacl  @0b             ; 0x088b
80db  apl   @0b, #00ff      ;   low octet
80dd  bsar  8
80de  sacl  @09             ; 0x0889 - high octet
```

That splitter is in the resident, on the same background path as the mailbox
dispatcher that polls port `57h`.  **It stops when the overlay loop starts**,
and the counters show this exactly. `0x0889` gets 57,187 writes, and the last of them
comes from the overlay at `eb3f`. Across the full 26-second call after the `5e`
command, it gets **none**.  The cell that the flag hunt reads stays at the value
that was in it when the background loop stopped.

The receive path itself is correct, and this makes the diagnosis precise.
Octets continue to arrive during the loop. The interrupt side fills a
ring at `0x0bd0..0x0bde`, with 4,491 writes to each of its eight words, with the
pointers at `0x0390`/`0x0391`. When we feed `7e` to the peer and not a sine
wave, each word of that ring becomes `007e`.  The bytes are there.  Nothing
carries one to `0x0889`, because the code that would do it is the caller of the loop itself.

Thus, the deadlock is complete and symmetrical. The flag hunt waits for a byte that the
background loop supplies. The background loop cannot run until the flag hunt
returns. The `5e` command waits behind the two.  `TREG2` shows it directly:
3,186,292 writes during the loop. It decrements freely through all sixteen bit
positions. It is not loaded again to 15 for each byte, because the per-byte level
that would load it is never reached.

The `ff` on the wire is intentional.  The overlay selects its own idle
codeword at `e8e9` and `e909` (`splk @21, #00ff`, DXR). It selects between `ff`
and `7f` on a flag bit.  A modem with an HDLC receiver that is not synchronized
transmits mark idle. That is exactly what the capture contains.

## Two time slots per frame, which the model now clocks

The firmware programs the serial port with **`SPC = 40c8`**. `FO` (bit 2,
as table 9-13 of the C5x user's guide gives) is **0**: sixteen-bit word format.  That
is not a new interpretation.  [quad-dsp-pcm-path.md](quad-dsp-pcm-path.md) already
separates the two products on exactly that bit (`40cc` of the Quad against
`40c8` of the 302), and says clearly that the 302 moves sixteen-bit words.
The core had the opposite. A comment claimed byte format, and the core put one
octet in each frame in the low byte, with the high byte at zero.

The firmware shows the same fact two more times.  Its splitter at `80db..80de`
takes *two* octets out of one received word. The `@7c = 7`
terminator of the flag hunt is the bit index where the top half of a sixteen-bit word ends.
Sixteen bits each 125 us is 128 kbit/s: **two eight-bit time slots of the peripheral port**.
One B channel is 64 kbit/s.

Thus, the model now operates the boundary as the part does:

* `native/c5x_core.cpp` reads `FO` from `SPC`, and does not assume it.  `FO=1`
  keeps one octet for each frame. That is the path of the Quad, and it did not change.  `FO=0`
  exchanges a full sixteen-bit word, **MSB first. Thus, the first time
  slot of the frame is the high byte at the two ends**. This fact sets the mapping. It is not
  a preference.
* `Am79C30.peripheral_slots()` tells which logical channel each slot carries.
  It takes them in the sequence in which the MCRs list their connections, MCR1 first.
  `PPCR1` (`07` here) and `PPCR2` are recorded but *not* decoded. Nothing in
  the image has shown what their fields mean. A slot map invented from
  them would be a guess that looks like a datasheet fact.
* `ImodemDsp._sync_pcm` exchanges one MUX frame for each pair of octets. Thus, B1 still
  carries one octet each 125 us and stays at 64 kbit/s.  An odd octet at the end of
  a scheduler slice is half a frame, and it waits for its other half.

A modem call programs `MCR1 = 16h` and nothing else. Thus, B1 takes the first slot,
and the second slot is not connected.  The run now shows `DRR = 7eff`: the flag octet of the far end
in the high half, from `Bd`, and the idle codeword in the low half,
from a slot that has nothing on the MUX.  `0x0889`, the cell that the flag hunt reads,
holds `007e` where before it held zero. The report names the slots:

```
pcm   slots ['Bd', None]   frames 144798   octets 289596
dsc   peripheral_slots [6, None]   routes [[1, 6]]
```

There is one `DRR` read and one `DXR` write for each frame. That is what a sixteen-bit port
must do.

This does not move the deadlock, and we did not expect it to. The flag hunt still
cannot get a second byte, because the background loop that it blocks
fills the cell again. But it removes the doubt about *which* byte. Thus, the
question above it is the only one left.

## Why the byte-ready test never fired: TREG2 was not a register

The flag hunt is a coroutine, and it has a driver at `e63a`. The driver does exactly
what a coroutine driver must do:

```
e63a  lacc  #000f
e63c  samm  @0e        ; TREG2 = 15 - start at the top bit
e63d  lacc  #0007
e63f  sacl  @7c        ; stop after bit 8: the high byte, eight bits
e640  lacl  @67 / sacl @7e     ; restore the hunt's saved counters
e642  lacl  @69 / sacl @7f
e644  lacl  @65 / sacl @7d     ; @65 is where it got to last time
e646  cala                     ; run it
e647  lacl  @7d / sacl @65     ; and save where it got to this time
```

The second stream comes immediately after it, at `e64f`, with `@7c = 8`: seven bits
and not eight. This is the same 7/8 choice that the initializer at `e8ec` makes.

Thus, the byte-ready test is not a gate that operated early.  It is `TREG2`, which counts
down from 15 to `@7c` while the hunt consumes the byte. The `pop; ret` that operates
on it is how the hunt gets back to its driver. The helper was called with `call`. Thus,
when the code discards its return address and returns, it goes to the return address of the driver.
The full cycle for each frame is this:

1. The resident divides a word.
2. It calls the handler that the overlay installed at `0x088c`/`0x088d`.
3. That handler at `eb39` bit-reverses the octet and continues the chain.
4. The hunt consumes eight bits.
5. `pop; ret` brings control back.

Control never came back, because **in this core, `TREG2` was only half a register**.
The write side of `cpuregs_w` bound TREG1, TREG2 and DBMR. The read side of
`cpuregs_r` bound TREG0 and stopped.  Thus, `lamm @0e` read an unused data
cell, and not the register that `samm @0e` had just written. That is the exact division that the
comment above `case 0x0c` warns about, applied only half.

The results agree with each symptom on this page.  `lamm @0e` returns
0, `sub @7c` is -7 and is never equal, the `pop; ret` never executes, and
`samm @0e` writes `0 - 1 = ffff` back each time. Thus, `bitt` tested bit
15 of the byte again and again, for 3,186,292 iterations, while the counter that it
waited for never moved.  The binding of the read side is four lines.

## What it does when the register is whole

All the items after it become unblocked at the same time:

```
bri.media   tx_non_ff 6937 of 46608      the B channel stops being silent
mailbox     23 / 23 consumed             the 5e command is taken
```

The octets are not noise. They are **`7e`, HDLC flags**, 6,937 of them in
a continuous run after the receiver synchronizes.  The modem answers, synchronizes on
the flags of the far end, and idles the link with its own flags. That is what a V.120
terminal does after CONNECT.

With more time, the call also finishes correctly.  The far end here only replays
flags (the peer does not yet send any protocol above HDLC on the B channel). Thus,
the modem waits, stops, and clears the call in its own words:

```
BCH_ENABLED Detected | l4_DISCONN : modem primitive | Prim = N_DISC_CF :
```

The DTE shows `NO CARRIER`, the call is cleared, the mailbox drained 39 of 39, and
the DSP is back at IDLE.  This is a full call, from SETUP to hangup, with the bearer
in operation under it.

## What that makes the frontier

The chain from an incoming call to a routed B channel is now complete, and we can
see it at each joint: line, TEI, data link, called-number match, bearer,
RING, `ATA`, CONNECT, `BCH_ENABLED`, MCR, and a bearer command that is built and
posted.  The single missing joint is the last one:

**what the DSP waits for in that loop, and what would return it to the
dispatcher at `85c6` so that the `5e` command is taken.**

The section above answers that. The answer was in the core of this repository and not
in the firmware: a memory-mapped register that was bound for writing but not for
reading.  The modem never waited for the board.  It waited for a
counter that could not count.

The open question is now at a higher level.  The bearer carries HDLC and the modem
frames it. But the peer at the other end of the B channel replays the
file that it received. Thus, nothing above the framing is answered, and the call
clears on a timeout.  `courier_emu/v120.py` is now that far end: HDLC, the
logical link identifier, and the procedures of Q.921 on the bearer.
[imodem-v120.md](imodem-v120.md) records how far it gets. The frames go out
with correct framing, and the modem does not answer them. Thus, the remaining
question is a protocol question and not a hardware question.

If we invented a wake-up, the result would be a modem that seems to communicate.  The
counters show the difference, and they are easy to read:
`tx_non_ff` of `bri.media`, `consumed` against `committed` of the mailbox, the read count of port
`57h` before and after the command, and the write count on
`0x0889`.
