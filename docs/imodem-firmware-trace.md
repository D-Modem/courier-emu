# The I-modem's ISDN stack logs itself, in English

We recovered all other information in this repository about the ISDN stack of the I-modem
by disassembly and inference. That was not necessary. **The stack
is instrumented, and the instrumentation is symbolic.** It gives the names of the
primitives of the developers, and a run can read it back with two
memory reads.

```
LINE_ACTIVE Detected
l4_DISCONN : modem primitive
```

That is an `ATDT` in the words of the firmware. It answers a question that three
separate configuration hypotheses could not answer: the dial *does* get to layer
3, and it arrives there as a **disconnect**, not a setup.

## How it works

There is a printer at `0x77fc2`. Callers give it a far pointer to a string.
It packs the characters two in each word into a ring at `ds:0xa79a`, and it keeps the
count of used words at `ds:0xb79a`. It adds a CRLF after each entry.

`ds` is `ce0`. This is the segment into which the initialiser relocates `0x41c0` bytes from
image `0x98d50`. For this reason, we give all other addresses in this stack relative to it.
When we resolved the string offsets against that block,
`push 0x1594` became `l4_DISCONN : modem primitive`.

It is a **fill-once** log, not a wrap-around log. The guards at `0x78039` and
`0x78051` compare the index with `0x7fd` and `0x7ef`, and then stop the additions. Thus, the
log of a long run stops at the end, and it does not lose its start. The capacity is 2048 words.
The characters are packed low byte first. Thus, when you read the ring as raw bytes,
it is already the text. The `or ax, 0x2000` at `0x77ff6` pads an odd trailing character
with a space.

`courier_emu/imodem_trace.py` reads it, and `isdn-run` includes it in each
report as `firmware_trace`. An index outside the ring reads as empty. The reader does not
decode the data at the address. Thus, a wrong segment gives no information,
and it does not give false information.

## The vocabulary

That block contains 465 strings. This is a sample of the strings of the ISDN side:

```
l4_SETUP : modem primitive          code =l4_SETUP
l4_DISCONN : modem primitive        code =l4_DISCONN
l4_CONNECT : modem primitive        code =l4_CONNECT
l4_DIGIT : modem primitive          code =l4_DIGIT
default : modem primitive           code =l4_CHANGE
                                    code =l4_TXDATA
LINE_ACTIVE Detected                code =l4_BCH_FLOW_OFF / _ON
LINE_NOT_ACTIVE Detected            code =l4_GET_V120
SPID_ERR Detected                   code =N_CONN_IN / N_CONN_CF
MISC_INFO Detected
STAT_OFFHOOK Detected>>>            TEI_REMOVED
STAT_ONHOOK Detected                TEI_REM_INFO
BCH_ENABLED Detected                N202 Cnt Exceeded - no TEI assigned!!!
START_ALERT / STOP_ALERT Detected   TEI ASSIGN msg received with TEI that
L4_DIALDGTS Detected                  had already been assigned => remove TEI
SIGNAL_IND Detected with #          CONNECT REQUEST REFUSED - NO MORE
PROGRESS_IND Detected                 B_CHANNELS AVAILABLE
                                    SETUP not compatible INTL, release call
```

Those names agree with the items that we already recovered with much work, and they confirm
them. The handler at `0x75882` dispatches a "modem primitive" on a character:
`'@'` logs `l4_SETUP`, `'B'` logs `l4_DISCONN`, and `'C'` and `'a'` log the others.
The layer-2 arms at `0x7743c`, `0x7744f`, `0x77468` and `0x77481` are
`SPID_ERR`, `LINE_ACTIVE`, `LINE_NOT_ACTIVE` and `MISC_INFO`.
Thus, when `0x7744f` sets `ce0:8d7c`, this is exactly what its name says. This
independently confirms the interpretation in
[imodem-config-sector.md](imodem-config-sector.md).

## What it says about ATD, and about this harness

A dial with no other activity gives:

```
LINE_ACTIVE Detected
l4_DISCONN : modem primitive
```

The AT layer gave a disconnect to layer 3, but it did not *decide* to do this.
When we follow it, we get the full answer, and the answer is not
in the AT layer. Refer to
[the ATD path](#atd-never-builds-a-setup-and-the-reason-is-layer-2) below.

A dial while the network peer first presents an incoming call gives
a different result:

```
LINE_ACTIVE Detected
LINE_NOT_ACTIVE Detected
default of n_stat_in detected
001A
l4_DISCONN : modem primitive
```

At first, we wrote this up here as a defect in `courier_emu/bri.py`. **It is
not a defect there.** The method that excluded it is important to keep, because "our peer must
be the cause" is the easy answer, and it was wrong.

* The peer never changes the line after activation. A watch on
  `Am79C30.set_liu_state` records exactly three changes in the full run:
  F1→F2, F2→F6, F6→F7. All of them occur during activation, and none near the frame.
* The chip model does not damage the frame. It delivers 35 bytes, the firmware **reads back
  35 bytes**, and DRCR reports 35.
* The firmware reads the line again itself at `0x71b3d`, calculates `(LSR & 7) + 2`
  = **8**, and stores F7. Then it raises the status. Its own stored
  state says that the line is up, while it reports that the line is not up.
* The cause is not the broadcast data link, and it is not the information elements.
  We injected four different frames and read the log back. This separates them
  fully:

  | frame | firmware's verdict |
  |---|---|
  | UI, SAPI 63 / TEI 127, TEI identity check | `LINE_ACTIVE` only |
  | UI, SAPI 0 / TEI 127, payload `00 00 00` | `LINE_ACTIVE` only |
  | UI, SAPI 0 / TEI 127, bare SETUP, no IEs | `LINE_NOT_ACTIVE`, `001A` |
  | UI, SAPI 0 / TEI 127, full SETUP | `LINE_NOT_ACTIVE`, `001A` |

A junk UI on the same broadcast path has no effect. Only a **valid Q.931
SETUP** causes it. Thus, this is the layer 3 of the firmware itself. It reacts to an
incoming call for which it has no TEI. `001A` is a status code for which its
`n_stat_in` dispatcher has no arm: the `default` at `0x774ac`.

### What was actually wrong with the peer

The examination found two real defects. The two made the behaviour of the firmware
more difficult to interpret, but they did not cause it:

* **No T303.** The peer sent one SETUP and then reported `call_state:
  call-present` for the remaining part of the run. Thus, a call that nobody answered looked like a
  call in progress. In Q.931, the network retransmits one time after four
  seconds and then clears. The peer now does this, and it reports it.
* **No model of the line going down below it.** The peer only
  read back the state that it had set. Thus, if the firmware had deactivated its LIU, the
  peer would have continued to report a data link that could not exist. It now
  sees the change, drops its layer-2 and call state, and does not activate the line
  again immediately. A new activation would hide exactly the behaviour that we want to
  see.

`tests/test_bri.py` covers the two fixes. Neither changes the trace above.
This is the important point: the firmware never reacted to them.


## ATD never builds a SETUP, and the reason is layer 2

`l4_DISCONN` was not the cause, and the trace of it showed
that. The routine that issues it, at `0xc5519`, pushes `0x42`
**unconditionally**. It is the hang-up routine, not a decision. During
an `ATD`, the code gets to it from `0xab2ef`, a teardown sequence that calls it
without a test. Thus, `l4_DISCONN` is the cleanup *after* the dial failed. It is not
the dial.

The dial itself is easy to find when you look for the other primitive. Of
the nine call sites of the primitive handler at `0x75882`, exactly **one**
pushes `0x40`, `l4_SETUP`:

```
cbf90  push word [0xc8fc]
cbf94  push ds
cbf95  push 0xd130            ; the dialled number
cbf98  push 0x40              ; l4_SETUP
cbf9a  lcall 7561:0272
```

That block never executes. Nothing in `0xcbf20`-`0xcbfb8` runs during an
`ATD`, because the only path to it is from `0xcbe81`:

```
cbe7f  or al, al
cbe81  je cbf1d               ; result code 0 - only then does the dial run
```

### The command table, and the handler

The interpreter dispatches on a table indexed by the command letter:

```
cbe36  sub bl, 0x21           ; index = character - '!'
cbe39  shl bl, 1
cbe3b  call word ptr cs:[bx + 0x607]
```

This is in segment `cbb8`. Thus, the table is at `0xcbe87`. `'D'` resolves to
**`0xcc6a3`**, and the handler runs to this code at `0xcc84b`:

```
cc84b  lcall 6757:0a9e            ; refresh the layer-2 status
cc852  mov ax, 0ce0 ; mov es, ax
cc857  mov bl, es:[8d7d]          ; Data Link Layer
cc85c  mov bh, es:[8d7c]          ; Physical Interface
cc862  cmp bl, 0
cc865  je cc869                   ; data link down - keep going, to the error
cc867  clc ; ret                  ; data link up - success
...
cc87e  or byte [0xca57], 0x80
cc883  stc ; ret                  ; the error return
```

Those are the same two bytes that `ATI12` prints as `Physical Interface` and
`Data Link Layer`. We read them at the gate in a live run:

```
ATD reads  data link ce0:8d7d = 0, physical ce0:8d7c = 1
        -> error return, no SETUP is ever built
```

The handler returns carry. The interpreter stops the command with `al = 3`,
that is, Hayes result code 3, `NO CARRIER`. The teardown that follows calls the
hang-up routine. This is the source of the `l4_DISCONN` in the log.

### What that settles

**`ATD` is gated on the data link being established.** It could never
dial, with any switch protocol, dialing mode, bearer capability or DIP
switch setting, because we tested each of those while `ATI12` still
reported `Data Link Layer   :  Inactive`.

Thus, the two questions of this repository become one question.
There is no separate problem of "why does the AT layer refuse to dial". There is
only one problem: **layer 2 does not come up**. All other symptoms come from it.
