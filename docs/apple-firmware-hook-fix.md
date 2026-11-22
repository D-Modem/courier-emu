# Apple seizure fix: use the original driver's firmware hook command

## Result

**The reproduced seizure failure is fixed in two captured native V.32/LAPM
calls**, including a repeat with the final helper's default configuration and
no environment override. Both endpoints train at 9600 bps and exchange their
complete 180-byte messages exactly. The subsequent [sustained binary/ASCII tests](apple-sustained-traffic.md)
expose unresolved link stalls, block errors and retransmissions. This is not a sustained-throughput or BER
certification, and the historical intermittent network loss is not claimed fixed.

The helper no longer implements normal off-hook transitions by writing raw
DAA register 5 and manually disarming/re-arming OPE. Instead it uses the actual
Apple/Motorola firmware hook operation recovered from the original Windows
stack. The existing nonzero-current, OPD, notification, settling, sample-loss,
reset and fail-closed release guards remain enabled. There is no automatic
fallback to the old register sequence if the firmware command fails.

## Original-driver evidence

The source installer is the Boot Camp `MotorolaSetup.exe` documented in
`../v90modem/docs/apple_usb_modem_sm56.md`, downloaded from Internet Archive:

- Size: 1,840,991 bytes.
- SHA-256: `f22dc4057e41f28c9f5698054fb512f9032ca6a3ed5352847fc1586123414483`.
- Exact Apple binding: `USB\\VID_05AC&PID_1401`.

Read-only Ghidra analysis of the extracted x86 drivers establishes this chain:

1. `USmSerial.sys` `FUN_0009d97b` passes the hook state to `FUN_0009c813`.
2. `FUN_0009c813` sends private IOCTL **0x22009c**, with hook state 0/1.
3. `utlamot.sys` `FUN_0001316a`'s **0x22009c** branch builds a
   `URB_FUNCTION_CLASS_INTERFACE` OUT request with:

   ```text
   bmRequestType = 0x21
   bRequest      = 0x11
   wValue        = 0 (on-hook) or 1 (off-hook)
   wIndex        = 0
   wLength       = 0
   ```

This is **not** the register write operation (`00 <index> <value>` on interface
1). Earlier notes had not traced/tested this hook operation and incorrectly
concluded that the original stack never used the interface-0 control family.
No downloaded Windows code was executed. Installer, extracted drivers,
analysis script, decompilation and logs are private evidence under
`.artifact-archives/apple-seizure-timing-20261024/`.

The hardware accepts this request. The host leaves OPE enabled rather than
manually clearing it, then verifies hook readback, actual loop current and the
full guarded settling interval, including OPD/USB overload notifications.
Protection must read enabled after settling. Firmware internals/re-arm timing
have not been measured; `rearmed_ms=-1` means no host re-arm write, **not**
that protection was disabled. On failure and shutdown the helper releases the
hook, clears firmware hook state and verifies release. Raw register writes
retain the monitor bit and serve as an independent release attempt.

`APPLE_LINE_HOOK_PROTOCOL=register` retains the old path only as an explicit
failure-control diagnostic. It is never selected automatically. Unsupported
firmware requests fail closed rather than retrying through that path.

## Hardware verification

First, the normal PCM smoke probe that had repeatedly failed raw-register
seizure passed with the firmware command. A separate six-second protected
silence probe also passed, including a codec-rate change from 7200 to 9600 Hz
on the fixed 10286-Hz hardware grid. No digits were sent by either probe.

Then two fresh calls used V.32/9600, required error correction, compression off,
200-ms timestamp-based RTP delay plus the existing 200-ms bearer reserve:

| Check | Explicit firmware control | Final default (no override) |
| --- | --- | --- |
| Apple caller | CONNECT 9600/ARQ/V32/LAPM | CONNECT 9600/ARQ/V32/LAPM |
| I-modem receiver | CONNECT 9600/ARQ | CONNECT 9600/ARQ |
| Complete Apple → I-modem payload | 180 bytes exact | 180 bytes exact |
| Complete I-modem → Apple payload | 180 bytes exact | 180 bytes exact |
| Local → PBX packets at both captures | 1439 / 1439 | 1435 / 1435 |
| PBX → local packets at both captures | 1446 / 1446 | 1441 / 1441 |
| Shared payload mutations / unshared identities | 0 / 0 | 0 / 0 |
| Captured outgoing packets exact in DSP TX | All | All |
| RTP playout missing samples / late packets | 0 / 0 | 0 / 0 |
| Active USB TX gaps / RX overflows | 0 / 0 | 0 / 0 |
| Capture kernel drops, both ends | 0 | 0 |
| Independent final hook / protection | On-hook / 0c | On-hook / 0c |

Evidence:

- `.artifact-archives/apple-rtp-firmware-hook-20261024/`
- `.artifact-archives/apple-rtp-default-hook-20261024/`

Each includes `validation-summary.json`, `dual-capture-comparison.json`, raw
private pcaps, extracted RTP, native helper logs and both firmware UARTs.
Capture coverage includes the complete SIP test; comparisons use packet
sequence/timestamp identity and actual payload bytes, not clock synchronization
or concatenation across possible missing timestamps. The first call's sender
API count also agrees with all 1439 locally/PBX-captured outgoing packets.

The final helper was rebuilt; its memory-only self-test and **130 focused
regressions pass**. Tests validate the exact USB setup fields, successful
firmware seizure, command error after it takes effect, hook-readback mismatch,
OPD, disabled/missing protection, cancellation and release ordering. Firmware
mode must not assert the raw hook or clear OPE on the host. The full suite was
not rerun for this follow-up.

## Reproduce

Build and run the memory-only checks:

```sh
.venv/bin/python tools/build_apple_line.py
.build/apple_line --selftest
```

The default now uses the firmware hook command. For one explicitly authorized,
bounded test call with simultaneous captures and a new private directory:

```sh
env -u APPLE_LINE_HOOK_PROTOCOL .venv/bin/python tools/capture_apple_sip.py \
  --run-call --output .artifact-archives/apple-rtp-NEW
```

No gateway/PBX configuration, line gain, current threshold or modem firmware was
changed. Remaining validation is longer/binary payloads, drift and throughput,
and reproducing/localizing the older intermittent network loss if it recurs.
