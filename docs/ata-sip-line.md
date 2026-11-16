# A loop in front of the SIP instrument

With [answer-tone.md](answer-tone.md) and [fsk-modulation.md](fsk-modulation.md),
the datapump sends its own signals. With [audio-312-path.md](audio-312-path.md),
it dials. All of that goes into a sample buffer, and it goes no farther. This
work connects it to a real network. `courier_emu.ata.SipLine` puts the modelled
subscriber loop between the modem and a `SipSession`. Thus, a number that the firmware
dials in tones becomes an INVITE.

There are two parts. The first part is necessary for the second part.

## Rate adaptation: the dial path is 7200 Hz and RTP is 8000

`sip.RateConverter` was a zero-order hold. It was written for the exact 6:5 ratio of the
9600 of the codec against the 8000 of G.711. It repeats or drops samples, and this leaves
the image of all signals that it passes. At 7200, that is important: the images of the
hold for the DTMF column tones fall in the band to which a far-end receiver listens.

`sip.PolyphaseResampler` is the standard rational resampler. It upsamples
by L, does a low-pass at the lower of the two Nyquists with a Blackman-windowed sinc, and
decimates by M. It evaluates only the taps that meet a non-zero sample. The taps of each
phase are normalised to a sum of one. Thus, the DC gain is exactly unity on each
phase, and the phase rotation itself adds no ripple.

We measured this on the rendering of `6245` by the firmware
(`artifacts/dtmf-emulator-302-01/`, rendered through `courier_emu.audio312`).
The measurement is in the first digit, and it is the worst out-of-band bin against the peak:

| 7200 -> 8000 | worst spurious |
|---|---|
| `RateConverter` (hold) | -11.7 dB |
| `PolyphaseResampler` | -27.0 dB |

The remaining -27 dB is the harmonic content of the tone itself, not of the resampler.
The SIP path of `bridge.py` now also uses it in the two directions.

## The loop: what `LineExchange` was missing

`LineExchange` already models all items on the loop side: hook, dial tone,
in-band DTMF collection, ringback and busy cadences, and the audio path when a
call is active. Its docstring already called it a digital ATA. But it did not
have a far end. `directory` decided the result of a number before the call
started, and its ringback was a timer that counted to `answer_after_rings`.

Three additions give it a real far end. They are additive: the directory still
operates when no router is set:

* `router(number) -> str | None` supplies the result when the collection stops.
  A return value of `None` means *the call is not yet ready*. The exchange then waits silently in
  `routing`. It does not route on a guess.
* `set_outcome(outcome)` resolves that wait later, from the component that does the
  real work.
* `answer()` is a far end that answers on its own decision, not after a ring
  count.

`SipSession` got `hangup()` to agree with this. It sends BYE for an established dialogue, and
CANCEL for a dialogue that is not yet established. The CANCEL carries the branch and the CSeq of the INVITE,
because this is the one request that must carry them. After this, the session is usable for the next
call, and its sockets stay open.

## What `SipLine` does with them

| loop side | network side |
|---|---|
| digits decoded off the line | `start_call(number)`, outcome pending |
| `ringback` | 180 Ringing |
| `connected` | 200 OK, `answer()` |
| `busy` | 486 or 600 |
| `reorder` | any other failure |
| on-hook | `hangup()` - BYE or CANCEL |
| `released` | far end's BYE |

Audio crosses at `peer_audio`, and it is resampled in the two directions. The modem does not know
about it. It seizes a loop, hears dial tone, dials, and hears ringback.

## Verified

`tests/test_ata.py` runs the full chain over real UDP sockets against a mock
PBX. When you dial `6245` in-band at 7200 Hz, the states go through
`dial-tone -> collecting -> routing -> ringback -> connected`. The test gets
`INVITE sip:6245@...`. It puts the 1000 Hz tone of the far end on the loop, more
than 20 dB above the adjacent bin. The audio of the loop gets to the
PBX as RTP. On-hook sends BYE. A 486 gives busy tone on the loop.

## In the bridge: ATDT6245 places the call

`CourierDspBridge` builds a `SipLine` each time it gets both an exchange
and a SIP session. The loop then controls the call. Four paths that ran
next to the exchange before are skipped while the loop controls the call, because the loop already
carries them:

* The `start_call` of `begin_dialing`. It took the number from the parsed AT
  command, and not from the line.
* `set_call_progress`. It controlled the operation of the DAA from the SIP state, and
  it would move the DAA out of `dialing` before the call engine of the ASIC had started.
* The `_publish_connected_event` from the SIP state. Now the exchange
  publishes it when the call goes through, on the same edge that the board sees.
* The transmit tap. It took `line_tx_samples` at the rate of the codec and sent
  it without resampling. The copy of the loop is rate-corrected two times: codec to line, then
  line to 8 kHz.

Thus, `--exchange` plus `--sip-server` is now a modem that dials a real peer:

```sh
python -m courier_emu run --exchange --sip-server pbx.example:5060 \
    --sip-username courier --daa quiet
```

`tests/test_ata.py::BridgeDialTests` runs it end to end against the mock PBX.
No part of the test gives the number to a component directly. The encoder of the supervisor sends one
keypad index for each digit as `0x16`/`0x13`/`0x16`. The board plays each tone. The
exchange decodes `6245` from the line, and the ATA changes that into
`INVITE sip:6245@...`. The test asserts `_dial_digits_commanded` (the request of the supervisor)
and `exchange.dialed` (what the line heard) separately. This
is the measurement. The 200 OK of the peer then connects the loop, and the
connected event of the board is published. The BYE of the peer releases the loop, and the DAA
reports `disconnected`.

That last step showed one bug. `SipSession._handle_request` answered an
inbound BYE with `sendto` on a socket that is `connect`ed to the server. This
raises EISCONN. Thus, the code had never answered an inbound BYE. It now uses `send`.

## What is still not shown

The board itself is not shown. These runs use the mock core of the bridge with a tone generator
attached. The real tone generator is in the ASIC, and its firmware is not in the
image. For the same reason, `_play_dial_tone` records the request of the supervisor
and does not play it. All items above the tone come from the firmware itself.

## Real-time physical-peer run

The complete 4.03d ROM now uses a native Unicorn basic-block clock. It does not
cross into Python for each guest instruction or basic block. SIP runs also
select a C52 scheduling batch of 4096 instructions by default, and they keep the
CPU service interval of 1024 instructions for the timer poll. The same call path of 150 million
instructions advances 44.1 seconds of line time in 27.0 seconds when
no external clock is attached. This gives sufficient headroom to pace a live call.

`SipLine` paces each 100 ms line frame with the wall clock, and it polls SIP/RTP while it
waits. `SipSession` sends each 20 ms packet that is due from that block. The former
behavior, one packet for each block, made an emulator at 30% of real time give only about 6%
of the audio at the peer.

We made a live call through `6000@asterisk.net.cryan.nz` to the physical ID_SDL 4.03d
Courier on extension `6245`. It advanced 47.1 seconds of line time in 50.2 seconds of
wall clock, and it exchanged 1,338 outbound and 1,330 inbound RTP packets. The
physical modem rang and heard full-rate audio. It still returned `NO CARRIER`.
The emulated side reports no start of the call engine and no call overlay. Thus, real-time
transport is not the blocker now. The datapump activation is still a blocker.
