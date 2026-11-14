# 302/403 DSP boot integration

The two runs execute 60,000,000 supervisor instructions from the flash reset
vector. They use the recovered DSP boot ROM (enabled), board ID 7, the
`CourierNvram.idsl302_fixture()` EEPROM fixture and a 5 ms supervisor tick.
The input is `AT\rATI7\r`. Run it from the repository root:

```sh
.venv/bin/python artifacts/dsp-boot-integration-01/run.py
```

On macOS, Unicorn must have an execution environment that permits its native
memory mappings. We ran these checks outside the Codex filesystem sandbox.

| Result | 302 | 403 |
|---|---:|---:|
| DSP revision reported by ATI7 | 3.0.13 | 3.1.2 |
| OK responses | 2 | 2 |
| Unconsumed serial input | 0 | 0 |
| DSP downloads | 1 | 1 |
| Download matches image | yes | yes |
| DSP errors | none | none |
| Missing ROM accesses | 0 | 0 |
| IPTR | 0 | 0 |
| ROM program accesses | 3,195,350 | 3,283,995 |
| Frame interrupts serviced | 160,244 | 242,591 |
| Serial DXR writes | 158,610 | 240,753 |
| Serial control writes | 5 | 5 |

The five serial control writes are one initialization. They are not a
repeated re-entry into the reset prologue of the DSP. At termination, the DSP
runs its service code. `instruction-limit` is the intentional end of the run.
The ROM images use supervisor addresses that are different from the XMF
milestone recognizer.

The `.json` files keep the emulator reports. The `.txt` files decode the
parity bit of the DTE to show the AT responses. The first report is older than
the `boot_rom_enabled` summary field. Its ROM mapping and its access counters
show the actual execution path.

The bridge buffers the ASIC download and supplies its serial table at the
checksum submission. The ASIC handshake timing and the checksum acceptance
are still modeled. Now, the boot words share the codec queue of DRR. Thus,
they count as codec input. These runs do not dial, train or establish an
end-to-end data connection.
