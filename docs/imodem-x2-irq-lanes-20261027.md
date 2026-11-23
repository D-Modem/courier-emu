# x2 CPU/DSP lane timing and the 48000 control, 2026-10-27

## Rates: 53333 is not a hard-coded limit

The firmware negotiates multiple x2 rates. The fresh lower-ceiling control
prints **CONNECT 48000/ARQ/x2/LAPM/V42BIS**. Earlier calls have reported 52000,
53333, 54666, and 56000. These reports are not sustained-throughput
qualifications. The isolated passing 20-second x2 gate remains at 52000;
repeatable sustained x2 is still unqualified.

The original manual's &N table maps **26=40000, 32=48000, 36=53333,
39=57333**. A fixed40000 pilot did not reach analog CONNECT and is excluded
from traffic evidence. It is not proof of either reliable 40000 support or
a fundamental minimum rate. The earlier &N39 setting was not a 53333 cap.

## New passive timeline

The [valid-input/shortened-output boundary](imodem-x2-downstream-output-boundary-20261027.md)
is now accompanied by a separate **2048-row native CPU/DSP timeline**, enabled
only by `--analog-trace-link-errors`. Each row has CPU instructions, DSP
instructions/cycles, event kind, port/vector, value, and optional PC/FLAGS.
It records actual CPU lane accesses and acknowledgments without advancing the
DSP. Reading the ring does not drain it or the older full lane-capture stream.

Event kinds:

| Kind | Meaning |
| ---: | --- |
| 1 | CPU commits a transmit bank |
| 2 | CPU receive-bank acknowledgment at port 1A |
| 3 | CPU reads a lane byte |
| 4 | Native worker frame-IRQ entry |
| 5 | Native worker observes deferred EOI |
| 6 | Python dispatcher IRQ entry |
| 7 | Python controller EOI observation |

The I/O events have native per-access instruction stamps. **EOI observations
are not necessarily exact write times**: batched MMIO can replay later, and
its PC/FLAGS can describe that observation boundary. The observer reports both
Python frame state and native worker state; an inactive native worker's zero
counters must not be interpreted as absent CPU IRQs. In the captured console
calls, frame IRQs use the Python dispatcher, not native worker injection.

The native/Python worker structure gains only an optional diagnostic pointer;
its layout is checked at construction. Tests exercise boundedness, disabled
behavior, non-draining reads, unchanged legacy capture, no diagnostic DSP
advance, and unchanged native EOI/controller effects.

## What the default-timing capture establishes

`artifacts/imodem-x2-downstream-irq-boundary-20261027-100335/` reproduces four
missing octets between an FCS-valid input frame and matching DSP-output/CPU-ring
bytes. Four status reads have all six receive free bits clear. The last bank
acknowledgment before the burst of full-bank reads is at CPU instruction
**178458900**; the next is at **178462796**, a gap of **3896 instructions**, or
about **1.15 ms** at the identified CPU timebase. The timeline also retains
intervening frame, serial and tick IRQ activity.

This establishes real modeled service latency around output-lane exhaustion.
It does not yet establish which scheduling or hardware-model rule is wrong.
The original CPU's receive continuation can resume partway through the six
banks and stop at the end of that bank pass; pending low-numbered banks and
burst-style DSP publication therefore need explicit attention, not just an
average interrupt-rate calculation.

## Interrupt polling is distinct from DSP service cadence

The earlier service-only 256-/64-instruction controls left interrupt polling
at **1024 instructions**. New controls temporarily lowered **both** intervals.
CPU/DSP clock ratios, firmware, configuration correction S39=8, payloads and
traffic gates were unchanged.

| Control | U / D complete records in 20 seconds | Downstream max gap including trailing silence | Final U / D BLER | Gate |
| --- | ---: | ---: | ---: | --- |
| Default1024, IRQ trace | 14 / 7 | 8.8 s | 0 / 67 | FAIL |
| Interrupt/service256 | 25 / 68 | 8.1 s | 0 / 33 | FAIL |
| Interrupt/service64 | 24 / 66 | 9.8 s | 0 / 34 | FAIL |
| Default1024, ceiling48000 | 12 / 8 | 8.0 s | 0 / 46 | FAIL |

Artifacts respectively:

- `imodem-x2-downstream-irq-boundary-20261027-100335`
- `imodem-x2-interrupt-poll256-20261027-100938`
- `imodem-x2-interrupt-poll64-20261027-101214`
- `imodem-x2-ceiling48000-20261027-101919`

The finer polling controls deliver substantially more data, but each still
loses an octet from an independently FCS-valid five-octet control frame. The
64-instruction call's maximum gap *between completed downstream records* is
only 0.2 s; its **9.8 s trailing silence** still fails the original gate.
Neither control is a fix. Both source edits are reverted and documented in
their artifact directories' `source-control-notes.json`; `command.json` alone
does not encode these temporary edits. Retained service and interrupt polling
are both still 1024.

## 48000: a lost boundary, not only a shortened information frame

The 48000 call's coherent trace contains two separately FCS-valid frames:

```
01 a0 34 81 08 00 8e bf
01 a2 34 c6 28 4f e2 76 c1 b8 4b b3 6b 72 65 b4
```

The **23** consecutive DSP output octets and matching CPU ring are:

```
01 a0 34 81 08 00 8e bf a2 34 c6 28 4f e2 76 c1 b8 4b b3 6b 72 65 b4
```

The intermediate FF00 frame-boundary token and second frame's first **01**
are absent from the DSP output. The next FF00 appears only after the combined
23-octet sequence. Thus the output loss can **merge valid input frames**, as
well as shorten a single frame. The offline decoder retains the two valid
frames separately; it never invents a repaired guest frame.

## Regression, replay and remaining boundary

Fresh default-timing V.34 control with the enhanced observer:
`artifacts/imodem-v34-irq-trace-regression-20261027-102249/`.
The unchanged fixed14400, 512-byte, 20-second duplex gate passes with **13/13**
records in-window, maximum upstream/downstream gaps **1.6/1.7 seconds**, final
drain **14/14**, and zero BLERs at both receivers.

**126 focused tests pass.** No full-suite pass is claimed. The independent
verifier replays raw complete records and partial prefixes, hashes, unchanged
record and trailing-gap gates, UART/PCM health, and coherent boundaries:

```
PYTHONPATH=. .venv/bin/python .artifact-archives/imodem-irq-lanes-20261027/verify.py
```

It preserves all four x2 traffic failures, the V.34 pass, and the excluded
non-CONNECT fixed40000 pilot. No UART overruns, terminal drops, PCM underruns,
or connected receive underruns were observed in the five connected calls.

The [first-full-bank follow-up](imodem-x2-first-full-bank-20261027.md) now
freezes native DSP/CPU execution order at the first signature-checked non-idle
output attempt with all six banks full. Repeat20 and 60-second calls reproduce
it with internally consistent sampled status/word/ACK transitions; sustained
x2 still fails. An unfiltered idle trigger and post-window V.34 diagnostics
are explicitly distinguished from measured lost-data evidence.

Next distinguish bank-pass/wrap timing, IRQ latching/priority and the source
of the ASIC's frame/data-ready interrupt. Finer polling alone is insufficient;
do not compensate with a larger invented FIFO, arbitrary interrupt frequency,
modified firmware, or weaker traffic gates.
