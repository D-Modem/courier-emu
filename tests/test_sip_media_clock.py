from collections import deque
import threading
import time
from types import SimpleNamespace

import pytest

from courier_emu.sip import SipSession
from courier_emu.rtp import RtpPlayout, RtpReceiveStats


def clocked_session():
    session = object.__new__(SipSession)
    session.state = 'connected'
    session.closed = False
    session.error = ''
    session.codewords = True
    session._tx_codewords = deque()
    session._tx_audio = deque()
    session._rtp_sequence = 0
    session._rtp_timestamp = 0
    session._rtp_ssrc = 1
    session._next_rtp_at = 0
    session._rtp_lock = threading.RLock()
    session._rtp_clock_thread = None
    session._rtp_clock_stop = threading.Event()
    session._rtp_clock_wake = threading.Event()
    session._rtp_tx_primed = False
    session._rtp_tx_buffer_samples = 480
    session._rtp_playout = RtpPlayout()
    session._rtp_rx_stats = RtpReceiveStats()
    session._rx_audio = deque()
    session._rx_codewords = deque()
    session.rtp_packets_received = session.rtp_octets_received = 0
    session.remote_rtp = ('127.0.0.1', 5000)
    session.rtp_packets_sent = session.rtp_octets_sent = 0
    session.preanswer_samples_discarded = 0
    return session


def test_media_clock_sends_continuous_codewords_while_producer_is_paused():
    session = clocked_session()
    packets = []
    complete = threading.Event()

    def send(packet, peer):
        packets.append((time.monotonic(), packet))
        if len(packets) == 4:
            complete.set()

    def empty_receive(size):
        raise BlockingIOError

    session.rtp_socket = SimpleNamespace(sendto=send, recvfrom=empty_receive, close=lambda: None)
    session.socket = SimpleNamespace(close=lambda: None)
    source = bytes(i % 256 for i in range(640))
    session.enable_media_clock()
    try:
        # Only one producer call. The sender must continue independently and
        # must not flush the queued packets as one scheduler catch-up burst.
        session.send_pcmu(source)
        assert complete.wait(2)
        assert b''.join(packet[12:] for _, packet in packets) == source
        assert [int.from_bytes(packet[4:8], 'big') for _, packet in packets] == [0, 160, 320, 480]
        assert packets[-1][0] - packets[0][0] >= 0.05
    finally:
        session.state = 'idle'
        session.close()
    assert not session._rtp_clock_thread.is_alive()


def test_media_clock_primes_before_starting_and_keeps_every_queued_octet():
    session = clocked_session()
    # Run the clock decision synchronously to check startup without wall-clock
    # sleeps. A marker enables its playout buffering branch.
    session._rtp_clock_thread = object()
    packets = []
    session.rtp_socket = SimpleNamespace(sendto=lambda packet, peer: packets.append(packet))
    session._tx_codewords.extend(b'\x12' * 160)
    session._flush_rtp_locked(10)
    assert packets == []
    session._tx_codewords.extend(b'\x34' * 320)
    session._flush_rtp_locked(11)
    assert [packet[12:] for packet in packets] == [b'\x12' * 160]
    assert bytes(session._tx_codewords) == b'\x34' * 320


def test_media_clock_reports_real_production_outage_without_fabricating_audio(monkeypatch):
    session = clocked_session()
    session._rtp_clock_thread = object()
    packets = []
    now = [10.0]
    monkeypatch.setattr('courier_emu.sip.time.monotonic', lambda: now[0])
    session.rtp_socket = SimpleNamespace(sendto=lambda packet, peer: packets.append(packet))
    session._tx_codewords.extend(b'\x91' * 480)
    for instant in (10.0, 10.021, 10.041, 10.061, 10.081):
        now[0] = instant
        session._flush_rtp_locked(instant)
    assert len(packets) == 3
    assert b''.join(p[12:] for p in packets) == b'\x91' * 480
    assert session._rtp_tx_stats.rebuffer_events == 1
    assert session._rtp_tx_stats.max_packet_gap_ms == pytest.approx(21)
    assert session._rtp_tx_stats.max_queue_samples == 480
    assert session._rtp_tx_stats.max_packets_per_flush == 1


def test_subpacket_producer_jitter_does_not_rebuild_startup_reserve(monkeypatch):
    session = clocked_session()
    session._rtp_clock_thread = object()
    packets = []
    now = [10.0]
    monkeypatch.setattr('courier_emu.sip.time.monotonic', lambda: now[0])
    session.rtp_socket = SimpleNamespace(sendto=lambda packet, peer: packets.append(packet))
    session._tx_codewords.extend(b'\x91' * 480)
    for instant in (10.0, 10.02, 10.04, 10.061):
        now[0] = instant
        session._flush_rtp_locked(instant)
    assert session._rtp_tx_primed
    assert session._rtp_tx_stats.rebuffer_events == 0
    # The next real packet is five milliseconds late, not a 150-ms outage.
    session._tx_codewords.extend(b'\x42' * 160)
    now[0] = 10.065
    session._flush_rtp_locked(now[0])
    assert [p[12:] for p in packets] == [b'\x91' * 160] * 3 + [b'\x42' * 160]
    assert [int.from_bytes(p[4:8], 'big') for p in packets] == [0, 160, 320, 480]
    assert session._rtp_tx_stats.rebuffer_events == 0
    assert session._next_rtp_at == pytest.approx(10.08)


def test_grace_never_sends_or_discards_partial_packets(monkeypatch):
    session = clocked_session()
    session._rtp_clock_thread = object()
    session._rtp_tx_primed = True
    session._next_rtp_at = 10
    session._tx_codewords.extend(b'\x12' * 80)
    packets = []
    session.rtp_socket = SimpleNamespace(sendto=lambda packet, peer: packets.append(packet))
    session._flush_rtp_locked(10.005)
    assert not packets
    assert bytes(session._tx_codewords) == b'\x12' * 80
    assert session._rtp_tx_primed
    session._flush_rtp_locked(10.025)
    assert not session._rtp_tx_primed
    assert session._rtp_tx_stats.rebuffer_events == 1
    assert not packets
    assert bytes(session._tx_codewords) == b'\x12' * 80


def test_analog_transmit_backlog_fails_before_deque_discards_samples():
    session = clocked_session()
    session.codewords = False
    session._tx_audio = deque([1, 2], maxlen=3)
    with pytest.raises(RuntimeError, match='refusing silent sample loss'):
        session.send_audio([3, 4])
    assert list(session._tx_audio) == [1, 2]
