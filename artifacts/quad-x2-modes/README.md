# Quad x2 role controls

**2026-10-18 update:** asymmetric **server** x2 now passes at 52000/33333
against an actual analog Courier client, with both payloads intact.
[New evidence](../quad-traffic-and-asymmetric-x2-20261018/README.md).
The matrix below preserves the earlier forced-role **digital-to-digital**
controls, not the supported analog-client topology. Vendor documentation
explicitly states that Quad client mode is unsupported.

## Measured status

| Requested Quad role | Result with feature provisioning | Original status replay |
|---|---|---|
| Symmetric | **Both `CONNECT 64000/ARQ/x2/LAPM`; both payloads intact** | 1: x2 operational |
| Asymmetric server | No x2; fixed-DTE control falls back to working V.34/LAPM, variable-DTE control has Quad `33600/V34/NONE` and no caller CONNECT | 11: Excessive high frequency attenuation |
| Asymmetric client | No caller CONNECT; Quad `33600/V34/NONE` | 9: Incompatible x2 modes |

Symmetric passes with and without `&B0`. The latter profiles were tested to
remove the fixed-9600 DTE limiter from asymmetric eligibility. The client
control uses the same topology (Quad answering an originating I-modem); its
role mismatch does **not** establish that the Quad cannot act as a client in
a correctly selected reverse-role topology.

Working symmetric evidence and command:
[`../quad-x2-symmetric-provisioned/README.md`](../quad-x2-symmetric-provisioned/README.md).
All three variable-DTE controls are in `../quad-x2-{role}-variable-dte/`;
fixed-DTE provisioning controls are in `../quad-x2-{role}-provisioned/`.
They have no CPU/DSP errors or PCM receive underruns. Failure controls must
not be presented as working x2, even when a V.34 fallback delivers data.

## Reproduce the role matrix

Common options:

```sh
PYTHONPATH=. .venv/bin/python tools/probe_quad_pair.py \
  --settings 'S54=0S58=50&M5&K0' \
  --quad-terminal-init 'Q0V1&A3&B0S76=131S81=32' \
  --quad-feature-mask 0x20 --trace-dsp --trace-negotiation \
  --post-call-diagnostics \
  --imodem-send X2-IMODEM-TO-QUAD-482619 \
  --quad-send X2-QUAD-TO-IMODEM-731954 \
  --check-x2 --check-data --output /tmp/quad-x2-symmetric
```

Change these values to select another requested role:

| Quad role | Quad S76 | Caller S58 |
|---|---:|---:|
| Symmetric | 131 | 50 |
| Server | 133 | 58 |
| Client | 134 | 56 |

S76 bits 1/2/4 **disable** client/server/symmetric; 128 enables high-power
constellations. S81=32 disables V.90 server mode. Caller S58's 1/2/8 disable
x2/server/symmetric, 16 enables high-power constellations, 32 disables V.90.
The client control leaves the caller's server availability enabled; whether
that caller actually selects the required transmitting role must still be
traced. Server/client x2 are asymmetric PCM/V.34 roles, not 64k both ways.

`--check-x2` requires explicit x2 modulation in **both** firmware CONNECT
results, not merely a 64000 rate or transparent `/DIGITAL`. Carrier, data and
modulation verification are now independent report fields; any requested
failure still exits unsuccessfully.

## Previously missing genuine inputs

1. Operating mode: wire `003f=2` selects firmware mode 4. Wire 4 was mode 6.
2. The entire extended AT setup must finish with its real OK before chassis
   arming. `initialization_completed_at` records the barrier. The first
   `../quad-x2-{role}-current/` sweep predates this fix: setup was interrupted,
   so those runs do **not** prove that the requested S76 values took effect.
3. **Feature provisioning:** normal type-1 parameter `01f2=20` is dispatched
   at `f4889..f4894` to `f3b2:4dbb` (`f88db`). Its original code at
   `f8967..f896b` enables the local `8838 & 20` gate. The setup audit reads
   `8838=cf` without it and `ef` with it, with S76/S81 correctly stored.
   Firmware, not a host write to call state or callback pointers, makes this
   change. Without this input all four acknowledged S76 controls
   (`../quad-x2-{role}-configured/`) fall back to V.34/LAPM.
4. `&B0` removes the asymmetric DTE-speed limiter. The variable-DTE captures
   have `89b2=0`; removing that limiter alone does not solve asymmetric x2.

## Original diagnostic replay

The labels in the status column come from executing the **original**
`e273b` status routine in a separate Unicorn instance, with the saved
`x2_status_inputs` and working S54/S76/S81 cells from the variable-DTE runs.
This offline analysis does not touch the real call or invent received data.
Its status string table is at `db20:64c5`, physical `e16c5`.

The captured descriptors are:

| role | 8838 | 8954 | 895f | 89b2 |
|---|---:|---:|---:|---:|
| symmetric | ef | 04 | 00ff | 00 |
| server | ef | 00 | 013f | 00 |
| client | ef | 00 | 0007 | 00 |

The server's `895f & 40` condition is missing; the client lacks `895f & 10`.
Follow the actual writers of those flags and the asymmetric role/quality
exchange next. Do not force a mapper, error-control receiver, quality flag,
carrier or payload to make these cases pass.

The symmetric control verifies a **negotiated 64k x2 link and short ASCII
payloads**, not sustained application throughput, binary DTE or V.90. Its
ATI6 receive-speed display anomaly and one bler are preserved in the linked
evidence instead of being silently corrected.
