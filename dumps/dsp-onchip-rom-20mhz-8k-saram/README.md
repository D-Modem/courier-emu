# The full 8K read again, from a gadget executing in on-chip SARAM

This is the same board and the same day as
[dsp-onchip-rom-20mhz-8k](../dsp-onchip-rom-20mhz-8k/README.md): 20.16 MHz,
ID_SDL v4.03d, serial `0009540034268322`. We read eight 1K windows, with `--via-saram` on
each one.

## Result

```
SARAM-hosted     sha256 d57bc46e1bcd6d4dc8872b97bba2d98ba8fb6b8661440c566b534f0b3f82fac9
off-chip-hosted  sha256 d57bc46e1bcd6d4dc8872b97bba2d98ba8fb6b8661440c566b534f0b3f82fac9
```

**All 8192 words are identical.** The program-memory protection of TI is not programmed
on this part. Thus, each ROM reading that we took through a kernel at external
`0x8000` is the real ROM.

## Why this needed doing, and why SARAM rather than DARAM

The protection prevents these sources from reading on-chip program memory: instructions
fetched from **off-chip memory**, instructions from **DARAM B0**, external DMA, and the emulator.
Each earlier read ran from program `0x8000`, which is off-chip. That is the first item on the list.
Before, we did a spot check of two windows from SARAM. This read is the full ROM.

DARAM is not an alternative:

* **B0** is on the exclusion list. Thus, the protection would block a loop there
  exactly as it would block a loop at `0x8000`.
* **B1** (`0x0300`-`0x04FF`) and **B2** (`0x0060`-`0x007F`) are not accessible
  from program space. Only B0 maps into program space, through `CNF`, at
  `0xFE00`-`0xFFFF`.

Thus, SARAM (program `0x2000`-`0x23FF` on this part) is the only on-chip location that
is executable and also not on the exclusion list. For that reason, `ROM_DUMP_GADGET` is
`0x2000`.

## What it does not show

A null result cannot show the difference between "protection is off" and "protection is on but
SARAM is exempt". The TI wording suggests the second interpretation. In both cases, the
data is the ROM. A read from DARAM B0 would show the difference: if
protection were active and only SARAM were exempt, that read would fail and these reads
would succeed. We did not do this read, because nothing here depends on the difference.
