# x2 and V.90: one receiver, two capabilities

[datapump-slots.md](datapump-slots.md) put the PCM downstream layer in
overlay 8, which the loader chains onto the V.34 core. It did not explain the difference
between x2 and V.90. This document explains most of it. They are not two images and
not two datapump slots. They are two capability bits over the same overlay.
They are separated by one S-register bit each, one command and two
blocks of result codes.

## S58 is the switch, and S56 named the overlays

The help text of the modem itself has the bit meanings. The text is compressed, but the
values and names are clear. `courier_emu.datapumps.s_register_bits` reads
them:

| | bit 1 | bit 2 | bit 4 | bit 8 | bit 16 | bit 32 | bit 64 | bit 128 |
|---|---|---|---|---|---|---|---|---|
| **S56** | nonlinear coding | TX level deviation | preemphasis | precoding | shaping | V34+ | V34 | VFC |
| **S58** | **x2** | BLER monitor | | | | **V.90** | | |

We do not assume the base of the S-register file. The `ATSn` reader takes the number
that the user typed and does `mov al, byte ptr [bx + 0x48e]`. Thus, S*n* is at
`0x48e + n`, and S56 and S58 are at `0x4c6` and `0x4c8`.

This also answers a different question. The overlay predicates at `0x8972` and
`0x8999` use `[0x4c6]` bits `0x40` and `0x80` as gates, and S56 names these bits **V34** and
**VFC**. Thus, overlay 6 is V.34 and overlay 7 is V.FC by the label of the firmware itself,
not by inference from the symbol rates.

## The two schemes are the same routine twice

Each connection setup evaluates the two schemes, at `0xbbe6`:

```text
bbe6  call 8e9a     ; may we try x2?
bbe9  jb   bbee
bbeb  call 8f0e     ; x2 setup
bbee  call 8e59     ; may we try V.90?
bbf1  jb   bbf6
bbf3  call 8edb     ; V.90 setup
bbf6  ...           ; then the overlay choice
```

The two predicates are the same code two times. When you compare them, the only
difference is the bit:

| | x2 (`8e9a`) | V.90 (`8e59`) |
|---|---|---|
| disabled by | `test [0x4c8], 1` | `test [0x4c8], 0x20` |
| line/config gate | `call b88d` | `call b88d` |
| mode `[0x4e9]` | ≠ 1 and < 6 | ≠ 1 and < 6 |
| max speed `[0x4f8]` | 0, or ≥ `0x11` | 0, or ≥ `0x11` |
| ceiling `[0x4dd]` | ≥ 8 | ≥ 8 |

Thus, a modem has the same eligibility for the two schemes. `0x11` is the speed index where the
PCM rates start, and the same index is the minimum in the two predicates.

## What each one tells the DSP

Here they are different. The two setup routines clear the same block of PCM statistics at
`0xa0c`-`0xa16`, and then:

* **x2** (`8f0e`) builds a capability word: `and bx, 0xfdff`, then `0x0200`
  from S58 bit 4, `0x0400` unless S58 bit 16, then it clears `0x1800` and the
  top two bits. It sends the word as **command `70`**. The handler of the DSP puts it
  at data `0xfff1` under a `0x3fff` mask and sets `0xfff4` to `0x8000`. This
  tells the datapump that new parameters have arrived.
* **V.90** (`8edb`) has the same shape and an **empty body**: after the test comes
  `jne +0 ; ret`, a branch to the next instruction. In this build,
  the V.90 path gives the DSP nothing of its own.

`courier_emu.datapumps.pcm_control` reports the two routines, with the empty body.

They share the rate mask. `8fc9` changes the min and max speed settings
(`[0x4f7]`, `[0x4f8]`, both relative to the same `0x11`) into a 15-bit mask
through the table at `0x9048`. It sends the mask as command `71`, which goes to
data `0xfff3` under a `0x7fff` mask. There is one mask, for the scheme that trains.

## The ladders

All the rates are multiples of **8000/6 bps**. PCM downstream is 8000 symbols each second
in six-symbol frames. Thus, a rate is a count of bits for each frame, and 1333⅓ bps is
one of them. `courier_emu.datapumps.pcm_ladders` reads the CONNECT strings:

| | rates | count |
|---|---|---:|
| **x2** | 33333 … 57333, and 64000 | 16 |
| **V.90** | 28000 … 62666, and 64000 | 28 |

V.90 starts four steps lower and fills each step. x2 starts at 33333 and
skips 34666, 38666 and 40000. The two ladders stop at 57333 before the 64000 entry. That entry
is the rate of the digital side, not a modem rate.

The result-code table at `0xa1eb` (336 entries) also keeps them separate.
The block of x2 starts at code 182 and uses four codes for each rate (plain, `/ARQ`,
`/x2`, `/ARQ/x2`). The block of V.90 starts at 258. Where the two ladders overlap, at
33333 through 57333, the entries of V.90 use only two codes each, because the plain
and `/ARQ` strings for those rates are already in the x2 block.

The diagnostics are also separate: `x2 Status` and `V.90 Status` are different
report blocks, with reasons such as `x2 disabled on local modem` and
`Unspecified impairment`.

## Overlay 8 holds two receivers

It has two state machines, not one. The image divides into an **e-family** near
`e4c5`-`eaff` and an **f-family** near `f442`-`f94a`. They share identical subroutine
bodies. `courier_emu.datapumps.receiver_twins` finds ten runs of a minimum of
ten identical words, far apart at a consistent offset. These include:

```text
e9be-e9cb  ==  f7eb-f7f8    (+0xe2d)
e9d8-e9e1  ==  f805-f80e    (+0xe2d)
e9f2-e9ff  ==  f821-f82e    (+0xe2f)
e59f-e5b3  ==  f4e2-f4f6    (+0xf43)
```

Only 158 of 7,498 words repeat identically. At the best alignment of the two
spans, only 46 words of 1,536 agree. Thus, this is not one state machine built
two times. It is two sequences that call the same helpers (`e019`, `e356`, `8766`,
`8797`) and do different things with them.

**The fork is one bit.** At `de0b`, at the top of the dispatch of the image:

```text
de0b  lar   ar1, #039f     ; the datapump flag word, @1f on page 7
de0d  bit   8, *           ; bit code 8, which is bit 7
de0e  bcnd  f442, ntc      ; clear -> the f-family
de10  b     e4c5           ; set   -> the e-family
```

**Bit codes are not bit numbers.** The C5x `BIT` shifts by `~code & 0xf`
(`op_bit` in `native/c5x_ops.ipp`). Thus, `bit 8, *` tests **bit 7**, mask
`0x0080`. `courier_emu.datapumps.receiver_fork` reports the number.

The V.34 core dispatches into the two families from its own side, and there it uses two bits,
one for each family:

```text
a456  bit  8, *  ; bcnd e9a0, tc     ; bit 7 - the e-family
a45b  bit  9, *  ; bcnd f7d8, tc     ; bit 6 - the f-family
```

`0x039f` is the same flag word that each datapump entry writes. Thus, bits 7 and 6 are
two more datapumps in the same register. Two identical resident
routines, `b402` and `c91a`, set bit 7. `b2df` and `c87f` clear it.

**The supervisor arms them by mailbox command.** Three siblings at `823d`,
`8245` and `824d` each install a sample-path routine in `@61` and then change the
flag:

| tag | sample path `@61` | flag |
|---|---|---|
| `4f` | `819d` | **sets** bit 8 |
| `4d` | `819d` | clears bit 8 |
| `4e` | `81bb` | clears bit 8 |

`819d` and `81bb` are the two sample paths, and their difference is what PCM
needs. `819d` assembles each sample from **two 8-bit halves** with saturation
(codewords). `81bb` interpolates and writes port `0x6a`. The two commands
that select the PCM sample path, `4d` and `4f`, are different *only* in the receiver
bit. A different pair, at `dccd` and `dcde`, sets and clears bit 9.

## What the two families differ in

`courier_emu.datapumps.receiver_families` reads the four differences from the
image.

| | e-family (`e4c5`) | f-family (`f442`) |
|---|---|---|
| equalizer installed at `@0a` | `e055`, **96 taps** | `e047`, **64 taps**, then `e055` later |
| its adaptation at `@16` | `e08c` | `e079`, `e0be`, then `e08c` |
| phase hooks at `0x03cd` | `ae72`, `ae7b`, `ae64` | `ae57`, `ae60`, `ae31` |
| `0xfff4` bits tested | 9, 12 | **2**, 1, 0, 12 |
| into the V.34 core | `a35e` | `a35e`, `a661`, `c56a`, `c5e0`, `c91c`, `c961`, `c9fc` |

**The equalizer.** `e047` is a 64-tap `mac` against the coefficient bank at
`fba0`, with a two-tap section after it. `e055` is a 96-tap `macd` with 14-tap
and 6-tap sections and a different bank. `e079` adapts the 64-tap bank.
`e08c` and `e0be` adapt the 96-tap bank. All of them have a gate on `0xfff4` bit 6. The e-family
installs the long filter at its entry and keeps it. The f-family starts short
and **changes to the long pair at `f6e4`**, immediately after its
four-candidate search. Thus, it makes its equalizer larger during the startup.

**The phase hook.** `0x03cd` is the callback cell that each datapump phase writes.
The values of the e-family go to the codec rate selector: `ae72` calls `adee`, loads
a batch of parameters and continues into `call 8140`. `ae7b` is a shorter entry
into the same `call 8140`. The values of the f-family are only `ret`:
`ae57` and `ae60` are both a bare `ret`. **The e-family programs the codec sample
rate again at that hook. The f-family does not.**

**What the rate change selects.** The hook of the e-family is the only path that
gets to `8140`, and the index that it passes comes from `adee`:

```text
adee  call adc4        ; acc = ffb0 & ffb1 & ffb2 & ffb3, parked at ffb4
adf0  sacl @7d
adf1  bit 10, @7d ; lacl #05 ; retc tc     ; bit 5 -> row 5
adf4  bit 11 -> 04    ; bit 4 -> row 4
adf7  bit 12 -> 03    ; bit 3
adfa  bit 13 -> 02    ; bit 2
adfd  bit 14 -> 01    ; bit 1
ae00  lacl #00                             ; none -> row 0
```

Those are bit codes again. Thus, the scan reads **bits 5 down to 1**. The
supervisor builds the capability word at `0xffb1` from three S-registers:
`(~S54 & 0x3f) | ((~S55 & 0x0f) << 6) | ((~S56 & 0x1f) << 10)`. **Bits 0 to 5 of S54
are the six V.34 symbol rates**, 2400, 2743, 2800, 3000, 3200 and
3429, as the help text of the modem says. `0xffb0` is a fixed mask (`7d7f`).
`0xffb2` is written during the negotiation, and `0xffb3` is built at `adcc`. Thus, the
`and` is what all parties permit.

Thus, the rate change of the e-family selects **the codec sample rate for the fastest
V.34 symbol rate on which all four words agree**.
`courier_emu.datapumps.rate_choice_selects` reads it:

| common symbol rate | codec row | sample rate |
|---:|---:|---|
| 3429 | 5 | 8000 Hz |
| 3200 | 4 | 8000 Hz |
| 3000 | 3 | 7578.95 Hz |
| 2800 | 2 | 7578.95 Hz |
| 2743 | 1 | 7578.95 Hz |
| none of them | 0 | 7200 Hz |

The fit is also a check on the bit numbering: six symbol rates go to six
codec rows in sequence. The bit *codes* would not do that.

**The parameter flags and the V.34 core.** The f-family reads `0xfff4` bits 2,
1 and 0, and the e-family reads none of them. The two families read bit 12. The
four-candidate search of the f-family *sets* bit 13 (`opl *, #2000`), which overlay 6 reads at
`c5e7`. Note that this is not the same flag that the parameter
selectors of overlay 6 read. `c9f3`, `c9d2` and `c5e0` are written as `bit 13`, but that is a
bit code. Thus, they read **bit 2**. It is necessary to examine again, with the correct numbering, which sites use the bit 13 of the search
other than `c5e7`.

The f-family calls into the V.34 core at seven points, and its phase pointers
include overlay-6 addresses (`c4e7`, `c50a`, `c682`, `c683`). Thus, it gives the
sequencing to the core and takes it back. The e-family calls the core one time and
keeps all of its phase pointers in overlay 8.

Thus, the f-family is the complex one: it fits four candidates, makes its
equalizer larger, and drives the parameter tables of the core. The e-family is
self-contained and programs the codec rate again. This agrees
with the bit that selects them being `&X`: the e-family is what runs when the
transmit clock is recovered from the received signal.

## The `0xfff1` thread ends short of the fork

The capability word of x2 does not get to the datapump as a bit test. **No overlay
reads `0xfff1`**. Only the resident reads it, at `8e4b`, where it selects
`fff1` or `fff2` and gives it on. Each overlay does branch on
`0xfff4`, but its **bit 2** (the instructions say `bit 13`, a bit code) is
not the scheme:

```text
f632  lar   ar1, #0822 ; rptz #0006 ; sacl *+     ; clear seven words
...                                                ; try four candidates,
f6b5  lar   ar1, #0822 ; cpl *, #0003             ; keep the best in 0x0822
f6c3  lar   ar1, #fff4 ; xc 2, tc ; opl *, #2000  ; winner 4 sets bit 13
```

`f632`-`f6b3` is a search. `@72` counts four candidates down. Each candidate gets a score from a
sum of squares against the tables at `f7bb` and `f7c5`. The best is kept in `0x0830`
and copied to `0x0822`. Then bit 2 selects between two parallel parameter sets
in all later code, in overlay 6 and in overlay 8: `c9f3` selects table
`cc72` or `cb47`, `c9d2` and `c9e3` select adjacent entries, `c5e0` selects 1 or
2. That is the shape of a **measured property of the digital path** (a law or
a pad, decided when four candidates are fitted). It is not the shape of a scheme that the supervisor
configured.

## Who sends `4d`/`4e`/`4f`, and it is not V.8

They never show as `mov ax, imm`, because they do not go through that sender.
They go through the **packed** sender (`lcall 0x8f46:0x01e8`, tag in `ah` and data
zero), and a byte of the stored profile selects the tag:

```text
be6f  mov  al, byte ptr [0x4ed]
be72  cmp  al, 1 ; je be7e
be76  cmp  al, 2 ; je be82
be7a  mov  ah, 0x4d      ; 0
be7e  mov  ah, 0x4e      ; 1
be82  mov  ah, 0x4f      ; 2
be84  xor  al, al
be86  lcall 0x8f46, 0x1e8
```

`courier_emu.datapumps.receiver_selector` finds the two sites that do this:

* **`0xbe6f`**, a bare sender that runs only when `[0x4e9] > 5` or `== 1`
  (`be5f` skips it for modes 0 and 2-5). That is the complement of the x2 and V.90
  eligibility test. Thus, no call that can train x2 ever sends a tag. Its caller
  is the datapump bring-up, and the instruction before the call is the overlay
  loader: `b620 cmp byte [0xd28], 0 ; jne ; call e60a`, then `b62d call be5f`.
  The receiver family is armed at the same time as the image that holds it.
* **`0x4749`**, in a routine that programs again the ASIC ports 2, 4, 6 and 8.
  For the same three cases, it writes `0x3c`, `0x3d` or `0x3e` to port `0x0c`
  before it sends the tag. The analogue path is switched together with the receiver.

Thus, the selection is not V.8 and not an INFO sequence. **It is a saved
setting.** `[0x4ed]` is written only at `0x26cae`, by an AT handler that parses
a number and rejects all values above 2. It has a twin at `[0x563]`, selected by
the same active-or-stored test that the S-register reader uses. The two profile
blocks start at `0x048e` and `0x0504`, and the two copies are `0x5f` into their
block. That is after the S-registers, and the help text documents the S-registers only to S70.

## The command is `&X`, and it is the clock source

The setting names itself in the `&V` display. Each line there is a label
routine followed by a value. A label routine prints the string that comes after
its own call:

```text
1b4d6  call 1bb11            ; the label
1b4d9  jae  ...              ; then the value:
1b4f0  mov  al, [0x4ed]
1b4f3  jmp  1b38e            ; print it as a number

1bb11  test byte [058b], 48
1bb18  call <print inline>
1bb1b  82 '&' 'X' 00         ; the string it prints
```

`courier_emu.datapumps.receiver_setting_command` follows that and reads **`&X`**
from the image. Its help entry at `0x19790` has three options and ends with
`RX ... is Source`. `&X` is the **synchronous transmit clock source**: DCE,
DTE, or recovered from the received signal.

| `&X` | `[0x4ed]` | tag | sample path `@61` | `@1f` |
|---:|---:|---|---|---|
| 0 | 0 | `4d` | `819d`, a sample from two 8-bit halves | clears bit 8 |
| 1 | 1 | `4e` | `81bb`, interpolating, writes port `0x6a` | clears bit 8 |
| 2 | 2 | `4f` | `819d` | **sets bit 8** |

The two sample paths explain it. When the DTE supplies the clock, the
data must be resampled between two clocks. That is what `81bb` does with its
interpolation, and `819d` only assembles the word. `@1f` bit 8 is read back
at `81e4` (`bit 7, @1f`), in the same ISR region as those two paths.

## What this retires

**`&X` does not select the receiver family, and the families are also not x2 and
V.90.** Two interpretations stop here, one from each of the last two sections.

The three-way shape of the setting looked like
"off / one scheme / the other scheme". That was a guess from a shape, and the name of the
setting showed that it was wrong. Then the bit numbering showed that the remaining part was wrong: `&X2` sets `@1f`
**bit 8** (`opl @1f, #0100`), but the fork tests **bit 7**. They are
different bits. `&X` gets to the sample path, not to the fork.

The structure stays correct. Overlay 8 holds two code families, `de0b` forks
between them on `@1f` bit 7, and the V.34 core dispatches into the two families on bits 7
and 6. The code that sets bit 7 is `b402`/`c91a`, in the datapump phase code and
not in a configuration path. Thus, the purpose of the two families is still open.

## What is still open

**We recovered the wire-level selector of V.90, but not the selector of x2.** The DSP has one
writer for the outgoing INFO1a bits `37:39`: `9185` calls `9267` and writes its
three-bit result to `ff1a` at bit offset `0x25`. Under Table 10/V.90, the
integer `6` in that field requests V.90 and the 8000-symbol/s direction of the digital modem.
The nearby six-row V.34 index decoder is a different path. Do not
think that it is this selector. x2 has no parallel writer for bit offset
`0x25`. Its known local difference is still command `70` into `fff1`. Refer to
[x2-v90-protocol-selection.md](x2-v90-protocol-selection.md) for the exact
instructions and the remaining x2 trace.

**What the two families are.** With the clock-source interpretation, the fork
looks like a timing variant. But nothing here tells what is different between the
tables that each family has.

**The arming of bit 9.** `dccd` sets it from the `dc00` block, which overlay 8
replaces. Thus, it is necessary to find which image owns that handler when it runs.

**What bit 2 actually measures.** Four candidates and a least-squares fit is
the correct shape for µ-law against A-law, or for the digital pad. But nothing
here names it.

**The empty V.90 body gives a second possible interpretation.** It can mean that V.90 needs no
DSP-side parameters, because its capabilities go in the V.8 CM/JM exchange,
which the supervisor drives. Or it can be a routine with a body that this build no
longer needs. The evidence here agrees with the two interpretations.
