# Courier `/dev/cu.usbserial-11430` capture comparison

We captured this read-only on 2026-09-14. The flash collector sent only `AT`, `ATI7`,
and `ATGLK2` reads. All 2,048 256-byte pages agreed between the two reads. No
attempts failed. After the sweep, the two flash anchors agreed again.

## Identity

- Product: Australia External
- Serial: `0409550000376154`
- Clock: 20.16 MHz
- Supervisor: `061-7.4.16`, dated 1998-04-30
- DSP: `3.0.13`, dated 1998-03-13
- ATI0 product code: `5607A`
- ATI1 ROM checksum: `B60A`
- Flash SHA-256: `85665f6db32b06b256dd70d631be3e0e0a120890b31b04c0f571f72497a22bcb`
- Reset entry: `FC00:0FE7`

## Closest image

The decoded body of `SV_49.XMD` is the closest known image: 518,091 of
524,288 bytes agree (98.8180%). The comparison divides clearly into these areas:

| Flash offsets | Interpretation | Different bytes |
|---|---|---:|
| `00000..3ffff` | application and DSP area | 0 |
| `40000..77fff` | supervisor area | 4 |
| `78000..7bfff` | late/erased area | 0 |
| `7c000..7f7ff` | board boot block | 6,190 |
| `7f800..7ffff` | parameters and vectors | 3 |

The four bytes in the supervisor area are at `77ffc..77fff`. This is the checksum
location that the downloader programs. Thus, the installed application and DSP payload is `SV_49`,
byte for byte. The important difference is the board/regional boot block.

For a wider context, the full flash has these identities with other hardware captures:

- 76.6766% identical to the previous 20.16 MHz IDSDL 4.03 hardware capture.
- 48.5929% identical to the prior 20.16 MHz stock 3.02 hardware capture.
- 47.9553% identical to the 25 MHz stock hardware capture.

## RAM and stored settings

Two passes of the lower RAM captured `00000..0feff`. 46 live bytes changed. The known
18-byte EEPROM-cache offsets were stable, but all zero. Thus, that decoder does not
find usable records in this firmware variant. This is not a dump of the
physical 93C66 EEPROM.

Two passes of the upper window captured `10000..1ffff`. 45 live bytes changed. Five
stable sampled pages agreed exactly with the related pages of the lower RAM. The
page near address zero was different only in active working bytes. This is strong
support that the upper window is a mirror of the lower RAM, not more memory.

The `ATI5` formatter of the modem shows a stored profile at 115200 baud, 8N1,
tone dialling, with `S0=2`. The stored phone numbers and the stored command are empty.
`ATY14` shows `000,000,031,007,015,014`. `ATY15` shows these DIP switch positions:
OFF, OFF, ON, OFF, ON, OFF, OFF, ON, ON, OFF.

## NVRAM limitation

In this repository, no read-only AT command that we proved can directly dump all 256 words
of the physical 93C66 EEPROM of the board. The RAM images and the `ATI5` output keep
the accessible views of the settings. They do not claim to be a full EEPROM image.
