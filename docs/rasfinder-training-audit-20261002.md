# Native I-modem call to RasFinder 3999

## Connected after digital-codec receive fix

A new native outgoing call to 3999 through account 2903 now connects.
The PBX routes this call to member 8423 (8416 is busy with a separate
call). The I-modem reports `CONNECT 9600/ARQ` and receives the live
`MULTITECH SOFTWARE SYSTEMS`, `USA` and `login:` banner. No login
credentials are sent. The run stops intentionally at its limit of 400 million
instructions.

Configuration: original Ie030002.nac, erased private runtime NVRAM,
`AT*V2=3`, `AT&W`, `AT&M5&K0S58=0&B0`, `ATDT3999`. The direct PCMU/RTP
path carries raw G.711 bytes. It does not use the offline SmartLink
reconstruction profile. This is a live endpoint connection after we isolated the native
digital path from the analog-codec readback. The earlier analysis of the failed
call below is historical.

- [Successful live call summary](../artifacts/imodem-rasfinder-3999-digital-codec-fixed-20261002/summary.json)
- [Full terminal, DSP and SIP result](../artifacts/imodem-rasfinder-3999-digital-codec-fixed-20261002/result.json)


The PBX hunt group answers on member 8416. Native I-modem calls through SIP
account 2903 get to V.8, request image 6, and repeat the phase-2 training
without Hayes CONNECT. This is earlier than the sequence-J wait of the offline answering I-modem.
Do not think that they are the same failure.
The later sample-writer call does continue to the native symbol-rate report
0034:0005 before it retrains. Thus, phase 2 is not a permanent wall in
all calls.

## Confirmed SIP transmit backlog and correction

Before, `SipSession.send_pcmu` and `send_audio` enqueued media while the
session was in the inviting, trying or ringing state. `_flush_rtp` transmits only after the session is
connected, and it starts its media clock at that point. Thus, a slow answer
left old samples from before the answer in front of each later DSP response. The
queues hold up to 16000 samples, thus the delay can be up to two seconds.
The original call gave 393840 bearer samples to the RTP path, but sent only 368480 through
RTP before the capture limit. That difference includes queued and discarded
samples. It is not an exact measurement of the queue latency.

The two transmit paths now discard the samples from before the answer. They do not keep them
for later playback. The session reports that count and the length of its transmit queue.
A regression verifies that the first packet after the answer contains
current audio, in the linear mode and in the unmodified-codeword mode.

The corrected native call (V.34 only) discarded 25488 samples from before the answer, sent
440640 through RTP and ended with seven samples queued. The bearer identity is
466135 = 25488 + 440640 + 7. This proves that the old transmit backlog is gone.
It does **not** establish the modem carrier. The call still repeats the training, and
the receiver comparison below still fails.

## Receiver decision and independent arithmetic checks

The live completion checks verify image 6 at a000. All 13912 words agree with the
words that the supervisor transferred, and the destination increments to d658. There
is no later overlay request during the repeated state.

At 97cf, the firmware compares the accumulated spectral power with a minimum.
At 97d7, it compares that power with the reference at 03e8:03e9. In the first
receive audit, all 519 retained attempts got to the second comparison, and
none got to its successful exit at 97d9. When we disabled x2 and V.90 through native
S58=33, this did not solve it (454 attempts, zero successful exits).

Read-only PC captures record the exact sample and transform buffers at the
comparison. In strong-tone windows, the power of the selected bin of the native transform
agrees with a direct Fourier calculation in about 0.11%. The
isolated original transform also correctly puts known tones in their
expected bins. The reference-update routine 8d0f gives the expected
fixed-point square increment for positive and negative test inputs. In the
sample-history capture, each of 1280 recorded input subtractions agrees with
the new sample minus its stored predecessor. All 1699 adjacent retained
sample captures also increment the history index by exactly one. These checks exclude errors
in those specific calculations. They do not exclude errors in all DSP arithmetic or interrupts.

The reference accumulates squared differences between new samples and
samples from the 64-sample history buffer. We do not know why its value is high at the failing
decision. The captured returned Tone A includes the expected
1800 Hz guard tone. V.34 specifies that component, and it is not spurious
audio. The original receive capture aligns with the received RTP at an almost
constant offset after startup. Thus, that recording does not support frequent sustained receive sample slips.

The follow-up phase-timing call selected image 8 and not image 6 after
V.8. Thus, it did not use the configured V.34 capture point. It repeatedly
reported native timeout/retrain replies 000f:0000 and 0006:0000, without
CONNECT. It cannot establish the V.34 phase-change timing.

## Consecutive receive capture and PCM scheduling correction

The consecutive history call keeps 293558 samples. There are 274113
checks of the exact 64-frame predecessor and 292849 checks of the reference
increment, with zero mismatches in either. Periodic large sample excursions
increase the reference during some repeated detector windows. The later FIR
capture independently reconstructs all 135138 retained executions of the receive
conversion 8234, with zero output mismatches. The native original mu-law
expander also agrees with G.711 for all 256 codewords, decoded at one-quarter
scale. These are checks of specific routines. They do not prove that the scheduling of their input
samples is correct.

The optimized `advance_imodem` path ran all of its requested cycle budget
before it returned PCM to the DSC MUX. The existing receive-pacing regression
used a fake core that did not have this optimized method. A native reproducer
with one receive word and a 20000-cycle advance makes three PCM frames
and four empty receive octets before the host can supply the next word.

The native optimized advance now yields at each completed PCM frame. The
instruction-coupled scheduler and the realtime scheduler exchange that frame before
they continue the remaining cycle budget. During the realtime catch-up, the BRI peer
also exchanges each completed DSC frame before the next MUX clock. It does not
wait for the next pass of the outer CPU scheduler. The regressions use
the actual native path and a receive queue that is supplied one frame at a time.
Neither change patches the modem training state or accepts a failed detector.

The uninstrumented live call with fixed pacing clocks 364173 PCM frames with
**zero DSP empty receive slots and zero DSC receive underruns**. Its receive
queues finish at exactly one word in the DSP and one octet in the DSC. Earlier calls
kept hundreds of samples. The native firmware
reports 0034:0005 and later retrains. The DTE still does not report CONNECT.
Thus, the scheduling defect is corrected, but the carrier establishment
is still not solved. Refer to the [fixed call summary](../artifacts/imodem-rasfinder-pcm-frame-fix-20261002/summary.json).

## Evidence and validation

### Later training and RTP playout

The later-training capture identifies the exact retrain caller as `a90c`.
`a909` checks the signed high word of the training timeout at `031a`, then
shifts two received bits into the `0343:0342` history. It needs two equal
16-bit words with the value `8990` when bit 5 is masked. This is the V.34 J
sequence detector. The timeout capture occurs at DSP time 25.839289 seconds,
with coroutine `006d=a7b1` and receiver `088d=a2c2`. The overlay executes.

A later unmodified native call **does recognize J**, at DSP time
19.364888 seconds. The firmware then sets the expected `006f` flags, sends its
own training, and later retrains from `a198`, the timeout check of the S detector.
Independent calculations agree with all 1691 consecutive captured descrambler
updates and all 1691 bit-history shifts. This shows that the J recognition
works sometimes. It does not show that the carrier or the payload transfer works.

The packet-level observation also found 101 inserted silence samples after the
first 100 ms of RTP, although the packets were otherwise continuous. The bearer consumed
each arriving packet immediately. Thus, the normal arrival jitter emptied its queue
and inserted silence into the modem waveform. `BearerSipLine` now fills a
320-sample receive queue before the playout, and builds that reserve again after a real
outage. It keeps each received codeword in sequence, without resampling and without
a change to any training decision. Its initial reserve adds about 20 ms
of playout delay for normal 160-sample RTP packets.

One validation call had an actual incoming timestamp gap of 2560
samples and a 320 ms arrival gap, followed by a change of the RTP SSRC. A small
buffer cannot hide that source outage. The final buffered live call has
**zero inserted silence after the first 100 ms of RTP and zero DSC underruns**,
with 248 samples left in the receive queue. It still repeats phase 2 and
does not report CONNECT. The removal of these waveform discontinuities is a
verified transport correction. It is not proof that the remaining DSP failure is
solved.

- [Later retrain trace](../artifacts/imodem-rasfinder-late-training-20261002/retrain-trace.json)
- [Independent J bit checks](../artifacts/imodem-rasfinder-j-detection-20261002/bit-analysis.json)
- [Unbuffered packet timing](../artifacts/imodem-rasfinder-phase3-media-20261002/media-analysis.json)
- [Buffered live validation](../artifacts/imodem-rasfinder-rebuffered-media-20261002/media-analysis.json)

The full applicable suite passed 130 tests before the refinement of the outage recovery.
All 10 affected bearer, SIP startup and native receive-pacing tests pass after
that refinement. These include a new regression with an outage followed by jitter.

An additional bearer transparency regression uses guest instructions to write
DXR. It clocks the native digital serial port and the programmed DSC MUX, and
checks all 256 G.711 codewords in the two directions. Each octet is kept,
the first slot carries B1, the unrouted second slot stays idle, and the receive
latency is a constant one modeled frame. No sample is duplicated or dropped,
and no receive queue underruns. All nine pacing and playout tests pass
with that regression. This verifies the local frame path. It does not verify the live RTP delivery
or the full equivalence of the device timing.

### Independent outgoing RTP clock

The outgoing RTP trace of the buffered call has a maximum packet gap of 62.23 ms,
followed by catch-up bursts. Its average rate is 8000.02 samples/s. Thus, this
is scheduler jitter and not sustained clock drift. When packets are sent from
the per-frame callback of the emulator, the network delivery depends on when the
host next runs that callback.

The BRI SIP peer now enables an independent RTP sender. It first fills three
160-sample packets, sends at monotonic deadlines of 20 ms, and keeps all G.711
codewords unchanged. The initial reserve adds about 40 ms of TX
latency. An actual production outage builds that reserve again. It does not invent
audio. Codeword queues no longer silently discard their oldest samples at a
length limit of two seconds. The clock thread stops when the session closes.
The analogue SIP sender keeps its existing synchronous behavior.

The [clocked live trace](../artifacts/imodem-rasfinder-clocked-rtp-20261002/timing-analysis.json)
has 1225 outgoing packets, a **25.00 ms maximum gap**, a 24.35 ms 99th-percentile
gap, and a maximum phase delay of 8.94 ms relative to a 20 ms packet schedule.
Its receive side again has zero inserted silence after the RTP startup and zero
DSC underruns. The firmware still repeats phase 2 and does not report CONNECT.
This is a measured decrease in the transport jitter. It is not a solved modem call.
All 134 applicable DSP, I-modem, bearer, RTP, bridge and resampler tests pass.
The sender tests verify these items: continued packet delivery while the producer is paused,
codeword preservation, monotonic RTP timestamps and a clean thread shutdown.

The assumed machine-cycle frequency of the C51 is still a separate timing uncertainty.
The oscillator can is 40.320 MHz, but we did not measure the ASIC output frequency and the levels of the C51 clock
mode pins. The clock modes of TI support different
relations between the input clock and the machine clock. A change of the assumption
without those facts would not establish an instruction timing that is equivalent to the device.

### Larger-buffer control

The [100 ms buffer call](../artifacts/imodem-rasfinder-large-buffer-20261002/timing-analysis.json)
uses 800 samples in each direction, compared with 320 RX / 480 TX in the
call before it. It finishes with 697 RX samples buffered, zero inserted silence
after startup and zero DSC underruns. The outgoing packet gaps have a peak of 30.05 ms.
The firmware still repeats phase 2, and the DTE never reports CONNECT. This trial
does not show an improved training from the larger reserve. It does not establish
that all buffer sizes or calls have the same behavior.

`isdn-run --bri-sip-buffer-ms 100` now selects that setting for the two directions.
The existing defaults stay at 40 ms RX and 60 ms TX. For normal 20 ms packets,
the 100 ms priming adds about 80 ms playout delay in each direction. Buffer sizes
below one 20 ms RTP packet are rejected. Small and large receive-buffer tests
verify the codeword continuity through delayed packets.

### Fixed peripheral slots and remaining receiver failure

Before, the DSC assigned the peripheral slots from the sequence of the MUX registers, including
the MAP/MPI ports. It also labeled C4 incorrectly as PPCR2 and C8 as PPCR3. AMD 09893H defines
Bd/Be/Bf as fixed peripheral channels 6/7/8. SBP sends those three octets in
sequence. The first two octets of IOM-2 are Bd/Be, and PPCR1 bit 3 selects the fifth or
sixth octet for Bf. PPCR2 is C8, PPCR3 is C9, and C4 is C/I channel 0 data.
The model now implements those slot positions and the correct register addresses.
The tests use reversed MUX programming order, two independent B channels,
disabled/SBP/IOM-2 modes, and IC1/IC2 selection. The earlier native pacing test
fixtures incorrectly used the MAP port as a peripheral slot. They now use Bd.

The [fixed-slot live call](../artifacts/imodem-rasfinder-fixed-pp-slots-20261002/summary.json)
reports physical slots [6,7], zero DSC underruns, and zero inserted silence
after the RTP startup. It still does not connect. In this call, MCR1 connects B1 to
Bd. Thus, the correction of the slot model does not change which slot carries its audio.

An isolated execution of the original `81fd` mu-law compressor agrees with the
standard reference for all 32768 even signed 16-bit input levels. Its wrapper
sets DP=7 and ARP=1, supplies half-scale input as the routine expects, and
extracts the returned codeword with SACH shift 4. This complements the earlier
check of all 256 codewords of the expander.

The clean sample-timing trace keeps 248337 receiver samples. Across its
64057 captures while coroutine `006d=97b2` is active, none has accumulated
tone power above the adaptive reference threshold. The original receive callback cadence of 9600 samples/s
is kept during contiguous detector windows.
This limits the investigation to the received waveform and its DSP processing.
The trace alone does not show if the cause is an incorrect transmitted handshake or a
defect of the receiver emulation.

A diagnostic [20.16 MHz C51 call](../artifacts/imodem-rasfinder-c51-half-clock-20261002/summary.json)
halves the machine cycles each second and keeps the 8 kHz DS0 divider. It
also repeats phase 2 and does not connect, with zero DSC underruns. This does
not identify the actual clock pins of the device. The default clock did not change.
All 138 applicable DSP, I-modem, bearer, bridge and resampler tests pass.

Source: [original AMD Am79C30A/32A datasheet, tables 18 and peripheral-port registers](https://dtsheet.com/doc/268597/amd-am79c30ajc).

- [Original call](../artifacts/imodem-rasfinder-3999-20261002/result.json)
- [Live overlay audit](../artifacts/imodem-rasfinder-overlay-audit-20261002/overlay-verification.json)
- [Receive comparison trace](../artifacts/imodem-rasfinder-receive-audit-20261002/receive-traces.json)
- [Exact decision captures](../artifacts/imodem-rasfinder-decision-capture-20261002/decisions.json)
- [Independent Fourier comparison](../artifacts/imodem-rasfinder-decision-capture-20261002/decision-analysis.json)
- [Input history capture](../artifacts/imodem-rasfinder-history-capture-20261002/decisions.json)
- [Corrected live call](../artifacts/imodem-rasfinder-media-start-fix-20261002/result.json)
- [Consecutive history checks](../artifacts/imodem-rasfinder-contiguous-history-20261002/history-analysis.json)
- [Independent receive FIR check](../artifacts/imodem-rasfinder-receive-fir-20261002/fir-analysis.json)
- [Per-frame pacing live call](../artifacts/imodem-rasfinder-pcm-frame-fix-20261002/summary.json)
- [ITU-T V.34, section 10.1.2.1 and phase-2 procedures](https://www.itu.int/rec/dologin_pub.asp?id=T-REC-V.34-199610-S!!PDF-E&lang=e&type=items)

128 applicable C5x, I-modem, bridge, resampler and SIP regression tests pass.
The instruction-boundary capture feature is disabled unless it is explicitly
configured. It reads data and mapped registers and does not change the guest state.

## Direct 8416 and 8423 calls

We tested the same native I-modem configuration directly against the two
extensions, one after the other, through SIP account 2903. The first 8416 attempt
receives SIP 486 Busy Here while a separate 2900 call uses that endpoint.
The first direct 8423 call answers and trains, then receives a remote BYE
and reports NO CARRIER. We keep these initial results.

When the two endpoints are free, each repeated direct call reports
`CONNECT 9600/ARQ` and receives the MultiTech `USA` / `login:` banner. No
login credentials are sent. Each run stops at its limit of 400 million
instructions. This confirms direct carrier and received application
data at the two endpoints. The unsuccessful first 8423 attempt also shows that
the live negotiation is not yet guaranteed on each call.

- [Both successful direct call summaries](../artifacts/imodem-direct-8416-8423-retry-20261002/summary.json)
- [8416 successful terminal and SIP state](../artifacts/imodem-direct-8416-8423-retry-20261002/8416/summary.json)
- [8423 successful terminal and SIP state](../artifacts/imodem-direct-8416-8423-retry-20261002/8423/summary.json)
- [Initial busy and NO CARRIER outcomes](../artifacts/imodem-direct-8416-8423-20261002/summary.json)

`tools/probe_imodem_sip.py` reproduces these calls. It uses only the existing
2903 authentication stanza, which it reads over SSH. It never prints or saves the password of that
account, and it does not change the PBX routing or the endpoint settings.
