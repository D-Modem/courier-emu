# Hardware memory dumps

Flash, RAM and ROM images read off physical boards. These cannot be regenerated
without the hardware, so they live apart from the experiment output in
`artifacts/` and are never archived or pruned by `tools/archive_artifacts.py`.
Each directory's `manifest.json` (or `result.json` for the 3453 reads) records
the device, firmware identity and SHA-256; treat it as the authority.

`responses/` and `blocks/` (per-page serial replies and 256-byte pages) are
`.gitignore`d; the assembled images and `pages.jsonl` are tracked, so
`audit_capture.py` only runs in a working tree that still holds them.

## Courier V.Everything CPU flash (0x80000-0xfffff)

| Directory | Board / firmware |
|---|---|
| `courier-board-21210-capture-403/` | 20.16 MHz, ID_SDL v4.03d, supervisor 7.4.16, DSP 3.1.2 (the 403 image) |
| `courier-board-21210-capture-01/` | Same board before reflashing, with its audit and recovered-handler check |
| `courier-board-11430-flash-20260914-02/` | Australian unit 1: 061-7.4.16, DSP 3.0.13 |
| `courier-board-11430-flash-20260914-unit2-02/` | Australian unit 2: 061-7.6.7, DSP 3.1.2 |
| `courier-2806-25mhz-flash-20260912/` | 25 MHz 2806: 7.3.14, DSP 3.0.13 |
| `courier-714-221-flash-20261007/` | 20.16 MHz: 7.1.4, DSP 2.2.1 |

## Courier RAM

| Directory | Window |
|---|---|
| `courier-board-21210-ram-01/`, `courier-board-21210-ram-403/` | `00000..0feff`, two live passes |
| `courier-board-21210-upper-ram-01/` | `10000..1ffff` |
| `courier-board-11430-ram-20260914{,-unit2}/` | `00000..0feff`, both Australian units |
| `courier-board-11430-upper-ram-20260914{,-unit2}/` | `10000..1ffff`, both Australian units |

## TMS320C5x on-chip ROM

| Directory | Source |
|---|---|
| `dsp-onchip-rom-01/` | 20.16 MHz 403 board (serial 0009540034268322), first read |
| `dsp-onchip-rom-20mhz-8k/`, `-saram/` | Same 403 board, full 8K; the second read from a gadget running in on-chip SARAM |
| `dsp-onchip-rom-2806/` | 25 MHz 2806 |
| `dsp-rom-half0/`, `dsp-rom-half1/`, `dsp-rom-dump-v1/`, `dsp-rom-dump-v2/` | Earlier half and full reads via the diagnostic transport |

## Courier 3453

| Directory | Contents |
|---|---|
| `3453bc-firmware-read-2.2.09/`, `3453bc-4MBRYA8G1514-bootmodem-read-20261014/` | 3453B/C serial 4MBRYA8G1514: firmware 2.2.09 and boot-modem |
| `3453c-5MBRZ16P0186-firmware-read-20261014/`, `3453c-5MBRZ16P0186-bootmodem-read-20261014/` | 3453C serial 5MBRZ16P0186: firmware and boot-modem |
| `3453c-firmware-read-20261003/` | Earlier read of the same 3453C firmware (identical SHA-256), with its XMODEM frames |
| `3453c-parameter-sector-20261003/` | Flash `f8000..fffff` parameter sectors |
| `3453c-dsp-mask-rom-read-20261003/` | DSP mask ROM `0000..0fff` and the comparison against the Courier ROMs |
| `3453c-dsp-memory-read-20261003/` | DSP program `0000..7fff` and partial data reads |
