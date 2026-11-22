# What Courier is doing on 7910

**Current status:** the demonstrated receive-loss problem was repaired by
restoring VLAN-70 multicast control. One unchanged automatic 7910 call now
reaches **CONNECT 19200/ARQ/V34/LAPM/V42BIS**, with eight actual ATA receiver
reports showing zero loss. The switch change is saved to startup configuration.
This is not V.90 or sustained-throughput certification.

## Scope

The initial diagnosis retained one normal automatic call to 7900 and two
separately bounded failed calls to 7910. The second 7910 call added passive
diagnostics, not a modem setting change. A third, post-repair 7910 call connected
as described below. No automatic
redial, gateway/peer configuration change, gain adjustment, or carrier injection
was used. Existing sibling calls were not stopped; a busy 7910 check delayed the
instrumented attempt until it was free, and a second check gated the actual call.

7900/7910 route through Cisco SIP trunk 6501, not a Cisco modem DSP. The old
sibling inventory (`../v90modem/docs/eicon_live_20261008.md`) led us to assume
7910 terminated on the native Eicon modem. **That assumption was wrong for the
clean connected call.** Subsequent authorized read-only access as `scottcryan`
correlates its 19:02:55 connection and 19:03:07 hangup with
`multitech-ppp.service`, `mtppp0`, **`/dev/ttyM4`** on the Eicon host. Distinguish
the Linux host, the Eicon BRI hardware and the actual answering modem.

The native `bri-test-answerer` config still names controller 1/7910 and controller
2/7900, and its worker sets `AT+MS=V90,1`. However its 7910 workers log no
CONNECT after their 11:06 startup; its 7900 workers do log V.90 connections with
other callers. This does not establish the native Eicon as the receiver of our
7910 training. The separate MultiTech chat initialization currently sets
`ATE0V1S0=1S109=0`. No owned TTY was opened, profile changed, service restarted
or competing call stopped. Actual received CM and the precise physical route
remain to be captured. Evidence is private at
`apple-v90-peer-inspection-20261024/`; SSH access is no longer blocked.

## Confirmed downstream receive loss (follow-up)

The receive audio **is corrupted in short bursts**. This is now supported by
independent endpoint reports, not just an offline decoder's poor recovery.

`tools/analyze_rtcp.py` extracts the AudioCodes ATA's own RTCP receiver reports
from the existing captures, scoped to its RTCP port and the actual call's RTP
SSRC. In the instrumented repeat the ATA reports:

| remote RTP clock | cumulative packets reported lost | interval loss fraction |
|---:|---:|---:|
| 7.28 s | 19 | 6.25% |
| 13.84 s | 42 | 6.64% |
| 20.20 s | 63 | 6.25% |
| 27.60 s | 93 | 7.81% |
| 51.78 s | **177** | **8.20%** |

Those are actual on-wire RTCP values from reporter `10.69.70.221:6031`, reporting
source SSRC `0c8d583e`, **not BER**. The original 7910 call also has positive
interval loss reports and reaches **132 packets lost** in its last report
(`6001`, reported SSRC `0ce8583e`). The receiver's counters cannot by themselves
distinguish network drops from rejection/loss inside its receive processing.

At the PBX, the repeat's selected **2,696 remote→ATA packets** are all present,
with contiguous sequence numbers, contiguous 160-sample timestamps, no duplicates,
and unchanged forwarded payloads. During the JM interval its captured arrival
gaps peak around 21.24 ms. The PBX's reports of receiving the opposite ATA→PBX
stream show zero loss. That does **not** mean the ATA received the PBX's stream.

The hardware waveform independently shows six short mismatch bursts around RTP
packet starts **7.12, 7.46, 7.64, 7.96, 8.48, and 8.80 s**. Each spans about
21–26 ms including the offline filter's edge response; the audio returns to close
agreement between bursts. Fixed linear-channel predictions have approximately
0.7–1.1% relative mean-square error in adjacent clean packet interiors, versus
roughly 31–263% in these affected interiors. These are **model residuals, not
calibrated SNR/BER or independently measured per-packet loss counts**.
The unique answer-tone→JM transition anchors the waveform alignment, rather than
choosing an arbitrary offset among repeated menus. Scanning all offline detector
sample phases and decision thresholds did not recover the missing complete menus.

The primary demonstrated fault is therefore **PBX→ATA delivery/receive loss,
manifesting as packet-sized corruption before the emulator's DSP**. Packet loss
concealment/substitution is consistent with the waveform, but the exact ATA
concealment algorithm and exact dropping hop have not been established. A test
of simple previous-packet repetition did not consistently explain the bursts.
No live filter, gain, timing, carrier, or datapump change was applied.

The earlier description of clean transport must be read narrowly: USB counters,
local receiver playout counters and PBX forwarding were clean, **not end-to-end
RTP delivery**. This is a real fault to resolve before interpreting modem
training failures as emulator defects. It does not prove no other defect exists.

Reproduce the endpoint evidence with the standard-library-only tool:

```sh
.venv/bin/python tools/analyze_rtcp.py \
  .artifact-archives/apple-courier-7910-mailbox-20261024/pbx.pcap \
  --port 6031 --source 10.69.70.221 --ssrc 0c8d583e
```

The tool retains its JSON evidence and exits 1 for reported loss or missing
selected reports; extraction success is not silently presented as healthy media.

Evidence in the repeat's `training-analysis/`: `ata-rtcp-validated.json`,
`jm-phase.png`, `jm-phase-bursts.json`, `jm-timing-scan.json`,
`jm-unique-transition-alignment.npz`, and the retained analysis scripts.
`pbx-readonly-network-state.json` records a subsequent read-only check: route via
`192.168.88.1`, no configured egress netem/qdisc impairment in the PBX container.
Its cumulative interface counters are **not call-time deltas** and cannot locate
the drop. No network configuration was changed and no new call was needed.

## First 7910 call: V.90 request, then V.34 fallback

Evidence: `.artifact-archives/apple-courier-7910-20261024/`.
The selected streams are Cisco `16444` ↔ PBX `12526` and ATA `6000` ↔ PBX `19252`.
Unrelated traffic in the host-scoped capture is excluded from comparisons.

The following times use the first **remote RTP packet** as zero, with the
Courier stream's 41.63-ms origin offset added. They are approximate demodulator
sample decisions / signal search windows, not calibrated physical DAC times.

| approximately | direction | measured observation |
|---:|---|---|
| 4.25–6.59 s | Eicon → Courier | 2100-Hz answer-tone band |
| 5.89 s onward | Courier → Eicon | V.21 ch1 CM repeats `e0 c1 65 13 10 27 0a 0d` |
| 6.59–7.89 s | Eicon → Courier | V.21 ch2 JM repeats `e0 c1 65 13 10 2a 8d 47 65 8d` |
| 7.88 s | Courier → Eicon | CRC-checked 17-bit INFO0/INFO0a, 2400-Hz carrier |
| 7.98 s | Eicon → Courier | CRC-checked 30-bit V.90 INFO0d, 1200-Hz carrier |
| 11.06 s | Eicon → Courier | CRC-checked 77-bit INFO1c/INFO1d |
| 11.55 s | Courier → Eicon | CRC-checked INFO1a, bits 37:39 = **6: request V.90** |
| 25.59 s | Courier → Eicon | CRC-checked INFO1a, bits 37:39 = **4: request V.34** |
| 43.17 s | Courier → Eicon | another CRC-checked INFO1a requesting V.34, value 4 |
| ~56 s | local release | no CONNECT; firmware returned NO CARRIER |

The analogue stream's exact INFO1a bodies are retained in
`training-analysis/validated-courier/timeline.json`. This is wire evidence of
protocol selection/fallback, not merely an interpretation of an overlay ID.
The bit-field interpretation is documented against the Recommendations in
[x2-v90-protocol-selection.md](x2-v90-protocol-selection.md#against-the-itu-recommendations).
The actual recorded frames have CRC residue **zero**. The analyser also accepts
the complemented-FCS residue `f0b8`; it must not reject the real frames simply
because they do not use that convention. Fill bits are reported separately;
not all remote frames have four clean trailing fill decisions.

Thus this call got beyond V.8 and initial probing and requested V.90. It did
not complete training, and later requested V.34. It is not accurately described
as simply failing to hear an answer tone. The particular Phase 3/4 receive
comparison that caused fallback is not yet decoded.

## Instrumented repeat: a different, earlier stall

Evidence: `.artifact-archives/apple-courier-7910-mailbox-20261024/`.
Selected streams: Cisco `16508` ↔ PBX `13340`, ATA `6030` ↔ PBX `11420`.
Times below use the remote stream origin `1792811668.016221`. The Courier
stream starts **1.52213 s later**; comparing their unadjusted sample times would
produce a false timing diagnosis.

- The remote JM persists from **6.58 to 18.68 s**, rather than ending near 7.9 s.
  Courier CM persists until approximately **18.58 s** on the common clock.
- The ordered native mailbox records the indexed JM bytes
  `c1 65 13 10 2a 8d 47 65 8d 00` and an overlay-6 request. The host observes
  those messages within **18.04–19.04 s**. It transfers overlays 6 and 8 around
  **18.35–18.41 s**. All **20,096** words verify against the firmware source.
- Courier sends its 17-bit INFO0/INFO0a at **18.665 s on 2400 Hz**. The remote
  sends a **17-bit** INFO0/INFO0a at **18.765 s, also on 2400 Hz**, rather than
  the first call's 30-bit digital INFO0d on 1200 Hz. Later the remote repeats
  that 17-bit body; recovery includes 1200-Hz transmissions.
- Courier holds a strong 2400-Hz band. No INFO1a was recovered from its selected
  outgoing stream, and the retained ordered mailbox contains no later DSP rate
  report or datapump-gate/status message. Absence of a decoded frame alone does
  not prove it was never sent; these independent observations locate an earlier
  stall than the original call's V.90/V.34 fallback sequence.
- The remote sends BYE around **53.9 s**. This differs from the original call,
  where the local side sent BYE. Both produce NO CARRIER; they are not the same
  measured failure stage.

There is therefore a concrete **mode/role handoff discrepancy to investigate**:
the first call exchanges complementary V.90 INFO0 roles; the repeat initially
puts both INFO0 frames on 2400 Hz with a 17-bit remote body. Prolonged V.8 and
fallback are possible contributors, but the evidence does not establish which
side first chose an incompatible mode, or whether per-B-channel Eicon settings
contributed. Missing later host command `000a` is not by itself proof of a loader
bug: its ordering/requirements need to be established from the firmware.

### What actually reaches the Apple receive boundary

Using the same offline V.21 detector on two-second windows:

| remote-RTP-clock window | complete matching JM menus in remote RTP | in Apple hardware RX |
|---|---:|---:|
| 7–9 s | 4 | 1 |
| 9–11 s | 5 | 1 |
| 11–13 s | 5 | 0 |
| 13–15 s | 4 | 1 |
| 15–17 s | 5 | 0 |

Hardware windows are selected by host observation time, not exact ADC arrival;
counts include framing/search edge effects. An offline 1450–2050-Hz bandpass did
not change those hardware results. No live audio filter was changed. This is
**not BER**, nor a calibrated modem-receiver quality metric. It does show that
clear repeated menus exist at the network capture while the simple decoder has
much poorer recovery at the physical receive boundary. The native codec queue
holds only **2–5 samples** in these snapshots, not twelve seconds of queued
samples. Do not confuse cumulative `codec_rx_queued` with current queue size.

Files: `hardware-jm-visibility.json`, `rtp-jm-visibility.json`, and
`hardware-jm-bandpass-comparison.json` in `training-analysis/`.

## Instrumentation retained for the next targeted investigation

`tools/apple_mailbox_trace.py` is enabled by the existing diagnostic worker only
when diagnostics are requested. It records bounded incremental native port
writes, rather than attempting to reconstruct messages from sampled counters.
It archives messages before reset/close and saves bounded full program/data
snapshots before destructive lifecycle operations. The native bridge has already
notified reset silence, or closed the physical line, at these boundaries.
Diagnostic failure is recorded and never prevents the original reset/close.

The pre-repair repeat retains **3,822 ordered IO writes**, **77 observed host commands**,
zero loss/error markers, and a complete 128-KiB program plus 128-KiB data snapshot
from the active generation before reset. Snapshot construction took about
**60 ms inside explicit reset silence**, not an unannounced active-stream pause.
The sender at `83d4/83d7/83df` emits tag, header-high word, optional payload;
the zero header word is preserved, not discarded or mislabelled as payload.
One-second observer snapshots now also include non-consuming handshake-register
views for future captures. Messages have exact DSP instruction ordering and
bounded host observation times, **not fabricated exact emission timestamps**.

`run_attempt.py` records before/after epoch/monotonic clock anchors. Their offset
changed by about 0.60 ms during this call. The report converts observation bounds
using the endpoint offsets, explicitly assuming no hidden clock step:

```sh
.venv/bin/python tools/apple_mailbox_trace.py \
  .artifact-archives/apple-courier-7910-mailbox-20261024/call/7910/codec-mailbox.jsonl \
  --clock-reference .artifact-archives/apple-courier-7910-mailbox-20261024/call/7910/clock-reference.json \
  --rtp-start 1792811668.016221
```

Offline raw-PCMU analysis, requiring the optional NumPy analysis environment:

```sh
python tools/analyze_apple_call.py SELECTED-STREAM.g711 --g711 --output NEW-DIRECTORY
```

The INFO decoder now checks 38- and 77-bit bodies as well as INFO0, and exposes
CRC residue, fill decisions and the INFO1a protocol selector. The older short
`7e`-run heuristic falsely labelled ordinary near-zero audio as a structured
startup source, then high-RMS audio as scrambled data. Those annotations were
removed. Spectral 2100-Hz bands alone also no longer claim proven ANSam, and
1200/2400-Hz tones no longer assign physical caller/answerer roles blindly.

## Initial repair investigation (before switch access)

The initial, then-blocked repair investigation is retained privately under
`.artifact-archives/apple-ata-loss-fix-20261024/`. It made **no modem calls** and
changed **no** network, gateway, gain, port, firewall, or modem configuration.

- Read-only PBX, Proxmox host, and firewall inspection found no configured
  traffic impairment on the inspected path. The firewall has no active IPFW
  rule engine; no rules were disabled or reloaded.
- A wired host on the ATA's own VLAN also has missing ICMP replies. One capture
  contains all **120 transmitted requests** and only **117 replies**, from one
  ATA MAC `00:90:8f:57:0c:31`. ICMP is not RTP; this supports a local-path/device
  concern but does not distinguish missing requests from missing replies or an
  ICMP-specific response policy. A later counter probe had a missing SNMP
  baseline and is not claimed as a verified counter delta.
- Read-only ATA web inspection and configuration backup succeeded. Its Ethernet
  status is **100 Mbps / full duplex**. Proxmox and firewall NIC snapshots show
  zero CRC errors, but this does not establish the ATA's switch-port health.
  No reboot, configuration submission, counter reset, or flash save was issued;
  the diagnostic web session was logged out and its session-cookie file removed.
- LLDP identifies the wired host's upstream switch as
  **3560CXSw.net.cryan.nz / 192.168.88.239**, port **Gi1/0/2**. This is the host
  uplink, **not yet the identified ATA port**.
- The current SSH identity is denied by that switch, and a public-community
  read-only SNMP query times out. Authorized switch management access is needed
  to locate the ATA MAC and inspect the correct port's error/drop/duplex/queue
  counters. No password guessing, port reset or switch configuration change
  followed that denial.

At that checkpoint the loss was **not yet repaired or uniquely located**.
A successful management login or a partly passing ping probe was not treated as
a modem acceptance result. The following authorized switch investigation
supersedes that checkpoint's `status.json` and blocked-access conclusions.

## Repair applied and verified

After the user supplied switch access, its MAC table located the ATA behind
**Gi1/0/6**, a shared **1-Gbps** branch. The ATA itself remains **100 Mbps**.
There were no CRC/collision errors or configured policer on that switch port.
However, it had transmitted approximately **572 million multicast frames** and
was carrying a multi-megabit multicast flood. A short VLAN-70 capture identified
unsubscribed IPTV streams from **10.69.70.137** to **239.1.1.x:1234**. No IGMP
querier, registered IPTV groups or multicast-router ports existed on VLAN 70.

A bounded, network-only diagnostic sent **one ordinary IGMPv2 General Query**
from the wired host's existing `10.69.70.16` address. It did not alter a service
or generate modem results. The switch learned a router port and real client
group reports, and the flood toward the ATA branch stopped. Two subsequent
600-packet ICMP probes each returned 600/600. When that temporary query/router
state aged out, multicast flooding returned and the next probe lost packets
(610 transmitted, 600 returned). This was an actual before/temporary/aged-out
comparison, not an assumed benefit from enlarging a buffer.

The retained fix enables the switch's IGMP snooping querier for VLAN 70, using
its verified existing management IP as the query source. IOS requires its global
querier engine to be enabled; every other existing supported VLAN is explicitly
disabled:

```text
ip igmp snooping querier
no ip igmp snooping vlan 1 querier
no ip igmp snooping vlan 2 querier
no ip igmp snooping vlan 10 querier
no ip igmp snooping vlan 66 querier
no ip igmp snooping vlan 68 querier
no ip igmp snooping vlan 69 querier
ip igmp snooping vlan 70 querier address 192.168.88.239
no ip igmp snooping vlan 88 querier
no ip igmp snooping vlan 414 querier
no ip igmp snooping vlan 1001 querier
```

**IOS ordering caveat:** global enable resets the earlier per-VLAN overrides.
Post-enable inspection caught that behavior; the disable guards were reapplied
**after** enabling the engine, then every other supported VLAN's operational
state was independently checked as Disabled. There was a brief interval of
querier operation on other VLANs during the initial enable; that intermediate
state is retained, not presented as the final scope. No sibling process/call was
stopped, and no unicast ACL, port reset, QoS policy, gain or protection setting
was changed. No blanket multicast block, static router-port workaround, or
source-stream shutdown was used. Joined groups continue to be learned normally.

Afterward, simultaneous direct and PBX-routed probes each returned **600/600**;
the direct probe also reported one duplicate reply, so it is not claimed to be
a universally duplication-free network. More importantly, one ownership-gated,
bounded, unchanged automatic 7910 verification call produced the genuine result:

```text
CONNECT 19200/ARQ/V34/LAPM/V42BIS
```

During the ten-second post-CONNECT listen the peer sent **three PPP LCP
Configure-Requests**, all with valid PPP FCS residue **f0b8**. These were checked
from the actual untruncated `report.json` **serial_hex**, not reconstructed from
the printable escaped serial text; see `ppp-receive-validation.json`.
No local PPP session, IP connectivity or exact sustained payload was attempted
or claimed. The call used unity gain, default buffering and unchanged negotiation;
no carrier, payload, firmware result or ACK was injected.

Verification in `apple-ata-loss-fix-20261024/verification/`:

- **8 actual ATA RTCP report blocks:** cumulative loss **0**, interval loss **0**,
  scoped to ATA `6021`, reported SSRC `150f583e`.
- Selected PBX forwarding: **2,271 remote→ATA / 2,269 ATA→remote packets**, all
  payloads identical between legs, no selected sequence/timestamp gaps.
- **Zero** USB active output gaps, input overflows and capture kernel drops.
- Independent final native status: **on-hook (`hook=8`)**, protection **12**.
- `validation-summary.json` and `ata-rtcp-validated.json` preserve the result.
  The same RTCP CLI exits **1** on the retained pre-fix capture and **0** on the
  post-fix capture; missing reports are not substituted with zeros.

The switch's running/startup preflight found **only the 11 intended IGMP
configuration additions**, after excluding IOS's auto-expanded public certificate
bodies from text comparison. Raw private backups are retained. `write memory`
returned `[OK]`, and all 11 lines were then read back from startup configuration.
No reload was performed. Source-IP configuration should be revisited if the
switch's management address changes. Newly created VLANs also need an explicit
querier policy because the global engine is enabled; the disable guards cover
the existing VLAN inventory, not arbitrary future VLANs.

This repairs the demonstrated multicast-flood/receive-loss condition. It does
not resolve the exact internal ATA versus downstream-switch buffering mechanism,
nor prove that all remaining V.90 or sustained-traffic defects are fixed.

## V.90 follow-up on the clean, connected call

Offline decoding of that same zero-reported-loss call shows that the V.34
connection is a fallback, not a V.90 success. Both directions below are on the
**remote RTP start clock**; the Courier RTP stream starts **0.024429 s later**:

| Time | Evidence |
|---|---|
| 7.956 s | Remote CRC-checked 30-bit INFO0d; bit 39 announces **A-law** |
| 10.950 s | Remote CRC-checked INFO1d-family frame |
| 11.430 s | Courier CRC-checked INFO1a requests **V.90**, UINFO **78** |
| 15.490250 s | Remote starts exact **Sd**, 384 samples / 64 six-symbol repetitions |
| 15.538250 s | Exact **Sd-bar**, 48 samples / 8 repetitions with reversed signs |
| 15.544250 s | Exact prescribed **TRN1d** starts; first **2,040 samples all match** |
| 14.889–15.893 s | Ordered trace bounds the Courier's native tag `0006`; sampled mode changes from `0043` to `0053` |
| 25.824 s | Courier CRC-checked INFO1a requests **V.34** |

This establishes a real digital V.90 Phase-3 transmission, not merely a
1333-Hz spectral peak. The raw PCMU comparisons use the **announced A-law**
levels (`UINFO=78`: 3904; `UINFO+16=94`: 7808), converted to the captured PCMU
transport. They match signs, signed zeroes, amplitudes and durations exactly.
The TRN1d reference independently generates the all-one input, zero-initialized
`1 + x^-18 + x^-23` scrambler sequence. Reproducible private evidence:
`apple-v90-training-clean-20261024/{check-sd.py,exact-v90-phase3.json}` and the two
CRC-validated `timeline.json` files.

The trace does **not yet prove** that the C51 ADC consumer saw Sd in time, or
which detector/timeout caused retrain. Host observation bounds are too broad
to assign a sub-100-ms cause. A packet-stream match is not an analogue BER or
ADC-consumption measurement. Do not change V.90 thresholds or the announced law
on the strength of this comparison.

The saved **loaded C51** resident program identifies a common retrain entry at
`8d5b`, with tag-6 sender at `8dcf`. Neither is V.90-exclusive. The initial probe
watched `8d5b`, but exact replay subsequently proved that the active V.90 overlay
**bypasses that entry**, calling `8d9a` from `ddc5` instead. The corrected default
probe watches **`8dcf`**, which both paths reach. Do not infer the active V.90
overlay from a program snapshot taken after V.34 overwrites it.
`tools/apple_v90_trace.py` provides explicitly opt-in **`APPLE_V90_PROBE=1`**,
together with `APPLE_CALL_DIAGNOSTICS=1`:

- Verifies both loaded handler fingerprints before arming the native debug
  PC-capture slot, and disarms if those fingerprints change.
- Captures pre-instruction accumulator/DP/carry, C51 timer `031a:031b`, retrain
  count `0337`, measured-delay cell `033a`, dispatch/mode cells and
  `fff1/fff2/fff4/fff6/fff7` flags.
- Drains before reset/close via the existing passive mailbox lifecycle. Logs
  ring saturation, context loss and recording-budget exhaustion explicitly.
- Never writes guest program/data, consumes DRR, changes a threshold or
  supplies a decoded result. This is a rare-entry probe, **not** a consecutive
  ADC stream capture. It owns the single native PC-capture slot.
- Native paired execution checks show identical instruction state and sampled
  guest data with/without the probe. **Live timing overhead is not yet
  qualified**, so this is not a new default or a completed live diagnosis.

One subsequently requested retry is retained at
`apple-v90-retry-20261024/`. It returned `NO CARRIER` but **did not reach modem
training**: after an empty preflight channel check, caller **2900** reached 7910
before the Apple ATA finished dialing. Our Cisco INVITE remained ringing until
the PBX's **20-second** Dial timeout cancelled it; the PBX then answered and hung
up the ATA leg only **62.308 ms** apart. There was no selected remote→ATA media
stream and no applicable ATA RTCP report. Those results mean **unknown delivery,
not zero loss**, and the other captured Cisco streams belong to unrelated calls.
No competing call was stopped and no automatic redial was made. Independent
final status again verified on-hook and protection intact. Future hardware
work needs a coordinated exclusive peer window, not just a momentary idle check.

## Exact software replay: remaining V.90 failure is still not repaired

Further evidence is retained privately at `apple-v90-offline-replay-20261024/`.
No USB/PBX calls or network changes were made for this analysis. A replacement
**offline-only** helper returns the original hardware RX stream and rejects any
TX, exchange-size or control-flag difference. It requires an explicit replay
opt-in and never opens the real helper. The unchanged worker matches **1,695
exchanges / 348,106 outgoing hardware PCM samples byte-for-byte**, through the
real retrain and the incoming Sd burst. Deliberate input end then returns a
worker error; that is a bounded reproduction, **not** a successful connection.

Independent bounded replay probes establish:

- Timer setup at native instruction **774,013,268**, cycle **871,027,713**:
  accumulator **7915**, measured-delay cell `033a = 1246`.
- Retrain sender at instruction **806,842,845**, cycle **910,945,163**:
  accumulator **−5**, timer `031a = fffb`, mode `006f = 0043`,
  continuation `006d = ddd5`.
- A filtered write trace contains the timer initialization and **7,920**
  subsequent decrements, all from the actual overlay's `dd9b`; its `ddc5`
  conditional call reaches the shared retrain sender. No timer threshold was
  modified. Native cycles show **0.990016 s** between setup and sender entry;
  this measurement alone does not establish the timer's intended units.
- A separate filtered DRR trace records **all 198,410 actual guest reads at
  `8182`**, exactly matching the native `drr_reads` counter. It stays below its
  500,000-record limit. Correlation of the unique Sd-plus-TRN hardware segment
  locates it at consumer instruction approximately **816,512,067**, **after**
  the retrain at **806,842,845**. This is actual consumer ordering, not a
  64-record PC ring or a sample-clock-only plot. Waveform localization remains
  an estimate (correlation 0.969), not a BER/SNR measurement.

Two explicitly **counterfactual** replays move the existing RX recording earlier
only after a declared quiet-region point; they do not synthesize Sd, change
firmware, inject results, or claim a physical fix. A 300-ms advance still times
out (with continuation `ddd9` rather than `ddd5`). A **450-ms** advance gets past
Sd/Sd-bar: no tag-6 retrain in the bounded interval, continuation `006d = 0000`,
mode still `0043`, and receiver flag `fff4` changes from `8001` to `8041`.
TX deliberately diverges only after the retiming begins. This is a changed-input,
open-loop detector experiment, **not** a V.90 connection, a safe live latency
setting, or an end-to-end throughput result.

Read-only correlation of several remote→raw-hardware-RX landmarks during V.8,
INFO0d, INFO1d and Sd gives roughly constant host-batch/wire offsets (within
about 21 ms). That does **not** support a sudden 300-ms ATA jitter-buffer jump.
Offsets span different clocks and host-batch observation is not physical ADC
time, so they are not calibrated one-way latency measurements. The remaining
work is to explain the late server training response/turnaround or remove a
proved transport scheduling delay—not to lengthen the guest's timeout blindly.
The shared peer remained occupied by sibling 7900 calls during read-only checks;
no further live call was attempted through that activity.

The corrected sender probe has a native regression that takes the direct
`8d9a → 8dcf` route without visiting `8d5b`, and verifies the exact negative
accumulator, DP and timer snapshot. The focused trace/ADC/RTCP selection now
passes **48 tests**. Live V.90 remains **not fixed** and no speculative gain,
ATA jitter-buffer, DSP threshold or firmware timer change has been applied.

## Follow-up 256-frame experiment: peer selected V.34, not a V.90 control

A further explicitly experimental, single bounded 7910 call used 256-frame HAL
buffers, asynchronous status polling, unity gain, unchanged automatic
negotiation and the corrected passive sender probe. Evidence is private at
`apple-v90-buffer256-20261024/`. Unlike the previous cancelled call, SIP answered
and selected incoming RTP carried 2,684 packets over 53.66 seconds. There were
**12 actual ATA RTCP blocks, all reporting zero loss**, no observed active USB
output gaps/input overflows, and zero capture kernel drops. The modem still
reported `NO CARRIER`.

This is **not a valid test of the V.90 Sd timeout or a V.90 repair**: the actual
remote JM was `e0 c1 45 13 10 2a 0d`, whose modulation octet has the V.34 bit
`40` set and V.90 bit `20` clear. The guest independently recorded indexed
`c1 45 13 10 2a 0d 00` in its ordered mailbox trace. No remote V.90 INFO0d was
recovered. The probe armed but captured no shared retrain-sender entry; its
absence does not certify V.90 timing in a call that never negotiated V.90.

This proves the peer **selected/offered V.34 only on this call**, not that a
particular configuration changed: its live profile and the CM it actually
decoded have not been read. Do not call this proof that 256 frames fixes or
breaks V.90. Unrelated 2900 calls were again present before and near the end
of the call; they were not stopped and their media are excluded from ATA
analysis. No further redial followed. Independent cleanup verified hook `8`,
protection `12`, and the HAL buffer restored to **512 frames**. Experimental
settings were not made defaults.

Initially, read-only tower SSH timed out and Eicon root key authentication was
denied, including an explicit attempt with the existing project key. No passwords
were guessed and no peer/service configuration was changed. **Access was later
resolved using the user-specified `scottcryan` login**, including passwordless
sudo. Read-only service/log inspection corrected the target identity above:
7910's clean connected call reached the MultiTech PPP receiver, not the assumed
native Eicon modem. The next live control needs the actual receiver's CM evidence
and an exclusive peer window—not another blind local buffering or firmware-timeout
change.

## Remaining checks

Re-run the strict 20-second duplex acceptance gate before claiming any 60/120-
second soak, throughput or drift qualification. Keep endpoint RTCP checks in
addition to PBX payload comparison; an ATA-side ingress capture is still useful
if loss recurs. The connection above is **V.34 at 19200**, not V.90. For any
remaining failures on a verified healthy receive path, useful emulator checks are:

1. Capture what the original C51 ADC reader actually consumes, rather than only
   the USB boundary. The retained program identifies `8182: lamm @20` and
   `8183: sacl *+` as its input read/store. A properly bounded native trace here
   can separate analogue/codec distortion from native conversion/receiver state.
   The existing PC-capture ring holds only 64 records: it cannot certify a
   consecutive 7200-Hz ADC stream drained once per second.
2. Trace the actual receive-state/timeout comparison for the two distinct
   failures. Do not apply C52/other-image RAM addresses or guessed status names
   to this C51 without resolving the loaded program.
3. Obtain read-only Eicon per-call/B-channel diagnostics and current profiles.
   SIP answer and PBX forwarding do not reveal the hardware receiver's reason.

All observed helper active-loss counters stayed zero, capture kernel drops were
zero, and independent final status was on-hook with protection 12. These facts
are transport/cleanup evidence, not proof of a good analogue modem channel.

Validation: **220 focused tests passed**, including 21 RTCP parsing/scoping/failure
checks, with the optional NumPy test module
skipped in the runtime venv. Its **10 decoder tests passed separately** using the
existing sibling analysis environment, without installing runtime dependencies.
The real-ROM offline worker regression proves that ordered native mailbox writes
are archived before guest reset clears them. A final post-repair focused check
of RTCP parsing, mailbox recording and the native ADC-grid controls passed
**39 tests**. After adding the optional C51 retrain probe, the expanded RTCP,
mailbox, PC-capture and ADC selection passed **45 tests**; the probe's native
paired control preserves instruction state/data, and tests reject mismatched or
changed handler fingerprints and explicitly report ring/budget loss. No complete
repository suite, live probe timing qualification or passing sustained modem
connection is claimed.
