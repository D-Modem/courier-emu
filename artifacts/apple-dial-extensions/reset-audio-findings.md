# Sound and underrun analysis

**Update:** the reset/control fix is implemented. The [6311 retry](../apple-reset-continuity/README.md)
returns cleanly with `NO CARRIER` and zero active gaps/overflows. The analysis
below describes the earlier failing implementation.

No new calls were placed for this analysis.

## Listening copies

Each extension directory now has `tx-listen.wav` and `rx-listen.wav`: mono
8000 Hz PCM, off-hook samples only, resampled using each recorded codec rate
and attenuated by 12 dB for listening. These are not calibrated recordings of
line voltage; RX was already DC-blocked/rate-converted and is visibly clipped.
Attenuation does not repair that clipping. On-hook startup pauses are omitted.

Codec TX independently decodes as 6311 and 6312 respectively. RX has strong,
distorted low-frequency tone energy: a Hann-windowed 300–600 Hz scan finds
398–399 Hz in both recordings at 1, 5, 10 and 20 seconds after seizure. Earlier
nominal-bin analysis after DTMF finds very little 2100 Hz energy. This supports
"dialing plus a rough approximately 400 Hz line tone," not a normal modem
answer/training sequence. It is not sufficient to label the remote state as
busy, unobtainable or no-answer.

## Why the helper underruns

Final codec service trace entries:

| Extension | Last off-hook request to next (on-hook) request |
|---|---:|
| 6311 | 177.678 ms |
| 6312 | 170.690 ms |

The HAL block is 512 samples and the helper primes two blocks at 10286 Hz:
1024 / 10286 = 99.55 ms. Actual queued audio at reset can be less than that.
The gap exceeds the output cushion. The helper still considers the line active
until it receives the on-hook request, so its render callback correctly detects
an empty queue and invokes the current fail-closed policy. The on-hook request
arrives too late; helper cleanup releases and verifies the physical hook.

The bridge resets `active` and `launched` when the DSP is reset.
`clock_x86` returns before `_service_line` while the DSP is inactive/unlaunched.
Physical codec service additionally requires a programmed codec rate and waits
for codec samples or its fallback timer. Thus **hardware PCM and hook control
are incorrectly coupled to DSP execution/availability**, even though the real
DAA/audio interface must keep running independently. A legitimate DSP reset
becomes a physical transport starvation event.

This is distinct from sustained compute throughput: the optimized firmware
previously serviced a long off-hook hold without a gap; these failures occur at
repeatable reset/hang-up boundaries with the emulated DAA already returning
on-hook. It does not prove there are no other possible throughput limits.

The required fix is to keep the hardware audio/control pump alive across DSP
reset, emit silence when the DAC has no active DSP output, and propagate hook
release independently of a PCM batch or resampler producing output. Preserve
strict underrun detection for unexpected loss during an active datapump stream;
merely enlarging the FIFO or globally ignoring underruns would hide the bug.

This explains the interrupted cleanup/final Hayes response, not necessarily
why neither extension produced an earlier modem answer. RX levels/clipping and
the actual approximately 400 Hz call-progress response remain separate issues.
