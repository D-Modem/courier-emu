# Usage

All commands run through the `./courier` launcher. You do not install anything,
and you do not activate an environment. At the first use, the launcher makes
`.venv` adjacent to the repository and installs the project into it. After
that, it only starts the CLI.

```sh
./courier info main211.xmf
./courier extract main211.xmf extracted/main211
```

You can select the CPU execution. The non-JIT interpreter uses a guarded native
execution loop with a Python fallback. It has an 80186EB profile for analog
Courier images and a 386EX profile for I-Modem images:

```sh
./courier run main211.xmf --cpu-engine interpreter --instructions 1000 --summary
./courier isdn-run Ie030002.nac --cpu-engine interpreter --instructions 10000 --report
```

The interpreter shares the current peripheral, interrupt, flash and I/O models.
It does not need executable-memory/JIT permission. Native execution falls back
at device accesses, watched addresses and instructions outside its supported
subset. The Python reference still sets the instruction coverage. An
unsupported instruction stops the run with its opcode, profile and physical
address. `--report` enables ISDN profiling for each address. Usual runs use
bounded instruction-clock callbacks. To compare, set `COURIER_X86_NATIVE=0`.
This selects the Python reference.

To measure firmware execution, use `python tools/benchmark_x86.py Ie030002.nac`
or `python tools/benchmark_x86.py IDSDL302.ROM --with-dsp`. To identify native
fallback addresses, add `--profile-exits`. This option adds profiling overhead.
To use the reference engine, add `--python`. For measured workloads, see
[paired emulation performance](paired-emulation-performance.md).

Native-worker runs that are applicable also do the batch-call setup and the
cleanup after the run in native code. Refer to
[native worker wrapper measurements](native-worker-wrapper-performance.md).
`COURIER_X86_NATIVE_WRAPPER=0` keeps the Python wrapper, and the CPU still runs
in native code. The worker arming-rejection gate and the native FIR and
polyphase block loops of the resampler are in
[native service and resampler performance](native-service-resample-performance.md).
Each of these variables disables one path:

- `COURIER_NATIVE_ARM_GATE=0`
- `COURIER_NATIVE_FIXED_RESAMPLE=0`
- `COURIER_NATIVE_POLYPHASE=0`

The resampler kernels use only a core library that is already loaded. Older
libraries use the Python paths. These changes make the runs faster. They do
not show that live calls are stable.

To open the browser console, run `./courier gui`. Refer to
[the browser GUI](gui.md).

The launcher uses `uv` when `uv` is on `PATH`. If not, it falls back to `venv`
and `pip`. These settings change its behavior:

- `PYTHON=<interpreter>` selects the interpreter (3.10 or later) for the
  environment.
- `COURIER_EMU_VENV=<path>` moves the environment.
- `make clean-venv` deletes the environment.

You can run `./courier` from any directory. If you prefer to manage the
environment yourself, install the project with
`pip install -e '.[execute,disasm]'`. Then use `python3 -m courier_emu` in
place of `./courier` in all the commands below.

Execution uses the 16-bit x86 core of Unicorn and runs in an isolated child
process:

```sh
./courier run main211.xmf --instructions 250000
./courier run main211.xmf --instructions 1000000 --summary
./courier run main211.xmf --instructions 7000000 --with-dsp --at AT --summary
```

For Courier, the default DSP is C51. For a C53 image, select `--model c53`. Raw
MICA harnesses can use `NativeC5x.from_program(..., model="c53")`. For on-chip
maps and the GREG board configuration, see
[DSP memory models](c5x-memory-models.md).

The C5x runner has no third-party runtime dependency. At the first use, it
builds with the C++17 compiler of the system:

```sh
./courier dsp-run main211.xmf
./courier dsp-run main211.xmf --trace 40
./courier dsp-run main211.xmf --port 0x50=0x1234
```

If you inject no supervisor events or line-side events, `main211.xmf` gets to a
deterministic 169-address service/polling cycle after 10,241 DSP instructions.
It then reports `status: stable-loop`. To make the run longer, use
`--instructions`. To examine a later instruction window, use `--trace-start`
with `--trace`. If this firmware path does not use an opcode form, that form
fails clearly with its PC. It does not silently make a guessed state.

By default, the harness accelerates these items: the known fatal-blinker
calibration loop, the initial 80186 timer-ready poll and the tick-delay helpers
of the firmware. It does this because a CPU-only core cannot supply their
hardware timing. If instruction-accurate delay counts are important, use
`--real-delays`.

To seed hardware input values, use repeatable `--port PORT=VALUE` arguments.
Port `0x40` is the first recovered board-control latch. The recovered DTE UART
model accepts `--at COMMAND` (this adds a carriage return) or literal
`--serial-input TEXT`. Its RX ISR is vector `0x0e`. Status/control is at port
`0x00`, data is at port `0x0a`, and the RX-ready bit is `0x08`. `serial_text`,
`serial_interrupts` and `serial_trace` report the terminal exchange that
results.

The modeled DTE attention detector accepts the `AT` prefix of the firmware in
all uppercase or all lowercase. It sends only the remaining command body to the
banked parser. The captured output has a limit of 64 KiB. If a diagnostic
command is larger than that limit, `serial_truncated` reports it.

The harness gives a command line to the firmware only from its
command-line-ready state. The state machine publishes that state as the
callback pointer at `0x02ac`:

1. `a8d9` collects a line, one character at a time.
2. The terminator advances the pointer to `a910`, which parses the line and
   prints the result.
3. The end-of-command path at `a8b1` clears the collector and returns to
   `a8d9`.

Bytes that arrive in the `a910` window go into a buffer that nothing parses.
The type-ahead flag of the firmware at `0x1cf2` would carry a line across. But
the DTE front-end sets this flag, and this harness replaces that front-end.
Thus, the harness waits for `a8d9`. For each line, it sets the collect flag at
`0x1cee` bit `0x40` again, exactly as it does one time at the main-loop
milestone. Because of this, a second and third command also get an answer.
