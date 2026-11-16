# No, the I-modem does not need an ISDN carrier

The B channel is 8000 octets per second, and no rule says that they must be data.
If you offer the call as audio, the I-modem answers it **as a modem**. It uses its own
datapump directly on the bearer. There is no rate adaption above it, and no ISDN
protocol to establish. That is the interesting case for x2 and V.90, because
it puts this board on the *digital* side of an analogue connection, with direct
access to the codewords.

```sh
.venv/bin/python -m courier_emu isdn-run Ie030002.nac --with-dsp \
    --bri-network --bri-establish terminal --bri-call-at 20000000 \
    --bri-call-to 7349195 --bri-bearer audio \
    --bri-tx-g711 answer.g711 --send ATA --send-after 30000000
```

## What comes back

The result is 49,006 octets, and it is not framing:

```
t=  0.00s  level   405.6  dominant 2100 Hz
t=  0.62s  level   434.9  dominant 2100 Hz
t=  1.25s  level   428.1  dominant 2105 Hz     <- a reversal inside the window
t=  1.88s  level   437.2  dominant 2100 Hz
```

The phase of a 2100 Hz reference turns over at **0.47, 0.92, 1.37, 1.82,
2.27, 2.72 and 3.17 seconds**. This is 450 ms apart, six times one after the other. 2100 Hz with
phase reversals each 450 ms is **ANSam**, the answer tone of V.8. A modem sends this tone
when it can negotiate V.90 and not only V.34. The tone
continues for about three seconds. Then it stops, and it starts again seven seconds later.
The modem answers two times, because nothing answered it.

Thus, the full chain operates, and it is a short chain:

```
SETUP (3.1 kHz audio, mu-law) -> RING -> ATA -> l4_CONNECT -> BCH_ENABLED
-> MCR1 = 16h -> the datapump -> ANSam on B1
```

There is no V.120, no X.75, no LLI, and no SABME. `courier_emu/v120.py` and
[imodem-v120.md](imodem-v120.md) are for the other type of call, the digital
call. Nothing on this page needs them.

## The one thing that has to be right

The one necessary item is **mu-law**. The layer-1 protocol octet of the bearer capability is `A2` for mu-law
and `A3` for A-law. This modem accepts the first and refuses the second:

| bearer capability | offered as | verdict |
|---|---|---|
| `90 90 a2` | 3.1 kHz audio, mu-law | ALERTING - it rings |
| `80 90 a2` | speech, mu-law | ALERTING - it rings |
| `90 90 a3` | 3.1 kHz audio, A-law | `SETUP with result= FFFE`, cause 88 |
| `80 90 a3` | speech, A-law | `SETUP with result= FFFE`, cause 88 |

The two directory numbers have the same behavior. Thus, the cause is the law, not the
number. We state this clearly because it caused a wrong interpretation
earlier in this work. The modem refused `--bri-bearer speech`. We interpreted the refusal
as *a wrong bearer class*, and we stopped work on the analogue call. The cause
was `A3`. The peer now sends `A2` by default. `--bri-law a` requests the
refusal intentionally.

## Where this goes

The bearer is an audio path with a datapump on it. At the far end of it, there is a
recording. A modem must be there: something that answers ANSam with a V.8
call menu, negotiates, and trains. The repository already has much information
about the data on that wire: [pcm-x2-v90.md](pcm-x2-v90.md),
[x2-v90-protocol-selection.md](x2-v90-protocol-selection.md),
[v34-arming.md](v34-arming.md), [answer-tone.md](answer-tone.md). The
datapump of the analogue Courier is also in this tree, and we can connect it to this wire.

Thus, the next useful work is not more ISDN. It is to
connect this bearer to the analogue side that we already model here. Then the two
Couriers can answer each other. The first half of that work is done:
[imodem-bearer-over-sip.md](imodem-bearer-over-sip.md) carries the bearer to a
SIP call as PCMU, codeword for codeword. The answer tone above comes out
of the far end of an RTP stream.
