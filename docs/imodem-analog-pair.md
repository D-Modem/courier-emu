# I-modem against an emulated analogue Courier

The current path is verified at **41333/x2/LAPM** on the analog Courier.
The two application markers arrive, and the server mode of the I-modem is enabled.
Refer to [the 2026-10-03 results and reproduction](imodem-analog-x2-20261003.md).
The experiments below record the earlier examination of the transport and the firmware.

## 2026-10-02: x2 with V.8 and high-power constellation

After the successful digital I-modem pair at 64000/x2/LAPM, we tested the
analogue Courier as caller with `S27=1S54=0S58=32&A3&B0`, and
the I-modem as server with `S54=0S58=48&A3&B0`. We used the original firmware and
the native DSPs, with the foreground overlay assistance disabled.

The run of 300M instructions establishes the ISDN call of the I-modem, answers the
analogue line, and exchanges 278400 bearer octets in each direction. Neither terminal
reports modem CONNECT, and neither application marker arrives. There are
no reported CPU errors or I-modem DSP errors. Thus, the digital pair that operates
does not yet show an x2 connection with the emulator of the analogue Courier.

[Verification](../artifacts/imodem-analog-pair-x2-v8-high-power-20261002/verification.json)
and [full capture](../artifacts/imodem-analog-pair-x2-v8-high-power-20261002/result.json).

## 2026-10-02: remove host command handling from the default path

The foreground overlay acknowledgement described below was an execution of a DSP command handler
on the host side. It was not an ASIC emulation. It is now disabled
by default. `ImodemDsp(foreground_overlay_assist=True)` and the
`--assist-overlay-command` of the pair probe keep it only as an explicit diagnostic option.
The endpoint reports the setting and the number of assisted commands.

With the current core, the firmware without the assist gets to image 6 and
`0034:0005` at 7.8246 seconds. Its live completion audit verifies all 13,912
transferred words at `a000`. This includes the three padding words of the supervisor.
The destination advances to `d658`. The host assist count is zero.
Thus, the old handoff bypass is not necessary now. We did not isolate the exact change that
made it unnecessary.

The Bell 103 control without the assist still returns the two CONNECT results and
sends the two different payloads. These runs do not establish V.34 carrier.

- [Unassisted overlay run](../artifacts/imodem-analog-pair-unassisted-overlay-20261002/result.json)
- [Unassisted Bell 103 control](../artifacts/imodem-analog-pair-bell103-unassisted-20261002/summary.json)

The native pair probe does not enable negotiation tones, forced carrier reports, or the analogue `&T1` acquisition
assist. The active device models
still supply clocks, interrupts and holding-register handshakes. Specifically,
the IRQ13 and RTOS IRQ11 service cadences of the I-modem supervisor are modeled
from instruction counts, and not from the captured interrupt timing of the board. They
are assumptions that we must verify. They do not give permission to patch the guest state.

## 2026-10-02: regression for the first failed transition

The original `imodem-analog-pair-20261001/result.json` and the September
`imodem-pair-connect-fix-20260930` control show the same loader failure.
Q.931 establishes the telephone call, and the audio flows. Neither failed run
reports a Hayes modem `CONNECT`. The September pair exchanges 176,000
mu-law octets in each direction (220 frames, 22 seconds), with no PCM receive
underruns. Its V.8 replies request image 6 (`0047:0006`), followed by
`0002:a000` at 19.5405 seconds on originate and 19.6150 on answer.
Two seconds later, each supervisor repeats the command, sends `0083:0083`,
and loads the startup images `d100`/`9260` again. Originate prints `NO CARRIER`
at instruction 143,707,136, and then sends Q.931 DISCONNECT at 144,158,720.
Answer prints it at 161,055,744 and disconnects at 161,505,280. Cause 16
is the normal cleanup of the supervisor after the modem failure. The socket-close error of the peer
comes after that failure. It does not cause it.

The October analogue pair gets to the same image-6 request earlier,
at 5.4229 seconds. It repeats the timeout/reset sequence from 7.4150
seconds onward. Its I-modem call stays active at the capture limit,
in spite of those resets. This capture stops without a Hayes result on either end.
The zero `bri.media.rx_delivered` counter in that capture does not mean that
the digital endpoint received no samples. This peer sends data to the DSC directly,
and its `from_line` counter records 277,600 octets. The mailbox trace
shows that the negotiation gets to V.8 before the loader stops.

The first failed transition is from the pre-download strobe of the supervisor to
the command-2 acknowledgement of the DSP. The focused endpoint correction in
the working tree copies the destination to `0bff`, and clears PA7 `0700`
together with command bit 0. It leaves the final completion strobe to native
DSP execution, and it returns the startup reloads to the resident dispatcher.
The overlay ownership now also clears when the DSP instance closes. Thus,
a fresh bootstrap does not get the previous foreground shortcut.

The automated handshake regression executes the original resident handler
at `840f..8413` as its reference. This includes the preservation of the PA7
bits that are not related. The paired-firmware regression is:

```sh
.venv/bin/python tools/probe_imodem_pair.py \
  --instructions 220000000 --check-keepalive \
  --output artifacts/imodem-pair-keepalive-regression-new
```

`--check-keepalive` requires these conditions: active B1 calls, a minimum of 250 exchanged frames,
the image-6 handoff and the final download strobe, no DSP reset/timeouts, no
receive underruns, and no guest clearing or `NO CARRIER`. The two sides of the September
control fail this check. The corrected
[paired regression](../artifacts/imodem-pair-keepalive-regression-20261002/keepalive-check.json)
passes on the two sides at 220M instructions, with 338 exchanged frames and
zero underruns. This verifies that the call continues after the original teardown window.
It does not claim V.34 carrier acquisition. The Bell 103 evidence below
separately shows a real modem connection and payload delivery.

## 2026-10-01: connected with terminal data in both directions

The two original firmware supervisors return Hayes `CONNECT` with Bell 103 at
300 bps. The I-modem keeps its ISDN call active, and it transmits the Bell 103
answer mark. The analogue Courier transmits the originate mark. This is a
native DSP connection, with no injected carrier result.
The [final preset verification](../artifacts/imodem-analog-pair-connected-data-20261001/summary.json)
records the two CONNECT results, an active I-modem call, and the two data-delivery
verdicts as true. The I-modem receives a 75-character Courier marker. The
analogue Courier receives a different 74-character I-modem marker.

```sh
.venv/bin/python tools/probe_imodem_analog_pair.py \
  --protocol bell103 --instructions 200000000 \
  --analog-send COURIER-12345 --imodem-send IMODEM-67890 \
  --output artifacts/imodem-analog-pair-connected-new
```

The preset sets `&N1`, selects `B1`, disables V.8 (`S54=192`) and V.34/V.FC
(`S56=192`), selects normal mode (`&M0`), and follows the terminal rate of the line
(`&B0`) on the two ends. The originating
Courier also uses `S27=1`. The first test with carrier only kept the
active call of the I-modem for the full run of 350M instructions, about 45 seconds of bearer
audio. The analogue worker reports `NO CARRIER` when the probe closes the
socket of the I-modem at the instruction limit.

The failed earlier payload test showed an ASIC data window of the I-modem that was not wired.
CPU ports `40h..56h` carry six words through DSP ports `58h..5dh`, separately
in each direction. CPU `18h` commits outgoing words and `1ah` acknowledges
incoming words. DSP PA6 holds the occupancy bits. The I-modem model
continued to return the boot status from `18h`, returned zero from `1ah`, and did
not show the received words. It now implements the same bank handshake as the
analogue model. Also, the native DSP output registers stay separate from the input
registers. The two supervisors move the payload themselves.

The analogue DTE uses 7E1. Normal mode keeps the parity bits of the remote terminal
in the payload. Thus, the report decodes its raw `serial_hex` as seven-bit
characters. The original byte stream stays in `result.json`. The probe
waits for the terminating LF of CONNECT before it sends the payload. If it sends
earlier, the answer sequence of the I-modem aborts.

The original fixed DTE setting of 9600 bps passed the short markers, but it corrupted
the longer transfer from the Courier to the I-modem. The native analogue transmit audio
decoded independently to the full expected message. Changes of the line level did
not always fix the reception. When we followed the link rate with `&B0`, the
full messages arrived in the two directions at the default line level, and the
final preset run was successful again. This is part of the Bell 103 preset.
More examination of DTE operation at a fixed rate is necessary.

V.34 carrier is still not resolved. These changes did not give a verified data connection:
lower audio levels, a shorter receive cushion of the bearer,
a local hybrid-return experiment, V.32-only/V.22bis controls, and an
older analogue firmware control.
We reverted the buffering and hybrid experiments. The codec history now
records clock changes also when the divider registers stay identical. This confirms
the change from 9.6 kHz to 10.2667 kHz after symbol-rate index 5. An offline execution
of the native mu-law decoder of the I-modem agrees with all 256 reference codewords.

The [2026-10-02 audio clock audit](imodem-audio-clock-continuity.md) identifies
and corrects the time compression of the receive FIFO and the phase jumps of the resampler during
retuning. The corrected V.34 replay has zero live receive gaps, but still no
modem CONNECT. Bell 103 keeps delivery in the two directions.

## Earlier overlay blocker and V.34 investigation

The local pair establishes a 3.1 kHz mu-law ISDN bearer and exchanges audio.
The V.34 runs do **not yet establish a modem carrier**: neither side returns a Hayes
`CONNECT`. Q.931 `CONNECT`, `BCH_ENABLED`, and the `answered` state of the socket
describe the telephone call. They do not describe successful modem training.

The pair runs the original `Ie030002.nac` supervisor and C51 firmware against
the captured 7.4.16 / DSP 3.1.2 analogue Courier image. This probe does not inject a
successful-carrier reply or a data connection.

### The repaired blocker

The loader of the supervisor at `b152c` first strobes port `1e` with `4`. Then it
sends mailbox command `0002:a000`. At `b1545`, it waits until bit 2 of the
CPU-facing status is ready, before it publishes download words.

The existing foreground overlay shortcut acknowledged only PA7 bit 0.
Thus, PA7 bit 10 stayed set, the supervisor waited two seconds,
and the loader reset the DSP. After that first failure, the kept call mode
also applied the shortcut to the startup pair, and this caused repeated reloads.

The shortcut now agrees with the acknowledgement in the resident handler at
`840f..8414`. It writes the destination cell `0bff` and clears PA7 `0700`, plus
the command-consumed bit. A startup `0002:d100` stops call mode. The final
download strobe goes to the DSP, and the shortcut does not rewind its destination or
erase its completion bit.

In the corrected run of 200M instructions, the DSP loads image 6 at `a000`:
**all 13,909 words agree with the firmware**, with zero mismatches. The two hashes are
`577e8280b68ae40287acb1b93f25900645161db3ec008652462ff229174c870d`.
The I-modem PCM endpoint reports zero receive underruns. The last mailbox
exchange is still the V.8 result `0047:0006`, followed by `0002:a000`. No
carrier result follows in that run.

The evidence is kept in
[the native-completion run](../artifacts/imodem-analog-pair-native-finish-20261001/result.json),
[overlay verification](../artifacts/imodem-analog-pair-native-finish-20261001/overlay-verification.json),
and the `dsp-program.bin`, G.711 captures, WAVs and checkpoints of that directory.
A longer run of 400M instructions with the initial correction of the acknowledgement
stopped with analogue `NO CARRIER`. It occurred before the correction of the final strobe.
The byte-exact control run with two I-modems also loads `a000`, but it has no Hayes
`CONNECT` at 200M instructions.

The final V.34-only run with the two handshake corrections gets to one more DSP
reply, `0034:0005` at 16.1234 seconds of received bearer audio. But it still has
no Hayes `CONNECT` at 220M instructions. Its compact
[summary](../artifacts/imodem-analog-pair-v34-fixed-20261001/summary.json)
records that result. A trace of the reply producer at `9b98..9b9d` shows that
tag `34` carries `@5b`, the symbol-rate index. The code that follows uses that
index to select rate-dependent tables. Thus, `0034:0005` is a parameter
report during training. It is not an indication of a successful carrier, and it is not an identified
failure reason. We did not yet trace which caller made it in this run.

At the end state, its program comparison is different from the original image in the
contiguous range `ce00..d654`. This later comparison is not a transfer
checksum. We do not yet know if V.34 operation legitimately uses that range again
or if it is corrupted. The zero-mismatch observation above
applies specifically to the earlier run with the default protocol.

### Reproduce and inspect

```sh
.venv/bin/python tools/probe_imodem_analog_pair.py \
  --protocol v34 --instructions 220000000 \
  --analog-to-imodem-db -3 --imodem-to-analog-db -3 \
  --output artifacts/imodem-analog-pair-v34-new
```

The probe needs permission to bind a local Unix socket. It writes:

- `summary.json`: serial results and explicit carrier verdicts on the two sides;
- `result.json`: full supervisor, DSP and bearer diagnostics;
- `checkpoints.json`: periodic DSP state and recent mailbox traffic;
- `dsp-program.bin`: the program memory that is actually present at the end;
- `dsp-data.bin`: data memory at the end;
- `imodem-{tx,rx}.g711` and `analog-{tx,rx}.wav`: audio in the two directions.

`--protocol x2` sets S58 to 32 on the two sides. `v90` sets 1, and `v34` sets 33.
The previous x2/V.90 test settings on the analogue side were reversed. These bits
**disable** their related PCM protocols.

`--speed-index 1` sets 300 bps on the two sides for a control at a lower speed.
That corrected dial-order run also establishes the audio call, but it does not
return `CONNECT` at 240M instructions. Its I-modem mailbox stops at
`0071:0002` / `004a:0000`, without an image-6 request.

The remaining examination is the phase transition of the datapump and the carrier
acquisition after V.8. The verified overlay transfer and the absence of receive
underruns remove those two specific failure modes from the corrected run.
They do not prove that the DSP arithmetic, the waveform timing or the training are correct.
