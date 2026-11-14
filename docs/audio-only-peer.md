# Two independent firmware instances over PCM

The `link` command starts two separate emulator processes. Add
`--line-audio-only` to exchange only a sample count and signed little-endian
PCM16 at 8,000 samples/second. The two ends must select this protocol. Each
side resamples between the common wire rate and the codec rate that its
firmware programs. Frames contain 100 ms of audio and synchronize the two
processes. The socket advances on the conversion-frame clock of each codec,
and this includes silent frames. CPU instruction counts do not set the
quantity of audio that the processes exchange.

```sh
./courier link artifacts/courier-board-21210-capture-403/courier-board.rom \
  --with-dsp --line-audio-only --socket /tmp/courier-audio.sock \
  --audio-dir artifacts/audio-only-peer-02/audio \
  --nvram-fixture idsdl403 --board-id 7 --dip-preset default --tick-ms 5 \
  --a-at ATX0 --a-at ATDT5551234 --b-at ATA \
  --instructions 85000000 --summary
```

Side A first sets `ATX0`, then sends `ATDT5551234`. Side B answers with `ATA`.
`ATX0` disables the wait for the dial tone of the exchange. This direct
connection has no telephone exchange, ringing or dial tone. Use explicit A/B
commands: the older default of `link` is `ATA` on the two sides. The default
DIP preset in the command above also prevents the carrier-detect override of
the older dedicated-line preset.

For processes that you start separately, use `courier run` with the same ROM,
fixture, timer and board options on the two processes. Give `--line-link
/tmp/courier-audio.sock --line-audio-only` to the two processes, `--line-listen --at ATX0 --at ATDT5551234`
to the first, and `--at ATA` to the second. The socket listener role does not
set the originate/answer role of the modem. Start the second process in 30
seconds or less. On a standalone instance, use `--line-record PREFIX` to
record `PREFIX-tx.wav` and `PREFIX-rx.wav`. `link --audio-dir DIR` gives the
prefixes `a` and `b`. These recordings are at the socket boundary, before the
local hook gate of the receiving modem. They are mono PCM16 WAV files at 8 kHz.

Audio-only mode does not send CPU instruction counts, hook state, ring state,
decoded bits or modem commands. The local relay state gates the local audio.
The mode disables the seizure shortcuts of the command parser, synthetic
mailbox replies, host-driven entry to training, and synthetic carrier/CONNECT
events. Firmware mailbox traffic continues to go through the emulated
hardware registers.

## Verified result and remaining failure

`artifacts/audio-only-peer-01/summary.json` records the 4.03d pair above:
40 million CPU instructions for each side, and 78 frames and 62,400 samples
sent and received by each side. There are no socket errors and no synthetic
connection events. The two CPUs seize their local relay. Their DSP report
tags are different (0008 on originate, 000a on answer), but neither side
receives nonzero audio in this run. That short run stopped immediately after
the commands started to execute, at about instruction 38 million. Thus the
first conclusion, that training audio never got to the peer, was too early.

`artifacts/audio-only-peer-02/before.json` repeats the original CPU-paced
transport for 150 million instructions with plain `ATDT5551234` and `ATA`.
The first answer audio arrives at about instruction 40.9 million, after the
end of the earlier run. The caller returns `NO DIAL TONE`. The transmit
backlog of the answerer increases to 115,429 line samples (14.4 seconds).

The codec-paced run with `ATX0` before `ATDT5551234` delivers audio in the two
directions. Its largest transmit backlog is 21 samples (2.6 ms). The socket
recordings decode as `5551234` at the receive side of the answerer. The
answerer sends a tone near 2100 Hz and, after it, a changing waveform. These
results verify the DTMF and waveform transport, **not completed training or
data transfer**: neither firmware reports `CONNECT` in the
150-million-instruction run.

The frame trace in `dsp_bridge.line.audio_trace` of each side shows these
items separately: the transmit peak before the hook, the actual
transmit/receive peaks of the socket, the codec-input peak, and the transmit
backlog. This makes it possible to distinguish buffering from hook muting.
The trace keeps the latest 512 frames.

The recorded run of 85 million instructions is in `recorded-run.json`, with
waveform checks in `audio-analysis.json`. Each received PCM byte agrees with
the transmitted stream of its peer. The caller sends one last 100 ms frame
after the answerer gets to its instruction limit. EOF at that point is the
test shutdown. `audio/call-excerpt.wav` contains seconds 8–18, with the caller
on the left channel and the answerer on the right. The four full recordings
stay mono.

The older link mode is still available without the flag. This includes its
hook/ring side channel and its behavioral call shortcuts. Its CONNECT result
is not evidence that the audio-only pair has trained.
