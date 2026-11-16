# QF060003 57333 PCM profile

The local constructor for rate index 15 supplies B=37. With MD=6, this
allocation uses 43 bits for each six samples. At the sample rate of 8000/s, this is 57333⅓ bit/s.
This is a seeded reconstruction of the component. It is not a captured
57333 connection or a recovered record of the peer negotiation.

## Mapping

The source appender B2BA scrambles the source bytes with the
GPC (1+x^-18+x^-23) or GPA (1+x^-5+x^-23) recurrence, as the role selects. It appends them
LSB first to the 128-bit ring. C5DF uses six sign bits and then a
37-bit amplitude integer X. In the default context (mode zero, zero record),
the six radices in emission order are **82,70,70,70,70,70**.

For each position, digit=X modulo radix; X=floor(X/radix). The digit
selects an entry in the bank of that position at E8F4+128*i. In the tested bank, the low seven bits
identify the magnitude uniquely. The bank product is
137817400000, which is more than 2^37=137438953472. The code makes only amplitude integers
0..2^37-1. The surplus mixed-radix tuples are not used.

C642 changes the six independent sign bits into successive differential
parities and toggles codeword bit 7. With MD=6, there are no free signs for
disparity shaping. The continuous original C544 dispatcher sends the six
codewords and applies the selected output XOR. Exact-symbol reception
removes that XOR, finds the bank digits and reconstructs the amplitude integer.
Then it reverses the differential parity, assembles the frame bits again across byte boundaries
and descrambles them.

## Builder setup and variants

**The constructor must execute with SPM 1.** Its C72D/C74E/C761 scaling
uses MPY/PAC product transfers. Earlier SPM 0 probes made duplicates
or did not return. These new results replace those results. The original overlay
also restores SPM 1 at C40C before it returns to the resident code. This is
supporting evidence about the calling convention. It is not a captured index-15 call.

The scan seeds 0340=mode<<11, E8F2=0600, FFD9=flags, 039F=0040,
03FB=1. A nonzero position is a record nibble of two. The active positions
are the first one or two. Zero positions start the default
record behavior of the builder. FFD9 bit 12 and 039F bit 7 stay clear.

| Mode | FFD9 bit 2 | Active positions | Emission-order radices |
| --- | --- | --- | --- |
| 0 or 2 | 0 | 0 | 82,70,70,70,70,70 |
| 0 or 2 | 0 | 1 | 45,79,79,79,79,79 |
| 0 or 2 | 1 | 0 | 72,72,72,72,72,72 |
| 0 or 2 | 1 | 1 | 48,78,78,78,78,78 |
| 0 or 2 | 1 | 2 | 49,49,87,87,87,87 |
| 1 | 0 or 1 | 0 | 72,72,72,72,72,72 |
| 1 | 1 | 1 | 42,80,80,80,80,80 |
| 1 | 1 | 2 | 46,46,90,90,90,90 |

The two tested states of FFD9 bit zero pass for each valid row. The mode has an effect on the
scaling and on the actual bank contents, also where the radices are the same. Full bank
snapshots are in profile-MODE-FLAGS-ACTIVE.json. The other forced combinations
in this scan do not have sufficient capacity, because not all descriptor rows extend
to index 15. A successful seeded construction does not show that
peers negotiate that combination.

## Reproduction and checks

Run these commands with the Python environment of the repository:

```
.venv/bin/python tools/probe_x2_57333_profile.py
.venv/bin/python tools/recover_x2_payload.py
```

The dedicated scan validates 28 of 36 contexts. Each valid context has 64
comparisons of the original DSP mapping with the ideal inverse. These include all-zero and
maximal 43-bit groups, random ring offsets and differential parity states.
The total is **1792 exact-symbol round trips**. search-spm1.json records all cases.
verification.json gives the scope. builder.asm keeps the disassembly.
search.json, search-override.json and mode1-builder-trace.json keep the
old SPM 0 investigation results for provenance.

The wider corrected harness builds all fifteen indices with SPM 1. It
checks 840 firmware-bank/inverse cases and 1260 sample steps of the continuous dispatcher.
Its 56 streams of 32 frames cover indices 10 and 15, MD=0..6,
the two scrambler role flags and the two output format states. It validates
10752 continuous samples and recovers 8400 source bytes. Index 15/MD=6
is included. The other MD choices at index 15 are arithmetic tests of the component.
They are not more established negotiated rates.

These items are still open: the actual selection of the peer rate/record, a full 57333 connection,
the acquisition/equalization of the analogue receiver and symmetric lower-rate calls.
