#!/usr/bin/env python3
"""Execute Ie030002's original call-time and IRQ watchdog arithmetic in isolation.

No calls or firmware patches. Stops before unrelated timer housekeeping and
mailbox I/O; this verifies the counter/flag decisions, not the board scheduler.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from courier_emu.isdn import IsdnMachine
from courier_emu.nac import NacImage
from courier_emu.x86_interpreter import (
    UC_ARCH_X86, UC_HOOK_CODE, UC_MODE_16, UC_X86_REG_CS,
    UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_IP, Uc,
)


def probe(image: Path) -> dict:
    base, flat = IsdnMachine(NacImage.load(image))._flat_image()
    expected = {
        0xA46FE: bytes.fromhex('fe0ec7c8'),  # decrement fractional call timer
        0xA470E: bytes.fromhex('c606c7c8c8'),  # reload 200, not 100
        0xBC0E9: bytes.fromhex('fe06edc8'),  # mailbox IRQ entry counter
        0xBC0F6: bytes.fromhex('c60657ca80'),  # general abort flag
        0xA468B: bytes.fromhex('c606edc800'),  # system tick resets IRQ count
    }
    for address, code in expected.items():
        if flat[address-base:address-base+len(code)] != code:
            raise ValueError(f'unsupported firmware at {address:#x}')

    uc = Uc(UC_ARCH_X86, UC_MODE_16, profile='386ex')
    uc.native_enabled = False
    uc.mem_map(0, 0x200000)
    uc.mem_write(base, flat)
    uc.reg_write(UC_X86_REG_DS, 0x2600)
    uc.reg_write(UC_X86_REG_ES, 0x2600)

    def stop(cpu, _address, _size, _data):
        cpu.emu_stop()

    for address in (0xA4713, 0xA47AB, 0xBC0FB, 0xA4690):
        uc.hook_add(UC_HOOK_CODE, stop, begin=address, end=address)

    def execute(address, segment):
        uc.reg_write(UC_X86_REG_CS, segment)
        uc.reg_write(UC_X86_REG_IP, address - segment * 16)
        uc.emu_start(address, 0, count=1000)
        if uc.running:
            raise RuntimeError(f'probe did not reach a stop from {address:#x}')

    def byte(address):
        return uc.mem_read(address, 1)[0]

    # Enable call accounting. Start at a full fractional period so the first
    # observed second is at tick 100, then 300, 500, ... (not every 100 ticks).
    uc.mem_write(0x32A68, b'\x04')
    uc.mem_write(0x328C7, bytes((200, 0, 0, 0)))
    call_time = []
    for tick in range(1, 501):
        execute(0xA46FE, 0xA400)
        if tick % 100 == 0:
            call_time.append({'system_ticks': tick, 'displayed_seconds': byte(0x328C8)})

    uc.mem_write(0x328ED, b'\x00')
    uc.mem_write(0x32A57, b'\x00')
    irq = []
    for entry in range(1, 51):
        execute(0xBC0E9, 0xB3D9)
        if entry in (49, 50):
            irq.append({'entries': entry, 'abort_flag': byte(0x32A57)})
    execute(0xA468B, 0xA400)
    reset_count = byte(0x328ED)
    uc.mem_write(0x32A57, b'\x00')
    execute(0xBC0E9, 0xB3D9)
    return {
        'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
        'call_time': call_time,
        'irq_watchdog': irq,
        'irq_count_after_system_tick': reset_count,
        'abort_after_reset_and_one_irq': byte(0x32A57),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=Path('Ie030002.nac'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    text = json.dumps(probe(args.image), indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
