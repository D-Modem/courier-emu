# Six-symbol PCM payload reconstruction

The larger C300 overlay in QF060003 now has a verified path from source byte
to codeword. The manual C lift agrees with the original DSP instructions. An
ideal inverse in the symbol domain recovers the source bytes over continuous
streams.

This is a bounded reconstruction of the PCM core. These items are still not
verified: the supervisor edge that selects this core during a complete x2
connection, the analogue receiver/equalizer, and the complete peer
negotiation. The smaller C300 overlay is a different filter implementation. Do
not mix its instructions with this core.

## Payload rule

A frame consumes MD independent sign bits, then B amplitude bits, least
significant bit first. MD is 0 through 6. The configured rate table contains
B values 19 through 37. Let X be the amplitude integer and m[i] the six bank
sizes. In emission order, digit[i] = X modulo m[i], then X = floor(X / m[i]).
The selected bank entry supplies an octet, a level index and a reference sign.
A valid allocation must have product(m) >= 2^B, and the low-seven codeword
bits in each selected bank must be uniquely identifiable.

Input sign bits update a continuous XOR parity state. For MD below six, the
positions rank by level index, descending. If two positions have the same
level, the earlier position comes first. The top MD positions carry
independent parity toggles, assigned in emission order. An exhaustive search
for the minimum absolute running disparity selects all other toggles. The
search visits free-sign masks in descending sequence. If scores are equal, it
keeps the largest mask. The search includes eight times the signed delayed
monitor value. At MD six, all toggles carry parity bits, and no search is
necessary.

Sign toggles XOR bit seven of the reference octet. The usual output path
sends the octet XOR the configured final format mask (0 or 0x2A in these
tests). It also updates the linear sample history, the delayed disparity, the
energy and the scaled output samples. This lift covers local 039F bit 7 clear
and FFD9 bit 12 clear, with the monitor coefficients of the builder and PM=1
for sample processing. We have not lifted the alternate companding override.

## Source and inverse

B2BA calls the role-selected scrambler at 921B and adds 1 to 8 bits to the
128-bit ring. C5DF reads that same ring. C642 applies differential signs and
shaping. C544 dispatches the six sample steps and calls the two stages. C544
tests the ring availability on each sample. It requests source data unless
the count is strictly greater than B+MD. Continuous tests fill the ring
before, with sufficient data for this condition to stay true after the
current frame is consumed. Source callbacks and serial queue delivery are
outside the harness.

The ideal inverse reverses the final mask and finds each unique bank digit and
reference-relative sign. It reconstructs X. Then it recovers the independent
bits from successive parity values. The frame bits are assembled into bytes
across boundaries and descrambled with continuous history. This inverse
assumes exact received octets and a known frame alignment. It is not a
decompilation of the client DSP.

## Verification

From the repository root, run `python3 tools/recover_x2_payload.py` with the
Python environment of the repository. It compiles `payload_lift.c` with clang.
It compares the memory effects with NativeC5x, which executes the original
firmware at the stock placement. The fixed random seed is 0xC5DF. The reports
are generated again only when all checks pass.

| Check | Coverage |
| --- | ---: |
| Amplitude extraction and mixed-radix selection | 512 cases |
| Differential signs and disparity search | 1,024 cases |
| Source scrambling and ring append | 1,024 cases |
| Firmware banks and ideal frame inverse | 840 cases |
| Continuous original dispatcher sample steps | 1,260 samples |
| Continuous byte streams | 56 streams of 32 frames |
| Samples in those streams | 10,752 samples |
| Original bytes recovered | 8,400 bytes |

The total of 15,468 adds check units of different types. It is not a count
of independent connection trials. The 30 constructed builder profiles cover
rate indices 1 through 15 with flags 0 and 1. The mode is zero for all
fifteen indices. Builders execute with **SPM 1**. These results replace the
prior constructor results with SPM 0. Continuous byte streams use indices 10
and 15. They test all MD values, the two source-role flags and the two final
format states. Index 15 at MD=6 is the 43-bit/6-sample 57333 profile.

Refer to `../x2-57333-profile-20261004/README.md` for the profile variants and
1792 more exact-symbol round trips. These seeded profiles do not show an
actual negotiated 57333 connection.

`example.json` records the first MD=3 frames of the index-10 and index-15
streams. Its source lists include the prefetch after the first frame.
`verification.json` gives the profile sizes, the SPM context and the full
check counts.

All 28 full-length comparisons of the overlay copies of the stock controller
established the source placement independently. Refer to the placement report
in `../x2-mapper-negotiation-20261004/placement-verification.json`.
