# The DSP is a 'C51: 8K of on-chip ROM, not 2K

We ran `probe_transport --memory-test` two times on the 25 MHz board. The two results
were identical. The result is seventeen words.

## What it does

[probing.md](../../docs/probing.md) proposed a stability test: read `0x0800`
two times and see if the live scratch of the firmware moves. This test cannot operate, because
the probe resets the DSP and takes control of it. No firmware runs
below the probe to move data, and the two parts return the same value two times. A different
test does not need live firmware: does the region accept
a **write**? SARAM that is visible from the two spaces is one physical memory. Thus, a write
through data space must read back through program space. ROM cannot do this.

The test writes each address two times, with two different patterns. Thus, a region that
only returns a constant cannot pass by chance.

## What came back

```
PMST as found                00b0
PMST after RAM|OVLY          00b0
0800 program before          ffff
0800 data after A55A         a55a      <- the write lands in data space
0800 program after A55A      ffff      <- and program space does not see it
0800 data after 5AA5         5aa5
0800 program after 5AA5      ffff
1800 program before          ffff
1800 data after A55A         a55a
1800 program after A55A      ffff      <- same
1800 data after 5AA5         5aa5
1800 program after 5AA5      ffff
2400 program before          ab5e
2400 data after A55A         a55a
2400 program after A55A      a55a      <- here program space follows the write
2400 data after 5AA5         5aa5
2400 program after 5AA5      5aa5
```


**`PMST` = `00b0`: `IPTR` 0, `AVIS` 1, `OVLY` 1, `RAM` 1, `MP/MC` 0.**

## MP/MC has now been read

Bit 3 of `PMST` is `MP/MC`, and it is **0**. This is microcomputer mode, with the on-chip ROM
mapped at program `0x0000`. Each ROM reading in this repository had the
caveat that nobody had read this bit directly. Now we read it, and it agrees with
the vector table at `0x0000`.

Also, `RAM` and `OVLY` are **already set when the kernel starts**.
`PMST` reads `00b0` before the `opl @07, #0030` and also after it. Thus, that `opl`
never changed anything.

## Why this is a 'C51

With `MP/MC=0` and `PMST.RAM=1`:

* A **'C50** maps its 9K SARAM into program space over `0x0800`-`0x2BFF`. Thus,
  `0x0800` and `0x1800` would both follow the write. Neither does. **Excluded.**
* A **'C51** has 8K of on-chip ROM at `0x0000`-`0x1FFF`. In microcomputer mode, this ROM
  has priority over SARAM in program space. The 'C51 has only 1K of SARAM. `0x0800` and
  `0x1800` read ROM and ignore the write. `0x2400` is above the ROM and is
  writable. **That is exactly the split that we saw.**

The package marking agrees, and it always agreed: `D17140PQ`. The 'C50, 'LC50, 'C51 and
'LC51 all have the `PQ` marking.

## The instrument shows both signatures

We also ran the same kernel offline against the emulator fixture. The fixture maps a 4K ROM at
`0x0000`-`0x0FFF` and SARAM above it. The kernel shows that the write has no effect on `0x0800`,
and that `0x1800`/`0x2400` follow the write. This is the opposite split
from the board, from the same instrument. Thus, if the instrument gave a null result here,
we would see it.
