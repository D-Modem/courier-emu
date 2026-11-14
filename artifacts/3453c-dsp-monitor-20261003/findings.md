# 3453C DSP monitor feasibility, 2.3.33 / DSP 2.1.41

Static analysis and isolated DSP execution, 2026-10-03. We did not open a
serial device, flash firmware, or make a flashable image. To reproduce, use
this command:

```
.venv/bin/python artifacts/3453c-dsp-monitor-20261003/analyze.py
```

## Recovered receive path

The resident is XMF file `002F0..0CEAF`, loaded at DSP program words
`1000..75DF`. The low program module (overlay index 7) is file
`12B20..14B1B`, linked at `0000..0FFD`. The isolated replay loads it
explicitly. Do not assume that this module is the internal mask ROM of the
DSP, or that it is present at reset.

The DSP receive routine is program `12B1`:

- `IN @7d,8057`, then test bit 0 for a pending host request.
- `IN @7d,805e` reads its tag. `IN @7a,805f` reads its data.
- Write 1 to `8057` to acknowledge the host request.
- Load the tag and subtract `87`. Return for signed-positive results. Then add
  `1394`, read the handler address from the table, and BACC to it.
- The actual table base is `130D` (`1394 - 87`), 136 words for tags `00..87`.
  Its XMF file base is `0090A`. `commands.json` records each entry and its
  source offset.

The dispatcher uses I/O space. This is different from the newer
memory-mapped ff5e pattern. Full-word/high-bit tags are not a safe extension
mechanism, because the existing bound is a signed comparison. A monitor
prefilter must agree with exact tags and keep the stock behavior for all other
inputs.

## Stock tag 80 is implemented

Table slot `138D` -> `1292`. It indexes a second table at `129D` with
`(data[012F] >> 8) & 7`:

| State | Handler | Behavior |
|---|---|---|
| 0 | 1137 | Return without a reply |
| 1 | 12A3 | Queue tag 7B, then derived identity data; clear 012F |
| 2 | 0064 | Queue tag 7C, then derived value; clear 012F |
| 3 | 0074 | Queue tag 7D, then low byte of 012F; clear 012F |
| 4 | 0078 | Queue tag 7E, then low byte of 012F; clear 012F |
| 5 | 1137 | Return without a reply |
| 6 | 1137 | Return without a reply (static table) |
| 7 | 1137 | Return without a reply (static table) |

Tag 84 -> `126D`: bit 13 of the request selects `0055`. This sets
`data[012F]=0400` and enters the line-side request path at `1175`. Writes go
to `112B`. This shows that tag 80 polls a pending result. It does not always
start a read of the ring register. This gives a possible reason for old ATGSI
output, but it does not show the live state on the board.

`replay.json` records eight isolated cases that pass: states 0..5 for tag 80,
the no-op tag 6C, and the unsupported tag 88. State 4 with fixture 012F=0403
returns 7E:0003. The tests run actual firmware instructions with fixture RAM
and an ASIC acknowledgement adapter in the C51 core of the repository. We do
not claim C52 boot/timing or hardware equivalence.

## Reusable reply path

`12C8` makes sure that the ring has space for a multiword reply (six spare ring
words). `12D3` puts one word in the queue. Data[78] is the producer and
data[79] is the consumer. The ring is `7FC0..7FCF`, and the wrap checks use
`AR0=7FD0`. A tag word with bit 15 set means that a full data word follows.
`12E4` sends replies:

- examine status 8057 bit 1;
- send the tag without bit 15 to 805E;
- send the next word to 805F when the flag is set;
- write 2 to 8057 to notify/acknowledge the outbound transaction.

A monitor must use the existing space check. It must not put two words in the
queue blindly: if the ring is full, a tag must not stay without its data word.

## Concrete patch design

First milestone: identity echo and one-word program/data reads, on hook.
The proposed request tags 0088 (identify), 0089 (data read) and 008A (program
read) are outside the stock table. These are design placeholders. They are
not working stock commands. Stock ATG already sends full tag/data pairs. Thus,
after you install a monitor, you can enter requests as ATG00890000, for
example.

1. Replace the two-word instruction pair at program `12C0..12C1`
   (`LACL @7d; SUB #87`) with a two-word branch to a verified monitor
   trampoline. For a request that does not agree, execute those instructions
   again and branch back to `12C2`. Keep the DP, the ARP/register
   expectations and the stack behavior of the stock path.
2. Find exact matches of the proposed tags. Use request data[7A] as the 16-bit
   address. Read program space with TBLR and data space with an indirect load.
   Keep those operations separate. Limit the first data reads to verified RAM.
   Arbitrary reads of data space can touch peripheral registers.
3. Use a dedicated reply tag below 80 (provisionally 7F), and the full value
   word, through the existing ring. The supervisor discards tags >=80.
4. Patch the 80186 receive path at physical `67700` to intercept the dedicated
   reply before the stock dispatch through [02DA]. Add a bounded serial query
   that reports a value or a timeout and connects the replies to the requested
   operation. If you only read the holding ports, other DSP replies can
   overwrite them.
5. Add writes only after echo and reads work, with an explicit address/value
   transaction and acknowledgement. One stock tag/data request cannot carry a
   16-bit address and a 16-bit write value together. Thus writes must have a
   defined staged protocol or a longer serial command.

## What prevents a flashable patch today

- We have not yet shown that a code cave is safe in each related DSP
  overlay/state. Blank bytes are not sufficient proof. We found the first hook,
  but we must allocate its destination. To do this, trace the program
  references and the loader bounds.
- Before we export a patched image, we must decode the XMF/loader acceptance
  checks and the firmware checksum handling, and test them against the
  unchanged image.
- The full 3453C boot fails in the current emulator, because its mask-ROM
  loader for the first download is different from the recovered 302/403
  loader. Isolated function tests bypass that boot. They cannot validate an
  upgrade or a reset.
- The repo has a captured boot block and the stock XMF. But before the first
  flash, a tested recovery transfer for this exact board is necessary.

A stock-only step before the patch could send a defined raw Si register read
and then ATGSI. But this analysis did not send commands to hardware. The next
practical engineering work is safe code allocation and a reproducible builder
of patched images with checksum verification. After that, make a monitor
prototype in the emulator.

## ATXMODEM option 1 confirmed in the 2.3.33 application

The user identified this readback route. Static verification confirms that
the X handler at physical `82D22` explicitly compares with the suffix `MODEM`
followed by NUL, and calls `777C:1EBE` (`7967E`). The menu text includes
`(1) Read firmware` and `(2) Write firmware`. The option parser at `79978`
compares AL with ASCII 1 and branches to `79994`. That path initializes the
source segment cell `[2710]` to `4000` and prints
`Start Xmodem-1K receive now.` before it calls the sender setup at `7A18C`.
Option 2 uses a separate path at `799C5`.

Thus ATXMODEM is a real application command on this image. The warning for
the older family in courier_firmware_analysis.md, which said that ATXMODEM was
only shorthand, does not apply to 3453C 2.3.33. Option 1 can supply the
application-flash capture of the board for a byte comparison against the local
XMF. Its exact end bounds and transfer framing must still be verified. Do not
assume that it captures the parameter sectors, the boot block or the internal
DSP mask ROM. This analysis did not start a hardware transfer.

### Option-1 bounds recovered

The sender routine `7A32B` compares the paragraph count [271A] with B800 before
EOT. The source starts at segment 4000. Thus option 1 covers exactly physical
40000..F7FFF (B8000 bytes). It does not include the parameter sectors and the
boot block. The live menu prompts `Start Xmodem-1K receiver`. This is not the
earlier wording that we recorded from an adjacent inline string. The read
capture is in `artifacts/3453c-firmware-read-20261003/`.

### Hardware readback result

ATXMODEM option 1 captured B8000 bytes in 736 CRC-valid 1K blocks, with zero
retries. The capture agrees byte for byte with the local 2_3_33.XMF, SHA256
c8d44a1c984a203f6e9a91b14c77382706ea05fc2b860081f986c47b6fa7c41e.
We validated the raw frames again, independently and offline. ESC exits this
application menu with a reset of the modem. After the reset, AT OK was
confirmed. Thus the firmware identity and the patch baseline now have
byte-level verification on hardware.
