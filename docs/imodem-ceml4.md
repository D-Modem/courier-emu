# CEML4: call-control events to modem/DSP setup

In Ie030002, `TID_CEML4` reads queue 10 at `46dd:000a`. It stores the message
pointer at `0ce0:a48c` and calls `7561:0009` with byte `message+8`.
This trace follows the `BCH_ENABLED` event to the modem/DSP mailbox.
It establishes the setup of the control plane. It does not establish the continuous PCM sample path.

## Primitive dispatch

| Message byte +08 | Meaning from the referenced diagnostic | Main handler / action |
|---|---|---|
| 00 | N_CONN_IN | `7561:00bc`. Classifies the incoming connection and calls `7561:0eb7`. |
| 01 | N_CONN_CF | `7561:0130`. Resolves the connection and calls `1ffe` and `2eea(slot,1)`. |
| 02 | N_DISC_IN | `7561:0167`. Sends the cause information on and calls `3b60(2,cause)`. |
| 03 | N_DISC_CF | `7561:01ef`. Calls `3b60(3,cause)`. |
| 07 | N_STAT_IN | `7561:14bf`. Dispatches the status subtype at message +10. |
| 0a | N_REL_IN | `7561:0210`. Calls `3b60(0a,cause)`. |
| 40 | Special connection event, name not confirmed | `7561:006d`. Acts on special slot 80h and updates the state/digit buffers. |

These are the message fields that we saw:

- +0b is the connection identifier that the lookup uses.
- +10 is a status subtype or a cause, as the primitive sets.
- +12 is used for channel information.
- +14/+16 make a far pointer to more information.

This is an internal message layout. It is not a raw Q.931 packet format.

`7561:3b2a` compares the identifier with `DS:a634`, `DS:a64c` and `DS:a640`.
It returns slot 0, special slot 80h or slot 1 respectively, or ffff on failure.
Slots 0/1 are call-record indices. They do not prove that they always agree with
physical B1/B2. Ordinary records have a 12-byte stride that starts at DS:a630.

## BCH_ENABLED path

Primitive 07, subtype **60h** selects `7561:17ae`. The diagnostic of this handler is
`BCH_ENABLED Detected`.

1. The handler resolves the connection with `3b2a`. If the identifier is unknown, it stops.
2. It updates the bearer-related record of the connection through `4290(slot, connection_id)`.
3. It calls `1ecf(slot)`. This routine derives a selector from the bearer state and
   sends **command 005eh** with the selector minus five (normally 1 or 2).
4. As the call state and the configuration set, it calls `3f36(slot,2)` and the
   link setup helper `8f6f:08af`. These later calls are conditional. They are not an
   action that occurs for each BCH_ENABLED indication.

`4290` compares the identifier with `DS:8eea` and `DS:8eee`. It reads the
related selectors at `DS:8ee9`/`DS:8eed`, and sets the byte of the record at
`a63a + 12*slot` to 6 or 7. It also sets the adjacent flag at `a639 + 12*slot`.
`1ecf` selects the related bearer state and subtracts five to get
the command argument. The two-channel structure gives strong support to the natural B1/B2 interpretation.
The isolated execution below proves the
numeric mapping, and it does not assume the board wiring.

## Exact command transport

```text
7561:1ecf -> 7561:431e(command=005e, argument=1 or 2)
  writes 2600:c982 = command, 2600:c984 = argument
  -> a400:1709 loads AX/BX
  -> b3d9:049a -> b3d9:04d8
  enqueues [ff00, command, argument]
  -> interrupt-side consumer b3d9:3efb
  outputs command via ports 58/5a, argument via 5c/5e
```

The read/write pointers of the ring are at `2600:c9ae`/`2600:c9b0`. Its data span
is `c9b2..c9f1`, 32 words. The ff00 marker is staged internally before the
command/argument pair is sent. It is not sent as a third payload word.
The code around the consumer uses ports 1c/1e for the handshake/status.
These are the mailbox windows that `mailbox_tap.py` also identifies.

## Additional bearer/mode commands

`7561:3f36(slot,mode)` builds an argument with these bits:

- bit 7 from `(record_selector - 6) << 7`, which identifies selector 6 or 7;
- bit 6 set;
- low bits adjusted from the modem configuration at `2600:d1be`, `2600:d1c0`,
  and `2600:e4ef`.

It sends **005ch** when the mode is 1, and **005dh** for other modes. Then it sends
command **000ah** with `(record_selector - 6) << 3 | 3` (3 or 11), and it saves
that value at `2600:c986`. We did not yet decode the interpretation of these bits on the DSP side.
Specifically, do not label them as A-law/mu-law or PCM enable bits
before you follow the DSP handlers.

The link helper at `8f6f:08af` logs PRIMARY CHAN/SECONDARY CHAN and sets a
rate field to 56000 or 64000, as an argument sets. That is evidence of a
separate data-link configuration. It is not evidence that the helper moves
G.711 samples.

## Executed verification

`tools/imodem_ceml4_probe.py` runs the original unpatched x86 routines
`4290` and `1ecf`, their command adapters and the mailbox consumer, with a synthetic
call state. It does not run the full CEML4 queue, and it does not make a complete synthetic call.

| Input bearer selector | Queued words | Port writes (port:value, hexadecimal) |
|---|---|---|
| 6 | ff00, 005e, 0001 | 58:5e, 5a:00, 5c:01, 5e:00 |
| 7 | ff00, 005e, 0002 | 58:5e, 5a:00, 5c:02, 5e:00 |

The two cases passed the assertions. To reproduce, run this command from the repository root:

```sh
.venv/bin/python tools/imodem_ceml4_probe.py \
  --output artifacts/imodem-ceml4/probe.json
```

The probe uses a synthetic far-call frame and configured RAM. Then it runs the
real staging and output instructions of the interrupt side. It stops before the remaining part
of the interrupt handler. The results and the image hash are in `probe.json`. The selected
instruction spans are in `artifacts/imodem-ceml4/disassembly.txt`.

## What is still open

CEML4 clearly connects call/bearer events to modem/DSP control commands. The
evidence does not yet establish these items:

- The DSP implementation of 5ch/5dh/5eh
- The connection of the Am79C30 multiplexer that is selected for a modem call
- The physical path that transfers the B-channel PCM

This probe did not show an end-to-end modem call.
