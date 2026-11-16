# 3453C streaming DSP program monitor

This is a revision of the installed DSP monitor, built from the verified stock
2.3.33 image. The DSP handler and the overlay relocation are identical to the
first monitor build. This revision adds CPU code at physical 8A200. It also
corrects ATGU so that ATGU consumes U.

`ATGDssssEEEE` streams the inclusive range of DSP program words `ssss..EEEE`.
Each address must have exactly four hexadecimal digits, and the two addresses
must be in sequence in the range 0000..7FFF. For example, `ATGD12C012C7` reads
eight words. The output is:

```
DSPDUMP <four hexadecimal digits per word, with no separators>
DSPEND

OK
```

The CPU sends one 008A request for each word. Then it waits for a changed
reply sequence and tag 0072. During the bounded wait, interrupts service the
existing mailbox queue. If a request stalls, the monitor prints DSPTIMEOUT and
returns ERROR. The monitor rejects invalid inputs before it sends a DSP
request. Numeric ATG requests keep their stock path.

To capture a full program map as little-endian 16-bit words, use this command:

```
.venv/bin/python tools/3453c_monitor.py dump program 0000 7fff --fast \
  --output artifacts/3453c-dsp-memory-read-20261003/dsp-program-fast-0000-7fff.bin
```

Before the host publishes the completed binary, it examines the opening
marker, the exact word count, the hexadecimal encoding, the closing marker,
and OK. If a failure occurs, the host keeps a partial file that is marked
incomplete, and its metadata. The host does not replace existing captures. The
capture reads the active program address map. It does not switch MP/MC. It
does not guarantee that the lower region contains the internal mask ROM.

To rebuild, use this command:

```
.venv/bin/python tools/build_3453c_dsp_monitor.py \
  --output artifacts/3453c-dsp-bulk-patch-20261003
```

The manifest records hashes and 12 DSP plus 17 CPU isolated executable checks.
These checks cover the handler behavior, range parsing, ordering, sequence
wrap, output, register/stack restoration, and timeout. The hardware results
are in the flash log and in the hardware verification report. Call operation,
all overlay modes, and the long-term ownership of reserved RAM are not
verified.

## Hardware result

We flashed the revision successfully: all 5,888 blocks were acknowledged
without retries. The modem reset and answered AT. ATGU returned its cache,
then OK. An eight-word test at 12C0..12C7 agreed with the candidate. Then the
full 0000..7FFF capture completed in 69.581 seconds: 32,768 words / 65,536
bytes. Its SHA256 is
`a76f8c82a497a087af58741c395199e69f7923cd84ca9b0a73bab8ab7e1b329c`.
The dispatcher and all 68 monitor words of the full capture agree with the
candidate. For the evidence, refer to `hardware-verification.json` and
`flash-log.json`.
