# Driving the tones ourselves, and reading the DSP back

Can the host command the C52 to make a tone, and then see that it did this?
The primitives for the two halves already exist, and hardware confirms most of
them. This document records what they are, what is proven, and what is not.
Thus you can judge the experiment before you run it.

We did not execute any of this. It is a plan, with its evidence attached.

**We wrote this for DSP 3.0.13. Two of its important claims are not true for
the 3.1.2 of the board. Do not run the experiment below as written.** The tag
`0x06` window does not carry a cell of the 3.1.2 audio path. Thus its diff
cannot see a tone. Also, the statement of blocker 3, "tag `0x13` is not
traced", is now out of date - `13` enters `ee20` and is fully traced in
[mailbox-312-comparison.md](mailbox-312-comparison.md). Refer to
[window-312-baseline.md](window-312-baseline.md) for the measured baseline, the
seventh streamed word, and the corrected chain vector. The addresses in
blocker 3 are also incorrect. [dsp-overlays.md](dsp-overlays.md) has the
measured overlay map.

## Driving: six mailbox messages

The dial path of the supervisor is not a waveform. It is a short conversation
(`courier_firmware_analysis.md`, "What it produces"):

| message | meaning |
|---|---|
| `0x16:0000` | start marker |
| `0x19:020d` `0x1a:3000` `0x1b:0c08` | three constant lanes |
| `0x13:<index>` | the keypad index from `0x6353c` |
| `0x16:0000` | end marker, when the tone stops |

Each message is a usual mailbox write - the tag word on `0x58`/`0x5a`, the
value word on `0x5c`/`0x5e`, committed when you write bit 0 back to `0x1c`.
`courier_emu.dsp_mailbox` already implements this, and it is **confirmed on
hardware**: `artifacts/dsp-mailbox-command-02/` reports `predictions_held:
true`. We fixed each prediction for the inbound registers from the disassembly
before the run.

We also understand three of the six messages, and we can do more than only
send them. `0x19`, `0x1a` and `0x1b` are in the recovered host-write table with
known destinations - DSP data `0x03ad`, `0x0392` and `0x03f1`. Thus their
effect is a store to a known cell. That table also shows that the tone
generator belongs to the datapump and not to the ASIC: the parameters go into
DSP memory.

## Reading back: two fixed windows

The two windows arrive through the DSP-to-host stream at `0x60`/`0x62`. This
stream has 27 read sites and zero write sites in all of the image. The CPU
continues it when it acknowledges bit 2 of `0x1c`.

| tag | what it streams | status |
|---|---|---|
| `0x46` | four DSP **program** words from `0x860b + index` | confirmed on hardware, `artifacts/dsp-window-pump-02/`-`03/`, against addresses that we predicted before |
| `0x06` | six DSP **data** cells: `0x0307`, `0x03ba`, `0x0385`, `0x030f`, `0x031c`, `0x0be6` | channel confirmed to respond, `artifacts/dsp-window-pump-01/` |

The second window is the reason to try this. When we pumped it for the first
time, we recorded this detail: **its sources are empty on an idle unit.** Thus
there is a baseline, and a change from it is visible.

## The experiment that needs no new code

1. Keep the modem on hook and idle. Arm tag `0x06` and pump the window. Record
   the six cells.
2. Send the six-message tone sequence.
3. Pump the window again and compare.

If one of the six cells changes, the DSP acted on the tone command. Then the
behaviour confirms the generator, and not only the mailbox table. If no cell
changes, the result is really ambiguous - refer to the second blocker.

## Blockers, stated before the run rather than after

1. **The mailbox belongs to the supervisor.** If you write it while the
   firmware has a conversation in progress, you corrupt that conversation.
   This is why `dsp_mailbox` runs against an idle modem. It is also why you
   cannot do any of this during a call.
2. **The read windows are fixed.** The code of the DSP selects the six data
   cells and the one program base. We do not select them. If the tone state
   is in a different location, a null result means "not visible here". It
   does not mean "did not occur".
3. **Tag `0x13` is not traced.** Its handler at `0xd82f` calls `0x84da` two
   times and then `0x0cb1`. An attempt to disassemble the adjacent table
   entries was not reliable. The entry of tag `0x19` points at `0xdaaf`. This
   is in the gap between the end of the resident bank at `0xd9ef` and the
   start of the overlay at `0xde83`, so it reads as zeros. Either the base of
   the jump table is incorrect, or that handler is in an overlay that is not
   loaded. Thus the effects of `0x13` are not known.
4. **Tag `0x16` is ambiguous because of the design of the firmware.** The
   call-start block uses the same `0x13`/`0x16` lanes with the same constants,
   and "nothing in a single message tells the two uses apart". The difference
   between them is whether the loop is seized. On hook, we expect that the tag
   has no effect. That is an expectation, not a measurement.
5. **You cannot hear the line.** A tone, even if it is generated perfectly, is
   visible only as DSP state, unless it goes to a device that can listen. The
   `AT%T` DTMF detector of the modem is the obvious candidate. But the only
   loopback without a line is `AT&T8`, which clears all free RAM
   (`artifacts/ram-sampler-01/`).

## Where the RAM routine would come in

Use the RAM routine only after the cheap version shows that there is something
to see. The host pumps the window at one word for each serial round trip,
about 165 ms. At that rate, a tone that continues for S11 milliseconds has bad
aliasing. The tick-hooked sampler (`courier_emu.ram_sampler`) reads at 200 Hz.
Thus it can capture the window densely across a tone burst. It can also do
the mailbox writes at bus speed. Without it, the six-message sequence takes
about one second of serial traffic.

That build is larger and has more risk than the baseline/diff above. Do not
do it until the diff shows a signal.
