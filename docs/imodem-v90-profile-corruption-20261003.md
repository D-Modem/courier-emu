# V.90 data corruption reproduction, 2026-10-03

The physical Courier gets to V.90, but the raw connection does not always
carry application data correctly. A CONNECT result alone is not a passed test.

The independent SmartLink probe shows the same receive failure without SIP,
Asterisk, or the VG224. The two modems negotiate V.90 at 44,000/31,200 bit/s.
The factory control, which is not saved, receives all ten known messages correctly. The
saved live profile receives none of ten. It also sends garbage that nobody requested.
If you change only its serial framing to 7E1, or only its speed to 9600, the problem stays.

We wrote a profile with the original firmware and copied the 91-byte ISDN block of the live
profile into it. This profile also fails in 8N1 and in 7E1. In the 7E1 test,
all five messages from the emulator to SmartLink arrive intact after we remove the
expected parity bits. None of five messages from SmartLink to the emulator arrive
intact. This makes the reproduction more specific. But it does not identify a defective CPU or
DSP instruction. It also does not show that this receive failure is
the same defect as the corrupt downstream of the physical Courier.

These tests did not repair the reproduction: changes to S67, S68, *V2, the synthetic
factory capability header, or the duplicate directory numbers. NET3 and a
profile that contains the two factory SPIDs did not make a data connection.
Thus, they are inconclusive tests of data integrity.

## Captured output reaches RTP unchanged

For all seven calls in the saved 02:20:29 UTC run, the concatenated outbound RTP
payloads agree exactly with the related raw B-channel output. The final
raw V.90 call agrees across 7,380,000 bytes. The alignment uses a unique data
segment, because different calls have the same initial training waveform.
For these captures, this shows that the RTP packetizer of the emulator does not change
codewords. It does not show that receiver playout or other channel effects are absent.

## Evidence and reproduction

- [Experiment comparison](../artifacts/imodem-slmodemd-v90-profile-framing-audit-20261003/comparison.json)
- [Factory control](../artifacts/imodem-slmodemd-v90-factory-profile-audit-20261003/result.json)
- [Saved live profile](../artifacts/imodem-slmodemd-v90-live-profile-audit-20261003/result.json)
- [Fresh saved profile, 7E1, valid ISDN block](../artifacts/imodem-slmodemd-v90-fresh-7e1-ni1-audit-20261003/payload-analysis.json)
- [RTP byte comparison](../artifacts/real-courier-pcm-trace-20261003T022029Z/rtp-bearer-byte-audit.json)

For each run, use a new output directory. This command uses the existing
isolated SmartLink test modem on Tower:

```sh
.venv/bin/python -m tools.probe_imodem_slmodemd \
  --protocol v90 --payload-check --payload-packets 5 \
  --payload-start-delay-blocks 200 --instructions 300000000 \
  --flash-nvram artifacts/imodem-slmodemd-v90-profile-framing-audit-20261003/nvram-firmware-fresh-7e1-ni1.sav \
  --imodem-initialization 'ATX1S54=0S58=1&A3&B1Q0&N0&U0&M0&K0' \
  --output artifacts/v90-profile-reproduction-new
.venv/bin/python -m tools.analyse_slmodemd_payload \
  artifacts/v90-profile-reproduction-new
```

For the factory control that operates correctly, do not use `--flash-nvram`. The probe keeps the
supervisor RAM, the native DSP program/data, the two PCM streams, and the two serial
streams. These experiments did not find a production fix.
