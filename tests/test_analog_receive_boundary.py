import json
from pathlib import Path

import pytest

from tools.imodem_link_errors import crc16_lapm
from tools.imodem_receive_boundary import inspect_event, inspect


def make_event():
    data = b'\x01\x8e\xacgood-frame-with-three-missing-bytes'
    data += (crc16_lapm(data) ^ 0xffff).to_bytes(2, 'little')
    bits, ones = [0, 1, 1, 1, 1, 1, 1, 0], 0
    for byte in data:
        for shift in range(8):
            bit = byte >> shift & 1
            bits.append(bit)
            ones = ones + 1 if bit else 0
            if ones == 5:
                bits.append(0)
                ones = 0
    bits += [0, 1, 1, 1, 1, 1, 1, 0]
    rows = []
    for i in range(0, len(bits), 8):
        group = bits[i:i+8]
        rows.append([i, i*2, 0xdeadbeef, 6, 0,
                     sum(bit << k for k, bit in enumerate(group)), len(group)])
    ring = data[:9] + data[12:]
    writes = [{'write': True, 'port': 0x58 + i % 6, 'value': byte, 'instruction': i}
              for i, byte in enumerate(ring)]
    # Mailbox control words must not break the data-bank match.
    writes.insert(10, {'write': True, 'port': 0x5f, 'value': 123, 'instruction': 10})
    return {'phase': 'online', 'line_frame': 123,
            'receive_ring': {'hex': ring.hex(), 'crc_matches_firmware': True},
            'dsp_bank_history': writes,
            'dsp_bit_capture': {'pc': 0x8304, 'addresses': [0x320, 0x322],
                                'signature_verified': True, 'rows': rows}}


def test_memory_word_capture_finds_valid_fcs_before_missing_output_octets():
    result = inspect_event(make_event())
    assert result['frame'] == 123
    assert result['bank_match']['octets'] == len(bytes.fromhex(result['ring_hex']))
    frame, = result['pre_hdlc_events']
    assert frame['crc_valid']
    assert frame['ring_is_subsequence'] and frame['octets_missing_from_ring'] == 3
    assert not frame['matches_ring_exactly']


@pytest.mark.parametrize('change', ['signature', 'addresses', 'page', 'count'])
def test_wrong_analog_capture_is_never_decoded(change):
    event = make_event()
    capture = event['dsp_bit_capture']
    if change == 'signature':
        capture['signature_verified'] = False
    elif change == 'addresses':
        capture['addresses'] = [0x320]
    elif change == 'page':
        capture['rows'][0][3] = 7
    else:
        capture['rows'][0][6] = 17
    with pytest.raises(ValueError, match='unsupported analog coherent'):
        inspect_event(event)


@pytest.mark.parametrize('name,missing', [
    ('imodem-x2-downstream-coherent53333-20261027-091843', 3),
    ('imodem-x2-downstream-service256-20261027-092450', 3),
    ('imodem-x2-downstream-service64-20261027-093015', 4),
])
def test_captured_downstream_failure_has_valid_input_fcs_but_shortened_dsp_output(name, missing):
    path = Path('artifacts') / name / 'result.json'
    if not path.exists():
        pytest.skip('optional local captured call')
    report = json.loads(path.read_text())
    assert not report['traffic_verified']
    assert report['imodem']['link_errors']['bler_count'] == 0
    observer = report['analog']['rom_link_errors']
    first, = inspect(observer)
    assert first['ring_crc_matches_firmware'] and first['bank_match']
    candidates = [f for f in first['pre_hdlc_events'] if f['crc_valid'] and f['ring_is_subsequence']]
    frame, = candidates
    assert frame['octets_missing_from_ring'] == missing
    assert crc16_lapm(bytes.fromhex(first['ring_hex'])) != 0xf0b8
    if missing == 4:
        event = next(e for e in observer['events'] if 'dsp_bit_capture' in e)
        full_reads = [e for e in event['dsp_bank_history']
                      if not e['write'] and e['port'] == 0x56 and e['value'] & 0x3f00 == 0]
        assert len(full_reads) == 4


def captured(name):
    path = Path('artifacts') / name / 'result.json'
    if not path.exists():
        pytest.skip('optional local captured call')
    result = json.loads(path.read_text())
    assert not result['traffic_verified']
    return result


def test_cpu_dsp_timeline_retains_real_bank_accesses_and_frame_irq_acknowledgments():
    r = captured('imodem-x2-downstream-irq-boundary-20261027-100335')
    observer = r['analog']['rom_link_errors']
    boundary, = inspect(observer)
    frame, = [f for f in boundary['pre_hdlc_events'] if f['ring_is_subsequence']]
    assert frame['crc_valid'] and frame['octets_missing_from_ring'] == 4
    event = next(e for e in observer['events'] if 'cpu_dsp_timeline' in e)
    rows = event['cpu_dsp_timeline']
    assert len(rows) == 2048
    assert any(e['kind'] == 2 and e['port_or_vector'] == 0x1a for e in rows)
    assert any(e['kind'] == 3 for e in rows)
    assert any(e['kind'] == 6 and e['port_or_vector'] == 12 for e in rows)
    assert any(e['kind'] == 7 and e['port_or_vector'] == 12 for e in rows)


@pytest.mark.parametrize('name', ['imodem-x2-interrupt-poll256-20261027-100938',
                                  'imodem-x2-interrupt-poll64-20261027-101214'])
def test_finer_interrupt_polling_does_not_hide_trailing_stalls_or_missing_control_octets(name):
    r = captured(name)
    assert r['imodem']['link_errors']['bler_count'] == 0
    boundary, = inspect(r['analog']['rom_link_errors'])
    frames = [f for f in boundary['pre_hdlc_events'] if f['ring_is_subsequence']]
    frame, = frames
    assert frame['crc_valid'] and frame['octets_missing_from_ring'] == 1
    window = r['traffic']['windows']['analog']
    assert max(window['max_gap_frames'], window['elapsed_frames'] - window['last_rx_frame']) > 50


def test_48000_connect_is_real_but_two_valid_input_frames_merge_after_output_loss():
    r = captured('imodem-x2-ceiling48000-20261027-101919')
    assert 'CONNECT 48000/ARQ/x2' in r['traffic']['connect']['analog']
    assert r['imodem']['link_errors']['bler_count'] == 0
    boundary, = inspect(r['analog']['rom_link_errors'])
    frames = boundary['pre_hdlc_events']
    assert len(frames) == 2 and all(f['crc_valid'] for f in frames)
    first, second = [bytes.fromhex(f['complete_hex']) for f in frames]
    ring = bytes.fromhex(boundary['ring_hex'])
    assert ring == first + second[1:]
    assert boundary['bank_match']['octets'] == len(ring) == 23
    assert boundary['bank_match']['following_token'] == 0xff00
    assert boundary['ring_crc_matches_firmware']


def test_fixed40000_without_analog_connect_is_not_traffic_evidence():
    r = captured('imodem-x2-ceiling40000-20261027-101839')
    assert not r['traffic']['connect']['analog']
    assert r['traffic_failure'] == 'call cleared before the traffic window completed'
