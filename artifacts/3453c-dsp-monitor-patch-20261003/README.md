# Experimental 3453C DSP monitor patch

We built this patch from the hardware-verified 2.3.33 XMF (DSP 2.1.41). This is a real patched
image, and its isolated handler tests pass. It is not a release that we tested on hardware.
We did not flash firmware while we developed it.

## Implemented commands

The patch keeps the existing ATG tag/data transport. ATGU now shows a cache of the monitor
reply as `DSPMON <tag> <value> <sequence>`. All fields are four hex digits.
The CPU intercepts monitor replies before the ordinary dispatch of DSP events. It
makes a snapshot of the cache with interrupts masked before it prints it.

| Input | Meaning | Response tag |
|---|---|---|
| `ATG00880000` | Identify the monitor. Returns D541 | 0070 |
| `ATG00890123` | Read DSP data word 0123 | 0071 |
| `ATG008A12C0` | Read DSP program word 12C0 | 0072 |
| out-of-range read | Returns error code 0001 | 0073 |
| `ATGU` | Show/initialize the cached reply | — |

The commands use DSP **word addresses**. Data reads have the limits 0100..03FF.
Program reads accept 0000..7FFF. Program zero shows the active program map.
It is not necessarily the internal mask ROM. This patch does not change MP/MC, and it does not add writes.

After the installation and the boot, this is a manual identification sequence:

```
ATGU
ATG00880000
ATGU
```

The final display must contain `DSPMON 0070 D541` and a sequence that is different
from the first display. A serial OK after ATG means that the request is queued. It does not mean that the DSP received it.
The host tool checks the sequence and the response tag. If they are not correct, it times out. It does not
accept an old cached value:

```
.venv/bin/python tools/3453c_monitor.py identify
.venv/bin/python tools/3453c_monitor.py data 0123
.venv/bin/python tools/3453c_monitor.py program 12C0
```

To dump an inclusive range of DSP word addresses, use these commands:

```
.venv/bin/python tools/3453c_monitor.py dump program 0000 7FFF --output dsp-program.bin
.venv/bin/python tools/3453c_monitor.py dump data 0100 03FF --output dsp-data.bin
```

The range command sends consecutive one-word requests with the existing
firmware patch. It does not need a new firmware build. For each word, it checks for a new
sequence and a matching response tag. It reports the progress and saves
little-endian 16-bit words. `FILE.json` records the address range, the byte order,
the word count and the SHA256. The two endpoints are included. Thus, the examples make
65,536 and 1,536 bytes respectively.

If a failure occurs, the completed words stay in `FILE.partial`, together with
`FILE.partial.json` with `complete: false` and the error. The tool writes a completed binary
only after all the words arrive. It does not overwrite existing output/metadata/partial files.
It refuses them. These are sequential live reads, not an
atomic snapshot. The DSP data can change while the dump runs. We
tested the range tool with simulated replies, not on installed hardware.

The tool first must find the DSPMON marker. Thus, on standard firmware, it stops before it
sends a DSP request. We did not send these commands to patched hardware.

## Layout changes

- Add 68 DSP words at program 75E0..7623. All known overlays end below 75E0.
- Redirect the DSP dispatcher instructions at 12C0 to the monitor. Tags that do not match
  replay the original comparison and return to the standard dispatcher.
- Move the stored bytes of overlay 6 from XMF CEB0 to XMF 50000
  (physical flash 90000). Keep its DSP destination and its contents.
- Update all five resident download call sites and the resident table row.
  Align the extents with the four-word transfer groups of the hardware.
- Add the CPU reply capture at physical flash 8A000 and the ATGU display at 8A100.
- Reserve CPU RAM 3FF00..3FF07 for the tag, the value, the sequence and the signature.
- Calculate again the boot payload CRC at XMF 0202. Keep the header CRC at 0200.

The boot CRC is the reflected CRC-16 polynomial 8408 with seed zero. The captured
boot code at FC00:1E50 checks 40000..401FF against [40200], and 40206..F7FFF
against [40202]. Before it makes changes, the builder reproduces the two standard stored values.

The assembler scan found no standard literal 8070/8072/8073 reply tags. The only
8071 word is an SAR instruction at program 479A. It is not a reply constant. This
is static evidence. It does not prove anything about all the standard tags that are generated dynamically.

## Validation and outstanding work

`manifest.json` lists the hashes, each edit and the execution results. The builder
verifies that the standard XMF loader metadata agrees with all four segments that it writes.
12 DSP executions cover these items: identification, data/program reads, range errors,
fallback to standard commands, rejection of a full queue without a partial reply, and
correct operation after overlay loads. 10 CPU executions cover interception, standard
pass-through, ignored tags, preservation of registers/stack and the cache display.
Pytest also checks the byte identity of the moved overlay and the detection of CRC corruption.

Before the hardware installation, these tasks are still necessary:

1. Find which code owns the reserved CPU RAM.
2. Validate the moved flash source through the complete hardware loader path.
3. Test the reset/recovery for this exact image.

The current emulator does not have the first-download mask-ROM protocol of the 3453C. Thus, these isolated tests cannot
replace a full boot validation. No update command or flashing script is
included.

To build again and test, use these commands:

```
.venv/bin/python tools/build_3453c_dsp_monitor.py
.venv/bin/python -m pytest -q tests/test_3453c_monitor_patch.py
```

`2_3_33-dsp-monitor.candidate.xmf` is the experimental output. Keep the captured
standard image as the recovery baseline.

## Guarded uploader

By default, `tools/flash_3453c_monitor.py` does only an offline preflight. It checks the
candidate against its manifest and checks the captured standard backup. It verifies the
image identity and the two boot CRCs, and it does not open a serial port. Its simulated
receiver test covers the full 5,888-block transfer and the monitor check after the reset.
We did not test the actual write path of the updater on hardware.

The `--flash` flag enables ATXMODEM option 2. It must have a new `--log` file.
The write handler commits after it receives and validates the first 1K. It cannot
validate the complete image before it erases.

> **CAUTION: A FAILED BOOT OR AN INTERRUPTED TRANSFER CAN MAKE IT NECESSARY TO RECOVER THE MODEM WITH PHYSICAL ACCESS.**
> The handler cannot validate the complete image before it erases the flash.

The uploader keeps its acknowledgement/error log. It does not force a reset
after an incomplete transfer. The limits of the experimental image above
stay. This uploader does not establish that a full boot is safe.

## First hardware installation

We flashed the candidate SHA256 598e1f1e506547d3e47b64ef3d72aa497bc304ee91c8d98dc7c22835e15c401b
after explicit approval from the user. All 5,888 blocks were acknowledged
without retries. The write path reported TRANSFER SUCCESSFUL (with the correct spelling,
which is not the same as the read path). The modem reset and answered AT. The identification returned
D541. Live program dumps of 12C0..12C7 and 75E0..7623 are identical to the candidate
byte for byte. A data dump of 012F..0132 also completed. Refer to flash-log.json and
hardware-verification.json.

The hardware showed a quirk of the ATGU parser. The display handler does not consume the U.
Thus, ERROR comes after a valid DSPMON record. The host tool accepts this exact
response. Other ERROR responses are still failures. This installed build still has
the quirk. We did not flash the firmware a second time. We did not test the call/overlay operation and
the RAM ownership over a long period.
