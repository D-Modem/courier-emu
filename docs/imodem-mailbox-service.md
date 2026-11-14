# I-modem supervisor/DSP mailbox service

The immediate blocker of the supervisor was missing **IRQ13 service plus
runtime mailbox status**. It was not the VRTX task startup. The original
Ie030002 firmware now empties its command ring without guest patches. This is
a transport correction: `IsdnMachine` still captures DSP downloads and does
not execute the C52. Its default mailbox endpoint explicitly reports
`capture-only`.

## Recovered path

- IRQ13 maps through the programmed PICs to INT 2dh.
- INT 2dh contains `4030:0316` (physical `40616`). That wrapper saves the
  registers, sets DS/ES to 2600h, pushes the flags, and does a far call to
  `[c893]`.
- The service pointer after boot is `b3d9:0000` (physical `b3d90`).
  Its `iret` returns through the synthetic interrupt frame of the wrapper.
- The handler reads ports 1eh/1ch and masks to the low two bits. It tests
  bit 0 for permission to transmit, and bit 1 for a pending receive word.
- The queue is at `2600:c9b2..c9f1`. The read/write pointers are c9ae/c9b0.
  An ff00 marker selects a full command/argument pair. Compact words encode
  the command in their high byte and the argument in their low byte.
- CPU writes 58h/5ah hold the low/high bytes of the command. 5ch/5eh hold the
  argument. A write of bit 0 to 1ch commits the pair. The zero write after it
  is not a different command.
- The receive direction uses separate latches at those same addresses. A read
  does not acknowledge. A write of bit 1 to 1ch releases the pending reply.
  This permits transmit and receive at the same time, without corruption of
  each window.

The alternative handler at `b3d9:3f91` (`b7d21`) uses the same mailbox windows
and status bits. It is not the handler that executed in this startup run. The
`b7c8b` consumer of the earlier CEML4 probe is valid isolated code. But it
does not prove that the live IRQ uses that specific consumer.

## Implementation and limits

`imodem_mailbox.py` implements directional latches, commit, receive
acknowledgment, transmit backpressure and a bounded command history.
`offer_reply` does not overwrite a reply that waits for acknowledgment.
An optional command callback gives an attachment point for a DSP endpoint.
The default capture endpoint does not fabricate a successful DSP response.
The endpoint also records the writes during startup/reset. Thus not each
recorded commit is a runtime command.

`isdn.py` raises IRQ13 one time for each 2048 supervisor instructions through
the PIC. It obeys the masks of the PIC and the interrupt-enable flag of the
CPU. This is a **modeled cadence**. It is not a measurement of the physical
interrupt clock of the I-modem. The service handler also does timer work.
Thus we must recover the real rate before we claim accurate call timing.
`mailbox_service=False` disables this source for comparisons. The existing
IRQ10 tick stays. Ports 18h and 1eh keep the existing download-handshake
model. The runtime mailbox acknowledgment is different from the
acknowledgment of DSP execution.

## Unpatched firmware comparison

To reproduce this with Unicorn, use this command. (On macOS, the JIT can
require execution outside the sandbox.)

```sh
.venv/bin/python tools/imodem_mailbox_probe.py \
  --output artifacts/imodem-mailbox-service/probe.json
```

The two cases run Ie030002 for 5,000,000 instructions with transmit-ready
status. Only the IRQ13 service is different. The image hash and the full
summaries are in the artifact.

| Observation | Service disabled | Service enabled |
|---|---:|---:|
| Runtime handler entries at b3d90 | 0 | 1,234 |
| Ring-wait visits at a543b | 509,590 | 1 |
| Ring-drain timeout visits at a5446 | 15 | 0 |
| Final read pointer | c9b2 | c9c2 |
| Final write pointer | c9de | c9c2 |

The enabled run sends four runtime pairs: `0002:d100`, `0002:9260`,
`0001:003f`, `005b:0000`. Five earlier commits belong to the startup/reset
traffic. There are no injected DSP replies. These results show that MODEM
gets past the blocked send queue. They do not show the completion of DSP
commands or a working modem call. An AT-to-OK exchange is no longer an open
item - refer to [the AT interface](imodem-at-interface.md). But it runs over
SIO0 and tells nothing about this path.

The next DSP integration must do these steps:

- consume these committed pairs;
- drive transmit-ready from the actual availability of the endpoint;
- publish the replies that the DSP makes into the receive latch;
- send the CPU acknowledgment back to the DSP.

If the endpoint only returns ready all the time, that is only the behavior of
the capture endpoint. It is not evidence that the C52 processed a command.

## Native C50/C52 connection

The transport-only limit above is now optional. To run the native endpoint,
use this command:

```sh
./courier isdn-run Ie030002.xmp --with-dsp --instructions 5000000
```

`IsdnMachine(..., with_dsp=True)` connects `ImodemDsp` to `NativeC5x`.
Without the flag, the earlier capture-only mode is still available. Library
callers must call `machine.mailbox.close()` after they examine the native
results. The CLI closes it automatically.

The connection includes:

1. **Bootstrap capture:** the alternating 40h/50h windows of the CPU each
   contain four 16-bit words, committed by port 18h bits 0/1. The two ready
   bits stay available. When the model only echoed the last strobe, the last
   two-bit wait of the firmware failed. The 8000h destination comes from the
   reset transaction. The checksum-completion strobe installs the captured
   resident (4,672 words, including two padding words) in the native core.
   The core executes the resident initialization to its first IDLE before it
   shows the completion. This keeps a modeled bootstrap transfer/completion.
   It is not an execution of the reset loader of the mask ROM, and it is not a
   validation of the wire checksum. The recovered mask ROM is loaded and its
   hash is examined for the interrupt vectors of the resident.
2. **Runtime commands:** the CPU bit-0 commit writes the DSP input ports
   5eh/5fh and sets PA7 bit 0. The resident dispatcher at 85c6 reads the pair
   at 85cah/85cch and clears bit 0 at 85ceh. Transmit-ready stays low until
   that acknowledgment. The endpoint does not select a command handler.
3. **Overlays:** command 2 supplies the destination to the handler of the DSP
   at 840fh. CPU port 1eh bits 0/1 publish two-word halves at DSP 58h/59h and
   5ah/5bh. PA7 bits 8/9 show the pending halves. The BLDP of the native
   resident at 82bfh writes four program words and clears those pending bits.
   The CPU ready status is the inverse of PA7 bits 8..10. Python does not
   install the overlay bytes directly, and does not read them from a second
   copy of the image.
4. **Replies:** the native sender at 8603 sends tag/value to its output
   latches and clears PA7 bit 1. The CPU bit-1 acknowledgment gives the DSP
   space to send again. A bug of the native core in `io_output` showed the
   input latch in mailbox-only mode, although the writes used a separate
   output latch. Now that accessor obeys the mailbox-only mode and the
   analog-codec mode.

The coupled scheduler advances four DSP instructions for each supervisor
instruction, at I/O boundaries and also at timer polls. When the scheduler
waited until the 512-instruction timer poll, each overlay block stalled
artificially for sufficient time to trigger the download timeout of the
supervisor. The scheduling ratio and the digital serial clock (the
20.16 MHz / 8 kHz setup of the existing model, idle octet ffh, DSP interrupt
5) are model choices. They are not recovered measurements of the board clock
of the I-modem. The Am79C30 bearer routing is still not connected.

### Native verification

```sh
.venv/bin/python tools/imodem_dsp_probe.py \
  --output artifacts/imodem-native-dsp/probe.json
```

In 5,000,000 unpatched supervisor instructions:

- The native DSP reads and acknowledges all four startup commands
  (`0002:d100`, `0002:9260`, `0001:003f`, `005b:0000`).
- Image 10 at d100h agrees with all **15,072 bytes** of its source.
- Image 11 at 9260h agrees with all **31,994 bytes** of its source.
- The command ring of the supervisor is empty, with **zero queue-drain
  timeouts**.
- No spontaneous DSP replies occur during that startup interval.

A separately labeled diagnostic then seeds `8074,beef` in the outgoing ring of
the DSP firmware and runs 50,000 more supervisor instructions. The real DSP
sender sends `0074:beef`. The real supervisor ISR stores the status bytes
`74,80`, acknowledges the reply, and gives the DSP space to send again. Neither
the CPU code nor the DSP code is patched, and Python does not fill the receive
latch directly. This proves the bidirectional service path with synthetic
queue input. It does not claim that a real call generated that report.

The native regression tests also send command 19h and verify that the original
handler updates DSP data 03adh. They also exercise the retention of the reply
until the CPU acknowledgment. Full AT command handling and a working modem
call are still outside what these runs show.
