# ITU audit of the failed Courier call

We examined these sources locally: ITU-T V.42 (03/2002), V.22 (11/1988), and
V.22bis (11/1988), in /Users/scottcryan/v90modem/ITU Docs.

| Requirement | Implementation / captured result |
|---|---|
| V.42 7.2.1.2: ODP is DC1 with alternating parity and 8–16 mark bits | The RX audio gives the expected alternating DC1 patterns, at 19 bits for each character (10 character bits plus 9 mark bits). |
| V.42 7.2.1.3: recognize at least four alternating DC1 characters | The receiver must get two complete ODP repetitions. |
| V.42 Table 3: ADP is E/C, each followed by 8–16 mark bits | The actual TX audio gives E/C characters at 18-bit intervals: 10 character bits plus 8 mark bits. |
| V.42 7.2.1.3: at least ten ADPs | The old implementation sent nine. The corrected isolated service sends 32. The audio confirms the count. |
| V.42 7.2.1.2: originator recognizes two adjacent ADPs before establishing LAPM | The Courier does not send flags after our ADP. |
| V.42 9.1.1: default T400 is 750 ms | The ODP burst of the Courier contains about 23 pairs, about 728 ms. This suggests, but does not prove, that its default detection timer expires. |
| V.42 7.2.1: use carrier-clock bits, without async speed matching | LAPM/detection connects directly to the bit callbacks of the datapump. It bypasses the V.14 character framing. |
| V.22bis 5: scrambler polynomial 1+x^-14+x^-17 | The TX taps at zero-based positions 13 and 16 agree. The inversion rule for an output run of 64 also agrees with V.22bis. |
| V.22bis Table 1 and 2.5.2.2: 00=90°, 01=0°, 10=180°, 11=270°; use constellation position 01 at 1200 | phase_steps={1,0,2,3}. 1200 selects constellation index 01. |
| V.22bis 6.3.1.2.2: answer sends scrambled marks, waits 765±10 ms before data | TX uses 756 ms. This is in the permitted tolerance. The readiness sequence of RX/TX must still have a full independent audit. |

The latest TX waveform demodulates independently to 32 E/C pairs and 74 flags.
The RX waveform demodulates independently to 47 ODP characters and no flags.
Here, "independently" means a separate decoder invocation. It still uses the
same SpanDSP implementation. It does not validate a waveform at the Courier
input.

Timing risk: the receive jitter buffer of the service has a fixed value of
200 ms. This uses 200 ms of the response budget of the originator before ODP
gets to our detector. ATA buffering, packetization, TX delivery and receiver
qualification add more time. Do not subtract positions in TX/RX files as if
their origins were calibrated. A controlled experiment at the endpoint only
decreases the fixed buffering to 40 ms. It keeps the fixed playout and
disables the discard function as before. This is a hypothesis test. It is not
a confirmed correction for the connection. No user data is necessary before
the protocol is established. We did not send an activation.
