# Mask ROM assessment

The full capture does **not** show the internal mask-ROM array.

- Words `0000..0FFD`: all 4,094 words are exactly the same as downloaded firmware segment 7.
- Words `1000..7623`: all 26,148 words are exactly the same as the patched resident segment 5.
- The captured resident startup sets PMST to `18B8`. Bit 3 (`MP/MC`) is 1, and this disables the internal ROM in program space. This is static evidence from the startup code. It is not a direct live measurement of PMST.

The dump command reads the current program map and never changes MP/MC. To get the actual silicon ROM, a separate ROM-mapping probe is necessary. The ROM size and the ROM protection on this part are not yet known. The recovered ROM of the older board in the repository is not a reference image for this different DSP mask.

The [TI C5x User’s Guide](https://www.ti.com/lit/ug/spru056d/spru056d.pdf), section 2.3.1, tells how to remove the boot ROM: set PMST.MP/MC.

Captured startup instructions:

```text
1000: BCFE         ldp     #0fe
1001: AE53 FFFF    splk    @53, #ffff
1003: 0C53 8057    out     @53, 8057
1005: BC00         ldp     #000
1006: AE7A 0000    splk    @7a, #0000
1008: BE41         setc intm
1009: BC00         ldp     #000
100A: AE2A 0010    splk    @2a, #0010
100C: AE28 2000    splk    @28, #2000
100E: AE29 0101    splk    @29, #0101
1010: AE21 0000    splk    @21, #0000
1012: 8B89         mar     *, ar1
1013: BE42         clrc ovm
1014: AE7D 27BD    splk    @7d, #27bd
1016: 0F7D         lst     st1, @7d
1017: 5E07 07F8    apl     @07, #07f8
1019: 5D07 18B8    opl     @07, #18b8
101B: BF09 039D    lar     ar1, #039d
101D: 7680         pshd    *
101E: 087A         lamm    @7a
101F: BE1E         sacb
```
