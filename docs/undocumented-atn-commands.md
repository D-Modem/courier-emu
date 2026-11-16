# Undocumented modem commands in the Sportster upgrade FAQ

The supplied Robert Aghababyan FAQ revision 1.15 lists `ATNn`, `ATNL` and
`ATNX`. Its descriptions are historical leads. They are not instructions to execute.
The saved HTML is already an English translation, although it has a KOI8-R header.
This analysis follows the actual captured ID_SDL 4.03d supervisor 7.4.16 /
DSP 3.1.2 image. We did not send commands to the physical board.

## The useful correction: ATN is a manual rate-change request

The FAQ calls `ATNn` a DSP procedure call. On our image, it injects a supervisor
event, and the consumers of that event request a change of the current rate
index. It is not an interface for arbitrary DSP subroutine numbers.

The normal command table at file `0x250cc` sends `N` to `0x250e8`, which
far-calls `8000:83a2`. The numeric handler at `0x8458` parses a decimal byte:

| Input | AX handed to the supervisor event dispatcher |
|---|---|
| `ATN0` | `007c` |
| `ATN1` | `017b` |
| `ATN7` | `077b` |
| `ATN255` | `ff7b` |
| `ATN256` | No dispatch: numeric overflow |

AL is the event code, and AH keeps the argument. The handler sets byte
`[0x0a16]=1`, then calls `8f46:32fb` (file `0x1275b`). That wrapper calls
`8f46:00f4` (file `0xf554`), which calls the current supervisor state through
`call word [0x0192]`. It does not send `n` as a DSP mailbox tag.

The state tables at `0x123b1`, `0x132cb` and `0x13f48` have consumers for the events
`7b` and `7c`. In the last family:

- `7c` goes to `0x1401b`, then `0x14414`. When the manual flag is set, it uses
  `[0x02b4] - 1` as the requested index.
- `7b` goes to `0x14078`, then `0x1442d`. When the manual flag is set, it uses
  `[0x02b4] + 1` as the requested index.
- Common code clears the manual flag, checks the masks of permitted indices and saves
  the accepted request in `[0x0a25]`. The caller sends operation `0054`
  through the regular queue helper, with this value in BX.

This supports **manual fallback / fall-forward** as the practical meaning
in those connection states. Zero selects down. A nonzero argument selects up.
The examined consumers do not use `7` as procedure 7 or as an absolute target
rate. These conditions control its effect: which states accept the event, which modulation is active and if
the requested index is permitted. An idle `OK` would not
prove a DSP action. We did not yet measure a capture of a rate change during a live call.

The `7b/7c` numbers here are supervisor event codes. Do not confuse them
with DSP outbound messages that have the same numbers, or with inbound
dispatch-table entries that do not exist. Refer to [the earlier table-boundary correction](who-produces-the-events.md).

## ATNL: a fixed programmed-I/O transfer, not a dump command

The branch at `0x83b7` recognizes `L`. The code at `0x83bf..0x8457` does these steps:

1. It disables interrupts, programs `[ffa4]=e000`, saves `[ff18]`, and sets
   `[ff18]=0010`.
2. It reads ports `c2/c0`, polls bit `0010` of the integrated peripheral register
   at `ff0e`, and sends header `0f3f` through `c4/c6`.
3. It selects CPU segment `e000`, offset zero, and loops `1554` hex times.
4. It uses three source bytes for each iteration and repacks them into two pairs
   of six-bit values (`and ...,3f3f`). It writes each pair to `c4/c6`, with
   readiness polling and reads from `c2/c0` between transfers.
5. It restores DS and `[ff18]`, calls `0x06fd`, restores the flags and returns.

That is **5,460 iterations, 16,380 source bytes and 10,920 packed transfers**
after the header. The “10K” of the FAQ is an approximate description. Its “DMA?” is not
how this implementation moves the bytes. The CPU explicitly loads, shifts,
polls and outputs each value. The output is through `c4/c6`, and `c0/c2` are read.

On each complete ROM that we examined here, the ordinary physical `0xe0000` source
window (`ROM[0x60000:0x63ffc]`) is all `ff`. All 16,380 bytes have SHA-256
`662a4843f357419e1a81d7587149277eed0018ef93f44c6bc3dd2ba5414d1a26`.
If that window is still selected after the `UCSST=e000` write, the encoder
would send four `3f` values for each three input bytes. There is no firmware
or DSP payload there. The reboot that we saw on the physical board agrees with
a more immediate problem: a change of the upper chip-select start can remove
the `0x88xxx` ROM code that executes before the transfer loop completes.

We did not establish the physical recipient and the exact bus decoding after the remap.
A legacy download/test interface is a possible interpretation.
It is not a measured identification. On the captured hardware, think of it
as an old, incompatible path and not as a useful transfer command. It is not the
verified `40..4e`/`50..5e` parallel DSP download path. It accepts no arbitrary
source address, and it does not return DSP memory on the serial terminal.
It also has readiness loops without a software timeout.

## ATNX: restart

At `0x83a6`, the suffix `X` sets bit 0 of `[0791]`, clears BP, disables interrupts
and jumps to the supervisor restart entry `8000:0480`. That entry initializes again the
segments and the stack, and clears RAM. This verifies the general “boot start”
description of the FAQ. It does not establish an NVRAM-save operation or a DSP entry-point
argument. The older configuration recipe that calls it “save changes” is
not proof that this handler writes NVRAM.

## The rest of the FAQ, and relevance to our DSP work

| Commands | Meaning / current evidence |
|---|---|
| `ATG=` / `ATGR` | Supervisor CPU memory dumps in bytes / words. Verified in this project. CPU addresses are not DSP data/program addresses. |
| `ATGI` / `ATGO` / `ATGB` | CPU I/O read, write and sweep. These are the useful primitives for the verified DSP mailbox. |
| `ATGW` | RAM write. Our ID_SDL extension supports byte or word writes, as the count of hex digits sets. The FAQ describes only byte writes. The successful RAM probes used it. |
| `ATGU`, `ATGBOOT5` | Historical claims / semantics not known in this analysis. Do not infer that BOOT5 is a command that executes RAM code. |
| `ATY4` (historically `Y24`) | Call-progress diagnostic mode. Already traced in our firmware. |
| `ATY7`, `ATY9` | The FAQ describes analog statistics of a connected call / 255 values not identified. That list does not establish the exact fields and if they apply to 4.03d. |
| `ATY5`, `ATY6` | The FAQ describes an LED self-test and a report similar to ATI6. These historical descriptions depend on the version. |
| `ATY14`, `ATY15` | Configuration and current DIP-switch report. Already identified in the repository. |
| `ATUSR`, `ATRS99?`, `ATI92`, `ATI99` | Credits/copyright/date, as the FAQ says. They do not mean direct DSP access. |
| `AT!E`, `AT&J`, `ATZ` variants | Calling-tone control, jack selection that is not certain, and reset variants, as the FAQ says. They are not DSP memory primitives. |

## `ATRS99?`: a single exact-match escape, not an `RS` family

The `R` handler contains one special case before its ordinary receive-mode
behavior. It must have a minimum of four remaining characters, and it compares them
directly with `S99?`:

```text
cmp cx,4
jb  ordinary_R
cmp word [si],3953h       ; "S9"
jne ordinary_R
cmp word [si+2],3f39h     ; "9?"
jne ordinary_R
lcall 8000:02adh
```

The supervisor stub at `8000:02ad` consumes exactly those four characters,
sets `SI=0006` and calls the normal zero-terminated string printer. Offset
`0006` is the CR/LF immediately before the ROM copyright banner. The banner ends
at the zero byte at `0063`. Thus, `ATRS99?` prints only that copyright block.

This path has no number parser, no selector table, no range check and no sibling `RS`
dispatch. The exact code occurs in the two Australian captures,
the two captured US revisions, the 25 MHz capture and `IDSDL302.ROM`. Other
strings that start with `ATR...` go back to the ordinary `ATR`. The main parser can
then interpret the remaining characters as a different chained AT command. For
example, an apparent `ATRS0?` is `ATR` followed by the standard `S0?` query.
It is not a hidden `RS0` function.

The adjacent stub that prints the credits is separate. The supervisor entry `8000:0296`
prints the copyright string at `0006` and then the credits string at `0064`.
The historical FAQ connects that output with `ATUSR`. The US board that we tested before
returned `ERROR` for that spelling. Thus, we do not claim its complete parser route
here. But it is not a different entry in an `RS` family.

For actual DSP observations, the `ATY12` buffered receive /
transmit report and the mailbox streamers, which we already traced, are more direct than the new `ATN`
lead. Refer to [ATY diagnostics](at-y-diagnostics.md),
[RAM delivery](ram-probe-delivery.md), and the
[recent measured NDX probe](dsp-mailbox-board-fix.md).

## Evidence and limits

### Remaining command mapping, and a newly verified G queue form

**Update:** we have now measured this form on the board, with alternating
query replies and a queue readback. Refer to [ATG DSP command format](atg-dsp-command.md)
for the verified syntax, the capture and the reply retrieval. The paragraph below
records the initial offline finding.

There is not yet a complete semantic inventory of the command parser. The
most important newly traced form is **`ATGhhhhdddd`**, with exactly eight hex
digits after G: first a command word, then a data word. At `0x25c5b`, the
handler selects this form by the remaining length. It parses two four-digit words,
puts the first in AX and the second in BX, and calls `8f46:01e4`.
File `0xf644` sends this on to `0xf678`, which queues three words:
`ff00`, AX, BX. This is the same queue helper that the normal supervisor
command/data requests use. It gives a possible direct AT route into the
DSP transmit path, without individual ATGO staging writes.

`g-queue-check.py` executes that path from the captured ROM with an empty
synthetic queue. The intentionally artificial input `ATG00541234` gives
`ff00 0054 1234` in sequence and moves the queue head by six bytes. The test
stops before the transmission. We did not verify the delivery on a real board, the response handling or the
behavior with a full queue. The data of the example is a parser test.
It is not a recommended hardware request. Also, the helper does not wait for space
when the queue is too full. Thus, a successful parse alone cannot prove the delivery.

These items must still be mapped:

| Form / area | What is known | What remains |
|---|---|---|
| Four-digit and shorter numeric `ATG` | Different code paths through `1ef1` or `1eed`. When it is enabled, the second path stages an AL byte. | Exact user-facing semantics, necessary state and delivery behavior. |
| `ATGN` | Sets bit 0 at `[0158]`. | All consumers of this enable flag and its relation to configuration writes. |
| `ATZ!` | Stores `80` at `[049b]`, then returns. | Its later meaning, and how it agrees with older notes that call it a reset. |
| `ATNL` | Fixed packed transfer traced above. | Physical recipient and mapped source contents. |
| `ATY7` / `ATY9` | Historical analog/statistics descriptions. | Exact applicability to 4.03d, fields and DSP producers. |
| ID_SDL extension selectors | The Russian ID_SDL manual documents some of them. Others have only partial code traces. | Complete inventory of command, handler and state effects. |

The resident `ATGU` branch itself is only `clc; ret` at `0x25ce6`. It does
nothing there, and it does not consume U. That does not establish the final
response of the full command. There is no reason to call it a DSP operation.

The ID_SDL `AT+S` family is already partly mapped, with the DTMF levels.
Refer to [extended registers](idsdl-extended-registers.md). If a command is not in the ordinary
AT help, this does not mean that it is unknown to this project.

### Follow-up: ATG? and ATZ variants

The `? - some more secret commands :)` of the FAQ is not evidence of a literal
help command. In the captured 403, `ATG?` finds no matching selector in the
extension or in the resident G handler. The generic path at `0x25c7a` parses zero
hex digits from `?` and gets AX=0. It does not consume the question mark, and it
calls `8000:1eed`. It does not show a command list. The isolated check
stops at that call. Thus, we do not claim a final serial response.

For comparison, the [USR Sportster Windows X2 manual](https://ads.usr.com/support/s-win/s-win-docs/winx2.pdf)
documents Z0 as the selected reset profile, Z1/Z2 as stored profiles 0/1,
and Z3/Z4/Z5 as factory profiles &F0/&F1/&F2 respectively. The Z handler in our captured 403 image
does **not implement that mapping**.

Our command table selects file `0x2631c` (`a4e2:14fc`). Except for the suffix
`!`, it goes directly to restart `8000:0480` with BP=2 or 3. Bit 7 of the existing byte `[049d]`
selects the value. It never parses a numeric suffix. An isolated
execution of bare Z and of Z0 through Z5 confirms the same restart entry and
BP=2 with that bit clear. Each numeric suffix stays unconsumed.
On this image, these are equivalent reset requests, not six profile choices.

There is a separate `ATZ!` branch. It writes `[049b]=80` and returns without
a reset. We do not establish its later effect here.

The reproducible `g-z-check.py` and `g-z-results.json` in the artifact
directory record these checks. They stop before the restart or the G fallback
call. Nothing was sent to the board.

The [artifacts](../artifacts/undocumented-atn-analysis/provenance.json) include the
ROM SHA-256, the selected disassembly and a reproducible isolated-handler check.
The check runs real captured instructions and stops at the state dispatch,
the restart or the transfer entry. It verifies the decoding, not the later hardware
behavior. The attempt with the full serial harness used all of its instruction budget
before it completed `AT`. Thus, it gives no acceptance/rejection result.
No emulator core or board settings were changed.

Source: the supplied
[Sportster FAQ](<x2/US-Sportster Upgrade FAQ. Frequently asked questions.html>),
section “Undocumented Teams” (translated heading for undocumented commands).
