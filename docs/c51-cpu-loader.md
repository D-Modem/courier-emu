# The 80186/C51 download architecture

This is an analysis of the captured 4.03 supervisor and the recovered C51 mask
ROM, 2026-09-14. The addresses in the CPU listings are offsets in the `0x8000`
code segment of the supervisor. The addresses in the C51 listings are DSP word
addresses.

## Conclusion

The 80186 does not address the DSP program SRAM, and the ASIC does not need the
full program address bus of the DSP. The CPU fills four-word ASIC holding
windows. Code that runs on the C51 reads those words through the DSP-side
register window of the ASIC. It writes them to program memory with
`BLDP`/`BLD(P)`, and it keeps the full destination address itself.

The same physical transport has two consumers:

* the mask-ROM service loader at program `0610` installs or reloads the
  resident image;
* the loader of the downloaded resident at `811b..8138` installs call
  overlays.

Thus the emulation must not publish a completed resident through the serial
receiver, or publish an overlay with `load_program`. It must model the shared
ASIC holding registers, the status, the acknowledgements and the C51 event.
Then it must let the original CPU and DSP instructions do the transfer.

## Reset line

The supervisor is an 80C186EB in the 80-lead QFP. CPU pin 58 is `P1.1`. Its
latch is bit 1 of `P1LTCH` at the relocated peripheral-control address `ff56`.
That one net goes to C51 `RS` (pin 127) and to the reset input of the codec:

```text
ff56 bit 1 -> P1.1 / CPU pin 58 -> C51 RS
                                  -> codec RESET
```

The line is active low. The routine at CPU `e3aa` clears bit 1, resets the
download/status registers, waits, and sets bit 1 again. Thus the emulator must
reset and stop the two modeled devices on the falling edge, and start the C51
at program `0000` on the rising edge. Recognition of the first eight payload
bytes is not a substitute for this observable signal.

## Resident transfer from the CPU

The launch routine at CPU `e3aa` first writes the requested DSP destination to
ports `40` and `42`. Then it pulses `ff56` bit 1. After the release, it waits
for the state of the far side and writes `02` to port `1c`.

The checksum routine at `e447` adds the 16-bit payload words and saves the
result at CPU data `0e39`.

The transfer routine at `e47b` sends eight words in each outer iteration:

1. Four little-endian words go through CPU ports `40..4e`. `out 18,1` commits
   the group, and the CPU waits for acknowledgement bit 1.
2. Four little-endian words go through CPU ports `50..5e`. `out 18,2` commits
   the group, and the CPU waits for acknowledgement bit 2.
3. At the end, the saved checksum goes through `40/42`. `out 18,4` submits it,
   and the CPU waits for acknowledgement bit 4.

Thus ports `40..4e` and `50..5e` are two CPU-facing banks of four 16-bit
holding registers. Port `18` is their commit/status port for the resident
download.

## Matching mask-ROM service loader

The reset code installs the service entry in the interrupt trampoline table of
the ROM:

```asm
0672  splk  @6a, #0610
```

The routine at `0610` initializes the service state. It gets the requested
program destination through ASIC cell `@58`. It saves it as the program-memory
pointer in `@1f`, and keeps it in `@7d` as the last entry address. It polls the
ASIC status cell `@56`.

For status bit/group 1, it takes four words that start at `@58` and executes a
four-word `BLDP *+` transfer. It writes `1` to `@56` to acknowledge, and
advances the program pointer by four. The indirect source pointer also
advances. Thus group 2 consumes the second ASIC bank at `@5c..@5f`, and then
acknowledges with `2`. At completion, it writes `4` to `@56` and branches
through the entry saved in `@7d`.

This agrees exactly in structure with the CPU routine: four-word banks,
statuses 1 and 2, completion 4, and a destination supplied before reset. It is
not the generic `XF`/`BIO` boot loader at `072c`.

## Overlay transfer

The overlay sender uses the same eight CPU data ports, but it uses port `1e`
for its handshake. It commits words 1-2 with value 1 and words 3-4 with value
2. Then it uses value 4 as the transfer boundary.

The resident C51 routine at `811b..8138` is the receive side. It reads the
initial program address through the external ASIC cell `ff62`. It reads four
source words that start at `ff58` and calls the existing wait/handshake helper
at `23f0`. It writes each word to program memory with `BLDP`, increments the
destination, and writes `0300` to `ff57` as its acknowledgement.

Thus the resident and overlay protocols are different in framing and in the
C51 routine that consumes the words. But they are not different in physical
architecture. The two protocols use ASIC holding registers, and make the C51
do the program-memory writes.

## Emulator consequence

The bridge must have one shared ASIC download device with:

* CPU-side byte lanes `40..5e` and the command/status ports `18` and `1e`;
* DSP-side registers/status at `ff57`, `ff58..ff5f` and `ff62` (with the
  applicable direct-page aliases of the mask ROM);
* four-word commit state and real back-pressure;
* the C51 interrupt/event related to a committed group;
* acknowledgements that only the writes of the C51 generate.

For boards with the ROM enabled, remove the synthesized `queue_codec_boot`
table and the boot-word selection of the serial loader. For overlays, remove
the direct `load_program` publication. The correct completion is when the
original C51 gets to the requested program address after its own `BLDP`
operations.

## I-Modem reset control

The I-Modem gives the same four-word transfer protocol to its 386EX, but not
the 80C186EB GPIO register of the analog board. Its reset transaction that the
software can see is `out 18,ff`. The supervisor writes the destination to
`40/42` and sends `ff` to ASIC port `18`. After that, it uses values 1, 2 and
4 on that port for the two four-word banks and the completion. The current
`ImodemDsp.write` model already treats `18=ff` as reset. But it implements it
when it closes the native core and later constructs a preloaded core.

The correct model must make `18=ff` an ASIC command that asserts the C51 reset
output. The release and the loader entry must follow the supervisor/ASIC
handshake after it. They must not depend on the recognition of destination
`8000` or on a wait until the checksum. On the analog board, the `P1.1` net is
directly measured. On the I-Modem, a continuity test has not yet shown the
ASIC output pin and the physical routing of the reset net. Thus the software
command is certain, but its final pin is still open.

## Service-path wake signal

The physical wake signal is the reset net that we identified above: 80C186EB
`P1.1` (CPU pin 58) drives C51 `RS` (pin 127). Its falling edge resets the
C51. The release starts the C51 mask ROM. The reset setup of the mask ROM
installs the service-loader path and gets to it. This is not a separate,
unidentified ASIC interrupt pin. The CPU and C51 instruction streams
independently show the four-word windows and the 1/2/4 handshake that follow.

## Earlier supervisors: 5/25/94 and the SDL images to 3/13/98

We measured this on 2026-10-04 on the Metropoli BBS SDL images
(`firmware/legacy-usrobotics`), unpacked with `tools/unpack_sdl.py`. The flash
image has no boot block. Thus, before `courier_emu.rom.CourierRom` loads one,
you must graft the top 16 bytes of `IDSDL302.ROM` on to it and bypass its
supervisor identification check.

Each image has the same 1/2/4 holding-register transfer: two `out 0x18,1`, one
`out 0x18,2`, two `out 0x18,4`. In all of them, the DSP resident is a C5x image
for `0x8000`:

| Supervisor | Payload words | Found by |
|---|---|---|
| 5/25/94 | 32329 (32312 before `ffff` padding) | the 5/94 sequence below |
| 5/15/95, 6/9/95, 7/5/95 | 25549, 25568, 25620 | `CourierRom.dsp_download` |
| 11/1/95, 1/23/96 | 26535, 26601 | `CourierRom.dsp_download` |
| 3/13/98 | 27710 | `CourierRom.dsp_download` |

`dsp_download` finds nothing in the 5/25/94 and 6/10/94 images. They start with
the same routines but with a different call shape. Thus the regex does not
agree. The 5/25/94 sequence, in the code segment of the supervisor:

1. `0xc8d6f` calls `0xce220`, which sends eight words of `0x0083` to the DSP
   destination `0xfff8` (`mov ax,0xfff8; call 0xce25a`, then eight word writes
   through ports `40`/`42` and `out 0x18,1`/`out 0x18,2`). The boot-mode word is
   written explicitly. We do not know of later builds that do this.
2. `mov ax,0x8000; call 0xce25a` writes the destination to ports `40`/`42`,
   clears bit 1 of `0xff56`, writes `0xffff` to ports `18`/`1a`/`1c`/`1e`,
   waits, and pulses bit 1 back. Then it polls ports `18`/`1a` and `1c`/`1e`
   for `0xffff`.
3. `mov ax,0; mov cx,0xfc92; call 0xce323` transfers `0xfc92` bytes from
   `e3aa:0000` (physical `0xe3aa0`) through the four-word windows. Then it
   sends the checksum with `out 0x18,4`. The source segment is hard-coded at
   `0xce35c`.

The payload starts with `bc00 ae57 ffff be41 bc00 ae2a 0010`. This is word for
word the start of the 6/9/95 resident. But only 123 words agree at the same
index across all of the image.

This document names `out 0x1c,2` after the reset pulse for the 4.03
supervisor. It is not a version marker. The 5/94 code writes port `1c` with
`mov dx,0x1c; out dx,al`. A search for `mov al,2; out 0x1c,al` does not find
this.

### Use of the on-chip ROM tables

Question: do the early residents use the tables of the DSP mask ROM
([dsp-rom-content-analysis.md](dsp-rom-content-analysis.md)), where the later
residents have their own copies? Two simple tests say no:

* None of the residents, 5/94 to 3/98, contains the quarter-wave cosine table
  of the ROM (`0x40..0x240`, Q14) in the variants that we searched: cosine and
  sine at 256 to 4096 points, Q12 to Q15.
* The number of control-flow targets in the ROM table and helper range
  `0x40..0x615` is about 73 in 5/25/94, 47 in 5/95 to 7/95, 58 to 59 in 11/95
  and 1/96, and 102 in 3/98. `splk #0040` and `lar #0244` occur at about the
  same counts in all of them.

The two counts come from linear disassembly (`tools/c5x_disasm.py`), which
reads data as code. Thus the numbers have noise. Not tested: table copies that
are scaled, interleaved or packed, and what the code reads from
`0x40..0x5af`.
