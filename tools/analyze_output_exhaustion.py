#!/usr/bin/env python3
"""Replay the passive 403 first-full-bank trace, without repairing guest data.

CPU stamps describe actual CPU accesses/IRQ observations. DSP rows deliberately
have no CPU timestamp: catch-up DSP batches prevent interpreting adjacent CPU
observations as a physical time bracket. EOI rows are observations, not writes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def analyze(trace: dict) -> dict:
    rows = trace['rows']
    result = {'armed': trace['armed'], 'triggered': bool(rows),
              'full_status_reads': trace['full_status_reads'],
              'status_mismatches': [], 'word_mismatches': [],
              'occupied_output_writes': []}
    if not rows:
        return result  # No trigger is not proof that the call was reliable.
    if not trace.get('output_signature_verified'):
        raise ValueError('unsupported or changed DSP output signature/epoch')
    trigger_index = trace['trigger_index']
    if not isinstance(trigger_index, int) or not 0 <= trigger_index < len(rows):
        raise ValueError('invalid first-full trigger index')
    trigger = rows[trigger_index]
    if (trigger['kind'] != 8 or trigger['port_or_vector'] != 0x56
            or trigger['value'] & 0x3f00):
        raise ValueError('trigger is not a full DSP PA6 read')
    result['trigger'] = trigger
    context = rows[trigger_index - 1] if trigger_index else {}
    result['blocked_word'] = context.get('value') if context.get('kind') == 11 else None
    result['post_events_remaining'] = trace['post_events_remaining']
    # None means the ring rolled over before this bank's initial state.
    free = [None] * 6
    words = [None] * 6
    last_publication = [None] * 6
    banks_at_trigger = None
    acknowledgments = []
    previous_dsp = previous_cycles = previous_cpu = 0
    for index, row in enumerate(rows):
        dsp, cycles, cpu = (row[k] for k in ('dsp_instructions', 'dsp_cycles', 'cpu_instructions'))
        if dsp < previous_dsp or cycles < previous_cycles or (cpu and cpu < previous_cpu):
            raise ValueError('mixed or unordered processor instruction epochs')
        previous_dsp, previous_cycles = dsp, cycles
        if cpu:
            previous_cpu = cpu
        kind, port, value = (row[k] for k in ('kind', 'port_or_vector', 'value'))
        if kind == 8 and port == 0x56 or kind == 10 and port == 0x1a:
            observed = value >> 8 & 0x3f if kind == 8 else ~value & 0x3f
            for bank in range(6):
                bit = bool(observed & (1 << bank))
                if free[bank] is not None and free[bank] != bit:
                    result['status_mismatches'].append({'row': index, 'bank': bank,
                                                        'expected_free': free[bank],
                                                        'observed_free': bit})
                free[bank] = bit
        elif kind == 9 and port == 0x56:
            for bank in range(6):
                if value & (0x100 << bank):
                    free[bank] = False
        elif kind == 9 and 0x58 <= port <= 0x5d:
            bank = port - 0x58
            if free[bank] is False:
                result['occupied_output_writes'].append({'row': index, 'bank': bank})
            words[bank] = value
            last_publication[bank] = {'row': index, 'word': value,
                                      'dsp_instructions': dsp, 'dsp_cycles': cycles}
        elif kind == 2 and port == 0x1a:
            acknowledgments.append((index, row))
            for bank in range(6):
                if value & (1 << bank):
                    free[bank] = True
        elif kind == 3 and 0x40 <= port <= 0x56 and port % 2 == 0:
            bank, half = divmod((port - 0x40) // 2, 2)
            if words[bank] is not None:
                expected = words[bank] >> (8 * half) & 0xff
                if value != expected:
                    result['word_mismatches'].append({'row': index, 'bank': bank,
                                                      'expected': expected, 'observed': value})
        if index == trigger_index:
            banks_at_trigger = list(last_publication)
    result['last_publications_at_trigger'] = banks_at_trigger
    before = [(i, r) for i, r in acknowledgments if i < trigger_index]
    after = [(i, r) for i, r in acknowledgments if i > trigger_index]
    result['last_ack_before_trigger'] = before[-1][1] if before else None
    result['first_ack_after_trigger'] = after[0][1] if after else None
    if before and after:
        low, high = before[-1][0], after[0][0]
        result['cpu_ack_gap_instructions'] = (after[0][1]['cpu_instructions']
                                               - before[-1][1]['cpu_instructions'])
        result['irq_observations_in_ack_gap'] = [r for r in rows[low + 1:high]
                                                 if r['kind'] in (4, 5, 6, 7)]
    # Absence of mismatches means the sampled modeled handshake is internally
    # consistent, not that the undocumented physical ASIC has identical rules.
    result['sampled_handshake_consistent'] = not any(result[k] for k in (
        'status_mismatches', 'word_mismatches', 'occupied_output_writes'))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path, help='analog-result.json or combined result.json')
    args = parser.parse_args()
    data = json.loads(args.result.read_text())
    observer = data.get('rom_link_errors') or data.get('analog', {}).get('rom_link_errors')
    if not observer or not observer.get('output_exhaustion'):
        parser.error('result has no first-full-bank capture')
    print(json.dumps(analyze(observer['output_exhaustion']), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
