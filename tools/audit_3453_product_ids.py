#!/usr/bin/env python3
"""Offline inventory of captured 3453 identity tables and DSP load ranges.

Does not read serial ports or private settings. Offsets refer to transfer files,
not CPU addresses. Literal IDs are fallback templates, not a board census.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from courier_emu.images import load_image

CAPABILITY = bytes.fromhex('00002900001400220028004228224800')


def product_type(capability: int) -> str:
    for mask, name in ((2, 'External'), (8, 'Internal'), (4, 'Rackmount')):
        if capability & mask:
            return name
    return 'Undefined'


def country_profiles(raw: bytes) -> list[dict]:
    """Decode the fixed 28 x 128-byte country table, not sales SKU prefixes."""
    start = 0
    candidates = []
    while (start := raw.find(b'US/Canada!', start)) >= 0:
        if raw[start + 8 * 128:start + 8 * 128 + 6] == b'CTR21!':
            candidates.append(start)
        start += 1
    if len(candidates) != 1:
        raise ValueError('expected one country table with CTR21 in slot 8')
    base = candidates[0]
    profiles = []
    for code in range(28):
        offset = base + code * 128
        row = raw[offset:offset + 128]
        name = row[:16].split(b'!', 1)[0].decode('ascii').strip()
        profiles.append({'index': code, 'name': name,
                         'file_offset': f'0x{offset:x}',
                         'si3034_reg16': f'{row[0x79]:02x}',
                         'si3034_reg17_table': f'{row[0x7a]:02x}',
                         'si3034_reg17_sent': f'{row[0x7a] & 0xfb:02x}',
                         'si3034_reg18': f'{row[0x7b]:02x}',
                         'sha256': hashlib.sha256(row).hexdigest()})
    return profiles


def audit(path: Path) -> dict:
    raw = path.read_bytes()
    offset = raw.find(CAPABILITY)
    if offset < 0 or raw.find(CAPABILITY, offset + 1) >= 0:
        raise ValueError(f'{path}: expected one captured board-capability table')
    image = load_image(path)
    literals = {}
    for value in (b'00345303', b'XX345303', b'00345302', b'XX345302', b'345403', b'345303', b'345402', b'345302'):
        positions = []
        start = 0
        while (start := raw.find(value + b'\0', start)) >= 0:
            positions.append(f'0x{start:x}')
            start += len(value)
        if positions:
            literals[value.decode()] = positions
    return {
        'file': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
        'capability_table_file_offset': f'0x{offset:x}',
        'straps': [
            {'code': code, 'capability': f'0x{cap:02x}',
             'type': product_type(cap),
             'usable': bool(cap) and not bool(cap & 0x40)}
            for code, cap in enumerate(CAPABILITY)
        ],
        'identity_literals': literals,
        'country_profiles': country_profiles(raw),
        'ati0_literals': {value.decode(): f'0x{raw.find(b"\x80" + value + b"\x80\x00") + 1:x}'
                         for value in (b'3368', b'3368A', b'5608', b'5608A')
                         if raw.find(b"\x80" + value + b"\x80\x00") >= 0},
        'bootstrap_segments': [
            {'origin_words': f'0x{origin:04x}', 'words': len(data) // 2,
             'end_exclusive_words': f'0x{origin + len(data)//2:04x}',
             'sha256': hashlib.sha256(data).hexdigest()}
            for origin, data in image.dsp_program_segments()
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', type=Path, nargs='+')
    args = parser.parse_args()
    print(json.dumps([audit(path) for path in args.images], indent=2))


if __name__ == '__main__':
    main()
