# C5x delayed-call/block-repeat repair and V.90 recovery (2026-11-02)

**Latest:** a separate [finite-bank scheduling repair](analog-sip-v90-data-banks-20261103.md)
now has independently confirmed **7900 V.90/LAPM/V42BIS at 50666**, with a readable
menu, in the opt-in level-conversion experiment. Sustained exact payload,
default-gain operation, and 7910 V.90 remain unqualified. This does not turn the
offline MP results below into live carrier evidence; the new call is separate.

**Original status: an emulator defect is fixed and verified offline. Live V.90 CONNECT and
sustained duplex payload are not yet qualified.** The first live retry was
skipped for an unrelated call. A later [7910 PPP test series](analog-sip-7910-ppp-20261102.md)
achieved PAP/IPCP and exact peer/internet payload at **31200 V.34**, but
V.90 still fell back. Native MP recovery is not an end-to-end V.90 repair claim.

## Defect

Courier 4.03 compacts its PCM constellation tables with this real DSP sequence:

```
f300 RPTB f306
f302 RORB
f303 CCD f30e, C
f305 MAR *-, AR5       ; first delay word
f306 MAR *-, AR4       ; second delay word, also block end
```

The helper copies a selected constellation point. There are 32 mask-bit
iterations. A taken delayed call must return to the next repeated iteration
while BRCR is positive, and to the linear continuation after the final one.

The native core already redirects sequential fetch to PASR when the last
block word is fetched. However, CALAD, CALLD and CCD always pushed the linear
`PC + 2` before executing their delay words. Here that saved `f307`, even
though fetching `f306` redirected the sequential PC to `f302`. RET therefore
left the repeat loop prematurely after its first selected bit.

For the nine-point training constellation, the resulting positive table was:

```
-1, -1, -1, -1, -1, -1, 902, 904, 337
```

The six invalid entries were then used as actual training targets, including
near-zero targets for large received samples. The equalizer adapted toward
a DC/decision-feedback collapse. This accounts for the previously observed
constant pre-descrambler word; changing MP CRC acceptance could not fix it.

## Repair and instruction tests

`native/c5x_ops.ipp` now uses `delayed_call_return_pc()` for all three delayed
call forms. When their two delay words finish an active repeated block and
BRCR is positive, the saved return address is PASR. Otherwise it remains the
linear continuation. The stack push still occurs before the delay words;
instruction timing, repeat counts, IRQ recognition and firmware are unchanged.
The helper is declared in `native/c5x_core.h`.

`tests/test_c5x_delayed_call_repeat.py` contains 40 tests covering:

* CALAD, CALLD and taken CCD;
* final and non-final repeat iterations;
* two one-word slots and one two-word slot;
* a call whose slots end the block and a call with a further body instruction;
* the actual RORB/CCD/delay-word pattern, with zero, single and multiple selected
  mask bits, checking that every selected bit reaches the helper.

Before the repair, the initial 18-test matrix had **12 failures**, each
executing the helper only once instead of twice or four times. After the
repair, all **40 tests pass locally and on Linux in the isolated vmhost
snapshot**. The larger local focused selection completed **202 passed,
1 skipped**; this is not a full-suite result.

## Offline receiver evidence

The same recorded RX input was replayed before and after the repair. This
remains open loop: the regenerated TX differs from the original recording,
so it is not a substitute for a new call.

After repair the positive and negative nine-entry tables agree:

```
6295, 5554, 4814, 4073, 3271, 2530, 1820, 1080, 362
```

At training-reference entry `eae0`, `030b` contains the preceding sample's
training error. Over retained records:

| Training records | Before: error RMS | After: error RMS |
| --- | ---: | ---: |
| 1–99 | 8253.13 | 137.25 |
| 100–499 | 5536.88 | 57.83 |
| 1000–2027 | 1048.18 | 22.64 |

Over the final interval, repaired signal RMS is 7713.65, rather than the
1180.78 of the collapsing original. These statistics describe the retained
2028 records, not a general guarantee about capture-ring loss.

At pre-descrambler PC `8ce8`, mode `0843`, the repaired replay captures 3435
eight-bit chunks spanning all 256 values, with sample standard deviation
7800.52. The original captured stream was `00,7e,03` repeated 4386 times.

An independent bit-level check of those native receiver chunks, LSB first,
using the `1 + x^-18 + x^-23` receive descrambler and strict reflected CRC,
recovers **143 valid type-1 MP frames**:

* maximum DRN 13; rate mask `0fff`;
* acknowledgments 0 and 1;
* CRCs `5018` and `1710`, respectively;
* precoder `(965,-95), (-634,6), (492,137)`.

Those parameters match the independent digital-RTP decoder. The same checker
finds **zero** valid MP frames in the original constant-output replay. This
is recovery through the native DSP receive path, not merely a decoder finding
information upstream of the emulator. It is still training/control evidence,
not a carrier or payload claim.

## Two earlier analysis ambiguities resolved

The upstream CPt waveform **can** be decoded. It is differential QPSK at
3200 baud with carrier 1828.5714 Hz, not the earlier attempted 16-point demap.
Searching timing, differential mapping and descrambling recovers **51 strict
CPt/CP frames** from the original latency-call TX WAV. The actual live CPt
has **one constellation, 292 bits**, DRN 16, D24/K19/Sr1, L3/a1=1, A-law,
DFI `000000`, codec-differ 0, mask:

```
89, 86, 83, 80, 74, 68, 61, 49, 23
```

This is not the three-constellation CPt reconstructed from the open-loop
replay. Feeding the **actual live CPt** to the private Phase-4 tap yields
24089 initial consecutive TRN2d one bits, rather than the earlier 457, and
recovers the same MP parameters. The extended interval still reports 1063
modulus errors and must not be treated as conformance of later transitions.

The first TRN2d RTP sample is index **153184**. Its first constellation indices
are `2,4,7,1,5,4`, agreeing with the independent recurrence and native reference.
Cross-correlation using nonperiodic windows establishes a **1120-sample** RX
WAV-minus-RTP offset and RX gain about 0.5242. The earlier 14122-sample match
was ambiguous within the repeating DIL waveform: it differs by one
13002-sample period. It must not be used to infer a 1.6-second training
misalignment. Windows at WAV 40000, 60000, 160000, 176000 and 184000 all give
1120, with residual RMS below 0.27 sample units.

## Evidence and remaining qualification

* `.artifact-archives/analog-v90-delayed-call-repeat-20261102/`: scripts,
  local test output, repaired PCM summary and before/after native MP checks.
* `.artifact-archives/analog-v90-offline-failure-20261102/`: `train-banks-*`,
  `fixed-train-banks-*`, and `fixed-raw-rx-*` traces/reports.
* Original latency archive: `7900-cp4-all.bits`, `7900-cp4-analysis.txt`,
  `7900-live-cpt.bits`, and `7900-live-cpt-phase4.txt`.

The native repair and regression test are deployed only to
`/root/courier-sip-20261102-113720`; existing vmhost installation and PBX/peer
configuration are untouched. No speculative level-conversion, memory-map,
clock or CRC changes were adopted with this fix.

Later bounded 7910 calls demonstrated PPP login and exact peer/internet ICMP
payload, but still connected at V.34. See the PPP report for complete tests,
failed loaded tests and the separate active-input scheduling repair. V.90
CONNECT and sustained duplex qualification remain outstanding.
