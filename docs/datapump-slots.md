# Nine modulations, four images, and where fax lives

[fsk-modulation.md](fsk-modulation.md) found a nine-slot datapump table. Mailbox commands `10` and `11`
dispatch through it. That document named two of its slots from
measurements. This document names the other slots and identifies the images that contain them. It also
follows the two items that are *not* in that table: the PCM downstream layer
and the fax modulations.

## The modem's own list

The firmware has its answer in plain text. `AT*C` transmits a constant
carrier. Its help text at `0x19f5a` lists each carrier that the modem can
make: 76 carriers, two for each modulation and rate, one for each side:

```text
(0)  Bell 103, 300        (8)  V.23 Forward Channel     (26) HST 4800 ... (31) 16800
(2)  V.21                 (9)  V.23 Backward Channel    (32) HST 300 bps Back Channel
(4)  V.22                 (10) V.32 4800                (33) HST 450 bps Back Channel
(6)  V.22bis              ...  V.32 up to 21600         (34) V.FC 9600 ... (52) V.34 2400 ... 28800
```

The text is token-compressed. Bytes `0x80` and higher index a length-prefixed
dictionary. The `0x17480` chain gets to only 32 entries in it. `a8` is
`00 bps`, `e7` is ` Originate ` and `c7` is `Answer`. Thus, `HST 3\xa8` is
300 bps, not 375. `carrier_families` stops at the first token. This is sufficient
for family names, but not for rates. The menu spells the fifth HST and V.32 rate as
`122` + `00 bps`, that is, 12200.

`courier_emu.datapumps.carrier_families` reads it: **Bell 103, V.21, V.22,
V.22bis, V.23, V.32, HST, V.FC, V.34**. These are nine families, slowest first. The
datapump table has the same nine in the reverse sequence.

## The slots

The flags are bit *numbers*. The `BIT` instructions that test them use bit
codes, and the C5x shifts by `~code & 0xf`. Thus, code 14 is bit 1.

| slot | flag | table `9b48` (originate) | table `9b51` (answer) | modulation |
|---:|---|---|---|---|
| 0 | `@27` bit 1 | `9d00` | `9d00` | **V.34** |
| 1 | `@26` bit 4 | `b000` | `b000` | **V.FC** ([vfc.md](vfc.md)) |
| 2 | `@27` bit 3 | `b052` | `b052` | **V.32 / V.32bis** |
| 3 | `@26` bit 5 | `c533` | `c7fd` | **HST** |
| 4 | `@26` bit 3 | `cd61` | `cce0` | **V.22bis** |
| 5 | `@26` bit 2 | `cd79` | `ccfa` | **V.22** (with Bell 212A) |
| 6 | `@27` bit 10 | `da31` | `d9bc` | **V.23** |
| 7 | `@27` bit 12 | `d808` | `d7fc` | **V.21** |
| 8 | `@26` bit 6 | `d7e9` | `d7d8` | **Bell 103** |

The sequence is the sequence of the menu, fastest first. That is the shape of a fallback ladder
for rate negotiation. For six of the nine slots, a measurement supports the identification.
The sequence alone is not the only evidence:

* **V.34 and V.FC.** The two overlay predicates use S56 bits `0x40` and
  `0x80` as gates. The help text of the modem itself names these bits `V34` and `VFC`. Thus,
  the label comes from the firmware, and it is not an inference. Refer to
  [pcm-x2-v90.md](pcm-x2-v90.md). Independently, `9d00` selects codec rate
  index 5: 8000 Hz for a symbol rate of 3429 baud.
  Only V.34 uses this rate, and no other slot asks for it. Refer to
  [codec-sample-rates.md](codec-sample-rates.md).
* **V.22bis and V.22.** The two slots install the *same* transmitter `d34a` and
  receiver `ce6e`. The only difference is a pointer to a parameter table of 12-16 words.
  That transmitter steps a 12-entry carrier table by `@44`. `@44` reads 2 on
  the originate entries and 4 on the answer entries: **1200 Hz** and **2400 Hz** at
  7200, with `@6c` at 300 and 600 Hz. Two configurations of one 600-baud
  datapump is exactly V.22bis together with V.22/Bell 212A.
* **V.23.** The two sides run *different* transmitters. Originate installs
  `db2d`, which changes between the increments `0x2000` and `0x1bbc`. That is a 13:15 ratio,
  which is 390/450 to five figures and agrees with no other standard pair. Answer
  installs `dae0`, which builds its increment from `0x4aab` plus a term from the data.
  `0x4aab` is the 2100.0 Hz constant that the answer tone uses. The backward channel comes from
  the caller, and the forward channel comes from the answerer. This is V.23, and it is independent proof
  that table `9b48` is the originate side.
* **V.21 and Bell 103**, measured in [fsk-modulation.md](fsk-modulation.md).

We executed slot 0 after this: refer to [v34-arming.md](v34-arming.md). We
measured slot 3: refer to [hst.md](hst.md).

The identification of one slot has weaker evidence, and a new test is recommended:

* **V.32** for slot 2. Its region writes `@08` = `#4000` = 1800.0 Hz at 7200.

That division also gives information. Slots 0-2 have the same entry in the two
tables. Slots 3-8 are specific to the side. Echo-cancelled full duplex (V.34, V.FC,
V.32) does not need a side in the entry. Frequency-split or asymmetric modulations
(HST, V.22, V.23, V.21, Bell 103) need it.

## HST

[hst.md](hst.md) measures and decodes slot 3: the forward channel is 2400
baud at 1800 Hz on the V.32bis constellations. The back channel is 8-DPSK at 200 or
300 baud near 350 Hz. It has its own mailbox tags `32`-`3b`.

## Four images, and why 8 rides with 6

The loader gives the count. It masks the requested index to four bits and
compares it with 6, 7 and 8. All other values go to the resident
segment. In the row table at `0xe741`, rows 0-4 are zero, and the rows after 8 are
garbage. Only 5, 6, 7 and 8 are ever written to the request byte `0x0d28`.

One image is never requested alone:

```text
e60a  mov al, [0xd28]
e60d  and al, 0x7f
e60f  cmp al, 6
e611  jne e61b
e613  call e61b            ; load overlay 6...
e616  mov byte [0xd28], 8  ; ...then overlay 8 as well
```

Thus, the sets are **{6, 8}** or **{7}**. They cannot be different, because
overlay 7 (`b000`-`cd49`) overlaps overlay 6 (`9d00`-`ce31`) in program
memory, but overlay 8 (`dc00`-`f949`) overlaps neither.
`courier_emu.datapumps.overlay_chain` reports it.

Two predicates select between them: at `0x8972` for 6 and at `0x8999` for 7. Each one
has a gate on a disable bit in `[0x4c6]` (`0x40` and `0x80`) and on a ceiling in
`[0x4dd]`. The DSP can also ask for an image itself:
`in al, 0x5c ; or al, 0x80 ; mov [0xd28], al`.

## V.90 and x2 are overlay 8

Overlay 8 is the PCM downstream layer, and the chaining is the argument. It
loads only together with overlay 6, the V.34 core. A PCM modem needs that core
for its upstream. It has no slot in the datapump table, because it is not a
modulation that the modem *transmits*. It is a receiver for what the digital end
sends.

The supervisor has the two rate ladders as `CONNECT` strings, in steps of 1333⅓ bps:

| | rates |
|---|---|
| **x2** | 33333 … 57333, and 64000 - 16 rates, each also `/ARQ/x2` |
| **V.90** | 28000 … 62666, and 64000 - 28 rates, each also `/ARQ/V90` |

x2 starts at 33333, but V.90 starts at 28000, and V.90 fills each step
between them. [pcm-x2-v90.md](pcm-x2-v90.md) tells how the two are enabled, what each one gives to the DSP, and what is still
unknown about them.

## Fax is resident, and it collides with overlay 8

The `AT*C` menu has no fax entry. Its own text says that fax carriers need
`AT+FCLASS=1+FATX=nn`. The fax commands are in a separate parser
table at `0x20d80`, with the names and then the handler offsets: `TS= RS= TM= RM= TH= RH= CLASS
ATX= ARX= AA TXD= …`. This is Class 1 (`+FTM`, `+FRM`, `+FTH`, `+FRH`) and
Class 2.0.

On the DSP side, the fax modulations are **in the resident bank**. Three mailbox tags
dispatch them. Their handlers put a table base in `@7d` and jump to a
shared selector at `dc8e`. That selector indexes the table by the high nibble of the argument:

| slot | tag `21` | tag `22` | tag `20` | carrier | modulation |
|---:|---|---|---|---|---|
| 1 | `d853` | `d808` | `d864` | 1650/1850 | **V.21 channel 2** (300 bps HDLC) |
| 2 | `dc79` → `e525`/`e532` | `dc59` | `ddbb` | **1800 Hz** | V.17 |
| 3 | `dc75` → `e4f6` | `dc55` | `dd96` | **1700 Hz** | V.29 |
| 4 | `dc71` → `e4d5` | `dc51` | `dd78` | **1800 Hz** | V.27ter |
| 5 | `def0` | `def0` | `def0` | - | none |

`courier_emu.datapumps.fax_carriers` follows the branches of each slot to the
`splk @44, #<increment>` that it installs, and reads it at 7200 Hz. 1700 Hz is
the carrier of V.29 and of no other modulation. Thus, that row is an
identification and not an argument from the sequence. The two 1800 Hz rows are
separated by the same convention of decreasing speed that the data ladder uses. Thus,
V.17 above V.27ter is an inference, not a measurement. The slots of tag `21` install a
transmit carrier, and the slots of tag `20` install receive coefficients. This is
what half duplex needs. Slot 1 does not need its own carrier, because it uses
the cells of the FSK modulator again through the V.21 setup routines.

The result is structural. The fax dispatch (`dc48`-`dcf4`) and its
datapumps (`e4d5` onward) are in `dc00`-`f949`, which is exactly the load range of overlay
8. **When the PCM layer loads, it overwrites the fax subsystem**. Thus, a
V.90/x2 connection and Class 1 fax cannot be resident at the same time. The
board loads again for one or the other. The one part that stays is slot 1. The
V.21 channel 2 code is the same FSK datapump that the data ladder uses, and it
is below `dc00`.

## What is still open

* Slot 2 = V.32 has only one constant as evidence. It is recommended to measure it with the same method as for HST.
* Nothing yet separates x2 from V.90 *in* overlay 8. Overlay 8 does have
  two code families, but the bit that selects between them is `&X`, the
  synchronous clock source. Refer to [pcm-x2-v90.md](pcm-x2-v90.md).
* V.17 against V.27ter for the two 1800 Hz fax rows is an argument from the sequence.
* The `+FTM`/`+FRM` handlers get to the mailbox through the command ring of the supervisor,
  not through a direct call. Thus, we did not read from the supervisor the mapping from a Class 1 modulation
  number to one of these five slots.
