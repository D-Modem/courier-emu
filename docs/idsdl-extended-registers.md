# ID_SDL's `AT+S` registers, and the post-flash step this board never had

Source: `firmware/legacy-usrobotics/ID20C403/IDSDL403.TXT`, the ID_SDL v4.03
manual. It is 62 KB of CP866 Russian, dated 24/01/00. This is the same date as the banner that
`ATI7` prints. It documents a command set that is in **no help screen on
the modem**: `AT$`, `AT&$`, `AT%$` and `ATD$` all print the standard USRobotics
Courier reference and say nothing about this command set.

## The line that matters

> `!! Внимание, после заливки этой пpошивки набеpите команды AT&F1,AT+SF,AT&W. !!`
> `иначе ловля Dialtone,Busy будет не возможна.`

"After flashing this firmware, enter the commands `AT&F1`, `AT+SF`, `AT&W` -
otherwise catching Dialtone and Busy will not be possible."

**Nobody did that step on this unit**. It explains a
fault that stayed after a power cycle, and that no other theory explained.

## The register set

`AT+S?` lists the registers. `AT+S$` prints their help. `AT+Sn?` reads one register. `AT+Sn=m`
writes one register. **`AT+SF` loads the documented defaults**.

| register | meaning | documented default |
|---|---|---|
| `+S1` | delay in ms between adjacent digits when dialling | 70 |
| `+S2` | break/make duration per dialled digit | 0 |
| `+S3` | Busy/Dialtone recognition **before** dialling starts | - |
| `+S4` | Busy/Dialtone recognition **after** dialling starts | - |
| `+S22` | DTMF **detection** sensitivity | 525 |
| **`+S24`** | **DTMF transmit level, first frequency** | **13000** |
| **`+S26`** | **DTMF transmit level, second frequency** | **3080** |

## What was actually wrong

We read these values from the live board before we changed anything:

```
AT+S1?  -> 00      (documented 70)
AT+S24? -> 00      (documented 13000)
AT+S26? -> 00      (documented 3080)
```

**The two DTMF transmit levels were zero.** The modem made its dial
tones at zero amplitude. Thus, it went off hook, held the line, and sent
nothing. Pulse dialling continued to work, because it uses the hook relay and
never touches the tone generator. This explains each symptom:

* The dial tone was audible, but no DTMF was audible, to the operator who listened on the line.
* `ATDT` returned no result code until the `S7` timeout, because the modem never sent digits.
* `ATDP` made audible relay clicks.
* The fault stayed after a power cycle, because the registers are also zero in NVRAM,
  and nothing loaded defaults into them.

`AT+SF` restores all four registers to the documented values. We read
them again after this, and this confirmed the values.

## What this rules back in

During the investigation, we suspected some items and then cleared them. They stay cleared:

* **The flash is correct**. All 2048 pages are byte-identical to the earlier capture,
  `artifacts/flash-verify-01/`.
* **The NVRAM is correct**, and it holds a profile that an operator configured.
* The `ATI2` RAM test of the board passes, and all the S-registers are at their
  documented defaults.

## Two separate things, established by flipping the switch back

This section was wrong two times. Thus, this is the measurement that gives the answer.

With **DIP 10 set back to the factory-defaults position** and an `ATZ!` reset:

```
running config : &A1 &B0 &G0 &H0 ... , DIAL=PULSE     <- defaults, as the switch selects
+S24           : 13000
+S26           : 3080
```

The switch clearly has an effect: the standard USR profile starts with the `&F0`
defaults and not with the stored profile. But **the switch does not change the extended
registers**. Thus, `+S` is not part of what DIP 10 selects.

That separates the two faults clearly. It also recovers evidence that
we thought was lost:

1. **The DTMF fault was an uninitialized `+S` block in NVRAM.** Before the
   `AT&W`, `+S24`/`+S26` read `00` at power-on. After it, they read
   `13000`/`3080` at power-on. The DIP switch was in the *same* position for the two
   readings. The only change was the NVRAM contents. Thus, the block held
   zeros, because nobody ran the post-flash `AT+SF`/`AT&W` on this unit.
   `AT+SF` followed by `AT&W` was the necessary fix. It was not unnecessary.
2. **DIP switch 10 was the cause that the profile was not applied at power-on**. This is
   not related to the first fault.

There were two faults, not one. Neither fault is the NVRAM-checksum story that an earlier draft
of this document told.

For the record, these are the claims that we made and then withdrew. First, we said that `AT&W`
repaired an incorrect NVRAM checksum, and that one cause explained the two symptoms.
That was wrong: DIP 10 explained the profile symptom. Then we said that the DIP switch explained
*the two* symptoms, and that `AT+SF` was not necessary. That was also wrong, because the measurement shows that the switch
does not touch `+S`. We also measured that the `AT&F0` command does not set the registers to zero.

After `AT&W`, the registers stay after a hardware reset in the two switch positions:

```
AT+S24? -> 13000    AT+S1?  -> 70
AT+S26? -> 3080     AT+S22? -> 525
```

## Doing this on another unit

Enter `AT&F1`, `AT+SF`, `AT&W`, in that sequence, as the manual says.

> **CAUTION: DO NOT DO THIS ON A UNIT WITH AN NVRAM PROFILE THAT YOU WANT TO KEEP, UNLESS YOU SAVE THE PROFILE FIRST.**
> `AT&W` stores the *current* running configuration. Thus, if you enter `AT&F1` first, the
> factory defaults overwrite the stored profile.

On this board, we built the profile again in RAM from an `ATI5` capture
before the write. We also set the DTE rate to agree with `&B1`, because `&W` also stores the DTE rate.

## Where the block lives in NVRAM, and the emulator fixture

We measured this in the emulator on the 302 image with a persistent `--nvram` file.
`AT&W` alone programs the standard USR profile at EEPROM words `0x00`-`0x22`.
`AT+SF` followed by `AT&W` also programs words `0xc1`-`0xf4`. That
block is a byte stream that starts on the high byte of word `0xc1`. It is
byte-identical to the defaults table at CPU `0xc8891`: first `+S1` = 70, then
`+S22` = 525, `+S24` = 13000 and `+S26` = 3080 at words `0xcc`-`0xce`. It ends
with the `3.02` version tag.

The dial path sends those three values with each digit on the mailbox tags
`0x19`, `0x1a` and `0x1b`. When the block is erased, the lanes carry `0xffff`, and
the tone generator of the DSP makes nothing that the modeled exchange can decode.
After `AT+SF`, they carry `020d`/`32c8`/`0c08`, and the exchange decodes each
digit. The `--nvram-fixture idsdl302` image now seeds this block together with the
settings cache. Thus, a cold boot in the emulator dials audibly.
