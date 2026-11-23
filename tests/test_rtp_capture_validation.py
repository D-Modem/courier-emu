import json
from pathlib import Path

import pytest

from tools.capture_apple_sip import capture_stats, main as capture_main, on_hook
from tools.compare_rtp_captures import compare_streams
from tools.replay_rtp_playout import replay
from courier_emu.cli import build_parser
from courier_emu.sip import SipConfig, SipSession


def stream(tmp_path, packets):
    path = tmp_path / 'stream.json'
    path.write_text(json.dumps([
        dict(time=1000 + at, sequence=seq, timestamp=ts, bytes=len(data))
        for at, seq, ts, data in packets]))
    path.with_suffix('.g711').write_bytes(b''.join(row[3] for row in packets))
    return path


def test_replay_retains_real_hole_without_shortening_timeline(tmp_path):
    path = stream(tmp_path, [(0, 1, 0, b'A' * 160), (.04, 3, 320, b'C' * 160)])
    result = replay(path)
    assert result['timestamp_span_samples'] == 480
    assert result['capture_missing_samples'] == result['playout_missing_samples_in_span'] == 160
    assert result['captured_samples_preserved']


def test_replay_exposes_insufficient_delay_for_reordered_packet(tmp_path):
    path = stream(tmp_path, [(0, 1, 0, b'A' * 160), (.04, 3, 320, b'C' * 160),
                             (.12, 2, 160, b'B' * 160)])
    short = replay(path)
    assert short['capture_missing_samples'] == 0
    assert short['playout_missing_samples_in_span'] == 160
    assert not short['captured_samples_preserved']
    longer = replay(path, delay_ms=200)
    assert longer['captured_samples_preserved']
    assert longer['playout_missing_samples_in_span'] == 0


def test_replay_poll_batching_is_explicit(tmp_path):
    path = stream(tmp_path, [(i * .02, i, i * 160, bytes([i]) * 160) for i in range(30)])
    assert replay(path)['captured_samples_preserved']
    assert not replay(path, poll_ms=100)['captured_samples_preserved']
    assert replay(path, poll_ms=100, delay_ms=200)['captured_samples_preserved']


def test_replay_reordered_initial_packet_and_timestamp_wrap(tmp_path):
    path = stream(tmp_path, [(0, 0, 144, b'B' * 160),
                             (.01, 65535, 0xfffffff0, b'A' * 160)])
    assert replay(path)['captured_samples_preserved']


def test_replay_rejects_conflicting_payload_and_truncated_extraction(tmp_path):
    path = stream(tmp_path, [(0, 1, 0, b'A' * 160), (.01, 1, 0, b'B' * 160)])
    with pytest.raises(ValueError, match='conflicting'):
        replay(path)
    path.with_suffix('.g711').write_bytes(b'A')
    with pytest.raises(ValueError, match='truncated'):
        replay(path)


def test_capture_counters_require_nonempty_capture_and_explicit_zero_drops():
    assert capture_stats('10 packets captured\n12 packets received by filter\n0 packets dropped by kernel\n')[
        'verified_no_kernel_drops']
    for text in ('', '0 packets captured\n0 packets dropped by kernel\n',
                 '10 packets captured\n1 packets dropped by kernel\n', '10 packets captured\n'):
        assert not capture_stats(text)['verified_no_kernel_drops']


@pytest.mark.parametrize('result', [
    {'returncode': 1, 'stdout': ''}, {'returncode': 0, 'stdout': 'bad'},
    {'returncode': 0, 'stdout': '{}'}, {'returncode': 0, 'stdout': '{"hook":1}'},
])
def test_hook_gate_fails_closed(result):
    assert not on_hook(result)


def test_capture_preflight_missing_modem_never_launches_call(tmp_path, monkeypatch):
    from tools import capture_apple_sip as tool
    monkeypatch.setattr(tool.os, 'umask', lambda value: 0o022)
    class Probe:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def connect(self, target): pass
        def getsockname(self): return ('10.0.0.1', 1234)
    monkeypatch.setattr(tool.socket, 'socket', lambda *args: Probe())
    monkeypatch.setattr(tool.socket, 'gethostbyname', lambda host: '10.0.0.2')
    monkeypatch.setattr(tool, 'run', lambda command, **kw:
                        dict(command=command, returncode=1, stdout='', stderr='missing modem'))
    monkeypatch.setattr(tool.subprocess, 'Popen', lambda *a, **kw: pytest.fail('must not launch'))
    out = tmp_path / 'preflight'
    monkeypatch.setattr('sys.argv', ['capture', '--output', str(out), '--run-call'])
    assert capture_main() == 2
    assert json.loads((out / 'preflight.json').read_text())['modem']['returncode'] == 1
    assert out.stat().st_mode & 0o777 == 0o700
    assert not (out / 'call').exists()


@pytest.mark.parametrize('value', ['-1', '1001'])
def test_cli_rejects_unbounded_receive_delay(value):
    with pytest.raises(SystemExit):
        build_parser().parse_args(['isdn-run', 'Ie030002.nac', '--bri-sip-rtp-delay-ms', value])


def test_cli_exposes_separate_bearer_reserve_and_rtp_deadline():
    args = build_parser().parse_args(['isdn-run', 'Ie030002.nac',
        '--bri-sip-buffer-ms', '200', '--bri-sip-rtp-delay-ms', '200'])
    assert args.bri_sip_buffer_ms == args.bri_sip_rtp_delay_ms == 200
    assert build_parser().parse_args(['isdn-run', 'Ie030002.nac']).bri_sip_rtp_delay_ms == 60


def test_session_validates_delay_before_opening_sockets(monkeypatch):
    monkeypatch.setattr('courier_emu.sip.socket.socket', lambda *a, **kw: pytest.fail('socket opened'))
    with pytest.raises(ValueError, match='delay'):
        SipSession(SipConfig(server='localhost', receive_delay_samples=16000))


def test_capture_comparison_separates_interior_absence_and_boundaries():
    def make(indices):
        return dict(packets={(i, (0xfffffff0 + i * 160) % 2**32): (i * .02, b'A' * 160)
                             for i in indices},
                    arrival_rows=[dict(timestamp=(0xfffffff0 + indices[0] * 160) % 2**32)])
    a, b = make([0, 1, 2, 3, 4]), make([1, 3])
    result = compare_streams(a, b)
    assert result['shared_packets'] == 2
    assert result['upstream_only_boundary_packets'] == 2
    assert result['upstream_only_interior'] == [dict(sequence=2, timestamp=304, samples=160)]
    assert result['shared_payload_mismatches'] == 0
    key = next(iter(b['packets']))
    b['packets'][key] = (1, b'B' * 160)
    assert compare_streams(a, b)['shared_payload_mismatches'] == 1


def test_capture_comparison_does_not_invent_loss_without_shared_boundary():
    a = dict(packets={(1, 0): (0, b'A')}, arrival_rows=[dict(timestamp=0)])
    b = dict(packets={(2, 160): (0, b'A')}, arrival_rows=[dict(timestamp=160)])
    result = compare_streams(a, b)
    assert result['shared_packets'] == 0
    assert result['upstream_only_interior'] == []
    assert result['downstream_only_packets'] == 1


def test_saved_reordering_regression_if_capture_available():
    root = Path(__file__).resolve().parents[1]
    path = root / ('artifacts/apple-courier-sip/bell103-packet-audit-retry/rtp/'
                   '10.69.220.8_62620--192.168.88.122_14366--a4496513.json')
    if not path.exists():
        pytest.skip('optional saved hardware capture not installed')
    assert replay(path)['playout_missing_samples_in_span'] == 320
    assert replay(path, delay_ms=200)['captured_samples_preserved']
