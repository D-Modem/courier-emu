# Connected-board DSP 3.1.2 mailbox comparison

## Initialized replay resolves the query-62 discrepancy

The fresh [eight-digit G capture](atg-dsp-command.md) made it possible to replay
`62, 07, 2d, 62, 07` against the native DSP and the bridge after a normal boot.
Each reply agrees with the board, which includes **`0069:0015` for the two query-62
requests**. Query 07 returns `0031:0000`, also with the data `a55a`. The
no-op makes no new reply, and it keeps the holding registers.

The older isolated `execute()` fixture still gives `0069:0012` with
the same current core. It goes into the handler without the initialization of the resident.
Thus, the discrepancy recorded below is not a difference between the board
and the initialized emulator. It is a difference between test conditions.
That comparison does not give a reason to change the arithmetic core.

**We measured this later, off-hook on a live line: the board returns `0015` for query
62 in silence, with dial tone and with an armed tone.** This agreement
confirms the transport and the dispatcher. It says nothing about the arithmetic of the handler.
Refer to [the 403 gate addresses](datapump-gate-403-addresses.md).

This does not prove all of the query-62 arithmetic. Its handler adds the squares of
DSP data `0900..098f`, uses other resident state, and limits its result.
`0015` is one of its explicit clamp values. An agreement with this idle result cannot
show that the audio is accurate sample by sample. We did not isolate which
initialized input/register causes the `0012` result of the fixture.

The [replay report](../artifacts/g-eight-hex-board/booted-emulator.json) and
`tests/test_g_dsp_capture.py` keep the two results. The new comparison runs
the real DSP boot and the initialization of the resident. Through the bridge, it checks that the request is consumed,
that a new reply is present, and that the reply words are exact. It does not
execute the AT parser/UART of the supervisor, and it does not prove that the interrupt timing is equivalent.

This makes future failures easier to isolate. If the full emulator cannot complete these
same G commands, examine these items before you change these DSP handlers: supervisor execution, the drain of the queue,
the delivery of the mailbox interrupt, and the serial completion.

## Earlier isolated comparison

On 2026-09-05, the modem on `/dev/cu.usbserial-21210` at 115200 baud
identified itself as ID_SDL 4.03d, supervisor 7.4.16 / DSP 3.1.2, 20.16 MHz,
512 KiB flash. Seven flash pages agreed byte for byte with the existing `courier-board-21210-capture-403`
image. These pages contain the dispatcher, the query handlers,
and the tone selector. The evidence is in
`artifacts/dsp-mailbox-312-comparison-01/`. It includes the raw command
transcript, the hardware manifest, the flash-page verification, and the emulator report.
The modem answered `AT` after the two sessions.

## Hardware versus original DSP code

The live sequence was `07, 2d, 62, 07`, each with data zero. It used the
existing mailbox commit protocol. No dialing or firmware upload was necessary.

| Command | Hardware tag:value | Emulator tag:value |
|---|---|---|
| 07 | 0031:0000 | 0031:0000 |
| 2d (no-op) | retains 0031:0000 | retains 0031:0000 |
| 62 | 0069:0015 | 0069:0012 |
| 07 | 0031:0000 | 0031:0000 |

`courier_emu.mailbox_compare` runs the actual 3.1.2 dispatcher at `8387`
and the sender at `83bf`, with its real accessor at `80e8`. A small test
caller goes into those routines with the fixture queue pointers `ff50`, and
all other RAM at its default. This is a component comparison, not a full modem boot.
It does not inject the expected reply into the DSP.

The first run used plain I/O-register storage, and it gave no reply. The
dispatcher wrote `1` to DSP status `57`, and this replaced the status value `3`.
Thus, bit 1 was lost, and the sender checks this bit before it sends. A test-side ASIC adapter
clears the acknowledged bits and keeps the other bits. With this adapter, the two real
firmware routines complete. The DSP writes the reply tag to port `5e` and the data
to `5f`, and it acknowledges with `57:0002`. On the CPU side, those words appear
at the byte pairs `58/5a` and `5c/5e`.

This gives a useful minimal handshake model for these transactions.
It does not give all status bits or the physical interrupt latency. It does not prove
that each write to the ASIC is write-one-to-clear. The adapter is only in
the comparison runner. It is not applied globally to other board profiles.

We intentionally keep the `62` difference visible. Its handler processes sample
RAM and prior DSP state. The emulator has no hardware sample snapshot,
and no complete initialization. State differences and the arithmetic emulation are still
possible causes. An agreement of the reply tag alone is not an agreement of the value.

To do this again offline:

```sh
.venv/bin/python -m courier_emu.mailbox_compare \
  --rom artifacts/courier-board-21210-capture-403/courier-board.rom \
  --capture artifacts/dsp-mailbox-312-comparison-01/manifest.json \
  --output /tmp/courier-mailbox-comparison.json
```

## The firmware-version error and the tone path

The 3.1.2 dispatcher calculates its table base as `8468 - 007f = 83e9`.
The older DSP 3.0.13 uses `8401`. Thus, you cannot use addresses and no-op assumptions from one version
in the other without changes:

* `0b` now goes into real code at `ec63`. It is not a null control.
* `2d` still points to a bare return. The serial probe now uses this
  shared no-op by default. It rejects commands of the old profile before it writes to a port.
* `13` goes into `ee20`. It masks the host word to four bits, doubles it, and reads
  a coefficient pair from program `ee34 + 2 * index`. It installs the callback
  `8743` in DSP data `039a`, initializes the phase/state, and returns.
* `19`, `1a`, and `1b` still store to DSP data `03ad`, `0392`, and `03f1`.
  Tag `1a` also writes `fff0`. Thus, these are not interchangeable generic
  RAM-write commands.
* `16` installs the callback `8128` in `039a`. Do not call it an
  unconditional start command only because of the location where the supervisor sends it.

The tone selector is present in the captured resident download of this board. Thus, a
missing overlay is not necessary to explain its handler address. This finding applies
only to DSP 3.1.2. It does not resolve the overlays of `main211`. To make or
hear a waveform, you must still execute the callback with the correct frame
context and trace its output to the codec. We did not send a tone command live.

The next limited experiment is to run that callback under controlled DSP
frame conditions. Then compare it with a captured hardware tone. The present mailbox
comparison supplies a verified entry path, and it records where the equivalence stops.
