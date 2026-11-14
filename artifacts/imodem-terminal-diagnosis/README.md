# I-modem terminal diagnosis, 2026-09-12

Refer to [the diagnosis](../../docs/imodem-terminal-framing.md).

All runs used these conditions:

- The local `Ie030002.nac`.
- The existing `flashnvram.sav`, loaded read-only.
- The default external enclosure.
- No DSP execution.
- Serial output without a filter, with the parity bit removed to make it easier to read.

* `raw-session.json`: AT, ATI, ATI6, ATY11, AT, ATI3, AT, with 5M
  instructions between them after a 5M warmup. It shows the keypress abort that we did not intend.
* `spaced-session.json`: ATI, ATI6, ATY11, AT, ATI3 at 20M intervals. It shows
  aborts and old diagnostics that accumulate, also when the input has wide spaces.
* `route.json`: one ATI command. It shows the parser entry, the buffer contents, `[d16f]=1`,
  the return with carry set, and the branch into call handling.
* `suffix-session.json`: CR, I, I6, Y11, CR at 20M intervals. It shows that
  when you remove the prefix, you get OK, but this alone does not reset the buffer.
* `prefix-handler-session.json`: AT, ATI, ATI6, ATY11, AT at 20M intervals
  with the diagnostic selection of the external RX handler. All five return OK.
* `verified-responses.json`: the output of the successful experiment, in groups for each
  command. We checked for five OK result codes, a zero disconnect cause, and
  no old diagnostic reports in later responses.

`probe.py` does a five-command session again in one of these modes: legacy raw, suffix-only, or
prefix-handler. Run it from the root of the repository. For its arguments, use `--help`.
The normal emulator now selects the prefix handler. Thus, the raw
and suffix modes intentionally restore the former body-receiver dispatch for
comparison. The saved traces are from before the production fix.

The JSON event count `n` is the guest instruction count. The addresses in
`state`/`mem` are offsets in segment 2600. The write-hook `address` and `pc`
values are physical addresses. The state bytes are hexadecimal, in memory order.
