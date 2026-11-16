# Arming slot 0: overlay 6 runs

[datapump-slots.md](datapump-slots.md) named slot 0 V.34, and
[fsk-modulation.md](fsk-modulation.md) read its dispatch from `9b34`. But
nobody had executed the overlay before. The DSP download of the supervisor
contains only the resident bank, `8000..eea7`. Thus program `9d00` holds
resident words, and the 12,594-word V.34 image stays in flash at `36e90` with
no change.

`courier_emu.v34` publishes the image with `load_program` and enters it in the
same way as the firmware. Three conditions had to be correct. Each of them was
incorrect at first.

**Data page 0, not 7.** `9b41`'s `ldp #000` is between `9b34`'s
`splk @7c, #9b48` and `9b44`'s `add @7c`. If you enter the dispatcher with
DP 7, the two halves go to different cells: `add @7c` reads data `007c`,
`tblr` reads program `0000`, and the `bacc` goes to the value at the bottom of
program memory. The caller enters with DP 0.

**You cannot preset the mode flags.** `9b3c` calls `9b2c`, which ends with
`retd / lacb / sacl @27` - it *writes* `@27` from the return value of `d648`.
A value that you put there before is overwritten before `9b5a` tests it.

**The mode flags come from a list at data `fea1`, read with ARP 1.** `9b2d`
sets `ar1, #fea1`, and `d665` reads `*+`. With ARP 0, it reads AR0 instead,
and the scan stops on the first zero. `d665` keeps the first word whose low
five bits are 5. `d64d` takes bits 5-7 of that word, and the result becomes
`@27`. The word `#0045` gives `@27` = 2. Bit 1 of this value is the flag of
slot 0.

## What it does

| | originate (`9b34`) | answer (`9b38`) |
|---|---|---|
| enters `9d00` | yes | yes |
| instructions to return | 2,237 | 2,236 |
| `@6f` marker | `4042` | `4042` |
| `@1a` transmit callback | `aafb` | `aafb` |
| `@1b` receive callback | `9daf` | `9daf` |

The marker is the useful check: `#4042` is the value that
[fsk-modulation.md](fsk-modulation.md) read statically from `9d00`, before
anything ran. The overlay executes to it and returns correctly.

## No tone, and why that is the expected result

`aafb` returns in 278 instructions and installs its own successor
(`splk @1a, #ab3f`, then `ab83`). Thus the transmit chain advances for each
sample. Its body is filter banks - 46-tap and 140-tap `mac` runs into `@78`,
`@79`, `@7d`, `@7e`.

Overlay 6 does not touch a converter ([vpcm-datapump.md](vpcm-datapump.md)).
Thus its samples get to the line only through the resident mixer. When we
drive it in that way, the chain runs and the mixer buffer stays zero. A V.34
modulator with no start-up state, no committed symbol rate and no data source
has nothing to send. Thus silence is the correct behavior. But this means that
**we did not produce or measure a V.34 signal here**. The arming above is a
bring-up, not a carrier.

`v34.transmit_callback` keeps that result measured, not assumed:
`tests/test_v34.py` pins the advance of the chain *and* the silence. Thus, if
one of them changes, the change is visible.
