# Quad x2 downstream / V.34 upstream — directional verification

The two CONNECT suffixes do not identify two separate PCM directions.
QF060003 reports `33333/ARQ/x2/LAPM` initially while the analog 403 caller
reports `52000/ARQ/x2/LAPM`. Their actual upstream/downstream parameters
must be read from the original DSP reports and active datapump.

The original server handler at physical `d575f..d57ce` consumes tag `6a`:
the low five bits become `894d`/`8958`, and the high five bits are translated
into `894e` on the asymmetric server branch. The CONNECT selector at
`c2974..c298a` calls `e2700..e272f`, which reads **894e**, then selects its
x2 result string. It does not print the V.34 receive index from `894d`.
Thus its `33333` string is a PCM result index, not a 33333-bps upstream.

The analog report builder has the reciprocal layout: the high byte is the
V.34 transmit index and the low byte is its retained PCM receive index.
The original-instruction audit is in
[Courier MP fields](x2-courier-mp-fields.md#continuation-the-dsp-to-supervisor-rate-chain).
That audit also explains why retained local PCM indices and the initial
CONNECT labels can differ between peers.

The saved 2026-10-19 call contains these reports:

| Endpoint | Initial tag 6A | Last tag 6A | Last V.34 index | Last PCM index |
| --- | --- | --- | --- | --- |
| Quad server | `010a` | `0c0b` | 11 | 12 |
| Analog caller | `0a0b` | `0b0c` | 11 | 12 |

The initial V.34 index is ten (24000 bps) at both peers. After rate
renegotiation both report eleven (26400 bps); the last PCM index twelve
has the nominal firmware label 53333. These are negotiated parameter
reports, not measured DTE throughput. The original CONNECT text remains
unchanged after these rate updates.

Quad's active receive callback is `a44d`, also selected in the passing
V.34-only control. The checker additionally verifies the active code at
`a44d..a57f` against the stock common datapump, rather than identifying an
overlay solely by its address. Its source is flat offset
`53e02 + 2*(a44d-a180)` in `Qf060003.zip`'s flattened controller image.
The asymmetric PCM transmit callback is `c395`; the V.34-only control uses
`c354`, and the symmetric x2 control uses `f5da`/`f5e9` instead.

`--check-x2-v34` requires the existing duplex payload, execution-health,
carrier and shared-duration checks, asymmetric server selection, PCM TX
and common V.34 RX callbacks, a matching active RX code fingerprint, valid
directional indices and agreement between the latest original DSP reports.
It does not rewrite firmware flags, rates, payloads or CONNECT strings.

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_analog_pair.py \
  --check-x2-v34 --output /tmp/quad-x2-v34
```

Recheck the original saved capture independently when the local capture is available:

```sh
.venv/bin/python tools/quad_directional_link.py \
  artifacts/quad-asymmetric-peer-retest-20261019/analog.log \
  artifacts/quad-asymmetric-peer-retest-20261019/quad/results.json \
  --program artifacts/quad-asymmetric-peer-retest-20261019/quad/negotiation-dsp-program.bin
```

New reports include the active-code fingerprint, so `--program` is only
needed when replaying older captures. Regression tests replay the directional
records and receive-code fingerprint extracted from that capture and reject
symmetric selection/rates, the V.34-only transmitter,
a different receiver or overlay, absent reports and conflicting peer rates.

The [fresh peer run](../artifacts/quad-x2-v34-directional-20261019/README.md)
passes the directional verifier and duplex payload checks through the shared
3000-frame boundary, with retained carrier and no connected PCM/UART losses.
That is 60 seconds including training and short marker data, not a sustained
throughput soak. The focused regression selection passes 77 tests.
