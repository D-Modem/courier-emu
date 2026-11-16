# 2806 codec and audio-monitor control

We traced this from the exact 25 MHz 7.3.14 / DSP 3.0.13 flash image. We examined it with live M/L setting probes on 2026-09-13. The CPU addresses below are **ROM file offsets**. The DSP addresses are program-word addresses.

## The volume-related mailbox command is 0x0f

The CPU L-command handler at 263c4 validates a value below four and stores it at RAM 05e7 (the usual active-profile path). It calls the board-latch routine at 25f4 and the mailbox routine at 0732.

The mailbox routine selects a gain from this table at 075c:

| Setting | Candidate mailbox argument |
|---|---|
| L0 | 0200 |
| L1 | 0600 |
| L2 | 0e00 |
| L3 | 3f00 |

It forces the argument to **zero** when RAM 0693 bit 08 is clear, or when RAM 014b bit 01 is set. It sends tag 000f through the three-word queue thunk at 8f46:0224 (file f684). Thus these values are conditional. They are not commands that each board always sends.

DSP tag 0f dispatches to 8246:

```
8246 smmr @7a, #039d   ; save host gain
8248 lamm @7a
8249 retc neq
824a lacc #8000
824c samm @50         ; silence/idle code for zero gain
824d ret
```

The receive-audio ISR at 8193 loads the ADC word of the codec, stores it in the receive ring, and loads TREG0 with it. At 8196 it reads data 039d (page 7, @1d). If this value is not zero, 8199–819d multiply by that gain, shift by 14, and write the result to DSP I/O 0050. The usual DAC/codec serial output continues independently at 819e and after.

This is an **audio-monitor sample-copy path through the ASIC**. It is not a write to codec register 4. The L-command caller is the evidence that the gain is related to volume. We did not trace the electrical conversion of I/O 50 samples into an audible signal. This analysis does not prove a DAC or PWM circuit in the ASIC.

## M commands and the alternate volume-latch path

Live RAM snapshots show M0/M1/M2/M3 at RAM 05e8. The exact M handler at 263f7 stores the value there and calls the speaker wrappers at 2627/262b. These get to the generic latch clear/set routines with AX=1009. The port table at 27ef is 0010,0012,0014,0012. Thus index 1 means **CPU port 12, mask 10**. The clear operation enables. The set operation disables. The immediate enable of M2 is conditional on RAM 033e bit 04. The call-state code also tests the saved M setting. Thus an idle M sweep is not an audible test of all modes.

The alternate volume routine at 25f8 returns immediately if RAM 0693 & 06 is not zero. If not, it copies L bit 0 to port 12 mask 20 and L bit 1 to mask 40 with the same latch driver. These are CPU I/O operations. They are not DSP mailbox messages.

## What the live 2806 showed

The board reports serial 22AEB36ACKND and the expected 25 MHz / 7.3.14 / 3.0.13 identity. The original settings were **L2/M1**. We read them from RAM and restored them. RAM 0693 was **22 hex**: bit 08 clear and mask 06 not zero. Thus, on this board in this state, the gain argument of the DSP monitor is forced to zero, and the direct volume-latch writer returns without a write.

The L sweep changed RAM 05e7 through 0,1,2,3, but the monitor readback of port 12 stayed 9a. This agrees with the board-flag branch. The readback alone does not show that a writable latch is equal to its input readback. We did not do a call or an off-hook test. A corrupt serial RAM reply stopped the first volume run. Its finally block restored L2/M1 and the AT response. A second run uses bounded read retries and keeps the first capture.

We must still identify the physical purpose of the board-type flags and the actual speaker/volume circuit on this external board. A manual volume control is possible, but this analysis does not show it.

## Mailbox commands that actually reach codec control

| Tag | DSP entry | Proven path in 3.0.13 |
|---|---|---|
| 0f | 8246 | Sets the gain for the ADC sample copy to ASIC I/O 50. Zero disables it. No codec control word. |
| 2c | 8222 | Bare RET: no-op in this firmware. |
| 55 | 8da5 | Calls codec writer 8149 with 0409 at 8dbc–8dbe, then enters the mode-dependent initialization. |
| 59 | 8df9 | Gets to 8e0f/8e13: index 4 into rate selector 8151. |
| 5a | 8ddd | Gets to 8df3, then 8e13: index 4 into rate selector 8151. |

Selector 8151 writes four ASIC timing words. It puts the codec word of the row in data 006c, with request 3 in 006b. Index 4 puts **0212**, B=18. The sender/ISR uses a secondary serial frame to send it directly from the DSP to the codec. The branch of tag 55 can also get to that index. These are mode-initialization commands. They are not safe standalone volume controls. We did **not send them during this investigation**.

We claim only direct, decoded paths. This is not a complete transitive call graph of each modulation overlay. Do not use codec word 0409 and the monitor bits of register 4 to state that the physical speaker connects to MON OUT. The M/L trace shows more paths, and we did not measure that wiring.

## Reproduction and evidence

Artifacts: `artifacts/courier-2806-codec-control-20260913/`. `speaker_probe.py` records mode RAM snapshots. `volume_probe.py` records M/L values, port readback, board flags and restoration. `cpu-speaker-disassembly.txt` and `dsp-codec-disassembly.txt` record the bounded code paths. These hardware probes did not use RAM, flash, stored settings or arbitrary mailbox writes. They used only volatile AT M/L settings and reads.
