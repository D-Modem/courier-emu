import random

import pytest

from tools.inspect_quad_pcm_ring import PCS, analyze, compare_octets


def trace(endpoint, *, skip_tx_write=None, skip_rx_read=None):
    rx_store, rx_load, tx_store, tx_load = PCS[endpoint]
    events = []
    for sample in range(24):
        address = 0xbd0 + 2 * (sample % 8)
        for pc, cell in [(rx_store, address), (tx_load, address + 1),
                         (rx_load, address), (tx_store, address + 1)]:
            if pc == tx_store and sample == skip_tx_write:
                continue
            if pc == rx_load and sample == skip_rx_read:
                continue
            events.append(dict(pc=pc, address=cell, value=sample, instruction=len(events)))
    return events


@pytest.mark.parametrize('endpoint', PCS)
def test_pcm_ring_accepts_ordered_one_for_one_accesses(endpoint):
    result = analyze(trace(endpoint), endpoint)
    assert result['ok']
    assert all(result['counts'][role] == 24
               for role in ('rx_write', 'rx_read', 'tx_write', 'tx_read'))


def test_pcm_ring_detects_a_transmitted_slot_without_fresh_data():
    result = analyze(trace('quad', skip_tx_write=0))
    assert not result['ok']
    assert result['counts']['tx_stale_read'] == 1


def test_pcm_ring_detects_overwritten_receive_samples():
    result = analyze(trace('imodem', skip_rx_read=8), 'imodem')
    assert not result['ok']
    assert result['counts']['rx_overwritten_samples'] == 1


def test_transport_detects_an_idle_inserted_inside_an_overlapping_capture():
    source = random.Random(4).randbytes(512)
    received = source[80:200] + b'\xff' + source[200:400]
    result = compare_octets(source, received)
    assert result['aligned'] and not result['ok']
    assert result['matched_samples'] == 320
    assert result['slips'] == [dict(kind='insert', tx_index=200, rx_index=120,
                                    transmitted='', received='ff')]


def test_transport_accepts_byte_exact_overlap_with_different_capture_edges():
    source = random.Random(4).randbytes(512)
    result = compare_octets(source[80:400], source)
    assert result['ok'] and result['matched_samples'] == 320


def test_transport_does_not_hide_corruption_at_the_end_as_capture_padding():
    source = random.Random(4).randbytes(512)
    received = source[:400] + bytes(value ^ 1 for value in source[400:])
    assert not compare_octets(source, received)['ok']


def test_transport_without_a_shared_anchor_is_not_a_pass():
    assert not compare_octets(b'\x01' * 100, b'\x02' * 100)['ok']
