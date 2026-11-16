# Making it dial out as a modem, and what stands in the way

[imodem-live-sip-call.md](imodem-live-sip-call.md) dialled a real Courier and
found why the two did not train. The `ATD` of the I-modem sends
**unrestricted digital with a V.120 low layer compatibility**. Thus, it dials a
digital call. For V.34 or x2, it must dial an analogue call. The firmware
has the switches for this. This page shows which switch selects it, and how
S80 changes the SETUP that results.

## The switches, in the firmware's own words

`tools/imodem_help.py` decodes the built-in help table. The related
registers have these names:

```
S58   1 = Disable x2          2 = Disable server mode    4 = Force x2 A-law mode
      8 = Disable symmetric mode   16 = Enable -6dbm constellation
     32 = Disable V.90
S67   8 = Route 3.1K Audio Calls / Route Analog Telephony Calls
S68   1 = Disallow Analogue Connects
     16 = Route Speech Calls to / Route ISDN 3.1kHz Telephony
S80   4 = Force Modem Calls as Speech / Force Modem Calls as ISDN
```

S58 is the x2 register. Note what it says about the
roles: **server mode and symmetric mode are both on by default** (the bits
disable them). x2 needs this configuration with a modem that has a digital connection.
S68 bit 1 says that analogue connects are *permitted* unless you disallow them.

## S-register writes work, and an earlier reading here was wrong

We state this clearly because it caused us to do unnecessary work. An older run with incorrect timing
related `NO CARRIER` to `ATS80=20`, and after this `ATS80?` still showed `016`.
With a sequence that waits for the result code, the setter itself answers
`OK`. In the two cases, the conclusion that the modem refused the write is **false**.

The live register file gives the answer. The file is at `2600:d17b`, with one
byte for each register. The write routine at `0xcc471` indexes it directly
(`add ax, 0xd17b`, with a bounds check of the register number against `0x53`). We monitored
those bytes during a run:

| command | S80 in the register file | S0 |
|---|---|---|
| `ATS80?` | 16 | 0 |
| `ATS80=20` | **20** | 0 |
| `ATS0=7` | 16 | **7** |

The write is successful. `ATSn?` reads the **saved profile**, not the
working register. The general lesson is the same as the lesson that
[imodem-config-sector.md](imodem-config-sector.md) found for
`AT*V1`: a response is not necessarily an answer to the command before it.

## S80 alone is not enough

We set S80 bit 4 in the live register file and then dialled, with `ATD` as the
only AT command of the run. This did not change the call:

```
SETUP  bearer capability 88 90
       low layer compat  88 90 28 48 76 3b c0 c2 e2
```

The call is still unrestricted digital, and still V.120. Thus, "Force Modem Calls as Speech"
alone is not the switch, or not all of it. The help text has *two*
lines for bit 4: "as Speech" and "as ISDN". This suggests that its meaning
depends on a different setting. The probable candidate is the `*V2` data bearer
(Auto Detect, V.120, V.110, Modem/Fax Emulation, Clear Channel, PPP, X.75).
[imodem-config-sector.md](imodem-config-sector.md) puts this bearer in the record,
not in the table of ATI12.

## `*V2=3` is the analogue-origination switch

The command sequencer now waits for a complete final-result line before
it sends the next command. This removes the problem in the harness and makes this
single run reliable:

```sh
.venv/bin/python -m courier_emu isdn-run Ie030002.nac \
    --instructions 30000000 --send-every 0 --no-flash-nvram \
    --bri-network --bri-establish terminal \
    --send 'AT*V2=3' --send 'AT&W' --send 'ATD8406'
```

The modem sends SETUP, and the peer records:

```text
bearer capability       90 90 a2   3.1 kHz audio, 64 kbit/s, G.711 mu-law
low layer compatibility absent
```

The control with the default profile is `88 90` plus the LLC
`88 90 28 48 76 3b c0 c2 e2`: unrestricted digital with V.120. Thus,
`*V2=3` really changes outbound calls to an analogue modem bearer.

S80 bit 4 is an override at a second stage. In the same sequence, if you put
`ATS80=20` before the dial, the bearer changes to `80 90 a2`: Speech, 64
kbit/s, G.711 mu-law, and still no LLC. For the 3.1 kHz bearer, keep S80 at its default 16.
Set the bit only when you specifically want Speech.
