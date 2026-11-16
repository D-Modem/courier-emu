# I-modem versus Tower SmartLink, 2026-10-02

## Resolved: V.90 probe reconstruction

The V.90 stall is resolved in the SmartLink probe. The probe now uses the same
active downstream reconstruction path as Tower: a 257-tap, six-phase Hann-windowed
sinc through Sd/bar-Sd, then eight-point Lagrange interpolation from the
first TRN1d symbol. The old probe used its generic 128-tap Kaiser sinc
for the full call. This resolution did not need a change to the guest firmware, a supervisor command, the DSP program,
the DIL descriptor, or the serial clock.

With the Tower profile, SmartLink recognizes Jd and sends S. The native DSP
capture records the entry to the DIL generator `ca57`. The two terminals report
`CONNECT 34667`. SmartLink identifies the negotiated datapump explicitly as
V.90 with downstream 34667 and upstream 31200 bit/s. The repeated run of 300 million
supervisor instructions exchanges 2242 blocks (44.84 seconds of audio),
with no retrain before the probe shuts down. A subsequent data soak verifies bidirectional application transfer, with
an early upstream error, as the text below describes. The training timing estimate of SmartLink converges near
zero. It does not drift by thousands of ppm.

The full native TRN1d of 20004 symbols also agrees with an independently generated
GPC scrambler, initialized to zero and supplied with ones, after a constant polarity
reversal. There are zero dropped/repeated/incorrect symbols. This result and the valid
Jd frames separate the correct raw DS0 generation from the reconstructed
SmartLink input that fails. The evidence identifies the receiver-channel model as the
failed boundary. It does not show a general defect of the CPU arithmetic.

`--smartlink-rx-reconstruction auto` now selects `tower` for V.90 and
`bandlimited` for V.34. To get the original failure again, select `bandlimited` explicitly.
The production generic resampler does not change.
The sections that follow keep the earlier examinations and controls.

- [Sustained V.90 result](../artifacts/imodem-slmodemd-v90-reconstruction-fixed-20261002/result.json)
- [SmartLink V.90 data-mode log](../artifacts/imodem-slmodemd-v90-reconstruction-fixed-20261002/slmodemd.log)
- [DIL entry capture](../artifacts/imodem-slmodemd-v90-reconstruction-fixed-20261002/detector-captures.json)
- [Independent whole-TRN1d comparison](../artifacts/imodem-slmodemd-v90-jd-bits-20261002/trn1-reference-comparison.json)

```sh
.venv/bin/python -m tools.probe_imodem_slmodemd \
  --protocol v90 --instructions 300000000 --capture-pc ca57 \
  --output artifacts/slmodemd-v90-working-new
```


The direct SmartLink comparison found an emulation bug: the emulator interpreted digital G.711
slot words as AC01 analogue codec commands. If we bypass the AC01
handling on the digital serial port, the receive corruption stops. With that
fix, **the original I-modem firmware and SmartLink both report CONNECT 33600**.
We did not patch the modem state or the qualification decisions.

The idle `d-modem` container of Tower supplies `/src/slmodemd/slmodemd -d9`.
`tools/probe_imodem_slmodemd.py` installs a temporary socket relay, configures
SmartLink as a V.34 caller, and answers with the original I-modem firmware.
Each exchange carries 160 G.711 samples at 8 kHz and 192 linear samples at
9.6 kHz. Streaming band-limited converters join the sample rates. SSH latency
does not advance either datapump. One 20 ms receive reserve prevents queue
underruns. The relay collects the debug and terminal logs and stops the temporary
processes. The existing container of Tower stays idle after this.

## Peer observations before the fix

SmartLink finds ANSam, completes V.8, selects V.34, and accepts the INFO0 of the
I-modem. Then it stays in `RX_PHASE1_CALL` and sends Tone B, until its training
timeout. The I-modem stays in coroutine `94ca`, transmit callback `9dbe`, and
receive callback `9bf6`. At the end, it returns NO CARRIER.

The first probe with unity gain gave a misleading INFO0 CRC failure. The existing
d-modem backend scales the incoming PCM by 0.25 during this handshake. With
that same scale, SmartLink accepts INFO0. An independent demodulation of the
I-modem output with unity gain recovers 140 consecutive INFO0 frames at one symbol
phase, with the body `21ff` and the CRC `9bf1`. Thus, that CRC warning was a gain error of the probe.
It was not evidence that the I-modem made incorrect CRCs.

We can also decode the INFO0 of the correctly scaled peer independently from the
G.711 samples sent to the I-modem: body `21ff`, CRC `9bf1`, 1200 Hz
carrier and 600 symbols/s. The three original overlay transfers of the I-modem
complete with zero program-word mismatches and no host overlay assists.

## Continuous native receive evidence

At the entry to `9bf6`, DP is 7, and the direct cell `@0f` is data `038f`.
This is the input that the native DPSK receive processing uses. The observer
records that value, the receive index at `0393`, and the native cycle count.
It drains the capture ring of 64 entries each 10,000 supervisor instructions,
independently of the coarser state checkpoints.

The final capture has 23,367 entries. All 23,366 adjacent receive indices
advance by exactly one, which includes the wraparound. The last 9,600 samples span
0.999875 seconds between their first and last samples. The empty receive
slots of the DSP and the DSC underruns are both zero. The sample stream is continuous.
Do not use the earlier sparse captures as continuous waveforms.

During the last second of steady tone:

| Measurement | Delivered G.711, decoded | Native detector input `038f` |
| --- | ---: | ---: |
| Rate | 8000 samples/s | 9600 samples/s |
| Minimum | -4092 | -21338 |
| Maximum | 4092 | 9268 |
| RMS | 2977.98 | 5497.78 |
| Dominant component | 1200 Hz | 1200 Hz plus large spurs |

The native waveform repeats exactly after 48 samples. Its RMS difference
after eight samples (the expected period of a 1200 Hz tone at 9600 samples/s)
is 7336.61. Its difference after 48 samples is zero. It has strong 800, 1600,
2400 and 3200 Hz components, and more components on a 200 Hz grid. The
largest non-fundamental component of the delivered tone is its much smaller
3600 Hz G.711 harmonic. Different internal amplitude scales alone cannot
explain these added frequencies.

The separate INFO-bit capture shows that `0394` goes again and again through the
signed values -151, +744 and -434 during steady Tone B. The native qualification
counter `03e1` never goes above five in that capture. This is below the comparison
against 15 at `9d37`. The flag `03e2` does not get its tone-qualified bit 3.
Earlier arithmetic checks with the actual captured FIR operands did not
show that their inputs were correct. When we followed the input back through
the native mu-law decoder, we found occasional zero codewords in place of
the clean bearer samples. The decoder itself agreed with each captured input.
The corruption occurred at the serial register read, before the conversion.

## Root cause and fix

`cpuregs_w(DXR)` called `codec_transmit()` unconditionally. That function
recognizes AC01 secondary-frame commands also when the ROM codec is disabled.
Thus, ordinary digital words such as `ffff` followed by `25ff` armed
a codec register read. On a later guest `cpuregs_r(DRR)`, the readback branch
replaced the digital word that the frame clock latched with a codec register value.
A zero register value became the mu-law code `00`, a large negative sample.
This added the observed periodic distortion. The firmware
processed the corrupted inputs correctly.

Digital mode now bypasses `codec_transmit()` on DXR writes, and it returns the
DRR word that the frame clock latched directly on guest reads. The analogue codec handling
continues through the existing branches. A regression sends the two legal
digital words above, then executes a guest DRR read, and verifies that the received
`b1ff` word stays. Diagnostic register peeks alone did not exercise the
defective guest-read branch.

The fixed call of 300 million instructions exchanged 2,242 audio blocks (44.84
seconds). The serial output of the I-modem and the terminal output of SmartLink both contain
`CONNECT 33600`. SmartLink reports V.34 data mode at 33,600 bit/s in each
direction, and it stays there until the probe stops. Its final NO CARRIER comes after
the relay shutdown. The three firmware overlay transfers still have zero
word mismatches. This run verifies the connection and the sustained carrier. But it
does not yet verify the transfer of application payload.

The regression selection of native C5x, I-modem, bridge-rate and resampler tests passes
all 131 tests.

## x2 and V.90 follow-up

After the fix of the digital port, we ran the existing analog Courier pair probe
for 300 million instructions for each endpoint, separately with `--protocol x2`
(S58=32) and `--protocol v90` (S58=1). We added different bidirectional payload
markers and overlay auditing. Neither run reports Hayes CONNECT, and neither
delivers its payload markers. All three overlay transfers of the I-modem in each
run have zero mismatches. The V.90 selection repeats the training. The x2
selection gets to more mailbox reports, but those reports alone do
not show a carrier. The analog peer clears its call before the run stops.

These are tests against a different emulated endpoint. They show that this
pair harness still fails. They do not isolate the remaining problem to the
I-modem. V.34 interoperability with Tower SmartLink is confirmed, but x2
and V.90 interoperability are not verified. The documented
host-mode support of the firmware is a different item from an observed successful connection.

- [x2 pair verdict and payload checks](../artifacts/imodem-analog-pair-x2-digital-codec-fix-20261002/summary.json)
- [V.90 pair verdict and payload checks](../artifacts/imodem-analog-pair-v90-digital-codec-fix-20261002/summary.json)

### V.90 with SmartLink

The peer probe now accepts `--protocol v90`. SmartLink receives
`AT+MS=90,1,28000,56000`, and the I-modem receives `ATS58=1&M0&B0`.
The fixed-gain run of 300 million instructions exchanges 2,242 blocks (44.84
seconds) without CONNECT on either terminal. The log of SmartLink confirms
`V90=1`, the remote V.90 capability, a digital connection and a PCM indication.
It builds the analog V.90 client, selects V.90 during training, and
gets to its PCM demodulator and the digital-impairment training. Three attempts
request retraining with `requested DP is 90`. This is a V.90 training
failure. It is not a run that was limited to V.34 by mistake. The final
NO CARRIER occurs when the probe stops the peer at the instruction limit.
We did not isolate the remaining failure mechanism.

An independent comparison against the NAC source bytes confirms that each
transport hash, each immediate loaded-program hash and each firmware hash is identical
for images 10, 11 and 6. This includes the paragraph padding of the loader. The final
resident image 5 (4,670 words) and the complete call image 6 (13,909 words) also
agree with the firmware with zero mismatches after all three failed attempts.
Only one call-overlay command occurs, `0002:a000` at 4.9079 seconds.
There are no overlay reloads during the subsequent retrains, and there are zero host
overlay assists. This excludes missing or corrupted bytes in those loads.
A full comparison of image 10 after image 6 is misleading, because their address
ranges overlap, and the remaining high program memory is shared workspace.

Native snapshots go into the transmit callback `c89d`, the receive callback `c855`
and the coroutine `c861`/`c86c` in each PCM attempt, before they return to the
handshake callbacks `9dbe`/`9bf6`. Thus, the next examination must be at
that training transition and the sample path. Do not repeat the
overlay transfer checks, which are already verified.

- [I-modem state and V.90 probe parameters](../artifacts/imodem-slmodemd-v90-digital-codec-fix-20261002/result.json)
- [SmartLink V.90 training log](../artifacts/imodem-slmodemd-v90-digital-codec-fix-20261002/slmodemd.log)
- [Independent firmware and overlay verification](../artifacts/imodem-slmodemd-v90-digital-codec-fix-20261002/overlay-verification.json)

The follow-up `c861` capture follows the first PCM attempt. From bearer
second 12 through 19, each transmitted octet is `31` or `b1`:
the two signs of one mu-law magnitude. There is no DIL
ladder with changing amplitude in this interval. The first two full seconds descramble to a
constant bit with the GPC recurrence (with sign inversion permitted). This agrees
with TRN1d. Later sign patterns change. Thus, do not call the full burst
unchanged TRN1d before you decode its later messages.

The native transmitter stage at `03c8` advances through `ca3e`, `ca44`,
then `cbd2`. It is not only stuck before the timed TRN1 stage stops.
SmartLink logs its Ja transmit stage and the TRN1 processing, and then it retrains.
Thus, the missing DIL is a useful observed symptom. But we must still decode the
downstream message/acknowledgement exchange that comes before it, before we
relate the failure to the DIL generation itself.

- [First-attempt PCM wait and codeword measurements](../artifacts/imodem-slmodemd-v90-ja-wait-20261002/pcm-wait-analysis.json)

### Supervisor involvement and DIL dispatch

A follow-up run of 170 million instructions filters the writes to the descriptor cell
`dcf5` and captures the entry to `ca57`, the DIL generator of the DSP. The block move
of the DSP at `a7d0` stores the received
descriptor (the write trace reports
its final instruction word `a7d1`): `dcf5 = 0090`, with `dcf6 = 7777`.
That is N=144, and packed segment lengths that decode to 120/120. The generator
reads those fields and the patterns that start at `dcf7` directly from DSP
memory. It does not get the descriptor through a supervisor command.
There are zero captures at the generator entry `ca57` in this run.

The supervisor supplies the V.90 power through command `0072:0b76` before
training, and DSP cell `ffdf` keeps `0b76`. The supervisor sends no more commands
between the load of the call overlay and the failed PCM attempt. The
mailbox stops with no pending reply and 118 acknowledgements. This does
not prove that all supervisor behavior is correct. But we saw no pending
DIL request that waits for its acknowledgement. The current evidence shows that
the DSP waits for the S signal of the peer before it goes into DIL. A subsequent
`a194` capture shows that zero incoming energy holds the S receive gate while
SmartLink transmits silence. This is the normal gate that V.90
9.3.1.5 specifies. It is not evidence of a missing supervisor command.

- [DIL descriptor writer and generator-entry audit](../artifacts/imodem-slmodemd-v90-dil-dispatch-20261002/dil-dispatch-analysis.json)

```sh
.venv/bin/python -m tools.probe_imodem_slmodemd \
  --protocol v90 --instructions 300000000 \
  --output artifacts/slmodemd-v90-new
```

## Artifacts and reproduction

- [Fixed call, including I-modem CONNECT](../artifacts/imodem-slmodemd-fixed-training-20261002/result.json)
- [Fixed peer terminal CONNECT](../artifacts/imodem-slmodemd-fixed-training-20261002/tty.log)
- [Fixed peer training and data-mode log](../artifacts/imodem-slmodemd-fixed-training-20261002/slmodemd.log)
- [Complete peer timeout and I-modem states](../artifacts/imodem-slmodemd-v34-training-20261002/result.json)
- [Peer debug log](../artifacts/imodem-slmodemd-v34-training-20261002/slmodemd.log)
- [Independent outgoing INFO0 checks](../artifacts/imodem-slmodemd-info0-20261002/info0-demod.json)
- [Independent incoming INFO0 checks](../artifacts/imodem-slmodemd-quarter-scale-20261002/info0-rx-demod.json)
- [Native INFO decisions](../artifacts/imodem-slmodemd-info-bits-20261002/detector-captures.json)
- [Continuous waveform measurements](../artifacts/imodem-slmodemd-continuous-rx-20261002/waveform-analysis.json)
- [Continuous native samples](../artifacts/imodem-slmodemd-continuous-rx-20261002/detector-captures.json)

The capture rows start with the native DSP instruction count, the native DSP cycle count,
the accumulator, DP, and carry. The cells in `capture-addresses.json` follow them.

```sh
.venv/bin/python -m tools.probe_imodem_slmodemd \
  --instructions 300000000 --output artifacts/slmodemd-training-new

.venv/bin/python -m tools.probe_imodem_slmodemd \
  --instructions 115000000 --capture-pc 9bf6 \
  --output artifacts/slmodemd-native-receive-new
```

Use a new output directory. The probe uses SmartLink RX gain 0.25 by default.

### Independent Jd decoding and polarity control

`tools/analyse_imodem_v90_signs.py` reads the raw mu-law sign
bits independently. It removes the differential encoding, and it descrambles with the delays 18 and 23.
The window from 15 to 18 seconds in `imodem-slmodemd-v90-jd-bits-20261002` contains
334 consecutive valid 72-bit Jd frames, exactly 72 samples apart.
Their data words are `ffff:f03f`. The independently calculated CRC `c2e5` agrees with
each frame. The frame sync, the start bits, the reserved bits, and the fill bits agree with
V.90 Table 13. The fields enable all downstream rates through 56 kbit/s,
16-point training/renegotiation constellations, and the maximum lookahead 3.

The TRN1d window from 12.5 to 13.5 seconds descrambles to 8,000 zeroes with the
recorded absolute polarity. If you reverse the polarity, these become ones. A control
run with the SmartLink receive gain `-0.25` still gives no DIL entry, and
SmartLink requests retrain. Its receive timing estimate again drifts to
about -2,227 ppm. Thus, the polarity alone does not explain the failure.
A valid Jd at the raw digital output does not prove that SmartLink decodes the
resampled audio correctly. The remaining suspect boundary is its path for PCM
reconstruction/equalizer/timing.

- [Independent sign and CRC results](../artifacts/imodem-slmodemd-v90-jd-bits-20261002/sign-decoding.json)
- [Opposite-polarity control](../artifacts/imodem-slmodemd-v90-inverted-polarity-20261002/result.json)
- [V.90 specification, Table 13 and clauses 9.3.1.5–9.3.2.9](https://www.itu.int/rec/dologin_pub.asp?id=T-REC-V.90-199809-I!!PDF-E&lang=e&type=items)

A second control changes only the cutoff constant of the resampler at runtime, from
0.98 to 1.0. This affects the two audio directions. It also gets to PCM training,
gives no DIL generator entries, and retrains. The timing estimate of SmartLink
changes much, from about -2,227 ppm to +12,796 ppm. This is
evidence that the receive timing is sensitive to the filter. It is not proof of a corrected
channel or of a physical clock-rate error. The production filter settings do not
change. New probe runs also save the exact 9.6 kHz PCM that goes to
SmartLink as `smartlink-rx.s16le`. Thus, we can audit the receiver boundary
without a reconstruction of its input from the digital capture.

- [Full-Nyquist cutoff control](../artifacts/imodem-slmodemd-v90-full-nyquist-20261002/channel-experiment.json)

## Bidirectional data soak

The V.90 run of one billion supervisor instructions exchanges 9242 blocks
(184.84 seconds of audio), and it stays in data mode for about 162.82
seconds after CONNECT. SmartLink reports V.90 rx34667/tx31200 and zero
retrain requests. The run stops at the instruction limit. Thus, this gives
a minimum hold time, not the maximum connection lifetime.

Each endpoint sends one numbered 86-byte ASCII packet each second, with
a deterministic body derived from SHA-256. We check the seven-bit terminal data
byte for byte. The SmartLink upstream terminal removes the 7E1
parity bit of the I-modem. This does not test arbitrary eight-bit binary data.

SmartLink to I-modem: all 162 packets agree exactly, a total of 13932 payload
bytes. I-modem to SmartLink: 161 of 162 packets agree exactly (13846 verified
bytes). In packet 1, the bytes `56 7f 19 7f` replace one `0`. Two more
bytes `7e 4e` occur between the intact packets 3 and 4. All subsequent numbered
packets agree, with no extra bytes between them. These early upstream
errors are not resolved. CONNECT and sustained carrier do not show
an application stream without errors. Error correction was disabled on the two
ends (`&M0`, `AT\N0%C0`) for this raw datapump check.

- [Bidirectional payload verdict and hold time](../artifacts/imodem-slmodemd-v90-data-soak-20261002/payload-analysis.json)
- [I-modem received application bytes](../artifacts/imodem-slmodemd-v90-data-soak-20261002/payload-received.bin)
- [SmartLink received terminal bytes](../artifacts/imodem-slmodemd-v90-data-soak-20261002/tty.log)

```sh
.venv/bin/python -m tools.probe_imodem_slmodemd \
  --protocol v90 --payload-check --instructions 1000000000 --capture-pc ca57 \
  --output artifacts/slmodemd-v90-data-new
.venv/bin/python -m tools.analyse_slmodemd_payload artifacts/slmodemd-v90-data-new
```

## V.42/LAPM error-corrected data soak

Error correction is enabled with I-modem `&M5&K0` and SmartLink
`AT\N4%C0`, with compression disabled. SmartLink gets to `EC_ESTAB`, logs
`ec = 1 (1)`, and then gets to `MODEM_ONLINE`. Thus, this is an error-corrected
connection, and not only an AT setting. V.90 still negotiates
downstream 34667 and upstream 31200 bit/s.

The first trial of one billion instructions receives all completed packets
exactly, without the startup corruption of raw mode. Its final upstream packet
goes into the queue only 0.24 seconds before the instruction limit, and it is absent at
shutdown. To remove this timing ambiguity, the repeated run limits the traffic to
150 packets in each direction, and it leaves about 12 seconds for the drain.

The repeated run stays in data mode for about 162.24 seconds (2m42s), with
zero retrain requests. Then it stops intentionally at the instruction limit.
The two directions receive all 150 packets exactly one time: 12900 bytes in each direction.
The full application stream agrees with the concatenation of the expected
packets in each direction, with no missing/corrupted/duplicate packets and
no extra bytes. This verifies the tested seven-bit ASCII application data.
It does not verify arbitrary eight-bit binary data or the maximum throughput.

- [Error-corrected, fully drained payload verdict](../artifacts/imodem-slmodemd-v90-lapm-drained-soak-20261002/payload-analysis.json)
- [Negotiation, terminal transcript and state](../artifacts/imodem-slmodemd-v90-lapm-drained-soak-20261002/result.json)
- [SmartLink LAPM establishment and online state](../artifacts/imodem-slmodemd-v90-lapm-drained-soak-20261002/slmodemd.log)

```sh
.venv/bin/python -m tools.probe_imodem_slmodemd \
  --protocol v90 --error-correction --payload-check --payload-packets 150 \
  --instructions 1000000000 --capture-pc ca57 \
  --output artifacts/slmodemd-v90-lapm-new
.venv/bin/python -m tools.analyse_slmodemd_payload artifacts/slmodemd-v90-lapm-new
```

## Faster V.90 reconstruction profile

A controlled reconstruction sweep keeps the original firmware, LAPM, gain
0.25, the serial clocks and the initial Sd/bar-Sd sinc path unchanged. Only the
length of the Lagrange interpolation in the training stage changes. If we double the training
gain with eight points, the rate does not increase.

| Interpolation points | Downstream | Upstream | Outcome |
| --- | --- | --- | --- |
| 8 | 34667 | 31200 | clean LAPM soak |
| 16 | 38667 | 31200 | clean short payload test |
| 32 | 44000 | 31200 | clean LAPM soak |
| 64 | no connection | — | 2 retrain requests |
| 128 | no connection | — | 3 retrain requests |

The 32-point profile increases the negotiated downstream rate by about
26.9%. SmartLink selects a 39-level constellation, not the original
12-level constellation. The check of 300 million instructions and the repeated
soak of one billion instructions both connect at 44000/31200. The soak stays in
data mode for 162.24 seconds, with zero retrains and zero reconstruction
clipping. Each complete application stream agrees exactly with all 150 expected
86-byte packets: 12900 bytes in each direction, without corruption, missing
packets, duplicates, or extra bytes. This is still a test of seven-bit application
correctness at light load. It is not a benchmark of the maximum throughput.

The V.90 probe now uses 32 points by default. To get the original Tower profile again, select
`--smartlink-interpolation-points 8`.
A longer interpolation is not always better for SmartLink. The 64-point and 128-point profiles
retrain before they connect, although there is zero clipping. This is an empirical
optimization of the receiver channel. It is not evidence of a new DSP CPU bug.

- [Full 44000-bit/s payload verification](../artifacts/imodem-slmodemd-v90-44000-lapm-soak-20261002/payload-analysis.json)
- [Speed sweep and reconstruction settings](../artifacts/imodem-slmodemd-v90-44000-lapm-soak-20261002/speed-sweep-summary.json)
- [Faster connection state and clipping counters](../artifacts/imodem-slmodemd-v90-44000-lapm-soak-20261002/result.json)
