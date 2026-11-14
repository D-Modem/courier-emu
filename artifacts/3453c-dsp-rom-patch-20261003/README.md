# DSP ROM-mapping monitor revision

We built this revision from the hardware-verified 3453C stock 2.3.33. It adds two exact DSP requests:

- `ATG008Baaaa`: reads program word aaaa while PMST.MP/MC is temporarily cleared.
  The permitted range is 0000..1FFF. It returns 0072, the same as ordinary program reads.
- `ATG008C0000`: reads the live PMST and does not change it. It returns 0071.
- `ATGEssssEEEE`: streams inclusive mapped-ROM reads, in the limits 0000..1FFF.
- `ATGDssssEEEE`: the existing ordinary program stream, with the same address limits as before.

Each mapped read executes at 75E0 or higher, outside the candidate ROM window.
It saves ST0 and ST1 and masks interrupts. It saves the complete PMST on the hardware stack and
clears only bit 3. Then it does a table read of the requested word, and restores PMST before
it restores the interrupt enable and the status. The restoration of INTM is explicit, because LST does
not restore INTM. When ST0 is restored after ST1, ARP is also kept, although ARB is different.
The existing reply queue now uses the same correct restoration of the interrupt and the status.
The monitor uses 116 words, 75E0..7653. The known overlays end below this area.

27 tests pass. These include 18 DSP and 20 CPU isolated instruction executions.
The DSP cases use a simulated C51 ROM to verify mapped reads and the exact PMST
restoration. They include masked and unmasked entry, and also full-queue failures. The emulator
does not model the silicon ROM of this unit or its optional protection feature.
TI documents that external instructions can receive incorrect bus data when ROM
protection is enabled (SPRU056D, section 8.2.4). Thus, captures must have a hardware analysis
before we can identify them as mask ROM.

Host examples:

```
.venv/bin/python tools/3453c_monitor.py pmst
.venv/bin/python tools/3453c_monitor.py dump rom 0000 1fff --fast --output window.bin
```

If the silicon ROM ends earlier, the 8K-word window includes external memory.
The upper boundary is a limit of the probe. It is not a claim that this part has 8K words of ROM.

## Hardware result

All 5,888 flash blocks were acknowledged without retries. The reset and ATGU were successful. The live PMST was 18B8 before and after the mapped reads. Two 0000..1FFF windows, requested independently, were exactly the same, and we extracted the 4K-word internal ROM at 0000..0FFF successfully. The upper window is the same as the downloaded RAM. ROM protection did not block this read route. Refer to hardware-verification.json and ../3453c-dsp-mask-rom-read-20261003/README.md. The revision with the ROM function stays installed.
