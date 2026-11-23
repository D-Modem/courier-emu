"""Separate-socket telemetry, with no USB, firmware or SIP side effects."""
import json
import socket
import threading
import time
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from tools.apple_traffic_telemetry import Client, Server, PLAYOUT_COUNTERS, collect, summarize


def sample(phase, now, missing=0, late=0):
    counters = dict.fromkeys(PLAYOUT_COUNTERS, 0)
    counters.update(missing_samples=missing, late_packets=late)
    return dict(phase=phase, time=now, playout=counters)


def test_snapshot_collects_only_passive_accessors():
    counters = dict.fromkeys(PLAYOUT_COUNTERS, 0)
    session = SimpleNamespace(_rtp_lock=nullcontext(),
        _rtp_playout=SimpleNamespace(status=lambda: counters.copy()),
        _rtp_rx_stats=SimpleNamespace(status=lambda: dict(sequence_gap_events=0)),
        rtp_octets_sent=160, rtp_octets_received=320, state='connected')
    machine = SimpleNamespace(bri=SimpleNamespace(media_peer=SimpleNamespace(session=session), call_state='active'),
        instructions=1234, _native_io=SimpleNamespace(clock_stats=lambda: dict(frames=42)),
        dte_framing=lambda: 0)
    result = collect(machine)
    assert result['playout'] == counters
    assert result['native_clock'] == dict(frames=42)
    assert result['rtp_octets_received'] == 320
    assert result['instructions'] == machine.instructions == 1234


def test_client_and_server_use_separate_socket_and_validate_identity():
    a, b = socket.socketpair()
    stop = threading.Event()
    server = Server(b, snapshot=lambda machine: dict(time=time.monotonic(), observed=machine))
    def serve():
        while not stop.is_set():
            server.poll('read-only')
            stop.wait(.001)
    thread = threading.Thread(target=serve)
    thread.start()
    try:
        client = Client(a)
        for phase in ['pre_traffic', 'traffic_end', 'post_hangup']:
            result = client.snapshot(phase)
            assert result['phase'] == phase and result['observed'] == 'read-only'
            assert result['request_started'] <= result['time'] <= result['response_received']
        assert [s['id'] for s in client.snapshots] == [0, 1, 2]
    finally:
        stop.set()
        thread.join(timeout=2)
        a.close()
        b.close()
    assert not thread.is_alive()


def test_snapshot_error_is_reported_not_a_fabricated_healthy_status():
    a, b = socket.socketpair()
    def bad(machine): raise RuntimeError('snapshot unavailable')
    server = Server(b, snapshot=bad)
    a.sendall(b'{"id":0,"phase":"pre_traffic"}\n')
    try:
        server.poll(None)
        response = json.loads(a.recv(4096))
        assert response == dict(id=0, phase='pre_traffic', error='snapshot unavailable')
        assert 'playout' not in response
    finally:
        a.close()
        b.close()


def test_partial_requests_are_not_processed_early():
    a, b = socket.socketpair()
    calls = []
    server = Server(b, snapshot=lambda machine: calls.append(machine) or dict(time=time.monotonic()))
    try:
        a.sendall(b'{"id":0,')
        server.poll('machine')
        assert calls == []
        a.sendall(b'"phase":"traffic_end"}\n')
        server.poll('machine')
        assert calls == ['machine']
        assert json.loads(a.recv(4096))['phase'] == 'traffic_end'
    finally:
        a.close()
        b.close()


def test_missing_response_is_bounded_and_recorded():
    a, b = socket.socketpair()
    client = Client(a)
    try:
        with pytest.raises(TimeoutError, match='response timed out'):
            client.snapshot('traffic_end', timeout=.01)
        assert client.snapshots == []
        b.close()
        assert client.capture('cleanup') is None
        assert client.errors[0]['phase'] == 'cleanup'
    finally:
        a.close()
        b.close()


@pytest.mark.parametrize('change', ['wrong-id', 'wrong-phase', 'outside-time'])
def test_client_rejects_wrong_or_stale_response(change):
    a, b = socket.socketpair()
    response = dict(id=0, phase='pre_traffic', time=time.monotonic())
    if change == 'wrong-id': response['id'] = 9
    elif change == 'wrong-phase': response['phase'] = 'traffic_end'
    else: response['time'] = -1
    b.sendall(json.dumps(response).encode() + b'\n')
    try:
        with pytest.raises(RuntimeError):
            Client(a).snapshot('pre_traffic', timeout=.1)
    finally:
        a.close()
        b.close()


def test_phase_summary_distinguishes_diagnostic_loss_from_traffic_loss():
    rows = [sample('pre_traffic', 1), sample('traffic_end', 21),
            sample('pre_diagnostics', 22), sample('imodem_diagnostics_done', 24, 1920, 12),
            sample('post_hangup', 30, 1920, 12)]
    intervals = summarize(rows)
    assert intervals[0]['playout_delta']['missing_samples'] == 0
    assert intervals[2]['playout_delta']['missing_samples'] == 1920
    assert intervals[2]['playout_delta']['late_packets'] == 12
    assert intervals[3]['playout_delta']['missing_samples'] == 0
    assert sum(r['playout_delta']['missing_samples'] for r in intervals) == 1920


@pytest.mark.parametrize('kind', ['reset', 'negative', 'nan-time', 'backwards-time', 'noninteger'])
def test_invalid_phase_evidence_fails_closed(kind):
    rows = [sample('pre_traffic', 1, 10), sample('traffic_end', 21, 10)]
    if kind == 'reset': rows[1]['playout']['missing_samples'] = 0
    elif kind == 'negative': rows[0]['playout']['missing_samples'] = -1
    elif kind == 'nan-time': rows[1]['time'] = float('nan')
    elif kind == 'backwards-time': rows[1]['time'] = 0
    else: rows[1]['playout']['late_packets'] = .5
    with pytest.raises(ValueError): summarize(rows)
