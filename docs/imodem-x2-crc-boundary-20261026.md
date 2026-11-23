# I-modem receive-error boundary and V.34 controls, 26 October 2026

## Latest follow-up

The [2026-10-27 DSP boundary and S39 investigation](imodem-x2-s39-headroom-20261027.md)
locates malformed incoming bits before DSP deframing and identifies the captured
analog profile's invalid S39=0 transmit level. Setting S39=8 via AT removes the
observed upstream BLERs in four bounded calls. One 20-second x2 duplex gate passes,
but a 60-second run still stalls downstream; sustained x2 is not qualified.
The [later downstream trace](imodem-x2-downstream-output-boundary-20261027.md)
finds an FCS-valid analog frame shortened at the DSP's host-bank output, with
finite lanes full in a repeat. One later S39=8 call has a residual upstream
BLER, so the earlier four clean calls are not a universal zero-error claim.

The [analog UART starvation correction](imodem-v34-uart-starvation-fix-20261026.md)
now passes repeated 20-second 512-byte V.34 controls and a 60-second fixed-14400
V.34 control, with zero UART overruns or link errors. The separate x2 receive
CRC failure remains. The sections below retain the pre-fix diagnosis and
controls; their zero-BLER V.34 large-record failure is no longer current.

## Result

The [first-gap investigation](imodem-x2-first-stall-20261026.md) now reaches
the original firmware's receive-rejection and BLER update paths. In the final
instrumented x2 call, the first rejection occurs at line frame **390**, shortly
after CONNECT and five seconds before the first complete-record gap at frame
440. Eight bounded rejected-frame captures reproduce the firmware CRC register
exactly with an independent reflected CCITT implementation; none has the good
HDLC residue `f0b8`.

This is **not a fix**, and does not yet distinguish bad datapump bits from bad
bitstream transport or deframing/destuffing. It does establish that the sampled
errors precede record pacing and are not simply an erroneous ATI6 formatter or
CRC arithmetic mismatch on the stored bytes.

A separate fixed **14400/V.34/LAPM** control with 32-byte payloads **passes the
20-second duplex traffic gate**, with no observed pending-error flag writes,
BLERs, retransmissions, or link timeouts. However, 512-byte controls at fixed
14400 and automatic 21600 both fail the unchanged five-second record-gap gate
**without any BLERs**. There are at least two distinguishable symptoms; it would
be wrong to attribute every slow record to CRC rejection.

## Original firmware chain

The observer is tied to instruction signatures in unchanged `Ie030002.nac`.
The normal data segment at the observed sites is `2600`.

1. The ATI6 compressed diagnostic template contains `Blers` followed by field
   selector `1f`. The formatter at physical `c0ef9..c0f79` decrements the selector,
   subtracts `10`, multiplies by four and adds `d0d8`. The counter is therefore
   `2600:d110`, physical **`33110`**, a 32-bit integer.
2. At **`a9877..a9897`**, the periodic service exchanges zero with byte `d0b5`.
   If its former value is nonzero, **`a9881`** adds one to `d110`, with carry into
   `d112`. The pending-error flag is physical **`330b5`**.
3. The receive reject handlers write one to the pending flag at **`b4c8a`**
   and **`b4cb2`**. The latter uses the alternate `0080..00ff` receive ring;
   the former uses `8d00..beff`. They also increment a saturating byte at `ca66`.
4. The HDLC close path at **`b5255..b529b`** rejects short frames or a CRC
   register (`cf2e`) different from **`f0b8`**. It calls the reject handler at
   `b5298`, leaving near return offset `150b` on the `b3d9` code-segment stack
   (physical return `b529b`). This return appears in the captured pending-error
   events.

The pending flag is a latch. Multiple rejects before the periodic exchange
coalesce into one BLER increment. **The ATI6 BLER counter is not an exact
per-rejected-frame count.**

The independent CRC starts at `ffff`, consumes each byte least-significant bit
first with polynomial `8408`, and leaves the raw register uncomplemented. A full
frame including valid transmitted FCS has residue `f0b8`. Tests include the
`123456789` check value and a good full-frame residue.

## Observer implementation and limits

`tools/probe_imodem_analog_pair.py --trace-link-errors` installs
`tools/imodem_link_errors.py`'s read-only memory-write hooks. The observer:

- Verifies original code signatures before installing either hook; other
  firmware fails closed.
- Uses the active CPU backend's own hook/register constants, including the
  default native-backed interpreter, rather than assuming Unicorn's constants.
- Captures at most four events per phase and kind, while counting all observed
  pending-error assertions and BLER increments (including a low-word wrap).
  Phases are pre-traffic, traffic, and post-window; traffic begins once both
  CONNECTs have reached the traffic driver.
- Saves original registers, the return stack, receive ring/pointers, CRC and
  handler state, DSP lane statistics, and native clock/handshake counters.
- Preserves ring wrap. The alternate reject branch clears `cf32` before setting
  the error flag, so **the checked writer PC** selects its ring, not that already
  cleared flag.
- Normalizes the interpreter's post-decode IP back to the known five-byte
  writing instruction, recording both hook PC and verified writer PC. The
  interpreter's own `cpu_retired` is retained alongside the most recently
  synchronized board instruction counter.

It neither patches firmware nor changes acceptance, input, timing defaults,
ACKs or carrier state. Sparse Python callbacks still add observation overhead;
these calls do not establish a statistically identical error rate to an
uninstrumented run. `link-errors.json` and `imodem.link_errors` in `result.json`
contain the same report. The final counter is sampled later than printed ATI6,
so equality with ATI6 is not required while the call continues.

## Qualified x2 receive-rejection capture

Evidence: `artifacts/imodem-x2-first-crc-20261026-212243/`.

The unchanged 20-second, 512-byte-payload x2 test fails, exits 1, and finishes
in 48.82 host seconds. At final drain the upstream receiver has zero complete
records and 296 partial bytes; the downstream receiver has 14 complete records.

The four earliest saved traffic rejections are:

| Line frame (100-ms ticks) | Writer | Ring bytes including received FCS | Firmware / independently recomputed CRC |
| --- | --- | --- | --- |
| 390 | `b4c8a` | `6034beb6d9acf2` | `d49f` |
| 390 | `b4cb2` | `062219a0c0beec9c63ca16448c17c2` | `b5e2` |
| 391 | `b4c8a` | `121bc079c2b6` | `bf82` |
| 391 | `b4c8a` | `a0e81e0418f883fb` | `289f` |

The four saved post-window rejects also independently reproduce their firmware
CRC registers. All eight differ from `f0b8`. At the first rejection, native
occupied-bank-write and torn-word counters are zero. This does not prove those
lanes carry the right bits or that deframing is correct.

Observed counts are 774 traffic pending-error writes and 209 traffic BLER
increments, plus 151 pending writes and 43 increments after the window. Final
BLER count is 252; ATI6 printed 249 earlier. No inference of counter corruption
is made from the three later increments.

## V.34 controls

All use the same saved I-modem profile, native runtime, 20-ms line frames,
20-second requested window, original firmware, compression disabled, and the
same observer. Only these controls, not the x2 run above, use V.34-only
`S58=33` on both peers. The five-second record-gap limit remains unchanged.

| Evidence directory suffix | Mode | Payload | Upstream records at final drain | Downstream records at final drain | Traffic gate | Reported BLER/resend/timeout |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `imodem-v34-crc-control-20261026-212709` | fixed 14400 | 32 | 44 | 125 | **PASS** | 0 / 0 / 0 |
| `imodem-v34-crc-14400-full-20261026-212859` | fixed 14400 | 512 | 2 | 24 | FAIL | 0 / 0 / 0 |
| `imodem-v34-crc-auto-full-20261026-213008` | auto, CONNECT 21600 | 512 | 2 | 25 | FAIL | 0 / 0 / 0 |

Directories are under `artifacts/`. All observed pending-error/BLER hook counts
are empty in these V.34 controls, consistent with the zero final counter and
ATI6. The successful small-record control has maximum upstream/downstream
complete-record gaps of 0.5/0.2 seconds. The fixed and automatic large-record
controls instead have maximum upstream gaps of 11.3/12.6 seconds. Both large
controls eventually deliver their two complete upstream records, without
corrupt-prefix reports; they still fail sustained acceptance. These are ASCII
record gates, not arbitrary-binary or maximum-throughput certification.

Each control has an active measured call, no I-modem PCM underruns or analog
connected receive-empty events, and no recorded UART overruns/drops. This is
not proof of correct UART service cadence. The next non-CRC investigation is
input-delivery/service timing and buffering on the analog DTE path.

To reproduce the passing small-record control, use the base command in the
[first-gap report](imodem-x2-first-stall-20261026.md), replacing its settings
and adding:

```sh
  --analog-settings 'S27=1S54=0&A3&B1Q0&K0' \
  --imodem-settings 'S54=0&A3&B1Q0&K0' \
  --protocol v34 --speed-index 8 --traffic-size 32 --trace-link-errors
```

Use payload 512 for the fixed-rate large-record control, and additionally
`--speed-index 0` for the automatic-rate one. Each evidence directory retains
its complete `command.json` and bounded process status. Run sequentially with
host CPU headroom.

## Excluded instrumentation pilots

Do not use these as first-CRC evidence:

- `imodem-x2-first-bler-20261026-211606`: initially used Unicorn constants with
  the default interpreter. Hooks missed all counter writes; the nonzero final
  counter exposed this observation defect. A native-interpreter regression now
  exercises actual flag/counter instructions and their hooks.
- `imodem-x2-first-bler-native-20261026-212024`: establishes flag/counter ordering,
  but its alternate-ring snapshots incorrectly selected the main ring after
  `cf32` had been cleared. The final CRC capture above fixes ring selection and
  verifies every saved rejection against its independent CRC.

## Verification

**141 targeted regressions pass**, including actual original flag/counter
instructions under both Unicorn and the native-backed interpreter, bounded
per-phase capture, alternate-ring selection/wrap, counter carry, firmware
signature checks, and replay of the eight saved CRC rejections.
`git diff --check` is clean.

A separate read-only verifier replays measured DTE prefixes and complete-record
hashes for all four final calls, checks their reported health and expected
pass/fail outcomes, and recomputes each saved rejection's CRC and caller return.
Its script, successful report and regression output are under private
`.artifact-archives/imodem-crc-verification-20261026/`. This preserves the small
V.34 control's success and the other three failures; none is promoted to a
larger-payload or longer-duration qualification. No owned local probe/worker
remained after the controls.

## Remaining work

1. Trace the first x2 upstream bits through DSP output, host holding words and
   deframing to determine where the rejected bytes first diverge. Correct CRC
   arithmetic on the stored bytes does not clear the deframer or the datapump.
2. Independently time analog DTE delivery versus firmware data output in the
   zero-BLER V.34 large-record control. Do not loosen the five-second criterion
   or call a 32-byte-record success a 512-byte success.
3. Recheck any fix against both controls before attempting a longer soak.
