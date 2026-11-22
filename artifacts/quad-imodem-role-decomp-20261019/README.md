# Quad / I-modem x2 role decompilation

The server-to-server explanation is consistent with the recovered code:
the I-modem can change its advertised role while both tested paths still
arm marker receivers. A client-side marker sender has not been identified
on that path. No working x2/V.34 digital pair is established.

## Actual Ie030002 S58 builder

S58 is at supervisor `2600:d1b5`. The original instructions at
`b27fd..b2833`, after the common V.34 capability builder, reduce to:

```c
word = (v34_capability & 0xf9ff) | 0x1800;
if (s58 & 0x04) word |= 0x0200;  // A-law
if (s58 & 0x10) word |= 0x0400;  // constellation option
if (s58 & 0x02) word &= ~0x1000; // disable advertised server capability
if (s58 & 0x08) word &= ~0x0800; // disable advertised symmetric capability
send_to_dsp(0x70, word);
```

The earlier eligibility routine checks x2-disable bit `01`; the later
V.90 eligibility routine checks bit `20`. Neither unnamed upper S58 bit
changes this role word. The bounded original-instruction test exercises
all 256 S58 values with common V.34 input `21ff`:

| S58 | Tag 70 | Requested availability |
| --- | --- | --- |
| 48 | `3dff` | server + symmetric |
| 50 | `2dff` | symmetric; server disabled |
| 56 | `35ff` | server; symmetric disabled |
| 58 | `25ff` | server + symmetric disabled; constellation option set |
| 42 | `21ff` | server + symmetric disabled; constellation option clear |

This confirms that S58=58 was already clearing the two relevant advertised
capabilities. S58=42 is the corresponding lower-power control.

`s58-builder.asm` is the original supervisor code. The actual Ie030002
resident host-command table starts at **88d5**, not the older IM020104
882b table: its tag 70 entry is **926d**. `tag70-handler.asm` shows that
handler masking/storing the capability word in **ffdc** and updating
companding/reversal state; it does not directly select a client datapump.

## Why advertisement does not settle implementation

The original INFO0 gate at `9596..95ef` tests peer 3200/high capability,
the two symmetric bits, and XOR of the CME role bits. Eight native
contexts (four peer configurations, both call-role values) produce:

| Local / remote INFO0 roles | Branch |
| --- | --- |
| client / server | `95ca`, asymmetric receiver setup |
| server / client | `95ca`, the same setup |
| server / server | `965c`, drop x2 |
| both symmetric | `958f`, symmetric setup |

After `95ca`, **95e3/95e4 arms the seven-bit INFO receiver**, via `93de`.
There is no branch on which side has CME set in this continuation. Quad's
corresponding server continuation arms its seven-bit receiver at
`9790/9791`. This explains why clearing a capability bit alone is not proof
of a complete client implementation. It is consistent with both digital
datapumps awaiting a client marker in the live control; it does not prove
that every possible client-side path elsewhere in the image is absent.

### Scheduled receiver and fallback boundary, 19 October continuation

The original instructions have now been executed past that gate for both
INFO0 orientations and both originate/answer roles. `8cbb` is a scheduler
yield: it POPs the CALL return address into callback cell `006d` and returns
to the outer caller. First it installs `95dd` (delay 96 for originate, zero
for answer). The next callback installs tone generator `9e9e`, seven-bit
receiver length `0322=7`, buffer `0324=f6a8`, then yields to `95ed`.
Neither setup changes transmit-script cell `03cb`. Classifier `039f`
remains set at this boundary. `asymmetric_setup_cases` records four native
executions, with a sentinel identifying any transmit-script replacement.

The wait callback calls `96be`. That routine compares counter `031a` with
`bb80` (48000). Until the counter exceeds that threshold it POPs return
address `95ef`, adds two, and branches to `95f1`, skipping the two-word
fallback branch. Above the threshold it returns normally to `95ef`, which
branches to recovery `92e2`. `asymmetric_wait_cases` executes the original
instructions on both sides of that boundary, including equality.
Linear disassembly that treats `8cbb` or `96be` as normal returning
functions gives an incorrect immediate-fallback interpretation.

The fresh actual Quad/I-modem call in
`../quad-imodem-classifier-trace-20261019` records classifier transitions
`0042 -> 1442 -> 1462 -> 0062`. It enters the INFO0 gate with `1462`, then
clears the x2 bits through APL at `92ef` (trace PC `92f0`, its second word).
Both ends connect at 33600/V34/LAPM and exchange both markers; the strict
x2 assertion fails. This establishes successful initial classification
followed by the original recovery path, rather than an initial classifier
failure. `classifier-analysis.json` retains the exact DSP instruction
indices and the source trace location.

This further supports a missing client sender on the selected path; it
does not justify patching the fallback gate, classifier bits, or received
marker. The analog Courier supplies a working sender, but it is not the
requested I-modem. A complete digital client implementation is still not
established.

## Live register controls

`live-controls.json` retains both actual tests:

| I-modem S58 / Quad S76 | Result |
| --- | --- |
| 58 / 133 | Both 33600/V34/LAPM; both payloads intact; x2 rejected |
| 42 / 5 | Same fallback and payload result; x2 rejected |
| 56 / 134 | Reverse roles: both 33600/V34/LAPM; both payloads intact; no Quad tag 70 |

The first two have Quad x2 status `8954=00`, `895f=013f`. The original live reports
and DSP snapshots remain in their linked capture directories. The later
caller NO CARRIER occurs after the bounded Quad worker exits.

The reversed control is saved in `../quad-imodem-reversed-roles-20261019`.
Its actual digital configuration `a87e=20h` takes the original supervisor
gate `c913d..c914d`: with `(S76 & 6) == 6`, it skips the tag-70 builder,
even when S76's client-disable bit is clear. The original exchange log
confirms no tag 70 was sent. This rules out that straightforward role
reversal as a way to select a digital Quad client.

## Reproduce the decompilation checks

```sh
PYTHONPATH=. .venv/bin/python tools/decompile_imodem_roles.py \
  --output /tmp/imodem-role-decomp
.venv/bin/python -m pytest -q tests/test_imodem_x2_roles.py
```

`verification.json` contains the image hash, all 256 original supervisor
executions, eight native DSP gates, four scheduled asymmetric setups and
five wait-boundary executions. The focused role,
pair-verification and analog-control selection passes **49 tests**.
These are bounded semantic checks, not a working mixed-mode digital call.
