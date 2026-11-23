import json
from pathlib import Path

import pytest

from tools.imodem_link_errors import crc16_lapm
from tools.imodem_receive_boundary import hdlc_events, inspect

FLAG = [0, 1, 1, 1, 1, 1, 1, 0]


def stuffed(data):
    bits, ones = [], 0
    for byte in data:
        for shift in range(8):
            bit = byte >> shift & 1
            bits.append(bit)
            ones = ones + 1 if bit else 0
            if ones == 5:
                bits.append(0)
                ones = 0
    return bits


def test_all_octets_and_fcs_replay_through_flags_and_stuffing():
    data = bytes(range(256))
    data += (crc16_lapm(data) ^ 0xffff).to_bytes(2, 'little')
    frame, = hdlc_events(FLAG * 3 + stuffed(data) + FLAG * 3)
    assert frame['complete_hex'] == data.hex()
    assert frame['crc_valid'] and frame['kind'] == 'frame'
    assert frame['bit_length'] == len(data) * 8


def test_unaligned_close_is_not_padded_into_an_invented_full_octet():
    frame, = hdlc_events(FLAG + stuffed(b'abc') + [1, 0, 1] + FLAG)
    assert frame['kind'] == 'unaligned'
    assert frame['bit_length'] == 27
    assert frame['complete_hex'] == b'abc'.hex()
    assert not frame['crc_valid']


def test_abort_retains_only_complete_prefix_and_ignores_unbounded_tail():
    frame, = hdlc_events(FLAG + stuffed(b'abc') + [1] * 9 + [0] + stuffed(b'ignored'))
    assert frame['kind'] == 'abort'
    assert frame['complete_hex'] == b'abc'.hex()
    assert not frame['crc_valid']
    assert not hdlc_events(stuffed(b'no opening flag'))
    assert not hdlc_events(FLAG + stuffed(b'no closing boundary'))


def test_snapshot_rejects_incoherent_or_wrong_page_rows():
    report = {'events': [{'phase': 'traffic', 'dsp_bank_history': [],
                          'dsp_bit_capture': {'rows': [[0, 0, 3, 7, 0, 8]]}}]}
    with pytest.raises(ValueError, match='unsupported coherent'):
        inspect(report)


def test_saved_coherent_bits_and_bank_words_locate_a_malformed_frame_before_cpu_deframing():
    path = Path('artifacts/imodem-x2-coherent-bits-boundary-20261027-083514/link-errors.json')
    if not path.exists():
        pytest.skip('optional saved local call')
    report = inspect(json.loads(path.read_text()))
    traffic = next(e for e in report if e['phase'] == 'traffic')
    assert traffic['bank_match']['octets'] == len(bytes.fromhex(traffic['ring_hex'])) == 44
    assert traffic['bank_match']['following_token'] == 0xfe00
    assert traffic['ring_crc_matches_firmware']
    frame, = [e for e in traffic['pre_hdlc_events'] if e['matches_ring_prefix']]
    assert frame['kind'] == 'unaligned' and frame['bit_length'] == 350
    assert len(bytes.fromhex(frame['complete_hex'])) == 43
    assert not frame['crc_valid']


def test_saved_factory_level_removes_upstream_blers_but_preserves_downstream_failure():
    names = ['imodem-x2-stored-level-countercontrol-20261027-082959',
             'imodem-x2-s39-factory-repeat-20261027-082202',
             'imodem-x2-s39-factory-60s-20261027-082324']
    roots = [Path('artifacts') / name for name in names]
    if not all((p / 'result.json').exists() for p in roots):
        pytest.skip('optional saved local calls')
    stored, corrected, long = [json.loads((p / 'result.json').read_text()) for p in roots]
    assert stored['analog']['peek']['004b5'] == '00'
    assert stored['analog']['dsp_bridge']['dsp_cells']['00392'] == '7cff'
    assert stored['imodem']['link_errors']['bler_count'] == 246
    assert not stored['traffic_verified']
    for result in (corrected, long):
        assert result['analog']['peek']['004b5'] == '08'
        assert result['analog']['dsp_bridge']['dsp_cells']['00392'] == '2fd6'
        assert result['imodem']['link_errors']['bler_count'] == 0
        assert not result['imodem']['link_errors']['counts']
    assert corrected['traffic_verified']
    assert not long['traffic_verified']  # Never turn the long-run failure into a pass.
    assert long['traffic']['windows']['analog']['received_records'] == 7
    assert long['traffic']['windows']['imodem']['received_records'] == 42
