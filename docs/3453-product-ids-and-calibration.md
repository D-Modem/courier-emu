# 3453 product IDs, board straps, DSP RAM and calibration

Offline investigation of the captured B/C 2.2.09 and C 2.3.33 normal / 2.3.31
recovery firmware. No attached-hardware commands or writes were used.

## Different identity numbers are not interchangeable

For manufacturer sales SKUs, bottom-label variants, CTR21 approvals and the
independent country/ID fields, see [regional models](3453-regional-models.md).

* `ATI0` has four responses: `3368`, `3368A`, `5608`, `5608A`. The `5608`
  branch tests the V.90 feature bit (`19F7:20` on B/C; `1A07:20` on C).
  Strap capability bit `08` suppresses the `A` suffix; otherwise it is added.
  These are capability/variant responses, not eight-character manufacturing
  SKUs or physical RAM-size identifications.
* `ATI7 Product ID` is an eight-character stored override or firmware fallback.
  B/C's older valid captured settings records contain `00345303`. A measured
  CTR21 C reports `99345303`. Both families contain fallback literals
  `00345303` and `XX345303`; `XX` is not proof of a DAA failure.
* Both families also contain six-character SKU suffixes `345303` and `345403`.
  These literals alone do not establish every possible manufacturing prefix
  or which SKU an arbitrary board should have. The repository's older
  `main2205.XMF` instead has fallback `00345302` / `XX345302`; all four
  `MAIN_2.3.*` / `2_3_33.XMF` images have the `03` fallback. Arbitrary accepted
  overrides mean a literal scan cannot enumerate all possible reported IDs.
* `ATI7 Product type` combines a country label with a **strap-derived** class.
* `20-22EC` (modeled B/C flash) and `C2-22D6` (C flash) are flash manufacturer /
  device identifiers, not modem product IDs. `0013` is the DAA identity report.

### All 16 strap codes

All four captured supervisors use the same table:

| Code | Capability | Firmware class | Usable |
|---:|---:|---|---|
| 0, 1, 3, 4, 6, 8, 10, 15 | `00` | Undefined / no board | no |
| 2 | `29` | Internal | yes |
| 5 | `14` | Rackmount | yes |
| 7 | `22` | External | yes |
| 9, 12 | `28` | Internal | yes |
| 11 | `42` | External | no: unsupported bit `40` |
| 13 | `22` | External | yes |
| 14 | `48` | Internal | no: unsupported bit `40` |

Class selection tests bit `02`, then `08`, then `04`. B/C normal scans the
four drive lines at CPU `58557..585FB`, looks up the table at `585FC`, and
stores the capability byte at RAM `0A22`. The C normal table is at `58604`
and its capability byte at RAM `0A32`. The drive/sense wiring used by this
scan matches the existing panel model (ports `12`/`14`, sense bit `08`).

The old emulator default of code 2 caused the Internal report. `--board-id auto`
now models captured 3453 firmware as External using code 7; legacy
images retain their previous default. Explicit codes and `none` remain
available. **The physical choice between equivalent-class codes 7 and 13
has not been measured.** This is a documented external-board model default,
not a recovered exact strap population.

### Why the private B/C normal image printed a blank ID

B/C normal's getter at `832D4` reads RAM `1860`; C normal's at `830B6` reads
`1870`. A zero first byte selects the fallback: DAA revision exactly 4 prints
`00345303`, otherwise `XX345303`. A nonzero first byte enters the override
printer; bytes outside `30..7A` terminate printing. The setter copies at
most eight bytes and appends the current terminator.

B/C normal copies the selected settings payload to RAM `0A26` at
`7AFF7..7B028`. Thus override offset `0E3A` lands at RAM `1860`.
The private captured records have:

| Sector | Version | Whole-sector CRC valid | Product override |
|---|---:|---|---|
| 0 | 29 | yes | `00345303` |
| 1 | 30 | yes | `00345303` |
| 2 | 31 | yes | `00345303` |
| 3 | 32 | yes | erased (`FF`) |

The guest selects version 32, copies `FF` into `1860` (observed write PC
`7B022`), and rejects it as an override character. That explains the offline
blank without an output or RAM patch. This does **not** establish why that
record was created or what the physical modem reports now. Do not rewrite
settings, silently select an older record, or replace `FF` with zero to hide
this finding.

The earlier focus on RAM `1C04` was misplaced: bit 0 gates whether the normal
formatter prints the Product ID line at all. It does not select Internal /
External and does not generate the ID. The class comes from `0A22`.

## DSP SRAM is not codec calibration

The observed B/C hardware has 32K x 16 DSP SRAM (64 KiB); the observed C has
64K x 16 (128 KiB). CPU RAM is separate. Static SRAM does not require DDR-like
training. Its emulator questions are address decoding, program/data sharing,
high-address aliasing and any guest RAM diagnostic—not the DAA's ADC-offset
calibration.

All four initial downloaded segments stay below DSP word address `8000`:
`1000..75DF`, `1DC9..4C00`, a small `0000` segment, and `5CB0..74E4`.
The resident startup at `1020..1027` clears data `0100..04FF` and `0060..007F`;
`103A..1046` sets circular-buffer pointers around `7F80..7FDF` in both
families. These observations do not establish the geometry of later call
overlays or prove that upper 32K is unused on C.

The current native model's configured shared external window is
`1000..7FFF`. It does not yet implement a board-specific physical 32K/64K
SRAM mask. C52 internal ROM/DARAM/SARAM selection must stay distinct from
external-chip address aliasing. A capacity difference alone does not explain
missing digits: the observed bootstrap ranges fit the smaller chip. Upper
address behavior and later overlay accesses remain to be traced/validated.

## Actual Si3034 calibration requirements

Source: `docs/SI3034.PDF`, Rev. 2.02, sections 5.25–5.27 and register 17.

* Register 17 bit 5 is `CALD`, **auto-calibration disable**.
* Bit 6 is `MCAL`, manual calibration. The documented sequence sets `CALD`,
  toggles `MCAL` **one then zero**, and allows `512/Fs` seconds. Do not invent
  an automatically clearing MCAL handshake or older-family ASIC replies.
* Automatic calibration, when enabled, follows off-hook or loss of line
  power after DC termination stabilizes.
* At the firmware's modeled 7200 Hz rate, `512/Fs` is **71.11 ms**. The
  documented off-hook test setup waits `1548/Fs`, **215 ms**, before test mode.
* Codec register 6 power bits must be clear and register 12 `FDT` valid before
  line-side status is meaningful. A revision report alone is not calibration.

In these 3453 DSP images mailbox tag `82` writes codec register 17; `81`
requests its readback; `84` sends raw secondary controls. It is not the
older ASIC start/hold command. Native `codec_apply_register()` currently
stores register-17 bits and returns them, but does not model ADC offset
estimation or the 512-frame calibration interval. Therefore a correct
`0013`, register readback, or line seizure is not proof of calibrated audio.

### Historical guest dial observation (before native hook-pin correction)

`tools/probe_3453_calibration.py` timestamps CPU codec-mailbox controls against
native primary-frame counters. The private B/C probe with modeled External
straps, DSP-paced ticks, `ATX3S7=3` then `ATD5551212`, and a quiet modeled DAA /
exchange ran 24 million instructions: 4550 ticks, one line seizure/release,
431 DTMF analysis blocks, **no decoded digits and no overlay downloads**, ending
`NO DIAL TONE`. This supersedes neither the earlier Internal-model
`NO CARRIER` observation nor demonstrates a call.

Observed CPU tag `82` writes were `00A0`: CALD set, MCAL clear. No CPU-requested
MCAL one/zero sequence appeared in this run. Direct DSP register activity and
analog calibration remain separate questions. Frame counters reset when the
guest resets the codec; do not subtract counters across these reset epochs.
The earlier probe without a DAA or DSP tick source was an invalid call control
and is not published as call evidence.

Follow-up [native serial/audio trace](../artifacts/3453-audio-calibration-trace-20261014/README.md):
accepted secondary controls also contain only `11A0`, no MCAL pulse. Nonzero
ADC samples reach the original DSP ISR and input-processing ring, but output
stays zero. Those API probes exposed missing native external-hook wiring:
the pin was only updated when the optional Python `CodecBringUp` existed.
After correcting the bridge, blind dialing ends in `NO CARRIER` and accepted
controls include `1160 -> 1120 -> 1100`: a genuine guest MCAL one/zero pulse.
See `bc-blind-dial-hook-fixed.json` in the linked trace directory. Transmit
audio is still zero, with no decoded digits or overlays. The old lack of a
pulse is not a firmware limitation. Calibration interval fidelity remains
unimplemented. Unaccelerated startup at 40 million instructions has not
reached commands and is not a call test.

A subsequent [audio-path diagnosis](3453-audio-path-diagnosis.md) found a second
emulator issue: the C delay hook was firing on B/C's timer ISR, corrupting CX
and truncating the tone-library transfer. After fixing physical-PC filtering,
the unchanged guest downloads the complete library and the exchange decodes
`5551212` from nonzero transmitted audio. The blind call still ends in
`NO CARRIER`; a carrier/data connection is not demonstrated.

Remaining work: trace guest carrier/answer state and board handshakes, relate
calibration controls to reset epochs, distinguish them from RAM diagnostics,
validate physical high-address SRAM decoding, then demonstrate nonzero dial
audio and genuine call-overlay requests. No working call is claimed.

## Reproduce the public inventory

`tools/audit_3453_product_ids.py IMAGE...` emits capability tables, literal
IDs, DSP bootstrap bounds and hashes without opening serial ports or reading
private settings. Public output is in
`artifacts/3453-product-ram-audit-20261014/identity-tables.json`.
