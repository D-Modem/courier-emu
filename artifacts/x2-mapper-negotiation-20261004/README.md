# Verified Quad PCM placement and six-position preparation

The stock QF060003 controller solves the former conditional placement.
The seven flat offsets of the overlays were two bytes too early. The offset of the resident
was correct. The downloader does not omit a leading word. A fresh run of
8,000,000 controller instructions gives all seven source copies again in all
four modem RAM banks. All 28 complete byte comparisons pass.
`placement-verification.json` records the offsets, the lengths and the SHA256 values.
To do this again, run `.venv/bin/python tools/verify_quad_pcm_placement.py`.

We corrected the reusable map in `tools/probe_quad_pcm_codewords.py`. We generated the
reconstruction of the server helper again, and it passed its 6,562 cases.
The old extra leading codeword and the EF00 selector output were artifacts of the extraction.
They were not valid mapping parameters.

## Received parameters and position controls

The original instructions and the manual C agree in **13,504 cases**. There are also
**128 integrated original-instruction contexts**:

| Check | Cases | Scope |
| --- | ---: | --- |
| C6E5 nonzero six-position count | 4,096 | Every 12-bit control word |
| C6F4 size distribution | 4,096 | Zero selects high byte, nonzero low byte |
| C92A descriptor expansion | 192 | Seeded candidate lengths and contents |
| C870 parameter unpacking | 512 | Random working records and flags |
| AB06 received-record transfer | 512 | TC set at entry; stops at AB2E |
| Received record to six banks | 4,096 | Every control combination; supplied candidates |
| C840 startup caller through C4AB | 128 | Original constructor, conversion and expansion |

In the tested PCM branch, AB06 transfers FF48/FF49 to 0340/0341 and FF4A/FF4B to E8F1/E8F2.
C870 uses six four-bit cells from the low
24 bits of the second pair, high cell first. The low three bits of each cell
index `[0,1,2,1,0,3,0,3]`. The routine ignores the high bit of the cell. The results make six
two-bit controls. The last decoded cell supplies the least significant
control. The bank expansion uses this control first. This is the order of the working record.
It is not a known serialization on the wire.

The routine stores bits 8..10 of E8F2 separately. The mode comes from bits
11..14 of 0340. Bit 12 of FFD9 can force the stored mode to zero, but one scale lookup
keeps the original mode. The meaning and the units are not known. When all
controls are zero, the routine uses control word 0002 in their place, and it keeps the active
count at zero. The C lift keeps that default state.

C92A expands the banks at E8F4, E974, E9F4, EA74, EAF4, EB74. It selects source
0A60 for control zero or 0880 for a nonzero control. An odd control ORs 0100 into
each copied entry. The stored copy counts are last indices: 3 copies 4 words.
The physical meaning of the flag is not known.

## Constructor and its callers

C9BF selects one nine-word constructor table with bit 2 of FFD9:

```
A5 A7 AD AF B7 BD C5 CF E5
95 97 9D 9F A7 AD B5 BF D5
```

These are alternative constructor tables. They are not necessarily the two
candidate sets that C92A uses. The difference of hexadecimal 10 is a
codeword difference. It is not a verified amplitude ratio or companding law.

The 128 integrated contexts run the unmodified C840 caller, C9BF, C920,
C761/C777 and C92A until C4AB. They seed the second candidate, the extra entries of the
ninth index, the level indices and the levels. The checks show that the constructor keeps the low
byte, that there are six size slots of 9, and that the final bank selection/flags are correct.
They do not lift the intermediate level converter independently.
C761 processes nine entries, while C92A copies ten with count 9. The initialization of the
extra entry in the full call, and its purpose, are not known.

The 4,096 cases of the received-record pipeline execute transfer, unpacking and
expansion in sequence with candidates that we built before. They intentionally skip
the negotiated candidate builder between these steps. We do not claim a complete negotiated
connection, payload mapper, alignment waveform, PCM law or receiver inverse.

To generate the listing and the report again, run `.venv/bin/python tools/recover_x2_mapper.py`.
The tests use the corrected full overlay bytes, and they do not change the
original program instructions. The negotiation framing and the historical correction of the
preamble detector stay in `docs/x2-v90-protocol-selection.md`.
