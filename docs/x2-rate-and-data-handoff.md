# PCM received record to rate banks and payload source

4 October 2026. This document executes the server PCM handoff of QF060003.
It starts at the decoded input bits and continues through the record
acceptance, the rate selection, the bank construction, the mapped output and
the activation of the payload source. We use the larger C300 PCM overlay with
039F=8040 (bit 7 clear), SPM 1 and the constant-one cell 03FB=1. This is
evidence about shared PCM firmware. It is not yet an established x2 call, a
demodulator test or a proof that the client negotiates each seeded record.

## What the original instructions now establish

| Stage | Original entry or cells | Executed effect |
| --- | --- | --- |
| Receive bit dispatch | A9EA, 0320, 0322, 0343 | Dispatches decoded bits through the saved receiver continuation |
| Framed record receiver | AAA4 through AAF8 | Collects four words and examines the CRC before it commits the parameters |
| Commit accepted record | AB06, AB24 | FF48/FF49 to 0340/0341; FF4A/FF4B to E8F1/E8F2 |
| Schedule handoff | AA45, 03CD | Selects program script C7E7 for the tested local mode |
| Startup samples | B096, C7E7, C4AB/C4AD | Six sample callbacks, then selects C52A |
| Select rate and construct banks | C52A, C85E, AC34, C862 | Selects the rate from the peer limit and the local mask, then constructs all six banks |
| Mapped sample phase | C544, C5DF, C642 | Groups scrambled bits and sends six codewords for each frame |
| Payload source activation | C52E after 0FF0 samples | Sets 006F bit 2 and FFD9 bit 1, puts 0003 in the queue, installs source 84FB |

These integrated tests do not give a preselected rate to C862. After the
record reception, the harness does not write a working record or a mapping
bank. The harness supplies the local call state, the allowed-rate mask, the
synthetic decoded input bits and the source octets. C840 initializes the
original startup banks before AA45 selects the handoff script.

## Tested record framing and CRC

In the tested receiver branch, the framing is this sequence:

1. At least seventeen one bits.
2. One zero.
3. Four LSB-first 16-bit words. A zero separator follows each word.
4. Sixteen LSB-first CRC bits.

The CRC starts at FFFF and updates as follows:

```
v = crc XOR incoming_bit
crc = (v >> 1) XOR (0x8408 if v & 1 else 0)
```

The tested comparison has no final XOR. The CRC does not include the
separators. AAA4 initializes the receiver continuation. Then the harness calls
the original A9EA bit dispatcher. It does not inject decoded words. AAF8
compares the calculated CRC and the received CRC. Only the branch where they
agree gets to AB06 and copies the staging record to the working parameters.
Corrupt packets can overwrite the staging buffer, but they do not commit the
working record.

This four-word PCM record receiver is different from the receiver for the
short proprietary seven-bit directional announcement, which is still not
identified. Do not present it as a recovery of the framing of that
announcement.

## Rate selection

For the tested PCM transmit direction, C85E supplies direction selector one to
AC34. The peer ceiling is in bits 2 through 5 of received word zero. AC34
masks the local allowed-rate word FF39 with a ceiling mask and finds its
highest remaining bit:

```
peer_limit = (received_word_0 >> 2) & 15
eligible = local_mask_FF39 & ((1 << peer_limit) - 1)
selected_local_index = eligible.bit_length()
builder_table_index = selected_local_index - 1
```

Bit zero permits local index one. Bit fourteen permits local index fifteen.
This selects the highest allowed index below the peer ceiling, also for sparse
local masks. With peer limit fifteen and local mask 3FFF, the result is index
fourteen (B=36). With mask 0081, it is index eight (B=30). With mask 7FFF, it
is index fifteen (B=37). These agree with 56000, 48000 and 57333⅓ bit/s when
the record independently supplies MD=6.

The peer ceiling, the local index, B and MD are different values. The received
record also carries mode and position controls, which select the row and the
contents of the bank descriptor. The handoff does not search all possible
constellations for the channel. It consumes the selected record.

In the resolver tests, a zero eligible mask returns index zero. The harness
does not give that sentinel to C862. The upstream refusal/fallback path is
outside the integrated success cases. Other AC34 directions and the branches
for 039F bit 7 are outside the verified scope of this formula.

## Later source activation

Program C7E7 holds callback/parameter/count triplets:

```
C4AB, 01FF, 0006
C52A, 0000, 0FF0
C52E, 0000, 0000
0000
```

B096 loads the first triplet. The tail of the sample output decrements the
count and advances the script. C52A resolves the rate, constructs the banks,
sets an eight-bit source width/mask and replaces its callback with C544. The
0FF0 sample countdown continues through that replacement. After 4080 mapped
samples, it advances to C52E. C52E enables the source gate and sets FFD9 bit
one. It puts word 0003 in the queue through the original 86CD, initializes the
source state and installs 84FB. Then it continues at C544. This test does not
show the host interpretation of 0003 or the complete delivery of the external
byte queue.

The harness keeps the bit ring supplied through original B2BA calls. This
makes uninterrupted scheduler execution possible and isolates the transition
from the external source queues, which are not reconstructed. It does not show
that the 4080 earlier mapped samples carry terminal payload in an actual call.

## Verification and remaining boundary

Run `.venv/bin/python tools/trace_x2_rate_handoff.py`.

- 1249 comparisons of rate mask and peer limit. These include all one-hot bits
  against all fifteen nonzero ceilings, random sparse masks and zero masks.
- 128 accepted four-word records and 256 rejections of corrupted records.
- 40 integrated contexts from record to rate/bank/data. These cover all
  fifteen local indices, the two output states, more rate-15 bank variants and
  the decreases that sparse local masks cause.
- 1280 exact-symbol frame inverses across 7680 continuously dispatched samples.
- One complete 57333 scheduler countdown through the activation of the payload
  source. This includes the queued notification and the installed source
  callback.

The evidence is in `../artifacts/x2-rate-handoff-20261004/verification.json`,
`57333-trace.json` and `handoff.asm`.

The client side now has execution-checked rate-mask selection, position
classification and construction of the variable-length body, in the pre-V.90
3453B 2.1.1 and in the later 3453C 2.3.33. Their original serializers also
execute. 64 four-word bodies from the later client pass this server receiver.
Refer to [x2 client measurement records](x2-client-record-production.md).

The bitmap summarizer at 5EC3..5F11 is a host diagnostic report. It does not
make the peer record. The variable-length client body keeps five header words,
then packs the position controls and representative bitmaps. It has 15..103
words. It is not yet connected to this four-word branch. These items must
still be traced: the analogue measurements, the automatic exchange
scheduling, the complete call-state selection, the peer alignment, the short
announcement and the decoding of the analogue payload.
