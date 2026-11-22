# Hardware-model follow-up

All operations are offline. Captures and credential-bearing settings are not
modified. The assembled B/C source remains private and Git-ignored.

## Implemented

* EB chip-select decoding for LCS, UCS and GCS2, using the start/stop fields,
  enable, memory-space and ignore-stop bits documented in the 80C186EB manual.
* Firmware-derived GCS2-to-flash-A19 mapping: `800A` gives the normal half-bank
  decode, `000E` produces the low-flash alias used by the boot DSP downloader.
  Entry-point hooks no longer rewrite flash memory; they select execution ABI.
* The transfer sender's temporary RAM-copy window is decoded independently of
  which supervisor is running. Flash-view refreshes skip currently selected
  SRAM ranges. Separate physical SRAM backing/alias behavior remains incomplete.
* Read-only AMD-compatible unlock/autoselect/reset commands. Ordinary RAM-size
  probes cannot program flash. Manufacturer/device values come from recorded
  hardware ATI7: B/C **20-22EC**, C **C2-22D6**. Erase/program are unsupported,
  not silently treated as successful updates. Sector protection is not modeled.
* ASIC DAA identity is queued over the actual CPU-facing mailbox after native
  codec PLL/link setup. Firmware receives `007B:0013` on the healthy model;
  explicit revision zero is covered as an invalid-identity case. This is an
  ASIC model report, not a DSP-originated report or an ATI/RAM patch.
* Both mailbox IRET paths are relocated for B/C normal and both bootmodems.
  Missing translation previously left the timer-in-handler latch set and
  suppressed DSP-paced board ticks. The four-profile regression checks actual
  IRET opcodes, continuing ticks, AT replies and resident-download matching.

## Identity results

The private B/C full image now executes its original `ATI7` formatter and emits:

```
Flash ROM              1024k, 20-22EC
DAA rev                0013
```

Follow-up: Internal came from the legacy default strap code 2, not RAM `1C04`.
Captured 3453 profiles now model External with code 7 (physical 7 versus 13
remains unmeasured). The newest valid private settings record, version 32,
has an erased product-ID override; versions 29–31 contain `00345303`. The
original getter rejects `FF`, explaining the blank normal ID. `1C04` only
gates whether the ID line is printed. Nothing is patched to conceal this.
See [the product/RAM/calibration audit](../../docs/3453-product-ids-and-calibration.md).

## Offline dial control

```sh
./courier run "$FLASH" --with-dsp --exchange --instructions 24000000 \
  --summary --at 'ATX3S7=3' --at 'ATD5551212'
```

Before IRET translation: no board ticks, zero exchange calls, no line seizure.
After translation: **4,547 ticks**, **one exchange call**, **301 DTMF analysis
blocks**, line subsequently released; **no decoded digits**, no call-overlay
downloads, `NO CARRIER`. DTMF analysis blocks are not evidence that actual
DTMF was transmitted. No connection or payload delivery is claimed.

A `--real-delays` control with 18 million instructions had not reached the
command loop; it cannot be counted as a call test. Calibration/clock behavior
still requires investigation rather than assuming accelerated waits are faithful.

## Remaining work

* Product/country/board identification producer and complete ATI7 agreement.
* Serial-codec calibration, hook/control timing and nonzero dial audio.
* Board-specific DSP RAM aliasing (32K-word hybrid versus 64K-word C).
* Guest-driven XMODEM transfers and their exact byte/CRC checks.
* A complete lower-rate call before V.34/V.90/V.92 or payload interoperability.

See [implementation and usage](../../docs/3453-flash-boot.md).
