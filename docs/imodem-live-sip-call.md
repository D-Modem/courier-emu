# A real call, to a real Courier

The far end of this call was not a model.  It was `6000@asterisk.net.cryan.nz`, which dials
`8406`. That number rings a **USRobotics Courier V.Everything** on a serial port
(supervisor 7.3.14, DSP 3.0.13, `HST,V32bis,Terbo,VFC,V34+,x2,V90`),
with `ATS0=1` to make it answer.

```sh
COURIER_SIP_PASSWORD=... .venv/bin/python -m courier_emu isdn-run Ie030002.nac \
    --with-dsp --bri-network --bri-establish terminal \
    --bri-sip asterisk.net.cryan.nz --bri-sip-username 6000 \
    --bri-sip-record heard.g711 --bri-tx-g711 said.g711 \
    --send 'ATDT8406' --send-after 30000000
```

## What worked, which is most of it

```
l4_SETUP : modem primitive | BCH_ENABLED Detected | Prim = N_CONN_CF :
dialled '8406' -> INVITE target '8406'
tx INVITE cseq=1 | rx 401 | tx ACK | tx INVITE cseq=2 | rx 100 | rx 183 | rx 200 | tx ACK
rtp sent 911   received 1588
octets to_rtp 145769   from_rtp 145769   silence_filled 439
```

All the joints held.  `ATD` now makes a call. It could not do this before
[imodem-b-channel-silence.md](imodem-b-channel-silence.md), because the data
link gate was closed. These steps occurred:

1. The peer connects the call, and the bearer starts.
2. The bridge authenticates against a real Asterisk.
3. The call gets to a real modem across a real network.
4. **The modem rang** and answered.
5. Audio went in the two directions.

The silence fill was 439 octets in 145,769, that is three parts in a thousand. Thus,
the emulator almost kept the speed of the wire.

But the two ends gave `NO CARRIER`.

## Why they did not train

The cause was not the network and not the pacing.  The modem never had an analogue
conversation.  Its own `ATD` SETUP shows this:

```
SETUP  bearer capability 88 90          unrestricted digital, 64 kbit/s
       channel id 83                    B1
       keypad facility 38 34 30 36      '8406'
       low layer compat 88 90 28 48 76 3b c0 c2 e2    V.120
```

**It dials V.120.**  The recorded bearer agrees. `said.g711` is silence from
the start to the end: one sample above the noise floor in 145,769. An originating
analogue modem would send a calling tone and then answer ANSam.  The
real Courier answered, sent its answer tone into the bridge, received an idle
digital link, and timed out.  Our side also timed out.

This run occurred before the multi-command delivery was reliable.  The conclusion that
`AT*V2=3` did not change the bearer was an artifact of the harness. The modem
accepts the setting, and it stays as binary `03` at record offset `0x25f`.  With the
fixed sequencer, `AT*V2=3`, `AT&W`, `ATD8406` sends `90 90 a2` (3.1 kHz
audio, mu-law) and no LLC.  Refer to
[imodem-dialling-analogue.md](imodem-dialling-analogue.md) for the control and
the S80 speech override.

## Two things the live call gave up for free

**The dialled digits are in the keypad facility.**  `ATDT8406` comes as IE
`2c`, `'8406'` in ASCII, not as a called party number. This is
why the peer reported a correct dial as `the modem is calling (no number)`.
Now the peer reads the two forms, and `--bri-sip-target` is optional: the bridge INVITEs the number that the modem
dialled.

**The V.120 low layer compatibility of the modem.** This is worth more than
the call.  [imodem-v120.md](imodem-v120.md) had to guess those octets, and
the guess was refused. These octets are from the firmware itself. When we send them back to the firmware,
it **accepts** them: the call rings, `BCH_ENABLED` occurs and the bearer carries
flags. With `1080`, the result was `MISC_INFO` and a cleared call.  Use the value `--bri-v120-llc
48763bc0c2e2`.  The modem still does not answer SABME, thus
that question did not change. But a refused SETUP no longer blocks it.

## The next live run

The analogue side of this board works. It answers an audio call as a modem
and puts ANSam on the bearer ([imodem-audio-bearer.md](imodem-audio-bearer.md)).
It can also originate an audio call when `*V2=3` is selected.  Thus, it is not necessary
to swap the original roles only to get an analogue bearer.

The existing outbound SIP bridge can now repeat this call with `*V2=3` and put
the two datapumps on an analogue bearer.  Inbound INVITE support is still useful
to reverse the roles, but it is no longer necessary before we try the
original direction again.

After that, the next question is the pacing.  In this run, 439 octets of fill show that the bearer can almost
keep the speed of real time. It is necessary to find if *almost* is sufficient for a V.8 handshake.
Do not assume it. The mapped setting now makes that experiment possible.
