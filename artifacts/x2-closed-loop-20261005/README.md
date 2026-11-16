# Original Courier peers against the v90modem x2 engine

These are new feedback calls, not a replay of recorded audio. The original
403 analog ROM and the Ie030002 I-modem execute their native DSP paths. The
engine receives new peer samples before it makes its next reply. No DSP
register is forced and no CONNECT is injected. The I-modem PCMU is byte-exact.
The analog endpoint uses the existing codec calibration of BearerLineLink
(`from_line=0.509330871`, `into_courier=0.528445252`). The media is paced at 8 kHz.

Final results of the default build:

| Peer | Samples exchanged each way | Media duration | Result |
|---|---:|---:|---|
| analog Courier 403 | 213120 | 26.64 s | INFO0 / Tone A / marker wait / timeout |
| I-modem asymmetric diagnostic, S58=58 | 199955 | 24.99 s | INFO0 / Tone A / marker wait / timeout |

**No call gets to the accepted x2 marker, B1, CONNECT or data.** The
recorded B1 regression still passes. That is a separate acquisition test.
`results.json` lists all runs and the SHA-256 hashes of their raw PCMU streams.
The `call.json` of each run records the sample counts, the pacing, the commands/settings and the
codec parameters. `engine.log` records the live state changes. The final call files
also identify the hash of the built engine. `native-control.json` is a read-only observation of the DSP.
`native-program.bin` identifies the executed Ie030002 code.

To reproduce, run `make -C ../v90modem v90_engine_peer`, then these commands (use new output paths):

```
.venv/bin/python tools/probe_v90modem_closed_loop.py analog --output /private/tmp/x2-analog-new --instructions 160000000
.venv/bin/python tools/probe_v90modem_closed_loop.py imodem --output /private/tmp/x2-imodem-new --instructions 160000000
```

The wrapper binary is at `../v90modem/v90_engine_peer`. Its stdin framing
is a little-endian 16-bit sample count, followed by that number of PCMU octets.
stdout contains exactly that number of generated octets. The logs go to stderr.
The I-modem harness clocks its actual new media chunks, frequently one octet.
The analog exchange uses 160-sample frames. Do not use `--fast` when you interpret
negotiation timeouts that are in wall time.

## What the experiments isolated

* `analog`, `imodem`: the initial B1-fixed build, before these handshake fixes.
  The two calls complete V.8, but the native x2 eligibility stays off.
* `*-tone-end`: if only Tone A stops in MARKER_WAIT, this does not solve the problem.
* `*-recovery`: when the engine recognizes the 17-bit acknowledged INFO0 after the initial INFO0,
  a real retransmission occurs. But this still does not unlock the native x2.
* `imodem-gate-instructions`: only `9596,9597,9598,9599` execute. The native
  gate returns when `039f` bit 10 (`0400`) is clear.
* `*-digital-access`: adds the V.8 JM PSTN-access octet `8d`. The eligibility stays
  off. `*-ansam` tests ANSam without periodic phase reversal. The result is the same.
* `imodem-classifier`: at `de14`, `ffd9=8000` permits x2, but the ACC of the classifier
  is **−131230**. `de15` does not set `039f` bits `1400`.
* `imodem-phase-reversal`: a reversal of the V.21 carrier between JM messages
  changes ACC to **+210811** and executes `de15`. `039f` becomes `1442`, then
  `1462`, and the native V.8 report becomes `0071:0007`. With S58=48, the
  I-modem then offers INFO0 `3dff`. Thus, this is an offer of a digital server /
  symmetric capability, not the necessary analog-client offer.
* `native-classifier-control`: an unmodified Ie030002 pair, S58=48. The two native
  endpoints report x2 CONNECT. The classifier captures give **+133769/+135107**.
  The `03e3` carrier-amplitude writes alternate `0012/ffee` at `dd64` between
  messages and at `dd76` during CJ. This control did not request a user payload.
  To reproduce, use `tools/probe_imodem_v8_classifier.py` with the
  same arguments as `probe_imodem_pair.py`.
* `analog-phase-gate`: the analog native signature flags become `4040/4060`.
  Then the fallback builder clears them to `0020` at `909b`. Its 7-bit
  CRC-valid frame is `13`: ordinary rate index 1 with high carrier. The
  successful fast x2 path would use `9083..908a` to construct `4d` instead.
* `imodem-client-phase-reversal`: S58=50 removes the server capability, but
  INFO0 `2dff` still has the symmetric capability. `imodem-asymmetric-client`
  uses S58=58 and offers `25ff`. It enters native `95c4..95ef`, then
  `92e2..92ef` clears x2 because `ffd9` bit 1 is clear. No marker comes after this.
* `analog-final`, `imodem-final`: a repeat on the final default x2 build, with
  the phase signature enabled through an explicit V.8 API for each session.
  The two calls keep the later Phase-2 failure. `ME_V8_X2_PHASE_REVERSAL=0` disables it
  for comparison. The other modem modes do not enable it by default.

The specific remaining work is the native fast Phase-2 negotiation that
keeps x2 active and makes `4d`. This includes the timing from the received tone and the
INFO0 recovery. The current Tone-A waits are hypotheses. The digital I-modem
symmetric x2 is also a different session, and the engine does not implement it.
Do not force native flags. Do not accept the fallback `13` as the necessary marker.

## Regression checks on the final code

The production `sip_v90_modem` and `v90_engine_peer` build. The recorded session
tests pass. These include ACK recovery, MP/E, upstream-E detection with blocks
1/17/160, and capture marker `4d`. B1 acquires the retained Courier recording
at 99.9% with expanded shaping / 64-state trellis at blocks 17/160, and it rejects
silence. All 402 V.34 data cases pass. The Python harnesses compile.
