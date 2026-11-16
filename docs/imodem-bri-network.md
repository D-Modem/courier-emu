# Putting a network on the I-modem's S interface

[imodem-d-channel.md](imodem-d-channel.md) started layer 1, and
[imodem-config-sector.md](imodem-config-sector.md) gave the modem a real
configuration. The two pages stopped at the same point: the modem never
transmits a layer-2 frame, so layer 2 never starts. The reason is simpler than
the pointer search at the end of that page. **There was nobody on the line.**

A BRI terminal does not talk to itself. On a point-to-point line, it waits for
the network to establish the data link. On a multipoint line, it requests a
TEI when it has traffic. In the two cases, the first action belongs to the far
end, and this repository had no far end.

`courier_emu/bri.py` is a far end. It is not a model of a part of the board -
the side of the board is the Am79C30A and the firmware. It is a peer, built
from Q.921 and Q.931. It gets to the modem only through the receive and
transmit buffers of the chip, `deliver_frame` and `take_sent`. It never writes
the memory of the modem and never writes its registers. This is why it is
evidence and not a substitute.

```sh
.venv/bin/python -m courier_emu isdn-run Ie030002.nac \
    --instructions 60000000 --line-activate 3000000 --bri-network
```

`--bri-establish network|terminal` selects which end establishes. `--bri-tei`
selects the TEI that the network addresses. `--bri-call-at` makes a call to
the modem. The run reports all actions of the peer under `bri`.

Note that there is no `--line-activate` in that command. **The NT terminates the S bus, so the NT drives the
line.** The peer moves the terminal up through F2, F6 and F7, as INFO2 and
INFO4 do. F2 is first, because the layer-1 machine of the firmware dispatches
on its current state and discards an event that skips a state.
`--line-activate` still tells *when*. `--no-bri-activate` stops the NT, for a
run that drives the line in a different way. `--bri-deactivate-at` sets the
line back to F3. This is the only way to find what the firmware does when the
network goes away.

## What the peer speaks

* **Q.921** - address decoding for SAPI and TEI, the U, S and I formats,
  TEI assignment on SAPI 63 / TEI 127, multiple-frame establishment with
  SABME/UA, N(S)/N(R) accounting, RR and REJ, and T200 with N200
  retransmissions.
* **Q.931** - SETUP, CALL PROCEEDING, ALERTING, CONNECT, CONNECT
  ACKNOWLEDGE, DISCONNECT, RELEASE, RELEASE COMPLETE, and the information
  elements that those messages carry: bearer capability, channel
  identification, called and calling party number, cause.

`tests/test_bri.py` compares the encodings with the standards. This includes
the one asymmetry that is easy to reverse by mistake - Q.921 gives the C/R bit
opposite meanings on the two sides. Thus the same octet is a command from the
user and a response from the network.

## B-channel media

When Q.931 gets to Active, the peer connects the media to the channel that the
Channel Identification information element selects. It puts the octets from
the network to the terminal in the queue of that B1/B2 input. It captures the
octets from the terminal to the network after the MCR routing of the firmware
has moved them between the Am79C30 and the DSP. The bytes stay opaque at this
boundary: a speech call can contain G.711 audio, and an unrestricted
64 kbit/s call can use all eight bits as data.

The CLI can inject and capture that stream directly:

```sh
.venv/bin/python -m courier_emu isdn-run Ie030002.nac --with-dsp \
    --bri-network --bri-rx-g711 far-end.g711 --bri-tx-g711 modem.g711
```

The input is held until the call becomes active. The output that is recorded
before CONNECT is discarded. Thus the capture cannot mistake the idle DS0 for
connected media. The `bri.media` report of the run names the selected channel,
and gives the counts of delivered, captured and non-`ff` octets. It
intentionally does not call `ff` silence: the B channel is opaque here, and
the meaning of `ff` depends on the negotiated bearer.

On an answered call, it *is* silence.
[imodem-b-channel-silence.md](imodem-b-channel-silence.md) follows it back to
the single DSP command that the modem never takes. That page also gives the two
items that a SETUP must have correct before the modem rings - the called
number and the bearer. This replaces the "incompatible" question that the
sections below leave open.

## What it found, on the first run

With a record whose switch protocol is ETSI NET3 and a point-to-point line,
the peer sends SABME to TEI 0, and the modem does not answer. It does not
ignore it: the counters of the chip show that the frames arrive, and a trace
shows that the firmware reads each byte of them.

Now we know all of the receive path:

| where | what it does |
|---|---|
| `0x72e1e` | the ISR's receive loop - DCRB into a buffer, DSR2 bit 0 for the last byte and bit 1 for more waiting |
| `0x72eac` | `test [bp-2], 0x7b` - the DER error check; a frame with any of those bits is dropped here |
| `0x72f07` | posts the frame up as **message `0x33`** |
| `0x6674c` | the Q.921 entity's receive handler, reached from the dispatcher at `0x66734` |

We also know the validation that the entity does. This is where our SABME
stops:

```
667b1  test es:[bx+1], 1      ; octet 2's EA bit must be set
667ba  cmp [bp-0x16], 3       ; at least three octets
667d4  sar ax, 2              ; SAPI  = octet 1 >> 2
667e0  sar ax, 1              ; TEI   = octet 2 >> 1
667e9  SAPI must be 0, 2, 0x10 or 0x3f, else discard
66814  cmp dl, 0x7f           ; TEI 127 goes to TEI management
668a2  lcall 6757:2fe         ; otherwise look the data link up
```

The lookup at `0x6786e` goes through a table at `[0x6b88]` with six bytes for
each entry, indices 3 to 12. It compares the interface id, the SAPI and the
TEI. Two more passes accept `0xfe` and `0xfc` as wildcards. **No entry agrees
with SAPI 0 / TEI 0.** Thus the frame is discarded, and it is correct that
the modem stays silent. The modem is configured for automatic TEI assignment.
Thus it does not own TEI 0, and a network that addresses that TEI addresses
nobody.

That is a real answer to the question that the previous page left open, and it
replaces the hypothesis there. The transmit path at `0x71cb0` is not
unreachable because of a missing pointer. Nothing asks for it, because no data
link exists.

## The broadcast data link is the door

The point-to-point attempt above fails because the modem owns no TEI. A
network end has a different method, and Q.931 specifies it for an incoming
call on a multipoint bus. The network does not know which terminal wants the
call. Thus it puts the SETUP on the **broadcast data link** - a UI frame to
TEI 127. The terminal that takes it gets a TEI and establishes the link to
answer. That path needs nothing from the terminal before. Thus it is the only
path that can get to a modem that has never transmitted. The peer uses it
automatically when it has no data link.

```sh
.venv/bin/python -m courier_emu isdn-run Ie030002.nac \
    --instructions 120000000 --bri-network --bri-establish terminal \
    --bri-call-at 20000000 --bri-call-to 5551212
```

And it gets in. The trace shows that the modem accepts the broadcast SETUP,
where it discarded the point-to-point SABME:

| where | what happens |
|---|---|
| `0x66814` | TEI 127, so the broadcast branch rather than the data-link lookup |
| `0x6685e` | SAPI must be 0; the entry is marked `0xfa`, the wildcard the lookup at `0x6786e` accepts |
| `0x66882` | raises event `0x16` - one of the types the handler at `0x76acf` dispatches |
| `0x6724d` | walks data-link entries 3 to 12 and, for each whose interface matches, posts message `0x35` and calls `6757:8ed` |

The body at `0x672bd` executes. Thus **layer 3 gets the notification of the
incoming call**. It goes no further: the modem does not answer, does not ring
the AT interface, and transmits nothing. If we offer the call as speech and not
as unrestricted digital (`--bri-bearer speech`), nothing changes. Thus the
modem does not refuse the bearer capability.

But the limit of our knowledge has moved, and it is important to tell exactly
where. It is no longer "the modem never transmits a layer-2 frame, and we do
not know why". Now it is "the call control of the firmware received a SETUP
and does not act on it".

## What is still open

Two items are between this and a call. The two items are on the configuration
side of the modem, not of the peer:

* ~~**The modem's TEI request is never transmitted.**~~ It is transmitted now.
  The correction was to drive the LIU to the value that the part actually uses
  for an activated interface
  ([imodem-liu-state-field.md](imodem-liu-state-field.md)). The runs now show
  that `ID_REQUEST` arrives and a TEI is assigned, that layer 2 is established
  from the SABME of the modem, and that the call rings. The queued frame in
  [imodem-tei-request.md](imodem-tei-request.md) was a symptom of the layer-1
  state. It was not a defect of the transmit path.
* **`ATD` is gated on the data link, so it is not a second problem.** The
  `'D'` handler at `0xcc6a3` reads `ce0:8d7d` - the byte that `ATI12` prints as
  `Data Link Layer`. It returns an error when that byte is zero, before it gets
  to the one site in the image that issues `l4_SETUP`. Refer to
  [imodem-firmware-trace.md](imodem-firmware-trace.md). Thus we tested each
  configuration hypothesis with `ATD` against a gate that none of them could
  open.

The peer cannot yet do one thing, and the reason is in the firmware:
**terminal-initiated activation**. In I.430, a TE that wants the line to start
sends INFO1. On this board, that would be a write of the firmware to
`LIU_LMR1` of the Am79C30A. The firmware writes it one time at init, `0x40`,
and never again in the runs that we observed. Thus there is no request to
answer. If we invented a bit with that meaning, we would assert something that
the image has not shown. The runs above use the activation by the NT itself.

We also record this, because it caused a detour: the TEI field of the ISDN
block is at **index 88**, two ASCII characters. It is not at index 86, as
[imodem-config-sector.md](imodem-config-sector.md) says. `AT*T1=0` followed by
`AT&W` stores `30 30` there, and `ATI12` reads it back as `Automatic TEI`.

## The store makes this repeatable

None of the above needs a sector cut out by hand now. `isdn-run` keeps the
non-volatile region of the part - the 32 KiB above the update payload, which is
the three top boot sectors - in `flashnvram.sav` between runs. Thus, if a
session types settings and `AT&W`, the settings stay there for the next
session. `--no-flash-nvram` runs against an erased store.

## The peer's timers, and what it does not pretend

We made two corrections to the peer. We found both when we read the trace log
of the firmware ([imodem-firmware-trace.md](imodem-firmware-trace.md)):

* **T303.** If a SETUP gets no response, the peer transmits it again one time
  after four seconds, and then clears the call, as Q.931 tells the network to
  do. Before this correction, the peer reported `call-present` for the
  remaining part of a run. Thus a call that no terminal took looked like a call
  in progress.
* **A line that goes down below it.** Before, the peer only read back the line
  state that it had set itself. Now, if the firmware deactivates its own LIU,
  the peer sees this. It drops its layer-2 and call state, and keeps the line
  down. It does not move the line back up immediately - an NT that activated
  again immediately would hide the thing that we want to see.

It is important to be exact about the second correction, because it is a
safety net and not a fix for an observed problem: in the incoming-call runs,
the LIU **does not** move. The firmware reports `LINE_NOT_ACTIVE` while its own
stored state still says F7. That is the layer-1 machine of the firmware that
changes its decision. The line does not change, and no change to the peer has
an effect on it.
