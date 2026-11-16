# The ID_SDL ROM builds against the stock analog payloads

> **Corrected.** The first title of this file was "the ISDN Courier against the analog
> one". That was wrong. `IDSDL302.ROM` and the two `courier-board-21210-capture`
> dumps identify themselves as **Courier V.Everything**: "Courier
> V.Everything using ID_SDL, extended +S register HELP", with the supervisor dates
> 03/13/98 and 04/30/98. `ID_SDL` is the flash build with extended help. It is not ISDN.
> The ISDN image in this tree is `Ie030002.nac`. It says `I-Modem` and
> contains S67 "Misc. ISDN Configuration", S68 "ISDN Universal Connect", V.110,
> V.120, X.75 and Turbo PPP. All measurements below are analog against
> analog. The rows with the label ISDN are the ID_SDL ROM builds. We did not do the real
> ISDN comparison.

It is the same machine and the same four-image structure, but a different generation of the code.
`IDSDL302.ROM` (ISDN 3.0.2) and the analog `MAIN_*.XMF` payloads both contain a
C52 resident bank plus three overlays. The table that
[dsp-overlays.md](dsp-overlays.md) describes loads them. The two flash payloads are
`0xb8000` bytes, with the base `0x40000`.

## The structure is identical

We read these values from the overlay table of each supervisor (we applied the table and
segment patterns of `courier_emu.rom` to `XmfImage.supervisor`):

| image | resident | ov6 | ov7 | ov8 |
|---|---:|---:|---:|---:|
| ID_SDL 3.02 (03/13/98) | 27,710 w @ `8000` | 11,510 w @ `9d00` | 7,499 w @ `b000` | 7,350 w @ `dc00` |
| analog 2.1.1 | 30,170 w @ `8000` | 11,929 w @ `9d00` | 7,328 w @ `af50` | 6,211 w @ `dc00` |
| analog 2.2.05 | 30,170 w @ `8000` | 11,937 w @ `9d00` | 7,328 w @ `af00` | 6,218 w @ `dc00` |
| analog 2.3.12 | 26,080 w | 11,832 w | 4,090 w | 6,197 w |
| analog 2.3.31 / 2.3.33 | 26,080 w | 11,832 w | 4,094 w | 6,197 w |

There are four images, with the same slot numbers, the same load addresses for the resident
bank and overlay 6, and overlay 8 at `dc00` in all of them. With this pattern, the *entry* words
of the 2.3.x rows are not plausible (`1000`, `1dc9`, `0`).
Thus, we give only their lengths. The 2.1.1/2.2.05 entries parse correctly, and they
agree with the ISDN entries, except overlay 7: `af50`/`af00` against `b000`.

## The content is a fork of the 2.1.x line

We measured coverage as the fraction of the bytes of each ISDN overlay that are in runs of
≥12 bytes that also occur in the analog payload. This measure is byte-exact. Thus, relocation and
re-assembly make it smaller, and for this reason the baselines are important:

| analog pair | DSP coverage |
|---|---:|
| 2.3.33 vs 2.3.31 | 100.0% (one run - the DSP image is unchanged) |
| 2.3.12 vs 2.3.31 | 82.6% |
| 2.2.05 vs 2.3.31 | 50.7% |
| 2.1.1 vs 2.3.31 | 50.5% |

Thus, 50% is the value for "a different generation of the same code" here.
Also, the analog DSP was mostly rebuilt between 2.2.05 and 2.3.12.

| ID_SDL overlay | vs analog 2.1.1 | vs analog 2.2.05 | vs analog 2.3.31 |
|---|---:|---:|---:|
| resident (`8000`) | 54.6% | 54.5% | 45.8% |
| ov6 (`9d00`, V.34) | 36.8% | 36.7% | 33.3% |
| ov7 (`b000`, V.FC) | **63.1%** | 62.8% | 18.7% |
| ov8 (`dc00`, PCM) | 22.4% | 22.4% | 22.0% |

These are the three results:

* **The ID_SDL ROM contains DSP code from the 2.1.x/2.2.x era.** Each overlay
  is closer to 2.1.1 than to 2.3.31. Overlay 7 is clearly closer: 63% against
  19%, with a single shared run of 1,084 bytes. The 2.3.x analog builds made
  overlay 7 shorter, from ~7,300 words to ~4,090. The 03/13/98 ROM kept the long overlay.
* **Overlay 6 has the smallest shared part of the three images that came from the old line** (37%).
  V.34 is in this overlay, and it is the part with the most changes on the two sides.
* **Overlay 8 is not related to any analog overlay**: 22% against each analog build. The
  value is the same for 2.1.1 and for 2.3.33. The PCM downstream layer
  ([pcm-x2-v90.md](pcm-x2-v90.md)) is a separate build in the ISDN image, but
  `IDSDL302.ROM` contains the same `64000/x2` and `64000/V90` result
  strings.

The resident bank at 46-55% is the correct summary of the full comparison. It is the
same program, two branches apart, and the ID_SDL ROM comes from the older trunk. This
is what a 1998 ROM built on the 2.1.x DSP looks like next to a 2.3.x payload.
