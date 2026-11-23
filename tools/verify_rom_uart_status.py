#!/usr/bin/env python3
"""Record resident RX-ISR disassembly and UART command regressions, offline."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from courier_emu.machine import CourierMachine, serial_callback_table
from courier_emu.nvram import CourierNvram
from courier_emu.rom import CourierRom
from courier_emu.rom_serial import locate_rom_serial
from tools.x86_disasm import disassemble


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instructions", type=int, default=60_000_000)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "artifacts/rom-uart-status-20261013")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    command = b"AT\rATI\rATQ1\rATQ0\rAT\r"
    cases = (
        ("302", "IDSDL302.ROM", CourierNvram.idsl302_fixture, "5607"),
        ("403", "dumps/courier-board-21210-capture-403/courier-board.rom",
         CourierNvram.idsl403_fixture, "5607A"),
    )
    report = {"command_hex": command.hex(), "instructions": args.instructions,
              "cpu_engine": "interpreter", "runs": []}
    for label, path, fixture, identity in cases:
        rom = CourierRom.load(ROOT / path)
        callbacks = serial_callback_table(rom.data)
        assert callbacks is not None
        layout = locate_rom_serial(rom.data, callbacks)
        assert layout is not None
        start = 0x80000 + layout.receive_isr
        listing = "\n".join(
            f"{i.address:05x}  {i.bytes.hex():18} {i.mnemonic} {i.op_str}"
            for i in disassemble(rom, start, 7)) + "\n"
        (args.output / f"{label}-rx-isr.asm").write_text(listing)
        machine = CourierMachine(rom, serial_input=command, nvram=fixture(),
                                 board_id=7, tick_ms=5, cpu_engine="interpreter")
        result = machine.run(args.instructions)
        raw = bytes(machine.serial)
        terminal = bytes(b & 0x7f for b in raw).decode("ascii")
        expected = f"\r\nOK\r\n\r\n{identity}\r\n" + "\r\nOK\r\n" * 3
        assert terminal == expected, (label, repr(terminal))
        assert not machine.serial_rx
        assert machine.uart.received == len(command)
        assert machine.uart.transmitted == len(raw)
        assert machine.uart.overruns == 0
        report["runs"].append({
            "build": label, "rom": path,
            "sha256": hashlib.sha256(rom.data).hexdigest(),
            "receive_isr": f"{start:05x}", "callbacks": f"{callbacks:04x}",
            "status": result.status, "raw_hex": raw.hex(), "text": terminal,
            "uart": machine.uart.status(), "input_remaining": len(machine.serial_rx),
        })
    (args.output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Verified both resident UARTs; evidence: {args.output}")


if __name__ == "__main__":
    main()
