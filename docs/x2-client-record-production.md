# x2 client measurement records

The pre-V.90 3453B 2.1.1 and the later 3453C 2.3.33 execute the same rate-mask
intersection, position classification and variable-length record framing.
These are verified components of the path in the client from the measurement
to the message. The analogue acquisition and the automatic call-state
scheduling are still not verified. The variable-length message is different
from the four-word Quad receiver branch that we tested in
[the server handoff](x2-rate-and-data-handoff.md).

## Rate selection

The original entries E773..E7A2 in 2.1.1 and 6818..6847 in 2.3.33 keep the
header control bits. They select the highest eligible bit of two 32-bit masks.

```
limit = data[037D] + data[0364] - 20
eligible = measurement_mask & host_mask & ((1 << limit) - 1)
selected = eligible.bit_length()
header = (initial_header & (0x7007 if role_bit_5 else 0x7003))
         | (selected << (3 if role_bit_5 else 2))
```

The result is also stored at 031C. The original continuation receives
`selected - data[0364] + 20` at 037D. The qualification is: limits 1..31,
a nonzero initial 037D, and masks with bit 31 clear. The tests include zero
intersections. A zero initial 037D returns before the mask intersection.
The physical interpretation of 0364 is still open. We do not give nominal
line rates to these indices only because of their numerical values.

| Firmware | Measurement low / high | Host high / low | Header | Role bit |
|---|---|---|---|---|
| 3453B 2.1.1 | D2A0 / D2A1 | F7C9 / F7CA | FCD0 | FFE9 bit 5 |
| 3453C 2.3.33 | 52A0 / 52A1 | 77C7 / 77C8 | 7CCE | 7FE9 bit 5 |

The comparison examines 496 contexts in each firmware: the two role states,
eight offset values, all limits 1..31 and randomized sparse masks.

## Position classification and the variable-length body

F16B in 2.1.1 and 720A in 2.3.33 compare two six-position measurement
matrices. Each position uses eight 16-bit words. The constructor groups pairs
of position blocks that agree. It gives group numbers in the sequence of first
occurrence, and sends one representative block for each group. The tests
cover one through six groups, equal and different matrices, and randomized
repeated groups. The independent reconstruction agrees with the complete
constructed body, not only with its length or checksum.

Let N be the number of different groups. Let D be one if the two full matrices
are different, and zero if they are not. The existing first five header words
stay. The constructor makes the two control words that follow:

```
word[5] = group[0] | group[1]<<4 | group[2]<<8 | group[3]<<12
word[6] = group[4] | group[5]<<4 | D<<8
body_word_count = 7 + 8*N*(1 + D)
```

The first matrix supplies N consecutive eight-word representative blocks, in
group sequence. If D is one, the second matrix supplies N more blocks in the
same sequence. The count is from 15 to 103 words. The original constructor
saves that count at CE9F or 4E9F. Its temporary 007D value is 8*N if D is one,
and zero if D is zero. It is a block offset for the second matrix. It is not
an independent sign count.

For six different positions, the two control words are 3210 and 0054, or 3210
and 0154 when the matrices are different. For a repeated two-group sequence
0,1,0,1,0,1, they are 1010 and 0010, or 1010 and 0110.

In 2.3.33, the body starts at 7CCE, the controls are 7CD3/7CD4, and the bitmap
data starts at 7CD5. The equivalent 2.1.1 addresses are FCD0, FCD5/FCD6 and
FCD7. The last seven-word BLDD copies the assembled header back to scratch. It
does not replace the header with classification scratch. The disassembler now
shows the source and the destination in their correct sequence.

There are 76 whole-body comparisons for each firmware. These include twelve
explicit contexts for one through six groups and for equal against different
matrices. The 152 buffers that the native constructor makes go to the
original transmit initializers C5E8 and 4650. These initializers install the
source pointer, the returned count, the preamble and the serializer callbacks.
Then the original serializers execute with those values. The harness enters
the initializer. The complete call-state selection is a separate boundary.
For the older initializer, overlay 6 must be restored after the overlapping
overlay 7.

## Original framing and CRC

The 2.1.1 serializer starts at ADE2. The 2.3.33 serializer starts at 2E3A.
With the source-selection flag 039F bit 14 set, they consume the body that
033D points to, and the word count at 03C9. They send this sequence:

1. Seventeen ones and a zero.
2. Each word, least significant bit first, with a zero separator after it.
3. Sixteen CRC bits, least significant bit first.

The CRC starts at FFFF and uses the reflected polynomial 8408. It does not
include the separators and has no final XOR. The callback that follows sends a
zero tail.

The earlier serializer agrees independently with this framing for 96 seeded
bodies of one, two, four, six, seven and nine words. Sixty-four four-word
bodies that the later serializer generated pass the original Quad bit
receiver, which commits all four words without change. That shows compatible
framing. It does not make the variable-length client record equal to the
short body of the Quad.

## Diagnostic report is a separate output

DE1D..DE6B in 2.1.1 and 5EC3..5F11 in 2.3.33 summarize six measurement bitmap
windows. They count the windows with fewer than twenty set bits. They pack
that count, local flags, a rate field and an auxiliary value into a report at
F7C0 or 77BE. The execution agrees with the packing formula for 1024
contexts. The report pointer goes into the host diagnostic output path, which
includes OUT 0060. It is not the peer-negotiation body above. Each of the six
windows advances eight words before it reads a high/low 32-bit bitmap pair.

This difference removes 5EC3 as a candidate for the missing peer producer.
The actual rate/header writer and the position constructor have separate
entries.

## DSP condition timing and reproduction

The bitmap threshold showed an emulator error: XC must sample its conditions
one full cycle before execution. A predecessor of one cycle cannot change that
sample. TI SPRU056D sections 4.5.6 and XC page 6-278 give this rule. The
native core now keeps the correct accumulator/status sample, also across
delayed-branch slots. Six focused regression cases pass. After this change,
the full repository suite and a symmetric 64000/64000 call also pass.

Run `.venv/bin/python tools/trace_x2_client_record.py`. The evidence is
`artifacts/x2-client-record-20261004/packer-verification.json`, with the
original 2.1.1 overlay listings in the same directory. The symmetric-call
regression is in `artifacts/x2-xc-pair-20261004`.

The remaining work is: the analogue sample/measurement producer, the
interpretation of the five header words, the automatic scheduling of the
variable-length exchange, its peer receiver branch, the frame alignment, and
the decoding of the analogue payload.

## Courier 403 additive count audit

The captured Courier 403 counterpart makes the arithmetic of 0364 clear. It
does not show that its later record exchange runs in the observed call.
EA82..EABC returns N-0364+20. E970..E97B does the same conversion from the
header to 0351. E11C consumes 0351+0364 bits. At 0364=5, the intermediate count
is N+15 and the total is N+20. The original consumer passes 216 bit-count
contexts. Two items are still open: the assignment of the additive count
specifically to independent signs, and the binding of the XMF header fields to
the complete receiver. Refer to [Courier MP fields](x2-courier-mp-fields.md)
for the profile, the live-call coverage and the difference between the short
MP and the later body, which did not execute.
