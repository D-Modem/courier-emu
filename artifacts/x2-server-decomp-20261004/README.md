# x2 server DSP reconstruction

This bundle adds C code that we reconstructed manually for the **pre-V.90 I-modem
IM020104** server/symmetric image. It also adds the **QF060003
Quad** PCM helpers from the later dual x2/V.90 build, which we identified separately. These are semantic
equivalents of selected routines. They are not original source or a complete server.

## Artifacts

- `x2_server_lift.c`: I-modem mailbox, capability packing, bit reversal,
  mode dispatch, scramblers, width setup, training source, startup probe source
  and sample callbacks.
- `quad_pcm_lift.c`: Quad parameter setup, codeword-table copy and selectors.
- `server-focused.asm`: the original words and instructions. This includes the
  asymmetric callback chain around the lifted routines.
- `image-5.asm`, `image-11.asm`, `image-10.asm`: full linear I-modem listings.
- `quad-pcm-focused.asm`: the related Quad helpers and their tables.
- `verification.json`: firmware fingerprints and results of the C/native comparison.
- `../../tools/recover_x2_server.py`: the extraction and verification script.

The full linear listings also include data that decodes as instructions. Do
not interpret them as a reachability analysis.

## Source identity and program map

IM020104 is extracted from `docs/x2/im020104.zip`, member `IM020104.NAC`.
Its flattened flash starts at physical `40000`, SHA256
`e92a53f87b188911fb5961bf7ba4d219c7a4ade9627aa760813228b0a7b6ad8f`.
The existing map in `tools/imodem_x2_map.py`, derived from the supervisor, selects:

| Image | Source segment | Bytes | DSP origin |
|---|---|---|---|
| 5 | e005 | 2322 | 8000 |
| 11 | d84c | 7b86 | 9194 |
| 10 | d4ef | 35c2 | d000 |

The Quad source is `docs/x2/Qf060003.zip`, flattened SHA256
`61a8f031c7cdf94daad748cded191f8287757254bc3a3657609a7426ca2dca2d`.
Its combination of resident, PCM core and larger PCM mode comes from the recovered
map that `tools/probe_quad_pcm_codewords.py` uses.

## Reconstructed server chain

Host tag `70` goes to DSP `91a1`. That code masks the capability word with `3fff`,
stores it at `[ffdb]` and ORs `[ffd9]` with `8000`. Tag `71` stores the
rate word at `[ffda]` without the 15-bit mask of the client.

At `927f`, `[039f]` bit 12 selects `[ffdb]` and not `[ffdc]`. The routine
sets the two-word `[fef0:fef1]` work area to zero and tail-calls the field writer
`9617` at offset 16. The C lift follows that writer until its return:

```c
word = (flags_039f & 0x1000) ? capability_ffdb : capability_ffdc;
fef1 = word << 15;
fef0 = ((int16_t)word) >> 1;  /* SXM=1 in the verified entry context */
```

Thus, this server has a verified route from the x2 command into its INFO0
capability buffer. That link is still not resolved in the 3453C client lift.

We also reconstructed the sample callback path:

```text
TX e65f: source 83c4 -> mask -> optional GPC scramble 8faa
          -> optional octet reversal e7e7 -> ff01 + width ff0c -> sample
RX e67b: sample -> ff00 -> optional reversal e7e7 -> mask
          -> optional GPC descramble 8fe1 -> sink dispatch 847e
```

The two scrambler entries that are called directly use the GPC (18,23) recurrence.
The receive routine around them also has a different entry/branch. The lift
models the **actual direct entry `8fe1`**, not a generic GPA receiver.
The TX state is relative to the DP page of the caller. The ordinary callback uses
DP=7, thus its history is `[03d8:03d9]`. RX changes to DP=6 and uses
`[031e:031f]`. Do not think that the two histories are fixed DP=6 cells, because that is not correct.

The callback comparison intentionally closes the `[006f]` source/sink gates and
preloads the input word. It verifies the complete transform/write part,
with the original subroutine calls. It does not verify the payload queues of the supervisor
or the byte-delivery state machine of the sink.

## Digital width and training

`e5e7` installs matching TX/RX widths and masks from mode bit 0:

| Mode bit 0 | Width | Mask |
|---|---|---|
| clear | 8 | 00ff |
| set | 7 | 007f |

`e172` selects a pattern path (`e60b`) on mode bit 2. It calls the alternative
initializer `e822` on bit 1. In other conditions, it goes to `e61d`. The checks stop
at those destinations. They do not claim that each initializer is fully lifted.

The pattern source `e4d1` packs a repeated `7e` byte into the selected width
through a bit reservoir. The lift agrees with 256 consecutive words at each
width. The callback masks the reservoir output. The source routine itself
does not remove its upper buffered bits.

These seven/eight-bit routines are for the digital-bearer/server/symmetric
machinery. **Seven bits at 8 kHz is digital 56000. It is not the analogue x2
56000 rate in a six-symbol PCM frame.** This bundle does not fully reconstruct the actual
constellation mapper of the analogue downstream.

## Quad PCM helpers

The source copies of the standard controller now validate all seven corrected overlay
flat offsets across four modem RAM banks. The earlier extraction put each
overlay two bytes too early. The downloader does not drop a leading word.
The resident offset did not change. Refer to
`../x2-mapper-negotiation-20261004/placement-verification.json`.

The regenerated QF lift and the tests use the corrected complete sources:

- `c7ad` sets four working parameters from `[ffd9]` bit 0.
- `c9bf` copies nine codewords from program `c9ce` or `c9d7`, as bit 2 selects,
  to a destination that the caller supplies.
- `c994`/`c9a5` select program words with bit 2 and submode `[03e4]`.
  `c9b6` selects table base `cc2b` or `cb00`.

The earlier extra leading codeword and the EF00 selector output were errors of the source
extraction. The corrected constructor and its startup consumers also
execute together in 128 seeded contexts. The separate mapper bundle adds
13,504 C comparison cases for the received-record transfer, the unpacking and the preparation of six
positions. These are shared x2/V.90 helpers. The complete proprietary
x2 payload mapping is still open.

## Verification

```sh
.venv/bin/python tools/recover_x2_server.py
```

The script compiles the two C lifts with `clang`, and compares them with the
original instructions in the native C5x emulator. **6,562 cases pass**:

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
2,010-call cycle repeats. The delayed-return pointer updates are verified.
These are source words before the sample transforms. They are not established wire
durations, and they do not prove a signal that is equivalent to the V.90 Sd.

No modem hardware is accessed. These items are still open: the full-call negotiation, the asymmetric
receive training state machine, the downstream constellation mapper and the
end-to-end payload buffering.
