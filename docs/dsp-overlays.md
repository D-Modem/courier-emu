# The DSP takes four images, not one

> **Transport correction, 2026-09-14.** The downloaded C51 loader at `811b..8138`
> consumes the overlay. It reads the ASIC holding registers
> and does the program-memory `BLDP` writes itself. It uses the same
> physical ASIC register bridge as the mask-ROM resident loader at `0610`.
> Direct publication through `core.load_program` is a shortcut of the emulator. It is not the mechanism of the board.
> Refer to [The 80186/C51 download architecture](c51-cpu-loader.md).

The supervisor downloads a resident C52 bank at boot. It can also send three
more images, and the resident bank is only one row of the same table that
names them. This document records the mechanism, the map, and what it does and does not
explain.

## Two transfer routines, one set of ports

The two routines push words through the same eight data ports, `0x40`-`0x4e`, four words for each
block. They are different in the handshake and in the origin of the source.

| | resident downloader | overlay loader |
|---|---|---|
| handshake port | `0x18`, one acknowledgement per block | `0x1e`, one per half-block, `1` then `2` |
| source segment | hard-coded `mov ax, a914` | selected by index |
| entry | `mov ax, 8000` at the call site | the table's third word |

Because of that hard-coded segment, a second payload could not come through the
first routine. That routine can only send the resident bank.

## The table

The loader masks a four-bit code, multiplies it by six and adds a table base
(`mov bl, 6 ; mul bl ; mov bx, <table>`). Then it selects the source segment: it
compares the same code with 6, 7 and 8, and uses the resident
segment for all other values. Each row is three words: the start offset, the end offset, and the C52 program
address to load at.

`courier_emu.rom.CourierRom.dsp_overlays` reads it. The length of the table is not
marked, and the rows after its end still look like possible ranges. Thus, a row is kept
only if the loader has a segment for its index, or if it is the resident row. The
full result is discarded unless one row reproduces what the download call
site says independently. That check identifies the table. It does not
assume it.

For the 3.1.2 board:

| id | flash | words | loads at |
|---:|---|---:|---|
| 5 | `29140..36e8e` | 28,327 | `8000` (resident) |
| 6 | `36e90..3d0f4` | 12,594 | `9d00` |
| 7 | `3d100..40b94` | 7,498 | `b000` |
| 8 | `40ba0..44634` | 7,498 | `dc00` |

All three 512 KiB images agree on those four entry addresses (standard 7.3.14,
ID_SDL 4.03 and the flat `IDSDL302.ROM`). Only the lengths are different.

The map shows two facts. Overlays 6 and 7 **overlap in program space**.
Thus, they are alternatives that load one at a time, not three pieces of one program.
Also, each overlay goes *into* the range of the resident bank itself, which goes to
`eea7` here. Thus, when one loads, it overwrites resident code. It does not extend it.

## What the overlays contain

They contain nothing that communicates with the outside world. Across all three:

| | `out *, 0060` | `samm @21` (DXR) | codec writes |
|---|---:|---:|---:|
| resident | 1 | 4 | 6 |
| overlay 6 | 0 | 0 | 0 |
| overlay 7 | 0 | 0 | 0 |
| overlay 8 | 0 | 0 | 1 |

They have no host sender and no serial transmit. They are algorithm code, fed by
the ISR of the resident bank.

The single codec write of overlay 8 is **register 4 again**. It loads `0409`, adjusts
the low byte conditionally by four and then by one, and calls the resident
sender. Thus, with the overlays included, the result in
[codec-rate-312.md](codec-rate-312.md) does not change. Each codec write that this
firmware makes after reset (three from the supervisor by tag `2c`, one from
overlay 8) goes to register 4.

> **Corrected.** Before, the last sentence was "the divider registers are
> written once, at reset, and never again". That is false. The rate selector at
> `8140` writes register 2 from a six-row table, and the overlays get to it. The
> `call <sender>` counts above do not find it, because it inlines the handshake of the sender
> and does not call it. Overlay 6 selects 8000 Hz at its entry. For a short time, this document recorded
> that overlay 7 selects 7578.95 Hz. That was a data-page error, and we
> withdraw it. No evidence shows that overlay 7 selects a rate. Refer to
> [codec-sample-rates.md](codec-sample-rates.md). That document also identifies
> overlay 8 as the V.90 layer, and overlay 6 as the PCM core that runs together with it.

## A correction to driving-the-tones.md

The third blocker of that document says that the entry of tag `0x19` at `0xdaaf` "falls in the
gap between the resident bank ending at `0xd9ef` and the overlay starting at
`0xde83`, so it reads as zeros".

With the payload as `dsp_download` now extracts it, none of that is correct. The
3.0.13 resident bank goes from `8000..ec3e`, not to `d9ef`. The overlays load at
`9d00`, `b000` and `dc00`, not at `de83`. `0xdaaf` is in the resident bank and
holds instructions, not zeros. The payload has no zero run longer than
32 words. Thus, it is necessary to check again the premise of that either/or. The
table above is the measured replacement for its resident/overlay boundary.

## The bridge now services a mid-call overlay transfer

Until 2026-09-09, the bridge discarded each overlay download. This
is why no run in this project ever made a second `bootstrap`. There were three
separate faults. We found each one when we measured what arrived, not when we read the code:

**1. The wrong handshake port.** The strobe path examined only
`self.transfer.command_port`. For a board ROM, that is `ROM_COMMAND_PORT`
(`0x18`). The overlay loader acknowledges on `0x1e`, as the table at the top
of this document records. Writes to `0x1e` returned early. Thus, the payload
windows were never committed, and the firmware strobed correctly into a port
that nothing monitored. This fix alone took the answering side from 6
window strobes to 3,750.

**2 and 3. The wrong block size, and the wrong window for the second half.**
First, we inferred these from the data that arrived. The first window came as
`06bc807a` + old bytes, against `06bc807a9fad807a` of overlay 7. But
the inference is not necessary, because the loop is in the image. From `0x8e6c2`:

```text
8e6c2  in   al, 0x1e / test al,1 / je wait / test al,2 / je wait
8e6cc  lodsw ; out 0x40, al ; out 0x42, ah      ; word 1
8e6d4  lodsw ; out 0x44, al ; out 0x46, ah      ; word 2
8e6dc  mov  al, 1 ; out 0x1e, al                ; acknowledge the first half
8e6f1  in   al, 0x1e / test al, 2 / je wait
8e6f7  lodsw ; out 0x48, al ; out 0x4a, ah      ; word 3
8e6ff  lodsw ; out 0x4c, al ; out 0x4e, ah      ; word 4
8e707  mov  al, 2 ; out 0x1e, al                ; acknowledge the second half
8e70b  loop 8e6af
8e730  mov  al, 4 ; out 0x1e, al                ; end of transfer
```

Thus, this is the real method, read from the code and not fitted:

* a **block is four words**, low byte then high byte to `0x40`, `0x42`,
  `0x44`, `0x46`, then `0x48`, `0x4a`, `0x4c`, `0x4e`;
* the loader acknowledges **two times for each block**: `1` after words 1-2, `2` after
  words 3-4. Thus, each acknowledgement covers **four bytes**;
* the two halves are lanes of the **same** eight-port window. The strobe `2` of the resident
  downloader, which selects `0x50`, has no equivalent here;
* it polls `0x1e` for bits 1 and 2 before each half, and for 1, 2 and 4 before
  the closing `out 0x1e, 4`;
* `CX` is the block count, `(end - start) / 2 / 4` rounded up, from the same
  table row. `ES` is the source segment that the code selects when it compares the id with 6,
  7 and 8, with the resident segment for all other values.

Thus, `out 0x1e, 4` marks **the two** boundaries: at `0x8e631` to start and at
`0x8e730` to end. This is why the bridge uses that value as a transfer
reset and not as data.

The empirical framing and the firmware agree exactly. The reconstructed
14,996-byte image is identical to the ROM byte for byte, and this is the same statement in
a third way.

### What it does now

`_accumulate_overlay` takes half-blocks. It identifies the overlay when it compares
its first eight bytes with **the overlay table of this ROM**. The ASIC then
publishes each complete four-word block at DSP registers `58..5b` and sets
status bit `0200`. The resident routine at `811b..8138` does the four
`BLDP` writes, increments the destination in `ff62`, and acknowledges with
`0300`. Only after those writes does the bridge compare the program RAM with the
ROM payload. Nothing calls `core.load_program` on this path.

Measured on a two-instance link, with A as the originator and B as the answerer:

| | side A | side B |
|---|---|---|
| `overlay_downloads` | 0 | **1** |
| `overlay_id` | - | **7** |
| `overlay_match` | - | **true** |
| `call_overlay_active` | false | **true** |

Overlay 7, 14,996 bytes, identical to the ROM byte for byte, loaded at `b000`.
This is the address that the table of this document gives. The DSP requests it on the answering side.
Refer to
[datapump-gate-403-addresses.md](datapump-gate-403-addresses.md) for the
chain from the request to `out 0x1e, 4`.

`tests/test_asic_ports.py`, `test_mailbox_protocol.py`,
`test_dsp_board_ndx.py` and `test_g_dsp_capture.py` pass without changes.

This does not yet claim a completed call. It claims that the datapump image
now gets to the C52. No run before it did that.

### Transport wake signal

The recovered mask ROM now installs the resident, and the running resident
installs the flash overlays. Neither path publishes program memory directly. The
ASIC acknowledges the first half-block when it has latched it. Then it holds
the second-half ready bit until the C51 has consumed the complete block and
written `0300`.

The board reset net wakes the service path of the C51: 80C186EB `P1.1`
(CPU pin 58) drives C51 `RS` (pin 127). The reset release enters the mask-ROM path.
The model then uses the status latch that the firmware reads. Its data and
acknowledgement behavior is visible independently from the two processors.

This also found one defect. The first version of the publish set
`_call_overlay_active`. That flag belongs to the in-resident call overlay of main211,
which is a different mechanism that `_find_call_overlay` finds by its signature. A flash
overlay is not that. It now reports itself only through `overlay_downloads`,
`overlay_id` and `overlay_match`.

## Destination handshake correction, 2026-09-21

The start strobe holds CPU port 1e bit 2 low until the DSP operates on the tag-02
destination. Detect this through the guest write count at data FF62. Do not
wait for its value to change, because a valid destination command can repeat the
value that is already there. The old value-change test stopped such a transfer
before its first payload group. A native-core regression executes the same-value
store, and checks that the CPU status becomes ready only after that write.
This establishes the handshake defect. It is not the cause of each reported overlay
stall. To reproduce a specific stall, you still need its image and its run command.
