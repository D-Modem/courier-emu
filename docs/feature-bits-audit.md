# Audit of the Courier feature bits

Written in ASD-STE100 Simplified Technical English.

This document gives the result of an audit of the feature record (record 2,
`ATC8`) in the Courier supervisor firmware. It tells which bits have an
effect, in which builds, and which builds let a host change them. D-Modem's
x2 upgrade host (`AT+X2UP`) writes this record.

## 1. Images

The images came from `firmware/legacy-usrobotics/` and from the board
captures in `artifacts/`. `tools/unpack_sdl.py` made a flash image from each
DOS flasher (`SDL.EXE` and others). The outer `.EXE` files are ZIP and ARJ
self-extractors; 7z and unar open them. A DOS emulator is not necessary.

| Supervisor | Date | Images | Upgrade handler | x2 at power on |
| --- | --- | --- | --- | --- |
| 6.2.0 to 6.5.4 | 05/94 to 09/96 | 13 flashers (`SDL0196` ... `SDL0920`, `V34PLUS`, `SDL_CS*`) | No | Not present |
| 7.1.4 | 02/25/97 | `courier-714-221-flash-20261007` | Yes | Record 2 bit 5 |
| 7.3.14 | 03/13/98 | `IDSDL302.ROM`, `courier-board-21210-capture-01`, `courier-2806-25mhz-flash-20260912` | Yes | Record 2 bit 5 |
| 7.4.16 | 04/30/98 | `SDL0430`, `SDL0430N`, `SV_49`, `courier-board-11430-flash-20260914-02` | Yes | Always on |
| 7.6.7 | 12/02/98 | `V90SDL` (`SDL1202I`), `courier-board-11430-flash-20260914-unit2-02` | Yes | Always on |
| 7.4.16, ID_SDL 4.01 to 4.03 | 04/30/98 | `ID20*`, `ID25*`, `courier-board-21210-capture-403` | Yes | Always on |

The ID_SDL images are not U.S. Robotics firmware. They are "Extended USR
SDL" by Igor Diagilev (Khabarovsk), and `ATI7` shows "NOT For Sales". See
[the firmware lineage map](firmware-lineage.md). The strings of
`IDSDL302.ROM` also name this author, but its feature code is the same as the
stock 7.3.14 code.

## 2. From the record to the runtime byte

At power on, the supervisor decodes record 2 and sets bits in a runtime
feature byte. The address of the byte changes with the build.

| Build | Power-on code | Runtime byte |
| --- | --- | --- |
| 6.5.4 | `08b8` | `0871` |
| 7.1.4 | `0908` | `0893` |
| 7.3.14 | `08ea` | `089d` |
| 7.4.16 | `08f1` | `0791` |
| 7.6.7 | `08f3` | `0795` |

All builds use the same map:

| Record 2 bit | Value | Feature | Runtime bit |
| --- | --- | --- | --- |
| 1 | 1 | HST | `04` |
| 2 | 2 | Fax | `08` |
| 3 | 4 | Terbo (V.32terbo) | `40` |
| 4 | 8 | V.FC and V.34 | `80` |
| 5 | 16 | x2 (and V.90 in builds that have it) | `20` |

The 6.x builds do not read bit 5. No build reads bits 6, 7 or 8. Other code
sets the runtime bits `01`, `02` and `10`; the record does not control them.

## 3. Code that overrides the record

These steps occur after the records are decoded:

- **HST.** The supervisor sets runtime bit `04` (HST) when a hardware byte
  has neither bit `40` nor bit `80`. The probe at `096f` (7.1.4) sets this
  byte, not a record. The step is at `0549` (7.1.4), `052b` (7.3.14) and
  `0532` (7.4.16, 7.6.7). Most 6.x builds from 11/95 have it too. Thus, on the
  board that was examined, HST is always on.
- **x2.** Supervisor 7.4.16 and 7.6.7 set runtime bit `20` (x2) at `0519`
  with no condition. Thus, in these builds, record 2 bit 5 has no effect.
  7.1.4 and 7.3.14 do not have this step.
- **ID_SDL.** The ID_SDL builds also change the x2 test of the power-on code
  (`091c`) from `74 05` (`je`) to `90 90` (`nop nop`). This change has no
  effect, because of the step at `0519`.

## 4. Effects that were measured

The emulator ran each image with an EEPROM from `tools/feature_nvram.py`
(board ID 7, default DIP switches).

### 4.1 ATI7

Supervisor 7.3.14 (`courier-board-21210-capture-01`):

| Record 2 | Options line |
| --- | --- |
| 0, 1, 2, 3 | `HST,V32bis` |
| 4, 7 | `HST,V32bis,Terbo` |
| 8, 9, 10 | `HST,V32bis,Terbo,VFC` |
| 12, 15 | `HST,V32bis,Terbo,VFC,V34+` |
| 16 | `HST,V32bis,x2,V90` |
| 24 | `HST,V32bis,Terbo,VFC,x2,V90` |
| 31 | `HST,V32bis,Terbo,VFC,V34+,x2,V90` |

7.1.4 gives the same lines for 0, 15 and 31, but without `V90`. `V34+` needs bit 3 and bit 4.
The fax line (`Class 1,Class 2.0`) and `AT+FCLASS=?` (`0,1,2.0`) did not
change with bit 2.

Supervisor 7.4.16 and 7.6.7 show `x2,V90` with record 2 set to 0.

### 4.2 Speed limit (`&N`)

Supervisor 7.3.14. The table gives the highest `&N` value that the
Courier accepts. A higher value gives `ERROR`.

| Record 2 | Highest `&N` |
| --- | --- |
| 0 | 9 |
| 4 | 10 |
| 8, 12 | 16 |
| 16, 31 | 39 |

Thus a Courier with no x2 bit gives `ERROR` for an x2 speed, for example
`&N39`.

### 4.3 Calls

Supervisor 7.3.14 called D-Modem's `courier_peer` (`AT+MS=X2`) with
`tools/probe_v90modem_closed_loop.py`:

| Record 2 | Result |
| --- | --- |
| 31 | `CONNECT 49333/ARQ/x2/LAPM/V42BIS` |
| 15 | The Courier sent no x2 marker. D-Modem went to V.34. The V.34 start-up failed (a known limit of the emulator). |

Thus, in 7.3.14, record 2 bit 5 controls x2 in the call, not only the text
of `ATI7`.

## 5. Who can write the record

| Build | `ATC8=` (after `ATGLK2N`) | Remote (LAPM UI type `0a`) |
| --- | --- | --- |
| 6.x | Only when the record is not valid | No handler |
| 7.1.4 | Only when the record is not valid | Yes, with no permission bit |
| 7.3.14 and later | Only when the record is not valid | Yes, when S30 bit 0 is set |

In 6.5.4, the record decoder (`ec59`) has these callers only: the power-on
code, `ATY14` (`7f6e`) and the `ATC` handler (`ec21`). Its LAPM code
accepts UI frames of type `08` and of types `40` and `60`, but not of type
`0a`. Thus the features of a 6.x Courier cannot be changed from the line.
The `ATC` path cannot change a valid record. It is for a new board.

## 6. Results for the x2 upgrade host

- The host has an effect on x2 only on supervisor 7.0 to 7.3.x. In 7.4.16
  and later, x2 and V.90 are always on. A host call changes the record but
  not the modem.
- A 6.x Courier must load 7.x first.
- The host can also set bit 3 (Terbo) and bit 4 (V.FC and V.34) on all 7.x
  builds. These bits change `ATI7` and the speed limit. Whether the DSP code
  of a board that was sold without these features can run them is not known.
- Bit 1 (HST) has no effect on the examined board, because the hardware
  probe sets HST.
- The effect of bit 2 (fax) was not found. The supervisor reads runtime bit
  `08` in about nine places (7.1.4), mostly together with hardware bit
  `40`. These places were not traced.

## 7. Not examined

- Boards with hardware byte bit `40` or `80` (models without HST).
- The code that reads runtime bit `08` (fax).
- A V.34 call. The emulator does not complete the V.34 start-up with
  D-Modem.
