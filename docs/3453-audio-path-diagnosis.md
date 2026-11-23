# 3453 audio path: standalone validation and missing tone-library code

All work here is offline. No attached modem was accessed. These are separate
DSP tests, not patches to the supervisor-driven call or its results.

## Independent PCM path

`tests/test_3453c_pcm_path.py` executes a tiny DSP program that repeatedly
writes `2468` to the primary serial DXR. The native Si3034 DAC emits that
exact sample, and the real bridge's codec-to-line resampler produces nonzero
telephone-line audio. Independently queued receive PCM reaches DRR. The TDM
transmitter is unused.

This validates the modeled primary-serial path:

* line -> ADC -> Si3034 DOUT -> DSP DRR;
* DSP DXR -> Si3034 DIN -> DAC -> line-rate resampler.

It does not measure PCB wiring or prove electrical/timing fidelity.

## Historical guest output-processing trace (before hook fix)

Reproduction:

```
.venv/bin/python tools/probe_3453_calibration.py "$PRIVATE_BC_FLASH" \
    --dial-command ATX0D5551212 --processing-trace --instructions 11000000
```

Evidence: `artifacts/3453-audio-calibration-trace-20261014/bc-output-processing.json`.
Only DSP state and whitelisted call diagnostics are published; no supervisor
settings/RAM or credentials are dumped.

The supervisor issues genuine tone-start requests `0013:0005`, followed by
requests for the remaining digits. During the first digit:

* PMST reads `18B8`, with MP/MC set: low program addresses are not mask ROM.
* The resident dispatch table at program `1317` points tag 13 to `0413`.
* Live program `0413` is **0000**, not the captured library's `BC07`.
* The low library is incomplete, not entirely absent: `0015` and `0018`
  already contain their captured `097A` instructions.
* Output callback data `039A` stays `1173` (idle return), instead of selecting
  the library's tone-generation callback `044A`.
* The gain at data `0392` changes from `32D6` to `3000`, but the output sample
  at `03C7` remains zero. This is not simply a zero output-gain setting.

`--processing-trace` captures state at supervisor tone-control requests and
before DSP resets. Captures are bounded to the latest 64 samples; PC summaries
cover a bounded recent window, not total execution. Capture rows contain
instruction count, cycles, ACC, DP, ARP, then the listed data addresses.

## Genuine library control

`tests/test_3453c_tone_library.py` loads the unchanged B/C resident and captured
low-program library into a separate DSP instance. It does not modify a running
call. Original mailbox commands `1A:3000`, `1B:0C08`, `13:0005` then:

1. execute the real handler at `0413`;
2. set the original output callback to `044A`;
3. generate nonzero primary-serial PCM;
4. pass that PCM through the actual line resampler;
5. produce digit **5**, decoded by the exchange's DTMF decoder.

This demonstrates that the modeled transmit path and the original tone
algorithm can work together. It does **not** prove a guest-requested library
download, dialed number, carrier, overlay negotiation or data connection.

## Root cause and corrected guest execution

The B/C supervisor's table row 7 requests `0000..1FF4` bytes at DSP program
origin zero. Its loader rounds 4090 words up to **1023 four-word transfers**.
This is real firmware code, not a request to synthesize tones.

The pre-fix transport trace
`artifacts/3453-audio-calibration-trace-20261014/bc-library-transfer-before-fix.json`
shows the CPU starting with CX=1023, then completing after only 101 groups,
leaving DSP program `0194..0FFB` uninstalled. It ends normally with CX=0;
the timeout byte is still FD, so it is not a legitimate transfer timeout.

`courier_emu/machine.py:on_hot_code()` translated a physical PC to a canonical
PC, then tested the canonical hot-address set. Hook ranges include gaps and,
for complete flash, all supported profiles. At physical B/C `5868C`, the
fallback canonical address was C's delay-loop address. The delay accelerator
therefore wrote **CX=1** at B/C's timer-ISR `CLD`, immediately before its
`PUSHA`. The ISR saved and restored the already-corrupted transfer counter.

The fix checks the **current profile's physical hot-address set first**, then
translates. B/C `58684` remains the genuine delay loop; B/C `5868C` is not
eligible. Mode switches rebuild this physical set. No guest RAM, output
callback, DSP program or reply is forced.

`bc-hot-hook-fixed-dial.json` repeats the supervisor-driven blind call:

* The guest completes all **1023 groups / 4092 padded words**, ending at 0FFC.
* Program `0413` now contains the captured `BC07` instruction.
* Real transmit audio reaches the line, peak 32331.
* The exchange's DTMF decoder records **5551212** from that audio.
* A later guest-requested row-9 RAM-source transfer installs 176 words at
  `7658..7707`. The legacy `overlay_downloads` counter remains zero and does
  not count these Board3453 transfers; use the transport trace/verified words.

The call still ends in `NO CARRIER`. No carrier, negotiated data mode or
end-to-end bytes are demonstrated. Carrier/answer processing and later
negotiation downloads remain the next target; absence of transmit audio is
no longer the blocker in this blind-call probe.

Regression: `tests/test_3453c_hot_hook_profiles.py` executes the real guest
loader using public firmware and erased synthetic settings, and verifies the
low tone library is installed. The broader 3453C/product/native-machine subset
passed **62 tests**. The full 3453/map/CLI/native aggregate passed **108 tests**
in 403.74 s. Compilation, evidence assertions and diff checks passed. No
carrier/data connection is claimed.

## Line-control decompilation and two-peer receive tracing

See [the line-control audit](../artifacts/3453-line-control-decomp-20261014/README.md)
for reproducible stage-specific DSP/supervisor disassembly and four additional
unchanged-firmware peer controls. The answering waveform is 2100 Hz followed by
2250 Hz; it reaches the other peer. The silent leased-line originator remains in
the original monitor/classifier (RX 2127, TX idle 1173, state callback 006D=0).
Bounded supervisor writes prove that DSP status 0809 reaches 1D6C/1D6D; the
receive mailbox is not wholly broken. The guest's qualification is more specific
than nonzero PCM or the status energy bit. A manual dial/answer control also
ends in `NO CARRIER` on both sides. The transition into originate handshake
setup is still unresolved; no new emulator fix or successful negotiation is
claimed by this audit.

## Originate transition resolved: firmware queue rejection

The [follow-up trace](../artifacts/3453-originate-queue-trace-20261015/README.md)
supersedes that transition hypothesis. The originating guest **does** request
command `0017:5040` (DSP entry `1DE4`), but its original enqueue routine rejects
it at `67D89`: the 48-byte outbound ring already holds 46 bytes. Accelerated
call-time waits compressed the setup burst without equivalent DSP queue service.

The first correction preserved timer waits, calibrated busy loops, and
queue-drain waits with timer deadlines during off-hook, DSP-clocked 3453 calls. The latter
were also misclassified as plain delays: forcing RAM 014E to the deadline took
the timeout exit before the queue drained. It does not patch the guest ring,
insert or retry commands, or force carrier. A timer-wait-only control delivers
command 0017 and generates nonzero native transmit PCM, but **does not**
demonstrate bidirectional wire audio or carrier. That intermediate control
still drops other setup commands. The complete correction's quiet-line
regression verifies genuine 0017 delivery, all six 0050 setup words, and **zero
queue rejections**, using public captures and erased synthetic settings.

The final live peer control instead exposes later DSP download failures:
A reports an overlay mismatch at FFFE; B reports no acknowledgment at resident
PC `1133`. The run aborts; transfer verification is not bypassed. Those later
request/readiness/INT1/reset sequences remain unresolved. No successful
negotiated connection is claimed. The full 3453/map/CLI/native-machine regression
aggregate passes **116 tests in 389.09 seconds** (focused subset: 22 passed).

## On-hook recovery download corruption resolved

The [recovery transport trace](../artifacts/3453-download-recovery-trace-20261015/README.md)
supersedes the unresolved-download finding above. At normal on-hook recovery,
the old timing guard re-enabled queue-deadline acceleration. The guest requested
an origin-zero library correctly, but its individual-word enqueue rejected the
`0000` destination at `67D5A`. Actual later CPU port writes supplied `1200` as
the destination of command `0002`, causing the library to overwrite resident
code. This was not evidence for weakening payload verification or changing the
physical memory mask.

`_clocked_3453_runtime()` now retains the waits after the firmware frontend has
started, even on hook; cold-start handling is retained. Both original firmware
peers run 50 million instructions / 130 requested frames without transfer
errors or queue drops. Public-image/erased-settings regression exercises genuine
`NO CARRIER` followed by recovery and repeated origin-zero loads. Restoring the
old emulator guard reproduces a word drop and missing download acknowledgment.
The aggregate at this stage passes **118 tests in 432.22 seconds**.

This is not yet a successful connection. Native processing traces now show
originate entry `1DE4`, genuine 2100/2250-Hz qualification in `1E45`, transition
through `4486` to Bell-103 TX/RX callbacks `45F2/4538`, and DSP reports `003D`,
`0004`, `0028`. These are not all failure reports. A short native transmit burst
before reset does not establish reverse wire audio. The supervisor's tag-28
handler also switches the mailbox interrupt vector to a different original
ISR; its return/latch handling was the next identified emulator fault.

## Both firmware peers now report CONNECT

The [native Bell-103 peer control](../artifacts/3453-native-bell103-link-20261015/README.md)
registers that original post-carrier mailbox return (BC `6ED9A`, C `6EEFA`).
Previously the emulator's in-service latch stayed busy after the new ISR;
mailbox service then stopped progressing normally. The guest's own tag-28
handler selects the new vector; no vector/callback injection is involved.

Both unchanged B/C firmware peers now print their own `CONNECT` with
`AT&N1&U1`, `AT&L1`, opposite dedicated-line DIP presets, and a PCM-only link.
A/B native codec RX peaks are 3014/3068 and both line TX paths are nonzero;
recorded WAVs establish bidirectional wire audio. The run reaches 50 million
instructions and 130 requested common frames without errors. The aggregate
at this stage passes **120 tests in 493.60 seconds**.

## Exact bidirectional terminal payload after settling

The [selected data-path evidence](../artifacts/3453-bell103-data-path-20261015/README.md)
now demonstrates distinct, exact **32-byte ASCII payloads in both directions**
between unchanged B/C firmware peers, using `AT&M0&N1&U1`, `AT&L1`, and only
PCM across the line. Payload is typed after both peers settle; immediate
local-CONNECT typing can still lose initial characters. Independent external
terminal delays are available as `--a-send-delay-ms` / `--b-send-delay-ms`;
these do not change firmware readiness or modem decisions.

The leased-line command legitimately remains pending until hangup, so it must
not block the selected online UART callback. Delivery also waits until the
original abort-on-key receiver has changed; the emulator does not replace it.
UART bus reversal follows both original ISR loops, and an actual `OUT 0A` is
TX regardless of the harness's requested interrupt reason.

The remaining corruption was not a DSP demodulation failure: complete payloads
were recoverable from receiver PCM and the actual CPU input words. Original
CPU-framer replay recovered them correctly in both engines. Live interrupt
ownership was wrong: an untracked UART INT2 EOI released an interrupted INT0,
and the periodic mailbox source bypassed the same INT0 in-service state.
Reentrant data ISRs corrupted the original shared framer state. All delivery
paths now share controller EOI ownership; captured live call-state continuity
is restored without replacing the guest receiver or its ring.

Finally, the first received byte uses the original foreground **S0TBUF FF6A**
write rather than the later `OUT 0A` path. Register-based capture now replaces
the 2.x printf-PC capture and observes this byte without duplicating replies.
Seven-bit/parity framing is preserved. No decoded payload is injected into the
line or the DSP. Binary/long-run transfer and full electrical UART fidelity
remain separate work.

## Original firmware hangup from external DTR

A separate `AT&D2&M0&N1&U1` / `AT&L1` control leaves the DTR-override DIP open,
transfers both exact payloads, and deasserts **only A's DTR** 5000 ms after
CONNECT. Both original supervisors print `NO CARRIER` and release their hooks,
with no errors or original outbound-ring drops. B's DTR never changes, so its
disconnect is caused by far-end loss through the PCM path. Both finish on hook
in the 55-million-instruction control (`dtr-disconnect.json`); a longer public
control observes B's legitimate dedicated-line retry after hook release.

The public erased-settings control also emits one original-framer NUL at B
during loss, **after** both 32-byte payloads are complete and A's DTR drops.
Captured input words reproduce that NUL in both CPU engines. It is retained,
not suppressed in UART capture. Exact stable-link data, loss-period bytes,
`NO CARRIER`, and hook/retry transitions are checked separately; a byte-clean
carrier-loss interval is not established. See `carrier-loss-control.json`.

The original kind<6 monitor checks EB **P1.6 at FF5A** and ASIC input selector
`0104` (port 14, bit 0). Both read set for DTR lost. Earlier controls drove
only the GPIO path and retained the older front end's opposite port-14
polarity, so the original predicate never passed. The 2.x input model now
presents both actual DTR inputs, without detaching the terminal UART. The
original `&D2` option is at B/C `0979`; no guest setting or callback is patched.
Isolated original-code predicate controls cover both CPU engines, and the
paired regression checks exact pre-drop payload and genuine `NO CARRIER`,
while preserving original carrier-loss output and leased-line retry.
