# x2 upstream headroom and the remaining downstream stall, 2026-10-27

## Current result — partial correction, not sustained x2 qualification

The supplied analog 403 EEPROM restores **S39=0**, outside the original AT
parser's accepted range of **1..29**. Explicitly setting the factory transmit
level **S39=8 through AT** removes the observed upstream CRC failures in four
fresh bounded x2 calls. The ROM, captured EEPROM, instruction semantics, and
acceptance thresholds are unchanged.

One corrected call passes the existing **20-second, 512-byte ASCII duplex**
gate. Its analog CONNECT is **52000/x2**, not the earlier 53333 target. Three
other corrected calls still fail downstream delivery, including a **60-second
call** that receives only seven complete downstream records and then remains
stalled. **Sustained x2 reliability and the 53333-bps target remain unqualified.**

The previously qualified [V.34 UART fix](imodem-v34-uart-starvation-fix-20261026.md)
is unchanged. This investigation changes no CPU/DSP arithmetic or UART behavior.

A [later downstream boundary trace](imodem-x2-downstream-output-boundary-20261027.md)
finds FCS-valid analog input shortened at the DSP host-bank output, with finite
receive lanes full in a repeat. All six new x2 controls fail. One corrected
call also has one residual upstream BLER; the four clean calls here do not
establish universally error-free upstream reception.

## Receive boundary: corruption precedes both deframers

`--trace-link-errors` now snapshots bounded, already-emitted native DSP bank
history at the first rejection in each phase. `--trace-link-bits` additionally
arms the native 64-row capture at original resident instruction **9096** after
checking its instruction words. The coherent header contains ACC (the bits
about to be stored), DP, and the live bit count at **0322**. No instruction
hook in Python runs per bit, and no diagnostic advances the processor.

The qualified coherent capture is:

`artifacts/imodem-x2-coherent-bits-boundary-20261027-083514/`

At its first traffic rejection:

- The DSP's output bank words contain all **44 bytes** of the CPU's rejected
  ring, in the same order, followed by **FE00**, the DSP's error token.
- Independent flag recognition and bit unstuffing find a **350-bit** frame,
  which is not octet aligned. Its **43 complete octets** exactly match the
  receive-ring prefix. The firmware's final partial-octet flush is not guessed
  or represented as a valid received FCS by the independent decoder.
- The CPU ring CRC independently agrees with its original CRC register.

Thus the captured malformed frame already exists before DSP HDLC deframing,
mailbox holding words, and CPU rejection. This rules out repairing those
later stages as the cause of this event; it does not alone distinguish a
transmitter fault from a demodulator fault.

Replay without running either modem:

```sh
PYTHONPATH=. .venv/bin/python tools/imodem_receive_boundary.py \
  artifacts/imodem-x2-coherent-bits-boundary-20261027-083514/link-errors.json
```

An earlier single-cell **0320 write trace** also records several unrelated
scratch/HDLC writes. Treating every 9096 result as an eight-bit group without
coherently retaining its live count was insufficient evidence. The coherent
capture above supersedes that exploratory interpretation.

## S39: original power-control path, not a DSP patch

Earlier local waveform work in `../v90modem/docs/x2_v34_upstream_review.md`
identified signed output wrapping and traced the profile's S39 setting. That
was the lead, not a new discovery made by this observer. This investigation
independently checks the supplied 403 ROM and fresh analog/I-modem calls:

- Original supervisor **C9B1D** reads S39 at **0000:04B5** when the alternate
  local level selectors are inactive.
- **C9B24** reads the ROM gain table at **C9B50**. **C9B32** subtracts **0300**
  in this board configuration, then **C9B36..C9B39** posts host command **1A**.
- Table entries 0 and 8 are **32767** and **13014**, yielding runtime gains
  **31999 (7CFF)** and **12246 (2FD6)**.
- **CA2D3..CA2D9** exclude zero and values above 29 before the store to 04B5.
- Readback in the fresh matched upstream-rate calls confirms S39 **00/08**
  and DSP gain cells **0392/FFF0 = 7CFF/2FD6**, respectively. Both retain
  **B=78 bits per eight symbols at 3200 baud**, i.e. 31200 upstream.

The earlier waveform audit found that the original PM=1 multiply followed by
shifted SACH can wrap the output word at the excessive gain. Codec attenuation
is later and cannot undo that wrap. TI SPM/SACH semantics must not be changed
into saturation to conceal a bad local configuration. A post-codec bearer-gain
change also cannot restore an already wrapped word.

`--analog-tx-level 8` prepends `S39=8` to the normal analog AT settings. The
default is **stored**, preserving existing reproduction behavior and the
captured fixture. Later explicit `--analog-settings` take precedence, including
a deliberately supplied S39. The helper neither writes an EEPROM file nor
issues `AT&W`, `AT&F`, or direct guest-memory writes. No gain adjustment is
silently made to another board or a user's stored profile.

## Sequential fresh calls

All artifact names below are under `artifacts/`. U/D counts are complete
upstream/downstream records **inside the measured window**, not final drain.
All corrected calls have zero observed analog RX/TX overruns and an active
call at the window boundary. Zero I-modem BLER does not imply zero downstream
errors: retransmissions and timeouts remain in the failed calls.

| Capture | S39 | Window | U / D records | Final I-modem BLER | Duplex gate |
|---|---:|---:|---:|---:|---|
| `imodem-x2-stored-level-countercontrol-20261027-082959` | stored 0 | 20 s | 2 / 7 | 246 | FAIL |
| `imodem-x2-s39-factory-control-20261027-081958` | 8 | 20 s | 13 / 9 | 0 | FAIL; downstream gap 6.8 s |
| `imodem-x2-s39-factory-repeat-20261027-082202` | 8 | 20 s | 13 / 13 | 0 | PASS; largest U/D gaps 1.5/1.6 s |
| `imodem-x2-s39-factory-60s-20261027-082324` | 8 | 60 s | 42 / 7 | 0 | FAIL; downstream last record at 11.2 s |
| `imodem-x2-s39-option-control-20261027-082703` | option 8 | 20 s | 13 / 8 | 0 | FAIL; downstream stops |

The 60-second final drain contains **43 upstream / 7 downstream** complete
records. Its **48.8-second trailing downstream receive gap** is a failure even
though the saved maximum gap *between* its earlier completed records is only
1.7 seconds. No criterion was weakened to turn this into a pass.

The passing call's ATI6 reports two resent blocks, one NAK, and no link timeout;
there is no zero-retransmission claim. Its final drain is 13 upstream / 14
downstream records. None of these calls establishes maximum application
throughput or arbitrary-binary transport.

## Reproduction

```sh
COURIER_LINE_FRAME_MS=20 PYTHONPATH=. .venv/bin/python tools/probe_imodem_analog_pair.py \
  --wallclock --traffic-seconds 20 --traffic-size 512 \
  --link-diagnostics --trace-link-errors --analog-tx-level 8 \
  --analog-settings 'X1S27=1S54=0S58=48&A3&B1Q0&U26&N39' \
  --imodem-settings 'S54=0S58=48&A3&B1Q0' \
  --imodem-nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --analog-peek 04b5 --analog-dsp-peek 0392 --analog-dsp-peek fff0 \
  --analog-dsp-peek 03a4 --analog-dsp-peek 03db \
  --instructions 1500000000 --analog-instructions 750000000 \
  --output /tmp/imodem-x2-s39-8
```

For the counter-control use `--analog-tx-level stored`. For coherent first-error
bits add `--trace-link-bits`. For 60 seconds increase the instruction budgets
to 3000000000/2000000000, not the record-gap threshold.

## Other controls and exclusions

- Upstream bearer +3 dB did not fix the untuned call: BLER 246.
- Disabling shaping (`S56=16`) still failed: BLER 161.
- Disabling nonlinear coding (`S56=1`) still failed on a repeat with x2 CONNECT.
- Ordinary fixed-24000 V.34 failed before CONNECT, both before and after S39=8;
  it is not a qualified rate-matched data control.
- `imodem-x2-bank-boundary-20261026-230605` and the first nonlinear-coding pilot
  did not establish analog x2 CONNECT. They are not CRC-boundary evidence.
- These calls were run sequentially, with process-group timeouts. There were
  no remote calls, RasFinder logins/configuration changes, firmware patches,
  synthesized payloads, ACKs, or carrier decisions.

## Verification

**219 focused tests pass** in 14.29 seconds, including the UART regressions,
explicit transmit-level configuration, bounded passive capture, HDLC stuffing /
unaligned / abort cases, and optional saved-call replay. `git diff --check` is
clean. No new full-suite pass is claimed.

The independent verifier at
`.artifact-archives/imodem-s39-boundary-20261027/verify.py` replays raw DTE
records and partial prefixes, hashes, unchanged window/drain checks, readback
levels, and carrier/UART/PCM health. It preserves the one passing x2 gate and
all five failed x2 controls rather than inferring success from zero BLERs.

A fresh unchanged-settings fixed-14400 V.34 512-byte call also passes:
`artifacts/imodem-v34-s39-work-regression-20261027-084507/`, with 12 downstream
and 13 upstream complete records in-window, maximum gaps 1.7/1.6 seconds, and
zero I-modem BLERs. Its final drain adds one record in each direction. The verifier
includes this control too. All run-status records and exact commands are saved
beside their captures.

## Remaining work

The [analog downstream observer](imodem-x2-downstream-output-boundary-20261027.md)
now locates valid input shortened at the DSP host-bank output. Next correlate
CPU frame-ISR entry/EOI and acknowledgments with exhausted DSP output lanes,
retaining S39=8 and the unchanged traffic gates. Neither a true 53333 ceiling
nor 256-/64-instruction service cadence resolves the failure. Only after
repeatable unchanged duplex gates, including a 60-second call and the required
full-rate target, should x2 be described as reliable.
