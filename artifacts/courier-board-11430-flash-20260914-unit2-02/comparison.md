# Second Courier `/dev/cu.usbserial-11430` capture comparison

We captured this read-only on 2026-09-14. All 2,048 flash pages agreed between the two
reads. No attempts failed. After the sweep, the anchors agreed again.

## Identity

- Product: Australia External
- Serial: `21OWZ849PS95`
- Clock: 20.16 MHz
- Supervisor: `061-7.6.7`, dated 1998-12-02
- DSP: `3.1.2`, dated 1998-09-09
- ATI0 product code: `5607B`
- ATI1 ROM checksum: `2F89`
- Flash SHA-256: `d68f6fd8c1a2fcc047f88d05ec9f581b2186d660b93e3bb3866f433820c1cc7e`
- Reset entry: `FC00:0FE7`

## Closest distributed image

The decoded `firmware/legacy-usrobotics/SDL1202I/V90XX.XMD` body is the closest
known image: 518,091 of 524,288 bytes agree (98.8180%).

| Flash offsets | Interpretation | Different bytes |
|---|---|---:|
| `00000..3ffff` | application and DSP area | 0 |
| `40000..77fff` | supervisor area | 4 |
| `78000..7bfff` | late/erased area | 0 |
| `7c000..7f7ff` | board boot block | 6,190 |
| `7f800..7ffff` | parameters and vectors | 3 |

The four bytes in the supervisor area are the normal programmed checksum bytes at
`77ffc..77fff`. Thus, the installed application and DSP payload is the same as
`V90XX.XMD`, byte for byte. The important difference is the Australian boot
block.

## Difference from the first Australian unit

The two Australian units have an identical boot block, late/erased region,
parameters, and vectors. But they have different firmware generations: only
47.8439% of the complete images agree. The second unit is different from the first
in 254,291 bytes in the application/DSP area and in 19,157 bytes in the supervisor
area.

## RAM and settings

Two passes of the lower RAM captured `00000..0feff`. 39 live bytes changed. Two upper
passes captured `10000..1ffff`. 33 live bytes changed. Five stable sampled
upper pages agreed exactly with the related lower pages. This again supports a
mirror, not more memory.

The legacy 18-byte EEPROM-cache offsets were stable zeros. Thus, that decoder does
not find valid records on this Australian firmware. This is not a complete
dump of the physical 93C66 EEPROM.

The `ATI5` display of the modem shows these settings: 115200 baud, 8N1, pulse dialling, `M1`,
`X7`, `&X0`, and `S0=2`. The phone-number slots and the stored command are empty.
`ATY14` shows `000,000,030,007,031,014`. The DIP switches are OFF, OFF, ON, OFF,
ON, OFF, OFF, ON, OFF, OFF.
