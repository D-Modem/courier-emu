# Quad V.42 receive path — first decompilation

**Resolved: the Quad now delivers bidirectional V.34/LAPM and symmetric x2 data.**
The repeating receive bytes were valid packed V.42 ODP, not established
demodulator corruption. A wrong chassis operating-mode enum selected the
no-op receive path; early caller DTE input then hit its keypress-abort handler.
See [the working call](quad-server-bringup.md#working-v34lapm-mode-enum-and-dte-handoff)
and [evidence](../artifacts/quad-v34-lapm-online-handoff/README.md).
The decompilation and dated captures below preserve the investigation.

Source: `artifacts/quad-v42-odp-trace-20261013/quad/dsp-program.bin`,
QF060003 resident plus the downloaded call overlay. Addresses below are C5x
program-word addresses.

## The host/DSP mailbox path

The resident code around `0x82d9` is not V.42 framing. It is the host mailbox
service:

```text
82d9  SETC INTM
82da  CALLD 23f0       ; fetch four words from the host window
82dc  LAR   AR1,#FF57  ; PA7/status
82de  CLRC INTM
82df  AND   #0200
82e1  BCND  82ec, NEQ  ; a word is available
82e3  ...              ; no data: compare the pending slot
82e9  XC    1, TC
82ea  IDLE
82eb  RET

82ec  ...
82f2  SETC INTM
82f3  CALLD 23f0
82f5  LAR   AR1,#FF57
82f7  CLRC INTM
82f8  AND   #0200
82fa  BCND  82ec, EQ   ; wait for host data
82fc  LDP   #1FE
82fd  LACL  @63         ; destination/program selector
82ff  LAR   AR1,#FF58
8301  LACL  #3
8302  SAMM  @09
8304  RPTB  8310
8306    CALLD 23f0
830a    MAR   *+
830b    SACL  @7d
830c    BLDP  @7d
830d    LAMM  @1f
830e    ADD   #1
830f    SAMM  @1f
8311  LACC  #0300
8313  SAMM  @57         ; acknowledge/arm host transfer
8315  BD    82ec
```

`0x8328` is the failure/power-down path, not a receive decoder:

```text
8328  SETC INTM
8329  IDLE2
832a  B     8328,*
```

It is entered after the resident has stopped accepting the current host
transaction. `IDLE2` must therefore stop instruction fetch until a peripheral
edge or NMI wakes the clock domain; after wake, `INTM` still prevents automatic
vectoring and the branch polls the mailbox.

## Serial receive ISR chain

The two relevant frame handlers are selected by the resident's handler cell
`@65`. The full-word phase is `0x83e1`; the byte-oriented phase is `0x8406`.
They are deliberately consecutive phases, not alternative modem algorithms.

```text
83e1  LDP   #7
83e2  LACC  @19
83e3  SUB   #1
83e4  SACL  @19
83e5  XC    2, EQ
83e6  CLRC  XF
83e7  DMOV  @18
83e8  MAR   *,AR7
83e9  SAR   AR7,@11
83ea  LAR   AR7,@10
83eb  LAMM  @20         ; DRR
83ec  SACL  *+          ; store received word
83ed  LAMM  @6b
83ee  OR    *+
83ef  SAMM  @21         ; DXR = next/combined transmit word
...
83fd  ...               ; next interrupt target is 83fe or 83e1

8406  LDP   #7
8407  MAR   *,AR7
8408  SAR   AR7,@11
8409  LAR   AR7,@10
840a  LAMM  @20         ; DRR
840b  BSAR  8           ; select the delayed byte in byte mode
840c  SACL  *+          ; store one received octet
840d  LACL  *+          ; fetch transmit octet
840e  SAMM  @21         ; DXR
840f  SAR   AR7,@10
8410  LAR   AR7,@11
8411  RETE
```

The byte ISR consumes the accumulator after `BSAR 8`, so the DRR shifter's
byte ordering is observable and must not be guessed from the low-byte read
API. The current model retains the prior octet in the other half of DRR. This
is the first receive-framing assumption to validate against the physical C50.

## DSP-side line processing

`0x8412` is the short line/DAC helper, not LAPM:

```text
8412  LDP   #0
8413  MAR   *,AR5
8414  LAR   AR5,@74
8415  LACC16 *+
8416  ADDS  *-
8417  LT    @76
8418  SATH
8419  SATL
841a  SACL  @7c
841b  LAR   AR5,@75
841c  LACC16 *+
841d  ADDS  *-
841e  LT    @77
841f  SATH
8420  SATL
8421  AND   #00ff
8423  ADD   @7c,8
8424  SACL  @31
8425  RETE
```

`0x8427` dispatches the four TDM phases through a table at `0x844c`, then
scales/limits the resulting sample and writes the line DAC at `0x006a`.

## What this says about V.42

No V.42/LAPM parser is present in the resident block `0x82d9..0x8500`.
The resident only:

1. receives serial words/octets;
2. places them in the circular buffers selected through `@10/@11`;
3. advances the handler phase through `@65`;
4. emits the next transmit word through DXR;
5. services host mailbox/download traffic.

This alone does not locate the V.42 decoder: the DSP can also deliver packed
bits to the supervisor, which performs protocol detection and framing. The
next trace points originally proposed were:

- writes to `@65` (`0x83fc`, `0x8404`) to identify the active receive phase;
- writes to `@10`, `@11`, `@18`, `@19`, and `@6b` to reconstruct circular-buffer
  ownership and byte alignment;
- reads/writes of the overlay's host data banks `0x58..0x5d`;
- the first transition from the V.8/V.34 overlay into the V.42 parser;
- the exact word written to `0xffd9` before the `IDLE2` path.

The existing `data-lanes.json` is empty in the failed LAPM capture, which means
that failure occurs before a decoded LAPM payload is delivered to the CPU. It
is not evidence that the CPU-side bank mapping is the immediate cause.

## Overlay state machine reached by the failed call

The capture does reach the downloaded overlay. The final snapshots are in the
resident/overlay transition at `0xc405`, `0xa476`, and `0x924d`; the last one
is a bit-manipulation helper, not the host mailbox loop. The first useful
control entry is `0x942f`:

```text
942f  LAR AR1,#6f
9430  BIT 14,*          ; call/overlay state gate
9431  RETC TC
9432  RPT #04 / POP    ; discard stale return words on the reset path
9435  LACC #82d0
9437  PUSH
9437  LAR AR1,#039f
9439  BIT 15,*
943b  BCND 9468,TC
943d  LDP #6
943d  LACC @37
943e  BCND 9468,GT
9440  CALL 94a4         ; advance mailbox/control exchange
...
946b  LAR AR1,#ffd9
946d  BIT 1,*
946f  BCND 9483,TC
9470  LAR AR1,#039f
9472  BIT 6,*
9474  BCND 9483,NTC
9475  APL @1f,#7fbf     ; clear the pending receive/control flag
9477  LAR AR1,#ffdd
9479  OPL *,#0100
947b  LAR AR1,#ffd9
947d  BIT 13,*
947f  ...
9485  APL *,#fffd
9487  CALL 9528         ; consume/update negotiated status
9489  CALL 94a4
```

`0x9528` reads `FFDB/FFDC`, copies the result into the `FF18` control area,
and uses `FFDF` plus `FFD9` bits to select the next control action. `0x9743`
is the receive/control gate: it tests `@1f`, `@62`, `FF00`, and `FFDD`, then
updates `FFD9` and schedules the callback at `0xa05f`. `0x97a0` extracts the
three-bit values from `FF08` and writes the selected values to `FF20`.

The bit-level receive/assemble helper at `0x924a..0x9267` operates on
`@1e/@1f/@20/@21`; it is the most likely V.42 symbol/bit accumulator. It
maintains a three-bit feedback value, XORs the current and delayed words,
limits with `@21`, and returns a saturated result. It is reached from the
overlay's phase machinery rather than directly from `0x8406`.

The original DSP-focused experiment proposed tracing `@1e`, `@1f`, `@20`, `@21`,
`FF08`, `FF18`, `FF20`, `FFD9`, `FFDD`, and the calls into `0x924a`, `0x942f`,
`0x9528`, and `0x9743` for one frame. Do not add a LAPM parser or inject CPU
payload yet; first establish whether the repeating pattern is introduced by
the DRR byte alignment, the bit accumulator, or the `FFD9` control gate.

## Packed ODP reaches the supervisor

`tools/inspect_quad_v42.py` analyzes the captured DSP-to-CPU bank words as
LSB-first bit streams. It never feeds data back into either emulator.

```sh
PYTHONPATH=. .venv/bin/python tools/inspect_quad_v42.py \
  artifacts/quad-v42-cpu-bitstream-20261013/quad/data-lanes.json
```

That capture contains 1,966 receive words and 2,130 transmit words. All
captured transmit words are `40ff`. The receive prefix includes **235
consecutive alternating `11` / `91` detection characters**, each with a zero
start bit, eight LSB-first data bits, a one stop bit, and exactly nine
additional mark bits before the next start. The run starts at receive-stream
bit 11,271 and ends at bit 15,727 (exclusive). Initial `ffff` receive words
are excluded from decoding but retain their bit offsets. The record is a
bounded prefix of bank reads, not a full-call or full-bearer capture.

The repeating `7f 11 ff 8b fc 5f c4 ...` bytes are therefore a packed V.42
originator detection pattern. They are not arbitrary terminal bytes or, by
themselves, evidence of broken DRR alignment or DSP demodulation. This does
not prove the Quad recognizes ODP or sends ADP, nor does it establish LAPM.

The original supervisor consumes these words at `d4f2e`, `d4f4b`, `d4f68`,
`d4f85`, `d4fa2`, and `d4fc2`. Each bank dispatch supplies `AX=word`, `CX=8`
and calls through `839d` before acknowledging that bank at port `9a`.
The `1803` callback (physical `d15b3` when CS is `cfdb`) is an LSB-first
asynchronous framing state machine; its assembled-character callback is
`8399`. This is a CPU-side framing path, not a terminal-byte interface.
The older snapshots already retain `839d=3210` from 46M through 54M
instructions. At CS `cfdb`, that callback is physical `d2fc0`, exactly
`CLC; RET`: it consumes no bits. Two call/reset paths install it at `c89ad`
and `c8fbe`. Thus valid packed ODP reaches the host interface while the saved
receive callback remains a no-op. This points to a missing firmware
receive-mode transition, not proof of a defective DSP bit accumulator. The
next concrete question is why the real call never replaces the no-op with
the required receive handler; do not patch the callback to force success.

The probe's receive-call trace now retains the last 96 dispatches across all
six banks and counts each actual `CS:callback` pair. The earlier first-96,
first-bank-only trace could fill with idle `ff` before ODP arrives. New
`receive-calls.json` entries include bank, physical callback, and character
callback; `receive-callback-counts.json` summarizes the whole observed run.
Counters also watch the callback reset, asynchronous initialization,
restoration, and framing-install sites. Snapshots include `8399` and `8517`.

The [fresh control](../artifacts/quad-v42-current/README.md) confirms **all
6,294 receive-bank dispatches use `cfdb:3210`**, including the captured ODP
tail. The character callback also remains the `13d0` no-op (`RET` at
`d1180`). Startup asynchronous initialization and each reset path execute
twice; none of the watched asynchronous selection, restore, or
framing-install sites executes. Neither CPU/DSP reports an error and Quad
PCM RX underruns remain zero. The I-modem ends with NO CARRIER, not CONNECT.
Thus the next experiment should follow the real initialization/control
transition that leaves these callbacks disabled rather than alter the
received bitstream or install a fabricated handler.

## Trace rollover cost

The 200,000-event DSP trace used a vector and erased its first element on
every overflow, moving the entire buffer for each subsequent memory event.
This made full-call traced probes disproportionately slow. The native data
trace now uses a deque, preserving ordering and the C/Python access API while
making oldest-event removal constant-time. Lowering the event limit also
trims retained history immediately. Regression tests exercise rollover for
both memory writes and fixed-watch reads, including repeated identical reads.
This is a diagnostic-performance fix, not a firmware or carrier-state change.

## Resolution: configuration, then terminal readiness

The apparent missing Quad receive-mode transition was caused by sending
chassis `003f=4`, which its original setter maps to **firmware mode 6**.
Sending **wire value 2** instead selects firmware mode 4 and naturally runs
the detection and framing handlers. No DSP accumulator or callback patch
is needed. The normal error-control setting is now the default in both probes.
Symmetric x2 subsequently passes at 64000/x2/LAPM after genuine chassis
feature provisioning (`01f2=20`), with no receiver patch. See the
[x2 evidence](../artifacts/quad-x2-symmetric-provisioned/README.md) and
[remaining asymmetric-role controls](../artifacts/quad-x2-modes/README.md).

The first data-direction failure was also not demonstrated corruption:
the caller's ATI6 explicitly reports **Keypress Abort**, with zero characters
sent. The I-modem printed CONNECT while its receive callback was still `0e0e`;
the marker pump typed into that abort handler before the firmware installed
`46cc`. Reading the actual DTE handoff fixes the send timing, without injecting
completion or imposing a fixed delay. The passing control needs just 512
additional CPU instructions, within the same 100-ms bearer frame.

The [passing strict data control](../artifacts/quad-v34-lapm-online-handoff/README.md)
receives both distinct payloads, keeps the Quad connected to its instruction
limit, and has zero PCM underruns, UART drops or CPU/DSP errors. The receive
bank trace limit in the call probe is now 65,536 events so it retains later
HDLC/data activity, rather than only the original 4,096-event ODP prefix.
The endpoint's default limit remains 4,096. Traces are still bounded and do
not constitute multi-minute or full-rate throughput verification.
