# Configuration command analysis: Courier 7.1.4 / DSP 2.2.1

Source: courier-board.rom in this directory. The addresses below are file offsets.
The CPU physical addresses are the file offsets plus 0x80000.

- The G handler at 0x24f0d must have the literal LK2 prefix. If the prefix is different, it returns with carry set at 0x24ee4.
- The N subcommand at 0x24ffc sets bit 0 of RAM byte 0x025e and returns with carry clear. Command: ATGLK2N.
- The C selector table at 0x0d8d7 is decimal 10, 8, 23, 39, 56, 74.
- C8 selects record 2, that is, the three encoded bytes at RAM 0x0748.
- The initialization at 0x00908 reads record 2. At 0x00933, bit 0x10 of the record sets bit 0x20 of the runtime capability byte [0x0893].
- IMPORTANT: The C write handler calls the record decoder at 0x0d8ed. If carry is clear, it branches to failure at 0x0d8f0. The decoder returns carry clear for a valid record. Thus, ATGLK2N followed by ATC8=31 cannot overwrite a valid provisioned record.
- Only after the validity gate of the record fails does 0x0d8f2 test the permission bit. The permitted write path encodes all three copies at 0x0d9c3. Then it keeps the changed EEPROM words at 0x0da13.
- In this build, the G subcommand dispatch has no W memory-write case. Its = and R cases read memory. Its O case writes an I/O port. Do not use ATGLK2W recipes from other builds again.

This analysis used only the saved ROM. We did not send configuration writes to the modem.
