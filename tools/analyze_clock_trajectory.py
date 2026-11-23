#!/usr/bin/env python3
"""Read-only CPU/DSP/PCM counter analysis; never interpolates event times.

Snapshots are observations at CPU interrupt entry. DSP catch-up may lag CPU
elapsed device time. A flat cycle-debt curve does not prove IRQ ordering or
physical ASIC correctness. Compare steady-state segments within one DSP epoch;
never form a delta across a reset or codec retune.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def summarize(rows: list[dict[str, int]], *, cpu_hz: float, dsp_hz: float,
              dsp_per_cpu: float) -> list[dict]:
    if min(cpu_hz, dsp_hz, dsp_per_cpu) <= 0:
        raise ValueError('clock rates must be positive')
    groups: list[list[dict[str, int]]] = []
    for row in rows:
        if not groups or any(row[key] != groups[-1][-1][key]
                             for key in ('epoch', 'codec_period')):
            groups.append([])
        if groups[-1] and row['cpu_instructions'] <= groups[-1][-1]['cpu_instructions']:
            raise ValueError('CPU clock samples must strictly increase within an epoch')
        groups[-1].append(row)
    result = []
    for group in groups:
        if len(group) < 2:
            continue
        first, last = group[0], group[-1]
        counters = ('dsp_cycles', 'dsp_instructions', 'dsp_xf_edges',
                    'codec_primary_frames', 'line_input_queued', 'line_input_consumed',
                    'codec_tx_samples', 'frame_irq_entries', 'frame_eoi_observations')
        for a, b in zip(group, group[1:]):
            if any(b[key] < a[key] for key in counters):
                raise ValueError('counter rewind inside a DSP epoch/codec segment')
        if any(r['line_input_queued'] - r['line_input_consumed'] != r['line_input_pending']
               for r in group):
            raise ValueError('raw line PCM accounting is inconsistent')
        cpu_delta = last['cpu_instructions'] - first['cpu_instructions']
        dsp_delta = last['dsp_cycles'] - first['dsp_cycles']
        if dsp_delta <= 0:
            continue
        seconds = dsp_delta / dsp_hz
        delta = {key: last[key] - first[key] for key in counters}
        debt = [r['dsp_cycles'] - first['dsp_cycles'] - dsp_per_cpu *
                (r['cpu_instructions'] - first['cpu_instructions']) for r in group]
        pending = [r['line_input_pending'] for r in group]
        result.append({
            'epoch': first['epoch'], 'codec_period': first['codec_period'],
            'snapshots': len(group), 'cpu_start': first['cpu_instructions'],
            'cpu_end': last['cpu_instructions'], 'cpu_seconds': cpu_delta / cpu_hz,
            'dsp_seconds': seconds, 'dsp_cycles_per_cpu_instruction': dsp_delta / cpu_delta,
            'relative_cycle_debt': {'first': debt[0], 'last': debt[-1],
                                    'min': min(debt), 'max': max(debt)},
            'xf_edges_per_dsp_second': delta['dsp_xf_edges'] / seconds,
            'frame_irqs_per_dsp_second': delta['frame_irq_entries'] / seconds,
            'irq_minus_xf_delta': delta['frame_irq_entries'] - delta['dsp_xf_edges'],
            'codec_samples_per_dsp_second': delta['codec_primary_frames'] / seconds,
            'raw_line_samples_consumed_per_dsp_second': delta['line_input_consumed'] / seconds,
            'raw_line_pending': {'first': pending[0], 'last': pending[-1],
                                 'min': min(pending), 'max': max(pending)},
            'counter_deltas': delta,
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    parser.add_argument('--start-cpu', type=int, default=0)
    parser.add_argument('--end-cpu', type=int)
    parser.add_argument('--before-first-error', action='store_true')
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    analog = report.get('analog', report)
    errors = analog['rom_link_errors']
    pending = [e['instructions'] for e in errors.get('events', [])
               if e['kind'] == 'pending_error']
    end = args.end_cpu
    if args.before_first_error and pending:
        end = min(end, pending[0]) if end is not None else pending[0]
    rows = [r for r in errors['clock_timeline'] if r['cpu_instructions'] >= args.start_cpu
            and (end is None or r['cpu_instructions'] <= end)]
    tb = analog['timebase']
    print(json.dumps({'report': str(args.report), 'first_pending_error_cpu':
                      pending[0] if pending else None,
                      'segments': summarize(rows, cpu_hz=tb['instructions_per_second'],
                          dsp_hz=tb['dsp_clock_hz'], dsp_per_cpu=tb['dsp_cycles_per_x86'])},
                     indent=2))


if __name__ == '__main__':
    main()
