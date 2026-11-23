# Apple USB modem: full audio-path audit

**Latest follow-up:** [the original-driver firmware hook operation](apple-firmware-hook-fix.md)
fixes the reproduced seizure blocker. Two captured V.32/9600 LAPM calls now pass
complete 180-byte duplex payloads with the new timestamp playout (200-ms delay),
zero active USB losses and zero playout missing/late samples. Local and PBX RTP
identities/payloads match completely in both runs. This does not establish that
the older intermittent delivery loss is permanently fixed; the historical audit
and its failure evidence remain below.

## Result

The evidence separates **emulator timing faults, a real USB-host underrun,
and RTP delivery faults**. They are not one gain/calibration problem.

- Replayed **nine captures** from codec samples through the actual TX converter,
  gain, mute and reset boundaries: **every helper-bound sample matches**.
- The newest real call delivers **180 bytes exactly each way**; independent
  Bell 103 decoding agrees at all five saved audio boundaries.
- Nevertheless, that call has **four RTP packets missing between the local
  sender and the PBX capture**, outside its payload interval. The path is not
  established as reliable or suitable for high-speed training.
- Fixed additional framing, queueing and reset-publication defects; remaining
  architectural gaps are listed explicitly below.

Evidence is under [`artifacts/apple-audio-path-audit/`](../artifacts/apple-audio-path-audit/).
Earlier failed calls are retained in `artifacts/apple-courier-sip/`.

## Boundaries examined

```text
403 firmware DAC words / codec-clock events
    -> codec-to-hardware resampler + firmware/host gain
    -> Python/helper socket, hardware-grid TX recording
    -> native TX FIFO -> CoreAudio output callback -> Apple DAC
    -> analog line / FXS gateway -> G.711 RTP
    -> PBX -> SIP receive queue -> bearer playout FIFO
    -> I-modem DSC / DSP-facing G.711 -> firmware / UART

Return: I-modem DSP -> RTP sender -> PBX -> FXS/analog -> Apple ADC
    -> CoreAudio input callback -> native RX FIFO -> helper RX recording
    -> 8-Hz DC blocker -> native hardware-grid input FIFO
    -> reconstruction at actual 403 ADC edges -> firmware / UART
```

**Recording limitation:** helper-bound TX is a submitted waveform, not an
independent measurement of DAC output voltage. Raw hardware RX is the HAL input
recording, not an oscilloscope measurement before the Apple ADC. The latest HAL
counters establish callback continuity, not perfect electrical fidelity.

## Findings by stage

| Stage | Evidence and conclusion |
| --- | --- |
| Firmware TX / clock labels | Exact replay across all nine captures, including resets, rate changes, gain and on-hook mute. No observed codec-to-helper TX corruption. |
| TX resampling | Byte-for-byte/sample-for-sample agreement with submitted hardware TX, even in the failed calls. Tests cover known/transient clocks and independent waveform reconstruction. No reason to add another 8-kHz conversion. |
| Hardware callbacks / queues | One archived call genuinely failed on **80 missing output samples** (7.78 ms at 10286 Hz). Latest call: zero active gaps/overflows, equal input/output frame totals, zero reported sample-time discontinuities. Sporadic host stalls are not ruled out. |
| USB status control | Synchronous reads ran **before** publishing the received PCM block, unnecessarily consuming its output deadline. Moved ordinary status polling after TX publication; control/seizure checks remain ahead of activation. Worst-case blocking is still an open risk. |
| Reset publication | Output could read old `tw`, then a newly cleared reset flag, and falsely classify an empty old queue as a live underrun. Read/check reset before loading published output indices, including an entry-into-reset recheck. Strict underrun detection remains enabled. |
| Helper failure reporting | A callback failure aborted normal replies before Python learned the counters. An old Python report says zero gaps while helper stderr says **80**. Added a best-effort zero-count terminal error header, only when no normal reply has started; Python records counters before demanding PCM. EOF/stderr remain fallback evidence. |
| Analog levels / headroom | Bell 103 TX payload AC RMS is about **11770**, peaks **~20000**; RX RMS **~3300**, peaks **~6000**, in signed-16-bit units. Payload windows have **zero near-rail samples**, including the corrupt return-path repeat. Dial tone/ringback do clip. No AGC or speculative gain change was applied. Absolute physical dBm calibration remains open. |
| DC removal | Raw RX has a small DC offset (~−127 units in the long Bell 103 calls). An 8-Hz blocker is not an AGC or a clipping repair. Whole-call peak/clip counters must not be interpreted as payload clipping. |
| 403 ADC timing | All active snapshots in the audited calls retain `rx_empty_frames = 143`, including the bad return-path repeat and the failed USB call. Those 143 initial frames are startup, not additional losses during data. Hardware-grid reconstruction avoids the former ADC-retune relabeling fault. No new native ADC starvation is observed. |
| DSP / supervisor scheduling | Previous fixes remove the live console's redundant instruction-count sleep and bound native DSP catch-up by actual CPU progress. Earlier captures establish that wrong symbol timing existed even when the CPU supplied the right bit pattern. Kept regression coverage. |
| RTP sender | New telemetry distinguishes producer rebuffering, deadline lateness, packet spacing, bursts and queue size. Latest call has **zero rebuffer events**, **24.94-ms max send interval**, **5.16-ms max deadline lateness**, at most one packet per flush. This is API send timing, not a NIC timestamp. |
| RTP framing | Receiver previously played everything after byte 12, including CSRC/extension/padding bytes, accepted malformed versions, replayed duplicates, and could truncate datagrams at 2048 bytes. Fixed parsing, duplicate suppression and receive size. These are real software defects, but no evidence says extended headers caused the historical failures. |
| RTP sequencing / ownership | **Still incomplete:** unique packets are appended in arrival order, with no timestamp-aware reorder/loss playout or per-dialog source/SSRC gate. New counters expose order, timestamp and SSRC changes. A receive byte FIFO is not a complete RTP jitter buffer. |
| Silent queue loss | The analog SIP TX deque had a fixed length and could silently throw away old samples on overflow. It now rejects an overflowing append before modifying the queue. Digital TX backlog remains observable through max queue telemetry; a universal backlog policy is not introduced here. |
| Receive silence accounting | Split reserve/startup fill from fill after the receive stream has started. Old cumulative `silence_filled` included preanswer and reserve startup and was not a packet-loss percentage. New fields are `startup_silence_filled` and `active_silence_filled`. |

## Packet delivery: a separately measured fault

The latest call used a passive PBX Ethernet capture with **zero packets dropped
by the capture kernel**. Inspect `live-180/rtp-byte-audit.json`,
`live-180/rtp/summary.json`, and `live-180/receiver/report.log`.

### I-modem to PBX / ATA

- Local sender: **597** RTP packets sent successfully through `sendto`.
- PBX capture: **593** from that sender.
- Sequences **23124–23127** are absent; timestamp span is **95520 samples**,
  captured payload is **94880**, a **640-sample / 80-ms hole**.
- Every captured packet's payload is **exactly** the corresponding samples
  in the DSP TX recording when aligned by RTP timestamp. Concatenating across
  the missing packets is deliberately **not** treated as a contiguous waveform.
- The PBX forwards **588 shared packets** to the ATA with **zero altered
  payloads**. Five earlier packets are outside the forwarded answer boundary;
  this initial boundary difference is not labeled random packet loss.
- Max sender interval: **24.94 ms**; max PBX arrival interval: **101.16 ms**.
  Shared-packet PBX forwarding delay is at most **0.214 ms**.

Thus the measured hole lies between the sender API and PBX ingress, not in the
DSP waveform or in sample mutation by the PBX. Host UDP queues, the tunnel and
its underlay are not separated by this capture. The route to the PBX uses
**`utun8`, MTU 1420**. This is not proof of which component dropped the packets.

The hole occurred **after the six-second test payload**, so both payload checks
still pass. It must not be omitted when judging overall audio-path quality.
The earlier successful packet capture also shows an out-of-order arrival
(18025 preceding 18023/18024) and a 101.84-ms interval. Delayed/reordered packets
are not automatically proven losses.

### ATA to PBX / I-modem

The PBX forwards **593 shared packets / 94880 samples**, with zero changed
payloads and max forwarding delay **0.776 ms**. The local receiver reports
zero duplicate/order/timestamp/SSRC changes in this call, but its **polled**
arrival interval reaches **95 ms**. Poll timing includes receiver scheduling;
it is not a kernel packet-arrival timestamp. The 200-ms reserve absorbs that
variation for this payload. A previous 100-ms trial inserted 80 silence samples
inside data and corrupted two characters.

## Current USB measurements

Latest live call, fixed hardware grid **10286 Hz** / HAL block **512 frames**:

- **374784 input and 374784 output frames** in the callback accounting.
- Maximum active callback intervals: **49.937 / 49.938 ms**, input/output.
- **Zero sample-time discontinuities**, zero active TX gaps, zero RX overflows.
- TX low-water at output callback entry: **1025 samples**; RX high-water: **718**.
  These are sampled queue observations, not continuously measured latency.
- Maximum single active USB register read: **6.933 ms**; complete three-register
  status poll: **12.530 ms**.
- Independent hook readback verifies release at the end.

A no-dial, silence-only hardware smoke probe at **7200 -> 9600 Hz** also passes
with balanced callback totals, zero active sample loss and verified release.
It exercises transport/host retuning, not native modem training. Its diagnostic
RX path is the probe's Python converter, not the native ADC path used by calls.

Device properties report 17 input latency frames / 17 input safety frames,
12 output latency frames / 12 output safety frames. These values are retained
separately; this audit does not invent an end-to-end delay by blindly summing
properties and sample-clock offsets.

## Timestamp playout follow-up (offline implementation)

`courier_emu/rtp.py` now provides bounded, timestamp-based 8-kHz receive
playout, integrated into both the codeword and decoded-audio SIP paths.
This supersedes the arrival-order FIFO limitation in the historical audit
above; it is **not yet live-hardware validated**.

- A configurable priming interval (default **480 samples / 60 ms**) permits reordering, including
  an earlier initial packet. Packet samples retain their timestamp positions;
  sequence and timestamp wrap do not compress or extend the timeline.
- Missing deadlines produce counted codec-idle octets (`ff` for PCMU, `d5`
  for PCMA), not reconstructed modem audio. Late packets cannot repair audio
  already due. Duplicate/overlapping payloads cannot overwrite queued samples.
- The SDP endpoint must match exactly; the first nonempty accepted packet
  pins its SSRC for that dialog. There is no automatic symmetric-RTP learning
  or SSRC migration. This is ownership gating, not cryptographic authentication.
- The timestamp window is bounded to **16000 samples / two seconds**. Far-future
  packets are rejected without reanchoring. A consumer stalled beyond that
  bound raises an explicit error rather than silently deleting elapsed media.
- `rtp_receive.playout` reports missing/played samples, current occupancy,
  rejected sources/SSRCs, late packets, overlaps and out-of-window packets.
  Dialog reset clears queued media and ownership, retaining diagnostic totals.

The existing bearer receive reserve is **additional** to the RTP priming
interval; this change does not silently retune it. Hardware tests must check
negotiation latency, drift and missing-sample telemetry. Packet loss between
the sender and PBX and blocking USB status work remain unresolved.

Offline focused regression selection: **108 tests passed**, covering framing,
playout, both SIP receive modes, media-clock/start/registration behavior, bearer
reserve behavior, Apple RTP auditing and adjacent Apple/native paths. An attempt
at the full suite exceeded a 120-second limit; it is not claimed to pass.

Follow-up capture-timing replays found that **60 ms is insufficient for an
actual archived reordered stream**; 200 ms preserves that stream. The ISDN CLI
now exposes `--bri-sip-rtp-delay-ms` separately from the bearer reserve. A dual-
capture runner and detailed evidence are in
[playout validation](apple-rtp-playout-validation.md). The attempted hardware
preflight found no Apple `05ac:1401` device, so no new call was made.

## Remaining work, in order

1. **Find and remove the API-to-PBX delivery loss.** Compare sender-side packet
   capture and PBX ingress concurrently, including tunnel/underlay counters.
   A larger jitter reserve cannot reconstruct absent audio samples.
2. **Validate the new timestamp-based RTP playout live**, including bounded
   reordering, missing/late deadlines and source/SSRC ownership (see follow-up
   above). Check its additional priming delay against training and the existing
   bearer reserve. Preserve/report real discontinuities; do not add invented
   modem carrier/data or conceal loss with normalization.
3. **Move/bound USB status work outside the PCM deadline.** Publishing TX first
   removes needless head-of-line blocking, but existing USB control timeouts
   can still exceed the roughly 100-ms priming reserve. A robust asynchronous
   control plane needs bounded cancellation, serialized hook/control access and
   the current fail-closed/overload protections, not merely another sleep.
4. Validate longer payloads, arbitrary binary data and clock drift, then retry
   high-speed negotiation. None of the short Bell 103 results certify V.34,
   x2/V.90, analog calibration or long-duration BER.

## Follow-up: advanced modulation / error correction

The [advanced controls](../artifacts/apple-advanced-sip/README.md) now establish
**9600-bps V.32/LAPM**, with required error correction and exact 180-byte payloads
both ways. Raw V.22bis/2400 and V.32/9600 train and deliver the complete return
message, but their forward payloads corrupt. The automatic 19200 result is
explicitly labeled V32 by the firmware and is **not confirmed V.34**. These
results improve the usable data-link demonstration without repairing the
underlying RTP timeline or certifying sustained reliability. One raw 9600 call
corrupts forward data without a recorded incoming RTP discontinuity, so packet
loss is not a sufficient explanation of every remaining error.

## Reproduce offline

```sh
OPENBLAS_NUM_THREADS=1 ../v90modem/.venv/bin/python tools/audit_apple_audio_path.py \
  artifacts/apple-courier-sip/bell103-fair-clock-180-repeat \
  artifacts/apple-audio-path-audit/live-180 \
  --output artifacts/NEW-AUDIT.json

.venv/bin/python tools/audit_apple_rtp.py \
  artifacts/apple-audio-path-audit/live-180/rtp --host 10.69.220.8 \
  --dsp-tx artifacts/apple-audio-path-audit/live-180/receiver/imodem-to-apple.g711 \
  --output artifacts/NEW-RTP-AUDIT.json
```

The helper must be rebuilt after the native transport changes. Regressions
cover malformed/extended/padded RTP, duplicates and oversized datagrams,
sequence/timestamp wraps, sparse packet-vs-DSP comparisons, exact converter
replay/reset/mute, terminal error-counter delivery, receive fill accounting,
and the existing Apple/native timing and fail-closed controls.
The final focused suite passes **171 tests**. The rebuilt helper's memory-only
self-test and the no-dial hardware smoke probe both pass; final independent USB
readback confirms on-hook. No PBX/gateway configuration or modem firmware was
changed during this audit.
