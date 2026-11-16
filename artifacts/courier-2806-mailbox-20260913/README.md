# 2806 mailbox handshake, 2026-09-13

Target: 25 MHz Courier 2806, serial 22AEB36ACKND, supervisor 7.3.14, DSP 3.0.13. The probe operates through the serial monitor while the native supervisor and the DSP run. We wrote only the mailbox ports 58, 5a, 5c, 5e, 1e and 1c. We did not use firmware, RAM, NVRAM, board latch, dial or reset commands.

## Direct observations on this board

The decisive transaction is in first-results.json and first-transcript.json:

| Step | Reply tag | Reply data | CPU 1c |
|---|---|---|---|
| Baseline | 0008 | 0000 | fd |
| Stage tag 0007, data a55a across four bytes | 0008 | 0000 | fd |
| Write 1e=00 | 0008 | 0000 | fd |
| Write 1c=01 | 0031 | 0000 | fd |
| Read again | 0031 | 0000 | fd |

This shows that the write of the last data byte to the stage does not send this query. The additional write 1e=00 also does not send it. The write 1c=01 completes the transaction. The readback continues to show the prior DSP reply while the CPU writes a different outbound tag and data. Thus, the two directions have different storage or an equivalent independent state.

The first run stopped during a later no-op snapshot, because the existing parser accepted only one type of line ending. The completed repeat, results.json/transcript.json, accepts the line-ending variants that we saw. It runs query 07, no-op 2d, then query 07 with different ignored data patterns. All readbacks stay at 0031:0000, and the last AT returns OK. Because the replies are identical, these repeated queries alone do not prove that the DSP generated new replies. The first transition 0008→0031 is the decisive evidence.

## Protocol reconstructed from exact 2806 firmware and prior board evidence

CPU tag low/high = ports 58/5a. CPU data low/high = ports 5c/5e. DSP tag = I/O 5e; DSP data = I/O 5f. DSP status = PA7 / 57. These ports have the same numbers, but they belong to different processors. You cannot interchange them.

CPU→DSP:
1. CPU 1c bit 0 means that the input slot is free.
2. The CPU writes the tag/data bytes to the stage. Then it writes bit 0 to 1c to publish.
3. DSP PA7 bit 0 means that input is pending.
4. The DSP reads the tag/data. Then it writes 0001 to PA7 to acknowledge receipt and release the input slot.

DSP→CPU:
1. DSP PA7 bit 1 means that the output slot is free.
2. The DSP writes the tag/data. Then it writes 0002 to PA7 to publish.
3. CPU 1c bit 1 means that a reply is pending.
4. The CPU reads the reply. Then it writes bit 1 to 1c to acknowledge and release the output slot.

The DSP receiver at 839b reads the two words and acknowledges at 83b3–83b4 BEFORE the command dispatch. The sender at 83d6 tests availability. It writes the tag at 83eb and the data at 83ee/83f6. Then it publishes in the delayed-return slots at 83fe–83ff. Refer to dsp-disassembly.txt. The CPU handler at ROM file fde0–fe68 tests bits 0/1/2 and writes the bytes to the stage. It writes its serviced mask to 1c at fe4a, then the high byte to 1e. Refer to cpu-handler.txt. Thus 1c is an action/handshake interface. It is not a replacement value for all of the status register.

A minimal functional model has two independent tag/data holding registers and two full flags. CPU-free = NOT host_to_dsp_full; DSP-pending = host_to_dsp_full. DSP-free = NOT dsp_to_host_full; CPU-pending = dsp_to_host_full. The acknowledgement releases availability. The retained reply data stays readable. This is a behavioural model. It does not prove the physical FIFO depth or the number of flip-flops.

## Limits

All serial snapshots read 1c=fd: the native supervisor services the replies before the slow monitor can show the transient pending state. Thus, this run does not directly measure the time of the DSP acknowledgement. It does not prove that the CPU acknowledgement alone clears the pending state. It does not show the FIFO depth or the interrupt edge/level behaviour. The exact resident firmware and the earlier 20.16 MHz kernel measurements support the status semantics of the opposite side. These are in docs/dsp-mailbox-board-fix.md and docs/mailbox-from-the-rom-dump.md. We did not sample them independently on the DSP in this run.

Port 1e=00 is part of the known transaction. But it is not proven that this write is necessary, or what nonzero values do. We did not exercise bit 2 (stream channel) or the handshakes of the download window. A definitive transient/backpressure experiment must have a bounded CPU/DSP probe with exclusive ownership of the mailbox. The existing co-resident runner has a guard for 20.16 MHz 7.4.16 firmware. We did not change it blindly for use on this board.
