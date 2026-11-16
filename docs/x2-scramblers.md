# x2 scramblers recovered and executed

Date: 2026-09-10. Sources: the depacketized `firmware/legacy-usrobotics/sdl6-x2.exe`
and the captured 4.03 `artifacts/courier-board-21210-capture-403/courier-board.rom`.

**The x2-only build contains the same two V.34 scrambler recurrences and the
same selector behavior as 4.03. A fixed-GPC generator in the training path that is related to PCM
is also byte-identical across the two builds.** This is now a result of
instructions and execution. It is not an inference from the protocol history.

## Resident routines

| Function | x2 PC | 4.03 PC | Physical selector |
|---|---|---|---|
| Scramble a batch of bits | `8c63` | `8cb7` | `[006f]` bit 0 |
| Descramble a batch of bits | `8c94` | `8ce8` | `[006f]` bit 1 |
| Generate two scrambled-one bits | `8c4e` | `8ca2` | `[006f]` bit 1 |

The selector reads are indirect through `ar1 = 006f`. Thus, their physical address
does not depend on DP. We executed the first two routines. We identified the third routine
by its adjacent shift/XOR implementation, but we did not test it separately.

| Selector | Scrambler | Descrambler |
|---|---|---|
| clear | `1 + x^-18 + x^-23` (GPC) | `1 + x^-5 + x^-23` (GPA) |
| set | `1 + x^-5 + x^-23` (GPA) | `1 + x^-18 + x^-23` (GPC) |

For DP=6, the transmitter state is at `[0358]:[0359]`, and the receiver state
is at `[031e]:[031f]`. Each one holds a 23-bit history in the low 23 bits of
the combined 32-bit word. Bit 0 is the oldest bit, and bit 22 is the newest bit.
The input/output batches are LSB-first, at `[0350]` and `[0320]` respectively.
The masks and the batch widths are `[0351]/[0352]` and `[0321]/[0322]`.
These state addresses are relative to DP. DP=6 is the tested ABI. It is not a property
that the routines establish internally.

For tap `t = 18` or `5`, the equivalent single-bit operation is:

```python
output = input_bit ^ ((state >> (23 - t)) & 1) ^ (state & 1)
state = (state >> 1) | (output << 22)       # scrambler
# Descrambler instead shifts the received input_bit into bit 22.
```

The GPA transmit branch has an extra `v ^ (v << 5)` operation. This operation is for the
feedback in a batch that is wider than five bits. It is not a different polynomial.

## Fixed polynomial in the PCM-associated training path

The 18 words at x2 **`ed2e..ed3f`** are **byte-identical** to 4.03
overlay 8 **`f938..f949`**. This includes the ABI of the state registers:

```text
ed2e  lacc @7a
ed2f  bsar 5
ed30  xor  @7a
ed31  cmpl
ed32  and  @7c
ed33  sacl @7d
ed34  lacc @7d, 7
ed35  or   @79
ed36  sacl @79
ed37  lacc16 @79
ed38  adds @7a
ed39  clrc sxm
ed3a  lt   @7e
ed3b  satl
ed3c  setc sxm
ed3d  retd
ed3e  sach @79
ed3f  sacl @7a
```

The complement injects binary ones. The recurrence is GPC (18,23), without
a role test. The caller of x2 at `ecf8` sets width **6**, and its delayed call at
`ecfa` sets mask **003f** before it enters the generator. `ecff..ed00` transfers
the six generated bits into `@53`. The handler `eceb` fills that word again
on its `@4b == 5` condition, and it shifts its bits out through the sign path.

The paired path at `ed0b..ed26` collects sign decisions in `@53`. It calls the
resident descrambler `8c94` at `ed19`, and it packs the result into `@42/@43`.
The initialization at `e862` explicitly sets receive width 6 and mask 003f.
Then it installs `ed0b` in `@2f`. At `e85a..e85b`, the initialization before it
clears the `@79/@7a` state of the generator after a zero-repeat operation.

This gives specific locations of the x2 training generator/consumer. It does **not**
yet identify these handlers as a named V.90 sequence. It does not find the Sd equivalent of x2,
and it does not prove each scrambler reset and role selection over a complete call.

The common overlay entry at `9d00` writes `[006f] = 4042`. The dispatchers
at x2 `9a19` and 4.03 `9b41` set DP=0 before the table-indirect jump to
`9d00`. Thus, that entry initially selects GPC for the two generic routines.
Do not use that initial state to make a claim about the complete
upstream/downstream call, because we did not trace the full transition chain.

## DIL comparison

The unpacked x2 image has **zero** exact occurrences of the three known
4.03 descriptor signatures:

* SP bytes `55 4b 2d b5 b4 d2 4a 2b 01`;
* TP bytes `00 21 84 10 22 84 10 42 00`;
* assembler header `splk *+,#00c5; splk *+,#4141`.

Each one occurs once in the 4.03 ROM. This is evidence that the specific V.90
descriptor machinery that `vpcm-datapump.md` documents is not in this x2 release without changes.
It does not prove that x2 has no impairment-learning procedure
and no descriptor that is generated in a different way. SP/TP here are the patterns that this firmware selected.
They are not universally fixed V.90 patterns.

## Reproduction and verification

Run this command from the repository root:

```sh
.venv/bin/python artifacts/x2-scrambler-hunt/verify.py
```

The script depacketizes the original EXE with `packet_runs()`. The self-referential address of the INFO fill
handler anchors the resident program: the flat offset
is `0x18100 + 2*PC`. This is a local DSP mapping. It is not a claim that the
concatenated image has accurate flash addresses.

The script finds the fixed generator by its unique 36-byte match. Its six-bit
caller before it names `ed2e`. This independently anchors the program addresses
of the training code (flat offset `0x3f8cc` for `ed2e`).

The original instructions run in `NativeC5x`, with a small call
trampoline that sets DP/ARP. The expected output and the complete updated history come from a separate
recurrence that operates one bit at a time. Results:

* 2,304 cases across the two builds, the two directions, the two selectors, widths 1–9,
  and randomized input/state;
* 256 six-bit training cases: a continuous 768-bit zero-seeded sequence plus
  128 randomized histories;
* all **2,560** comparisons pass, including the full updated state.

The generated disassemblies, the script and `verification.json` are in
`artifacts/x2-scrambler-hunt/`. We did not access a physical modem.
