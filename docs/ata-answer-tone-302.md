# ATA on 3.0.13: the datapump's answer voice, end to end

[answer-tone.md](answer-tone.md) showed that DSP **3.1.2** contains a family
of oscillator callbacks: a plain 2100 Hz tone, a tone with 450 ms phase reversals,
and a tone with 15 Hz amplitude modulation. It rendered all three through the
mixer and the serial ISR of the firmware. It could not show the supervisor
when it *decides* to send one:

> **Not the supervisor's decision to send it.** `9f40` is reached from a state
> machine this harness does not run.

That gap is now closed on **3.0.13**, in the full emulator, without a component
harness and without fixtures. `ATA` on `IDSDL302.ROM` puts two tones on the line.

## What comes out

We captured this with `--dsp-tx-pcm`, after we deleted the tone generator of the harness
(commit `797ed28`). Thus, only the C52 program can have made
them. The capture is in `artifacts/ata-answer-tone-302-01/`.

| burst | onset | length | measured | identification |
|---|---|---|---|---|
| 1 | 2.49 s | 3.29 s | 2100 Hz +/- 1.5, sidebands at +/-15.05 Hz near 10% | **V.8 ANSam** |
| 2 | 5.83 s | 1.49 s | 2250.00 Hz, no sidebands | consistent with **V.22/V.22bis unscrambled binary 1** |

The ANSam identification is certain. The carrier is within 1.2 Hz of 2100, the
first-order sidebands are the 15.05 Hz modulation, and the second-order pair is
at 1%. It agrees with the 3.1.2 answer tone rendered at the component level in
`artifacts/answer-tone-01` (sidebands 0.101 / 0.100). That agreement is
important, because these are **different images with different code**.
None of the oscillator addresses of 3.1.2 contain the same words in 3.0.13. Thus, this is
not the same routine measured two times.

We now found the two tones in the firmware. Refer to
[the generators](#the-generators-and-what-arms-them) below.

## The generators, and what arms them

3.0.13 relocates the oscillator family of 3.1.2, but it **keeps the same data cells**.
For this reason, the two agree, although `dsp-map-302.md` warns that the mailbox
cells are different. The mixer at `80e0`/`80e4` calls the routine that is in `@1a`/`@1b`
(`0x39a`/`0x39b` at DP 7), exactly as the mixer of 3.1.2 does.

| role | 3.1.2 | 3.0.13 |
|---|---|---|
| arm routine | `86d1` | `86dc` |
| one oscillator | `874f` | `875a` |
| pair oscillator | `8743` | `874e` |
| phase reversals | `8739` | `8744` |
| ANSam (15.05 Hz AM) | `8712` / `8716` / `8718` | `871d` / `8721` / `8723` |

The cells are identical in the two versions: increment `0x3f2`, amplitude `0x3f3`, phase `0x3c0`,
output `0x3c7`.

### ANSam, at `0x9f62`

This is the direct equivalent of `9f40` in 3.1.2, with the same constants:

```text
9f64: lacc #4aab          ; 2100.04 Hz at 7200
9f66: call 86dc
9f6a: splk @75, #0ca7     ; 3239 samples = 449.9 ms reversal
9f70: splk @1a, #8744     ; reversals
9f77: splk @1a, #8721     ; ANSam
9f7a: splk @1a, #871d     ; ANSam
9f7c: splk @73, #06cf
```

`8723` loads the increment `0x0089` (15.05 Hz) and multiplies the carrier by it.
At runtime, `0x3c0` advances by `0x4aab` for each sample, and `0x3f4` by `0x0089`.

### The 2250 Hz tone, at `0xd354`, reached from `0x9ffc`

```text
9ffa: splk @2b, #0096     ; state timer
9ffc: call d354
      d354: lacc #5000    ; 0x5000/65536*7200 = 2250.00 Hz exactly
      d356: b    86dc     ; a tail-call - see below
```

`86dc` then stores the increment at `0x3f2` and installs the **plain** oscillator
`875a` in the callback slot. It sets the amplitude to its own literal `0x0898`,
and it clears the phase.

Two items are important to record. First, `d354` ends in `b 86dc`, not
`call 86dc`. A search for calls to the arm routine finds the five literal
callers (375, 600, 1650, 2025 and 2100 Hz), and it **does not find this one**.
We found it with a search for all words equal to `86dc`.

Second, this corrects an earlier guess in the history of this repository. We saw a cell at
`0x3ef` advance by `0x5555`, and we interpreted it as a 2400 Hz carrier. This
suggested that the tone was the carrier of V.22, rotated 90 degrees for each symbol. That was
wrong. `0x3ee:0x3ef` is a *32-bit* accumulator (`d901`) that advances by
`0x01555555`, and `0x5555` is only the delta of its low half. The tone is a plain
oscillator, made directly.

Thus, the *signal* is the same as V.22 unscrambled binary 1 on the line:
2400 Hz minus 150 Hz, which is 90 degrees for each symbol at 600 baud. But the
*implementation* is a single tone, not a running modulator.

### Confirmed at runtime

In the middle of the burst, the emulator shows `0x3f2 = 0x5000`, `0x3f3 = 0x0898` and
`0x39a = 0x875a`: the increment, the amplitude literal of the arm routine, and
the plain oscillator. The static and the dynamic results agree.

## How far down the ladder it goes: two rungs, then silence

The firmware contains a descending fallback ladder. These are all the tones that it can arm:

| increment | frequency | |
|---|---|---|
| `4aab` | 2100.04 Hz | V.8 ANSam / V.25 answer |
| `5000` | 2250.00 Hz | V.22bis unscrambled binary 1 |
| `4f1c` | 2224.95 Hz | Bell 103 answer mark |
| `3aab` | 1650.04 Hz | V.21 channel 2 mark |
| `2d28` | 1270.02 Hz | Bell 103 originate mark |
| `22d8` | 979.98 Hz | V.21 channel 1 mark |

`a040`-`a0af` is the ladder itself. It is a chain of stages. Each stage is gated on a
capability bit. It loads a duration, arms a modulation, counts down, and
continues to the next stage. There is an escape branch (`b0a0`, `d819`, `da5c`) if a detect
bit in `@2f` says that the remote modem answered.

**A 43-second capture gets to only the first two rungs.** ANSam starts at 2.48 s for
3.30 s, and 2250 Hz starts at 5.82 s for 3.02 s. From 8.84 s, the DSP writes
*exact zeros* for the remaining 34 seconds. It does not go down to Bell 103.

### Why: the gates are clear

The stages after the answer tone need bits that are never set:

| stage | gate | runtime value |
|---|---|---|
| `a061` - 1650 Hz | `@27` bit 12 | clear |
| `a081` - `dac3` modulation | `@27` bit 10 | clear |
| `a09b` - 2025 Hz | `@26` bit 7 | clear |

In the middle of the run, the capability words are `@26 = 0x715d` and `@27 = 0x001b`.
Note that these are **not** the values that the `splk` pairs at `9e31`/`9e3b` write
(`4000`/`0008` and `4010`/`0000`). Those values are a start point that other code
changes later. Thus, if you read the gates of the ladder only from the static writes, you get
the correct answer for the wrong reason. All three gate bits are clear in the two
cases.

### It is not stalled

Keep this separate from the silence: after the tones, the DSP still operates.
The mixer callback goes through `b6e6` -> `b726` -> `b766` -> `b6e6` in a cycle (each installs
the next at `@1a`). The stage timer `@2b` continues to count, and the most frequent PCs are
the idle wait at `810a` and the shaping filter at `8a88`-`8ac6`. The
line is silent because the increment `0x3f2` and the amplitude `0x3f3` of the oscillator
are both **zero**. Thus, the generator runs and makes no signal. That is a
configured quiet state. The DSP has not stopped.

This does not show if a real Courier with this NVRAM would
also stop after two rungs. The gates are clear in the emulator. We did not test if
the fixture is correct on this point.

## Where Bell 103 lives, and why it never sounds

The FSK tones are not part of the answer ladder. They are part of the
**datapump modulation chooser**, which is a separate consumer of the same two
capability words.

`d79c`-`d7ee` is six configuration routines. In these routines, `@72` and `@73` are an
FSK **mark/space pair**. They are not the increment and the amplitude of the oscillator:

| routine | `@73` | `@72` | pair |
|---|---|---|---|
| `d7a7` | 1170 Hz | 980 Hz | V.21 channel 1 |
| `d7b1` | 1070 Hz | 1270 Hz | Bell 103 originate |
| `d7cb` | 1850 Hz | 1650 Hz | V.21 channel 2 |
| `d7d5` | 2025 Hz | 2225 Hz | Bell 103 answer |

That also identifies 2025 Hz: it is the Bell 103 answer **space**, paired with the
2225 Hz mark. It is not the standalone tone that an earlier pass guessed.

`d7ef`-`d829` dispatches to those pairs. The code gets to it like this:

```text
9b58: splk @7c, #9b6c      ; table base: originate
9b5c: splk @7c, #9b75      ; table base: answer
9b62: call 9b7e            ; the selector
9b68: add  @7c
9b69: tblr @7d
9b6b: bacc                 ; jump to table[base + index]
```

`9b7e` is a **priority selector**, not a ladder. It tests nine capability bits
and returns the index of the *first* bit that is set:

| idx | gate | originate (`9b6c`) | answer (`9b75`) |
|---|---|---|---|
| 0 | `@27` bit 1 | `9d00` | `9d00` |
| 7 | `@27` bit 12 | V.21 ch1 | V.21 ch2 |
| 8 | `@26` bit 6 | Bell 103 orig | Bell 103 answer |

**Bell 103 is not disabled. It has a lower priority.** At runtime, `@26 = 0x715d` and
`@27 = 0x001b`. Thus, the gate of index 8 (`@26` bit 6) is *set*. But the
gate of index 0 is also set, and the selector returns there first. The selector never gets to index 8.

This corrects an earlier interpretation in the history of this repository. That interpretation used "the
gates are clear" as the explanation for the missing Bell tones. Two different
mechanisms read `@26`/`@27`: the answer-tone ladder at `a040`-`a0af`, and this
modulation chooser. They are not the same gates, and they do not answer the same question.

It also puts the FSK block in the correct location. The tones of Bell 103 are part of the
modulation to which the modem *commits*. They are not part of the enticement. Thus, they occur only after
the negotiation has failed sufficiently to clear the bits with a higher priority. No
run until now gets to that point.

## It is the ATA handler, not the scenario

The sequence occurs again with two different line models, `--exchange-hotline`
and `--ring`, at the same onsets, durations and levels. The 2250 Hz burst is
**byte-identical** between the two runs. Thus, it comes from the answer path of the supervisor,
and not from either seizure.

## The harness cannot yet ring the exchange

Neither run is a true answer on the exchange side. This is a limitation of the harness.
We record it here, before somebody reads `daa.operation` and thinks that the firmware
originated the call.

`--ring` builds a `RingSource` that controls the ring detector bit at input port
`0x14` (`machine.py`, `RING_DETECT_PORT`). It does **not** put `LineExchange`
into `ringing`. The only caller of `exchange.ring()` is the SIP inbound path in
`ata.py`. `CourierDspBridge.set_line_hook` decides the seizure with

```python
answering = self.exchange is not None and self.exchange.state == "ringing"
```

Thus, each CLI seizure has the label `originate`, independent of the detector. The
supervisor obeyed `ATA` and armed these tones in all cases. For this reason, the
capture still has a meaning. But a real answer-side run needs `--line-link`
with a paired instance, or an exchange that the CLI can ring directly.

## What this does not show

* **Not hardware.** The codec, the ASIC transport and the line are models. We did not measure a
  board.
* **Not a located caller for every path.** We found the oscillators and their arming
  sites above. We followed the path to `0x9ffc` and `0x9f62` in this image
  only as far as the state timer. We *have* done the equivalent work
  on 3.1.2. Refer to [the path to `9f40`](answer-tone.md#the-path-to-9f40). That work
  finds the same one-shot scheduler (`@6d` the state vector, `@6e` the
  countdown) that 3.0.13 runs at `8767`.
* **Not a completed handshake.** Two tones went out. Nothing here shows that a
  far end answered them, or that a carrier trained.
