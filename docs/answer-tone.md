# The datapump's second voice: a 2100 Hz answer tone

The dial path of DSP 3.1.2 already made DTMF through the oscillator, mixer
and serial ISR of the firmware ([audio-312-path.md](audio-312-path.md)). It is
not the only generator in the resident bank. The same callback slot drives a
family of oscillators. One of them is a modem tone, not a dialling tone:
**2100.0 Hz, with a 180 degree phase reversal every 3239 samples**.

The two numbers come from the firmware, not from a specification that we read
first. The own caller of the ROM supplies them.

## How the generators are selected

The mixer at `80d3` calls the address that is in data `0x39a`. A scan of the
resident bank for stores to that cell finds the family:

| callback | what it does |
|---|---|
| `874f` | one oscillator: increment `0x3f2`, amplitude `0x3f3`, phase `0x3c0` |
| `8743` | a second oscillator on `0x3f4`/`0x3f5`/`0x3c1`, falling through to `874f` - the DTMF pair |
| `8739` | decrements a counter, inverts the phase's top bit with `XPL` when it expires, reloads, falls through to `874f` |
| `8712`, `8716` | `874f` or `8739`, then `8718`, a second oscillator that *multiplies* the tone |

The arming routine at `86d1` takes a phase increment in the accumulator and
stores it at `0x3f2`. It installs `874f`, sets the amplitude to `0x0898` and
clears the phase. Its caller at `9f40` makes this a modem tone:

```text
9f40  lacc  #4aab
9f42  call  86d1
9f44  splk  @28, #01d7
9f46  splk  @75, #0ca7     ; the reversal counter's reload
9f4c  splk  @1a, #8739     ; the reversing callback
9f58  splk  @73, #06cf     ; a quieter amplitude than 86d1's
```

At the 7200 Hz of the dial path, `0x4aab / 65536 * 7200` is **2100.04 Hz**,
and `0x0ca7` is 3239 samples, or **449.9 ms**. These are the V.25 answer tone
and its 450 ms phase-reversal period, in the resolution of the numbers. This
is a second, independent confirmation of the 7200 Hz value that
`audio-312-path.md` inferred from the DTMF increments: no other possible rate
puts `0x4aab` on a standard tone and `0x0ca7` on a standard interval at the
same time.

`8718` is the same type of item, one level higher. It advances a second phase
at increment `0x0089` - 15.05 Hz at 7200 Hz - and multiplies the carrier by
it. That is the ANSam amplitude modulation of V.8. It explains why the
selector has four callbacks and not two: with or without reversals, and with
or without modulation.

## Rendering it

`courier_emu.answer_tone` arms the tone with the instruction words of the
firmware, copied exactly from `9f40`, `9f46`, `9f4c` and `9f58`. Then it runs
the same main-loop mixer and serial ISR body that `audio312` runs for DTMF. It
does not synthesize anything.

```sh
.venv/bin/python -m courier_emu.answer_tone \
  --rom artifacts/courier-board-21210-capture-403/courier-board.rom \
  --output /tmp/answer-tone --variant ans-reversals --seconds 2
```

The saved runs are in `artifacts/answer-tone-01/`. Measured from the rendered
PCM:

| variant | callback | measured | reversals |
|---|---|---|---|
| `ans` | `874f` | 2100.0 Hz | none |
| `ans-reversals` | `8739` | 2100.0 Hz | every 3200-3264 samples |

The reversal spacing has the resolution of the 64-sample block of the
detector. The range includes the value 3239 of the counter.

## One correction to the harness, and it is load-bearing

`audio312` enters the frame at `80d3`, the callback call itself. That is
correct for `874f` and `8743`. It is incorrect for `8739`, because its `BANZ`
tests the register that the ARP points at now, not the `AR1` that the
instruction before it loaded. The mixer sets ARP to 1 at `80c9`. If you enter
below that, ARP has a different value. Then the counter is never stored back,
`XPL` operates on each sample, and the output is a square of constant
magnitude, not a tone. Thus this harness enters at `80c7`, the top of the
sample body of the mixer.

We record that failure because it is silent: the path runs, the ISR transmits
1440 words, and the result is only the incorrect signal.

## What this does not show

* **Not a boot.** As with `audio312`, the frame scheduling, the idle RAM and
  one buffer pair are fixtures. The harness enters the ISR body directly, not
  through an interrupt.
* **Not the decision of the supervisor to send it.** A state machine that this
  harness does not run gets to `9f40`. The harness renders the generator, armed
  in the same way as that site arms it.

  *Closed on this image too, 2026-09-08.* The path is traced in
  [the section below](#the-path-to-9f40). *Also closed on the other image.*
  `ATA` on `IDSDL302.ROM` (DSP 3.0.13) sends ANSam in the full emulator, with
  the supervisor, from its own equivalent of this site at `0x9f62`. After it,
  it sends a 2250 Hz tone armed at `0xd354`. Refer to
  [ata-answer-tone-302.md](ata-answer-tone-302.md), which also maps the
  oscillator family of 3.0.13 onto this one: all of the code addresses are
  different, but the data cells - increment `0x3f2`, amplitude `0x3f3`, phase
  `0x3c0` - are the same in the two builds. That does not find the own path of
  3.1.2 to `9f40`.
* **ANSam renders too.** *Corrected.* Before, this section said that the
  `8712` and `8716` variants could not be rendered, and said that the cause was
  missing delay-line state. The real cause was a bug in the C5x core of this
  repository: `MADD` and `MADS` read their coefficients from data memory and
  not from program memory. Thus the shaping filter at `8a88` returned zero.
  With that bug corrected - refer to [fsk-modulation.md](fsk-modulation.md) -
  the two variants give the 15.05 Hz amplitude modulation, as a symmetric
  sideband pair at 2085 and 2115 Hz. Each sideband is about 10% of the
  carrier.
* **The `&T` self-test was not the way in.** When we drove the supervisor with
  `AT&T1`, `AT&T8` and `ATS18=2&T8` under `courier_emu.mailbox_tap`, it gave
  `OK` and the same fourteen idle-cycle mailbox messages as a bare `AT`. We
  found the generator above when we read the writers of the callback slot.

  *Corrected.* Before, this item also said "the loopback path does not engage
  in the emulator", because the runs showed no different execution. We read
  that from `hot_addresses`, which gives only the most-executed addresses. Thus
  the idle loop is the largest part of it in the two cases. When we record each
  address instead - `CourierMachine(code_observer=...)`, added for this - we
  see that `AT&T8` gets to **548 addresses a bare `AT` never reaches**, in
  about thirty regions of the supervisor. The handler runs. It is not shown
  that it gets to the datapump in the observed window.

## The path to `9f40`

No branch goes to `9f40`. The code falls into it, from a state that the
scheduler dispatches.

### The scheduler

`875c` is a one-shot state machine that the idle path drives (`9f0d: call
875c`). Two memory-mapped cells control it - `0x006e`, a frame countdown, and
`0x006d`, the address of the state to run when that countdown expires:

```text
875c: lamm @6e        ; the countdown
875d: bcnd 8762, eq
875f: sub  #01
8760: samm @6e
8761: retc neq        ; still waiting
8762: lamm @6d        ; the state vector
8763: retc eq         ; nothing armed
8764: bacc            ; branch into the state
8765: samm @6e        ; (entry point) arm the countdown
8766: pop
8767: samm @6d        ; (entry point) arm the state
```

### What arms the answer-tone state

Two sites write `9f3e` into that vector. A bit of the flags word at data
`0x006f` gates each site:

```text
afeb  lar ar1, #6f              reached by conditional call from
      ...                       b0e7, b233, b5a1 and b5ca
afff  bcnd 9e09, tc             gate: bit 0 of 0x006f
9e0a  splk @6d, #9f3e           @26 = 4000, @27 = 0008

a320  countdown at 0x031a       called from aaa2 and ab7e
a327  bit 14, *                 gate: bit 1 of 0x006f
a32c  call 8140                 sets the codec sample rate first
a32e  b 9e13
9e14  splk @6d, #9f3e           @26 = 4010, @27 = 0000
```

Note that `bit 14` is a bit *code*, not a bit number: the C5x tests bit
`15 - code` (the core calculates `(~op >> 8) & 0xf`). Thus `bit 14` reads bit 1
and `bit 15` reads bit 0. The disassembler prints the raw code.

Path B calls `8140` on its way. This is a small confirmation of
[codec-rate-312.md](codec-rate-312.md): the firmware programs the sample rate
immediately before the tone that assumes it.

### Into the tone

```text
9f3a: lacc @2b ; sub #01 ; sacl @2b ; retc gt    the timer variant
9f3e: call a092                                  falls through
9f40: lacc #4aab ; call 86d1                     the arming
```

`9f3a` is the same state with a countdown before it. The code enters it from
`9f12`, `9f20`, `9f28` and `9f33`. The stubs at `9f11` and `9f15` that dispatch
to them are armed at `9e1d` and `9e21`.

### Confirmed by running it

We did not use a full boot, because this image does not get to it now, for
reasons that are not related to this path. Instead, we confirmed the last two
links directly. We seeded `0x006d` with `9f3e` and `0x006e` with zero, then
entered the scheduler at `875c`. It executes `9f3e`, `9f40` and `86d1`, and
gives:

| cell | value | |
|---|---|---|
| `0x3f2` | `4aab` | 2100.04 Hz at 7200 |
| `0x3f3` | `0898` | `86d1`'s own amplitude literal |
| `0x39a` | `874f` | the oscillator, installed |

Thus the scheduler gets to the arming, and the arming loads the answer
tone.

### What sets the two gate bits

A scan for writes to `0x006f` must be careful in the two directions.
`SPLK @6f` is DP-relative. Thus most apparent writers are `0x036f` or `0x03ef`
at DP 6 or 7, and are not related to this word. The reliable writers get to it
through `lar ar1, #6f` and an indirect `*`, and a search for `@6f` never finds
these. We can only attribute writes that have an `LDP #000` immediately before
them, or an explicit AR load.

Three sites pass that filter. We confirmed each of them when we executed it:

| site | instruction | effect on `0x006f` |
|---|---|---|
| `9090` | `lar ar1, #6f` / `opl *, #0003` | **sets both**, preserving the rest |
| `a372` | `ldp #000` / `splk @6f, #0043` | **sets both**, and bit 6, as a whole word |
| `a337` | `ldp #000` / `splk @6f, #0040` | **clears both** |

`9090` is itself a scheduler resume. Two instructions before, the code
yields -

```text
908c: lacc #0508
908e: call 8765        ; @6e := 0x508, @6d := the return address
9090: lar ar1, #6f     ; ...resumed 1288 frames later
9091: opl  *, #0003
```

Thus a timer opens the gates, not an event. `9f98`, in the answer sequence
itself, gets to `a372`. Thus that write asserts the bits again. It does not
open them for the first time.

Note that `9091` works only because `ARP` is 1 when it runs: `lar ar1, #6f`
loads the register but does not select it. With `ARP` at 0, the `opl` writes
`0x0000` instead. When we execute the pair with `ARP` forced to 1, `4400`
becomes `4403`. With `ARP` at 0, the cell does not change.

Several sites clear the two gates when they write the full word - `a338`
(`#0040`) above, and at DP 0 also `d9cc` (`#0000`), `da31` and `da46`
(`#0010`).

**Unresolved.** `c583` (`xpl @6f, #0001`) and `c58f` (`xpl @6f, #0002`) toggle
bits 0 and 1 of *something*, in a toggle-and-test shape that usually means an
alternating-sample flag. Their nearest `LDP` is 20 and 32 words back, with a
`ret` between. Thus the DP comes from the caller of that routine, and we
cannot attribute these writes to `0x006f` by reading alone. The
`MACD`/`MPY`/`APAC` around them suggests that they belong to a filter and not
to this word. But that is an impression, not a measurement.

### What decides to run the yield

`9083` does not occur in the image as a target, because no branch goes to
it: a **skip-return** gets to it. `907f` calls `901a`. The two-word `b 9099` at
`9081` either executes or is stepped over. This depends on how that call
returns.

```text
901a: lar  ar1, #ff2d
901c: lacl *-            ; scan down for the first non-zero word
901d: bcnd 901c, eq
901f: sar  ar1, @5b      ; where the scan stopped
9021: sub  #ff27         ; as an index
9024: sub  #04
9025: retc lt            ; index < 4 -> ordinary return, and 9081 runs
902a: bit  1, @1f        ; bit 14
902b: retc ntc           ; clear -> ordinary return
902c: call 90c3
902e: pop
902f: add  #02           ; return address + 2: step over the branch
9030: bacc               ; -> 9083, the yield
```

We examined the two conditions. We ran the call site with the table and the
flag seeded, and read where the control goes:

| highest non-zero word | index | `@1f` bit 14 | lands on |
|---|---|---|---|
| `ff2b` or below | 0-3 | set | `9099` (normal) |
| `ff2c` | 4 | set | **`9083`** (yield) |
| `ff2d` | 5 | set | **`9083`** (yield) |
| `ff2d` | 5 | clear | `9099` (normal) |

Thus the yield - and 1288 frames later the two gate bits, and after that the
answer tone - runs only when two conditions are true. The table that ends at
`0xff2d` must be filled to two words or less from its top, **and** bit 14 of
`@1f` must be set. One condition alone is not sufficient.

Two cautions, if you run this again. First, the scan stops at the *first*
non-zero word from the top. Thus the index measures how high the table is
filled, not how many entries it holds. More words below the top do not change
it. Second, you must enter the call site with `DP` already at 6, as `9077`
leaves it. If you enter at `907f` with `DP` at 0, `sar ar1, @5b` writes the
incorrect cell, and each case falls through to `9099`. This looks exactly like
a closed gate.

It is still not shown what fills that table, or what sets bit 14 of `@1f`.

