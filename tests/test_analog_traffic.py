import pytest

from tools.analog_traffic import AnalogTraffic
from tools.imodem_traffic import record


def test_fragmented_connect_and_payload_share_a_chunk_without_losing_bytes():
    pair = AnalogTraffic(2, 32)
    pair.receive('analog', '\r\nCON', 10)
    assert pair.streams['analog'].start_frame is None
    pair.receive('analog', 'NECT 53333/ARQ/x2/LAPM\r\n' + record('A', 0, 32), 11)
    assert pair.streams['analog'].received == 1
    assert pair.streams['analog'].start_frame == 11


def test_window_is_frozen_and_final_records_are_stream_verified_during_drain():
    pair = AnalogTraffic(2, 32)
    for side in pair.streams:
        pair.receive(side, '\r\nCONNECT 53333/ARQ/x2/LAPM\r\n', 0)
    for frame in range(20):
        a = pair.next_record('analog', frame)
        i = pair.next_record('imodem', frame)
        pair.receive('analog', i, frame)
        pair.receive('imodem', a, frame)
        pair.update(frame)
    pair.update(20)
    assert pair.done(20)
    pair.verify(20)
    assert pair.windows['analog']['received_records'] == 20
    status = pair.status(20)
    assert status['drain']['analog']['received_sha256'] == status['drain']['imodem']['sent_sha256']
    assert status['drain']['imodem']['received_sha256'] == status['drain']['analog']['sent_sha256']
    assert status['throughput']['analog']['payload_bytes_per_second'] == 320
    pair.receive('analog', '!', 21)
    assert pair.windows['analog']['errors'] == []
    with pytest.raises(AssertionError, match='corrupt'):
        pair.verify(21)


def test_stalled_receiver_preserves_the_requested_window_but_fails_verification():
    pair = AnalogTraffic(60, 512)
    for side in pair.streams:
        pair.receive(side, '\r\nCONNECT 53333\r\n', 0)
    pair.update(51)
    assert not pair.done(51)
    assert pair.stalls == {'analog': 51, 'imodem': 51}
    pair.update(600)
    assert pair.done(600)
    with pytest.raises(AssertionError, match='insufficient verified traffic'):
        pair.verify(600)


@pytest.mark.parametrize('directory', [
    'imodem-v34-uart-fixed-repeat-20261026-222730',
    'imodem-v34-uart-fixed-auto-20261026-222843',
    'imodem-v34-uart-fixed-60s-20261026-223152',
])
def test_saved_fixed_uart_calls_replay_the_unchanged_large_record_gate(directory):
    import json
    from hashlib import sha256
    from pathlib import Path
    import re
    from tools.imodem_traffic import check_records, check_record_window

    root = Path('artifacts') / directory
    if not (root / 'result.json').exists():
        pytest.skip('optional saved paired-call capture')
    result = json.loads((root / 'result.json').read_text())
    assert result['traffic_verified']
    states = result['traffic']['drain']
    for side, filename, role in [('analog', 'analog-dte.bin', 'A'),
                                  ('imodem', 'imodem-terminal.txt', 'O')]:
        raw = (root / filename).read_bytes()
        if side == 'analog':
            raw = bytes(b & 127 for b in raw)
        start = re.search(rb'(?:^|[\r\n])CONNECT[^\r\n]*\r\n', raw).end()
        state = states[side]
        complete = ''.join(record(role, i, 512) for i in range(state['received_records'])).encode()
        partial = record(role, state['received_records'], 512).encode()[:state['pending_bytes']]
        assert raw[start:start + len(complete + partial)] == complete + partial
        assert sha256(complete).hexdigest() == state['received_sha256']
        check_record_window(result['traffic']['windows'][side], side)
    check_records({'originate': states['analog'], 'answer': states['imodem']})
    assert result['analog']['serial_uart']['overruns'] == 0
    assert result['analog']['serial_uart']['transmit_overruns'] == 0
    assert not result['imodem']['link_errors']['counts']


def test_each_sender_waits_for_its_own_remote_receiver_independently():
    pair = AnalogTraffic(60, 32)
    for side in pair.streams:
        pair.receive(side, '\r\nCONNECT 53333\r\n', 0)
    a = pair.next_record('analog', 1)
    assert pair.next_record('analog', 1) is None
    assert pair.next_record('imodem', 1) is not None
    pair.receive('imodem', a, 2)
    # Only analog's first record has arrived. It may send another even
    # though it has not yet received anything in the opposite direction.
    assert pair.next_record('analog', 2) is not None
    assert pair.next_record('imodem', 2) is None
