# C51, C52 and C53 memory models

Older measured Courier boards use the C51 map. MICA uses C53. The 3453C
profile selects C52 with its recovered 4K-word mask ROM. Its current model
has no SARAM. The ROM extent is measured. But the absence of SARAM is a
conservative choice of the board profile until a hardware alias probe is done.

Source: TI SPRU056D, figures 8-2/8-4 and section 8.4 (the PDF is in this directory),
and [TI's C5x datasheet](https://www.ti.com/tw/lit/gpn/tms320lbc53s).
All addresses and sizes below are in 16-bit words.

| Region | C51 | C53 | Control |
| --- | --- | --- | --- |
| Program ROM | 0000–1FFF | 0000–3FFF | MP/MC=0 |
| Program SARAM | 2000–23FF | 4000–4BFF | RAM=1 |
| Data SARAM | 0800–0BFF | 0800–13FF | OVLY=1 |
| Program DARAM B0 | FE00–FFFF | FE00–FFFF | CNF=1 |
| Data DARAM B0 | 0100–02FF | 0100–02FF | CNF=0 |
| Data DARAM B1/B2 | 0300–04FF / 0060–007F | same | always |

SARAM has independent physical storage. When they are enabled, its program
and data windows alias it. If you disable a window, the external storage
becomes visible, and the SARAM contents stay. For diagnostic runs without a
ROM dump, the existing fallback from a missing ROM to loaded program storage
is still available.

For MICA images, Python callers use
`NativeC5x.from_program(origin, image, model="c53")`. For a compatible
container, they use `NativeC5x(xmf, model="c53")`. The default is `c51`. The
standalone runner and `dsp-run` accept `--model c51|c52|c53`. The selection of
a DSP does not add a MICA image parser. It does not emulate the board
peripherals of MICA.

The shared external program/data RAM of the Courier at 8000–FEFF is a board
mapping. C52 and C53 instances start with that mapping disabled. Their harness
must configure all board-specific external aliases explicitly.

GREG selects global external bus cycles, and asserts BR with DS. It does not
make RAM inside the processor. By default, GREG keeps the existing storage
mapping of the board. If a board uses BR to select different storage, it can
request `separate_global_memory=True` on the two Python constructors, or use
`courier_c5x_set_separate_global_memory` in the C API. This option supports the
contiguous allocations 80, C0, E0, F0, F8, FC, FE, FF from TI table 8-14.
Fragmented allocations for other values and the BR/READY arbitration timing
are not modelled. GREG resets to zero and reads unused high bits as ones.

## Program interrupt/vector area

Program 0000–003F contains executable vector slots and reserved slots. It is
not a separate RAM or data-register window. Each vector reserves two words for
a branch instruction. This area follows MP/MC in the same way as the remaining
low program memory: ROM when MP/MC=0, external program storage when MP/MC=1.
Reserved labels tell the intended use. The emulator does not make those words
unreadable.

Reset clears IPTR and starts execution at program 0000. Later interrupts use
their slot offset in the 2K-word page that PMST.IPTR selects (for example,
INT2 at `(IPTR << 11) | 0004`, NMI at `(IPTR << 11) | 0024`). The processor
executes the instruction at that address. It does not read a handler pointer.
Refer to SPRU056D section 8.2.2 and table 8-7. If the harness configures them
explicitly, diagnostic line-frame vector overrides can bypass the usual vector
selection.

The 3453C bridge explicitly aliases external data/program RAM at 1000–7FFF.
It maps DSP I/O 8050–807F to the host ASIC. Its recovered ROM executes the
first transfer with IN instructions. Resident overlays execute IN/BLDP.
Refer to [the boot comparison](../artifacts/3453c-emulator-boot-20261003/README.md).
