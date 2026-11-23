# Full Apple audio-path audit

Main report: [docs/apple-audio-path-audit.md](../../docs/apple-audio-path-audit.md).

- `pcm-audit.json`: exact TX converter replay, payload levels/clipping, ADC
  snapshots and authoritative helper failure counters for nine captures.
- `live-180/`: new real Apple -> SIP I-modem call. Both complete 180-byte
  payloads and all five independent audio decodes pass. The full RTP capture
  nevertheless exposes four missing outgoing packets **after** the payload.
- `live-180/rtp-byte-audit.json`: timestamp-aware comparison to DSP TX;
  zero changed bytes across the PBX's shared packets in either direction.
- `previous-rtp-byte-audit.json`: analogous check of the preceding saved call,
  including its recorded reordered packets.
- `audio-device.json`, `route-to-pbx.txt`: read-only device/route observations.
- `helper-selftest.*`: native callback/reset/strict-failure checks, no hardware.
- `silent-retune-probe.*`: powered-line, **no digits dialed**, silence-only
  7200 -> 9600 host converter/transport smoke probe and hook release evidence.

Listen, at low volume (hardware TX left / raw RX right):

```sh
afplay artifacts/apple-audio-path-audit/live-180/caller/2903/apple-stereo.wav
```

This is not a claim of end-to-end reliability: the report distinguishes
successful payloads from actual packet delivery holes and the older host
underrun. No waveform gain, firmware decision or decoded modem byte is patched.
The actual electrical line voltage and post-DAC waveform have not been probed.
