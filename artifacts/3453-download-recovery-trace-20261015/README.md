# 3453 B/C on-hook recovery download corruption

Offline unchanged-firmware peers; no hardware access, firmware/RAM patches,
forced acknowledgments, or disabled transfer verification. Settings/full flash
remain private. These files contain selected DSP transport/control diagnostics,
not standard PC traces or settings dumps.

## Demonstrated failure

The previous call-only timing correction stopped preserving semantic waits when
DAA off-hook became false. During normal firmware recovery after a failed call,
that re-enabled the queue-deadline shortcut and flooded the outgoing ring.

Both peers read the original download table correctly and requested an
origin-zero library: the BX register at the download strobe is `0000`, and row 7
in the immutable table is `(0000,1FF4,0000)`.

Nevertheless, the guest's individual-word enqueue rejects the destination word:

| Peer | Guest instruction count | PC | AX (dropped word) | BX / CX |
| --- | ---: | --- | --- | --- |
| A | 35,269,760 | `67D5A` | `0000` | `02E8 / 02EA` |
| B | 34,779,072 | `67D5A` | `0000` | `02E8 / 02EA` |

The subsequent actual CPU port writes deliver header `0002`, data `1200`.
Specifically, the CPU writes low byte `00` to `5C` and high byte `12` to `5E`;
this is not a host latch inventing a destination. The DSP therefore attempts to
install the origin-zero payload at `1200`, overwriting resident code. The later
payload mismatch / missing acknowledgment is a consequence, not evidence that
verification or the physical memory mask should be relaxed.

The 48-byte ring and both original enqueue guards remain unchanged. In
particular, a six-byte request can pass the packet guard with 42 bytes used,
then lose its final word when the individual-word guard encounters the read
pointer. Preserve the original queue-drain wait rather than modifying the ring
or retrying a rejected request.

## Correction and controls

`CourierMachine._clocked_3453_runtime()` preserves the three existing waits
(timer, calibrated busy loop, queue drain with deadline) during off-hook calls
**and after the firmware frontend has started**, including on-hook recovery.
Cold startup before frontend service retains its previous handling. The guard
still requires a verified 3453 profile, DSP-paced ticks, and a finished resident
bootstrap.

`after-*-transport.json` and `after-*-summary.json` cover 50 million instructions
and 130 requested common frames using the same dedicated-line commands. Both
workers finish without download errors; no packet/word drops or destination
`0002:1200` appear. Original `0002:0000` loads and the B `0002:7658` loads remain.

A separate reproducible regression uses only public boot/normal captures and
erased settings: blind dial with `S7=1`, an exchange configured not to answer,
then genuine firmware `NO CARRIER` and on-hook recovery. The corrected run has
zero queue drops and at least two original origin-zero loads. Restoring only the
old off-hook-only emulator guard reproduces a word drop and:

```
3453C overlay did not acknowledge at 12C8, PC=1133
```

This correction does **not** establish a negotiated connection. In this control,
A line TX peak is 10299 and RX peak is 0; B line RX peak is 1962 and TX peak is 0.
Later native processing traces show a short Bell-103 transmit burst before
reset, which is not the same as delivered reverse wire audio. The subsequent
post-carrier mailbox ISR transition is being investigated separately.

## Reproduction

```
.venv/bin/python tools/probe_3453_download.py "$PRIVATE_BC_FLASH" \
  --instructions 50000000 --frames 130 --output /tmp/bc-download-control
```

Add `--processing-trace` for bounded originate-state captures and unique DSP
status reports. The tool supports hash-guarded B/C normal 2.2.09 only. CPU table
bytes, transfer-control flags and selected registers are explicitly scoped;
worker stdout and standard PC traces are not published.
