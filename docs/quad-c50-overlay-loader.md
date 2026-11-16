# How the Quad loads C50 code

## Source offset correction verified on 4 October 2026

A new run on the stock controller confirms the overlay source offsets in the
flattened QF image. They are two bytes after the earlier extrapolated offsets.
The resident source stays at `449b0`, length `f450`, origin `8000`.
All the full overlay byte ranges agree with all four modem RAM copies. The
loader does not discard a word. To get the same result again, use
`tools/verify_quad_pcm_placement.py`. The detailed fingerprints are in
`artifacts/x2-mapper-negotiation-20261004/placement-verification.json`.

| Source paragraph | Flat byte offset | Bytes | DSP origin |
| --- | --- | --- | --- |
| 2f45 | 53e02 | 42e0 | a180 |
| 3373 | 580e2 | 252c | b400 |
| 35c6 | 5a612 | 0f18 | d900 |
| 36b8 | 5b532 | 0cb6 | c300 |
| 3784 | 5c1f2 | 15d6 | c300 |
| 38e2 | 5d7d2 | 08f2 | c800 |
| 3972 | 5e0d2 | 1808 | 9440 |

All values are hexadecimal. This correction applies to the flat source
extraction. The source paragraphs, copy lengths and DSP destinations do not
change. The corrected PCM entries include C7AD, C994, C9A5, C9B6 and C9BF. The
reproduction tools share the source placement. The sections that follow
describe the original transport and the overlay selection mechanism.

[`docs/x2/README.md`](x2/README.md) recorded three facts about each Quad image.
It has exactly one call to its 80186-to-C50 downloader. It has no Courier-style
x86 overlay table. It has no source-segment reference to the tail of the DSP
payload. Thus the overlay selection mechanism was "not yet decoded". This
document decodes it. The addresses are for `QF060003`. `QR060103` has the same
shape at shifted offsets.

## The supervisor loads the resident, and nothing else

The download transport is two pairs of 80186 I/O ports:

| Ports | Role |
| --- | --- |
| `0xc0` / `0xc2` | download data, one 16-bit word split low byte then high byte |
| `0x98` / `0x9a` | handshake — write `1`, poll bit 0; write `2`, poll bit 1 |

`0x93864` sets a destination word address. It sends `AX` out to
`0xc0`/`0xc2`, then sets a `0xff56` PCB bit and does a `0x98` sequence.
`0x93904` is the downloader itself. It takes a source offset in `AX` and a byte
length in `CX`. It sends eight words at a time and polls with
`in al, 0x98` / `test al, 1` between the chunks.

There is **exactly one** call to the downloader in the image, at `0x93810`:

```
93804  mov ax, 0x8000     ; destination program address
93807  call 0x93864
9380a  mov ax, 0           ; source offset
9380d  mov cx, 0xf450      ; byte length -- the resident, and only the resident
93810  call 0x93904
```

Before it, at `0x9382a`, a preamble sends eight words of `0x0083` to
destination `0xfff8`. Thus the supervisor pushes the resident bank to program
`0x8000` at boot and never pushes other data. The supervisor does not send the
overlay store at `0xd3e00..0xdf910` in this way.

## The resident plants its own fetch stub

At cold boot, sixteen words into its entry path, the resident builds three
words of code in low program memory:

```
8067  lacc  #23f0
8069  samm  @1f          ; BMAR = 0x23f0   (BMAR is MMR 0x1f, spru056d)
806a  lar   ar1, #82d6   ; source
806c  rpt   #02
806d  bldp  *+           ; program[BMAR++] = data[ar1++], three times
```

`BLDP` is "block move from data to program memory with destination address in
BMAR" (spru056d). The external RAM of the board answers in both program space
and data space at `0x8000..0xfeff`. `courier_emu/dsp.py` already models this
window. Thus the source at data `0x82d6` is the image of the resident itself.
The three words are:

```
23f0  1080  lacc  *
23f1  0880  lamm  *
23f2  ef00  ret
```

This is the host-word fetch. It explains the `calld 23f0` that the main loop
makes to an address below the `0x8000` load origin. No code is missing. The
resident writes that code itself before it uses it.

## The host link is the DSP I/O window, not data memory

The caller sets `ar1` in the delay slot before it calls the stub. The value is
`0xff57` in the idle path and `0xff58` in the transfer loop. `lamm *` addresses
a memory-mapped register by the low seven bits of the auxiliary register. Thus
these are **MMR `0x57` and `0x58`**. They are in the `0x50..0x5f` I/O window
that `native/c5x_core.cpp` already maps to board I/O.

This **corrects** a claim in [quad-dsp-pcm-path.md](quad-dsp-pcm-path.md). The
CPU-to-DSP link of the Quad is not global data memory. It is the same DSP I/O
window that the ASIC mailbox of the analog Courier uses. On the analog Courier
the ports are `0x5e`/`0x5f` ([dsp-cpu-interconnect.md](dsp-cpu-interconnect.md)).
On the Quad they are `0x57`/`0x58`. This is also why a poke to data address
`0xff57` had no effect: the value never came from data memory.

## The loader

After the resident plants the stub, the overlay load at `0x82fc` is simple:

```
82fc  ldp   #1fe
82fd  lacl  @63          ; 0xff63 -- destination program address
82fe  samm  @1f          ; BMAR = it
82ff  lar   ar1, #ff58   ; the word-fetch port
8303  ldp   #000
8304  rptb  #8310
8306  calld 23f0, *      ; fetch one word from I/O 0x58
830b  sacl  @7d
830c  bldp  @7d          ; program[BMAR] = it
830d  lamm  @1f
830e  add   #01
830f  samm  @1f          ; BMAR += 1
```

Thus the host supplies the destination for each transfer, and the loader pulls
the words one at a time through an I/O port. Neither side has a static overlay
table. This is why the search for one failed.

The resident has 19 anchored `samm @1f` sites and six anchored `bldp` sites.
Thus this is a general facility for several loads, not one special case.

## Confirmed by execution

We ran the resident under `courier_emu.dsp.NativeC5x` and put seed values in
DSP I/O:

| Seed | final `pc` | `SPC` writes |
| --- | --- | --- |
| none | `0x83aa` | 72 |
| `0x57 = 0x0200` | `0x83aa` | 72 |
| `0x57 = 0xffff` | `0x83aa` | 72 |
| `0x57 = 0x0200`, `0x58 = 0x0000` | `0x83aa` | 72 |
| `0x57 = 0x0200`, `0x58 = 0xef00` | **`0x0485`** | **8** |

When port `0x58` supplies `0xef00` (`ret`), the run changes. Execution gets to
`0x0485`, in the low program memory that the loader writes. The port
initialisation becomes stable after 8 writes, not 72. The resident puts the
words from I/O `0x58` into program memory and executes them. The mechanism
operates correctly.

This is a demonstration, not a real overlay. A constant `ret` is not the code
of the firmware. But it shows that the transport operates from one end to the
other.

## The supervisor's load table

The table has eight rows at `0x93ba2..0x93be1` in `QF060003`. Each row has
four words:

```
source paragraph (32-bit, low word then 0x0000) | length in bytes | destination program address
```

You can identify the table because one row holds the arguments of the
downloader call: length `0xf450` and destination `0x8000`. These are the
`mov cx, 0xf450` / `mov ax, 0x8000` at `0x93804`. That row is the resident.

In flash order:

| Source para | Byte | Length | Words | Destination | Flat address |
| --- | --- | --- | ---: | --- | --- |
| `0x2000` | `0x20000` | `0xf450` | 31,272 | `0x8000` (resident) | `0xc49b0` |
| `0x2f45` | `0x2f450` | `0x42e0` | 8,560 | `0xa180` | `0xd3e00` |
| `0x3373` | `0x33730` | `0x252c` | 4,758 | `0xb400` | `0xd80e0` |
| `0x35c6` | `0x35c60` | `0x0f18` | 1,932 | `0xd900` | `0xda610` |
| `0x36b8` | `0x36b80` | `0x0cb6` | 1,627 | `0xc300` | `0xdb530` |
| `0x3784` | `0x37840` | `0x15d6` | 2,795 | `0xc300` | `0xdc1f0` |
| `0x38e2` | `0x38e20` | `0x08f2` | 1,145 | `0xc800` | `0xdd7d0` |
| `0x3972` | `0x39720` | `0x1808` | 3,076 | `0x9440` | `0xde0d0` |

**The chain closes exactly.** For each row, the source paragraph multiplied by
16, plus the length, rounds up to the source paragraph of the next row. There
are no gaps: `0x20000 + 0xf450 = 0x2f450`, `0x2f450 + 0x42e0 = 0x33730`, and
the chain continues to `0x3af28`. The eight images are contiguous in flash.
Paragraph `0x2000` maps to flat `0xc49b0`, the start of the DSP payload.
Paragraph `0x2f45` maps exactly to `0xd3e00`, the start of the overlay store.

The lengths total `0x1aefa` (110,330 bytes). The DSP payload is `0x1af60`
(110,432). The chain ends at flat `0xdf8d8`. The NAC paints a 48-byte span
separately at `0xdf8e0..0xdf910`, and this span is the remainder. Immediately
after the table are the `6.0.3` version string and the `09/22/98` date string.
The table ends there.

Each overlay destination is **inside** the span of the resident,
`0x8000..0xfa28`. Thus these are overlays in the strict sense: they replace
regions of the resident that is already loaded. Two rows share `0xc300`, thus
those two are alternatives for one slot.

This answers the original question. On the supervisor side, the selection is a
table of (source, length, destination) rows. The delivery is the DSP-side
`BLDP` pull that this document describes above. The search for a Courier-style
table from a second downloader call found nothing, because there is no second
call. Also, this table is not adjacent to the call that exists.

## Matching the Quad's images against the documented 302 overlays

[dsp-overlays.md](dsp-overlays.md) maps the four C5x images of the analog
Courier. `CourierRom.dsp_overlays` reads them from `IDSDL302.ROM`: id 5
resident at `0x8000` (55,420 B), id 6 at `0x9d00` (23,020 B), id 7 at `0xb000`
(14,998 B), id 8 at `0xdc00` (14,700 B). That document identifies **id 8 as
the V.90 layer and id 6 as the PCM core that operates with it** (it refers to
[codec-sample-rates.md](codec-sample-rates.md)).

Because the sources of the Quad are known, we compared each of its eight images
separately, with 32-byte block hashes. Each figure is the percentage of the
blocks of the *Quad* image that are also in that 302 image:

| Quad dest | Words | 302 id5 | 302 id6 | 302 id7 | 302 id8 |
| --- | ---: | ---: | ---: | ---: | ---: |
| `0x8000` resident | 31,272 | **18.7%** | 0.1% | 0.1% | 0.0% |
| `0xa180` | 8,560 | 0.2% | **50.8%** | 4.5% | 0.2% |
| `0xb400` | 4,758 | 7.1% | 4.1% | **35.2%** | 0.0% |
| `0x9440` | 3,076 | 0.7% | 11.2% | **41.9%** | 0.0% |
| `0xc300` | 2,795 | 0.1% | **36.4%** | 0.1% | 0.0% |
| `0xd900` | 1,932 | **26.9%** | 0.2% | 0.2% | 0.0% |
| `0xc300` | 1,627 | 0.0% | **17.2%** | 9.3% | 0.0% |
| `0xc800` | 1,145 | 0.0% | 0.0% | 0.0% | 0.0% |

**The resident agrees with the resident.** The `0x8000` image of the Quad
agrees only with the 302 resident. The only other strong match to that resident
is the `0xd900` overlay of the Quad. Thus some code that is resident on the
analog Courier is an overlay on the Quad. This is reasonable, because the
resident of the Quad already has four channels to hold.

**The PCM core carries over.** The largest overlay of the Quad, `0xa180`, has a
50.8% match to 302 id 6, the PCM core. The `0xc300` pair also matches id 6.

**302 id 7 is split in two.** The Quad images `0xb400` and `0x9440` match id 7
at 35.2% and 41.9%, and match almost nothing else. Thus one 302 overlay
corresponds to two Quad overlays.

**No image matches 302 id 8, the V.90 layer.** That column is 0.0-0.2% for all
eight Quad images. The Quad does V.90 (its supervisor string tables have many
entries such as `48000/ARQ/V90`), but it does not use this DSP code for it.
The `0xc800` image of the Quad (1,145 words) matches *nothing* in the 302.
Thus it is the first candidate for the location of the V.90 or DS0-side work of
the Quad.

### Limits

These are 32-byte block-hash overlaps. At 35-51%, the images are revisions of
common sources, not identical images. The percentages are of the Quad side.
Thus a low figure against a much larger 302 image is not, by itself, evidence
of absence. But the id 8 column is 0.0% for all eight Quad images, and that is
evidence of absence.

### Corrections

An earlier version of this document read the rows as
`(length, destination, third, 0x0000)`, with an unidentified third field. It
found only five rows. The row boundary was two words incorrect. The third field
is the source paragraph address, and the table has eight rows. The earlier note
said that the lengths covered only a third of the overlay store. The same
misalignment caused that error: the lengths cover all of the store. The earlier
version also noted an equal size between 302 id 7 and those five rows (both
14,998 bytes). This was also an artifact of the error, and we withdraw it.

## What remains

- ~~The request and acknowledge protocol on ports `0x57`/`0x58`~~ — **recovered
  2026-09-10 when we ran the resident**. Refer to "The host link is a five-word
  window" below.
- ~~The supervisor code that walks this table and streams a row on request.~~
  Recovered at physical `0xcee5f`. It indexes the table at `0xcefa8` and writes
  4 to CPU port `0x9e`. Then it streams four words through lanes
  `0xc0/c4/c8/cc` and strobes `0x9e` with 2 after each burst.
- Which overlay the modem selects at which time. The table gives the eight
  images and their destinations. It does not give the image that a given call
  needs.
- `QR060103` has the same downloader shape. Its table is not found yet.

## The host link is a five-word window

We ran the captured resident on `NativeC5x` with no CPU attached, and this run
shows the handshake. In 200,000 steps it makes 10,637 I/O events. The steady
state is one cycle that occurs 1,768 times:

```
WRITE 0x57 = 0x0300    pc 0x8313
read  0x57             pc 0x23f1
read  0x58             pc 0x23f1
read  0x59             pc 0x23f1
read  0x5a             pc 0x23f1
read  0x5b             pc 0x23f1
```

**All reads are at the same address.** `0x23f1` is the `lamm *` of the fetch
stub, and `ar1` increments automatically. Thus these are not five instructions
that poll five registers - this is one instruction that reads a **five-word
window from `0x57`**. The window is a status word followed by **four** data
words at `0x58`..`0x5b`. The stub always reads all five. This is why a seed in
`0x57` alone never moved the loop forward. The handshake does not have more
bits than one. The *window* has more ports than one.

Four data words for each request is exactly the burst size of the CPU. The
supervisor writes four words into lanes `0xc0`, `0xc4`, `0xc8`, `0xcc` (or the
`0xd0` group), strobes `0x98` and waits. The DSP takes four words from
`0x58`..`0x5b` and writes `0x0300` back to `0x57`. Thus each lane corresponds
to one MMR:

| CPU lane | DSP MMR |
|---|---|
| `0xc0`/`0xc2` | `0x58` |
| `0xc4`/`0xc6` | `0x59` |
| `0xc8`/`0xca` | `0x5a` |
| `0xcc`/`0xce` | `0x5b` |

Only one window occurs, at `0x58`..`0x5b`. The resident never touches
`0x5c`..`0x5f`. Thus the second lane group of the CPU, at `0xd0`, addresses a
second device with its own I/O space, not a second window in this one.

Before the cycle starts, start-up does these writes: `0x57 = 0xffff` at
`0x8002`, then `0x56 = 0xffff` and `0x57 = 0xfffc` at `0x8031`/`0x8033`, then
five peripheral writes at `0x8058`..`0x8066`: `0x68 = 0x000f`,
`0x69 = 0x0002`, `0x6a = 0x0000`, `0x6b = 0x0078`, `0x6c = 0x0901`. Six reads
of `0x55` occur at `0xbc0`/`0xbf4`.

To get the same result again, use
`PYTHONPATH=. .venv/bin/python tools/probe_quad_c50_resident.py`. The results
are in `artifacts/quad-c50-resident-20260910/results.json`.

The CPU-side routine also shows the status bits. After it writes 4 to `0x9e`,
it waits for bit 2 (`0x04`). After each four-word strobe, it waits for bit 1
(`0x02`). `QuadC50Endpoint` models these as two separate states: link-ready and
burst-acknowledge. A focused test runs the captured resident and holds bit 1
low while a burst is pending. The test sees that the resident reads all four
words and writes `0x0300` to `0x57` before bit 1 goes high.

## Why 302 id 8 has no counterpart: V90A against V90D

V.90 is asymmetric, and the two ends run different code. The analog client
(V90A) **receives** PCM codewords and **transmits** V.34. The digital server
(V90D) **transmits** codewords directly onto its timeslot and **receives**
V.34. Thus the analog Courier and a chassis modem NAC do not share a V.90 layer
at all, although they share much other code.

The configuration of the Quad tells which end it is. Its `S81` help block
reads:

```
S81  V.90 Configuration
  1   TX power level applied before digital pads
  2   (reserved)
  32  V.90 server mode
S82  V.90 Transmit Power Level (-dBm)
```

There is **no client-mode bit**, and both V.90 settings are transmit levels.
"Before digital pads" is a digital-network item: the server compensates in
advance for pads downstream. The Quad is V90D only. (Its `S76` x2 block does
have client, server and symmetric modes. Thus the absence on the V.90 side is
a real difference, not a missing string.)

This explains the full match pattern:

| | needs it | Quad has it |
| --- | --- | --- |
| V.34 datapump and PCM core (302 id 6, id 7) | both ends | yes — 35-51% across four images |
| V90A receive layer (302 id 8) | client only | **no** — 0.0% across all eight |
| V90D transmit mapping | server only | no 302 counterpart exists to match |

It also connects to the serial-port finding in
[quad-dsp-pcm-path.md](quad-dsp-pcm-path.md). The Quad runs `SPC` with
`FO = 1`, 8-bit bytes MSB first. The 302 runs `FO = 0`, 16-bit words. For a
V90D transmitter, this *is* the transmit path. It does not synthesise a
waveform. It writes codewords to a byte-formatted timeslot. The analog client
needs 16-bit linear samples for its codec, because it must recover codewords
from an audio waveform.

### The `0xc800` image: a mode slot, contents unidentified

`0xc800` is the only Quad image with no 302 ancestry. But this does **not**
make it the V90D layer. That conclusion was too fast. The structure shows only
that it is one of three alternatives for a single slot.

Program spans, from destination and length:

| Destination | Words | Span | Matches |
| --- | ---: | --- | --- |
| `0x9440` | 3,076 | `0x9440..0xa044` | 302 id 7, 41.9% |
| `0xa180` | 8,560 | `0xa180..0xc2f0` | 302 id 6, 50.8% |
| `0xb400` | 4,758 | `0xb400..0xc696` | 302 id 7, 35.2% |
| `0xc300` | 1,627 | `0xc300..0xc95b` | 302 id 6, 17.2% |
| `0xc300` | 2,795 | `0xc300..0xcdeb` | 302 id 6, 36.4% |
| `0xc800` | 1,145 | `0xc800..0xcc79` | **nothing** |
| `0xd900` | 1,932 | `0xd900..0xe08c` | 302 resident, 26.9% |

The last three overlap, thus `0xc300`/1,627, `0xc300`/2,795 and
`0xc800`/1,145 are mutually exclusive: one slot with three alternatives. This
is a **mode slot**, and `0xc800` is the mode that has no counterpart in the
analog Courier.

We also compared the images of the Quad with each other. `0xc800` shares
**0.0%** with each of them, thus it is also not a variant of a sibling. (The
1,627-word `0xc300` image shares 16.7% with `0x9440`, thus those two are
related.)

The head of the image branches to `0xa98d`, inside the span of the `0xa180`
PCM core. It also calls `0xc85b` inside its own span. Thus it is a mode layer
on top of the shared core. All three alternatives must have this shape.

### What it might be

Candidates, none of them settled:

- **V90D downstream mapping.** The card is V90D-only, as `S81` above shows.
  Server-side codeword transmission has no counterpart in the analog Courier.
  This agrees with "matches nothing".
- **x2 server downstream mapping.** These are `x2` NACs. x2 is older than V.90
  and is a scheme of the same shape. Server-side x2 and V.90 mapping can
  possibly share one image. That would explain why only *one* image does not
  match, not two.
- **Another G.711 or PCM mode** for the DS0 side.

Against **clear channel / unrestricted 64k**: this mode needs almost no DSP
code. This image branches into the PCM core and does real arithmetic. Thus a
direct passthrough does not agree with it.

Against **V.91**: we tested this directly, and it is absent. Table 5/V.91 gives
the default DIL parameters: `N = 125`, `L_SP = L_TP = 12`, `SP = 0x0FC0`,
`TP = 0x0FFF`, and a 125-symbol training sequence. That sequence interleaves
counts that go down with counts that go up
(`124, 0, 123, 1, 122, 2, ... 63, 61, 62`).

We searched `QF060003`, `QR060103`, `IDSDL302.ROM` and `Ie030002` for that
training sequence. We searched for it as bytes, as reversed pairs, and as
16-bit words in both endiannesses. There is **no match in any image**, not even
for the first sixteen entries. The `SP`/`TP` pair is never adjacent in any of
them. `QF060003` has exactly one `0x0FC0`, at flat `0xc78dc`. It is inside the
*resident*, not the `0xc800` image. It is the immediate of an `add`
(`ldp #006; lacl @2b; add #0fc0; sacl @1a`), not a stored parameter.

There are two cautions. First, code can easily generate the training sequence,
thus its absence as a literal table is evidence, not proof. Second, the same
search finds nothing in the analog Courier either. This is expected, because
none of these images must contain V.91.

The build stamp gives the same result independently. `QF060003` has an
embedded `6.0.3` / `09/22/98`. Thus the date excludes all standards that came
later. These two results together exclude V.91.

### A usable method

That search has the shape of the test that can identify `0xc800` positively.
Search the images for constants from a specification: parameter values,
training or probing sequences, scrambler taps, constellation tables. Then
localise them to a span. This can identify the mode. The method worked as an
exclusion for V.91. The same run with x2 or V.90 downstream constants can work
as a confirmation.

The measurements support only the shape. The image has 1,145 words. Its
multiply density is 25.3 per thousand, against 46-54 for the PCM cores. Its
`rpt` density is 11.4, against 55-67. It has no large lookup table (the entropy
is approximately 6.0-6.7 for each 128-word block, with no peaks). It has a
branch into the shared core. This is a small decision-and-mapping layer. To
find which mapping it implements, you must read the code. Measurements are not
sufficient.

### The V.PCM datapump is absent from the Quad

[vpcm-datapump.md](vpcm-datapump.md) already identifies 302 overlay 8 as **the
V.PCM datapump — x2 first, with V.90 layered onto it**. It finds the DIL
descriptor of the datapump by the fixed SP and TP training patterns. Each
pattern is packed LSB-first and has 66 bits. We verified this against
`IDSDL302.ROM`. The block is at these file offsets:

| Field | Offset | Bytes |
| --- | --- | --- |
| SP pattern | `0x410c2` | `55 4b 2d b5 b4 d2 4a 2b 01` |
| TP pattern | `0x410cc` | `00 21 84 10 22 84 10 42 00` |
| H1-H8 | `0x410d6` | `0a` x 8 |
| assembler `splk *+,#00c5` / `#4141` | `0x410ec` | N = 197, LSP = LTP = 66 |

All four are consecutive. All four are inside the flash range of overlay 8
(`0x3fdd0..0x435bc`), as that document says.

**None of them occurs in `QF060003` or `QR060103`**. We searched as-is, with
the words swapped, and with bit shifts of 1-7 in the two directions. We did not
find the SP pattern, the TP pattern, the H block, or the `N`/`L` signature of
the assembler.

This agrees with the block-hash result above. That result found that 302 id 8
matches 0.0-0.2% of each Quad image, with a longest common run of 10 bytes.
Two independent methods give the same answer: **the Quad does not have the
V.PCM datapump of the analog Courier at all.**

[vpcm-datapump.md](vpcm-datapump.md) carefully says that nothing in these
images separates an x2 descriptor from a V.90 descriptor. Thus the correct
statement is the broader one: the Quad does not have the full V.PCM page, for
the two schemes. This agrees with the Quad as the *server* end of the two
schemes and the Courier as the client end. It does not depend on the
attribution of overlay 8 specifically to V.90.

It also explains an earlier failure in this document. A scan of id 8 for a
training table similar to a permutation found nothing. This looked like a
limit of the scan. That document records the cause: **the training UCode
sequence is not stored in any image, in bytes or either word order. It is
generated rather than tabulated.** The null result was correct.

### The packed Ja blobs: why searching for them could not work

The USR DIL and the V.91 default are also available as packed Ja blobs (258 and
164 bytes). We searched for them in all eight Quad images, the full `QR060103`
payload, 302 id 8 and the full `IDSDL302.ROM`. We searched as-is, with the
words swapped, and with bit shifts of 1-7 in each direction. The best match is
**10 bytes**, and each hit is on the run of zero bytes at pattern offset `0x24`
(USR) or `0x13` (V.91). These hits are artifacts.

This includes 302 id 8, which we know has the descriptor. The blobs are the
wire form. The Ja has a CRC, and the CRC does not cover all of its bits. USR
calculates the CRC while it transmits. Thus the firmware does not have to store
those exact bytes. The stored form is the SP/TP/H/REF field block above. You
must search for that block, and that search does find it.

Also, we could not decode the blobs here. No fixed-width 7-bit or 8-bit
unpacking of the V.91 blob gives its Table 5 training sequence. We tried the two
bit orders, the two value orders, and all start offsets up to 320 bits.
`SP`/`TP` never occur as adjacent 12-bit fields.

### Status of `0xc800`

It is not identified yet, but its limits are better known. It is one of three
alternatives for a single mode slot. It shares 0.0% with each other Quad image
and with 302 overlay 8. The Quad has no V.PCM datapump that it can be a
revision of. Thus it is original Quad code, not a descendant of other code in
this tree. A server-side downstream mapping would be code of this type. To name
it, you must still read the code.

### PCM mapping helpers in the larger `0xc300` image

The larger `0xc300` alternative has an executable mapping family that is
sensitive to the companding law. Routine `0xc7ae` reads bit 0 of flag word
`0xffd9` and installs its four mapping constants. When the bit is clear, data
`0x03a3/0x03eb/0x03ec/0x03ea` becomes `0/0/0x0108/0x007f`. When the bit is set,
those words become `0x002a/0x0042/0/0x007f`. Routine `0xc789` expands the
selected program table into eight working levels.

Routine `0xc9c0` is a codeword-table constructor that you can execute directly.
It takes the destination address in ACC. It uses bit 2 of `0xffd9` to select
`0xc9ce` or `0xc9d7`, and copies nine values from it with `rpt #8 / tblr *+`.
The outputs are `c1 a5 a7 ad af b7 bd c5 cf` and
`e5 95 97 9d 9f a7 ad b5 bf` respectively. The adjacent routines `0xc995`,
`0xc9a6`, and `0xc9b7` select more program-space tables from bit 2 and submode
word `0x03e4`. For example, `0xc9b7` returns table base `0xcc2b` when the bit
is clear and `0xcb00` when it is set. These addresses are data tables, not
executable kernels. The executable consumers are in the `0xc8xx..0xc9xx` block
before them. The component runner `tools/probe_quad_pcm_codewords.py` executes
these helpers and records their outputs. It does not call compressor `0x817f`.
