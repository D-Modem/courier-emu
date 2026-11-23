# Full extension dialing: the extra TX attenuation was the problem

**Fixed:** change the Apple output default from **0.25 to 1.0**, preserving the
Courier firmware's waveform levels. No gateway or Asterisk configuration, DTMF
duration, or interdigit gap was changed.

## Controlled comparison

Same optimized 403 firmware, same `ATX1S7=20DT6312`, same Apple device and line:

| Output gain | Observed Asterisk destination | PBX result |
|---:|---|---|
| 0.25 | `6` | `484 Address Incomplete`; no call to 6312 |
| 1.0 | `6312` | Routed to endpoint 6312, ringing, answered |

The level change is **+12.041 dB**. Codec-side analysis of the original quarter-
scale attempt shows ~69 ms DTMF bursts, with firmware per-tone peaks of about
0.30 (row) and 0.40 (column). The extra gain factor made the transmitted digital
levels approximately **-22.5/-20 dBFS**. Unity retains the firmware levels and
stays within PCM16; it does not manufacture or stretch digits.

The original 0.25 was a conservative loopback/test attenuation, not a validated
real-line calibration. The reused v90modem coupler defaults to unity engine TX;
its hardware notes also record this ATA rejecting quiet DTMF. The successful
live level-only comparison is the decisive evidence here, not that history.

At unity, Asterisk records:

- **6004 → 6312, ANSWERED**, unique ID `1792624894.2114`, 24 billed seconds.
  Call starts 2026-10-22 **12:21:34 NZDT**, answered at 12:21:37.
- A subsequent call using the corrected tool default reaches **6313** and is
  **ANSWERED**, unique ID `1792625193.2117`, 7 billed seconds.
  Call starts **12:26:33 NZDT**, answered at 12:26:35.

Thus the ATA now sends the complete requested extension, and Asterisk actually
rings/bridges that modem endpoint. The duplicate ingress INVITEs are the normal
SIP authentication retry. In the 6312 trace the later `486 Busy Here` belongs to
an OPTIONS probe while the port is busy, not rejection of the answered INVITE.

## Remaining limitations — do not confuse ANSWERED with CONNECT

- **6312:** local firmware eventually returns `NO CARRIER`, worker exit 0,
  zero active gaps and zero input overflow. Its codec retunes through 9600 Hz
  after answer. No successful modem connection/data transfer is established.
- **6313:** correct destination and remote answer are confirmed, but an active
  output underrun occurs afterwards: **130 samples (~12.6 ms)**, worker exit 1.
  This occurs during the running 9600 Hz datapump, not DSP reset; strict loss
  detection is still enabled. It is a separate live-training pacing issue.
- Both attempts release the physical hook and independently verify on-hook.
- RX levels/clipping and modem-training behavior still need investigation.
  The 20-second guest carrier-wait limit was chosen for bounded dialing tests,
  not as proof that all possible training sequences have been exhausted.

## Files / changes / tests

- `verification.json`: comparison, PBX records, worker results and final helper
  counters (the last socket snapshot can precede a later underrun).
- `sip-unity.log`, `sip-default-6313.log`, corresponding `*-status.log`: passive
  SIP summaries and capture-drop counts. Neither capture changes PBX logging.
- `unity-cdr.json`, `default-6313-cdr.json`: read-only CDR extracts, UTC timestamps.
- `unity/6312/`, `default/6313/`: original firmware reports, hardware diagnostics,
  all-generation codec PCM, frame metadata and independent hook readbacks.
- Baseline: [earlier PBX capture](../apple-asterisk-check/README.md).

Python backend, CLI and standalone worker now all default to **1.0**. Explicit
attenuation remains available through `--apple-tx-gain`. Regression tests check
exact sample preservation at unity, explicit attenuation, CLI override behavior,
standalone worker default, reset safety and native polling equivalence.
The focused set passes **80 tests**. No PBX, ATA, modem firmware or digit-map
configuration was changed.
