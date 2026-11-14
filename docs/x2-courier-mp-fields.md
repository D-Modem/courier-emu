# Courier MP fields and the 53333 result

5 October 2026. Profile: the captured board ROM of the Courier 403, SHA-256
`f1c91621fbf14aad34547056feb4425e64fcf0b38ec5d57f86c9f432ca999db6`,
paired with `Ie030002.nac`. These addresses are for that Courier profile.
They are not for the 3453C XMF or the Quad server.

## Four-word MP and N1

The MP decoded from the line has seventeen ones, a zero, four LSB-first words with a
zero after each, sixteen LSB-first CRC bits and two trailing zeros: 104 bits.
The CRC starts at FFFF and uses the reflected polynomial 8408. It does not include the separators, and it
has no final XOR. The body `0344 03FE 0000 0500` gives CRC `14AD`.
The earlier claim that this frame fails the V.34 CRC/layout test is replaced.
It is a four-word record, not the three-word standard MP layout.

The native builder first calculates a local ceiling with E2DD. In the live call,
that result is 12. F86E saves it in 037D, and the first F895 call packs it.
F874 saves the recovered N1 at 031C. Then the delayed call at F875 executes
`SPLK @7D,#0001` in its delay slots and calls F895 again. This forces the MP
input to one, and it keeps the saved local ceiling.

F8A1 loads the allowed mask at FFF3. A661 calculates its highest set bit,
and returns a one-based ceiling. In the call, FFF3 is 7FFD and its ceiling is 15.
F8AA loads W2, masks it with 7FFF and calls A661 again: 1FFE has ceiling 13.
F8B1..F8B7 takes the smaller of 037D and the FFF3 ceiling, and combines it
with that W2 ceiling:

```
N1 = min(data[037D], bit_length(data[FFF3]))
N2 = bit_length(W2 & 0x7fff)
returned_fields = (N1 << 2) | (N2 << 6)
```

Thus, the second call returns 0344, with N1=1 and N2=13. F87C writes it
to 0940 at DSP instruction 956242670. F58F reduces W2 from 1FFE to 03FE
five instructions later. It does not build N2 again. This explains why the encoded
N2 is larger than the final mask ceiling. Later, A536 sets the acknowledgement bit of W1,
and this gives 8344 at instruction 983920584.

`tools/verify_courier_mp_fields.py` executes the original F895 packer in 1536
controlled contexts, which include empty and sparse masks. It verifies the full
returned field value and that the W4 byte is kept. These are local component
checks. They are not analogue measurements or tests of automatic call scheduling.

## W4 and the rate offset

F895..F89C writes:

```
W4 = (data[0364] << 8) | (previous_W4 & 0xff)
```

The live write trace shows that F715 clears W4, and that both F895 invocations then
write it as 0500. Thus, its low byte is zero in this MP, kept
from the clear. Its general protocol meaning is still not assigned. This
trace does not show that each peer or mode uses zero.

0364 is an additive bit-count parameter, and it is also the offset that the
rate selector uses. It is not a standalone line rate. In the separate variable-length
client path, EA82..EABC selects a one-based mask index N, stores it at 031C,
and passes `N - data[0364] + 20` at 037D to the continuation. E970..E97B
does the same conversion on the five-bit field of the local header and stores it
at 0351. E11C..E14B adds 0364 to 0351 and consumes that number of input bits.
With 0364=5, the intermediate count is N+15, but the total is **N+20**.
An original E11C execution with a return-only callback for each bit verifies this sum
in 216 contexts: counts 20..43 and additive values 0..8. Specifically, 0351=35
and 0364=5 give forty callbacks. In the six-sample allocation model,
N=20 gives K=40 and the nominal rate `40*8000/6`, or 53333 bit/s. Five is
the number of five bits in that sum. To assign those bits specifically to independent signs,
the connection of the downstream mapper/receiver is still necessary. Do not apply this interpretation
to the forced N1=1 bootstrap MP as a completed allocation.

## The bit 9 instruction

The live trace identifies F8CB (`5D80 0200`, `OPL *,#0200`, AR1=006F).
It writes 0243 at instruction 910792158. F8CD immediately adds 0800,
and writes 0A43 one instruction later. The two are in the receive check of F8BD.
The conditions are: the timer has not failed, 034B is zero, the two recovered words
0342 and 0343 agree, and 0343 is equal to 09B0. Thus, bit 9 is set as a
response to the repeated 09B0 word of the server, before the MP is built.
The later second AEDE pass uses this bit to select four bits for each symbol.

## Does the later client record explain this 53333 result

We saw no execution of the known variable-length client exchange in
these calls. The coverage gives zero for E724 (initializer path), EA82
(selector), EAB2/EABA (writes of the selected index/header), EAC7 and EAD6
(preparation of the body/acknowledgement), and E970 (conversion from header to allocation).
The separately enabled PC trace of EA82..EABC is empty. The watched 0940..0946
buffer has no later record construction after its acknowledged MP.

The live F856 trace already gets the local index 12 before the forced-one MP.
031C keeps 12, and the host reports include 006A:0A0C and later 0020:000C.
The Courier terminal prints `CONNECT 53333/ARQ/x2/LAPM/V42BIS`, while the
server prints `CONNECT 33333/ARQ/x2/LAPM/V42BIS`. Index 12 agrees with the
recovered ladder of x2 nominal rates. This supports a kept local-rate result.
It does not support the proposed causal sequence of this MP followed by the known variable
client record. The continuation audit below shows the formatter
chain of the Courier and the live MP-to-rate selector of the I-modem. The complete record
receiver of the I-modem and the payload rate are still separate verification boundaries.

## Continuation: the DSP-to-supervisor rate chain

Three more calls with a cap show the reporting path in the actual
Courier 403 / Ie030002 pair. The evidence and the original-instruction checks are in
`artifacts/x2-courier-rate-report-20261005`.

The first E2DD invocation is the F86A call. Its input is 4220, after F864
loads 4020 and F868 adds 0200. The optional subtraction of E2DD with FFF4 bit 12 is
inactive. The signed FFFB adjustment is FF00 (-256), and this takes the metric to
4120. With 039F bit 7 clear, E2EB subtracts two times 037B shifted by eight.
037B=1 subtracts 0200, and this gives **3F20**. The descending threshold search at
E2F3 tries 4680, 4100, 40C0, then 3EC0. The last is the first threshold that is not
greater than the metric. E2FC returns **12**. These are fixed-point firmware
values. We do not infer their physical measurement units here.

The threshold table of fifteen entries is at overlay-1 program C77D, and it is
available at data CF2C. Its threshold at index 12 is 3EC0, and its threshold at index 13
is 40C0. Thus, 3EC0 <= 3F20 < 40C0. An original E2DD execution verifies
the two sides and the equality at each threshold, which includes duplicate thresholds:
46 cases. Later training invocations can return other indices. They do
not replace the value that the first F874 write saved in these calls.

The native reporting sequence is:

| Stage | Original instructions | Effect in the call |
| --- | --- | --- |
| Retain local ceiling | F86E, F86F, F871..F874 | Store 12 at DSP 031C |
| Force peer-facing MP N1 | F875 delay slots F877 | Set 037D=1; preserve 031C |
| Queue rate-report tag | E20A..E20C through 83B1 | Queue 806A |
| Resolve the other direction | E19C..E1A2 through A63A | Save 10 at 087A |
| Build report argument | E1A3..E1AC | Form (10<<8)+031C = 0A0C; queue through 83B1 |
| Receive tag 6A | Supervisor 93CD9..93D08 | Set x2 mode and call 94399 |
| Decode mailbox argument | 94399..943C1 | Read 5E high then 5C low; mask low with 001F; store 12 at 0A19, 0A27, 0A17 |
| Resolve result enum | 82FB9..83052 | x2 branch uses 0A27 and result/ARQ flags; return E3 |
| Select literal suffix | 89F57..89F5F | A1EB[E3] points to AC78, literal 53333/ARQ/x2 |
| Print CONNECT prefix | 89F78 -> C800:0044 -> CA811 | Emit CONNECT and continue normal result output |

E1A8..E1AB selects 031C while FFF4 bit 1 is clear. Its alternative uses 0347.
The high-byte resolver follows the N2 of the peer and the local mask, and it returns ten
in this call. It is not the x2 displayed-rate selector of the Courier. The wire
N1 value one does not overwrite the saved local index twelve.

The new supervisor write trace shows that 0A27 becomes 000C when tag 6A is
consumed, and that 93D77 keeps it. The original result selector with
0238 bit 2 set, 04E2=3 and 022A bit 0 set returns E3. The literal is at
physical 8AC78. A later disconnect reset at 88964 changes 0A27 to one.
Thus, a final RAM peek alone gives the misleading value one, although
the connection was reported from twelve. The native callbacks for supervisor memory writes
record the next instruction pointer. For example, the recorded 943AA
identifies the store at 943A7. The DSP write traces give the actual writer.

The original x2 result table is not linear at its two lowest entries:

| One-based rate index | Nominal result bit/s |
| --- | --- |
| 1 | 33333 |
| 2 | 37333 |
| 3..15 | floor((index+28)*8000/6) |
| 12 | 53333 |

The DSP report builder passes 45 controlled contexts. It keeps MP N1=1
while the saved indices and masks change. The original supervisor handler,
the result selector and the pointer lookup pass 150 contexts that cover all fifteen
indices, high bits of the low byte, verbosity and ARQ flags. This verifies the behavior of the original
firmware. It is not a replacement rate calculation on the host.

## Continuation: what the same MP does on the I-modem

The live CFF4 selector of Ie030002 calls ABBC with direction one. Its x2 branch
at AC07..AC26 reads W1 at 0340, extracts N1, and intersects its ceiling with
the local allowed mask F6D9. For the received 0344 and the local mask 7FFF, this returns
one. CFF8 subtracts one, CFF9 stores zero at 03A2, and CFFC reads the first
entry of table D24A into 03C0: **19**. The live PC trace records the returned
one at CFF8, zero at CFF9, W4=0500 at D009, and its high byte five at D00C.
The working MP cells stay 0344/03FE, and the I-modem terminal reports
CONNECT 33333/ARQ/x2/LAPM/V42BIS.

The selector and the D24A table are in image 6 of Ie030002, loaded at A000. They are not in
the overlapping image-11/image-10 pair. Fifteen original selector contexts
verify each N1 ceiling against the same full local mask. The table entries are
19,22,25,26,...,37. This agrees with the first two special indices of the shared nominal ladder.
The sampled 03C0 value shows the selected allocation.
It is not a measured payload throughput at the terminal.

The high byte of W4 has a direct effect on the source count of this receiver branch.
D00C stores it at 03ED. CC95..CC99 removes that number of bits from the source
ring into 03E3. The amplitude extraction that follows removes 03C0 bits. An original
CC95..CCBE execution verifies the total cursor advance **B+MD** for all
fifteen amplitude entries and MD=0..6, with a zero cursor and with a wrapping cursor:
210 contexts. CE85..CE99 sends the MD bits through the differential-sign
recurrence, while the branch for MD not six prepares the remaining sign choices.
This identifies five as the supplied sign-bit count in the I-modem branch. It
does not assign each use of Courier 0364 to the same downstream function.

In this live selected context, B=19 and MD=5 give **24 source bits for each invocation of the
bit consumer**. This is different from the K=25 of the nominal table for index one.
Thus, the displayed label of the firmware does not itself verify the usable
payload rate. The callback cadence and the full data path must be connected before
we can change this local bit count into a claim of measured throughput.

Thus, the reported asymmetry is explained without the variable-length client exchange,
which did not execute: **the Courier keeps and displays 12, and
the MP supplies N1=1 to the transmit selector of the I-modem**. The hypothesis of a later variable
record is not necessary for these observed CONNECT results.
This does not yet show that the short MP alone completes each receiver
state, or that 53333 is the measured usable payload rate.

## Evidence and reproduction

`artifacts/x2-courier-mp-20261005` keeps the original listings, the component
verification, compact live traces of the flag and buffer writes, and the coverage results.
We examined the raw call results and dumps before we made these compact extracts.
The record extract starts at instruction 745909000, because the
same buffer was used much as training scratch before it became the MP.

```
.venv/bin/python tools/verify_courier_mp_fields.py
COURIER_DSP_TRACE_LIMIT=10000 COURIER_DSP_DUMP=/private/tmp/x2-mp-flags \
.venv/bin/python tools/probe_imodem_analog_pair.py \
  --analog-settings 'X1S27=1S54=0S58=48&A3&B1Q0&U26&N39' \
  --imodem-settings 'S54=0S58=48&A3&B1Q0' \
  --imodem-nvram artifacts/imodem-pair-x2-full-rate-routed-20261002/nvram-230400-switch2.sav \
  --instructions 300000000 --analog-instructions 220000000 \
  --analog-dsp-write-watch 006f --analog-dsp-trace-range f856:f8b8 \
  --analog-dsp-peek 0364 --analog-dsp-peek 037d --analog-dsp-peek 031c \
  --output /private/tmp/x2-mp-flags-call
```

For the buffer run, use `COURIER_DSP_WATCH_LAST=0946`, watch 0940, and set the
PC range to EA82:EABC. Use different output/dump directories. A full-length
call can reset the DSP and discard its earlier trace. The call with a cap keeps
it. Wide ranges that contain frequently used signal-processing scratch can fill the trace
and make the run slow. Narrow field ranges keep the related writes efficiently.

For the continuation run, add `--analog-mem-watch 0a17:0a28`, watch DSP 031C,
and use `--analog-dsp-trace-range e2dd:e307` for the threshold arithmetic. In a
separate call, use `--dsp-trace-range cff4:d01c` for the I-modem selector.
For the component checks, run `.venv/bin/python tools/verify_courier_rate_report.py`.
The compact live extracts keep the original writes and PC traces.

## Continuation: the upstream E boundary

A separate upstream E event follows the short MP. The Courier script
AE83 is the triplet `AF2E,0,5`, then `AF99,0,0`. With 006F bit nine set,
AF2E does not double the five-symbol count. AF38 supplies nibble 000F to
the same AF7D scrambler/16-point transmitter that MP uses. That is five
four-bit all-one source symbols, twenty decoded ones, before the data mapper
initializer AF99. This does not identify the complete B1 frame that follows.

AABF of Ie030002 clears its counter of consecutive ones. A881..A889 increments
0323 for a one and clears it for a zero. Then it calls the saved bit coroutine.
AAC4..AAC6 waits for seventeen ones, and AACB..AACD waits for twenty before
it jumps to A891, which runs the data receiver initializer AAD3. A zero after
the seventeen-one sync returns to the record parser at A941. It is not an
E acknowledgement. `tools/verify_x2_upstream_e.py` executes the original
dispatcher and coroutine in nine contexts: sixteen through nineteen ones
wait, twenty go into A891, and an interrupted nineteen-one prefix returns to
the record path. The harness starts after the record is accepted. It does not
reconstruct that acceptance or demodulate audio.

The MP receiver of v90modem now finds the boundary of twenty consecutive ones on a
hypothesis that already has two matching CRC-valid MPs. Bits in an MP
body cannot add to that run. The kept PCMU fixture includes the
E boundary: detector sample 11434 in the bearer samples 88640..100959,
or absolute sample **100074** (12.50925 s, detector time that includes the filter
latency). Input blocks of 1, 17 and 160 give the identical sample. This is
a timestamp of the receive detection. It is not the unfiltered transmitted E endpoint.

The full engine replay keeps INFO0=21FF, marker=4D, MP=0344/03FE/0000/0500,
and the downstream startup/payload activation, and it now records upstream E.
An opt-in `ME_X2_UPSTREAM_ACQUIRE=1` experiment prepares the existing V.34
T/3 receiver for 3200/high, N=10 (24000 bit/s), linear encoding and a 16-state
trellis. Then it starts B1 acquisition on E. It does not acquire the kept
recording. The template fit stays below 25 percent, and the engine stays
in TRAINING. Thus, E reception does not give an upstream data lock.
The next boundary is the AF99/AFC9/B006 mapper reset and framing of the Courier,
compared with the B1 template of the receiver. This failure does not give a reason to adjust the E threshold
or the rate label.

The original listings, the component results and the two engine replay logs are saved
in `artifacts/x2-upstream-e-20261005`. The acquisition experiment stays
off by default. We do not claim a CONNECT or a decoded upstream payload.

### Continuation: upstream B1 acquisition

The fresh original trace of the Courier at B1A1..B1C2 confirms the upstream rate N=10:
B1B4 holds ACC=000A before the A71B mapper builder. The built parameters
are B=60 bits for each eight symbols and Q=3. Thus, 60*3200/8 = **24000 bit/s**.
This upstream rate is independent of the downstream N1=1 and of the five signs of W4.

A controlled execution of B1A1, AF99 and B006 from the kept original DSP
snapshot gives the same 480 mapper symbols. If we seed the received word 0340=F37C,
the mask 0941=03FE, the direction 039F=4060 and the baud index 03DB=4, we get expanded
shaping and the 64-state trellis. Against the all-one reference of SpanDSP,
minimum/16-state agrees with only 49 complex symbols. Expanded/64-state agrees with
475, and all 480 amplitude norms agree. Five remaining rotations need
more analysis of the mapper/frame epoch. The seeded execution does not give
a complete decode of the MP fields on the wire.

The captured audio resolves the acquisition choice independently. A search of
minimum/expanded shaping for x2, together with the existing scrambler/trellis
candidates, selects GPA, expanded shaping and 64 states with a **99.9% fit**.
The independent check of 256 symbols after B1 has a mean lattice distance of 0.252,
and a mean power of 147.2 against the template power 147.7. The 95% acceptance threshold
and the validation after B1 do not change. The selected shaping and trellis
are kept for DATA decoding, and x2 acquisition now runs by default.
The recorded regressions pass at block sizes 17/160 and reject silence. All
402 cases of the V.34 data decoder pass. The evidence and the original-instruction
reproduction are in `artifacts/x2-upstream-b1-20261005` and
`tools/verify_x2_upstream_b1.py`.

This closes the earlier B1 acquisition failure. Upstream DATA has many
shell/frame errors, and it is not a verified payload stream. The engine still
stops in TRAINING and gates CONNECT/user bits. As the next step, resolve the inversion epoch of the mapper/frame
and verify V.42/LAPM upstream before you open that gate.
