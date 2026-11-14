# CPU–DSP parallel mailbox: board comparison, 2026-09-07

## Exact long-immediate confirmation, 2026-09-09

The new [capture](../artifacts/ndx-long-1234-20260909/frame.txt) from the
attached Courier confirms the existing model for `lar ar0, #1234` (hex).
ATI7 again reports supervisor 7.4.16 and DSP 3.1.2. Before each load, the minimal probe seeds
ARCR=`eeee` and INDX=`dddd` independently. It clears and then sets
PMST.NDX, and it returns the registers through the verified tagged mailbox.
The PMST and AR0 readbacks are controls. `9209` identifies this probe.

| NDX | PMST | AR0 after LAR | ARCR | INDX |
|---|---|---|---|---|
| Clear | `00b0` | `1234` | `1234` | `1234` |
| Set | `00b4` | `1234` | `eeee` | `dddd` |

The nine-word frame passes its count and its checksum (`a908`). Before the execution, we read back the 4256-byte
supervisor RAM image byte for byte. The DSP
kernel is 160 bytes. After the watchdog recovery, AT answered, vector 8 was
restored to `8000:108f`, and T0CON read back as `8021`. We did not write to the flash or to the stored
settings. This is a standalone instruction test. It is not a measurement of a live call.
**No change to the C5x behavior was necessary.**

The [artifact manifest](../artifacts/ndx-long-1234-20260909/manifest.json)
records the hashes, the identity, the decoded samples and the recovery. The raw serial traffic,
the RAM readback, the binaries, the labels and the separate offline result are in the same location.
The tests keep the existing model, replay the exact captured binary,
validate the raw frame and compare the upload with its readback. The replay masks only PMST
AVIS, as in the earlier captures. It does not mask NDX.

To reproduce the result from the repository root, use a **new** output directory:

```sh
.venv/bin/python artifacts/ndx-long-1234-20260909/build.py /tmp/ndx-long-new
.venv/bin/python artifacts/ndx-long-1234-20260909/run-board.py /tmp/ndx-long-new /dev/cu.usbserial-11420
.venv/bin/python -m pytest tests/test_dsp_board_ndx.py tests/test_mailbox_protocol.py tests/test_asic_ports.py -q
```

The runner must have the measured firmware identity. It verifies the RAM before
it arms Timer 0, and it does not overwrite an existing frame. The name of the serial device
can change when you connect it again. On macOS, the offline execution must have the Unicorn JIT
permission.

## Earlier findings

We now know the cause of the NDX failure. Two faults hid each other. The core
did not do the AR0 compatibility side effects, and PA7 writes incorrectly made a
download-ready status. When we fixed only NDX, the firmware entered that false
ready path and repeatedly downloaded `FFFF`, also into its interrupt vector
area. This was not evidence of incorrect `*0+` addressing.

## Fresh hardware measurements

The connected board at `/dev/cu.usbserial-1420` reports ID_SDL 4.03d,
supervisor 7.4.16, DSP 3.1.2, 20.16 MHz. We uploaded the two probe images only
to RAM, and we read them back byte for byte before the execution. The two images returned complete
frames with checksums. After this, AT answered, vector 8 was `8000:108F`, and
T0CON was `8021`. We did not write to the stored settings or to the flash.

`artifacts/ndx-addressing-02/` contains 47 words from a probe with a unique marker:

- With NDX clear, the direct, indirect, short-immediate and long-immediate LAR AR0
  all copy the loaded value to ARCR and INDX.
- With NDX set, those registers keep their independent sentinels.
- SAMM AR0 does **not** copy to ARCR or INDX with either polarity.
- The tested indirect addressing modes without ARP update agree with the core.
  These include indexed addition/subtraction and reverse-carry addressing.

`artifacts/dsp-status-03/` contains 23 more words:

- PA7 reads `0002` before and after writes of `0200`, `0300` and `0000`.
  These writes do not make an incoming-download readiness, and they do not destroy bit 1.
- With NDX clear, the MAR increment/decrement of AR0 copies the result to ARCR/INDX.
  With NDX set, it does not change them.
- A load of AR1 does not copy to ARCR/INDX. Its related first AR0 sample
  is the incoming bootloader state, and the emulator assertions do not include it.

The original `artifacts/ndx-probe-01/manifest.json` has incorrect decoded
fields for the first direct load. Its raw frame supports the later notes,
not those fields. The new captures remove that ambiguity.

## Implementation

The core implements the AR0 side effects of LAR and ARAU, and it keeps the MMR writes
independent. On the measured ROM-board profile, PA7 writes acknowledge flags.
They do not replace the full register. The hardware observations with an empty window
support the correction. An acknowledgement with a populated download window must still
have its own measurement. We do not claim universal semantics for all unused PA7 bits.

Also, the bridge had the return handshake in the reverse direction. PA7 bit 1 means that the DSP
can send. CPU port 1C bit 1 means that a reply is waiting. The CPU acknowledgement sets
the DSP-ready bit again. The related stream bit uses the same opposite
polarity. CPU bit 0 means that the input holding register is free, but DSP PA7
bit 0 means that a CPU message is pending.

For the measured ROM profile, the bridge now commits the staged CPU tag/data
on the bit-0 write to 1C. It returns the readiness from the actual latch, and it reads
the status from one authoritative I/O value. It does not OR old mirrors back
in. The CPU input and the DSP output have separate holding registers. A read of
an acknowledged output still returns the last word. The legacy image profiles
keep their existing bridge behavior.

`dsp_messages_taken` is a count of **CPU acknowledgements of DSP replies**.
Older notes incorrectly use it as a count of messages that the DSP consumed.
The actual DSP receive acknowledgements are writes of `1` to PA7. The new
round-trip regression checks those directly.

## End-to-end command check

`artifacts/mailbox-confirm-04/` repeats `07, 2D, 07` on the recovered board.
The reply holding registers are `0031:0000` at all times: 07 makes that
reply, and 2D does not change it. The emulator now reproduces the same
sequence after it runs the real boot ROM and the resident initialization. It uses
CPU-side byte writes, commit, ready polling, reply reads and acknowledgement.
It no longer needs a fixture caller to enter the dispatcher directly.

`tests/test_dsp_board_ndx.py` replays the two exact captured DSP binaries. It
checks the booted round trip, the commit boundary, the backpressure, the held reply
and the independent input/output registers. The instruction comparison masks PMST AVIS.
Its difference in the reset state is outside these assertions.

The full dialing results are recorded separately below. When these mailbox
queries agree, this does not prove a working call, the codec levels or all the ASIC registers.
