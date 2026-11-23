"""Offline dispatch-table audit of the four captured analogue Courier images."""
from pathlib import Path
import hashlib
import json
import re
import struct
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_16

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'artifacts/bootmodem-command-audit-20261014'
IMAGES = [
    ('bc-boot', 'dumps/3453bc-4MBRYA8G1514-bootmodem-read-20261014/bootmodem.bin', 0),
    ('bc-normal', 'dumps/3453bc-firmware-read-2.2.09/firmware.bin', 0x40000),
    ('c-boot', 'dumps/3453c-5MBRZ16P0186-bootmodem-read-20261014/bootmodem.bin', 0),
    ('c-normal', 'dumps/3453c-5MBRZ16P0186-firmware-read-20261014/firmware.bin', 0x40000),
]
MD = Cs(CS_ARCH_X86, CS_MODE_16)


def instructions(data, start, length):
    return list(MD.disasm(data[start:start + length], start))


def table(data, address, count, base, names):
    result = {}
    for name, offset in zip(names, struct.unpack_from(f'<{count}H', data, address)):
        target = base + offset
        rejected = offset == 0xFFFF or data[target:target+2] == b'\xf9\xc3'
        result[name] = {'offset': offset, 'file_address': None if offset == 0xFFFF else target,
                        'immediate_error': rejected}
    return result


def annotated(data, start, end, near_printer):
    lines = []
    pos = start
    while pos < end:
        ins = next(MD.disasm(data[pos:min(end, pos+15)], pos), None)
        if ins is None:
            lines.append(f'{pos:05x}: db {data[pos]:02x}')
            pos += 1
            continue
        lines.append(f'{pos:05x}: {ins.mnemonic:8} {ins.op_str}')
        pos += ins.size
        is_printer = ins.mnemonic == 'lcall' and ins.op_str.split(', ')[-1] in ('0xfaf', '0xfc3')
        is_printer |= ins.mnemonic == 'call' and ins.op_str == hex(near_printer)
        if is_printer:
            terminator = data.find(b'\0', pos, min(end, pos+1024))
            if terminator >= pos:
                lines.append(f'{pos:05x}: inline print string {data[pos:terminator]!r}')
                pos = terminator + 1
    return '\n'.join(lines) + '\n'


def audit(label, path, flash_base):
    data = (ROOT / path).read_bytes()
    # Exact common entry of the !..Z/~ dispatcher, independently identified in stock C.
    reference = (ROOT / IMAGES[-1][1]).read_bytes()[0x416a5:0x416a5+12]
    dispatch = data.find(reference)
    assert dispatch >= 0 and data.find(reference, dispatch+1) == -1
    assert data[dispatch+23] == 0xBA  # mov dx, table segment
    main_table = struct.unpack_from('<H', data, dispatch+24)[0] * 16 - flash_base
    g_entry = data.find(bytes.fromhex('813c5349756f83c60283e902e32283f9'))
    g_relative = struct.unpack_from('<H', data, main_table + 2*(ord('G')-33))[0]
    base = g_entry - g_relative
    main = table(data, main_table, 59, base, [chr(i) for i in range(33, 91)] + ['~'])
    calls = [int(re.search(r'\+ (0x[0-9a-f]+)', ins.op_str)[1], 16)
             for ins in instructions(data, base, dispatch-base)
             if ins.mnemonic == 'call' and 'cs:[bx +' in ins.op_str]
    assert len(calls) == 3 and calls[0] == calls[1]
    percent = table(data, base+calls[0], 26, base, list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
    amp = table(data, base+calls[2], 26, base, list('ABCDEFGHIJKLMNOPQRSTUVWXYZ'))
    i_entry = main['I']['file_address']
    indirect = [ins for ins in instructions(data, i_entry, 80)
                if ins.mnemonic == 'jmp' and 'cs:[bx +' in ins.op_str]
    assert len(indirect) == 1
    i_offset = int(re.search(r'\+ (0x[0-9a-f]+)', indirect[0].op_str)[1], 16)
    ati = table(data, base+i_offset, 18, base, [str(i) for i in range(18)])
    i9 = ati['9']['file_address']
    near_call = next(ins for ins in instructions(data, i9, 12) if ins.mnemonic == 'call')
    near_printer = int(near_call.op_str, 16)
    sections = {
        'parser': (base, dispatch+0x40),
        'ATG': (g_entry, main['H']['file_address']),
        'ATI': (i_entry, main['K']['file_address']),
        'ATX': (main['X']['file_address'], main['Y']['file_address']),
        'ATZ': (main['Z']['file_address'], main['~']['file_address']),
        'AT~': (main['~']['file_address'], main['~']['file_address']+0x100),
    }
    x_instructions = instructions(data, main['X']['file_address'], 0x30)
    x_call = next(ins for ins in x_instructions if ins.mnemonic == 'lcall')
    segment, offset = (int(value, 16) for value in x_call.op_str.split(', '))
    transfer_entry = (segment << 4) + offset - flash_base
    sections['ATXMODEM-transfer'] = (transfer_entry, transfer_entry+0xE40)
    if not percent['N']['immediate_error']:
        start = percent['N']['file_address']
        sections['AT%N'] = (start, start+0x16)
    for name, (start, end) in sections.items():
        (OUTPUT / f'{label}-{name}.asm').write_text(annotated(data, start, end, near_printer))
    result = {'source': path, 'sha256': hashlib.sha256(data).hexdigest(),
              'addresses_are': 'file offsets, not necessarily runtime CPU addresses',
              'dispatcher': dispatch, 'command_module': base,
              'xmodem_transfer_entry': transfer_entry,
              'tables': {'main': main, 'percent': percent, 'ampersand': amp, 'ATI': ati},
              'has_bootmodem_menu': b'(#) Read bootmodem' in data,
              'has_PQC_text': b'+PQC' in data,
              'boot_entry_vector_at_3fff0': data[0x3fff0:0x40000].hex() if flash_base == 0 else None,
              'main_entry_vector_at_2e0': data[0x2e0:0x2f0].hex() if flash_base else None,
              'limitations': ['A non-error table slot does not prove every argument is accepted.',
                             'Main-table error slots may have prefix handling before this table.',
                             'Linear disassembly is annotated for identified inline string printers; it is not a complete CFG.',
                             'No unknown command was sent to hardware during this audit.']}
    return result


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    results = {label: audit(label, path, base) for label, path, base in IMAGES}
    comparisons = {}
    for family in ('bc', 'c'):
        boot, normal = results[family+'-boot'], results[family+'-normal']
        comparisons[family] = {}
        for name in boot['tables']:
            b = boot['tables'][name]
            n = normal['tables'][name]
            comparisons[family][name] = {
                'boot_only_non_error_slots': [k for k in b if not b[k]['immediate_error'] and n[k]['immediate_error']],
                'normal_only_non_error_slots': [k for k in n if not n[k]['immediate_error'] and b[k]['immediate_error']],
            }
    (OUTPUT / 'dispatch-tables.json').write_text(json.dumps({'images': results, 'comparisons': comparisons}, indent=2)+'\n')
    print(json.dumps(comparisons, indent=2))
    print('Evidence:', OUTPUT.relative_to(ROOT))


if __name__ == '__main__':
    main()
