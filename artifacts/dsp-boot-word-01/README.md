# Reading the DSP's boot-mode word off the board

At reset, the on-chip ROM reads data `0xffff` and dispatches on it. Bit 3
selects the parallel XF/BIO loader at program `0x072c` instead of the serial
loader at `0x06d4`. Bit 2 selects 16-bit pairs instead of 8-bit pairs. Refer to
[docs/dsp-boot-transport.md](../../docs/dsp-boot-transport.md).

The harness assumes `4` - serial, 16-bit. This probe measures what the ASIC of
the board supplies there.

## The kernel

The kernel is `build_boot_word_probe` in `courier_emu/dsp_probe.py`. It reads
one DSP data address 16 times and mails the values through the outbound
pattern of the resident - the same sender that sent the ROM dump.

It samples one address many times. It does not sweep a window, for two
reasons. First, the top data page is the mailbox window of the ASIC. Thus a
sweep can consume data that the firmware uses. Second, repetition is the
actual question: a strap that the ASIC holds reads the same each time, but
mailbox traffic does not.

## Rebuilding the commands

```sh
python -m courier_emu.probe_transport --reference IDSDL302.ROM \
    --boot-word --output /tmp/bootword
python tools/emit_ram_writes.py /tmp/bootword/diagnostic-ram.bin \
    --base 0x3000 --output artifacts/dsp-boot-word-01/commands
```

## Delivery

Board: ID_SDL v4.03d, supervisor 7.4.16, DSP 3.1.2, 20.16 MHz, on the DTE port
at **57600 8N1**.

1. `place.txt` - 2120 `ATGLK2W` word writes for `0x3000`-`0x408f`. These
   writes go to RAM only. A power cycle removes them.
2. `verify.txt` - `ATGLK2=` page dumps to examine the placement.
3. `arm.txt` - sets interrupt vector 8 to `0000:3000`. Then the `INT` bit of
   Timer 0 starts the monitor.

**On this unit, the vector that this overwrites was `8000:108F`.** To restore
it, use these commands:

```
ATGLK2W0020,108F
ATGLK2W0022,8000
```

Alternatively, do a power cycle. This restores all values.
