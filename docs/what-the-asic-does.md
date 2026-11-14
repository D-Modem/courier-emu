# What the ASIC does

This is a summary of what this repository has shown about the `NEC USA
1-016-905` gate array, and of what is still a guess. Each claim says which it is.

The short version: it is **the entire board outside the two processors**. The
80186 communicates with all other parts through it, the C52 communicates with the 80186 through it, and
the line-side parts are controlled by it. It is not one peripheral of several. On the
I/O bus of the CPU, it is the only device.

## Why "the only device" is a measurement, not a figure of speech

The peripheral control block of the CPU is relocated into *memory* at
`0xff00`-`0xffff`, and flash and SRAM are also memory. Thus, any device that answers
an `IN` is the gate array. A sweep of the space
([asic-port-map.md](asic-port-map.md)) gives its shape:

* Only **even** addresses are decoded. All 64 odd ports below `0x80` read
  `0x00`, because the ASIC presents 16-bit registers and `IN AL` reads a byte.
* The decode **stops at `0x7f`**. Above it, all 64 even ports read back their
  own address, and all 64 odd ports read `0x00`. This is a bus that nothing controls.

That is 64 registers, and the firmware uses about half of them.

## The register map, by what the firmware does with each group

The static site counts come from `artifacts/io-port-map/board-21210/`, and the values come from the
CPU-side capture in `artifacts/cpu-port-map-01/`. The read/write asymmetry is the
useful signal. A group that the firmware only writes is a control surface. A group that it
only reads is a status surface.

| ports | sites | idle value | what it is |
|---|---|---|---|
| `0a` `0c` `0e` | 5r / 21w | `f7` `40`/`60` `07` | configuration; `0e` is write-only |
| `10` `12` `14` | 20r / 34w | `86` `8a` `7e` | **board latches** - hook relay, NVRAM strobe, carrier-detect pair, ring detect, option straps |
| `18` `1a` `1c` `1e` | 104r / 137w | `ff` `ff` `fd` `ff` | **the handshake** - busiest group by far; `1c`/`1e` are the mailbox status pair |
| `40`-`4e` | 20r / 45w | `55`/`00` alternating | **the DSP download window** - eight latches |
| `50`-`56` | 9r / 8w | `55`/`00` alternating | second window bank |
| `58` `5a` / `5c` `5e` | 68r / 44w | `20` `00` / `0e` `00` | **the mailbox** - tag pair and data pair |
| `60` `62` | **27r / 0w** | `4b` `00` | **DSP-to-host stream** - pure input |
| `64`-`7e` | 3r / 0w | `78 09 8f a7 e8 aa b6 97 51 51 06 4f b3` | read almost never; looks like identity or strapping |

Two of those rows give their own argument. `60`/`62` has **zero** write sites
in the full image. Thus, it is a one-way channel out of the DSP. Also, ten of the
thirteen values in `64`-`7e` are byte-identical to a sweep that we took when this unit
ran stock 7.3.14 and not ID_SDL 4.03. The values are the same across two firmware
versions and two sessions. This is what fixed configuration looks like. State does not
look like this.

## The four jobs

### 1. It is the board's I/O

Ports `0x10`, `0x12` and `0x14` are latches that carry the hook relay, the NVRAM
chip strobe, the carrier-detect pair, ring detect and the option straps. The
supervisor controls all of them through a single read-modify-write latch
driver (`panel.py` records it at physical `0x5e2b0`/`0x5e2e5`). For this reason,
the firmware reads and writes these ports. Nothing here is complex. It is the front
panel and the line relay.

### 2. It bootstraps the DSP

The program memory of the DSP above `0x8000` is **RAM**. The download stream of the
supervisor agrees byte for byte with the resident segment of the image, all 30,172
words: `bootstrap_match: true` at `bootstrap_bytes: 60344` in each
answered-call run. It says nothing about `0000..1fff`. This firmware
never addresses this range, and the board answers it from the mask ROM of the C51
([hardware-timebase-and-audio-path.md](hardware-timebase-and-audio-path.md#3-corrected-the-xmf-payload-loads-at-8000-not-0000)).

The transfer goes through `0x40`-`0x4e`, with thousands of strobes while the
C52 is held in reset. Thus, the ASIC holds the DSP in reset and writes its
program RAM. [dsp-rom-probe.md](dsp-rom-probe.md) gave this architectural alternative
but could not select it. The download stream now gives the answer.

### 3. It is the mailbox between the two processors

An outbound message is a 16-bit tag on `0x58`/`0x5a` and a value on
`0x5c`/`0x5e`. The CPU commits it when it answers the standing request of the board,
that is, when it writes bit 0 back to `0x1c`. On the far side, the dispatcher of the DSP reads the tag from
its own data cell `0xff5e` and the word from `0xff5f`. It rejects tags above
`0x7f`, and it branches through a jump table of 121 entries.

Thus, the ASIC connects *CPU I/O ports* to *DSP data-memory cells*. It joins two
address spaces that are not related to each other. For the emulator, this
is the most important function of the ASIC, because it is the
only path through which the supervisor and the datapump can communicate.

The reverse direction is `0x60`/`0x62`, the read-only window. The sender of the DSP
writes it, one word for each interrupt. It continues when the CPU acknowledges bit 2
of `0x1c`.

### 4. It fronts the analogue side - and this is the part that is missing

The firmware clearly does *not* do these items. Thus, they are functions of
the ASIC:

* **The codec bring-up.** Neither processor does the initialisation sequence
  of the datasheet. The 80186 writes `0x40`-`0x4e` thousands of times and
  never reads them. The external reads of the C52 are the host window and
  the line ADC. Thus, neither processor can see the readiness byte for which the sequence waits.
* **The line detector.** The supervisor counts its own five qualifying hits at
  `[0x649]`, but the reading that it counts comes from outside. The harness must
  answer the `0x7c` poll manually.
**Not the tone generator, though this document first said so.** The statement of the README
"the tone generator is the ASIC's" is not correct. When the firmware dials a digit, it
sends `0x16:0000`, three constant lanes `0x19:020d`, `0x1a:3000`, `0x1b:0c08`,
the keypad index on `0x13`, then `0x16:0000` when the tone stops. Those
three lanes are host-write tags, and their handlers store into **DSP data memory**,
at `0x03ad`, `0x0392` and `0x03f1`. The tone parameters go to the C52. Thus, the
synthesiser is part of the datapump. `--exchange` hears silence because the
C52 of the harness does not get to that code. A generator in an unmodelled location
is not the cause.

These are the tones, from the dial path of the firmware:

| tone | where it is decided |
|---|---|
| DTMF, all 16 keys | `0x6353c` maps characters to keypad indices: `0`-`9` pass through, `#` to `0x0a`, `*` to `0x0b`, `A`-`D` to `0x0c`-`0x0f` |
| tone duration | S11, held at `[0x8e9]` by the countdown at `0x82342` |
| interdigit gap | the same countdown less `0x30`, at `0x8235b` |
| pulse dialling | `0x822a3`, a break/make loop - no tone at all |

There are also the call-progress tones that the firmware must *recognise*, but not send.
`exchange.py` models them: dial tone 350+440, ringback 440+480, busy and reorder
480+620, answer tone 2100.

There is a fourth, smaller job. The identity of the DAA gets to the supervisor as
mailbox tag `0x7b`, one time. The firmware has information about the line-interface part,
because the ASIC *tells* it.

## What it is not

**Not the timebase.** The 5.000 ms tick is the Timer 0 of the 80186 itself: max count
25,200 at CLKOUT/4 with a 40.320 MHz oscillator. Four independent methods confirmed this.
One of them was a counter routine on the modem that logged exactly 200.0
increments each second.

**Not in the CPU's audio path.** We swept each port during analogue loopback.
Only the four handshake registers change. No CPU port carries samples. The path of the
audio on the *DSP* side is still not known. The DSP polls `DRR`, `TRCV` and
its own ASIC ports together, and it never transmits on either serial port after
reset.

## What is still unknown

* **Its behaviour is unpublished.** We inferred all of the above from the traffic of the two
  processors. There is no datasheet, and `1-016-905` is a USR part
  number. Thus, it is improbable that a datasheet will ever be available.
* **The pin connections are not traced.** "It is the only device on the I/O
  bus" is an argument from the memory map, and from the absence of other
  candidates. It does not come from a probe on a pin.
* **The monitor lies about the download window.** `ATGLK2I` and the `IN` of the CPU
  agree on 51 of 64 ports. They do not agree on all twelve of `0x40`-`0x56`,
  and the pairing is inverted (`artifacts/cpu-port-map-01/`). Any result about the
  window that depends on the monitor sweep must be measured again.
* **`0a`, `0c`, `0e` and the `64`-`7e` block are unattributed.** The second
  looks like identity, but nothing shows that code reads it for that purpose.
  There are only three read sites in the full image.
* **The dynamics are barely sampled.** A tick-rate sampler now exists, and it sees
  events that the serial monitor cannot see. But 200 Hz is still slow compared with a codec
  frame, and the only capture until now is one line seizure.

## The DSP sees the ASIC as its 16 I/O ports (2026-09-07)

SPRU056D tells what the resident actually reads when it polls `0xff57`.
Data `0050h`-`005Fh` is not reserved, and it is not a peripheral block. It is the
**16 memory-mapped I/O ports, PA0 through PA15** of the 'C5x (section 3.5.11 and
the note of Table 8-8; `0x50` = PA0, `0x5F` = PA15). They are accessible through
ordinary data addressing and through `IN`/`OUT`. `LAMM`/`SAMM` force the
9 MSBs of the address to zero. For this reason, `lamm *` with AR1 = `0xff57` goes to
`0x57`.

Thus, each DSP-side address that this repository called "the ASIC window"
(`0x50`, `0x51`, `0x52`, `0x54`, `0x57`, `0x5e`, `0x5f`) is one of sixteen I/O
ports, and **the ASIC is the device on the other side of them**. That is the
clearest statement of the interface until now, with one correction below: the ASIC
presents sixteen 16-bit registers to the DSP at `PA0`-`PA15`.

**"At most sixteen" is too narrow.** The DSP also writes ports `0x60` (the
stream sender at `0x84b7`) and `0x68`-`0x6c` (at reset and in the ISR region).
These are outside `0x50`-`0x5f`. Thus, they are ordinary I/O addresses that do not
alias into data space. They are `IS`-qualified cycles, as all other I/O cycles are, and we
now measured that `IS` is connected to the ASIC
([dsp-cpu-interconnect.md](dsp-cpu-interconnect.md)). Thus, the gate array also decodes
those ports, and its DSP-side register file **is** larger than `PA0`-`PA15`.
The address decode of the board is `A0`-`A3` plus `A5`, without `A4`. This
separates the `0x5x` bank from the `0x6x` bank, and it identifies each
port that the firmware uses without ambiguity. Thus, `0x60` is a separate register and not an alias of
`PA0`. Refer to [dsp-cpu-interconnect.md](dsp-cpu-interconnect.md).

The known uses until now:

| port | address | use |
|---|---|---|
| PA0 | `0x50` | the parallel boot loader's word source; a scaled sample written by the codec ISR at `0x8199` |
| PA1 | `0x51` | read by the handler at `0x8211` |
| PA7 | `0x57` | **status word**: bit 0 host message pending, bit 1 gates `0x83d6`, bit 2 gates `0x847a`, bit 9 gates `0x80f8`; the DSP acknowledges by writing 1 |
| PA14 | `0x5e` | inbound message tag |
| PA15 | `0x5f` | inbound message data |

The bit meanings come from the ASIC, and no TI document gives them. But we
can get to them from this side. The parallel window of the 80186 at ports `0x40`-`0x5e`
supplies the ports of the DSP. Thus, the code that sets them is supervisor code in
an image that this repository already has.

This also removes a suspicion that we recorded earlier: that the core mapping of data
`0x50`-`0x5f` to I/O space mixed two separate spaces. On the
'C5x, they are the same locations by design.
