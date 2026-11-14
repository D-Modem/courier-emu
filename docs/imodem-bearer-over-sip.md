# The B channel as a SIP call

At the end of [imodem-audio-bearer.md](imodem-audio-bearer.md), the I-modem
answers an audio call as a modem and puts ANSam on the bearer. But it finds
nothing at the other end of the bearer. `--bri-sip` puts a SIP call there.

```sh
.venv/bin/python tools/sip_answer_sink.py answer.g711 150 &

.venv/bin/python -m courier_emu isdn-run Ie030002.nac --with-dsp \
    --bri-network --bri-establish terminal --bri-call-at 20000000 \
    --bri-call-to 7349195 --bri-bearer audio \
    --bri-sip 127.0.0.1:5060 --bri-sip-target 5551234 \
    --send ATA --send-after 30000000
```

The answer tone of the modem comes out of the far end of an RTP stream:

```
bri.media_peer   INVITE to 5551234
                 tx INVITE cseq=1 | rx 200 | tx ACK cseq=1
                 state connected, 588 RTP packets sent
94,080 octets recorded, 2100 Hz throughout
```

## Why this join needs nothing in the middle

A B channel carries 8000 octets of G.711 each second. The PCMU payload of RTP
*is* 8000 octets of G.711 each second. They are the same octets. Thus the
bridge does not convert anything:

* **no resampling** - the two sides are 8 kHz. `ata.py`, which puts the
  analogue board on a SIP line, must run a polyphase filter, because the codec
  path of that board is not 8 kHz;
* **no companding conversion** - mu-law in, mu-law out.

The second item is not only for tidiness. The linear path of `SipSession`
decodes each codeword to a sample and encodes it again on the way out. That
round trip is identity for 255 of the 256 codewords, but **not for `7f`**.
One error in 256 is inaudible in speech, but it is a defect here. V.90 and x2
use exact codewords - the main idea is that the digital end of the call puts
them on the wire itself - and this board is that end. Thus we added
`send_pcmu` and `receive_pcmu` next to `send_audio`, and we did not change the
analogue path.

`tests/test_bearer_sip.py` sends all 256 codewords through a real socket pair
and makes sure that they arrive with no change. It also examines the linear
path with the same 256 codewords, so that the reason stays recorded.

## What it does not pretend

The emulator runs on an instruction budget, and RTP runs on a clock. The two
do not agree about the length of a second. The bridge does not hide this. It
returns exactly as many octets as it received. It fills the octets that did
not arrive with mu-law silence, and it **counts every octet of the fill**. A
run shows this clearly:

```
octets  to_rtp 94096  from_rtp 94096  silence_filled 94096
```

All of the output of the modem went out, and nothing came back, because the
sink above sends no audio. A far end that sends audio will show a decrease of
the fill. The size of that decrease is the honest measure of how close to real
time that run was. Nothing here tries to make the two clocks agree. A run that
needs this is a different task, and it must be an intentional one.

## Where it goes

The obvious far end is the other Courier. This tree already models the
analogue board and its datapump, and
[ata-sip-line.md](ata-sip-line.md) already puts that board on a SIP line
through `LineExchange`. Now the two ends speak PCMU to a SIP server. Thus you
can point the ISDN Courier and the analogue Courier at each other through one
server. The digital end puts codewords directly on the bearer, and the
analogue end hears them through a codec. That is the shape of an x2 or V.90
connection. It is the first time that this repository has the two halves of
it able to get to the same wire.
