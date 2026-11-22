#!/usr/bin/env python3
"""Summarize passive 403 LAPM observations; never equate staging with wire TX."""
import argparse
from collections import Counter
import json
from pathlib import Path


def analyze(trace, *, start_line_frame=None, end_line_frame=None):
    if not trace.get('signature_verified'):
        raise ValueError('unverified LAPM trace')
    origin = trace.get('origin_line_frame')
    scale = trace.get('line_frame_samples', 160) / 8000
    counts, invalid = Counter(), Counter()
    controls, gaps, busy_intervals = [], [], []
    previous_i, busy = {}, {}
    packets = trace['packets']
    for before, after in zip(packets, packets[1:]):
        if (after['line_frame'] < before['line_frame']
                or after['cpu_instructions'] < before['cpu_instructions']):
            raise ValueError('counter rewind in LAPM trace')
    for original in packets:
        # The first pilot used address-specific names. Preserve its evidence
        # without calling the reload parameter at 0AEF a running timer tick.
        packet = dict(original)
        for key, old in {'flow_flags': 'flags_0231', 'rx_read': 'rx_read_0258',
                         'rx_write': 'rx_write_0256', 'state_hex': 'state_0b47_0b8f_hex',
                         'timer_reload': 'tick_0aef'}.items():
            if key not in packet:
                packet[key] = packet[old]
        if start_line_frame is not None and packet['line_frame'] < start_line_frame:
            continue
        if end_line_frame is not None and packet['line_frame'] >= end_line_frame:
            continue
        direction = 'rx' if packet['kind'] == 'rx_crc_gate' else 'tx_staged'
        if direction == 'rx':
            if not packet.get('firmware_crc_valid'):
                invalid['firmware_crc_rejected'] += 1
                continue
            if not packet.get('ring_crc_matches_firmware'):
                invalid['ring_not_independently_verified'] += 1
                continue
        decoded = packet.get('decoded', {})
        kind = decoded.get('type', 'undecoded')
        counts[f'{direction}:{kind}'] += 1
        row = {'direction': direction, 'line_frame': packet['line_frame'],
               'seconds_from_trace_origin': (packet['line_frame'] - origin) * scale,
               'cpu_instructions': packet['cpu_instructions'], 'header_hex': packet['header_hex'],
               **decoded, 'flow_flags': packet['flow_flags'],
               'rx_read': packet['rx_read'], 'rx_write': packet['rx_write'],
               'state_hex': packet['state_hex'], 'timer_reload': packet['timer_reload']}
        if kind == 'I':
            old = previous_i.get(direction)
            if old is not None and (row['line_frame'] - old['line_frame']) * scale >= .5:
                gaps.append({'direction': direction,
                             'gap_seconds': (row['line_frame'] - old['line_frame']) * scale,
                             'before': old, 'after': row})
            previous_i[direction] = row
        else:
            controls.append(row)
        if kind == 'RNR' and direction not in busy:
            busy[direction] = row
        elif kind == 'RR' and direction in busy:
            start = busy.pop(direction)
            busy_intervals.append({'direction': direction,
                                   'rnr_to_rr_seconds': (row['line_frame'] - start['line_frame']) * scale,
                                   'rnr': start, 'rr': row})
    flow_offsets = {*trace.get('flow_state_offsets', (0xb64, 0xb7e, 0xb7f)),
                    trace.get('flow_offset', 0x231), 0x3cf if trace.get('profile', '403') == '403' else 0xd083}
    return {'packet_counts': dict(counts), 'excluded_rx': dict(invalid),
            'start_line_frame': start_line_frame, 'end_line_frame': end_line_frame,
            'trace_counts': trace['counts'], 'control_frames': controls,
            'rnr_to_rr_intervals': busy_intervals, 'rnr_without_following_rr': busy,
            'i_frame_gaps_at_least_half_second': gaps,
            'flow_state_changes': [e for e in trace['states']
                if e.get('offset', e['address']) in flow_offsets
                and (start_line_frame is None or e['line_frame'] >= start_line_frame)
                and (end_line_frame is None or e['line_frame'] < end_line_frame)],
            'interpretation': 'RX requires both firmware and ring CRC verification; TX is CPU staging only. '
                              'RNR-to-RR intervals describe observations, not proof of peer reception or lost ACKs.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--side', choices=('analog', 'imodem'), default='analog')
    args = parser.parse_args()
    result = json.loads(args.result.read_text())
    endpoint = result.get(args.side, result)
    trace = (endpoint.get('rom_link_errors', {}).get('lapm_trace') if args.side == 'analog'
             else endpoint.get('lapm_trace'))
    if trace is None:
        parser.error('result has no LAPM trace; use --analog-trace-lapm / --trace-lapm')
    start = result.get('traffic_stream_start_frames', {}).get(args.side)
    scale = 800 / trace.get('line_frame_samples', 160)
    bounds = {} if start is None else dict(start_line_frame=start * scale,
        end_line_frame=(start + result['traffic_seconds'] * 10) * scale)
    report = analyze(trace, **bounds)
    text = json.dumps(report, indent=2) + '\n'
    if args.output:
        if args.output.exists():
            parser.error('refusing to overwrite an existing analysis')
        args.output.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
