#!/usr/bin/env python3
"""Disassemble B/C 2.2.09 line control without merging mutually exclusive DSP stages.

Input is the public 753664-byte normal-firmware capture, never board settings.
This is an offline analysis tool: it neither runs nor modifies firmware.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from courier_emu.images import load_image
from tools.c5x_disasm import decode

BC_SHA256 = '6c3271782955f837fe23db7712f090cc84854e49cc43c2f4396cd1cc211371fc'
DSP_RANGES = (
    (0x00b0, 0x0156, 'transmit-bit packing and six PA6/8058..805D input channels'),
    (0x016d, 0x01d2, 'receive-bit packing and six PA6/8058..805D output channels'),
    (0x1d6d, 0x1d93, 'line-mode configuration; following words are a jump table'),
    (0x1da5, 0x1dc9, 'capability selection'),
    (0x1de4, 0x1f64, 'originate setup, detection qualification and protocol branches'),
    (0x1f64, 0x20e9, 'answer setup and handshake state machine'),
    (0x20e9, 0x229d, 'monitor/answer receive processing and status messages'),
    (0x229d, 0x22bc, 'energy qualification'),
    (0x23a3, 0x2479, 'receive filters'),
    (0x4430, 0x44e1, 'low-rate setup and report-3D/28 carrier transition'),
    (0x4504, 0x45b7, 'low-rate receive processing; MACD has a program-address operand'),
    (0x45e1, 0x4622, 'low-rate transmit setup and sample generation'),
)
CPU_RANGES = (
    (0x58f73, 0x58f9c, 'abort-on-key RX callback, still selected during CONNECT emission'),
    (0x5ccca, 0x5cd1c, 'online DTE input ring producer'),
    (0x59cb6, 0x59d40, 'queue-drain waits with timer deadlines; not plain delays'),
    (0x635a1, 0x6362b, 'originate configuration and command selection'),
    (0x638ad, 0x638e1, 'originate mode predicates'),
    (0x63975, 0x63a40, 'call supervision'),
    (0x63f9e, 0x6405b, 'qualified call-progress consumers'),
    (0x6405b, 0x6410c, 'originate commands 10/17 and monitor setup'),
    (0x6410c, 0x64148, 'call-progress reset and DSP configuration'),
    (0x67d33, 0x67d8c, 'outbound word ring and silent full-queue rejection'),
    (0x6d877, 0x6d8b3, 'report-28 handler selects the post-carrier mailbox ISR'),
    (0x6db02, 0x6dd35, 'DSP monitor report processing'),
    (0x6e9c5, 0x6ea09, 'post-carrier ASIC channel service'),
    (0x6ecfe, 0x6ed9b, 'post-carrier mailbox ISR and its original IRET'),
)


def dial_stage_program(image):
    """Resident plus the separate origin-zero library, not later overlays."""
    segments = image.dsp_program_segments()
    selected = [segments[0], next(segment for segment in segments if segment[0] == 0)]
    words = [0] * 65536
    for origin, payload in selected:
        words[origin:origin + len(payload) // 2] = struct.unpack(
            '<' + str(len(payload) // 2) + 'H', payload)
    return words


def audit(path: Path) -> str:
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != BC_SHA256:
        raise ValueError('requires the unmodified B/C 2.2.09 normal capture')
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    words = dial_stage_program(load_image(path))
    lines = [
        '; B/C 2.2.09 line-control disassembly',
        '; DSP stage: resident + origin-zero library; later overlays excluded.',
        '; BIT operands below are LSB-based indices emitted by c5x_disasm,',
        '; not TI assembler BIT numbering. Interpret as (word >> index) & 1.',
        '; Branches beyond a listed range are not decompiled here.',
    ]
    for start, end, title in DSP_RANGES:
        lines.append(f'\n; DSP {start:04x}..{end - 1:04x}: {title}')
        address = start
        while address < end:
            instruction = decode(words, address)
            lines.append(f'{address:04x}: {instruction.text}')
            address += instruction.size
    for start, end, title in CPU_RANGES:
        lines.append(f'\n; supervisor {start:05x}..{end - 1:05x}: {title}')
        for instruction in Cs(CS_ARCH_X86, CS_MODE_16).disasm(
                data[start - 0x40000:end - 0x40000], start):
            lines.append(f'{instruction.address:05x}: {instruction.mnemonic} {instruction.op_str}')
    return '\n'.join(lines) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    print(audit(args.capture), end='')


if __name__ == '__main__':
    main()
