# Minimal SIP dial-out

`--sip-server` attaches the DAA to a small UDP SIP user agent. It enables the
DAA and the DSP automatically. Parsed `ATD` digits become the destination URI.
The client supports these items:

- An unauthenticated INVITE, or one MD5 Digest retry after `401`/`407`
- SDP with PCMU payload 0
- ACK/BYE
- RTP in the two directions

The harness changes the 9.6 kHz line stream of the modem to and from 8 kHz
PCMU. The current DTMF assist goes in at the recovered C51 DAC write. Thus, it
travels as usual in-band audio. It is not yet evidence that the firmware
datapump went into originate mode.

To keep the password out of the command history, put it in the environment:

```sh
export COURIER_SIP_PASSWORD='your-password'
./courier run main211.xmf --instructions 12000000 \
  --sip-server pbx.example.net:5060 --sip-username 6001 \
  --sip-target 'sip:{number}@pbx.example.net' --at ATD123 --summary
```

`dsp_bridge.sip` reports these items: the target, the response status, the
dialog state, the RTP endpoints/counters and a bounded event trace. It never
includes the password. This client is intentionally minimal. It is UDP/IPv4
and PCMU-only. It does not yet do these items:

- REGISTER
- Use SIP/TLS
- Negotiate other codecs
- Send RFC 2833 events
- Change SIP failure responses into Courier `BUSY`/`NO ANSWER` result codes

A live 6000-to-7800 validation completed Digest authentication and received
`200 OK`. It carried 1,152 inbound and 507 outbound RTP packets. But the
Courier still returned `NO CARRIER`. The supervisor sent 30 two-word runtime
control messages on ports `0x58..0x5e`, and none of them got to a datapump. The
blocker is below SIP. It is not in the duration of SIP or in the RTP transport.
It is also not the host-latch timing that earlier notes named. See "The window
word `0x50` is not the datapump's command port".

The result includes these items: the CPU registers, the first 128 I/O/MMIO
operations, the full event counts for each address, the hottest code addresses
and the final execution path. It also records the `supervisor-entry`,
`dsp-transfer`, `startup-crc` and `main-loop` milestones. A run that gets to the
usual dispatcher reports `status: main-loop`.

Unknown input ports return all ones. Input responses and output latches are
separate, as on hardware such as DSP command/status port `0x1e`. `--port` sets
only the input response. This intentionally makes unmodeled hardware visible.
The harness does not silently pretend that the hardware exists.

On macOS, you can select a native Unicorn library with
`--libunicorn /path/to/library/directory`. The worker boundary changes native
signals into a clean CLI failure. Thus, the controlling process does not crash.
