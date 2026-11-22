# Original 3453 B/C firmware: bidirectional PCM and CONNECT

Follow-up: [exact terminal data and DTR disconnect](../3453-bell103-data-path-20261015/README.md)
are now demonstrated with settled peers. This artifact records the earlier
PCM/carrier/CONNECT milestone.

Offline control using two unchanged B/C normal 2.2.09 firmware peers, original
DSP code, opposite dedicated-line DIP presets, and a PCM-only socket. No forced
carrier/training/ACK, guest RAM/callback patches, or fabricated CONNECT result.
No hardware access or settings writes. Private settings/full flash are excluded.

## Result

Both guests print their own `CONNECT` after `AT&N1&U1`, `AT&L1`:

```
OK
OK
CONNECT
```

Both reach the instruction limit without errors (50 million each, 130 requested
common frames). Native codec RX peaks are A=3014 and B=3068. Line TX peaks are
A=11087 and B=10102. The four WAVs demonstrate actual audio in both directions;
RX WAVs tap peer TX before pair loss, not native ADC amplitude.

This establishes a firmware-driven low-rate carrier/control transition and
bidirectional wire audio. **It does not by itself establish bidirectional DTE
bytes or disconnect.** The first separate small-payload control left the data
queued at the DTE harness; investigation continues without sending payloads
outside the firmware/DSP path.

## Newly demonstrated interrupt fault

After the originate DSP qualifies the answering waveform, it enters original
Bell-103 setup at `4486`, installs TX/RX callbacks `45F2/4538`, and emits status
`003D`, `0004`, `0028`. These reports are not all failures. Before the correction,
native TX produced a short burst but the connection reset before reverse wire
audio was delivered.

The original supervisor's tag-28 handler at BC `6D877` changes the mailbox
interrupt vector to `675B:774E` (physical `6ECFE`). This handler returns at
**BC `6ED9A` / C `6EEFA`**, rather than the initial mailbox ISR's return. The
emulator failed to release its in-service latch at this new return and stopped
servicing the mailbox normally. Registering the genuine return, with the guarded
B/C-to-C PC mapping, restores service and both firmware-generated CONNECTs.
Neither vector nor callback is injected by the emulator; the original guest
chooses them. The unchanged handler ends `POP ES; POPA; MOV [FF02],8000; IRET`,
which is checked against both public normal captures by regression tests.

The preceding independent correction for origin-zero recovery downloads is
in [the recovery trace](../3453-download-recovery-trace-20261015/README.md).
Transfer verification remains strict throughout.

## Evidence and reproduction

`result.json` explicitly selects control/serial/DSP/codec/line-service fields
from the paired result. Raw standard PC traces and stack/SI memory-like fields
are deliberately excluded. `audio-analysis.json` is a 4096-point Hann FFT of
selected WAV windows, reproducible without third-party numerical libraries:

```
.venv/bin/python tools/analyze_3453_peer_audio.py \
  artifacts/3453-native-bell103-link-20261015
```

A TX changes from about 2100 Hz (1 s) to 2250 Hz (3 s), then the later FSK
waveform. B TX is nonzero by 5 s with a dominant 1269.53-Hz component. Each
corresponding peer RX recording has the same dominant component.

```
./courier link "$PRIVATE_BC_FLASH" --with-dsp --line-audio-only \
  --tick-source dsp --instructions 50000000 --line-frames 130 \
  --a-at 'AT&N1&U1' --a-at 'AT&L1' \
  --b-at 'AT&N1&U1' --b-at 'AT&L1' \
  --socket /tmp/courier-bc-online.sock --audio-dir /tmp/bc-online-audio --summary
```

The 3453/map/CLI/native aggregate after the recovery/ISR corrections passed
**120 tests in 493.60 seconds**. A further online-UART correction and public-image
paired regression are under validation; this count does not cover those later
changes yet. No commit is claimed.
