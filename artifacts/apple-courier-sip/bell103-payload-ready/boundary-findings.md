# Bell 103: locate corruption before blaming the Apple analog transport

Offline audit of the existing payload call; **no new call or firmware changes**.
`tools/analyze_apple_bell103.py` independently demodulates Bell 103 and scans
8N1 frames at 24 timing phases. It checks raw and parity-stripped bytes; it
does not use firmware CONNECT as evidence of correct data.

| Saved boundary | Independent decode of expected marker |
| --- | --- |
| Apple helper-bound TX, 10286 Hz | Exact `APPLE-TO-SIP-123` |
| I-modem SIP RX, PCMU/8000 Hz | Exact `APPLE-TO-SIP-123` |
| I-modem recorded DSP-facing RX, PCMU/8000 Hz | `APPLE-TO-SIP` prefix only; full marker absent |
| I-modem outgoing SIP audio, PCMU/8000 Hz | No exact `SIP-TO-APPLE-456` |
| Apple raw hardware RX, 10286 Hz | No exact `SIP-TO-APPLE-456` |

The first two boundaries independently establish successful delivery of this
specific 16-byte caller message through the Apple TX/analog/gateway/SIP path.
This does not prove arbitrary traffic or the reverse analog path error-free.

## Exact digital-stream discrepancy

Unlike an analog correlation, both I-modem receive captures use identical
G.711 codewords. Exact byte comparison anchors the source marker at SIP RX
sample **19333** to the heard stream at **54993**. The constant offset is
**35660 samples**.
At **SIP source sample 22560 / heard sample 58220**, the heard stream inserts
**30 consecutive `ff` mu-law silence samples**. The following **128 codewords**
match the original source exactly after adding those 30 samples to the offset.
That is **3.75 ms**, longer than one 300-bps bit (3.333 ms), inserted *inside*
the test message. See `bell103-boundary-audit.json` for exact interval offsets
and the byte-verified resynchronization.

Therefore the SIP RX recording alone was insufficient proof of waveform
integrity at the modem-facing boundary. The original summary's "zero active
Apple transport loss" remains true, but says nothing about these I-modem
playout insertions.

This is a concrete defect in end-to-end playout, not yet a complete root cause
for all the corrupted UART bytes: the decoded prefix is intact at the recorded
DSP-facing boundary, yet the firmware serial output is already wrong. The
reverse outgoing audio also fails the expected-marker check before reaching
the Apple receiver. DSP bit timing, data-bank handshakes and terminal framing
still need tracing. The audio decoder failing to find a marker is not by itself
proof of precisely which one is wrong.

## Reproduce without hardware

```sh
OPENBLAS_NUM_THREADS=1 ../v90modem/.venv/bin/python \
  tools/analyze_apple_bell103.py artifacts/apple-courier-sip/bell103-payload-ready

OPENBLAS_NUM_THREADS=1 \
PYTHONPATH=../v90modem/.venv/lib/python3.13/site-packages \
.venv/bin/python -m pytest -q \
  tests/test_apple_bell103_audit.py tests/test_3453_peer_uart_audio.py \
  tests/test_bearer_sip_playout.py tests/test_sip_media_clock.py tests/test_sip_media_start.py
```

**30 tests pass.** Synthetic controls recover the complete marker at
7200/8000/10286 Hz with both Bell 103 tone pairs, reject silence as a payload,
and identify an inserted 30-sample silence run by exact byte matching. These
are independent analyzer controls, not a claim that the live link is repaired.
