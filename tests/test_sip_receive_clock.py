"""Local UDP checks: RTP keeps flowing while the emulator does not poll."""
import socket
import struct
import time
from contextlib import contextmanager

import pytest

from courier_emu.sip import SipConfig, SipSession, ulaw_to_linear


@contextmanager
def session_pair(codewords=True):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as signalling, \
            socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as source:
        signalling.bind(('127.0.0.1', 0))
        source.bind(('127.0.0.1', 0))
        session = SipSession(SipConfig(server='127.0.0.1:%d' % signalling.getsockname()[1]))
        session.state = 'connected'
        session.codewords = codewords
        session.remote_rtp = source.getsockname()
        try:
            yield session, source
        finally:
            session.close()
        if session._rtp_clock_thread is not None:
            assert not session._rtp_clock_thread.is_alive()


def packet(index, payload):
    return struct.pack('!BBHII', 0x80, 0, index, index * 160, 7) + payload


def wait_for(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        assert time.monotonic() < deadline, 'media worker did not make progress'
        time.sleep(.002)


@pytest.mark.parametrize('codewords', [True, False])
def test_receive_playout_continues_without_emulator_poll(codewords):
    with session_pair(codewords) as (session, source):
        session.enable_media_clock()
        expected = bytearray()
        # Queue a known 300-ms timestamped train, then wait without any
        # emulator polls/consumption or queued TX. Prequeueing avoids making
        # this correctness test depend on cumulative sleep overshoot in a
        # loaded test runner (which is a real late sender, not a RX bug).
        for index in range(15):
            payload = bytes((index + offset) % 256 for offset in range(160))
            expected.extend(payload)
            source.sendto(packet(index, payload), ('127.0.0.1', session.rtp_port))
        queue = session._rx_codewords if codewords else session._rx_audio
        wait_for(lambda: len(queue) >= len(expected))
        result = session.receive_pcmu() if codewords else session.receive_audio()
        prefix = bytes(expected) if codewords else [ulaw_to_linear(v) for v in expected]
        assert result[:len(expected)] == prefix
        assert session._rtp_playout.late_packets == 0
        assert session._rtp_playout.missing_samples == len(result) - len(expected)
        assert session.rtp_packets_received == 15
        assert session.error == ''
        assert session.status()['rtp_rx_max_service_gap_ms'] > 0
        session.hangup()
        assert session.receive_pcmu() == b''
        assert session.receive_audio() == []
        assert session._rtp_playout.status()['buffered_samples'] == 0


def test_receive_backlog_fails_without_discarding_queued_audio():
    with session_pair() as (session, source):
        session._rtp_receive_capacity = 80
        session._rx_codewords.extend(b'kept')
        session.enable_media_clock()
        source.sendto(packet(0, b'A' * 160), ('127.0.0.1', session.rtp_port))
        wait_for(lambda: bool(session.error))
        assert 'receive backlog exceeds queue capacity' in session.error
        assert bytes(session._rx_codewords).startswith(b'kept')
        with pytest.raises(RuntimeError, match='receive backlog'):
            session.poll()
        with pytest.raises(RuntimeError, match='receive backlog'):
            session.receive_pcmu()
        with pytest.raises(RuntimeError, match='receive backlog'):
            session.send_pcmu(b'B')
        assert session.status()['rtp_media_error'] == session.error


def test_poll_does_not_compete_with_worker_for_receive_socket():
    with session_pair() as (session, source):
        # Marker selects worker ownership, without starting a real thread.
        marker = object()
        session._rtp_clock_thread = marker
        session._service_receive_rtp = lambda: pytest.fail('poll stole RTP ownership')
        try:
            session.poll()
        finally:
            session._rtp_clock_thread = None


def test_receive_service_gap_ignores_idle_time(monkeypatch):
    with session_pair() as (session, source):
        now = [10.0]
        monkeypatch.setattr('courier_emu.sip.time.monotonic', lambda: now[0])
        session._service_receive_rtp()
        now[0] = 10.1
        session._service_receive_rtp()
        assert session.status()['rtp_rx_max_service_gap_ms'] == pytest.approx(100)
        session.hangup()
        now[0] = 100
        session._service_receive_rtp()
        session.state = 'connected'
        now[0] = 200
        session._service_receive_rtp()
        assert session.status()['rtp_rx_max_service_gap_ms'] == pytest.approx(100)


def test_receive_socket_failure_is_propagated_and_worker_stops():
    with session_pair() as (session, source):
        session.rtp_socket.close()
        session.enable_media_clock()
        wait_for(lambda: bool(session.error))
        session._rtp_clock_thread.join(timeout=1)
        assert not session._rtp_clock_thread.is_alive()
        with pytest.raises(RuntimeError, match='RTP media worker failed'):
            session.poll()
        with pytest.raises(RuntimeError, match='RTP media worker failed'):
            session.receive_audio()
