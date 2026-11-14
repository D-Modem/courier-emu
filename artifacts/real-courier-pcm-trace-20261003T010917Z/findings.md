# Real Courier capture: V.34 connection and outgoing media stall

The third incoming call connected at 31,200/33,600 with V.34/LAPM/V42BIS.
After 4:40, the physical Courier reported loss of carrier. It also reported
21 block errors, one granted retrain, 36.7 dB SNR and 308 ms round-trip delay.
Its V.90 status was 02F7. This identifies an x2 server, but no PCM connection.
The last-call report of the I-modem recorded 2:17, 1,728 block errors, three link
timeouts, six retransmissions and one granted retrain.

In the connected call, the application RTP trace and the Asterisk PCAP show no missing,
duplicate or out-of-order packets, and no timestamp discontinuities.
Before CONNECT, the largest outgoing packet interval that we saw was about 25 ms.
At about 17 seconds after CONNECT, an outgoing packet interval at Asterisk was 160.094 ms.
The incoming packets stayed regular (the largest interval was about
24 ms). The transmit reserve of the DSP decreased below its priming threshold. After the
outage, its queued audio increased from about 60 ms to more than 200 ms.

The corrected PIT time source and the DSP sample clock follow wall time, but
the instruction progress of the CPU falls far behind. This does not make sure
that the firmware receives each timer edge. The scheduler raises only one
PIC request for many elapsed periods. Also, a PIC request bit combines edges
while an earlier request is still pending.

A one-second process sample shows much time in native C5x execution
and in Python/FFI work. The live catch-up loop of the DSP could continue until it
reached all of its absolute wall-clock target. During a backlog, this stopped the next CPU
slice. Now, the live DSP catch-up has a limit of one millisecond of host time.
It returns at PCM-frame boundaries and keeps its cycle
deficit. The next report and trace count the combined timer edges. This change
must have a retest on hardware. It does not show the cause of the x2 fallback.

Files: analysis.json, timeline.jsonl, run.log, asterisk-next-call-rtp.pcap,
process-sample.txt, and the three raw G.711 captures in this directory.
