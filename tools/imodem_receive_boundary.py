#!/usr/bin/env python3
"""Replay bounded, read-only Courier/I-modem receive snapshots; never feeds a modem."""
import argparse
import json
from pathlib import Path

from tools.imodem_link_errors import crc16_lapm


def hdlc_events(bits):
    """Decode flags/stuffing, retaining malformed and aborted frame prefixes.

    Only complete octets are returned. A firmware-generated partial-octet
    flush on an unaligned close is deliberately not guessed or CRC-qualified.
    Leading/trailing fragments without a complete boundary are not frames.
    """
    result = []
    active, ones, body, start = False, 0, [], 0

    def emit(kind, end):
        complete = len(body) // 8 * 8
        data = bytes(sum(body[i + b] << b for b in range(8))
                     for i in range(0, complete, 8))
        if body:
            result.append({'kind': kind, 'start_bit': start, 'end_bit': end,
                           'bit_length': len(body), 'complete_hex': data.hex(),
                           'crc_valid': kind == 'frame' and len(body) % 8 == 0
                           and len(data) >= 4 and crc16_lapm(data) == 0xf0b8})

    for position, bit in enumerate(bits):
        if bit not in (0, 1):
            raise ValueError('HDLC input must contain bits')
        if bit:
            ones += 1
            if ones == 7 and active:
                emit('abort', position + 1)
                active, body = False, []
        else:
            if ones == 6:
                if active and body:
                    body.pop()  # The flag's leading zero was held as data.
                    emit('frame' if len(body) % 8 == 0 else 'unaligned', position + 1)
                active, body, start = True, [], position - 7
            elif ones < 6 and active:
                body.extend([1] * ones)
                if ones != 5:  # A zero after five ones is stuffed, not data.
                    body.append(0)
            ones = 0
    return result


def inspect_event(event):
    ring = event.get('receive_ring', {})
    target = bytes.fromhex(ring.get('hex', ''))
    writes = [e for e in event.get('dsp_bank_history', [])
              if e['write'] and 0x58 <= e['port'] <= 0x5d]
    bank = None
    if target:
        for i in range(len(writes) - len(target) + 1):
            if [e['value'] for e in writes[i:i + len(target)]] == list(target):
                end = i + len(target)
                bank = {'first_instruction': writes[i]['instruction'],
                        'last_instruction': writes[end - 1]['instruction'],
                        'octets': len(target),
                        'following_token': writes[end]['value'] if end < len(writes) else None}
                break
    captured = event.get('dsp_bit_capture', {})
    rows = captured.get('rows', [])
    bits = []
    analog = captured.get('pc') == 0x8304
    if analog and (not captured.get('signature_verified')
                   or captured.get('addresses') != [0x320, 0x322]):
        raise ValueError('unsupported analog coherent DSP bit capture')
    for row in rows:
        if analog:
            if len(row) != 7 or row[3] != 6 or not 1 <= row[6] <= 16:
                raise ValueError('unsupported analog coherent DSP bit capture row')
            word, count = row[5:7]
        else:
            if len(row) != 6 or row[3] != 6 or not 1 <= row[5] <= 16:
                raise ValueError('unsupported coherent DSP bit capture')
            word, count = row[2], row[5]
        bits.extend((word >> b) & 1 for b in range(count))
    frames = hdlc_events(bits)
    for frame in frames:
        data = bytes.fromhex(frame['complete_hex'])
        frame['matches_ring_prefix'] = bool(data) and target.startswith(data)
        frame['matches_ring_exactly'] = bool(target) and data == target
        # This establishes a deletion-shaped boundary, not a guessed repair
        # or the timing/cause of the missing output words.
        cursor = 0
        for octet in data:
            if cursor < len(target) and octet == target[cursor]:
                cursor += 1
        subset = bool(target) and cursor == len(target)
        frame['ring_is_subsequence'] = subset
        frame['octets_missing_from_ring'] = len(data) - len(target) if subset else None
    return {'phase': event['phase'], 'frame': event.get('frame', event.get('line_frame')),
            'ring_hex': target.hex(), 'ring_crc_matches_firmware': ring.get('crc_matches_firmware'),
            'bank_match': bank, 'coherent_groups': len(rows), 'pre_hdlc_events': frames}


def inspect(report):
    return [inspect_event(e) for e in report['events'] if 'dsp_bank_history' in e]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = json.loads(args.capture.read_text())
    if 'analog' in report:
        report = report['analog']['rom_link_errors']
    text = json.dumps(inspect(report), indent=2) + '\n'
    if args.output:
        args.output.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
