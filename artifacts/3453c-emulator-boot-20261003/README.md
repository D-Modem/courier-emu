# 3453C recovered-ROM integration and idle comparison

The emulator now executes the recovered 4,096-word mask ROM of the board. The
supervisor transfers the stock resident (52,160 bytes) through the host window.
The IN instructions of the DSP ROM write it into the shared external data/program RAM.
The emulator verifies each transferred group against the program memory. No host shortcut
installs the resident or branches around its loader.

Then the resident installs the 4,096-word low overlay with its own IN/BLDP
loop at 1150–1171. The CPU gets to its main loop at 61D0C. In the previous 2.3
profile, the command entry A7A0 was in the middle of an instruction. A7B0 is the verified
2.3.33 callback. The serial TX capture now also includes the 2.3 UART write at 5944D.

`ati0-run.json` records a `3368` that the firmware made, followed by `OK`. This is
an execution check. It is **not a verified board identity**: the physical board shows
5608A. `ATI7` prints its profile header. Then it stops at the flash-ID service of the boot block
in INT 0A. The emulator does not yet model this service for this update payload. Now, a bare AT
gives no result. These items are not yet validated: the Si3034 audio/register transactions, the
complete board identity, and the call operation.

## Hardware comparison

`hardware-idle-data-0100-03ff.bin` captures all 768 accessible DARAM words,
one after the other, through the installed diagnostic monitor. We read PMST after this.
It was 18B8, with no change. The metadata of the capture includes its hash and the elapsed time.

`compare.py` executes stock firmware with a private copy of the captured
parameter flash. It records the DSP state immediately before the core closes.
It never initializes the DSP RAM from the hardware snapshot. The final comparison
has **763/768 matching words**, and PMST agrees: **18B8**. An earlier snapshot
had 764 matches, because the ring pointers and the interrupt phase are live state.

The final different addresses are 038D, 038E, 0390, 0391 and 0399. The initial
comparison was also different at gain cell 039D (hardware 1200, emulator 0000).
These differences come from startup/configuration and from the live serial loop. DARAM that agrees
and is mostly zero is not proof that the modem trains or that the codec is correct.
We captured only PMST from the hardware registers. The other register values in
`idle-comparison.json` are emulator diagnostics. They are not hardware measurements.

## Reproduce

```
./courier run 2_3_33.XMF --with-dsp --instructions 4000000 --summary --at ATI0
.venv/bin/python artifacts/3453c-emulator-boot-20261003/compare.py
```

Git ignores `private-parameters.sav`, because the parameter sector of the board contains
dial-security credentials. The intermediate numbered runs keep the debugging
failures. As the final evidence, use `ati0-run.json`, `comparison-run.json` and `idle-comparison.json`.

We measured the 4K ROM size of the C52 profile. The emulator does not model SARAM until
a physical alias probe is done. The recovered loader and the resident transfers
must have the external data/program alias at 1000–7FFF. The mailbox diagnostics use
the canonical 005x port names for the guest 805x accesses. The frame interrupt timing uses
the existing Courier clock model. It does not use a new 3453C timing measurement.

This findings bundle records experimental results of the emulator in the working tree.
To get these results again, you must have the separate changes for the emulator integration and
the private capture of the hardware parameters. The ROM/findings commit does not include
these items. We keep the numbered intermediate runs locally.
