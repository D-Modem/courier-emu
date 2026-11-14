# Full C51 ROM content analysis

This is a direct analysis of the 20.16 MHz and 2806 full dumps, 2026-09-13.
The addresses below are DSP word addresses. Each file has 8192 16-bit words
(16384 bytes), not 8192 bytes.

## Newly identified contents

* `0040–0240`: **513-entry quarter-wave cosine table**. Each entry is exactly
  `round(16384*cos(pi*i/1024))`, i = 0..512. Q14 amplitude, from
  `4000` down to zero. This is a mathematical identification, not a visual guess.
* `05b0–05cc`: trigonometric lookup helper. It folds an input phase, reads the
  table with the bases `0240` and `0040`, and adjusts the signs. This agrees with
  the generation of a sine/cosine pair. It is necessary to trace the precise calling convention.
* `0244–044f`: structured packed byte pairs. These agree with constellation
  coordinates. `0450–05af` contains small-index mapping/decision tables.
  This analysis does not establish their specific modulation standards.
* `05cd–060f`: arithmetic helpers. These include an iterative loop that is similar to a division,
  at `05f4`, and a polynomial computation before it. An angle calculation is
  possible, but it is not yet established.
* `0610`: a different download/service path. It polls `@56`, moves four-word
  blocks from `@58` onward into program memory, and transfers control
  through `@7d`. The reset at `0670` installs `0610` in `@6a`. The ROM vector of `@6a`
  is at `0024`.
* `1f9d–1ffa`: **probably diagnostic/manufacturing test code**, and not
  only a mailbox handshake. It does these operations:
  - It accumulates ROM data (`1fb7`).
  - It writes and sums data RAM (`1fbf–1fc9`).
  - It fills program `2000–23ff` (`1fca–1fd2`).
  - It tests arithmetic/logical operations.
  - It copies the results to the external addresses `7000` and `9028`.
  - It toggles XF and loops to `1fa2`.

  The factory-test interpretation is an inference from these operations. We did not find
  a manufacturer identification of this routine.

  > **CAUTION: DO NOT CALL THIS ROUTINE AS A HARMLESS QUERY.** It overwrites RAM.

## Comparison and limits

The two files are different in exactly 96 words, all in `0f9d–0ffc`. The 2806
image repeats the top block there. The 20.16 MHz image has the regular array
pattern there. Their low tables/code and the top block are identical.
This does **not** show if the cause is a decode alias, a mask revision or a different
silicon difference. The existing notes that say that the duplicate cannot be mask
content are stronger than the evidence.

The capture READMEs identify the two compared boards as analog V.Everything
units. The user saw that the ISDN unit has the same C51
markings. This is more hardware evidence, but these files alone are not a
comparison of the analog ROM with the ISDN ROM.

The ROM is mostly repeated fill. But the populated low region includes
useful DSP mathematics and probable modulation tables, not only boot code.
Most of the modem functions still come from downloaded firmware. We did not identify a complete
V.34/V.90 implementation in this mask ROM.

## Correction to older vector notes

Direct decoding gives `0008: 0868 be20`, that is, `lamm @68; bacc`, **not @63**.
The vector at `0012` uses `@63`. This contradicts the timer-vector
example in `docs/dsp-onchip-rom.md`. Use the binary as the authority.
This analysis made no changes to the emulator.

## Does the flash payload use it?

We checked the DSP 3.1.2 resident of the 4.03 capture and all three overlays.
The resident at `8030–8033` copies eleven handler addresses from program
`812d` into data `0060–006a`. The interrupt trampolines of the mask ROM use these pointers.
Together with the established ROM boot path, this is
positive evidence of a real dependency on the ROM.

This static analysis did not find convincing direct calls to the ROM math helpers.
A scan of each word gives false positives of conditional branches in
numeric data. Do not count these as calls. This analysis does not fully exclude
indirect calls or computed table reads.

But the downloaded firmware has its own sine computation at `8b6a–8b83`.
It uses a polynomial, not the cosine lookup of the mask. It also contains
byte-identical parts of the ROM arithmetic helper: ROM `05cd–05de` occurs
at resident `8b84`, and ROM `05f4–05fe` at resident `8baf`. This shows
a shared origin of the implementation. It does not show the execution of those routines in ROM.

The general scheme of the loader agrees with TI SPRU056D section 8.9 (reset into
ROM, selection word at data FFFF). That establishes a boot support of the TI type.
It does not establish that this full mask is identical byte for byte with a standard TI image.
The origin of the mathematics/constellation content is not proved.

## ISDN I-Modem comparison

We also checked `firmware/legacy-usrobotics/2332-x302/Ie030002.xmp`, decoded by
`XmpImage`. We used all seven image descriptors (5–11) at payload `71682` and
segment table `716ca`.

* Resident `805f–8062` installs eleven interrupt pointers from program
  `82e0` into data `0060–006a`. Specifically, `0068 = 838e`. Thus, the captured
  ROM timer trampoline would dispatch to downloaded code at `838e`.
* Resident `9112–912a` contains its own polynomial sine helper. It is very
  similar to the analog helper, but its coefficients are slightly different.
* ROM `05cd–05de` has an exact copy at `912b`. ROM `05f4–05fe` has an exact copy at `9156`.
* We found no ordinary immediate CALL/CALLD/B/BD into ROM `0040–077f` in
  the seven images. The BLPD reads from `0100` in image 6 that we saw are
  entries in a pointer/count table at `a487`. They are not established instructions.
  Conditional and indirect transfers and computed reads are still a limit of this analysis.

Thus, the ISDN code also explicitly expects the ROM interrupt infrastructure, and it
supplies downloaded maths helpers. This static result does not independently
prove that its physical mask ROM is identical to the analog dump.
