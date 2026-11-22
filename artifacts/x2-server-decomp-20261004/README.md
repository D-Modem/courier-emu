# x2 server DSP reconstruction

This bundle adds manually reconstructed C for the **pre-V.90 I-modem
IM020104** server/symmetric image, plus separately identified **QF060003
Quad** PCM helpers from the later dual x2/V.90 build. These are semantic
equivalents of selected routines, not original source or a complete server.

## Artifacts

- `x2_server_lift.c`: I-modem mailbox, capability packing, bit reversal,
  mode dispatch, scramblers, width setup, training source, startup probe source
  and sample callbacks, local PA6 payload lanes and receive octet assembly.
- `quad_pcm_lift.c`: Quad parameter setup, codeword-table copy and selectors.
- `server-focused.asm`: original words and instructions, including the
  asymmetric callback chain surrounding the lifted routines.
- `image-5.asm`, `image-11.asm`, `image-10.asm`: full linear I-modem listings.
- `quad-pcm-focused.asm`: the corresponding Quad helpers and their tables.
- `verification.json`: firmware fingerprints and C/native comparison results.
- `../../tools/recover_x2_server.py`: extraction and verification script.

Full linear listings also include data that decodes as instructions. They
must not be interpreted as a reachability analysis.

## Source identity and program map

IM020104 is extracted from `docs/x2/im020104.zip`, member `IM020104.NAC`.
Its flattened flash starts at physical `40000`, SHA256
`e92a53f87b188911fb5961bf7ba4d219c7a4ade9627aa760813228b0a7b6ad8f`.
The existing supervisor-derived map in `tools/imodem_x2_map.py` selects:

| Image | Source segment | Bytes | DSP origin |
|---|---|---|---|
| 5 | e005 | 2322 | 8000 |
| 11 | d84c | 7b86 | 9194 |
| 10 | d4ef | 35c2 | d000 |

The Quad source is `docs/x2/Qf060003.zip`, flattened SHA256
`61a8f031c7cdf94daad748cded191f8287757254bc3a3657609a7426ca2dca2d`.
Its resident/PCM-core/larger-PCM-mode combination comes from the recovered
map used by `tools/probe_quad_pcm_codewords.py`.

## Reconstructed server chain

Host tag `70` reaches DSP `91a1`, masks the capability word with `3fff`,
stores it at `[ffdb]`, and ORs `[ffd9]` with `8000`. Tag `71` stores the
rate word at `[ffda]` without the client's 15-bit mask.

At `927f`, `[039f]` bit 12 chooses `[ffdb]` instead of `[ffdc]`. The routine
zeros the two-word `[fef0:fef1]` work area and tail-calls the field writer
`9617` at offset 16. The C lift follows that writer through its return:

```c
word = (flags_039f & 0x1000) ? capability_ffdb : capability_ffdc;
fef1 = word << 15;
fef0 = ((int16_t)word) >> 1;  /* SXM=1 in the verified entry context */
```

Thus this server has a verified route from the x2 command into its INFO0
capability buffer. That link remains unresolved in the 3453C client lift.

The sample callback path is also reconstructed:

```text
TX e65f: source 83c4 -> mask -> optional GPC scramble 8faa
          -> optional octet reversal e7e7 -> ff01 + width ff0c -> sample
RX e67b: sample -> ff00 -> optional reversal e7e7 -> mask
          -> optional GPC descramble 8fe1 -> sink dispatch 847e
```

Both directly called scrambler entries use the GPC (18,23) recurrence.
The surrounding receive routine also has another entry/branch; the lift
models the **actual direct entry `8fe1`**, not a generic GPA receiver.
TX state is relative to the caller's DP page: the ordinary callback uses
DP=7, so its history is `[03d8:03d9]`. RX switches to DP=6 and uses
`[031e:031f]`. Treating both histories as fixed DP=6 cells would be wrong.

The callback comparison deliberately closes `[006f]` source/sink gates and
preloads the input word. It verifies the complete transform/write portion,
including original subroutine calls; it does not verify the supervisor's
payload queues or the sink's byte-delivery state machine.

## Digital width and training

`e5e7` installs matching TX/RX widths and masks from mode bit 0:

| Mode bit 0 | Width | Mask |
|---|---|---|
| clear | 8 | 00ff |
| set | 7 | 007f |

`e172` selects a pattern path (`e60b`) on mode bit 2, calls the alternate
initializer `e822` on bit 1, and otherwise reaches `e61d`. The checks stop
at those destinations; they do not claim every initializer is fully lifted.

The pattern source `e4d1` packs a repeated `7e` byte into the selected width
through a bit reservoir. The lift matches 256 consecutive words at each
width. The callback masks the reservoir output; the source routine itself
does not remove its upper buffered bits.

These seven/eight-bit routines serve the digital-bearer/server/symmetric
machinery. **Seven bits at 8 kHz is digital 56000, not the analogue x2
56000 rate in a six-symbol PCM frame.** The actual analogue downstream
constellation mapper is not fully reconstructed by this bundle.

## Quad PCM helpers

The stock controller source copies now validate all seven corrected overlay
flat offsets across four modem RAM banks. Earlier extraction placed each
overlay two bytes too early; no leading word is dropped by the downloader.
The resident offset is unchanged. See
`../x2-mapper-negotiation-20261004/placement-verification.json`.

The regenerated QF lift and tests use the corrected complete sources:

- `c7ad` sets four working parameters from `[ffd9]` bit 0.
- `c9bf` copies nine codewords from program `c9ce` or `c9d7`, selected by
  bit 2, to a caller-provided destination.
- `c994`/`c9a5` select program words using bit 2 and submode `[03e4]`;
  `c9b6` chooses table base `cc2b` or `cb00`.

The earlier extra leading codeword and EF00 selector output were source
extraction errors. The corrected constructor and its startup consumers also
execute together in 128 seeded contexts. The separate mapper bundle adds
13,504 C comparison cases for received-record transfer, unpacking and six
position preparation. These are shared x2/V.90 helpers; complete proprietary
x2 payload mapping remains open.

## Verification

```sh
.venv/bin/python tools/recover_x2_server.py
```

The script compiles both C lifts with `clang` and compares them against the
original instructions in the native C5x emulator. The original **6,562 cases**
are listed below; the payload-path additions bring the total to **9,122**:

| Check | Cases |
|---|---|
| Tags 70 / 71 | 128 each |
| All octet reversal inputs | 256 |
| Mode-family entry destinations | 8 |
| Consecutive asymmetric startup source calls | 4,096 |
| Capability selection / complete field packing | 128 each |
| TX / RX scramblers, widths 1..9 | 288 each |
| Width setup | 2 |
| Continuous training words, widths 7/8 | 512 |
| TX / RX preloaded sample callbacks | 256 each |
| Quad PCM helpers | 88 |

The startup source at `e1d2/e1dd/e1ea/e1f2` returns 1,747 `007e` words,
seven zero words, then 128 pairs `(0,255)` through `(127,128)`. Its
2,010-call cycle repeats; the delayed-return pointer updates are verified.
These are source words before sample transforms, not established wire
durations or proof of a V.90 Sd-equivalent signal.

No modem hardware is accessed. Full-call negotiation, the asymmetric
receive training state machine, the downstream constellation mapper and
end-to-end payload buffering remain open.

## Symmetric startup receiver (bounded lift)

The receiver helpers around `e2b1`, `e2d4`, `e2db`, and `e438` are now modeled
in `server_training_receiver_step`/`server_training_receiver_pair`. The lift
covers the observed qualification contract: seven `007e` run-in words,
seven zero separator words, then 128 ascending/complement pairs. A one-bit
low-order tolerance is accepted and recorded in a six-phase bitmap (both
words of each delayed pair contribute); a bad word restarts acquisition. This is intentionally a protocol-level lift, not
a claim that the delayed callback ABI and every report/timeout side effect of
`e438` have been recovered. Those remain targets for native instruction
comparison.

## PA6 payload lanes and open receive sink (2026-10-13)

The lift now also covers local source `843e..8456`, local sink `84a0..84ae`,
and receive octet assembly `8483..8499`. There are **9,122** total comparison
cases, including 2,560 payload-path cases:

| Check | Cases |
|---|---:|
| Local source, six lanes, ready/empty, reset flag | 384 |
| Local sink, six lanes, ready/full, reset flag | 384 |
| Reservoir, widths 7/8/9, every residual count, ready/full | 768 |
| Original RX callback with sink gate open | 256 |
| Bit-15 source: PA6 fallback and patched-port stream | 384 |
| Bit-15 sink: PA6 fallback, duplicate filter and patched-port stream | 384 |

The local path requires `[039f]` bit 15 clear; its set branch is now lifted
as `server_stream_source`/`server_stream_sink` from `e6fe`/`e732`. That
bit-15 path is page-sensitive: normal TX DP=7 and RX DP=6 fall back to
PA6. Other pages use DP=13 storage and self-modify the IN/OUT operand from
`[0987]`/`[09a7]`, respectively. The verified stream cursor range is
`0062..0067`, wrapping to `0062`; these are actual port operands, not six
slots all read through port `0062`. Status masks shift by the cursor's low
four bits (plus eight for the sink). Data address `0057` aliases board
status/ack port `0057`, and **both** directions acknowledge successful
transfers. The source sets its empty sentinel to `ff00` before dispatch.
The sink suppresses only repeated `ff00` when page offset `71` bit 1 is
**set**; repeated ordinary payload is delivered. Its last-word cell updates
even when a full sink drops the word. These corrections replace the earlier
unverified alternate-stream interpretation. The PA6 path remains separate: low bits
0..5 mean an input word is present in `0058..005d`. High bits 8..13 mean the
host has made the corresponding output lane available. Incoming and outgoing
holding registers are separate. Consumption writes a single mask back to
PA6, clearing only that bit. The PA6 source resets its cursor to `0058`
only on an empty read with `[039f]` bit 14 set, and otherwise preserves the
caller-supplied empty sentinel.

The receive reservoir appends sample bits least significant first and emits
octets whenever its count reaches eight. It advances the reservoir even when
the sink is full: no retry and no cursor advance on that dropped octet. An
8-bit sample with residual bits retains its alignment; a 7-bit sample carries
residual bits across callbacks. Width 9 with seven residual bits emits two
octets and is checked as a boundary case, not claimed as a DS0 mode.

The open-sink comparison enters the original `e67b` callback with `[006f]`
bit 3 set and `[0326]=8483`. It verifies sample capture, optional reversal,
optional GPC descrambling, octet assembly, outgoing lane values and PA6
acknowledgements together. The earlier preloaded checks remain valid and
still close their source/sink gates. This extends verified emulator coverage
through both firmware payload-delivery branches; it does not establish a
negotiated call or the supervisor's end-to-end terminal buffer. The standalone
`tests/test_x2_server_lift.py` covers the alternate ring, acknowledgement,
reset, duplicate suppression, and wrap behavior. The recovery script also
executes the original bit-15 dispatch and both helpers in 768 contexts,
checking normal-page fallback, all six alternate port operands, full/ready
status, reset flags, filter flags and repeated/nonrepeated words. Scratch
ST0 saves and program patch writes are outside the C data-effects contract;
the native checks execute those instructions rather than bypassing them.
