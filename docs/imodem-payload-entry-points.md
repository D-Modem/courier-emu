# I-modem Ie030002 payload entry points

**Updated:** [the VRTX startup trace](imodem-vrtx-startup.md) now follows
`4030:0000` through the kernel initialization and nine running tasks.
The historical "updater" labels below do not mean that this is only an
update program: `a400:0008` is registered as the `TID_MODEM` task entry.

We verified these entries directly from the decoded `Ie030002.xmp` bytes. The
flattened `Ie030002.nac` payload is byte-identical and starts at physical
`0x40000`. The offsets below are in the decoded payload. For XMP file offsets,
add `0x80`.

| Entry | Physical | Payload offset | Purpose / evidence |
|---|---|---|---|
| `4030:0000` | `0x40300` | `0x00300` | Updater initializer. It sets DS and the stack, clears RAM, initializes the hardware, copies data and installs vectors. Then it does a far jump to `7360:1ec0`. This is the existing emulator entry. |
| `7360:1ec0` | `0x754c0` | `0x354c0` | Updater kernel startup. It installs INT 30 at `7360:0000` and INT 31 as a pointer to the descriptor at `98d1:0000`. Then it calls INT 30 with AX=30h. |
| `7360:0000` | `0x73600` | `0x33600` | Updater INT 30 service gate. The startup before it installs it explicitly. |
| `4000:0000` | `0x40000` | `0x00000` | Debug-service dispatcher that you can far-call, with the selector word at physical `0xd0`. It keeps DS and the general 16-bit registers and returns with RETF. It is not a boot entry. |
| `4000:0148` | `0x40148` | `0x00148` | Debug exception handler. Dispatcher operation 0 installs it into vector 1. |
| `a400:0008` | `0xa4008` | `0x64008` | Confirmed `TID_MODEM` task entry, created through VRTX service 00. It starts with the DSP initialization. The kernel and subsystem setup must occur before it. |

The debug dispatcher has five identifiable table words at payload offset
`0x1b`: `0025`, `005b`, `0097`, `00d2`, `010d`. Operation 0 saves the old INT 1
vector, clears DR0–DR3 and DR7, and installs its handler. Operations 1–4 write
DR0–DR3 in that sequence. These are internal branches that share the saved
stack of the dispatcher. You cannot call them as independent functions. The
range check actually permits the doubled index `0x0a`, one word after those
five entries. Do not assume that selector 5 is a valid service.

## The NAC start record is not a verified executable entry

The NAC type 03 record names `0ce0:0000` (physical `0xce00`). The updater copies
`0x41c0` bytes from physical `0x98d50` to that RAM address. These bytes start
with the text `New entry added`. They are not a credible startup sequence.
Thus the record does **not** confirm the far-jump destination `7360:1ec0`,
although the older comment in `courier_emu/isdn.py` says so. For the recovered
updater path, enter through `4030:0000`.

## Supervisor cold start remains unconfirmed

The update payload stops at physical `0xf8000` (exclusive). It does not contain
the top 32 KiB boot block or the reset vector at `0xffff0`. The existing
synthetic boot block is an emulator construction. It is not evidence of the
entry of the board. A real dump of the boot block would show the reset
handoff. But the absence of that block alone does not prove that the
application entry is not in the remaining part of the payload.
