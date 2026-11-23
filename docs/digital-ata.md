# A modeled line: the digital ATA

`--exchange` puts a central office on the subscriber loop, in place of a fixed
`--daa-line` state. It is the network side of one line, and it is fully in the
codec sample stream. It has no loop current, no hybrid and no two-wire pair.
Thus, it is digital, not an analog terminal adapter. It monitors the hook. It
plays the tones that the loop carries. It **decodes the dialed number from the
audio that the modem transmits**, and it routes the call:

```sh
./courier run main211.xmf --exchange \
  --exchange-number 5551212=answer --at "ATDT5551212" \
  --instructions 120000000
```

```json
"exchange": {
  "state": "connected", "dialed": "5551212", "digits_decoded": "5551212",
  "outcome": "answer", "rings_delivered": 2, "calls": 2
}
```

Nothing gives the exchange that number. The supervisor qualifies its line
detector on the 350+440 Hz dial tone of the exchange. The C51 puts DTMF on the
line. A Goertzel receiver in the exchange reads the DTMF back from the transmit
stream. This is the difference from `--daa-line dial-tone`. That option
supplies a line state that the harness selected. It removes dial tone when the
model decides that dialing started. `courier_firmware_analysis.md` records
this gap under "What the dial sequencer is waiting on".

If you route the same number to `busy`, the call stops at the tone, with no
`CONNECT`: `state=busy outcome=busy connected=false`. The firmware does not
print `BUSY` for it. Call-progress tone detection belongs to the DSP, and no run
got to it. Thus, the exchange proves the line here, not the report.

The states, and what the loop carries in each state:

| state | line | leaves on |
|---|---|---|
| `idle` | silence, on hook | seizure |
| `dial-tone` | 350+440 Hz continuous | first digit, or 16 s to reorder |
| `collecting` | silence | `#`, a directory match, or 4 s interdigit |
| `routing` | silence, 500 ms | the outcome for the number |
| `ringback` | 440+480 Hz, 2 s on / 4 s off | answer after N rings |
| `busy` | 480+620 Hz, 500/500 | hang up |
| `reorder` | 480+620 Hz, 250/250 | hang up |
| `answer-tone` | 2100 Hz | 3 s, then connected |
| `connected` | whatever `peer_audio` supplies, else silence | release |
| `ringing` | ring cadence toward the modem | the modem going off hook |

`--exchange-number NUMBER=OUTCOME` routes one number to `answer`, `busy`,
`reorder` or `no-answer`. `--exchange-outcome` sets the outcome for a number
that has no route. `--exchange-answer-after` sets the ringback cycles before
pickup. `--exchange-answer-tone` sets how long 2100 Hz continues before the
exchange hands on the call. `LineExchange.ring()` offers an incoming call. It
drives the ring detectors of the codec directly, not through `--ring`.

### The firmware places this call

With `--exchange`, no DTE-level dial replacement remains. `arm_dial_tones`
returns and does not read the command. The supervisor itself does each step
below against the modeled line:

| step | what the firmware does | where |
|---|---|---|
| parse | reads the dial string out of its own command buffer | `0x82652` |
| seize | drives the hook relay, board latch 0 bit `0x04`, low | `0x5e317` |
| qualify | counts its own five detector hits before accepting dial tone | `0x5dbee` |
| encode | folds each character to a keypad index | `0x6353c` |
| dial | sends `0x16:0000`, the digit on tag `0x13`, `0x16:0000` | `0x63553` |
| time | holds each tone and gap on its own `[0x161]` countdown | `0x82342` |

Thus, `--exchange` implies `--tick-source dsp`. The dial-tone wait, the tone
duration and the interdigit gap all count on the countdown chain of the
supervisor. Without pacing, the harness must replace each of them, and the
exchange exists to replace that arrangement. The harness models the line
detector here and does not execute it. This is because the native core does
not yet run the recovered DSP detector path from start to end. The fallback
answers the `0x7c` poll with a low-band reading while the loop carries tone.
The supervisor counts its own five hits.

**Nothing renders the digits.** `dsp_bridge.exchange.dialed` is what the line
really heard. It stays empty while the firmware dials `ATDT5551212`. These
notes said before that "the tone generator is the ASIC's", and that is wrong.
The dial path sends three constant lanes with each digit: `0x19`, `0x1a` and
`0x1b`. These are host-write tags. Their handlers store into **DSP data
memory** at `0x03ad`, `0x0392` and `0x03f1`. The tone parameters go to the C51.
Thus, the synthesiser belongs to the datapump. The missing item is that the
harness does not get to that code. It is not a generator somewhere else that
the harness does not model. See [what the ASIC does](what-the-asic-does.md).
The run does report the sequence of commands that the supervisor sent:

```text
0016:0000  0013:0005  0016:0000   ...   x7   ->  commanded 5551212
```

The commands are about 600 ms apart, on the timers of the firmware. Thus, the
exchange hears silence, times out and returns reorder. This is the true state:
the firmware places the call, but the board that it talks to cannot yet put a
tone on the line.

We had to repair one bug before any of this could run. The receive handler at
`0x6ad6e` takes a message tag from ports `0x58`/`0x5a`. Then it takes its word
from `0x5e`/`0x5c`. The bridge served the C51 status latch on those two ports,
also while a reply was in the queue. The detector consumer at `0x5e4c4` read
`0xffff` for a reading that the bridge had already answered. It counted it as
out-of-band, and hung up. Now, queued replies own the data lanes.

### What the C51 puts on the line

The core has no tone generator of its own. Before, it had hand-written `sin()`
in C++: a DTMF pair generator, a 1300 Hz calling indicator and a 2100 Hz ANSam
approximation. These replaced the DAC output of the datapump. They *discarded*
its accumulation to make space. We removed that replacement, and also
`set_dtmf_digits` and `set_synthetic_line`. Now the line carries only what the
C51 calculates through its AC01. On 3.0.13, this is the DTMF of the firmware
itself. The modeled exchange decodes it as the dialed number
(`artifacts/dtmf-emulator-302-01`).

An answered call gets to the datapump. Ring the loop and answer it. Then the
recovered call overlay starts and executes. What it writes is not audio. The
frame ISR at `0x0228` keeps a 32-bit phase accumulator in `@7c`/`@7d`
(`0xfffc`/`0xfffd` at DP `0x1ff`). Before, the core read `0xfffd` as the DAC.
This gives a linear ramp with a constant step, which measures as broadband
noise.

The ISR calculates a word from the accumulator and sends it through `@7a` to
`0xffff`. That slot carries only two different values. Neither is a waveform.
`set_line_dac_slot` makes the choice switchable. Thus, you can measure the
answer and not assume it.

Thus, the datapump runs, but the destination of its PCM output is not known.
The next item to examine is the `tblr` at `0x022e`, which reads a table based at
`0x824d`. No run made V.21. The harness only measured it.

Without `--exchange`, nothing above applies. The `--daa-line`, `link` and SIP
paths keep their replacements. These include the parsed `ATD`, the faked line
transition and the digits that the harness makes.
