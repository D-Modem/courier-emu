# Analog 7930 disconnect investigation

## Result

An instrumented **actual NO CARRIER** reproduction now has a firmware reason:

> Disconnect Reason is Unable to Retrain

This was the faster macOS host calling through the VPN, not the original
vmhost/LAN failure. Its 403 RAM snapshot has `RAM[0x03d7] == 0x0a` and ATI6
reports 0 retrains requested, 1 granted, 83 blocks resent, 2 link timeouts,
3 BLER and 7 NAKs. Carrier was lost after 123.533 connected wall seconds.
Do not generalize that reason byte to other firmware revisions.

There is independently corroborated transport damage in that reproduction:

* PBX-side capture of the emulator's incoming RTP has **19 unique missing
  sequence numbers**, no duplicates and 73 out-of-order arrivals.
* The gateway's own RTCP reports reach **19 cumulative lost packets**.
  There are 27 report blocks; peak reported interval loss is 1.5625%.
* The PBX-to-gateway capture has a **1,264.357 ms packet gap**. The captured
  subset starts after negotiation, so its missing count is 16, not the full
  call's 19. Do not add positive sequence jumps: reordering inflates that sum.
* Gateway-to-PBX RTP has no missing sequence numbers in that capture.

Thus the faster-host reproduction is **not evidence that more CPU alone fixes
this** or that a clean local receive stream proves a clean outbound call. It
has a damaged outbound network path and an actual failed retrain. Packet
capture/RTCP establish loss, not which physical hop dropped the packets or
which individual loss caused the failed retrain.

The original vmhost NO CARRIER capture did not include ATI6 or a RAM dump.
Its exact firmware cause cannot be retroactively recovered from these new
calls. In particular, the VPN loss above is not proof of LAN packet loss.

## LAN controls: no packet loss, but substantial timing excursions

Additional vmhost calls had simultaneous captures on CT127, on the PBX's
emulator-facing leg, and on the PBX-to-gateway leg, plus gateway RTCP and
post-window modem diagnostics. Firmware, clocks, 20-ms blocks, modulation,
LAPM/no compression, quoting, media reserves and acceptance checks were not
relaxed. Reentry, codec batch and packet recovery remained enabled.

| Observation | vmhost 180 s | vmhost 600 s |
|---|---:|---:|
| Genuine CONNECT | 31200 V.34/LAPM | 31200 V.34/LAPM |
| Exact 512-byte pings / sent | 96/96 | 87/88 |
| SIP/carrier/PPP up at bound | yes | yes |
| All echoes exact at bound | yes | **no: one pending** |
| PPP FCS errors | 0 | 0 |
| ATI6 requested / granted retrains | 0 / 0 | 1 / 13 |
| Blocks resent | 67 | 1,115 |
| Link timeouts | 5 | 54 |
| BLER / NAK | 1 / 1 | 34 / 46 |
| Gateway RTCP report blocks, whole capture | 38 | 121 |
| Gateway-reported RTP loss | 0 | 0 |
| Unique RTP sequence holes, connected window, either direction | 0 | 0 |
| Max outbound arrival phase excursion at gateway-facing PBX capture | 127.646 ms | 341.354 ms |
| Max outbound packet gap there, connected window | 34.497 ms | 47.866 ms |
| Native TX max sample-clock lateness before bound | 128.317 ms | 342.651 ms |
| Native TX rebuffer/recovery transitions before bound | 329 | 8,547 |

Arrival phase is `(arrival - first_arrival) - (RTP_timestamp - first_timestamp)
/ 8000`, evaluated on the connected interval only. It measures a packet stream
falling behind its sample clock, not network latency to the physical modem.
The 600-s outgoing excursion is already present at the sender capture
(342.200 ms) and PBX ingress (341.351 ms); forwarding adds essentially none
(341.354 ms). This localizes that timing defect **before the PBX**, rather
than blaming PBX forwarding or random LAN packet loss. Reverse gateway RTP
stays much steadier (roughly -38.49 to +2.75 ms over this interval).

These captures show why sequence-loss counters alone are insufficient: every
packet can arrive, but hundreds of milliseconds behind its media clock. A
receiver can exhaust its playout reserve and conceal/drop late audio without
reporting missing network sequence numbers. **We did not obtain the gateway's
actual jitter-buffer discard counters or post-playout PCM**, so the precise
conversion from the measured excursions to modem errors remains an inference,
not a measured gateway-buffer event.

The 600-s LAN run remains online but repeatedly retrains and suffers severe
LAPM recovery, reproducing deterioration rather than the terminal carrier
loss. It is not an all-pings-pass result, and is not a stability fix. The
original failed vmhost call had a still larger 619.7-ms TX sample-clock
lateness peak. The evidence supports investigating producer real-time timing
and its effect on far-end playout; it does not establish that CPU lateness is
the sole possible modem-emulation defect.

Do not include diagnostic tail traffic in data-call timing statistics. The
post-window ATI queries produce larger excursions; including them would
incorrectly report 873-ms LAN phase excursion and a 141-ms packet gap during
the 600-second data window.

## Earlier investigation calls

* Initial vmhost 600-s postmortem: 102/103 exact pings, modem/PPP still up at
  bound, but SIP had already closed. PCAP contains PBX BYE at
  `2026-11-10 09:54:04.929141`, Q.850 cause 16. Not a valid connected-at-end
  result. The initial instrumentation only triggered on NO CARRIER.
* vmhost 720-s repeat: host PPP echo timeout at 642.375 connected seconds,
  modem still online, 29/30 exact pings. Host timeout is not a modem cause.
* First passive-trace attachment failed before a call because `machine.uc`
  did not yet exist; moved attachment to the first exchange callback.
* vmhost 180-s diagnostic control: 46/46 pings, 0/4 requested/granted
  retrains, 142 resends, 10 link timeouts, 11 BLER, 3 NAKs.
* Initial fast-host 180-s control: 65/65 pings, 0/3 retrains, 83 resends,
  5 link timeouts, 36 BLER, 3 NAKs. No TX rebuffer events. Because its network
  path differs from vmhost, it is not a CPU-only matched control. The later
  instrumented fast-host failure demonstrates why that matters.
* The first RTCP-observer launch was aborted by an SSH metadata-query timeout;
  no useful call outcome was collected. Query timeouts were subsequently
  separated from the call watchdog. Preserve that failed artifact as an
  instrumentation failure, not an emulator result.

Passive LAPM receive traces include CRC-invalid frames whose independently
computed ring CRC agrees with the firmware rejection. This rules out merely
an observer-CRC disagreement for those records, but does not determine where
the bits were damaged. CPU-staged TX records are not proof of on-wire TX.

## Instrumentation and validation

* `tools/analog_disconnect_diagnostics.py`: bounded ordinary DTE ATI6/ATI11/ATI4
  queries after disconnect, with timeouts and an output cap. Optional guarded
  escape is used only after recording a host-side failure or completed test
  window while carrier remains up. No guest-memory edits, ATH, or DTR drop.
* `tests/test_analog_disconnect_diagnostics.py`: 6 passing tests.
* `tools/analyze_rtcp.py`: extended to read Linux cooked SLL/SLL2 captures
  produced by PBX `tcpdump -i any`, in addition to Ethernet/raw IPv4.
* `tests/test_rtcp_analysis.py`: 23 passing tests, including SLL/SLL2 header,
  non-IPv4 and truncation cases.
* `courier_emu/machine.py`: final raw supervisor-cell report now includes
  `03d7`; the original 403 cause is its low byte. This is observation only,
  not an injected reason or firmware patch.

Temporary launchers and post-disconnect/LAPM integration are in
`tmp/vmhost-disconnect/`. Private captures, DTE output, firmware diagnostics,
RAM snapshots, audits and manifests are under
`.artifact-archives/vmhost-disconnect-investigation/`. The newest labels are
`hardware-7930-fast-host-rtcp-v34-180s-r2`,
`hardware-7930-vmhost-gateway-v34-180s`, and
`hardware-7930-vmhost-gateway-v34-600s`. Remote-call artifacts are nested under
the same label; PBX-side captures/RTCP analyses are at the outer level.

Gateway capture filters are derived from this call's SIP/SDP media ports,
not all media from the shared gateway. No PBX configuration, guest timing,
firmware, sample buffers or PPP checks were changed. Credentials are obtained
privately and passed through environment/stdin, not command-line arguments.
Only the test's capture processes were stopped; unrelated calls/captures were
not cleared. CT127 is restored to its original stopped state after testing.

## Remaining causal boundary

We now have a concrete failed-retrain disconnect and confirmed outbound
transport damage in one reproduction, and a separate measured sender-side
media-clock defect on vmhost with clean packet delivery. A defensible next
fix targets timely sample production, not relaxed PPP checks or bigger
buffers. A claim that this fixes the original NO CARRIER still requires an
instrumented LAN reproduction/control with actual modem disconnect reason
and, ideally, gateway playout/drop telemetry.

## Follow-up: attempted fixes rejected

The subsequent request to fix this did **not** produce a validated carrier-loss
fix. The following experiments were actually implemented and tested, then
removed from production source when they failed to improve the result:

1. A guarded Python SIP DSP-batch fast path used the existing fused native DSP
   service, bypassing only provably empty bridge work. Differential tests
   covered cycle debt, messages, TDM transitions, errors, probe timing and
   non-mutating refusal. Complete 300M-instruction replay reports matched,
   but the four-run CPU3 ABBA comparison did not show a speedup:
   disabled 31.968 / 34.881 s; enabled 34.128 / 34.976 s.
2. A native worker extension stepped the DSP and accumulated retuned codec PCM
   between SIP frame boundaries, yielding before actual SIP I/O. Complete
   replay reports again matched, including a 20-ms, 300M-instruction ABBA
   comparison. Disabled: 34.786 / 37.188 s; enabled: 36.937 / 37.841 s.
   A subsequent arm-selection refinement was used in the live candidate.
   That 180-s live run passed 47/47 pings but still had **4 granted retrains,
   228 resends, 13 link timeouts, 12 BLER, and 539-ms TX lateness**. This is
   not a timing or carrier fix.
3. A 180-s P-core-only control, with both candidate optimizations disabled,
   passed 24/24 pings but still had **7 granted retrains, 132 resends,
   9 link timeouts, 12 BLER and 281-ms TX lateness**. Affinity is not a fix.

CT127's allowed CPUs changed on restart to 3/5/6/9, with 3/5/6 reporting
4.4-GHz maximum and CPU9 3.3 GHz. Offline subprocesses were pinned to CPU3;
that P-core control used 3/5/6. Do not present these as a CPU-only comparison
with earlier calls from the previous container boot.

Low-overhead 1-in-128 native-call timing samples from a separate 60-s call
had DSP sampled wall/thread-CPU totals 0.226893 / 0.227014 s and a 1.598-ms
maximum sampled call. This did not support the proposed GIL/off-CPU stall
explanation in those samples. It is sampling, not proof that every long stall
was observed. The call passed 15/15 pings.

An intrusive connected-phase cProfile experiment overflowed the existing
receive backlog limit; the limit correctly raised instead of concealing it.
A follow-up bounded profile produced useful hotspot statistics, but its first
launcher dumped the disabled profile repeatedly after the sampling window.
That instrumentation defect was corrected; neither profiling call is valid
live-reliability or performance evidence.

Rejected source and differential tests are retained privately in
`.artifact-archives/vmhost-disconnect-investigation/rejected-sip-native/`.
Live experiment labels include `hardware-7930-vmhost-sip-native-v34-180s`,
`hardware-7930-vmhost-pcores-v34-180s`, and
`hardware-7930-vmhost-capi-timing-v34-60s`. Offline comparison outputs remain
in the isolated remote snapshot under `sipbatch300-*`, `sipnative100-*`,
`sipnative20ms100-*` and `sipnative20ms300-*`.
The rejected runtime paths and temporary native ABI extension were removed
from local and remote source, and the remote native library was rebuilt to
match. All pre-existing work was preserved. The post-revert focused suite
passed **115 tests**; this is not a full-suite or carrier-stability claim.
No test worker/capture remained, and CT127 was restored to **stopped**.
