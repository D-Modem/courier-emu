# Courier 2806 live ASIC probes — 2026-09-13

ATI7 confirmed the target: 25 MHz, supervisor 7.3.14, DSP 3.0.13, serial 22AEB36ACKND. The adapter is /dev/cu.usbserial-FT4TQOFT at 115200 baud.

## Flash

We read 24 pages two times (48 reads): offsets 0000, 4000 and ff00 in each 64 KiB region from 80000 through fffff. Each repeated page was identical and agreed with the flash capture of 2026-09-12. This supports the current flat mapping. But it does not exclude a dormant bank selection. We did not write a bank register. Repeated blank pages do not show address aliasing.

## ASIC CPU port space

We did two idle passes. These passes excluded the mailbox ports 1c, 1e, 58–62 and all of the download window 40–62. All sampled odd ports below 80 returned zero. Each even port from 80 through fe returned its own address. Each odd port above 7f returned zero. This agrees with the decode boundary that we saw before, with an undriven bus above it. It does not show useful registers there. The zero odd reads agree with the mapped eight-bit CPU interface. But the probe alone does not prove the bus width.

Changes between passes:

{}

These are monitor observations, not direct CPU instruction probes. Thus, behaviour that is specific to the monitor is still a limitation. We did not measure a mailbox handshake, DSP-side aliases, the clock frequency or an interrupt route. We did not send configuration, RAM, ASIC register or flash writes, resets, calls or self-tests. The last AT returned OK.

The first port attempt stopped on an incomplete last line that ended at port 8b. ports.py repeated the two passes and saved each result one at a time. results.json contains the completed passes and the raw replies. The earlier serial.json records the echo-only attempt before we corrected the DIP switches.
