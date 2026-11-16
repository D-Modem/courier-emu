# What the 2806 actually touches in its EEPROM

[asic-pinout.md](asic-pinout.md) maps the 93C66 to its pins. This document maps it to its
use. We ran the flash capture of the board under
`artifacts/eeprom-access-map-20260913/`. The trace of the NVRAM model recorded
each Microwire command that the firmware sends. The result is what the firmware does. It is not
what a datasheet says that it can do.

## The boot sequence, in order

| step | words | what happens |
|---|---|---|
| 1 | `0x00` | read - the result is `0xffff` on a blank part |
| 2 | `0x00` | **write-enable, write `0x0000`, write-disable** |
| 3 | `0x5e`-`0x66` | read - words 94..102, the datapump block |
| 4 | `0x00`-`0xf2` | read, linearly |

The boot does **266 reads and one write**, and it touches 243 of the 256 words. Words `0xf3`-`0xff`
(the top thirteen) are never read.

Three facts are important.

**The firmware initializes word 0 when it finds that the part is blank.** That is the
one write that a boot does. On an erased device, it always occurs: read
`0xff`, enable, write zero, disable. Thus, the firmware does not keep a "blank EEPROM" in that state.
Any fixture that starts blank is already
changed when the firmware parses the first `AT`.

**Words 94..102 are read before the sweep, not during it.** That block is
already documented from the other end: in [dsp-rom-probe.md](dsp-rom-probe.md),
the driver of the DSP caches exactly those words. Here, it is the first
item that the supervisor gets after the word-0 check. It is not part of the
general profile read. It is a separate, earlier task.

**The sweep reads almost all the words.** The firmware reads the full store, and does not
address individual settings. This is
why a blank fixture has an effect on many items at the same time.

## What `AT&W` does not do here

[idsdl-extended-registers.md](idsdl-extended-registers.md) records that
"`AT&W` alone programs the standard USR profile at EEPROM words `0x00`-`0x22`".
That result was measured on the 302 image with a persistent `--nvram` file.

**We could not reproduce that result.** `AT&W` answers `OK` and programs nothing
other than the word 0 of the boot. We tried this on the 2806 capture and on `IDSDL302.ROM`, through
the same CLI route with a persistent `--nvram` file. We also tried `ATE0&W`,
`ATS0=3&W` and `AT&F&W`, because the write possibly needed a changed setting. `AT&W1`
answers `ERROR`, thus the command parser receives the command. Each run gave `writes: 0`.

We record this as a discrepancy and not as a correction, because the earlier
result was also a measurement, and we did not find the difference in the setup. It is important because the DTE format is one of the items that `&W` stores.
The harness cannot store a profile, and this is the other half of the cause: each run
starts at [7 data bits and even parity](running-the-25mhz-image.md).

## Why this is worth having without a captured part

There is still **no captured 93C66 image in this repository**. This map does not
replace an image. It tells which words are important, not what is in them. But it makes smaller
the area that a capture must cover. Also, it tells something that a capture cannot tell:
the firmware writes to the part during an ordinary boot. Thus, a dump that you make
after the board has run is not a dump of the factory state.
