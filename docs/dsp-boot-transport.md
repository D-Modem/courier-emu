# The DSP's boot ROM has two generic boot transports

> **Superseded for the Courier CPU download path, 2026-09-14.** We did a complete
> comparison of the captured 80186 downloader with the ROM code. It identifies the
> board protocol as the separate mask-ROM service loader at `0610`. That loader uses
> four-word ASIC holding registers and `BLDP`. The overlay loader of the downloaded resident
> later uses the same ASIC transport. Refer to
> [The 80186/C51 download architecture](c51-cpu-loader.md).
>
> The serial and `XF`/`BIO` loaders that this document describes are real ROM functions.
> But neither agrees with the four-word 1/2/4 protocol of the supervisor. Specifically,
> we withdraw the later inference that the ASIC writes program RAM directly while the DSP
> is held in reset.

> **Measured, but weaker than first stated.** The ASIC of the board gives
> **`0x0083`** at DSP data `0xffff` *while the modem operates normally*, long
> after the boot. Its low two bits are `3`. This is a mode that transfers nothing and
> branches to `0x8000`. Refer to
> [artifacts/dsp-boot-word-01/result.md](../artifacts/dsp-boot-word-01/result.md).
>
> **That is not the same as knowing the value of the cell during reset**. The
> supporting argument that we gave first is not strong. The claim
> that it "decodes to exactly the download destination" is weak, because *any*
> value `0x80`-`0x83` gives the entry `0x8000`. Only the low two bits have content.
>
> **We withdraw the board inspection that argued for a serial download.** It
> said that the ASIC-to-DSP link was serial. The board shows a different result: the ASIC is
> on the 16 data pins of the DSP, and `IS` is connected to it. Thus, the link is
> parallel. Refer to
> [dsp-cpu-interconnect.md](dsp-cpu-interconnect.md). This removes the support
> for the serial loader. But it does **not** make the parallel loader
> the better choice. The read above is still a read at runtime, and we did not measure the value
> at data `0xffff` during reset. The `host_write(0xFFFF, 4)` of the harness is
> now a choice without support. It is not a confirmed choice.
>
> Also note that a `0xffff` read is a `DS` cycle. Thus, the ASIC answer to it is a
> separate question from the `IS` decode that is now established.
>
> We keep the two loaders and the argument for the parallel loader below, because
> the loaders are real and the reasoning led to the measurement. But
> its conclusion is superseded.

The recovered on-chip ROM (`artifacts/dsp-onchip-rom-01/c5x-onchip-rom.bin`)
contains **two** boot loaders, not one. Earlier notes here
([dsp-onchip-rom.md](dsp-onchip-rom.md), and the first version of
[ac01-codec-protocol.md](ac01-codec-protocol.md)) describe only the serial loader.
The reason is that the disassembly that they used stopped at `0x0700`, and the second
loader starts at `0x072c`.

## The dispatch

The loader reads its boot word from data `0xffff` into `@60`. After the low
two bits select "serial-ish", it tests two more bits:

```
06c6  4c60         bit  12, @60      ; bit 3 of the boot word
06c7  e100 072c    bcnd 072c, tc     ; set   -> the parallel loader
06c9  4d60         bit  13, @60      ; bit 2
06ca  f200 06d4    bcnd 06d4, ntc    ; clear -> 8-bit, set -> 16-bit
06cc  5e22 ff01    apl  @22, #ff01   ; SPC
06ce  5d22 0038    opl  @22, #0038   ; SPC
```

`bit k` tests bit `15-k`. Thus, `bit 12` is boot-word bit 3, and `bit 13` is bit 2.

| boot word | bit 3 | bit 2 | loader | transport |
|---|---|---|---|---|
| `0x04` | 0 | 1 | `0x06e2` | serial, 16-bit |
| `0x00` | 0 | 0 | `0x06f7` | serial, 8-bit pairs |
| `0x0c` | 1 | 1 | `0x0731` | **parallel, 16-bit** |
| `0x08` | 1 | 0 | `0x0748` | **parallel, 8-bit pairs** |

## The serial loader

This loader only receives, on the **primary** serial port of the C5x. It reads `DRR` (data `0x20`) and
polls `RRDY` (`SPC` bit 10, data `0x22`). It never writes `DXR`.

```
06de  4522  bit  5, @22   ; SPC bit 10 = RRDY
06e8  1020  lacc @20      ; DRR
06f3  a720  tblw @20
```

## The parallel loader, which nothing here had seen

Its word fetch is an **`XF`/`BIO` handshake**, and the data comes on a
memory-mapped port at data `0x50`:

```
0775  be4d    setc xf            ; assert XF - "send a word"
0776  e000    bcnd 0776, bio     ; spin on the BIO pin
0778  be4c    clrc xf
0779  ec00    retc bio           ; return once BIO says the word is there
077a  7980    b    0779
```

16-bit mode reads the port once for each word. 8-bit mode assembles a word from two
reads:

```
0731  7a80 0775   call 0775            ; 16-bit: fetch
0733  0950 0066   smmr @50, #0066      ; ...and take the word from port 0x50
...
0748  7a80 0775   call 0775            ; 8-bit: fetch
074a  1850        lacc @50, 8          ; high half
074c  7a80 0775   call 0775            ; fetch
074e  6950        lacl @50             ; low half
074f  bfb0 00ff   and  #000000ff
0751  6d66        or   @66
```

`SMMR dma, #addr` moves the memory-mapped register at `addr` into `dma`. Thus,
**`@50` is the source**: the DSP reads a port that the ASIC drives. It does not write
a port. The block-write loop has the same `tblw` / `banz` shape as the loop of the serial
loader.

## Why this is very likely the transport the board uses

We did not measure the value that the ASIC gives at data `0xffff`. Thus, this is
an argument from fit, not a reading. But four facts agree:

1. **The download of the supervisor is parallel.** It writes a window at 80186 ports
   `0x40`-`0x5e`. To feed the serial loader from that, the ASIC must do a
   parallel-to-serial conversion. [dsp-onchip-rom.md](dsp-onchip-rom.md)
   flagged this at the time as "a role for it this repository had not identified".
   The parallel loader does not need this conversion.
2. **Data `0x50` is already known to be the ASIC window.** The downloaded
   resident polls I/O `0x50`/`0x52`/`0x54` for the mailbox, and the codec ISR
   writes a scaled sample to `0x50` at program `0x8199`. The boot loader reads
   the same address. It is the same window, used earlier.
3. **It does not touch the port of the codec.** The AC01 owns the primary serial port.
   (The TI `slaa006` reference design connects it there, and it pulls the TDM port
   to COM.) A serial boot must share that port with the codec for the
   duration of a 27,710-word download. The only quiet window of the AC01 (`DOUT`
   in high impedance) lasts **eight frames**. That does not fit. This is why
   we withdrew the high-impedance explanation in `ac01-codec-protocol.md`.
4. **`XF` is connected to the `RESET` of the codec.** `slaa006` drives `RESET` from `XF`,
   and the parallel loader drives `XF` for each word that it fetches. Thus,
   the codec cannot listen quietly during a parallel
   download. This is exactly the arbitration that a shared serial port does not have.

## What the harness does today

`_configure_boot_rom` in `bridge.py` writes `host_write(0xFFFF, 4)`. Bit 3 is
clear, thus this selects **the serial loader**. We selected that value when we knew only the serial
loader. `dsp-onchip-rom.md` gives the choice as if bit 2 were
the only degree of freedom ("that single bit is what the ASIC has to present").
That is not correct.

The serial path does boot the DSP in the emulator. The download completes, the
firmware runs its prologue, programs the six registers of the codec and gets to its
idle state. Thus, this is not a bug that causes a failure. It is a transport that
works in the model, but it is probably not the transport on the board.

## What settled it

The board gave the answer, through the RAM-monitor rig that recovered the ROM. `--boot-word` builds
a DSP kernel that reads one data address sixteen times and sends the values
back through the mailbox. All sixteen reads gave `0x0083`.

Decode this value with the dispatch above: `0x0083 & 3 == 3`. This goes past
all three tested branches to `0x0696`. There, the loader moves
`(0x0083 << 8) & 0xfc00 = 0x8000` into `@66` and does `bacc`. **It transfers
nothing and branches to program `0x8000`**. This is the origin of the resident, and the
address that the download of the supervisor goes to. The entry is in bits 7:2 of the boot
word.

When we run the recovered ROM in the emulator with each candidate, the result confirms the
decode:

| boot word | outcome |
|---|---|
| `0x0083` (measured) | gets to program `0x8000` |
| `0x0004` (what the harness assumes) | stops at `0x06dc`, the wait of the serial loader |
| `0x000c` (the parallel hypothesis) | stops at `0x0779`, the wait of the XF/BIO loader |

Thus, the ASIC writes the resident directly into the external RAM of the DSP (the two
`CY7C199` at program `0x8000`-`0xffff`) while the DSP is held in reset. The
release of the reset is the "go". That is also why the download sequence has no "go"
command after it. `dsp-map-302.md` saw this and explained it differently.

**Thus, the mechanism of the harness is not correct, but its result is correct.**
It writes 4 to `0xffff` and serializes the transfer of the supervisor through the
serial loader of the ROM. The resident is at `0x8000` at the end in the two cases. This is why
this never caused a failure. A correct model would have the ASIC put
the resident in DSP RAM and the ROM do a warm start. That is simpler than the current
model.

### The caveat

We read the value while the modem operated normally, after its own
download. The strict measurement is that the ASIC holds `0x0083` there
**during normal operation**. That it holds the same value during the reset
window is an inference. Sixteen identical reads show that it is a held level and not
traffic. It decodes to exactly the download destination, and an old
mailbox word would not do this by chance.
