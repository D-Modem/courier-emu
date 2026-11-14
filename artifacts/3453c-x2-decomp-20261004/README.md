# 3453C x2 DSP decompilation, first pass

Source: `docs/3453C_v2.3.33/2_3_33.XMF`, SHA256
`c8d44a1c984a203f6e9a91b14c77382706ea05fc2b860081f986c47b6fa7c41e`.

`x2_dsp_lift.c` is a **manual C semantic reconstruction** of the identified
x2 setup routines and shared PCM routines. It compiles. But it is not recovered vendor
source, and it is not a complete modem datapump. We gave the names to the functions and variables.
The DSP uses separate program/data spaces, and the program addresses
depend on the overlay. Thus, a single flat disassembly would mix incompatible code.

## Files

- `x2_dsp_lift.c`: readable C equivalents, with the original PCs and preconditions.
- `x2-focused.asm`: the original words and decoded instructions for the lifted
  routines and their immediate negotiation context.
- `overlay-5.asm` through `overlay-8.asm`: full linear listings of each
  downloaded image. We extracted them with the overlay table of the supervisor.
- `verification.json`: the identity of the input image and the native execution results.
- `../../tools/recover_3453c_x2.py`: the extractor and verifier, for reproducible results.

The complete listings include tables and data that decode as plausible
instructions. If an item is in a listing, this does not claim that the code is reachable.
Here, we lift the semantics of only the specifically identified routines.

## Reconstructed routines

| Routine | Image | DSP PC | Evidence |
|---|---|---|---|
| x2 command 70 capability setup | low overlay 7 | 08f8 | Supervisor x2 caller and native execution |
| Shared command 71 rate mask | low overlay 7 | 090b | Dispatch table and native execution |
| Shared command 72 parameter | low overlay 7 | 0921 | Dispatch table and native execution |
| Shared command 74 enable | low overlay 7 | 091c | Dispatch table and native execution |
| Shared command 76 six-bit parameter | low overlay 7 | 0912 | Dispatch table and native execution |
| Shared command 77 parameter | low overlay 7 | 0919 | Dispatch table and native execution |
| PCM state selector | resident 5 | 5b17 | Native execution, stopping at tail target 112b |
| Initial capability-copy fragment | overlay 6 | 1dc9 | Native execution, stopping before call 088d |
| Batch scrambler | low overlay 7 | 0890 | C/native/scalar recurrence agreement |
| Batch descrambler | low overlay 7 | 08b0 | C/native/scalar recurrence agreement |
| Fixed-GPC training generator | PCM overlay 8 | 6421 | C/native/scalar recurrence agreement |
| Peer qualification fragment | low overlay 7 | 0e4f | Native execution through 0e68 |
| Negotiation cleanup fragment | low overlay 7 | 09a0 | Native execution through 09a7 |

We also lifted the mailbox dispatcher. But we did not do an independent
execution test of it as a C equivalent.

The lift of the peer qualification keeps the raw bit meanings: if bit 12 of peer word
`[7f00]` is clear, the routine sets bit 8 of `[7fe8]`. A rate-dependent margin
`4a00 - ((peer << 5) & 0f00) - signed([7f26])` sets bit 14. We do not give
unverified proprietary x2 labels to those fields.

The parallel [server bundle](../x2-server-decomp-20261004/README.md) now
reconstructs the capability writer and the sample transforms of the pre-V.90 I-modem,
with separate shared x2/V.90 Quad PCM helpers.

## What the code says

Command 70 applies:

```c
capability = (host_argument | 0x4000) & 0x7fff;
pcm_flags = 0x8000;
pcm_status |= 1;
```

The batch scrambler is shared V.34/PCM machinery. Bit 0 of data `[006f]` selects GPC
`1 + x^-18 + x^-23` or GPA `1 + x^-5 + x^-23`.
The receiver selects the opposite recurrence from bit 1. The C lift uses
an equivalent implementation that does one bit at a time. It does not use the original batched
fixed-point operations. The tests cover widths 1..9, the two roles, and random
23-bit histories.

The training generator at `6421..6432` is the same 18-word body as
`ed2e..ed3f` of the x2-only build and `f938..f949` of the 4.03 build. Its caller
at `63f8..6400` explicitly requests six scrambled-one bits with the mask `003f`.
This proves that the PCM training machinery of the x2 era is still present. It does not give
the proprietary name of that wire sequence, and it does not show the difference between each x2 call
and V.90.

This is the source of the transmitted capability. The supervisor sends the plain
base word as tag `51` (handler `08e3`, stored at `[7fec]`), and the word with the x2 edits
as tag `70` (handler `08f8`, stored at `[7feb]`). The negotiation start
(`09a9`, `0a04`, `0a58`) calls `0a64`. This routine reads **only `[7fec]`**, applies
`| 4000 & 7fff`, and pushes the result as a 16-bit field into the INFO0 bit queue at
`7f18` through `14b8`. (The stored value is the word shifted right one time, with
its low bit in bit 15 of `[7f19]`.) The 3453C has no equivalent of the choice
of the I-modem between two words with bit 6. Also, no code in the four images reads `[7feb]`.
We checked direct addresses, page-relative addresses and addresses made from pointers.
Thus, command 70 only sets bit 15 of `[7fe8]` and bit 0 of `[7fee]`.
In this build, its x2 asymmetry and its CME edits never get to the wire. The
entry of overlay 6 at `1dc9` also seeds its buffers from `[7fec]`.

## Verification

From the root of the repository:

```sh
.venv/bin/python tools/recover_3453c_x2.py
```

The verifier must have the native DSP emulator of the repository and `clang`. The verifier
compiles the actual C file into a temporary shared library. Then it compares it
with the original firmware instructions. All **1,793 cases passed**:

- 1,152 scrambler/descrambler cases.
- 256 training-generator cases, which include 768 continuous bits from zero state.
- 12 command-70 cases, which include the preservation of the existing status bits.
- 20 adjacent mailbox-handler cases.
- Six state-selector cases and three initial-capability fragment cases.
- 256 peer-qualification and 64 negotiation-cleanup cases.
- 24 INFO0 capability-queue cases: the output depends only on `[7fec]`.

The verifier does not access modem hardware. These are isolated routine checks. They are not a
complete simulation of an x2 call. More reconstruction is necessary for these items: peer recognition, the proprietary modulation
parameters, PCM mapping, and the complete training state machine.
