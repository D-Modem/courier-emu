# Where the ROM's AT command is lost

`IDSDL302.ROM` takes each byte of `AT\r` and answers nothing. This document traces the
path from the serial interrupt to the point where the line stops. It gives the execution
count that each site gets to in a 60M-instruction run with `--at AT`.

The ROM is not idle, and its serial front end is not missing. These were two earlier
incorrect interpretations. The firmware fully installs the front end, and the
callback table is at `026a`, not at `02a8` as the traces printed before. Refer to
[serial callback location](../courier_emu/machine.py) and `test_serial_callbacks`.

## The chain, and how far it gets

| site | what it is | executed |
|---|---|---:|
| `80f23` | serial type 0x14 ISR: `mov ax,[ff68] ; call [026a]` | **3** |
| `89a06` | RX callback: `and ax,7f ; call [b7c]` | 3 |
| `89a1e` | `test [b88],40` - is a command line open | 3 |
| `89a68` | the line collector | 3 |
| `89acc` | `inc [b8e]` / `mov [bx+b8f],al` - store a character | **2** |
| `89a6e` | `cmp al,[598]` - the terminator, S3 | 3 |
| `89a74` | terminator path: clear `[b88].6`, set the buffer to zero, `al=8` | **1** |
| `89a80` | `jmp word ptr [026e]` - give the line to the command state | **1** |
| `8934b` | the command state, idle | 556,934 |

Thus, the code collects `A` and `T`, recognizes the `\r` as the terminator, and
gives the line on exactly once. All the steps to this point work.

## Where it stops

`8934b` is a jump table, not a routine:

```text
8934b  xor ah, ah
8934d  xchg bx, ax
8934e  shl bx, 1
89350  jmp word ptr cs:[bx - 0x6cab]      ; entries at 89355 + 2*al
```

| `al` | target | |
|---:|---|---|
| 0,1,2,7,**8**,10,11 | `89386` | `xchg bx,ax ; clc ; ret` - **nothing** |
| 3 | `89392` | `mov [026e], 941c` |
| 9 | `89389` | `mov [026e], 93fc` |

The terminator comes as `al = 8`, and in the idle state, `al = 8` does nothing.
The code collects the line, gives it on, and then discards it. Nothing is ever
parsed, thus nothing is ever transmitted. None of these sites executes, not one time:
the 50 `mov [ff6a]` sites, the
transmit routine at `81613`, its TXE spin at `81603` and the type 0x15 ISR at
`80f1c`.

## What is missing

`[026e]` is still `934b` when the terminator comes. Its table shows the two
ways out of idle: `al = 3` to `941c` and `al = 9` to `93fc`. Thus, the command
state machine must be armed *before* the terminator, but nothing armed it.
The call of the collector at `89a9c` (`call word ptr [b7f]`) is **not an AT
attention detector**. The harness installs `9b0a` there, but that routine
compares the character with `+`. Its next state compares with `F`/`f`, and
the state after that compares with `P`/`p` or `L`/`l`. It is a `+F` command
recognizer. When `A` and `T` go through it, it cannot arm the command state.
The earlier suggestion that this callback was the missing AT detector was
not correct.

The `_rom_dte_opened` block of the emulator sets collector flags and forces the
integrated UART vector. But it does not do the command-state transition of the firmware.
Thus, its claim that it completes the startup/open event is too
strong. If only the collector opens, the state machine stays in idle.
The next implementation step is to recover and deliver the real command-mode /
autobaud event, with its state transition. Do not add a different buffer
flag, and do not bypass the parser of the firmware.

Two of the other pokes of that commit are already known to be important here. We do not understand
either of them:

* `[033e] = 2` sends `89a49` into `89a50`. The other arm of that routine puts the RX
  callback on the bare `ret` at `89a67`, which ignores all input after one character.
* `[b88] |= 0x40` is the flag that sends the byte to the collector. If you remove it,
  the run goes from three collected characters to one, and then to silence. Thus, it
  is necessary. It is also the flag that the terminator path of the firmware
  clears at `89a74`.

## 403 has an additional image-layout failure

The disassembly of `artifacts/courier-board-21210-capture-403/courier-board.rom`
shows that the 302 addresses are not portable:

| item | IDSDL302 | captured 403 |
|---|---:|---:|
| RX/TX/command callback table | `026a` | `0164` |
| integrated UART RX ISR | `80f23` | `80f54` |
| command-state pointer | `026e` | `0168` |
| command collector | `89a68` | `89a93` |
| collector flags | `0b88` | `0a7c` |
| command length / buffer | `0b8e` / `0b8f` | `0a82` / `0a83` |
| collector feature gate | `0695` | `058d` |
| `+F` recognizer pointer | `0b7f` | `0a73` |

`serial_callback_table()` already recovers `0164` from 403, but the ROM RX
delivery gate in `machine.py` still reads `026a`. The startup workaround also
tests and writes 302 RAM addresses, and it forces vector 14h to `8000:0f23`
and not to the `8000:0f54` of 403. If the workaround operates on 403, it writes
unrelated state and can send interrupts into the incorrect code. If it does not operate,
the delivery gate still checks the incorrect callback cell. A fix of TX-ready or
a larger instruction budget does not solve either problem.

## Reproduction, 2026-09-06

We ran the existing `tests/test_rom_serial.py` regression for its full 60M
instruction budget, with the EEPROM fixture, board ID 7, a 5 ms tick and
`AT\r`. It fails because the serial output is empty. It does not contain
`\r\nOK\r\n`. This is a known failing regression. It is not evidence that the
current startup workaround works. On this host, Unicorn had to execute outside the
filesystem sandbox. The sandboxed run stopped with an illegal
instruction during `mem_map`, before any firmware executed.

A later 40M-instruction diagnostic run used the same settings on each
image and counted the actual instruction sites:

| observation | 302 | captured 403 |
|---|---:|---:|
| UART bytes delivered / transmitted | 3 / 0 | 1 / 0 |
| startup workaround fired | yes | yes |
| executions at `80f23` | 3 (correct ISR) | 1 (wrong entry) |
| executions at `80f54` | 0 | 0 (correct ISR never entered) |
| final RX/TX/command callbacks | `9a06,1d03,934b` | `9a31,1d35,93b0` |

For 302, the collector ran three times, its terminator branch ran once, and the
`+F` recognizer ran two times. The idle command dispatcher ran 108,436 times.
`815f0` and `81613` did not run. For 403, the forced 302 ISR entry actually
executed. This confirms that the address mismatch is active in this reproduction.
It is not only a possible incompatibility. These are CPU-only harness results.
We used the 302 EEPROM fixture for the two images, not a captured 403 EEPROM image.
