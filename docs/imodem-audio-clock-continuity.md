# I-modem analogue-pair audio clock audit, 2026-10-02

The audio path had confirmed faults at clock transitions. The fix of the
overlay loader kept the ISDN call alive, but it did not give a V.34 carrier.
This audit follows waveform samples through the boundary of the analogue codec.

## Later audit: transmit batches crossing clock changes

Before, `_take_line_audio` drained all pending DAC samples and assigned
the final sample rate of the codec to the full batch. Native DSP execution can
change the rate in that batch. If we only keep the FIR history, we cannot fix
the incorrect timestamps that result. The resampler got the earlier samples
as if they had been made at the later rate.

The native core now records each DAC clock change with the index of its first sample
and its period in DSP cycles. The bridge splits a drained batch at those
indices, and it converts each segment at its original clock. This also uses
the actual modeled frame period, and not the nominal divider rate, when
the integer rounding of DSP cycles makes them different. These events only describe the
hardware output. They do not change the firmware state, and they do not make modem signals.

The corrected V.34 replay of 230M instructions exercises **seven batches that
cross retunes**. It keeps the count of the host overlay assist at zero, and it records no
live gaps in the analogue receive path. It gets to `0034:0005` at 7.1651 seconds, then
`0006:0000` at 13.0126 seconds. **There is still no modem CONNECT.**

The [transport comparison](../artifacts/imodem-analog-pair-v34-tx-clock-20261002/transport-verification.json)
checks the line WAVs and bearer codewords that we saved independently:

- Analogue to I-modem: all 166,061 captured receive codewords agree with the
  recorded transmit samples of the line after the specified gain and mu-law
  encoding. There are zero mismatches at one fixed setup offset.
- I-modem to analogue: 149,868 samples after the initial 16,000 bearer
  samples agree with the recorded analogue receive line after mu-law decoding
  and the specified gain. There are zero mismatches at one fixed setup offset.

This verifies the socket delivery and the conversion at the recorded boundaries.
It does not verify the complete analogue ADC/filter response of the DSP. The offsets include
recording time from before the call. They are not measurements of the end-to-end latency.

The new independent regression with a continuous tone checks a 3 kHz waveform
across a mixed 9.6/10.2667 kHz transmit batch. This includes the boundary, and the check does not
fit the phase again. A native regression verifies the indexed DAC clock changes,
and that a reset clears them. The wider selection of C5x, I-modem, bridge and resampler tests
passes 122 tests.

The [Bell 103 control](../artifacts/imodem-analog-pair-bell103-tx-clock-20261002/summary.json)
still connects and sends the two different payloads.

To do the corrected V.34 run again:

```sh
.venv/bin/python -m tools.probe_imodem_analog_pair --protocol v34 \
  --instructions 230000000 --audit-overlays \
  --output artifacts/tx-clock-audit-new
```

## Confirmed faults and corrections

The Python resampler reset its fractional input position each time the
output rate changed. For a continuous 8 kHz source, this puts a phase
step into the receive waveform of the codec. On transmit, a change of the input rate
also caused the resampler to interpret the kept history at the new sample spacing. The
resampler now keeps the fractional position for a change of the output clock, and it
keeps the physical timestamps across a change of the input clock. Uniform windows
use the cached polyphase kernel. Windows that cross a clock edge use sinc
weights at the actual sample times.

The independent 3 kHz tone comparison in
[tone-continuity.json](../artifacts/imodem-audio-clock-audit-20261002/tone-continuity.json)
compares against one continuous phase reference. It does not fit a new
phase after a retune. After the two rate changes, the receive RMS error decreased from 5,411/9,097 PCM units
to 4.75/4.46. The transmit error decreased from
5,938/13,829 to 9.10/11.64. These are measurements of the waveform continuity.
They are not estimates of the noise floor of a modem channel or of the possible data rate.
The regressions include 1, 3, and 3.7 kHz, independence from the scheduler chunk, and
a pass through an equal-rate state that does not drop the established FIR delay.

Also, the native DAC clock returned zero after a frame without a new DSP
write, but the model must hold the sample. It now keeps
the latest primary DAC word until a new word replaces it. A native regression
checks consecutive primary edges and the replacement by a new word.

A more important fault: the analogue receive FIFO held a full frame that was already
converted at the previous rate of the codec. At a clock change from 7.2 to 9.6 kHz,
the ADC used that waveform faster than its original time grid. The
[instrumented run before the fix](../artifacts/imodem-analog-pair-v34-live-gaps-20261002/result.json)
records **148 missing samples at line frame 299**, during the connected
call. The zero-underrun counter of the I-modem did not monitor this analogue FIFO.

The socket receive path now puts its original 8 kHz samples in a queue, and it does a
band-limited conversion at each native ADC edge. The FIFO keeps its line
time grid across codec retunes. A receive cushion is added only when
that input stream starts. Native regressions compare the actual ADC words
with continuous tones at the 7.2, 9.6, and 10.2667 kHz settings. They require more
than 60 dB SNR against the fixed-phase reference. They also check that the FIFO
consumption depends on the elapsed line time and not on the ADC sample count.
Explicit codec-rate inputs and other legacy paths keep `queue_codec_rx`.

## Firmware verification and remaining failure

The [validation report](../artifacts/imodem-audio-clock-audit-20261002/validation.json)
records the paired runs and all 159 tests, which pass. To do the V.34 check again:

```sh
.venv/bin/python tools/probe_imodem_analog_pair.py \
  --protocol v34 --instructions 300000000 \
  --analog-to-imodem-db -3 --imodem-to-analog-db -3 \
  --output artifacts/imodem-analog-pair-v34-audio-new
```

The corrected run of 300M instructions keeps the ISDN call active. It records
zero live gaps in the analogue receive path and zero receive underruns of the I-modem.
**Neither firmware reports V.34 modem CONNECT.** Its mailbox stops at the
V.8 image-6 request and `0002:a000`. It does not give the later
symbol-rate reports that we saw in the receive-phase-only experiment. When we remove the
waveform discontinuities, the training behavior changes, but the V.34 path is not yet
successful. More examination of the DSP/training state is
necessary. This audit does not show that all aspects of the audio or DSP
execution are now correct.

The Bell 103 control with these same audio changes reports Hayes CONNECT
on the two sides, an active ISDN call, delivery of the two different terminal
markers, and zero live receive gaps. The analogue NO CARRIER at the end
of that control occurs because the I-modem worker closes its socket at the
instruction limit.

`codec_rx_empty_frames` in the codec history includes empty conversions
before the call setup. `line_service.rx_empty_connected` and `rx_gap_events`
count gaps only while the call is answered and its socket is connected.
They do not include the expected shutdown of the worker, and they record the frame of each live gap.
