# Emulator architecture

The normal emulator is a model of a Courier. It is not a probe to discover the firmware.
Thus, the facts that we recover go into `courier_emu.machine_map`. Instruction tracing and
memory tracing stay as optional tools. We use these tools to find those facts.

## Layers

1. The CPU executes ordinary 80186 instructions.
2. `CourierMachineMap` assigns address ranges and service vectors to devices.
3. The device models contain the behavior of the UART, timers, ASIC, EEPROM, flash and DSP.
4. A `FirmwareProfile` with an exact digest supplies only the facts that change between ROM
   releases.
5. The scheduler advances the devices after limited amounts of guest execution.

An optimization can skip or replace firmware code only if two conditions are true:

- An exact digest selects its profile.
- The emulator also validated the related entry bytes.

Unknown ROMs continue through the general interpreter.

## Migration rule

Before normal execution can depend on a newly recovered address, give the address a name
in the machine map or in a firmware profile. Do not add one more anonymous
literal to the CPU dispatch loop. Discovery scripts can use raw addresses. But when you
promote their result, the result must include the image identity and the evidence.

The first mapped ranges are the 80186 peripheral block, the DSP host queue and the
serial callback cell. The two Australian flash captures are the first explicit
firmware profiles. Move the existing literals here in small steps. For each move, add a
behavioral regression test.

## Performance direction

The Python interpreter keeps the next device-service deadline in its
dispatch loop. It calls the machine one time for each limited interval. It does not
install a Python code hook for each instruction. The next change to execution
is a block API. This API executes until a mapped device deadline, a mapped watchpoint, an
interrupt boundary or a block exit. Then it advances the scheduler one time. After this,
known idle loops and polling loops can yield to the next device event. Profile rules that
code anchors guard will control this.
