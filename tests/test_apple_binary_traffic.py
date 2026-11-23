import io
import json
from pathlib import Path
import struct
from types import SimpleNamespace
import zlib

import pytest

from courier_emu.isdn_console import interactive_pump
from courier_emu.cli import build_parser
from tools.apple_traffic import HEADER, ReceiveStream, check_window, record, verify_saved


def test_binary_records_cover_all_octets_and_change_sequence_and_role():
    value = record('A', 0)
    body = value[HEADER.size:-4]
    assert set(body) == set(range(256))
    assert HEADER.unpack(value[:HEADER.size]) == (b'CEMU', b'A', 0, 256)
    assert struct.unpack('<I', value[-4:])[0] == zlib.crc32(value[:-4])
    assert value != record('A', 1) != record('I', 1)


def test_receive_verifies_every_partial_prefix_and_all_record_boundaries():
    stream = ReceiveStream('A')
    stream.start(0)
    data = b''.join(record('A', i) for i in range(12))
    for i in range(0, len(data), 17):
        stream.feed(data[i:i+17], .001 * i)
    assert stream.records == 12
    assert stream.bytes == len(data)
    assert not stream.pending and not stream.error


@pytest.mark.parametrize('mutation', ['fold-high-bit', 'drop-nul', 'lf-to-cr', 'duplicate', 'reorder'])
def test_corruption_is_not_normalized_or_resynchronized(mutation):
    data = record('I', 0)
    if mutation == 'fold-high-bit': data = bytes(b & 127 for b in data)
    elif mutation == 'drop-nul': data = data.replace(b'\0', b'')
    elif mutation == 'lf-to-cr': data = data.replace(b'\n', b'\r')
    elif mutation == 'duplicate': data += data
    elif mutation == 'reorder': data = record('I', 1)
    stream = ReceiveStream('I')
    stream.start(0)
    stream.feed(data, 1)
    assert stream.error


def terminal(monkeypatch, incoming, outgoing, *, binary=True):
    data = [outgoing]
    sent, stopped = [], []
    monkeypatch.setattr('courier_emu.isdn_console.select.select', lambda *a: ([1], [], []))
    monkeypatch.setattr('courier_emu.isdn_console.os.read', lambda *a: data.pop(0))
    sink = io.BytesIO() if binary else io.StringIO()
    machine = SimpleNamespace(instructions=0, with_dsp=True, _live_bearer=lambda: True,
        dte_framing=lambda: 0, take_serial=lambda: incoming,
        send_serial=sent.append, stop=stopped.append)
    pump = interactive_pump(after=0, input_stream=SimpleNamespace(fileno=lambda: 1),
                            output_stream=sink, binary_io=binary)
    pump(machine)
    return sink.getvalue(), sent, stopped


def test_binary_console_preserves_all_bytes_without_echo_or_detach(monkeypatch):
    data = bytes(range(256))
    output, sent, stopped = terminal(monkeypatch, data, data)
    assert output == data  # Not ASCII replacement and not local echo.
    assert sent == [data]  # Includes LF, Ctrl-], high bytes, XON/XOFF and NUL.
    assert stopped == []


def test_binary_console_eof_stops_without_an_in_band_escape(monkeypatch):
    output, sent, stopped = terminal(monkeypatch, b'', b'')
    assert not output and not sent
    assert stopped == ['binary terminal EOF']


def test_text_console_keeps_legacy_lf_and_detach_behavior(monkeypatch):
    output, sent, stopped = terminal(monkeypatch, b'OK\r\n', b'A\n\x1dB', binary=False)
    assert sent == [b'A\r']
    assert stopped == ['detached']


def test_cli_binary_terminal_is_explicit():
    args = build_parser().parse_args(['isdn-run', 'Ie030002.nac', '--terminal', '--terminal-binary'])
    assert args.terminal and args.terminal_binary
    assert not build_parser().parse_args(['isdn-run', 'Ie030002.nac', '--terminal']).terminal_binary


def saved(tmp_path):
    metadata = dict(seconds=60, binary=True, record_size=256, start=100, end=160,
                    sent_records=dict(apple=12, imodem=12),
                    window=dict(elapsed_seconds=60.1,
                        apple=dict(records=12, error=None, max_gap_seconds=5, open_gap_seconds=.1),
                        imodem=dict(records=12, error=None, max_gap_seconds=5, open_gap_seconds=.1)))
    events = []
    for i in range(12):
        now = 105 + i * 5
        for side in ('apple', 'imodem'):
            events.append(dict(event='sent', side=side, time=now-.1, records=i+1))
        for side in ('apple', 'imodem'):
            events.append(dict(event='received', side=side, time=now, records=i+1))
    (tmp_path / 'events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))
    for source, role, destination in [('apple','A','imodem'), ('imodem','I','apple')]:
        data = b''.join(record(role, i) for i in range(12))
        (tmp_path / f'{source}-sent.bin').write_bytes(data)
        (tmp_path / f'{destination}-received.bin').write_bytes(data)
    (tmp_path / 'traffic.json').write_text(json.dumps(metadata))
    return metadata


def test_offline_verification_regenerates_both_sources(tmp_path):
    saved(tmp_path)
    result = verify_saved(tmp_path)
    assert result['apple']['payload_bytes'] == result['imodem']['payload_bytes'] == 3072


def test_offline_verifier_rejects_identical_corruption_in_sent_and_received(tmp_path):
    saved(tmp_path)
    for name in ('apple-sent.bin', 'imodem-received.bin'):
        path = tmp_path / name
        path.write_bytes(bytes(b & 127 for b in path.read_bytes()))
    with pytest.raises(AssertionError, match='source differs'):
        verify_saved(tmp_path)


def test_offline_verifier_rejects_missing_tail_and_inadequate_duration(tmp_path):
    metadata = saved(tmp_path)
    path = tmp_path / 'apple-received.bin'
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(AssertionError, match='receive stream differs'):
        verify_saved(tmp_path)
    metadata['window']['elapsed_seconds'] = 59
    with pytest.raises(AssertionError, match='observation'):
        verify_saved(tmp_path, metadata=metadata)


def test_gap_at_end_of_window_is_a_stall_even_with_matching_bytes(tmp_path):
    metadata = saved(tmp_path)
    metadata['window']['apple']['open_gap_seconds'] = 6
    with pytest.raises(AssertionError, match='stalled'):
        check_window(metadata['window'], 60)
