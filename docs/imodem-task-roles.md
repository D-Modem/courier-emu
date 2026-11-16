# I-modem task roles from code and queue routing

This is an analysis of Ie030002. It follows the nine task entries that
[the startup trace](imodem-vrtx-startup.md) verified. The roles below keep
actual behavior separate from inferred expansions of proprietary
abbreviations. Selected instruction spans and identifying strings are in
`artifacts/imodem-task-roles/disassembly.txt`.

## Task map

| Task / ID | Input queue | Behavior | Interpretation and confidence |
|---|---|---|---|
| TID_TOUT / 1 | 0, QID_TOUT | The periodic timer service wakes it. It removes an expired timer and dispatches the event of that timer. | Timeout processing, confirmed. Not terminal output. |
| TID_T3L2 / 4 | 3, QID_QIDL3L2 | Dispatches upper-layer requests to the layer-2 link state machinery at `6806:0009`. | Layer 3 → layer 2 worker. Strong evidence from the queue name and the code. The exact spelling of the T prefix is not recovered. |
| TID_CES3 / 2 | 1, QID_CES3 | Sends requests into the signaling/call-state processing at `616b:000f`. | CE → signaling layer 3. Strong structural evidence. CE is the call-control executive side. Its original full name is not present. |
| TID_S3CE / 3 | 2, QID_S3CE | Dispatches signaling primitives at `6b39:0002`. This includes the forwarding of selected events to layer 4. | Signaling layer 3 → CE. The paired queues and the `NLS_CE_PROC` diagnostic of the handler confirm the direction. |
| TID_L2S3 / 6 | 5, QID_L2S3 | Sends link-layer indications/data to `5f41:0000`. The channel configuration selects an alternate protocol path at `4546:0009`. | Layer 2 → signaling layer 3. Strong evidence. Includes the processing of call-signaling packets. |
| TID_P3CE / 9 | 8, QID_P3CE | Accepts only event codes 4 and 7 in `6c37:0003`. Forwards these through `6efe:0ab4` to queue 10. Other codes have no handler action. | P3 → CE relay, behavior confirmed. “Packet layer 3” is a possible expansion of P3, but this code does not show it. |
| TID_LLL2 / 5 | 4, QID_LLL2 | Sends lower-layer messages/frames into `666c:0009`. Parses the frame address fields and selects a link context. | Lower/link layer → layer 2 receive worker. Strong evidence. The exact LL expansion is not recovered. |
| TID_MODEM / 12 | Not one of the C queue-wait loops | Starts at `a400:0008`, initializes DSP-related state, then continues the modem firmware path. Uses callbacks into the call-control/layer-4 code. | Modem supervisor task, name and startup confirmed. An AT exchange is now verified: `ATI2` answers `OK` and `ATI3` the banner over SIO0 ([the AT interface](imodem-at-interface.md)). |
| TID_CEML4 / 10 | 10, QID_CEML4 | Calls `7561:0009`, which dispatches connection, disconnection, release and status indications to the modem/layer-4 handling. | CE → modem layer-4 interface. Strong evidence. The primitive names of the handler support it. |

Most of the short C tasks are queue consumers. They call a larger protocol
handler and release the buffer of the received message. They are workers at
protocol boundaries. They are not nine independent applications.

## Why TOUT is timeout processing

The chain is explicit:

1. At `7360:1f85`, the periodic interrupt handler calls `46bc:0002`.
2. `46bc:0002` reads the head of the timer list through `DS:9ecc`. It
   compares its 32-bit countdown with `0x14`, and subtracts `0x14` while the
   timer is pending. This shows the countdown units. It does not show their
   physical duration in milliseconds.
3. When the timer expires, `46bc:0058` posts to queue 0 through `4063:005b`.
4. `459b:0025` waits on that queue through `4063:00a5`. After the wakeup,
   `459b:0056` calls `45a1:0001`.
5. That routine unlinks the timer, decrements the active-timer count at
   `DS:9eca`, clears its allocation/event word, and dispatches by event type.

`6958:0005` initializes the list as 50 records of 16 bytes that start at
`DS:9ed0`. `6958:0060` allocates and inserts timer records. This is timer
management. It is not a UART output buffer.

## Direction of the ISDN queues

The queue-creation strings are in the data that is copied from physical
`98d50` to segment `0ce0`. The paired queue names and consumers show the
general flow:

```text
CE --CES3--> signaling layer 3 --T3L2--> layer 2
CE <--S3CE-- signaling layer 3 <--L2S3-- layer 2 <--LLL2-- lower layer

S3CE --selected indications--> queue 10 / CEML4 --> modem/layer-4 handling
P3CE --event 4 or 7-----------> queue 10 / CEML4
periodic interrupt ---------> queue 0 / TOUT --> expired-event handlers
```

`T3L2` operates on the link context through `DS:6b8c`. Its handler selects the
link with the channel/address fields from the request. `LLL2` operates on that
same link-state area from received frames. At `666c:010c` and after, it
extracts one address field with a shift by two and a different field with a
shift by one. Then it examines values that include `3f` and `7f`. This agrees
with SAPI/TEI handling. That protocol interpretation is an inference. The
field extraction and the shared state are directly visible.

`L2S3` sends data to the signaling parser and state machinery. The default
diagnostic of the `S3CE` dispatcher is literally
`NLS_CE_PROC: UnSupported prim code=` at relocated data offset `12c0`.
Do not use the letters alone as proof of the original expansion of CE.

## Modem/layer-4 bridge

The [CEML4 deep trace](imodem-ceml4.md) after this follows BCH_ENABLED through
the bearer selection to mailbox command 005eh. Isolated execution verifies the
arguments 1 and 2 for selectors 6 and 7.

`CEML4` stores its message at `DS:a48c` and sends byte `message+8` to
`7561:0009`. Its case branches refer to these strings directly:

- `Prim = N_CONN_IN : `
- `Prim = N_CONN_CF : `
- `Prim = N_DISC_IN : `
- `Prim = N_DISC_CF : `
- `Prim = N_REL_IN : `

The companion dispatcher at `7561:0272`, for primitives that come from the
modem, refers to `l4_SETUP : modem primitive`, `l4_DISCONN : modem primitive`,
`l4_CONNECT : modem primitive` and `l4_DIGIT : modem primitive`.
These are concrete evidence of the modem/call-control interface. They are not
only an interpretation of the CEML4 label.

`P3CE` is very small: its event filter calls `6efe:0ab4`, which calls
`46c5:000c`. That last routine copies the 24-byte message and posts it to
queue 10 at `46c5:009c`. A scan for immediate far calls found no direct
caller of the queue-8 posting wrapper at physical `46603`. Indirect calls are
still possible. Thus this build keeps the P3 relay, but its usual traffic
source and the exact meaning of P3 are not known. Do not describe it as a
proven active X.25 subsystem.

## Scope of verification

The earlier runtime trace verified the startup and the first execution of all
nine tasks. We recovered the queue routes and the task responsibilities here
statically, from actual code and referenced strings. We did not inject
synthetic protocol messages to claim full coverage of the state machine. This
analysis did not positively identify an AT parser or a terminal-output task.
