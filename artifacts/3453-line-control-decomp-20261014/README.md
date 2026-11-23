# B/C line-control disassembly and unchanged peer tests

Offline only. No physical modem, settings writes, guest patches, forced carrier,
or synthetic training. `result.json` contains whitelisted call diagnostics,
not settings or whole-memory dumps. **There is still no negotiated connection.**

Follow-up: [the originate-queue trace](../3453-originate-queue-trace-20261015/README.md)
resolves the missing transition described below: firmware already requests
command 0017, but its full outbound software ring drops it. This document's
unresolved-transition discussion describes the earlier investigation.

Regenerate the disassembly:

```
.venv/bin/python tools/audit_3453_line_control.py \
  dumps/3453bc-firmware-read-2.2.09/firmware.bin > line-control.asm
```

The tool checks the public capture's hash. Crucially, it does **not** concatenate
all overlapping DSP modules: the later 1DC9 overlay replaces resident line-control
instructions. For example, the active answer entry 1F64 is `SPLK @6D,#1F7C`, not
the unrelated instruction found there after applying the later overlay.

## Executed controls

Common command prefix:

```
./courier link "$PRIVATE_BC_FLASH" --with-dsp --line-audio-only --tick-source dsp
```

`bc-line-decomp`: 24 million instructions, 60 requested frames, commands
`AT&N1&U1` then `AT&L1` on each side, `--audio-dir /tmp/bc-line-decomp-audio`.
DSP trace range 1D60..20E8. Native waveform recordings were examined with a
4096-point Hann-windowed FFT, at the WAV's declared 8000 Hz sample rate:

| file / interval start | dominant frequency |
| --- | --- |
| a-tx.wav / 1 s | 2099.6 Hz |
| a-tx.wav / 2 s | 2099.6 Hz |
| a-tx.wav / 3 s | 2250.0 Hz |
| a-tx.wav / 4 s | 2250.0 Hz |
| b-rx.wav / same intervals | same peaks |

A transmit peak was 10332. B transmitted silence. RX WAVs record the peer's
transmit waveform **before** the existing modeled pair loss; do not confuse
these with the codec ADC amplitude. This establishes the waveform, not its
successful protocol interpretation. The names `input-callback` / `output-callback`
in this first report were probe labels: 039A is the transmit generator and 039B
is receive processing.

`bc-classifier`: 32 million instructions, 65 requested frames, same leased-line
commands, `--mem-watch 0x1d68:0x1d79`. This small region contains call-progress
state, not settings. Reports include some earlier guest RAM-test writes; the
late B writes at 6DC4B/6DC4E record 0009 in 1D6C/1D6D. The supervisor really
consumes the DSP's status. Therefore a wholly broken receive mailbox is **not**
the explanation. Both 02DA callback pointers are 627D at the endpoint.

`bc-manual-pair`: 60 million instructions, 160 requested frames, commands
`AT&N1&U1S7=20X0D5551212` on A and `AT&N1&U1S7=20A` on B. The combined manual
answer command intentionally does not enable the CLI's wait-for-ring gate.
Manual ATA is a guest command, not a fabricated ring. Both peers exchanged
nonzero audio (A's includes dialing); both returned `NO CARRIER`. They reached
134 frames, not the requested 160.

`bc-factory-pair`: 30 million instructions, 65 requested frames, commands
`AT&F0&M0&N1&U1X0` then `AT&L1` on both ends. These are volatile guest
configuration commands; no `&W` or other settings save was issued. Clearing
stored runtime configuration and disabling ARQ did not change the endpoint:
A RX=2208/state=2030, B RX=2127/state=0/TX idle. B still transmits zero.

## Narrowed failure

* Answer setup 1F64 installs state callback 006D=1F7C; 21D7 installs RX 039B=2208.
* Monitor setup 20E9 clears 006D/006E and installs RX 039B=2127, TX 039A=1173
  (idle). The silent leased-line originator remains in precisely this state.
* Monitor processing emits header 8008 and its qualified flag word at 21C8..21CF.
  The host sees tag 0008. Status 0809 really reaches the supervisor.
* Supervisor 6DB86 rejects AL bits 003C from its generic-energy qualification;
  it sets 1D6B bit 0001 only after 20 eligible reports via 6DB92..6DBCC. Thus
  receiving nonzero PCM or seeing status bit 0001 alone is not carrier.
* The answerer progresses to state callback 2030, but the originator never
  receives a handshake-mode command in these traces. The control transition
  from monitor reports to originate setup remains unresolved.

### Partial decompilation (not replacement firmware)

The monitor's decision at 6DB6C..6DBD1 is approximately:

```c
if (settle_reports != 0) {
    --settle_reports;
    previous_mask = 0xff;
    goto store_report;
}
if (flags & 0x003c) {
    previous_mask = 0xfe;
} else {
    flags &= previous_mask;
    if (flags & 1) {
        // Original code increments/saturates two byte counters and performs
        // additional X-mode handling before this threshold test.
        increment_energy_counters();
        if (eligible_report_count >= 20)
            qualified_progress |= 1;
    }
}
process_other_progress_flags();
store_report:
last_flags = flags & 0x3f;
```

This is **not** a carrier detector replacement and does not mean twenty
consecutive reports. Notably 0809 contains bit 0008: those reports take the
first branch, not the energy-qualification increment. Clearing that bit or
setting `qualified_progress` in the emulator would hide, not solve, the
control-path issue. The remaining receive filters and handshake transitions
are retained as addressable original instructions in `line-control.asm`.

These findings do not yet establish an emulator fault, a valid handshake,
calibration accuracy, or the correctness of the existing analog loss model.
