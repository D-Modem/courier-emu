# V.120 on the B channel, and how far it gets

At the end of [imodem-b-channel-silence.md](imodem-b-channel-silence.md), the
bearer works: the modem answers a call, synchronises its HDLC receiver, and
idles the B channel with its own flags. Then it clears the call, because the
far end sent only flags. `courier_emu/v120.py` is the remaining part of the
work. This page tells as carefully where it stops as what it does.

## What the peer speaks

The peer has three layers. It uses the same rules as the Q.921/Q.931 peer next
to it: it gets to the modem only as octets on the B channel. It never writes
the memory of the modem. It sends only what the standards tell it to send.

* **HDLC** - flags, zero-bit insertion, and the 16-bit frame check sequence of
  ISO 3309. The transmitter is a continuous bit stream: flags when idle and
  stuffed frames when not idle. Thus the bearer always carries something. The
  receiver destuffs and compares the FCS with the residue `F0B8`. It counts
  the frames that it discards: aborts, runts, and bad FCS separately.
* **The V.120 address** - a 13-bit logical link identifier across two octets,
  with the command/response bit between them. That is the address field of
  LAPD, with the SAPI and TEI read as one number. The firmware reads it
  exactly in this way: `Illegal TEI/SAPI received from V120 peer:` is one of
  its own log strings. LLI 256 is the default link.
* **The data link** - the procedures of Q.921 at frame level: SABME and UA to
  establish, I frames numbered modulo 128, RR to acknowledge, DISC and DM to
  clear, and T200 with N200 retransmissions. The timers count octets, not
  instructions. Thus a timer means one second of bearer, independent of what
  the harness does.

```sh
.venv/bin/python -m courier_emu isdn-run Ie030002.nac --with-dsp \
    --bri-network --bri-establish terminal --bri-call-at 20000000 \
    --bri-call-to 7349195 --bri-v120 --send ATA --send-after 30000000
```

`--bri-v120-lli` selects the link. `--bri-v120-establish terminal` waits for
the modem to establish, and does not establish itself. `--bri-v120-send` puts
user data in the queue. The run reports all results under `bri.v120`.

`tests/test_bri.py` examines the encodings in the same way as it examines the
encodings of Q.921. It compares the FCS with the residue of ISO 3309. It tests
the stuffing with a payload that is intentionally full of flags and idle
marks. It tests the LLI across the two address octets with the C/R asymmetry.
It also tests a link that answers a terminal that establishes first.

## How far it gets, exactly

The bearer carries it. The modem synchronises, and the frames of the peer go
out and come back with correct framing - no FCS errors, no runts, and the flag
count increases during all of the call:

```
v120  state released  sent 4  flags_seen 8321  fcs_errors 0  runts 0
      SABME on LLI 256
      T200 expired, SABME again (1 of 3) ... (3 of 3)
      T200 expired 3 times: the modem never answered
```

**The modem does not answer SABME.** It sends flags and nothing more. After
its own timeout, it clears the call. The two ends idle at each other until one
of them stops.

The bit order is not the cause, or not obviously. The flag is a palindrome,
so it proves nothing. The receive handler of the modem at `eb39` reverses the
bits of each octet when a configuration word tells it to do so. This is why
`--bri-v120-msb-first` exists. We ran the two bit orders. The modem answers
neither of them, and neither gives a different count.

## The one thing that changes its mind

A V.120 call can say that it is V.120 in the SETUP, in the low layer
compatibility element. The strings of the firmware say that it reads it
there - `V120 SET no negotiate LLI`, `V120 SET Remote assignor and LLI present`,
and the `WARNING` forms of the two, at `0x43fcc` and after. They operate on a
parsed parameter block.

When we offer the element, the behaviour of the modem changes completely, and
not for the better:

| SETUP | what the modem does |
|---|---|
| bearer capability only | answers, `BCH_ENABLED`, idles flags, clears on timeout |
| plus low layer compatibility naming V.120 | `MISC_INFO Detected`, `l4_DISCONN`, no RING, no `BCH_ENABLED` |

Thus the modem parses the element and refuses the call because of what it
contains. This is more important than it looks. It is the first evidence that
the V.120 acceptance of this modem depends on something in those octets. It
makes the area for the next search smaller. `--bri-v120-llc 1080` offers the
pair that the standards suggest for a synchronous 64 kbit/s call - octet 5a
`10`, octet 5b `80` - and the modem clears the call. It is a probe. This is
why it is off by default, and why the octets are not written into the peer as
a setting.

**And the guess was incorrect.** The modem dials V.120 itself. A live call
([imodem-live-sip-call.md](imodem-live-sip-call.md)) captured its own SETUP,
which shows what the modem thinks the element must contain:

```
low layer compatibility  88 90 28 48 76 3b c0 c2 e2
```

The first three octets are as above. Then `48 76 3b c0` are for the rate
adaption, and `c2 e2` name Q.921 and Q.931 as the layer 2 and 3 protocols. The
guess did not include these. When we offer this back to the modem with
`--bri-v120-llc 48763bc0c2e2`, the modem **accepts** the call: it rings, gives
`BCH_ENABLED`, and the bearer carries flags. With `1080`, the modem cleared the
call with `MISC_INFO`. The modem still does not answer SABME. Thus the question
at the end of this page does not change. But now the question does not have a
SETUP that the modem refused in front of it.

## What is open

There are three open items, in the sequence of their value:

* **Why the LLC is refused.** The parser is at `0x43f60` and after. It operates
  on a structure whose fields at `+4`, `+6`, `+8`, `+0a`, `+0b` and `+0c` are
  the rate adaption parameters. `+4` is the field that the `no negotiate LLI`
  branch tests. To read what it must have is the same type of work that found
  the called-number comparison. It probably has the same type of answer.
* **V.120 with `*V2=1`.** `*V2` is now mapped as a literal binary selector at
  record offset `0x25f`. These earlier runs used the default, Auto Detect. If
  we repeat the link experiment with V.120 selected explicitly, we can
  separate the protocol negotiation from the automatic bearer selection.
* **Who establishes.** The peer tries the two methods, and the modem answers
  neither. Thus this item is the least probable of the three. But
  `--bri-v120-establish terminal` is available, and if the modem establishes
  first, the peer answers it.

The operation of the bearer is *not* an open question. Frames go out, with
correct framing and checks. Flags come back, and the peer counts them. The
link that this page cannot complete is now a protocol question, not a hardware
question.
