# Courier x2 activation test endpoint

We deployed this endpoint on 2026-10-07 to tower.net.cryan.nz, in the existing v90modem-sip container.
Isolated source/binary directory: /root/courier-x2-service.
Asterisk internal extension: 6012. It uses the endpoint-modem template, with ulaw only.
In the existing dialplan, MODEMEXT/6012=1 bypasses MixMonitor.
SIP 5072, RTP base 4072. It answers automatically after one ring. It uses V.22 1200 mode (we changed to this mode after live V.34 retraining failures).
For this experiment, ME_V42_T400_MS=5000 makes the detection time of error control longer.
Service log: /root/courier-x2-service/service.log in the container.
The credentials stay on the hosts. They are not in this artifact.

COURIER_X2_ACTIVATE=1 enables one frame for each v42_restart. The frame is queued after
two seconds of transmit bits in LAPM_DATA. Frame: 01 02 0a 02 25.
This is an experimental vendor command that we derived from saved firmware. It is not
an ITU command. It tries to set feature record 2 mask 0x10, which adds x2.
We did not make a call to a physical Courier. The registration is verified.
A test of the deployed library transmitter recovered exactly one frame with a valid
HDLC FCS in 100000 bits. The test forces LAPM_DATA. It does not establish
a real peer link, and it does not prove that the physical Courier accepts the frame.

Dial ATDT6012. Let CONNECT occur and wait 10 seconds. Disconnect, then examine ATI7
and ATY14. If the firmware accepts the frame, the expected record change is 015 to 031.
The service process runs detached. We did not configure an automatic restart after a container
restart. The existing modem installation did not change.

Live calls: V.34 got to MP, then the peer started a retrain. V.22 physical training
was complete, but the detection fell back to V.14. No activation frame was sent.
Restart command: docker exec -d v90modem-sip sh /root/courier-x2-service/start.sh

## Detection defect found and corrected
The live TX capture had nine complete E/C ADP pairs for each call, then
HDLC flags. RX had repeated Courier ODP and no flags. The answerer
increments txadps before it sends, and its >=10 branch stopped after nine.
V.42 (2002) 7.2.1.3 requires a minimum of ten complete ADPs. Appendix III.1
recommends many more. The isolated service now sends 32 complete
pairs (pre-increment threshold 33), unless the existing peer-flag detection
path moves it to establishment earlier. Explicit count test of the transmitter:
ADP E=32 C=32. The full v42_link_test passes. The live acceptance is not yet tested.

Capture of the latest failed call: courier-latest.rx.ulaw and .rx.bits/.tx.bits.
TX has 32 complete E/C pairs and 74 flags. RX has 24 even / 23 odd DC1
ODP characters and no flags. test_audio.c sends the captured TX bits through
a V.22 1200 answer datapump, G.711 mu-law quantization and a caller datapump.
The result: 32 E / 32 C / 74 flags recovered. This tests paired software datapumps.
It does not prove the delivery to the real Courier or the compatibility with it.
We added a capture of the outgoing codewords that go to RTP, with add_tx_capture.py.
COURIER_TX_AUDIO_CAPTURE points to audio.tx.ulaw. The RX capture is audio.rx.ulaw.
Do not think that their time origins are equal (TX includes idle callback time).

Actual audio analysis (latest call): we replayed courier-live.tx.ulaw independently
through a caller V.22 receiver at many start offsets. This recovers
32 E / 32 C / 74 flags. courier-live.rx.ulaw through an answer receiver
recovers 47 ODP characters and zero HDLC flags. Thus, the live bit callback did
not miss a Courier LAPM response. This does not verify the waveform at
the analog input of the Courier, because the outgoing capture is before the RTP/ATA delivery.
The live interoperability problem is still not solved. The earlier
fixes to the ADP count and the timer are valid, but they did not establish the physical link.
