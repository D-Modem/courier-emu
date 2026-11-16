# The TLC320AC01 protocol, as this board's DSP actually drives it

The codec next to the DSP is a TI `320AC01CFN` ([board-parts.md](board-parts.md)).
This file decodes the serial protocol between the codec and the C5x from two sources that
agree: the datasheet (`tlc320ac01.pdf`, section 2.19 and 2.20) and the DSP
firmware itself. We disassembled the firmware from the payload of `IDSDL302.ROM`, and then we monitored it
while it executed under the boot ROM.

The program addresses are those of the 20.16 MHz build, with origin `0x8000`. The copy of
the same code in `main211` is `0x8000` lower.

## The frame

The AC01 exchanges one 16-bit word in each direction for each frame. The word that the DSP sends
is a **14-bit DAC sample in DS15..DS02 plus two control bits in DS01:DS00**.
The word that it receives is the ADC sample. The two LSBs select what occurs next:

| D01 D00 | effect |
|---|---|
| `00` | ordinary frame, no phase shift |
| `01` / `10` | phase-shift request (earlier / later) |
| `11` | **request a secondary frame** |

Datasheet section 2.17.1 and Table 2-3. Thus, a DAC sample is never a full 16 bits.
For this reason, it was correct that `native/c5x_core.cpp` masked the transmitted word with `0xfffc`.

A **secondary frame** carries a control-register write in place of a sample
(section 2.19.1):

```
DS15 DS14 | DS13 | DS12 .. DS08 | DS07 .. DS00
control   | R/W  | reg address  | register data
 (2 bits) |      |   (5 bits)   |   (8 bits)
```

## What the firmware does

### Reset: prime the port, then write six registers

`0x8090` sets up the serial port and sends two priming frames:

```
8090  lar  ar1, #22          ; ar1 -> SPC
8091  splk *, #0008          ; SPC = 0008
8093  splk *, #40c8          ; SPC = 40c8
8095  lacl #01 ; samm @21    ; DXR = 0001
8097  bit  4, *              ; SPC bit 11 = XRDY
8098  bcnd 8097, ntc         ; spin until the shifter has taken it
809a  samm @21               ; DXR = 0001 again
```

Then there are six calls to the blocking control-word sender at `0x8149`:

```
80ad  lacc #010a ; call 8149
80b1  lacc #0214 ; call 8149
80b5  lacc #0300 ; call 8149
80b9  lacc #0409 ; call 8149
80bd  lacc #0505 ; call 8149
80c1  lacc #0620 ; call 8149
```

### The sender is three lines and an `idle`

```
8149  samm @6c              ; stage the secondary word
814a  lacl #03 ; samm @6b   ; request code 11
814c  idle                  ; wait for the next XINT
814d  lamm @6b
814e  bcnd 814c, neq        ; spin until the ISR clears the flag
8150  ret
```

`@6b` is the pending request code, and `@6c` is the staged control word. The two are
DARAM B2 cells, in the same block as the interrupt dispatch table of the ROM.

### The ISR ORs the request into the sample

`@65` is the B2 cell through which the on-chip ROM dispatches XINT
([dsp-onchip-rom.md](dsp-onchip-rom.md)), and the firmware installs `0x8189`
in it. The cell of RINT, `@64`, gets the shared stub `0x81ae` that does nothing. Thus, **the
transmit interrupt alone controls the part**, and one handler does the two
directions:

```
8189  ldp  #007
818a  lacc @19 ; sub #01 ; sacl @19   ; frame countdown
818d  xc   2, eq ; clrc xf
818f  dmov @18
8190  mar  *, ar7 ; sar ar7, @11 ; lar ar7, @10
8193  lamm @20              ; ACC = DRR - the ADC word
8194  sacl *+               ; into the receive ring
8195  samm @0c              ; TREG0 = sample
8196  lacl @1d ; bcnd 819e, eq
8199  spm #0 ; mpy @1d ; pac ; bsar 14 ; samm @50   ; scaled copy to I/O 50
819e  lamm @6b
819f  or   *+               ; DAC sample OR the request code
81a0  samm @21              ; DXR = sample | 3
81a1  sar  ar7, @10 ; lar ar7, @11
81a3  setc xf
81a4  lamm @6b ; sub #03
81a6  bcnd 81ab, eq         ; request pending -> arm the secondary frame
81a8  lacl #00 ; samm @6b ; rete
81ab  lacc #81af ; samm @65 ; rete    ; revector XINT for exactly one frame
```

The secondary-frame handler restores itself:

```
81af  lamm @6c ; samm @21   ; DXR = the control word
81b1  lacl #00 ; samm @6b   ; request satisfied
81b3  lacc #8189 ; samm @65 ; put the normal ISR back
81b6  rete
```

**There is no state machine to find: the state is the address in `@65`.**
The ISR writes its own vector cell again for one frame, and then it reverses the change.

### Watched executing

We stepped the boot-ROM run and sampled `@6b`, `@6c` and `@65`:

```
@6b=0x0000  @6c=0x0000  @65=0x8189
@6b=0x0003  @6c=0x010a  @65=0x8189
@6b=0x0003  @6c=0x010a  @65=0x81af
@6b=0x0003  @6c=0x0214  @65=0x8189
@6b=0x0003  @6c=0x0214  @65=0x81af
...
@6b=0x0003  @6c=0x0620  @65=0x81af
@6b=0x0000  @6c=0x0620  @65=0x8189
```

There are six words, and for each one the vector changes and then changes back. The disassembly and the
run agree.

## What the six words program

| word | reg | data | meaning |
|---|---|---|---|
| `010a` | 1, A register | 10 | `FCLK = MCLK / (2 x A)` = MCLK/20 |
| `0214` | 2, B register | 20 | `fs = FCLK / B` = MCLK/400 |
| `0300` | 3, A' register | 0 | no phase-shift adjustment |
| `0409` | 4, amplifier gain | `0x09` | monitor squelch; **analog input +6 dB**; analog output 0 dB |
| `0505` | 5, analog config | `0x05` | DS02 set: **high-pass filter bypassed**; `IN+`/`IN-` selected (not AUXIN), no loopback |
| `0620` | 6, digital config | `0x20` | DS05 set: **ADC and DAC conversion free run** |

All six have DS15:DS14 = `00` (no phase shift) and DS13 = 0 (write mode). The firmware
never reads a register back. Registers 7 and 8 (frame-sync delay and
frame-sync number, which are important only when slaves are chained) stay
at their defaults. Thus, this is a single AC01, not a chain.

### Free run is the interesting bit

Register 6 DS05 puts the part in free-run mode (datasheet 2.15.4). The external
shift clock and the frame sync **control only the data transfer**. The ADC
and DAC conversion timing comes from the A and B registers, from MCLK. Registers 7 and 8
are not changed. Together, this gives this topology: a device outside the
codec supplies SCLK and FS and moves the words, and the codec clocks its own
converters.

> **That device is the DSP, not the ASIC.** An earlier revision said that the
> ASIC supplies SCLK and FS. Continuity readings after that
> ([asic-pinout.md](asic-pinout.md)) put the `DOUT`, `DIN` and `FS` of the codec
> (FN pins 11, 10 and 12) on **DSP pins 43, 106 and 104**, each one pin from
> its TDM equivalent. The ASIC has exactly one line to the codec, and it is
> `MCLK` (pin 14, from ASIC 112). Thus, the ASIC clocks the timebase of the converters,
> and the DSP runs the serial port. This is the same division of work that this
> section describes, but with the two parts in the opposite roles.

That is the specific version of the claim in
[board-parts.md](board-parts.md) that "the ASIC fronts the codec". It is true
of the data path, and false of the conversion clock.

### The rate: MCLK is 2.880 MHz, and it is over-determined

The equations of the datasheet are `FCLK = MCLK/(2 x A)` and `fs = FCLK/B`.
[codec-sample-rates.md](codec-sample-rates.md) finds the three sample
rates independently of a clock. It uses the DTMF phase increments of the dial path,
and a six-row table indexed by the negotiated symbol rate of V.34. This table
programs **only register 2** again, with `0214`, `0213` or `0212`. If we solve for MCLK
with A fixed at 10:

| B | fs | implied MCLK | FCLK |
|---:|---|---|---|
| 20 | 7200 Hz | 2.880000 MHz | 144.000 kHz |
| 19 | 7578.95 Hz | 2.880001 MHz | 144.000 kHz |
| 18 | 8000 Hz | 2.880000 MHz | 144.000 kHz |

Three independent rates give one value. **MCLK = 2.880 MHz**, and

```
40.320 MHz / 2.880 MHz = 14.000
```

exactly. Thus, the codec clock is an integer division of the master
oscillator of the board, and the second can on the board is not necessarily its source.

Two results look like design and not like chance:

* **FCLK = 144.000 kHz is the characterization point of the datasheet itself.** Each
  filter and distortion table in section 3.5 is specified at "FCLK = 144 kHz,
  fs = 8 kHz", and B = 18 gives exactly 8.000 kHz. The board operates the part at the point where
  TI characterized it.
* **A is never programmed again, and that is the reason.** The corner of the anti-alias low-pass filter
  is `FCLK/40`, which depends only on A. It is a fixed **3.6 kHz** for all three
  sample rates, the standard voiceband corner. Only B changes. Thus, a change of the
  sample rate does not change the filter.

The high-pass filter of the part is switched **out** (register 5 DS02 = 1). Thus,
the `fs/200` corner never applies, and for the codec the DAC and ADC paths are DC-coupled.
The component that removes DC is downstream, in the DSP or
the ASIC.

An earlier revision of this section said that the design point was 9600 Hz, and that
thus MCLK was 3.840 MHz, an inconvenient division of 10.5 of the 40.320 MHz can.
That was wrong. It used the `DAA_SAMPLE_RATE` of the harness as a measurement. The
value 9600 does not occur in the firmware, the datasheet or the arithmetic.

## What the emulator does with all of this today: nothing

`native/c5x_core.cpp` stores `DXR` and counts the write. For two hardcoded PCs, it
pushes `value & 0xfffc` into the line-transmit buffer. It discards the two control bits.
It never delivers a secondary frame, and the register file does not
exist. Thus, the input gain, the high-pass filter, the analog input select, free run
and the A/B rate have no effect. `SPC` reports `XRDY` set each time
`XRST` is set, and it does not follow a frame clock. Thus, the reset loop at `0x8097`
and the `idle` at `0x814c` both continue immediately.

`courier_emu/codec.py` models an Si3038 register map, which the DSP of this board
never controls.

### And the sample rate is wrong on the side that generates audio

`configure_rom_codec` sets `m_line_frame_period = 3472`, which is `25e6/7200`.
Thus, the frame *interrupt* already arrives at the 2400-baud rate. But each component that
*fills* the receive queue assumes 9600 Hz:

| site | what assumes 9600 |
|---|---|
| `courier_emu/daa.py` | `DAA_SAMPLE_RATE`, and the 350/440 Hz dial tone it renders |
| `courier_emu/line.py` | `LINE_FRAME_MS`, the frame unit two linked instances exchange |
| `courier_emu/bridge.py` | the SIP rate converters and three tone mixers |
| `native/c5x_core.cpp:396` | the V.8 1300 Hz and 2100 Hz correlator references |
| `native/c5x_core.cpp:419` | the answer-tone cadence |
| `native/c5x_core.cpp:754` | the line-sample phase accumulator |

Thus, the samples are made at 9600 Hz, and the firmware consumes them as if
they arrived at 7200. **Each frequency that the firmware sees is scaled by 4/3.**
Dial tone gets to it as 262/330 Hz and not as 350/440. The 2100 Hz answer tone
arrives as 1575 Hz. DTMF is far outside the tolerance of its detector, which
[codec-rate-312.md](codec-rate-312.md) already showed is only ±1.5%.

This is a candidate explanation for why `--exchange` hears silence, and for why the
V.8 bootstrap needs a native detector and not the detector of the firmware. But it
is a candidate, not a proof. We did not run any of this again at 7200 Hz to
show that the firmware then recognises the tones.

## The model (2026-09-07)

`C5xCore::codec_transmit` now decodes each `DXR` write in the same way as the part.
The control bits of the *previous* frame decide which type of frame a word is part of.
Thus, the model does not need to know where the write came from.
This replaces a test against two hardcoded ISR addresses, `0x818f` and `0x81a0`,
which recognised the samples of two known builds and nothing else.

* Primary word: the sample is the top 14 bits. `11` in the LSBs arms a secondary
  frame. `01`/`10` count as phase-shift requests, and the model ignores them in all other ways.
* Secondary word: parsed into a register file of nine entries. Register 0 is the
  no-op. If `DS13` is set, it is a read. The read returns the register in the low byte of `DRR`, and it
  programs nothing. Register 6 `DS02` forces each frame to be secondary.
  `DS01` is a software reset, and it restores the power-up defaults.
* **The sample rate is derived, never assumed.** A write to register 1 or 2
  calculates `fs = MCLK/(2 x A x B)` again, and with it the frame period in C5x
  cycles. `configure_rom_codec` still starts at 3472, because it cannot know
  the clock rate of the port from the ASIC before the firmware programs anything. But
  from the first divider write of the firmware, the rate is that of the part.

`courier_emu/dsp.py` gives `codec_state()` and `codec_sample_rate`.

The analog gains of register 4 are also part of the modeled signal path. The input
codes select squelch, 0, +6 or +12 dB before the ADC word gets to `DRR`. The output
codes select squelch, 0, -6 or -12 dB between the DAC word and the phone line.
The receive gain is saturated to the signed 16-bit ADC word of DOUT. The transmit signal is
quantized again to the 14-bit DAC field of DIN after the model removes its two control bits.
This is important for the normal `0x09` setup: its +6 dB input gain doubles the peer
waveform that the datapump sees.

We booted 302 through the ROM and read the model back:

```
registers      ['0x00', '0x0a', '0x14', '0x00', '0x09', '0x05', '0x20', '0x00', '0x01']
sample rate    7200.0 Hz          frame period 3472 cycles
secondary 6    reg writes 6       reg reads 0    phase shifts 2
free_run=True  high_pass=False    loopback=False
input gain 6 dB   output gain 0 dB
```

The six registers are the six words above. The rate comes from B, and the two
phase shifts are the reset priming writes.

### Line audio meets the codec at the codec's rate

`bridge.LineToCodec` resamples all data that goes into the receive queue from the
line rate of the harness to the current conversion rate of the codec. It uses linear
interpolation and a carried sample, so that a batch seam does not click. Each audio
path in `bridge.py` now goes through `_queue_line_audio`. The boot table, which
is not audio, still goes directly to `queue_codec_rx`.

A 2100 Hz tone carried at 9600 and delivered to a 7200 Hz codec measures
2100 Hz after conversion. Without resampling, it measured 1575.

### The frame clock, per the datasheet

`C5xCore::codec_frame` runs at each frame sync. The harness did not have this before.
Before, `DRR` was filled only when the firmware read it.
Thus, in a run with an empty receive queue, the same stale word came back in each frame
for the full run.

* **One ADC word for each primary frame**: "one word for each primary
  communication interval", section 2.4. The converter runs also when the
  DSP does not listen, and an empty queue is silence on the line. Thus, it delivers a
  zero and does not repeat the last word.
* **A secondary frame delivers no sample.** Again section 2.4: DOUT carries the
  addressed register when a read was requested, and all zeros in all other cases. Thus, the
  register value arrives with the secondary frame sync, and not when
  the host reads `DRR`.
* **The secondary frame sync arrives half a frame period after the primary frame that
  requested it.** The note of Figure 2-1 gives `(B/2)` FCLK periods, and because
  `fs = FCLK/B`, that is `fs/2`. It is serviced before the next primary frame. It does not
  replace it.
* `RRDY` now follows a word that was actually clocked in. It does not follow audio in the queue
  of the harness.

We measured this on the 302 boot: 1911 frame syncs and 1911 samples consumed, exactly one word
each. `DRR` contains live audio and not a stale zero.

### The boot table is probably not on this port at all

> **Retracted.** An earlier version of this section said that the boot table
> and the codec share the primary serial port, and that the high-impedance window
> of the AC01 keeps them apart. **The arithmetic is not correct**: `DOUT` is tri-stated for eight primary frames, and the download is
> 27,710 words. The window is three orders of magnitude too small.
>
> The premise was also wrong. The ROM has **two** boot transports, and the
> serial transport is not the only candidate. Refer to
> [the boot transport note](dsp-boot-transport.md). The harness selects the
> serial path when it writes 4 to data `0xffff`. This is a choice of the harness. It is not a
> measurement of what the ASIC presents.

The text that follows gives what we actually know about the port itself.

### The codec is on the primary serial port

The AC01 is on the **primary serial port** of the DSP. It does not have its own port. The
application guide of TI (`slaa006.pdf`) wires it `DOUT -> DR`, `DIN -> DX`,
`SCLK -> CLKR/CLKX`, `FS -> FSR/FSX` and `RESET <- XF`. The pins of the second (TDM)
port are pulled to COM through 100 kOhm and are not used. The firmware agrees on
the two items. It controls `DRR`/`DXR`/`SPC` at `0x20`-`0x22`, and it configures
`TSPC` one time at `0x808a` and never uses the TDM port again.

> **The board also agrees, on three of the five.** `DOUT`, `DIN` and `FS`
> go to DSP pins 43, 106 and 104. This is the wiring of the application guide, which continuity
> confirms. We did not only infer it from the firmware. `SCLK` (FN pin 13) has a
> reading that calls it a reset net. This is almost certainly a wrong label, and it
> now has a predicted destination that we must check.
>
> **`RESET <- XF` is not correct.** The `RESET` of the codec (FN pin 8) is on the
> **shared reset net** that also goes to DSP `RS` (pin 127) and **CPU pin 58**,
> `P1.1`. `courier_emu` already controls this bit as `DSP_RESET_PORT`. Thus, the
> supervisor resets the codec together with the DSP. The `XF` of the DSP does not reset it.
> This answers the closing speculation of this section ("very likely how the codec
> is kept quiet during the download, but it has not been established here")
> negatively. The mechanism that keeps the codec quiet during a download is not `XF`
> holding `RESET`, because `RESET` is not on `XF`.

The *serial* path of the ROM boot loader is on that same port. It only receives. It
never writes `DXR` and never polls `XRDY`:

```
06e8  1020  lacc @20      ; DRR
06de  4522  bit  5, @22   ; SPC bit 10 = RRDY
06f3  a720  tblw @20      ; ...into program memory
```

But that path is only one of the two that the ROM gives, and the evidence points to the
other one. Refer to [dsp-boot-transport.md](dsp-boot-transport.md).

`queue_codec_boot` keeps the boot words of the harness in their own queue. The polls
of the loader drain it, and a frame sync never drains it. We added this because
the frame clock otherwise consumed the boot table. It stays correct for each possible
transport. But if the parallel transport is the correct one, the split is not
a workaround and becomes unnecessary, because the boot never uses this port.

The design guide also controls the `RESET` of the codec from the `XF` pin of the DSP. The
serial ISR and **the fetch routine of the parallel boot loader** both control `XF`.
That is very likely how the codec is kept quiet during the download, but it has
not been established here.

### XRDY follows the frame clock

`XRDY` says that `DXR` can accept one more word. This becomes true when a frame sync
moves the last word into the transmit shift register. Before, the model reported it set
each time `XRST` was set. Thus, the reset handshake at `0x8097` did not wait a frame:

```
8095  lacl #01 ; samm @21   ; DXR = 0001
8097  bit  4, *             ; SPC bit 11 = XRDY
8098  bcnd 8097, ntc        ; spin until the shifter has taken it
809a  samm @21              ; and again
```

It continued immediately. Now:

| point | XRDY |
|---|---|
| out of reset, `DXR` empty | set |
| after writing `DXR` | clear |
| mid-frame | clear |
| after a frame sync | set |

Also, a `0 -> 1` edge on `XRST` releases it.

**One scoping decision:** only the AC01 path has a frame clock that can set `XRDY`
again. The legacy TDM path models no framing on this port. Thus, a loop there
would never stop (four tests on that path stop without this), and the path keeps the
optimistic answer that it always had. That is a limit of this model. It is not a behaviour of
the hardware.

### What is still not modelled

The gain, high-pass and loopback settings are decoded and reported, but they do not
yet change the samples. The phase-shift requests are counted, and the model ignores them in all other ways.
The model also ignores the high-impedance window of `DOUT`. The boot queue
replaces it, and the model does not tri-state anything. The legacy TDM path (`m_rom_codec`
false) still decimates at a fixed 9600 Hz and keeps the optimistic `XRDY`. It
is not the AC01 path, and this change intentionally did not change it.

## What this does not establish

The register semantics come from the datasheet, and the words come from the firmware.
We did not measure any of this against the physical codec. It is an inference that the FS rate of the ASIC
agrees with the A/B conversion rate on the real board. The inference comes from the
constraint of the datasheet that the two must agree within half an FCLK period.
It is not an observation. We read the `0x8189` ISR under the boot ROM with an empty
receive queue. Thus, each `DRR` value that it consumed in that run was stale.
