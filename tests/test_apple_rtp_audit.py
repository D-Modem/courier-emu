import json

from tools.audit_apple_rtp import compare, compare_source, load_stream


def stream(tmp_path, name, order, alter=None):
    rows = []
    audio = bytearray()
    for i in order:
        payload = bytes([10 + i]) * 160
        if alter == i:
            payload = b'\xff' + payload[1:]
        audio.extend(payload)
        rows.append(dict(time=1 + i * .02, sequence=(65535 + i) & 65535,
                         timestamp=(0xfffffff0 + 160 * i) & 0xffffffff, bytes=160))
    path = tmp_path / (name + '.json')
    path.write_text(json.dumps(rows))
    path.with_suffix('.g711').write_bytes(audio)
    return load_stream(path)


def test_timestamp_order_restores_reordered_packets_across_wrap(tmp_path):
    s = stream(tmp_path, 'reordered', [0, 2, 1])
    assert s['ordered_audio'] == b'\x0a' * 160 + b'\x0b' * 160 + b'\x0c' * 160


def test_sparse_network_capture_does_not_implicate_correct_dsp_samples(tmp_path):
    s = stream(tmp_path, 'sparse', [0, 2])
    source = b'\xff' * 111 + b'\x0a' * 160 + b'\x0b' * 160 + b'\x0c' * 160
    report = compare_source(s, source)
    assert report['captured_packets_exact_in_dsp_tx']
    assert report['mismatching_captured_packets'] == 0
    assert report['uncaptured_timestamp_samples'] == 160
    assert report['source_sample_offset'] == 111


def test_pbx_comparison_detects_payload_mutation_not_arrival_reordering(tmp_path):
    upstream = stream(tmp_path, 'upstream', [0, 1, 2])
    downstream = stream(tmp_path, 'downstream', [0, 2, 1], alter=1)
    report = compare(upstream, downstream)
    assert report['shared_packets'] == 3
    assert report['altered_payload_packets'] == 1
    assert report['only_upstream_packets'] == 0
