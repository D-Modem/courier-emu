# Analog Courier V.90: finite-bank scheduling repair

## Status

**7900 has now established genuine error-corrected V.90 over SIP**, with the original 4.03 firmware:

```
CONNECT 50666/ARQ/V90/LAPM/V42BIS
```

The independent answerer journal confirms:

```
/dev/ttyds1 CONNECT V90/LAPM/V42BIS/50666:TX/31200:RX
```

The complete BRI MODEM TEST LAB menu reached the emulated DTE without the corruption seen in the earlier normal-mode calls. This is carrier and readable application-output evidence, **not sustained exact duplex qualification**. The passive DSP trace shows subsequent renegotiation/retrain transitions; stability remains open.

This successful call used the isolated, opt-in level-conversion experiment described in [the earlier investigation](analog-sip-v90-20261102.md). Its gain assumptions have **not** been adopted as a production calibration repair. Default/unscaled V.90 operation remains unqualified.

The scheduling repair is now in `courier_emu/bridge.py`, with regressions in `tests/test_sip_data_batch.py`, and deployed only to `/root/courier-sip-20261102-113720`. The first repeat launcher skipped an unrelated, active 6314→7910 call through the shared gateway. That guard was too conservative: after the user clarified two-call capacity, a second 7910 call was admitted concurrently and the original call remained active. The second call connected at **31200/ARQ/V34/LAPM/V42BIS**, not V.90, and received the peer’s PPP LCP requests. Both PBX legs used A-law without transcoding; active RX underruns and receive rebuffers were zero. Thus the A-law control does not by itself fix 7910 V.90 fallback. Evidence is in `.artifact-archives/analog-sip-vmhost-v90-training-20261103-053043/`, including simultaneous-channel and postflight snapshots. No extra number or configuration change was needed for this concurrent admission.

## Demonstrated defect

SIP run setup selects a 4096-instruction DSP scheduling batch to retain real-time training headroom. That also allowed the DSP to publish several XF edges and fill all six ASIC receive banks before the CPU could acknowledge any of them.

The CPU's 64-instruction IRQ recognition interval did not solve this: recognition cannot observe an edge until the DSP has actually run. Captured CPU bank reads clustered **exactly 4096 guest instructions apart**. At the captured 3,399,663 instructions/s this is approximately 1.205 ms. Even an instantaneous consumer can then drain at most about 4,980 byte-sized bank publications/s, below a 52,000-bit/s downstream's 6,500 bytes/s before considering control publications and burst alignment.

A matched live capture distinguishes this from a general inability to decode the downstream:

* Archive: `.artifact-archives/analog-sip-vmhost-v90-training-20261102-195908/`.
* Native pre-descrambler samples, independently descrambled with the standard [18,23] taps, contain a **CRC-valid 45-byte LAPM XID**; its FCS residue is `f0b8`.
* The simultaneously captured CPU-side bank stream does not preserve that complete frame.
* Earlier CPU CRC-gate observations likewise show truncated 33/34-byte XID-shaped frames rejected by the original firmware. Its computed CRC agrees with an independent calculation over the bytes actually received: the CRC check itself is not the defect.
* At the original coarse quantum, the full run reports 142,093 coalesced XF edges and 57,224 delivered frame interrupts. These are whole-run counters, not counts limited to a particular payload interval.

The original firmware output routine at `8320` explicitly returns without publishing when the selected bank is busy. Enlarging the six-bank device, accepting bad CRCs, or forcing carrier would hide this error, not repair it.

## Repair

The original resident's runtime command `000a` selects its receive byte/bit-framing routine. On this command, **ROM SIP bridges cap an oversized scheduling quantum at 1024 CPU instructions**:

* Smaller user-configured quanta remain unchanged.
* Other runtime commands, non-ROM paths, and non-SIP transports are unchanged.
* Reset restores the configured training quantum.
* Accumulated CPU ticks, DSP cycle debt, codec credits, and exchange credits are retained; no elapsed work is discarded or duplicated by the change.
* CPU/DSP frequencies, CPI, UART baud, the 64-instruction IRQ recognition interval, waveform buffering capacities, firmware, thresholds, and CRC handling are unchanged.
* Status now exposes configured/effective scheduling batches and a bounded change history.

This is a coupling-latency correction, not a clock-frequency adjustment. The coarse training path is retained deliberately: starting a whole live call at 128 instructions aborted on receive backlog, while a whole-call 1024-instruction control incurred 13,334 active receive-underrun samples and failed to connect. Neither is a valid clean PHY control or an adopted workaround. No reserve/capacity enlargement was used to conceal these failures.

## Positive live experiment

Archive: `.artifact-archives/analog-sip-vmhost-v90-training-20261102-201937/`.

The isolated experiment applies the same 4096→1024 transition on runtime `000a`, without changing firmware or device capacity. It transitions at CPU instruction 133,377,920. The call reports `CONNECT 50666/ARQ/V90/LAPM/V42BIS` and the readable menu. The answerer journal is archived as `7900-independent-peer-journal.txt`.

The run ends normally at its 300-million-instruction bound, approximately 88.44 seconds wall time. Active receive underruns: **0**; receive rebuffers: **0**; no receive-backlog error. The later DSP mode transitions include renegotiation/retrain sequences, so this is not evidence of a stable long-duration 50,666-bit/s payload link.

Earlier coarse-batch normal-mode calls genuinely established `52000/V90/NONE` and `40000/V90/NONE`, but their menus/echoes were corrupt. Lowering the requested rate alone did not fix the transport handoff; those are not usable-link qualifications.

## Regression evidence

`tests/test_sip_data_batch.py` covers the receive-mode guard, smaller explicit quanta, unrelated commands/transports, retention of clock credits, idempotence, reset-net restoration, and bounded diagnostics.

A component load test runs the **original resident output routine**, loaded from the 403 ROM, against the actual six-bank native device. It offers the captured 45-byte XID at 52 kbit/s, with an instantaneous CPU ACK on each serviced nominal XF event. This is an intentionally optimistic consumer, not a simulated successful call:

| Coupling quantum | Bytes preserved |
| --- | ---: |
| 256 | 45/45, exact |
| 1024 | 45/45, exact |
| 4096, uncapped negative control | 36/45 |

The test does not modify the resident routine, relax an FCS, or enlarge a queue. It demonstrates starvation even before real CPU ISR work is charged. It is not an exact physical-time or full-CPU replay.

Validation after this change:

* New regression file: **21 passed**, local and isolated Linux.
* Local focused SIP/native-port/XF/delayed-call/serial/phase-2-analysis selection: **166 passed**, using the existing sibling NumPy environment on `PYTHONPATH`.
* Isolated Linux SIP-data/quiet-clock/serial/native-port/XF selection: **89 passed**.
* A separate broader bridge selection encountered the previously known, unrelated `test_audio_line_frames_are_paced_at_codec_rate` fixture error: its incomplete `__new__` bridge lacks `line`. That selection was **71 passed, 1 failed**; it is not represented as a clean full-suite run.

## 7910: correct the transport-law assumption before another control

The earlier PCMU/account-6000 7910 normal-mode call (`20261102-194002`) fell back to `31200/V34/NONE`; the first attempt using PCMU with account 2905 was rejected with SIP 488 and never trained.

Further offline inspection of the answered PCMU recording shows:

* CRC-valid digital **INFO0d advertises A-law**: body bit 27 is 1. `tools/analyze_v34_phase2.py` now exposes this as `pcm_law`, with recorded-frame and bit-position regressions. This supersedes treating the previous endpoint/controller mapping as sufficient evidence that this particular call's digital modem is μ-law.
* Its downstream includes ±8 zero slots and ±3900 TRN1d levels in the PCMU recording. These map back to the A-law zero slots and U_INFO 78 levels.
* Reversing the recording's μ-law companding into A-law for **offline analysis only** allows the independent, strict A-law phase-3 decoder to recover Sd (64 repetitions), S-bar-d (8), and **52 CRC-valid Jd frames**, including J'd and entry into DIL.
* A separate diagnostic μ-law analysis with nonzero-zero-slot tolerances also recovers those Jd frames. Neither analysis changes the emulator, firmware, or live acceptance criteria.
* The decoder's DIL preset is not the actual Courier Ja descriptor, so its later DIL coverage/usable-level statistics are **not** a conformance grade for this call.

The next live 7910 control should therefore use the already available **2905/PCMA** path, verify both negotiated PBX legs, and retain the repaired data-phase coupling. No PBX, modem, authentication, or peer configuration needs changing for that control. Until a real live result exists, neither V.90 carrier nor V.90 PPP on 7910 is claimed.

## Two-call 7910 capacity check (2026-11-03)

The answerer configuration lists `/dev/ttyds3` and `/dev/ttyds4` on controller 1, both answering **7910**. The previous launcher treated any activity on gateway 6501 as busy; that was unnecessarily restrictive. The revised launcher counts actual caller-side 7910 dialogs and permits a second call, while still preventing overlapping use of our own test account. It issues no channel-clear or peer-reconfiguration command.

In `20261103-053043`, Asterisk simultaneously recorded the existing 6314→7910 dialog (`00001676/00001677`) and the new 2905→7910 dialog (`00001678/00001679`). The new call connected at **31200/ARQ/V34/LAPM/V42BIS**, received PPP LCP requests, and ended at its normal bound. The original dialog was still Up in the postflight snapshot. This verifies concurrent call admission and a second modem connection on the **same number**; a new number is not needed for that capacity check. It does not prove which physical tty accepted either call.

A subsequent PPP-oriented repeat (`20261103-053319`) was answered at SIP level but returned **NO CARRIER** before PPP began. This was not a BUSY/capacity rejection, and no PPP authentication or payload success is claimed for it. By final postflight no channels remained active. No unrelated call was explicitly cleared.

## Next qualification

1. Recheck per-number capacity, allowing two 7910 calls; preserve unrelated sessions.
2. Repeat 7900 with the production repair and exact text echoes, retaining the clean/experimental-gain distinction.
3. Enter 7900's existing `7 PPP lab link` menu option and verify exact binary peer ICMP through ordinary DTE serial input/output. This peer starts a **noauth** PPP lab session, not PAP login. Internet routing is a separate test.
4. Test 7910 using PCMA and the existing account, then repeat its PAP/IPCP and exact payload qualification if V.90 actually connects.
5. Characterize retrains, sustained duplex throughput, and the stock PTY/kernel-pppd path separately. The earlier [7910 PPP qualification](analog-sip-7910-ppp-20261102.md) remains V.34 evidence.
