# Recovered I-modem VRTX startup

The Ie030002 payload contains a working VRTX startup path, from the
initialization to the tasks. A run of the existing `IsdnMachine` for
3,000,000 instructions, with no guest code patches, creates nine tasks
successfully and executes all nine entries. The firmware itself calls the
task at `a400:0008` **TID_MODEM**.

This replaces the earlier interpretation, which said that the lower payload is
only an updater and that `a400:0008` is only a DSP helper. Flash command
activity alone does not distinguish an updater from a usual firmware startup.

## Startup chain

| Address | Action |
|---|---|
| `4030:0000` (`40300`) | Existing harness entry: initializes the stack/hardware, clears RAM, relocates data, installs vectors. |
| `4030:006e` (`4036e`) | Far jump to `7360:1ec0`. |
| `7360:1ec0` (`754c0`) | Installs INT 30 at `7360:0000`, and INT 31 as descriptor pointer `98d1:0000`. |
| `7360:1ee0` (`754e0`) | `mov ax,30h; int 30h`: kernel initialization. |
| `7360:1b3d` (`7513d`) | Implementation of service 30: clears the kernel workspace, builds the task-control-block/free lists and the idle context. |
| `7360:1f30` (`75530`) | Far call to `6ac3:000c`, the firmware subsystem initialization. |
| `6ac3:003d` (`6ac6d`) | Calls `6ad6:000f`, which calls nine subsystem initializers, including `4607:000a`. |
| `4607:000a` (`4607a`) | Creates synchronization objects and explicitly creates nine tasks. These are immediate call arguments. They are not a standalone table of task pointers. |
| `4063:02ae` (`408de`) | C task-creation wrapper: task entry in ES:BX, ID in CL, priority in CH. Calls service 00 at `408f1`. |
| `7360:03e2` (`739e2`) | Implementation of service 00: allocates the task state, installs the saved entry/context, puts the task in the queue. |
| `7360:1f35` (`75535`) | Service 15 with CX=3, after the subsystem setup returns. We do not assign its exact API name here. |
| `7360:1f4e` (`7554e`) | `mov ax,31h; int 30h`: scheduler start. |
| `7360:1e21` (`75421`) | Service 31 changes to the prepared stack, enables the scheduling state and branches to the scheduler. |

The service dispatch table is at `7360:1e59` (`75459`). It has 50
little-endian near offsets, indexed by AX. For services 16h/11h, the kernel
has special interrupt entry/exit paths outside the usual dispatch path.

## Tasks, in creation order

Refer to [task roles and queue routing](imodem-task-roles.md) for the
analysis that follows this one. TOUT is the timeout processing. The other
short C tasks mostly dispatch messages between the ISDN protocol layers and
the modem call control.

The names come from the `TCreate TID_*` strings. The success/error branches
immediately after the creation calls in `4607:000a` refer to these strings.
All nine requests use priority `0x20` and return status zero.

| ID | Firmware name | Entry | First execution, instruction count |
|---|---|---|---|
| 1 | TID_TOUT | `459b:0008` | 657132 |
| 4 | TID_T3L2 | `4678:0009` | 657417 |
| 2 | TID_CES3 | `46e9:0008` | 657702 |
| 3 | TID_S3CE | `45f2:0002` | 657987 |
| 6 | TID_L2S3 | `4692:0005` | 658272 |
| 9 | TID_P3CE | `45fc:000e` | 658557 |
| 5 | TID_LLL2 | `46ae:0000` | 658842 |
| 12 | TID_MODEM | `a400:0008` | 659130 |
| 10 | TID_CEML4 | `46dd:000a` | 2742349 |

For example, `4607:0421` pushes priority 20h, ID 0ch, segment a400h and offset
0008h. Then it calls the task-creation wrapper at `4607:042b`. The related
strings are `TCreate TID_MODEM Failure = ` and `TCreate TID_MODEM`.
The task starts with the initialization of DSP-related state, and it calls
back into other payload code. These callbacks do not disqualify it as a task
entry.

## Evidence and limits

Run this command from the repository root:

```sh
.venv/bin/python tools/imodem_vrtx_trace.py \
  --output artifacts/imodem-vrtx-startup/trace.json
```

The probe records image hashes, service counts, register arguments, the
return codes of the creation calls and the first execution of each task. It
uses the existing peripheral model and stops at the instruction limit. This
shows the startup and the task execution. It does not show complete modem
functionality or hardware-accurate timing. The observed run does four modeled
flash erases and zero program operations.

The real reset vector and the boot block are still not available. Thus we have
not proved the exact hardware reset handoff. We also have not proved a
relocation mapping that lets an assembled flash boot independently. But the
stronger previous claim, that the VRTX/application startup code must be
missing, has no support: the payload already contains the chain above.
Specifically, the lower payload contains VRTX and eight of the nine task
entries. If you treat all code below `80000` as disposable updater code, you
lose code that this demonstrated startup path must have.
