# Working Apple physical line / SIP Bell 103 payload control

**Result: both unchanged firmware modems report CONNECT and recover all 180
ASCII bytes sent by the other modem.** Independent FSK decoding recovers each
complete payload at every saved audio boundary. This is a working short
300-bps data exchange, not just SIP answer or carrier detection.

**Repeatability qualification:** a second independently captured call
(`../bell103-packet-audit-retry/`) also passes all 180 bytes each way and all five
independent audio checks. An intervening repeat has two corrupt return-path
characters even though its emitted SIP audio decodes perfectly; another attempt
fails closed on an 80-sample Apple output underrun. Thus the systematic emulator
bit-pump fault is repaired, but the complete physical/network path is **not yet
reliably error-free**. Those failures are retained, not discarded as outliers.

## Reproduce

Uses the powered Apple analog line (SIP identity 6004), PBX extension 2903,
403 caller firmware and Courier-emu I-modem receiver. No PBX configuration,
modem firmware, successful-carrier events or decoded receive bytes are patched.
Use a new output directory; this makes **one** bounded real call:

```sh
.venv/bin/python artifacts/apple-courier-sip/run.py \
  --protocol bell103 --payload-test --payload-size 180 --buffer-ms 200 \
  --output artifacts/NEW-APPLE-BELL103
```

The experiment launcher now defaults to the tested 200-ms SIP reserve. The
production CLI's general SIP defaults are unchanged; select
`--bri-sip-buffer-ms 200` explicitly when reproducing its receiver separately.

## Fixes and controlled comparisons

1. **Remove redundant interactive CPU throttling during live DSP bearers.**
   `courier_emu/isdn_console.py` previously slept against retired CPU instruction
   count even while SIP already paced the DSP and peripheral timers from
   monotonic time. This starved the firmware's CPU-serviced FSK bit banks.
   Offline/idle terminal pacing is retained and rebased when a live call ends.
2. **Do not treat every data-port access as another CPU scheduling turn.**
   The native wall-clock catch-up path formerly allowed another whole DS0
   frame on each closely spaced status/ACK access. A backlog could therefore
   rush the bit pump through frames before the supervisor serviced its banks.
   `native/c5x_capi.cpp` now bounds each advance by CPU instructions actually
   retired as well as one DS0 frame. The absolute wall target remains owed;
   it is not shortened and no DSP/audio cycles are discarded.
3. **Use an explicit receive reserve suitable for this test path.**
   At 100 ms, the 180-byte trial still inserted **80 silence samples (10 ms)**
   into the receive payload, corrupting two characters. With 200 ms, its entire
   **48000-sample** receive payload interval is byte-identical from SIP RX to
   the recorded DSP-facing stream. This is a tested configuration, not proof
   that every future network outage can be absorbed or a global default change.

Comparisons remain preserved:

| Capture | Actual firmware payload result |
| --- | --- |
| `../bell103-buffer100` | both corrupt; old scheduling, larger reserve alone insufficient |
| `../bell103-single-clock` | substantially improved, still corrupt; terminal fix alone insufficient |
| `../bell103-fair-clock` | both 16-byte markers correct with both scheduling fixes, 100 ms |
| `../bell103-fair-clock-180` | reverse 180 correct; forward two corrupt characters, exact 80-sample receive insertion |
| this capture | **both 180-byte payloads exact**, both scheduling fixes, 200 ms |

Independent software-pair controls with the same image and saved profile also
pass both markers: `../offline-bell103-profile` and
`../offline-bell103-wallclock`. The problem was not repaired by changing modem
waveform gain or substituting a different modem engine.

## Evidence / listen

- `payload-verification.json`: both firmware CONNECT and both full payload
  checks true; expected strings and raw caller serial hex included.
- `bell103-boundary-audit.json`: exact full payloads at Apple hardware TX,
  I-modem SIP RX, I-modem DSP-facing RX, I-modem SIP TX and Apple hardware RX.
  Source interval 18590..66590 matches heard interval 54928..102928 exactly.
- `receiver/report.log`: zero data-bank busy writes, zero torn holding words;
  native clock statistics are now included in standard I-modem reports.
- `caller/2903/summary.json`: zero active Apple output gaps/input overflows;
  independent final USB hook readback confirms released/on-hook.
- `caller/2903/apple-stereo.wav`: actual helper-bound TX left / raw RX right,
  no normalization or DC removal. Turn playback volume down first:

```sh
afplay artifacts/apple-courier-sip/bell103-fair-clock-180-buffer200/caller/2903/apple-stereo.wav
```

## Regression verification

**143 tests pass** across the focused audio/SIP/clock suite (106) and additional
I-modem pair, terminal handoff, CLI and native-machine checks (37), including
new terminal live-clock/rebase controls, a native
same-CPU-turn status-access regression, independent Bell 103 decoder controls,
Apple ADC-grid/rate-change tests, and existing native port, receive-pacing and
SIP playout/media-clock tests. See `tests/test_isdn_console_clock.py`,
`tests/test_native_port_models.py`, and `tests/test_apple_bell103_audit.py`.

## Limits

This validates short ASCII payloads at 300 bps on this physical/SIP path. It
does not establish sustained BER, arbitrary binary transparency, long-duration
stability or V.34/x2/V.90 training. The passive PBX capture in the second
successful trial observes up to **101.84 ms interarrival** on I-modem-to-PBX RTP
and an out-of-order arrival (sequence 18025 preceding 18023/18024), forwarded
in that order toward the ATA. The ATA tolerates it in that trial; this does not
prove that network jitter caused the earlier failed repeat. Packet loss/delay,
remote playout and sporadic host audio service stalls remain open boundaries.
Initial carrier/transient bytes outside the
payload are not counted as payload errors; no claim is made that every sample
before answer or after hang-up is speech/modem media. Earlier failed captures
and their failure verdicts have not been overwritten.
