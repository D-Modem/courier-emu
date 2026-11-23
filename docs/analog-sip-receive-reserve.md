# Analog SIP receive-block reserve

`courier_emu.ata.SipLine` now primes a 40-ms receive reserve in addition to
one full requested codec block before starting received audio. The RTP
playout layer schedules samples by wall time, whereas the analog emulator
consumes whole blocks. Previously a short block was played immediately and
padded with silence, even when all RTP samples arrived intact but their
handoff crossed a service boundary. That damages modem training/data.

The adapter retains the start of the received waveform during priming.
A later [block-priming correction](sip-exchange-block-priming.md) ensures the
reserve covers the full paced service block even when the exchange renders
it in smaller slices; direct-helper tests alone missed that distinction. Once
started, it consumes samples in order without interpolation, repetition or
loss. A genuine shortage is still padded and counted, then the reserve is
rebuilt. Transmit audio continues during receive priming. Every new connected
call resets the receive priming state. No carrier timeout or firmware state
is changed.

The reserve adds latency; it does not correct remote clock drift, packet loss,
CPU overload, or errors in the modem datapump. It does not change the I-modem
`BearerSipLine`, which already has separate receive buffering, or the Apple
USB audio path. Offline `LinePeerSession` peers retain unbuffered behavior.
Programmatic callers may select `SipLine(..., receive_buffer_ms=0)` for an
unbuffered comparison; the default is 40 ms.

## Diagnostics

The line status retains total `underrun_samples` (including startup silence)
and adds:

- `startup_underrun_samples`: silence before the first received audio;
- `active_underrun_samples`: shortages/rebuffering after audio has started;
- `receive_rebuffers`: active stream shortages triggering reprime;
- `receive_buffer_samples`: configured additional reserve at line rate;
- `receive_buffered_samples`: current queued receive samples.

Counters are cumulative across calls; priming state is per call. These
adapter counters are distinct from RTP playout missing/late-packet counters.

## Validation

`tests/test_analog_sip_receive_reserve.py` tests waveform retention, outage
accounting/recovery, new-call reset, offline/zero-reserve behavior and a
simulated two-minute stream with +/-20-ms block delivery variation. Every
input sample is accounted for in exact order, with zero active underruns and
a bounded backlog. An unbuffered control demonstrates an active waveform gap
under the same variation. Resampling is replaced with an identity operation
in these scheduling tests; this is not a full modem connection test.

98 focused tests passed:

```
.venv/bin/python -m pytest -q \
  tests/test_analog_sip_receive_reserve.py tests/test_sip*.py \
  tests/test_rtp*.py tests/test_bearer_sip_playout.py \
  tests/test_line_presend.py tests/test_bridge_acquisition.py \
  tests/test_resample_rate_changes.py
```

A separate `tests/test_bridge_audio_rates.py` run failed in
`test_audio_line_frames_are_paced_at_codec_rate`: its `__new__`-constructed
bridge lacks `line` when `_service_line` accesses it. That file/path was not
changed by this correction. No full-suite pass is claimed.

The initial reserve-only change had no live-call qualification. Subsequent
bounded 7900/7910 Asterisk checks did not reach observed modem carrier; see
[the independent receive-clock follow-up](sip-independent-receive-clock.md)
for actual outcomes, additional queue bounds and current diagnostics. Qualify
longer connects using actual duplex payload equality, firmware error counters,
and RTP delivery/playout evidence; simulated clean block handoff alone is not
proof of sustained modem reliability.
