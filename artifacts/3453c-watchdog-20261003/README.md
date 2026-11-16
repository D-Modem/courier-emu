# 3453C watchdog clock investigation

Two differences between the board model and the CPU interrupt model caused the immediate watchdog abort.
The fix did not need a change to a C52 opcode or to the interrupt recognition.
The C52 serial clock and the stock codec setup already execute.

## Recovered watchdog behavior

The original firmware increments byte `[0176]` in the mailbox INT0 handler at
physical `67704`. At 25 interrupts without a reset, it sets `[0694]=80`.
The line-qualification routine tests that flag and returns an error.

The installed vector table gives the answer:

| Vector | Physical handler | Role |
| --- | --- | --- |
| `0C` | `67700` | DSP/ASIC mailbox service; raises the watchdog counter |
| `0F` | `58693` | External board tick; resets the counter at `58750` |
| `08` | `58DD4` | Internal timer-0 handler, just EOI/IRET at this point |
| `12` | `7A925` | DTE timer-1 handler |
| `13` | `7A9EB` | DTE timer-2 handler |

The prior codec audit suggested that the missing watchdog reset was the delivery of the internal CPU timer.
This suggestion was too wide. When you enable those interrupts, the
DTE/loader paths change, and the necessary external tick still does not arrive.

## Fixes

1. Select `EbInterruptController` for the 2.3.x supervisor. The legacy
   controller with DMA used consecutive IMASK positions, with INT3 at
   bit 6. The 80C186EB has a reserved bit 1, serial at bit 2, INT4 at bit 3,
   and INT0–INT3 at bits 4–7. Thus, a firmware mask can disable INT2
   and keep INT3 enabled. The old model incorrectly blocked the tick.
2. Recognize the IRET of the mailbox ISR at `677F1`. The legacy service marker for the injected mailbox
   recognized only the return addresses of older firmware. It stayed
   asserted after the 3453C handler returned, and it suppressed the later board ticks.

The two fixes keep the mask handling of the firmware. They do not clear the
watchdog flag or counter of the guest directly. The original handler of the guest does the reset.
The local Intel manual documents the controller map:
[270830-003](../../docs/270830-003%2080C186EB%2C80C188EB%20Microprocessor%20Users%20Manual-Feb95.pdf),
Table 4-1 and Figures 8-4/8-8.

## Execution evidence

- `baseline.json`: 3 million instructions before these fixes. There are no hits of the watchdog
  reset handler, one qualification abort, and `[0694]=80`.
- `eb-controller.json`: 10 million instructions with the fixes. There are **357 hits of the tick
  reset handler**, no hits of the qualification abort, and `[0694]=00`. Hook stays
  asserted while the firmware qualifies the line. In this standalone diagnostic with a disconnected line,
  the codec reads increase from zero to 27.
- `interrupts.json`: a historical diagnostic that enables the internal timer
  interrupts and keeps the old timer-read behavior. It fails during a
  DSP overlay transfer at BMAR `00B4`. This is not the selected fix.
- `full-real.json`: a historical diagnostic that enables the internal timer reads and
  interrupts with real delays. The resident boots and clocks, but the DTE input
  stays in a queue in a wait before the command. Again, this is not the selected fix.

`timer_interrupts` in the machine result is a historical counter. It also
includes the injected mailbox-service interrupts. Thus, it is not proof that the
watchdog tick came from an internal timer. `ticks` and the PC watch at
`58750` show the external tick and the actual firmware reset.

The full I-modem retest runs 150 million analog and 400 million I-modem
instructions. The analog model sends **6,791 board ticks**. Hook asserts
at instruction 2,308,756 and releases at 15,290,095. With this CPU timebase, this is about **3 seconds**
later. The native codec clocks **222,509 frames** at
7,200 Hz. There is still **no CONNECT, incoming call or payload delivery**.
The transmitted PCM stays silent. The call qualification/transport is still
not complete, although the watchdog clock is corrected.

## Remaining C52/codec evidence

`codec_read_probe.py` isolates the serial read sequence of the original resident.
It directly loads and initializes the stock resident, and it supplies a connected,
off-hook external line. Then it sends the native mailbox command `7C:0000`.
That command requests Si3034 register 12 (`2CFF`). The documented expected
status of the model is `44` (frame detect plus modeled loop current).

The initial probe saw zero at each readback handler, and the pending cell
`012F=0200`. The serial model now keeps DXR in a queue until FSYNC, raises XINT at
that boundary, and completes the reception sixteen SCLKs later (SCLK = 256 × Fs).
Thus, the secondary read completes before the next primary XINT,
and it does not replace DRR too early at that boundary. The updated
`codec_read_probe.json` shows `0044` at `11E9` and `11FC`, followed by
`012F=0244`. We did not patch a reply cell or a handler PC of the guest.

The initial full pair retest in `readback-pair/` went into a DSP overlay
transfer and stopped with `3453C overlay mismatch at 3B21`. The focused
`readback-transfer-diagnostic/` run found a bug in the verification. The payload
was correctly installed at `7658`, with the firmware end marker `7F62=765C`.
The verifier had sampled the foreground BMAR (`3B21`) before the resident restored
its saved overlay pointer at `1158`. It now checks the four words that end at
the completion marker of the firmware. A regression test runs the unchanged loader
with a foreground BMAR that is different from the saved overlay destination.

The prior observation of repeated `7C`/`80` commands without codec reads
is about the earlier run in `pair/`. The final retest after the correction of the
verifier is in `readback-verified-pair/`.

## Final readback retest

`readback-verified-pair/` completes the configured 150 million analog and
400 million I-modem instructions without CPU/DSP errors or overlay-verification
errors. The native Si3034 clocks 244,369 primary frames at 7,200 Hz, with
52 register writes and 67 reads. The resident verifies 4,272 overlay words.
The completed PCM captures now contain audio that is not zero: analog transmit peak
11,288 with 54,721 nonzero samples, and receive peak 2,703 with 58,828
nonzero samples, each over 275,200 samples. In the earlier run with only the watchdog fix,
the analog transmit PCM was fully silent.

The I-modem reports `RING`, answers the ISDN bearer, and then reports
`NO CARRIER`. There is no CONNECT or payload delivery in either direction.
Thus, the corrections of the DAA readback and of the overlay verifier remove the early
stops in the qualification/transfer. A successful carrier negotiation is still an open item.
For the final result, refer to `readback-verified-pair/summary.json`.

## Validation and reproduction

**147 tests passed**. They cover native C5x execution, audio clocks/acquisition,
the 3453C boot, the UART status, the watchdog clocks, native CPU execution, the pair probe and
the ASIC mappings. The new guest-execution tests exercise the mailbox entry, EOI and
IRET together with the board tick. They verify repeated tick delivery when INT3
is enabled, and zero delivery when the guest masks it.

Run these commands from the root of the repository:

```sh
.venv/bin/python artifacts/3453c-watchdog-20261003/probe.py \
  --parameters artifacts/3453c-parameter-sector-20261003/f8000-fbfff.bin \
  --output /tmp/3453c-watchdog.json

.venv/bin/python artifacts/3453c-watchdog-20261003/codec_read_probe.py

.venv/bin/python -m tools.probe_imodem_analog_pair \
  --analog-board 3453c \
  --analog-parameter-flash artifacts/3453c-parameter-sector-20261003/f8000-fbfff.bin \
  --protocol v90 --instructions 400000000 --analog-instructions 150000000 \
  --analog-send '3453C-TO-IMODEM-12345' --imodem-send 'IMODEM-TO-3453C-67890' \
  --output /tmp/3453c-watchdog-pair
```

The parameter-flash probes use disposable copies. The historical baseline/timer runs
record the code before the corrections of the controller and of the ISR return. Do not expect their exact
results from the fixed default profile.
