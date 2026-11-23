# Browser GUI

```sh
./courier gui
```

This command opens a local browser interface. The interface has these parts:

- Firmware selection, and start and stop controls
- An AT-command console
- The front-panel LEDs, live
- A transcript download
- Worker diagnostics

The GUI uses the CLI workers that exist. It adds no dependencies. XMF and ROM
images use the analog console. NAC images use the ISDN terminal. External
analog backends, and simulated lines that are not disconnected, enable the DSP
automatically. For a disconnected simulated line, **Enable DSP** is optional.

## Front panel

The analog panel shows the live AA, CD, OH, MR, CS, SYN and ARQ/FAX states
from the latch model of the emulator:

- Bright red: on
- Dark red: off
- Grey `?`: not known

HS, RD and SD are not mapped yet, and they show as not known. NAC/ISDN
sessions do not supply panel data. A stopped session shows an idle panel.

## Text display and DTE format

The **Text display** of the terminal is **8-bit text (Latin-1)** by default.
This keeps all eight bits. **7-bit text (strip parity, opt-in)** is available
to examine a known 7E1 stream. Do not use the 7-bit display to repair UART
framing. The display setting changes only the display and the conversion for
Save transcript. It does not change the UART settings of the firmware or the
input that the GUI sends. The session buffer keeps the original console bytes,
thus a change of view also applies to the output that exists. Binary terminal
sessions are not available yet.

The GUI sets the real **DTE format** to **8N1** by default. When the firmware
accepts AT, after start-up and profile load, the attention adapter writes the
selected format to the active setting of the firmware. Thus, `ATI4` reports
`PARITY=N WORDLEN=8` (the spaces can be different). To keep the stored setting,
select **Preserve stored framing** under Analog board settings. The GUI does
not emulate the raw-pin autobaud timing, and it does not change other EEPROM
settings.

## Files, ports and limits

The GUI lists the `.xmf`, `.rom` and `.nac` files in the current folder. To
use a different folder or port, or to not open a browser, use this command:

```sh
./courier gui --directory /path/to/firmware --port 8765 --no-browser
```

The server binds only to `127.0.0.1`. Ctrl-C stops the server and its
emulator session. If you close the browser, the modem does not stop. The
terminal history and the diagnostic history each keep the latest 200,000
characters.

## Calls from the GUI

Before you start an analog XMF/ROM modem, select a **Connection**:

| Connection | Configuration | Connects to |
| --- | --- | --- |
| Simulated analog line | Disconnected, quiet, dial tone or ringing | Local line state only. No external calls. |
| SIP / PBX | Server, user name, password (or an environment variable), optional destination URI template, G.711 codec and local ports | An outgoing UDP/IPv4 SIP INVITE and RTP, through the SIP backend that exists |
| Another emulator | UNIX socket path, Listen or Connect, the same PCM-only setting on the two ends | A different local emulator |
| Physical line | Apple helper path, sample rate, transmit gain and a hardware confirmation | The experimental macOS Apple A1082 USB modem FXO bridge |

When the firmware is ready, type the number and click **Dial · ATDT**.
**Answer · ATA** answers at the modem, not at the SIP layer. These controls do
not show incoming SIP calls. The buttons send real serial commands. They do
not make modem results. In online data mode, use **Escape · +++** first. Wait
for the `OK` of the firmware, then click **Hang up · ATH**. Escape does not
send a carriage return. It stops the terminal input for the selected guard
time before and after. If you changed S12, make the guard time longer. `ATH`
is not an out-of-band disconnect. To end the worker session, use **Stop**.

### SIP

Select SIP / PBX, and type the server, the user name and the password. The
password applies to that start only. It has priority over the environment
variable. The GUI gives it to the child process through the environment, never
on the command line. The GUI does not save it to disk, does not return it in
the API state and does not put it in the diagnostics. The field becomes empty
after a successful start. Type it again for the next session. This is a local
interface, not a service that manages credentials remotely.

You can also leave the password empty, and set `COURIER_SIP_PASSWORD` (or a
different variable that you name in the fallback field) before you start the
GUI:

```sh
export COURIER_SIP_PASSWORD='your-password'
./courier gui
```

In a target such as `sip:{number}@{server}`, the GUI replaces `{number}` with
the dialled number and `{server}` with the server. This minimal analog backend
does not send REGISTER. Use a PBX that accepts direct INVITEs, with or without
Digest authentication. A SIP/RTP connection alone does not show a trained
modem connection.

### Two emulators

Start a second server with `./courier gui --port 8766`. Two tabs of one server
share one modem, thus use different server ports. On the two servers, select
the same short socket path (for example `/tmp/courier-gui-line.sock`). Select
Listen on one and Connect on the other. Start the two within 30 seconds. The
socket role does not select the caller and the answerer: dial on one, and
click Answer on the other.

PCM-only is the default. It must be the same on the two ends. It disables the
modelled training and carrier events, and it supplies no dial tone. Thus, you
can have to send `ATX0` before you dial. If you clear PCM-only, the modelled
call helpers operate. This does not show that the DSP alone trains.

A stopped listener can leave its socket. Select a new path, or remove the old
socket **only after the two workers stop**. The GUI never removes a path that
exists.

### Physical line

Refer to [Apple USB Modem line backend](apple-usb-line.md). It tells how to
build `.build/apple_line`, the macOS audio permissions, the hardware selection
and the firmware and settings that qualify. This is not a general USB or serial
modem driver.

**WARNING:** Connect the A1082 FXO to a powered FXS/PBX analog line. Do not
connect it directly to a different modem that has no power. A dial can make a
real call that costs money. The GUI asks for a confirmation at each start.

**Analog board settings** show the board ID, the EEPROM fixture, the DTE
format and the tick source. For the captured 4.03 set-up, use its ROM folder
with `--directory`, board 7, `idsdl403` and the default timer. Do not use that
fixture with different firmware. Stop first asks for a normal console cleanup.
The safety messages of the helper and the last on-hook readback show in Worker
diagnostics. After a forced shutdown or a failed readback, examine the line.
If necessary, disconnect the modem. If the host stops unexpectedly, the GUI
cannot release the line.

## Limits

These controls give access to backends that exist. They do not add DSP
functions. `main211.xmf` completes `ATI11` when idle, but it still has known
limits in call training. Other firmware and backend sets have their own limits
in the linked documents. NAC sessions keep their ISDN terminal, and the
external analog controls are disabled for NAC.
