# Remote feature-bit writer in supervisor 7.1.4

The analysis uses only the saved ROM. It does not send queries or writes to a
physical modem.

## Verified offline

We executed the real 80186 instructions with courier_emu.x86_interpreter.
The entry was CPU 8000:cd32, after the selection of the upstream receive
buffer. RAM 0x1a80 held the candidate frame, and SI/CX selected it. We
installed a valid feature record that encodes decimal 15 at RAM 0x748. We
intercepted the hardware EEPROM writer at 8000:da13, and it returned
immediately. Thus no physical EEPROM or emulated port activity was necessary.
The actual record decoder, bit setter and three-copy encoder executed without
modification.

Frame bytes 01 02 0a 02 25, and the address variant 03 02 0a 02 25, both
changed the feature record from 28 0f 12 (15) to 68 17 02 (31). Both got to
the EEPROM writer. Controls with P/F bit 0x10 set and subcommand 01 did not
write. The tested unnumbered branch did not examine the link state. This does
not prove that the upstream receive machinery accepts such a frame without a
live connection.

## Instruction path (file offsets)

- 0xcd32 calls the address/control parser 0xcc00, which consumes the LAPM address and control bytes.
- 0xcd39 tests control bit 0x02 and selects the unnumbered dispatch at 0xcd6b.
- 0xcd7a indexes the table at 0xcb86. Control 02 selects 0xc515.
- 0xc515 examines DL bit 0x10 through 0xc290. If it is set, the frame is rejected.
- 0xc53e recognizes the first payload byte 0x0a.
- 0xc554 uses the next byte as a subcommand index into table 0xc559.
- Subcommand 02 selects 0xc5a9, the set-bit handler. Subcommand 06
  selects 0xc59a, the clear-bit handler (not in the execution cases).
- 0xc5b9 consumes the packed selector 0x25: high nibble 2 is record 2,
  and low nibble 5 gives 1 << (5 - 1), or 0x10.
- 0xc5a9 ORs that mask into the decoded record.
- 0xc5b2 calls 0xd99e, then the encoder 0xd9c3 and the EEPROM writer 0xda13.
  This path bypasses the C8 validity/write-permission gate.

This traced inner path has no password or enable-key check. This harness did
not exercise the upstream link handling, frame admission, CRC/FCS and
escaping. These five bytes are a decoded frame candidate. They are not a
complete wire transmission, and they are not an AT command. If you type them
at the terminal, the result is not the same as the reception of this control
frame. For use on hardware, it is necessary to have a second endpoint that
can supply vendor control frames, or a different entry mechanism that is
verified independently.

This identifies a mechanism that agrees with USR remote activation. It does
not show which exact exchange the historical USR service used.

Run: PYTHONPATH=. .venv/bin/python artifacts/courier-714-221-flash-20261007/remote-analysis/check_handler.py

## V.42 transmitter to firmware boundary test

`tx_frame.c` links the existing static SpanDSP library of v90modem. It starts
V.42 with v42_restart(), puts 01 02 0a 02 25 into its control ring, and clocks
v42_tx_bit() into an HDLC receiver. The receiver gives the exact five octets
with ok=1 (valid FCS). We sent that decoded output to check_handler.run(). We
did not use a separate hardcoded frame. The firmware made the record encoding
for 31 and got to its EEPROM writer. Result: tx-to-firmware-result.json.

Build:
```
cc -I /opt/homebrew/include -I /Users/scottcryan/v90modem/spandsp-master/src tx_frame.c /Users/scottcryan/v90modem/spandsp-master/src/.libs/libspandsp.a -lm -o /private/tmp/courier-x2-tx-frame
```

Scope: the actual V.42 control queue, the bit-level HDLC encode/decode, and
the address/control dispatch of the firmware and the steps after it. The test
does not boot all of the Courier. It does not establish a modulated
connection. It does not exercise the HDLC/FCS receive logic of the Courier,
and it does not program the EEPROM. The write is intercepted. We did not
change production v90modem files, and we did not access a physical modem.
