# Hardware 7930: PPP recovery work

## Initial live result

The original analog Courier 403 / DSP 3.1.2 firmware, running in vmhost CT127,
negotiated `CONNECT 41333/ARQ/V90/LAPM/V42BIS` against hardware extension 7930
using account 2905 / PCMA, default gain handling and an isolated snapshot.
LCP opened, PAP `Login ok` and peer IPCP requests reached the captured DTE,
but a repeated peer LCP request restarted negotiation. The client ended in
`ack-rcvd`, with no running retry timer. The full serial capture ends in
`NO CARRIER`. No ping payload test ran. This was not a sustained PPP pass.

Evidence:
`artifacts/sip-hardware-timed/courier-hardware-timed-20261106-092949-7930/`.

## Corrections to the userspace PPP test client

The deployed `ppp.py` was byte-identical to `../modem-dsp-emu/tools/ppp.py` before
these changes. Fixes were made there and deployed only to the isolated vmhost
snapshot `/root/courier-hardware-timed-20261106-092949`:

* Keep the restart timer running in Ack-Rcvd; on timeout, return to Req-Sent
  and retry instead of hanging forever in half-open negotiation.
* Keep the request Identifier and options unchanged on pure timeout retries;
  use a new Identifier after a valid reply or option changes.
* Retransmit PAP Authenticate-Request with bounded retries, stop on a matching
  reply or LCP-down, and validate response Identifier and packet length.
* LCP codes 1..7 now always use default control-byte escaping, as required
  by RFC 1661 section 5, even when renegotiating an already-open link with
  ACCM zero. A peer restored to default framing otherwise discards raw controls.
* The instrument now records post-CONNECT NO CARRIER and terminal PPP failures
  rather than continuing a dead session to the nominal duration.

Firmware, CRC checks, gain handling, keepalive policy and default timeout values
are unchanged by the client fixes. Later controls explicitly disable V.42bis
compression (`&M5&K0`), retaining required LAPM. These are client recovery defects, not proof that the hardware
modem or audio transport is otherwise correct. Peer Configure-Requests still
cause normal renegotiation; no fake layer-up or authentication is introduced.

Regression:

```
.venv/bin/python -m pytest -q ../modem-dsp-emu/tests/test_ppp.py \
  ../modem-dsp-emu/tests/test_ppp_retry_recovery.py
```

94 tests plus 4 subtests pass, including new timer, recovery, PAP and default
LCP-framing checks.

## Repeat

Repeat output: remote `hardware-7930-retry-600s/` in the same isolated snapshot;
local collection:
`artifacts/sip-hardware-timed/courier-hardware-timed-20261106-092949-7930-retry/`.
Target remains 600 live seconds after genuine CONNECT, with exact 512-byte
binary ICMP payload checks, full DTE capture checked against total byte count,
and RTP packet capture. A failed negotiation or carrier loss invalidates any
claim of a completed timed test.

Retry-only call (before the default-LCP-framing correction): negotiated
45333/V90/LAPM/V42BIS, recovered through repeated LCP negotiation and eventually
authenticated, but got NO CARRIER at 28.9 connected seconds before IPCP completed.
RTP had zero missing/late packets, zero active receive underruns and zero TX
rebuffers; the SIP peer sent BYE. This does not identify why the peer hung up.

No-compression control (also before the default-LCP-framing correction):
45333/V90/LAPM, PAP/IPCP completed, 58 pings sent with zero replies, then NO
CARRIER at 73.3 connected seconds. Not a passing data test.

The next control `hardware-7930-quoted-600s/` includes all client corrections,
retains `&M5&K0`, and enables `COURIER_PPP_QUOTE_CONTROLS=1`. That instrument-only
switch applies legal extra escaping of all control bytes on transmission,
independently of the negotiated ACCM, to diagnose serial/converter consumption
of raw control bytes. It does not alter payloads, CRC checks, acceptance
thresholds or manufacture replies. This is not an isolated A/B of quoting,
because this call also includes the newly corrected default LCP framing.
Initial quoted-control live progress: negotiated 31200/V34/LAPM, authenticated
and completed IPCP about 6.1 seconds after CONNECT. At 33.9 connected seconds,
27 pings had been sent and one exact 512-byte reply received (24.5-second RTT),
with zero reported PPP FCS errors. It then failed at 33.9 connected seconds
with `SIP analog receive backlog exceeds queue capacity; emulator is not keeping
up with live audio`. No final native report was produced, so the full capture
cannot be length-validated and the test is invalid as a soak. This is not
evidence that quoting alone fixed V.90: modulation also changed from the
previous call, and the large delay remains unresolved.

Follow-up `hardware-7930-stopwait-600s/` keeps the same quoting, required LAPM,
no-compression settings and unrelaxed keepalives, but sends at most one ping
at a time. Its purpose is low-load stability and delay diagnosis, not a
throughput qualification. It retains the same 600-second connected-time target
and does not enlarge receive buffers. Result pending at launch.
