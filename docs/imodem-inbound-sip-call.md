# Inbound SIP: a real Courier calls the I-modem

This run uses the opposite direction of the existing live call. A physical analogue
Courier starts a call through Asterisk. Asterisk sends the INVITE to the
emulator. The virtual NT sends a 3.1 kHz, mu-law Q.931 SETUP to the I-modem.
The SIP response follows the actual behavior of the I-modem: 100 Trying on INVITE,
180 Ringing on ALERTING. Q.931 CONNECT starts the local bearer. But the SIP 200 OK
with the PCMU SDP waits for the answer waveform of the DSP: a minimum of 160 samples, with
32 samples of decoded magnitude of 128 or more. The emulator keeps the start of that waveform
in a buffer and transmits it after it accepts the call. Thus, the caller does not get
the idle bearer of some seconds that occurred before the answer tone
in the physical Courier capture of 2026-10-03. A live retest is still necessary to see the
physical training with this change.

`--bri-sip-register` registers the local contact with the configured username
and password. If you do not use it, configure the Asterisk extension as a static contact.
The emulator renews the registration at 80% of the lifetime that the registrar accepted. It makes a
new authentication attempt at each renewal. The requested lifetime is 300
seconds. Without renewal, the extension disappears after five minutes, although
the emulator continues to run.
The `--bri-sip` address must be the signalling address of Asterisk, because the UDP
socket accepts the INVITE and the subsequent dialog requests from that peer.

You can receive more incoming calls in the same process after the call clears. The
incoming-call check uses the current idle call state. It is independent of the
one-shot guard for `--bri-call-at`. The call clearing also resets the ringing flag and the
answer/receive buffers. This also occurs when a caller cancels before the answer.

Make an artifact directory. Then run the emulator in terminal mode, so that it
stays available while the physical Courier starts the call:

The launcher uses 8N1 by default. This also applies when it loads an older custom flash
profile. Set the terminal of the physical Courier to 8N1 too. To keep an explicitly saved serial format,
use `--dte-framing stored`. To select a format explicitly, use
`--dte-framing`. If the received text has unexpected characters with the high bit set, examine ATI4.

```sh
mkdir -p artifacts/imodem-inbound-sip-live

.venv/bin/python -m courier_emu isdn-run Ie030002.nac --with-dsp \
    --terminal --report --flash-nvram artifacts/imodem-inbound-sip-live/nvram.sav \
    --bri-network --bri-establish terminal \
    --bri-call-to 7349195 \
    --bri-sip asterisk.net.cryan.nz --bri-sip-username 6000 \
    --bri-sip-register --bri-sip-local-port 5062 \
    --bri-sip-record artifacts/imodem-inbound-sip-live/caller-to-imodem.g711 \
    --bri-tx-g711 artifacts/imodem-inbound-sip-live/imodem-to-caller.g711
```

At the I-modem terminal, enter `ATS0=1`. When it replies `OK`, dial the
extension from the real Courier. To stop the run, push Ctrl-]. Save the JSON report
that the emulator prints on stderr as `artifacts/imodem-inbound-sip-live/run.json`. (You can also redirect
stderr when you start the command.)

Analyze the two directions and make WAV files that you can listen to:

```sh
.venv/bin/python tools/analyze_bri_sip_audio.py \
    --from-caller artifacts/imodem-inbound-sip-live/caller-to-imodem.g711 \
    --from-imodem artifacts/imodem-inbound-sip-live/imodem-to-caller.g711 \
    --output artifacts/imodem-inbound-sip-live
```

The evidence has three independent parts:

1. `bri.media_peer.sip.rtp_octets_received` gives the number of caller octets that got to
   the RTP socket. `bri.media_peer.octets.received_from_rtp` counts the octets that
   the B-channel bridge took. The exact accounting identity of the bearer is
   `received_from_rtp + silence_filled == bri.media.rx_delivered`. The received RTP
   can be larger than the consumed count by a final partial block in the queue.
2. The emulator captures `imodem-to-caller.g711` at the B channel on the DSP side, before RTP.
   A strong 2100 Hz window shows that the answer signal of the I-modem got to
   the bearer. Over a sufficiently long interval, the 15 Hz
   ANSam modulation sidebands also show this.
3. `caller-to-imodem.g711` contains only actual received RTP payload. It never contains
   silence that the emulator added for pacing. Audio that is not idle, with V.8 V.21 energy near
   980/1180 Hz, shows that the negotiation traffic of the originating Courier
   got to the bridge. The delivered counter above completes the path to the DSP
   bearer.

The original outbound scenario does not change. If you supply `--bri-sip-target` (or
let the dialled digits of the modem fill it), `BearerSipLine` still
calls `SipSession.start_call()` and uses the existing authenticated INVITE flow.

During a live SIP B channel, monotonic wall time at 40.32 MHz paces the C51 digital-PCM
peripheral. The supervisor PIT and the periodic RTOS/mailbox
service interrupts use wall time during the same live call. Before, those
timers followed the progress of the CPU instructions. Under load, this could be much slower
than the real-time DSP. The clock transitions keep the elapsed time
across hangup and subsequent calls. The `pit.time_seconds` and
`pit.cpu_time_seconds` values of the report show the difference. Offline runs with an instruction budget
keep the deterministic coupling to instructions. A focused regression
checks that 100 ms gives 800 bearer frames. It also checks that when the call stops, a
new clock epoch starts, and the clock does not catch up the idle time.

The live DSP catch-up yields at a PCM-frame boundary after a host-time slice of one millisecond.
Thus, the supervisor can service interrupts during a backlog.
The absolute DSP target stays for the subsequent slices. If the clock sources
agree, this alone does not prove that the firmware receives each tick.
`pit.coalesced_timer_edges` counts timer requests that were lost because multiple
periods elapsed, or because a PIC request was already pending. The capture launcher with timestamps
is `python -m tools.run_imodem_inbound_trace --extension 2903`. It saves each
run in a new directory, and it uses the existing PBX test account.

The hardware call of 2026-10-03 got to V.34 at 31,200/33,600 with a reported SNR of 37.5 dB.
But it had errors. The Courier reported 100 retransmissions
and 23 block errors. The I-modem reported 88 retransmissions and 826 block
errors. The endpoints reported about four minutes against 52 seconds of
connected time. Because of this, we corrected the supervisor clock. It does not
show that timer drift caused the x2 failure. The report and the G.711
captures from before the fix are kept in `artifacts/real-courier-call-clock-audit-20261003/`.
A new hardware call is necessary to verify the effect on training and errors.

## Live result, 2026-09-13

Extension 6000 was registered on local UDP 5062. A physical Courier on
`/dev/cu.usbserial-1140` (source extension 8403) dialled `ATDT6000`. The
directory number of the I-modem is 7349195. Thus, the run used
`--bri-call-to 7349195` to map the PBX extension to that Q.931 number.

The signalling capture contains REGISTER/401/authenticated REGISTER/200,
INVITE/100/180/200/ACK, and BYE/200. Q.931 contains SETUP, ALERTING, CONNECT,
DISCONNECT cause 16, and RELEASE_COMPLETE. The active bearer delivered 107,871
octets. Of these, 107,681 came from RTP, and only 190 were pacing fill. It sent
107,871 octets to RTP, and 101,805 of them were not idle.

The caller capture has a strong 1300 Hz calling tone and V.21 energy at 980 and
1180 Hz. The I-modem capture has a 2100 Hz carrier with sideband-to-carrier
ratios of 0.0915 at 2084.95 Hz and 0.0736 at 2115.05 Hz. Thus, ANSam got to the DSP
bearer. But the two modems stopped with `NO CARRIER`. The transport operates,
but the training did not complete. The machine-readable result, the PCAP, the raw G.711,
the WAV files, and the spectral report are in
`artifacts/imodem-inbound-sip-live-20260913/`.

## Pacing retest, 2026-09-13

We used the same physical Courier and the `6000/6000` Asterisk account after the
wall-clock correction. The connected leg received 107,840 RTP octets and sent
108,320. This is 13.480 and 13.540 seconds, a duration difference of 0.45%.
The BRI bridge clocked 108,457 frames (13.557 seconds). It filled 1,314 frames
of real startup/network underrun. The earlier run had only 13.48
seconds of transmitted bearer during a call of 29.74 seconds. This run replaces it.

The new caller capture contains V.21 energy at 980 and 1180 Hz. The I-modem
capture again has a strong 2100 Hz ANSam carrier, with sideband-to-carrier ratios
of 0.0817 at 2084.95 Hz and 0.0689 at 2115.05 Hz. The physical call still did
not train to carrier. But the DSP bearer and the RTP clock now agree. The evidence
is in `artifacts/imodem-inbound-sip-paced-20260913/`.
