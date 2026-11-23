# x2 downstream loss at the analog DSP output boundary, 2026-10-27

## Result: narrower diagnosis, not a reliability fix

With the explicit **S39=8** correction retained, the analog Courier can receive
an **octet-aligned, independently FCS-valid downstream frame before HDLC
processing**, yet publish a shortened frame to its supervisor. The CPU ring
exactly matches those shortened DSP output words; its independently computed
CRC matches the firmware's rejection register.

This is different from the [stored-S39=0 upstream corruption](imodem-x2-s39-headroom-20261027.md),
where malformed bits already precede the DSP deframer. The new downstream
capture localizes loss between valid input to the analog DSP HDLC path and
its finite host output lanes. It does **not** establish a PCM demapping fault,
a CPU CRC bug, or a DTE delivery fault for this captured frame.

The original firmware, EEPROM files, payloads and traffic gates remain
unchanged. **No new x2 pass was obtained.** Both a true 53333 ceiling and finer
CPU/DSP service-cadence controls still fail. The 60-second/full-rate reliability
qualification remains open.

The [subsequent IRQ/lane trace](imodem-x2-irq-lanes-20261027.md) adds a bounded
native CPU/DSP timeline, distinguishes interrupt polling from DSP service
cadence, and confirms an actual **48000/x2 CONNECT**. Finer interrupt polling
improves delivery but still fails; the 48000 trace also loses a boundary token
between two valid input frames. None establishes sustained x2 reliability.

## Passive observation

`--analog-trace-link-errors` enables the original 403 ROM observer in
`courier_emu/rom_link_errors.py`. It uses narrow CPU memory-write hooks, not a
Python per-instruction or per-bit callback. Original ROM signatures are checked
before execution. Relevant addresses, with DS=0 in these captures:

| Path | Original address / cell |
| --- | --- |
| ATI6 generic counter table | base `0414`; selector 1F resolves to BLER dword `044C` |
| Periodic pending-error consumption | `854BE..854CD`; latch `03F7`; increment `854C8` |
| Main/alternate receive rejection | `90137` / `9015F`, setting `03F7=1` |
| Frame-close CRC comparison | `907B3`, residue `F0B8`, CRC register `02AF` |
| Receive length | `03BC` |
| Main ring / frame start | `B000..BFFF` / `025A` |
| Alternate ring / frame start | `1A80..1AFF` / `0262` |

Every verified rejection/increment is counted. At most four snapshots per
phase/kind retain registers, stack, frame bytes, CRC, DSP state and bounded
native I/O history. Non-error writes, such as boot RAM tests touching the
counter address, are counted separately as `other_write`, not BLER increments.
Results appear under `analog.rom_link_errors` in `result.json` and
`rom_link_errors` in `analog-result.json`.

The bridge also arms the native 64-row coherent capture at **8304**, the
original receive-bit dispatcher, with live **0320/0322** word/count cells.
Arming survives DSP rebuilds. Because the resident is downloaded later, its
five original words are checked at snapshot time; unverified rows are never
decoded. Each retained row contains native instructions, cycles, ACC, DP,
carry and the two live data cells. The offline decoder requires DP=6 and a
supported count and uses **0320**, not an assumed live ACC value.

`--analog-link-diagnostics`, requiring `--link-diagnostics` and a traffic
window, separately performs guard / `+++` / `ATI6` / `ATO` only **after** the
measured window. It requires a complete return CONNECT, bounds captured text
and timeouts, and preserves failures. One query timed out; no ATI6 BLER value
is claimed for that run. These diagnostics cannot make a failed window pass.

## Qualified coherent boundary

Artifact: `artifacts/imodem-x2-downstream-coherent53333-20261027-091843/`.
Analog initial CONNECT: **53333/x2**. Explicit upper limit: **&N36**.

At analog line frame 2547, independent unstuffing of the coherent bit groups
finds two complete FCS-valid frames. The rejected one is:

```
pre-HDLC, 26 octets, FCS valid:
01 8e ac 95 26 d2 84 9a 83 dc 63 55 c8 25 a1 bb 73 46 c8 94 63 9b 40 09 6f 54

DSP bank output and CPU ring, 23 octets, raw CRC 9505:
01 8e ac 95 26 d2 84 9a          55 c8 25 a1 bb 73 46 c8 94 63 9b 40 09 6f 54
```

All **23** ring octets appear consecutively in native DSP writes at **832E**
to banks **58..5D**, followed by the ordinary **FF00** close/flag token.
The missing **83 DC 63** are absent from the DSP output, not merely omitted by
the CPU's bank reader. This capture has zero observed I-modem upstream BLERs.

Two further controls reproduce this boundary: three missing octets with a
256-instruction service period, and four with a 64-instruction period. The
latter additionally retains **four status reads at 0056 with all six receive
free bits clear** (`value & 3F00 == 0`). Original `8320..8334` checks the selected
free bit and returns without publishing the current octet when it is clear.
That is consistent with finite-output-lane exhaustion. It is **not yet proof**
of why the CPU is too late: interrupt/in-service scheduling, the CPU timebase,
and acknowledgment/status modeling still need to be distinguished.

The experimental service periods are **reverted**. The retained default is
still `NATIVE_ROM_SERVICE_INSTRUCTIONS = TIMER_POLL_INSTRUCTIONS` (1024).
Changing cadence alone did not fix the loss and is not presented as a fix.

## Calls and unchanged gates

All windows below are 20 seconds with 512-byte ASCII payloads. Counts are
**in-window** upstream / downstream, not final-drain totals. BLER values are
final counters except explicitly labeled ATI6-only values.

| Artifact suffix (all 20261027) | Service period | U / D | Upstream BLER | Downstream BLER | Gate |
| --- | ---: | ---: | ---: | ---: | --- |
| `analog-ati6-stall-085707` | 1024 | 11 / 7 | 0 | 32, ATI6 only | FAIL |
| `s39-ceiling53333-085858` | 1024 | 13 / 8 | 0 | 44, ATI6 only | FAIL |
| `first-downstream-crc-090800` | 1024 | 12 / 9 | **1** | 36 | FAIL |
| `downstream-coherent53333-091843` | 1024 | 14 / 7 | 0 | 67 | FAIL |
| `downstream-service256-092450` | 256, reverted | 14 / 9 | 0 | 53 | FAIL |
| `downstream-service64-093015` | 64, reverted | 11 / 10 | 0 | 36 | FAIL |

All x2 directories have prefix `imodem-x2-`. **&N39 permits 57333**, not
53333; the ceiling control uses **&N36** and still fails. The coherent call's
ATI6 prints downstream speed 52000 and a return CONNECT 53333. Its ATI6 BLER
count is 66; the final memory counter is 67, so query and final totals must
not be conflated.

S39=8 removes the dominant earlier upstream corruption, but does not establish
universal zero-BLER operation: the first downstream-observer call has **one
upstream rejection during the measured window** (I-modem frame 533). Its analog
ATI6 query later times out. Retain that counterexample rather than describing
all corrected calls as upstream-error-free.

The fresh unchanged fixed14400 V.34 regression,
`artifacts/imodem-v34-downstream-observer-regression-20261027-093702/`, passes
with the new observer enabled: **13/13** records in-window, maximum gaps
**1.6/1.7 seconds** upstream/downstream, zero BLERs at both receivers. Final
drain is 14/13. No UART overruns, terminal drops, PCM underruns, or connected
receive underruns were observed in these seven calls.

## Replay and validation

```
PYTHONPATH=. .venv/bin/python tools/imodem_receive_boundary.py \
  artifacts/imodem-x2-downstream-coherent53333-20261027-091843/result.json

PYTHONPATH=. .venv/bin/python \
  .artifact-archives/imodem-downstream-boundary-20261027/verify.py
```

The private verifier replays all seven calls' complete records and partial
prefixes from captured DTE output, hashes, unchanged five-second trailing-gap
and ten-record requirements, UART/PCM health, BLER counters, and all three
coherent downstream boundaries. It preserves all six x2 failures.

**106 focused tests pass.** A broader C5x/focused attempt timed out after
60 seconds, so no broader-suite pass is claimed. A separate bridge-audio test
selection reports 86 passes and one failure: its `__new__`-constructed bridge
fixture lacks `line` at the pre-existing `_service_line()` access. That path
was not changed by this work; the failure is retained, not silently fixed or
reported as a suite pass.

## Next boundary

Capture CPU frame-ISR entry/EOI and bank acknowledgments against DSP status
reads at the first exhausted bank. Determine whether the supervisor loses its
service opportunity, its instruction-count clock overstates interrupt-disabled
work, or the bank/status model differs from hardware. Do not hide the loss by
adding an unlimited queue, inventing missing octets, modifying firmware, or
relaxing record/gap criteria. Then require repeated 20-/60-second duplex passes
and the 53333 target before claiming sustained x2 reliability.
