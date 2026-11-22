from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools.analyze_output_exhaustion import analyze


def row(kind, port, value, now=0):
    return dict(kind=kind, port_or_vector=port, value=value,
                cpu_instructions=now, dsp_instructions=0, dsp_cycles=0, pc=0, flags=0)


def trace():
    rows = [row(8, 0x56, 0x3f00), row(9, 0x58, 0x1234), row(9, 0x56, 0x100),
            row(10, 0x1a, 0xc1, 10), row(3, 0x40, 0x34, 11), row(3, 0x42, 0x12, 12),
            row(2, 0x1a, 1, 13), row(9, 0x56, 0x3f00), row(11, 0x320, 0x42),
            row(8, 0x56, 0), row(6, 12, 0, 20), row(10, 0x1a, 0xff, 21),
            row(2, 0x1a, 0x3f, 22), row(8, 0x56, 0x3f00)]
    return dict(armed=True, full_status_reads=1, rows=rows,
                trigger_index=9, post_events_remaining=0, output_signature_verified=True)


def test_replay_validates_status_polarity_word_halves_and_ack_gap():
    t = trace()
    before = deepcopy(t)
    result = analyze(t)
    assert t == before  # Offline analysis is not guest repair.
    assert result['sampled_handshake_consistent']
    assert result['blocked_word'] == 0x42
    assert result['cpu_ack_gap_instructions'] == 9
    assert result['last_publications_at_trigger'][0]['word'] == 0x1234
    assert len(result['irq_observations_in_ack_gap']) == 1


@pytest.mark.parametrize('index,value,key', [(3, 0xc0, 'status_mismatches'),
                                            (4, 0x35, 'word_mismatches')])
def test_malformed_status_and_torn_word_are_not_silently_accepted(index, value, key):
    t = trace()
    t['rows'][index]['value'] = value
    result = analyze(t)
    assert not result['sampled_handshake_consistent']
    assert result[key]


def test_occupied_output_write_is_distinct_from_a_full_status_read():
    t = trace()
    t['rows'].insert(3, row(9, 0x58, 0x1234))
    t['trigger_index'] += 1
    assert analyze(t)['occupied_output_writes'] == [{'row': 3, 'bank': 0}]


def test_unknown_initial_banks_and_absent_trigger_do_not_invent_evidence():
    t = trace()
    t['rows'] = t['rows'][3:]
    t['trigger_index'] -= 3
    assert analyze(t)['sampled_handshake_consistent']
    t['rows'] = []
    result = analyze(t)
    assert not result['triggered']
    assert 'sampled_handshake_consistent' not in result


def test_invalid_epoch_signature_or_trigger_fails_closed():
    t = trace()
    t['output_signature_verified'] = False
    with pytest.raises(ValueError, match='signature/epoch'):
        analyze(t)
    t = trace()
    t['rows'][-1]['dsp_instructions'] = 10
    t['rows'].append(row(7, 12, 0x8000, 23))
    with pytest.raises(ValueError, match='epochs'):
        analyze(t)
    t = trace()
    t['trigger_index'] = 0
    with pytest.raises(ValueError, match='not a full'):
        analyze(t)


@pytest.mark.parametrize('directory,blocked,gap', [
    ('imodem-x2-first-data-full-repeat-20261027-150822', 0xce, 5120),
    ('imodem-x2-first-data-full-60s-20261027-150912', 0xa0, 2023),
])
def test_replay_captured_first_nonidle_exhaustion(directory, blocked, gap):
    path = Path('artifacts') / directory / 'analog-result.json'
    if not path.exists():
        pytest.skip('optional live capture')
    data = json.loads(path.read_text())
    result = analyze(data['rom_link_errors']['output_exhaustion'])
    assert result['blocked_word'] == blocked
    assert result['cpu_ack_gap_instructions'] == gap
    assert result['sampled_handshake_consistent']
    assert data['rom_link_errors']['bler_count'] > 0
