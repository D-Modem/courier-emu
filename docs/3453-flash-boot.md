# Running the 3453 normal firmware and bootmodem

The emulator accepts the captured **272 KiB bootmodem transfers**, the existing
**736 KiB XMF/main transfers**, and assembled **1 MiB whole-flash images**. `--power-on` starts at the real hardware reset vector.
Both captured firmware modes run their original 80186 AT parser and download
their resident through the recovered C52 ROM loader. No replacement AT parser
or pre-installed DSP resident is used.

Verified supervisors:

| Board | Normal | Bootmodem | DSP |
|---|---|---|---|
| B/C `4MBRYA8G1514` | 2.2.09 | 2.2.09 | 2.0.34 |
| C `5MBRZ16P0186` | 2.3.33 | 2.3.31 | 2.1.41 |

The hybrid's **2.2.09** uses the low-memory C52 architecture, including a
resident at program `1000`; it must not inherit the older 2.1.1/2.2.05 map.
Execution hooks are guarded by hashes of each supervisor's first 64 KiB,
not by a version string or by settings containing board credentials.

## Boot a capture directly

```sh
# B/C normal firmware
./courier run dumps/3453bc-firmware-read-2.2.09/firmware.bin \
  --with-dsp --instructions 4000000 --summary --at ATI0

# B/C recovery firmware: its split transfer is recognized automatically
./courier run dumps/3453bc-4MBRYA8G1514-bootmodem-read-20261014/bootmodem.bin \
  --with-dsp --instructions 4000000 --summary --at ATI0

# C normal and recovery firmware
./courier run dumps/3453c-5MBRZ16P0186-firmware-read-20261014/firmware.bin \
  --with-dsp --instructions 4000000 --summary --at ATI0
./courier run dumps/3453c-5MBRZ16P0186-bootmodem-read-20261014/bootmodem.bin \
  --with-dsp --instructions 4000000 --summary --at ATI0
```

All four reach the main loop, consume the command, emit `3368` and `OK`, and
report `dsp_bridge.bootstrap_match: true` with erased/default settings.
That product number is an execution check, **not a verified hardware identity**.
The bootmodem-only capture cannot switch to normal firmware: those bytes are
not in the transfer. The emulator reports an error instead of inventing them.

## Assemble a complete flash image privately

The settings region can contain a clear-text dial-security password. Keep it
and the assembled image in `.artifact-archives/`, which is Git-ignored.
The assembly tool refuses outputs outside that private archive, refuses to
overwrite an existing file, and creates the image with mode `0600`.

The captured B/C image has already been assembled at:

```
.artifact-archives/private-board-settings/3453bc-4MBRYA8G1514-20261014/whole-flash.bin
```

Reproduction (use a new output filename if the image already exists):

```sh
.venv/bin/python tools/assemble_3453_flash.py \
  --bootmodem dumps/3453bc-4MBRYA8G1514-bootmodem-read-20261014/bootmodem.bin \
  --normal dumps/3453bc-firmware-read-2.2.09/firmware.bin \
  --settings .artifact-archives/private-board-settings/3453bc-4MBRYA8G1514-20261014/f8000-fbfff.bin \
  --output .artifact-archives/private-board-settings/3453bc-4MBRYA8G1514-20261014/whole-flash-copy.bin
```

The assembled flash offsets are:

| Range | Size | Source |
|---|---:|---|
| `00000..3FFFF` | 256 KiB | First part of bootmodem transfer |
| `40000..F7FFF` | 736 KiB | Normal transfer |
| `F8000..FBFFF` | 16 KiB | Private settings capture |
| `FC000..FFFFF` | 16 KiB | Final part of bootmodem transfer |

The bootmodem DSP source uses a high alias of low flash. `FlashBus3453` now
models the EB `LCSST/LCSSP`, `UCSST/UCSSP` and `GCS2ST/GCS2SP` registers.
The firmware-derived GCS2 output drives flash A19: stop `800A` selects the
lower half normally; `000E` ignores the stop boundary and exposes low flash
through the upper-half alias. The downloader restores `800A` afterward.
RAM windows and the relocated peripheral block take priority; the transfer
sender's temporary copy-to-RAM window is also decoded. Aliases change on
register writes, not supervisor entry PCs. The flash array stays immutable.
Mode-specific cache keys prevent one mode's DSP table offsets leaking into
the other. The normal table's RAM diagnostic row is excluded, not mistaken
for another flash-resident DSP overlay.

## Full power-on from the reset vector

```sh
FLASH=.artifact-archives/private-board-settings/3453bc-4MBRYA8G1514-20261014/whole-flash.bin
./courier run "$FLASH" --power-on --with-dsp \
  --instructions 14000000 --summary --at ATI0
./courier run "$FLASH" --power-on --with-dsp --console
```

The CPU starts at **FFFF:0000** (physical `FFFF0`), executes the captured
16 KiB reset/recovery loader, programs its peripheral registers and computes
both normal-image CRCs in guest code. There is **no checksum bypass**. On the
captured images, selection completes after **8,290,853 instructions**; allow
about 14 million instructions for CRC checking, supervisor initialization,
DSP download and an AT reply. The private B/C image returns `5608` and `OK`.

The loader selects normal firmware only when its CRCs pass and input port
`14` bit `40` is high. A bad application CRC—including a damaged normal
supervisor—selects bootmodem instead. The normal supervisor's execution hash
is checked only when it is actually selected; corruption does not prevent
recovery from starting. The reset loader itself is hash-guarded.

`flash.power_on` records actual reset-vector execution, the guest's CRC result,
the sampled selection input (when reached), selected mode and loader exit
instruction count. Initial selection is separate from subsequent `ATZ!!`
entries in `flash.mode_switches`. Both families pass normal startup, valid-CRC
recovery-input selection, damaged-image fallback and AT replies with matching
DSP bootstrap. A cold B/C startup also passes an `ATZ!!` round trip.

`--power-on` and `--firmware-mode` cannot be combined: the guest loader decides
the mode. A bootmodem-only transfer can also start with `--power-on`; missing
normal flash is represented as erased, and the real header-CRC failure causes
recovery selection after 5,912 instructions. This simulates an absent normal
image, not the connected board's actual uncaptured contents.

For selection-input experiments, a raw `--port 0x14=0xffbf` also overrides
other inputs and may interfere with later startup, particularly with erased
settings. The regression models a momentary low selection input, released
after the loader samples it, rather than holding a whole-port override forever.
This does not establish the physical front-panel wiring for every board.

## Select a mode and switch between them

```sh
FLASH=.artifact-archives/private-board-settings/3453bc-4MBRYA8G1514-20261014/whole-flash.bin

./courier run "$FLASH" --firmware-mode normal \
  --with-dsp --instructions 4000000 --summary --at ATI0
./courier run "$FLASH" --firmware-mode bootmodem \
  --with-dsp --instructions 4000000 --summary --at ATI0

# Round trip through the original guest ATZ!! handlers
./courier run "$FLASH" --firmware-mode normal \
  --with-dsp --instructions 10000000 --summary \
  --at 'ATZ!!' --at ATI0 --at 'ATZ!!' --at ATI0

# Interactive AT console
./courier run "$FLASH" --firmware-mode bootmodem --with-dsp --console
```

The whole-flash default is normal. The JSON `flash.firmware_mode` records
the final mode and `flash.mode_switches` records the transitions. Both
families pass a normal → bootmodem → normal regression with replies after
each switch and no unconsumed input. With the private B/C settings, `ATI0`
returns `5608` in both modes. `ATI7` also completes in both modes, including
the captured serial number.

## Scope and remaining limitations

* Without `--power-on`, runs still start at the selected supervisor entry.
  With it, the captured reset path and CRC-driven dispatch are now validated.
  This does not make all board peripherals or electrical reset timing faithful.
* The reset loader and `ATZ!!` execute their original guest handlers. Flash
  mapping now follows chip-select registers. Entry trampolines select only
  the hash-guarded front-end ABI, not memory aliases. This covers the captured
  flash/RAM windows, not every possible device attached to all eight GCS lines.
* The DTE front-end remains the harness's UART-ISR/attention-handoff model.
  Its callback, framing, parity and command-state addresses are selected per
  image. Queued lines are held until the previous parser invocation finishes.
  CPU execution traces retain actual physical PCs, not canonical hook aliases.
* Flash autoselect now gives the captured identities: B/C `20-22EC`, C
  `C2-22D6`. Command writes do not modify the array, and unarmed RAM-probe
  writes are ignored. Programming/erase sequences are explicitly unsupported.
* The ASIC now publishes DAA identity over the normal mailbox after native
  codec PLL/link initialization. The firmware receives tag `7B` and prints
  `0013` on the healthy model; no ATI string or revision RAM cell is patched.
  `--daa-codec-revision 0` models an invalid ASIC identity (such as the faulty
  connected C's report), **not the electrical fault itself**. This does not
  yet validate the complete codec calibration, hook control or audio path.
* Captured 3453 profiles now default to modeled External straps (code 7,
  capability `22`), rather than the legacy Internal default. The exact physical
  choice between codes 7 and 13 is not verified. Private B/C's newest valid
  settings record (version 32) has an erased product-ID override, explaining
  its blank normal-mode ID; older versions 29–31 contain `00345303`. No record
  or formatter output is patched. RAM `1C04` gates the ID line, not its value.
  See [product IDs and calibration](3453-product-ids-and-calibration.md).
* XMODEM transfers remain unvalidated. Flash updates are unsupported by the
  read-only bus; no captured image is modified. Do not infer transfer/update
  support from a working recovery console/menu.
* Carrier negotiation, V.34/V.90/V.92 and end-to-end calls remain unverified.
  An initial offline B/C exchange probe aborted with zero board ticks and
  no line seizure. The relocated mailbox-ISR IRET addresses (including the
  no-message return) are now translated for every captured profile, restoring
  DSP-paced ticks. A subsequent `ATX3S7=3` / `ATD5551212` probe seizes and
  releases the modeled line but decodes no digits, downloads no call overlays
  and ends in `NO CARRIER`. This is not successful dialing or negotiation.
  Calibration, DSP memory/overlay behavior and audio timing still need work.
* Standalone XMF images lack the reset-loader services used by full `ATI7`;
  use an assembled image for the complete identity query.
* The C whole-flash round-trip tests use **erased synthetic settings**. We have
  not captured this particular C unit's settings during the current session.

Evidence is in `artifacts/bootmodem-emulator-check-20261014/`. Regressions:

```sh
.venv/bin/python -m pytest -q tests/test_3453_flash_images.py \
  tests/test_3453c_boot_rom.py tests/test_3453c_uart_status.py \
  tests/test_machine_map.py tests/test_cli_link.py
```
