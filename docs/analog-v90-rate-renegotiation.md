# Courier's missed V.90 rate-renegotiation request

## Corrected implementation and qualification

The historical faults below have now been repaired in sibling `v90modem`.
The first corrected, wall-clock-paced **600M-instruction, 5-ms** call carried
**38400 bytes exactly in each direction**, completed a **short** renegotiation
with a fresh **100.0% B1 fit**, stayed at **31200 upstream**, and had **zero
full retrains**. The downstream CP changed from DRN=19 (52000 bit/s) to
DRN=21 (54666.67 bit/s). This is a real negotiated increase, not a forced
CONNECT or a rate ceiling override.

Pinned executable:
`artifacts/analog-v90-reneg-fix/fresh-rx/v90_engine_peer`, SHA-256
`ec7f7f8e9777391dde8f4f8a82b0266df8a61773755270519339955beece5fb9`.
The responder default is now ON; this passing run has no
`ME_V90_RENEG_RESPOND`, rate-forcing, or rate-control-disabling override.
The prior scoped DIL repeat profile and active-low CTS correction remain.

The final fault behind the spurious rate reductions was receiver lifecycle:
the responder used startup conditioning and left the old, already-acquired
T/3 DATA receiver active through the new CP exchange. It then called the
transition a data failure and offered 28800 instead of 31200. Reusing the
existing **fresh renegotiation conditioning** retires that receiver and
requires new E/B1 without changing any acquisition thresholds.

Other repaired protocol seams: fresh strict CP capture while retaining
ME_DATA/LAPM, CP rather than CPt on renegotiation, generation-based stale
worker exclusion, Rd/Rt constellation maxima rather than Ri's U_INFO,
acceptance of changed CP parameters, and zeroed TRN2d memories. The strict
batch decoder can now observe an actual adjacent 20-one E on its own
CRC-qualified CP hypothesis; it does not infer E from CP or qualify the
separate streaming tap. CP preambles, CPs/SCR and incomplete E are excluded.
B1 remains independently validated.

Completed matched results, all using that same pinned binary:

| Arm | Exact duplex | Short downstream resumptions | Completed full retrains |
| --- | --- | --- | --- |
| Corrected default, 5 ms, 600M instructions | 38400 bytes each way | 1 | **0** |
| Corrected default, 20 ms, 600M instructions | 38400 bytes each way | 1 | **0** |
| Responder disabled, 5 ms, 600M instructions | 38400 bytes each way | 2 (recovery) | **2** |
| x2 regression, 180M instructions | both requested payloads exact | 0 | 0 |

The disabled control also logs three upstream rate-reduction offers; neither
corrected V.90 arm logs any. All processes exit 0, all validation checks pass,
and the guest remains online at the instruction bound. The disabled control
still preserves bytes because the CTS fix and legitimate recovery remain in
place; it does **not** qualify the missed-response behavior as correct.

Consolidated machine-readable results:
`artifacts/analog-v90-reneg-fix/results.json`.
Full source rationale and regression coverage:
`../v90modem/docs/v90_courier_rate_renegotiation.md`.
The sibling engine repair is committed and pushed as **`66ab5db8`**.
Three selected engine fast-list tests pass (including strict retained-waveform
CP/E and fresh-receiver lifecycle checks), as do **108 focused emulator tests**.
This is not a full-suite pass claim.

These are finite software-loop qualifications, **not physical Courier tests
or proof of indefinite stability**.


## Isolated fault

The retained call contains a Courier S/S-bar request before the full retrain.
The digital engine does not answer that request with Rd. Its V.90 responder
is deliberately **off by default** (`ME_V90_RENEG_RESPOND`), unlike its plain
V.34 responder. This is a concrete v90modem-side interoperability limitation,
not evidence that the emulator spontaneously corrupts the upstream waveform.
It does not establish that every emulator detail is correct or that enabling
the existing responder is sufficient for a successful short renegotiation.

V.90 (09/98) §8.3.4 imports V.34 (10/96) §10.1.3.7's S: alternate a constellation
point with that point rotated **90 degrees**, not 180 degrees. Thus S contains
carrier energy as well as the two half-symbol-rate sidebands. S-bar reverses
all three components. V.90 §9.6.1.2.1 requires detecting S and its transition;
§9.6.1.2.2 requires the digital modem to send Rd/R-bar-d on a data-frame boundary.

## Evidence from the same retained recording

Capture: `artifacts/analog-v90-continuity-passive300-20261103/`.
Sample indices below are zero-based in its byte-exact 8000-Hz engine recordings.

| Observation | Evidence |
| --- | --- |
| S in upstream | Three-line fit over samples `[378680,378960)` at 228.571, 1828.571 and 3428.571 Hz; normalized squared residual 0.000201. |
| Following S-bar | Fit over `[378990,379010)`; residual 0.000143. Coefficient-vector cosine against S is **-0.999885**, projection -0.996946. |
| No timely downstream Rd | Maximum absolute correlation with Rd's repeated `+++---` sign pattern over every 384-sample window starting in `[378600,399200)` is **0.1875**. Both polarities and all six sample phases are covered. |
| Later full-retrain waveform | Upstream silence begins at 399256, followed by 2400-Hz Tone A with 1800-Hz guard. |
| Engine's late recovery transmission | First tested downstream 384-sample window with Rd sign correlation >0.95 starts at **399619**, after upstream silence begins. Logs report abrupt discontinuity and engine-initiated renegotiation, not a response to peer S. |

The S and S-bar fit windows are plateau interiors, not exact boundaries.
The observed S-to-S-bar transition is approximately sample 378970, about
2.54 seconds before the later silence. The earlier interpretation based only
on that silence and Tone A missed the preceding short-renegotiation request.

Reproduce the measurements without modifying or replaying samples:

```sh
PYTHONPATH="$PWD" ../v90modem/.venv/bin/python \
  artifacts/analog-v90-reneg-cause/analyze_retained.py
```

Numerical output: `artifacts/analog-v90-reneg-cause/retained-waveform-evidence.json`.

## Source corroboration

In sibling `spandsp-master/src/v34rx.c`,
`v34_reneg_respond_enabled()` returns false for V.90 unless the environment
explicitly enables it. `v34_rx_watch_peer_reneg_s()` exits without examining
incoming DATA when that responder is disabled. The engine handler of
`V34_EVENT_PEER_RENEG_S` explicitly documents the same opt-in requirement.

The Courier runtime command `0054` dispatches through program table entry
`843d` to `a456`. That handler tests **physical bit 7** of data `039f` and
branches to the V.90 path at `e9a0`; the retained data flags are `40a1`, with
that bit set. It is not an unconditional full-retrain command. The local
C5x disassembler prints physical bit numbers; do not reverse them again.
The earlier supervisor trace independently records the automatic requested
index `13` → `15` and runtime operation `0054:0015`.

## Matched live experiment

Two 360M-instruction, 5-ms, wall-clock-paced duplex runs were launched with
identical settings except `ME_V90_RENEG_RESPOND=0` versus `1`. Both use the
same copied engine executable, not the sibling's concurrently rebuilt path:

`artifacts/analog-v90-reneg-cause/pinned/v90_engine_peer`

SHA-256: `21c4fc3d0a66c41717efa1e9f84626a043b693474717f3722bd72f285fe036e0`.

Run directories: `respond-0/` and `respond-1/` under that artifact directory.
They retain G.711, engine logs, requested environment and payload validation.
The sibling host probe now accepts `--engine` to pin both execution and the
recorded executable hash. No DSP thresholds or engine defaults were changed
for this experiment.

Both runs completed. OFF logged no peer-request response and recovered only
after the discontinuity. ON detected S at trace +57795 ms, its end at
+57823 ms, and transmitted Rd. It nevertheless followed a peer full retrain
at +62499 ms. Neither run passed exact-duplex validation at this finite bound;
ON completed the native-to-host direction, but not host-to-native. The pinned
binary is newer than the previous 600M CTS controls: these results do not
replace or contradict those controls, and must not be compared to them as a
one-variable experiment. Both new arms recorded the same pinned hash.

### Second concrete engine defect: no fresh batch CP input

The responder calls `enter_v90_phase4_rx_locked()`, which arms the strict batch
CP receiver. In the ON run it logs an upstream capture index of **99800**.
However, in `me_rx_audio()`'s shared `case ME_TRAINING: case ME_DATA:` block,
`v90_cp_live_capture_append()` is called only when `state == ME_TRAINING`.
Renegotiation runs while the engine remains in `ME_DATA`. Consequently the
strict batch decoder is armed without receiving fresh renegotiation audio.
The ON log contains no fresh strict CP acceptance between this arm and the
subsequent retrain. This is a separate receive-path defect; the successful
S detector alone cannot repair it.

The arm also uses the startup helper, which sets
`g_v90_cp_live_expected_compatibility = 0` (CPt), whereas §9.6 calls for CP.
The transmitter's post-Rd log immediately reports `CPt accepted` using retained
startup parameters (D=24, K=19), not a newly decoded renegotiation CP. Fresh
capture lifecycle, CP versus CPt conditioning and retained startup state must
be audited together before implementing or claiming a complete repair.
These observations do not prove that repairing only the batch feed will
complete renegotiation.

## Scope

This establishes a missed mandatory response to a well-formed request in an
emulator capture. It does not yet qualify completed short renegotiations,
map the internal requested index to a new rate, explain every automatic rate
estimate, or prove physical Courier interoperability. Keep the separately
proven active-low CTS fix: even a correct implementation must preserve DTE
continuity during legitimate retrains and renegotiations.
