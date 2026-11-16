# I-modem terminal failures: AT framing is bypassed

We confirmed this against `Ie030002.nac` on 2026-09-12. We used the existing
`flashnvram.sav` read-only, the external product type, and no DSP execution.
Before the fix, the `--terminal` route sent the literal `AT` prefix to a
parser that expects the command body. It also did not do the new-command reset.
Together, these two faults explain the missing/`NO CARRIER` result, and also why the firmware
executed old commands again.

This replaces the earlier explanations in [imodem-at-interface.md](imodem-at-interface.md).
These explanations said that the symptoms came from missing capability data or from the typing speed.
There can still be gaps in the configuration and the hardware. But the controlled experiment below
got correct responses without a new configuration record and without an active ISDN line.

## Why AT produces silence or NO CARRIER

`interactive_pump` sends the full typed line through `send_serial` to SIO0.
At idle, the RX dispatch word `2600:e834` selects `a400:ec8d` (`0xb2c8d`).
That handler reads RBR and calls `[c922]`, which is `0x8b3e`: the collector of the command body
at `0xacb3e`. It masks the parity, but it does not recognize an AT prefix.

In the raw ATI trace, the parser at `0xcbb90` gets length 3 and the buffer
`ATI`. It must get length 1 and the buffer `I`. The ordinary command table
dispatches the leading `A` to `0xcc564`, which is the answer-call handler. Its write
at `0xcc5ac` sets bit 0 of `[d16f]`. The `I` that follows still prints `USR009F`.
Thus, the command looks successful.

At completion, `[d16f]=1` sends the parser through `0xcc182`, which returns with carry
set. The caller branches from `0xac74f` through `0xac764`, `0xac4eb`, and
`0xac52f` into call handling. Then, `[c922]` becomes `0x0e0e`, the
keypress-abort receiver at `0xa4e0e`. A bare AT has no diagnostic text to
print. Thus, it can look silent while it waits in this state.

The next input aborts the call that we did not intend, and sets `[d08b]=0x17` (keypress
abort). The result emitter at `0xacf8c` gets code 3 and prints
`NO CARRIER`. The firmware can discard input during this transition. This is a
real transition of the call state. It is not a duplication of the display or of the UART output.

## Why the old model code keeps coming back

A CR does not reset the command length at `2600:e49a`. The collector increments
it when characters arrive, and it terminates the buffer at `2600:e49b` on CR.
The reset of the length is part of the recognition of a new AT prefix.

The stock route skips that recognition. Thus, the next accepted input is added
to the previous command body, and the firmware parses the old `I` and `Y11` commands again.
In a raw run with **20 million instructions between lines**, ATY11 gave
the previous `USR009F` before its own heading. The ATI3 that was accepted after it
gave the two old reports again before it printed its banner. If you wait longer, the buffer
does not reset.

If you remove AT from the input, this is only a partial workaround. An empty line and
`I` then give real OK result codes, but later `I6` and `Y11` still
execute the accumulated commands again. The prefix recognition and the buffer reset are
both necessary.

## Controlled validation

The firmware already contains an external UART prefix handler:

* `0xb3596` recognizes A. It masks the parity/case with `and al,0x5f`.
* `0xb35aa` recognizes T. It also handles the A/ repeat form.
* `0xb35e6` clears `[e498]` and **`[e49a]`**, selects the body collector,
  and changes the RX dispatch back to `0xec8d` for the command body.

For diagnosis only, a code hook at `0xc7bf1` (after the firmware arms the reception)
selects this existing handler. It writes `0xf596` to `2600:e834`. The
experiment changes this RAM dispatch word. It does not do these things: patch firmware code,
force result codes, change the configuration, inject recovery lines, or
filter the transmitted output.

| Typed, consecutively in one boot | Firmware output |
|---|---|
| AT | OK |
| ATI | USR009F, then OK |
| ATI6 | Link diagnostics, No Connection, then OK |
| ATY11 | Freq / Level heading, then OK |
| AT | OK |

All five calls to the result emitter get code 0. The disconnect cause
stays 0. There are no stale reports. At result emission, the buffer lengths
are 0, 1, 2, 3, 0, and the buffers contain the new command bodies.

The emulator now models that missing selection of the external board at `0xc7bf1`.
This is the boundary where the firmware has armed the command reception. The emulator writes `0xf596` to
the RX dispatch word of the firmware. All other steps stay with the firmware: prefix recognition,
buffer reset, body collection, parsing, and result emission.
The selection applies only to the external product. The internal product keeps
its own input path.

With the input path fixed, `scripted_pump` does not inject recovery lines now, and it does not
suppress stale output. Scripted and interactive sessions now send the
same literal terminal traffic.

## Evidence and reproduction

The [saved traces](../artifacts/imodem-terminal-diagnosis/README.md) include the
raw transitions of the call state, the return of the parser with carry set, the suffix-only
control, and the successful experiment with the external prefix handler.

From the root of the repository:

```sh
.venv/bin/python artifacts/imodem-terminal-diagnosis/probe.py \
  --mode raw --output /tmp/imodem-raw.json
.venv/bin/python artifacts/imodem-terminal-diagnosis/probe.py \
  --mode prefix-handler --output /tmp/imodem-prefix.json
```

The probe reads the local NVRAM file and never saves it. The raw and suffix modes
explicitly restore the former selection of the body receiver. Thus, you can still get the original failure
again after the production fix. The prefix-handler mode exercises
the corrected selection.
