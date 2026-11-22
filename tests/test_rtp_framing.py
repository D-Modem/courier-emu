from collections import deque
import threading
import pytest

from courier_emu.rtp import RtpPlayout, RtpReceiveStats, parse_rtp
from courier_emu.sip import SipSession


def packet(sequence=1, timestamp=0, ssrc=7, payload=b'\x91' * 160, flags=0x80):
    return (bytes([flags, 0x80]) + sequence.to_bytes(2, 'big')
            + timestamp.to_bytes(4, 'big') + ssrc.to_bytes(4, 'big') + payload)


def test_header_csrc_extension_and_padding_are_not_modem_audio():
    payload = b'\x91\x23\x45'
    raw = packet(flags=0xb2, payload=(b'CSRC' * 2 + b'\xbe\xde\x00\x01'
                                     + b'EXTN' + payload + b'\x00\x00\x03'))
    parsed = parse_rtp(raw)
    assert parsed.payload == payload
    assert parsed.payload_type == 0  # Marker bit does not change the codec.
    assert parsed.sequence == 1
    assert parsed.ssrc == 7


@pytest.mark.parametrize('raw', [
    b'', b'\x80' * 11, packet(flags=0x40),
    packet(flags=0x81, payload=b''),
    packet(flags=0x90, payload=b'\xbe\xde\x00'),
    packet(flags=0x90, payload=b'\xbe\xde\x00\x02abcd'),
    packet(flags=0xa0, payload=b'abc\x00'),
    packet(flags=0xa0, payload=b'abc\x09'),
    packet(flags=0xb0, payload=b'\xbe\xde\x00\x00\x05'),
])
def test_malformed_packet_is_rejected_not_played(raw):
    with pytest.raises(ValueError):
        parse_rtp(raw)


def test_wraparound_is_contiguous_and_duplicate_does_not_advance_audio():
    stats = RtpReceiveStats()
    first = parse_rtp(packet(sequence=65535, timestamp=0xfffffff0))
    second = parse_rtp(packet(sequence=0, timestamp=144))
    assert stats.observe(first, 1)
    assert not stats.observe(first, 1.01)
    assert stats.observe(second, 1.02)
    assert stats.duplicates == 1
    assert stats.sequence_gap_events == stats.timestamp_jump_events == 0


def test_reordering_is_not_reported_as_proven_packet_loss():
    stats = RtpReceiveStats()
    for seq, ts, now in [(22, 0, 1), (25, 480, 1.1), (23, 160, 1.101),
                         (24, 320, 1.102), (26, 640, 1.12)]:
        assert stats.observe(parse_rtp(packet(seq, ts)), now)
    assert stats.sequence_gap_events == 1
    assert stats.reordered_packets == 2
    assert stats.max_arrival_gap_ms == pytest.approx(100)
    assert stats.max_timestamp_gap_samples == 320
    stats.reset_stream()
    assert stats.observe(parse_rtp(packet(22, 0)), 3)
    assert stats.ssrc_changes == 0
    assert stats.sequence_gap_events == 1  # Diagnostic totals survive hangup.


class Socket:
    def __init__(self, packets=()):
        self.packets = deque(packets)

    def recvfrom(self, size):
        if not self.packets:
            raise BlockingIOError
        return self.packets.popleft()[:size], ('127.0.0.1', 5000)


@pytest.mark.parametrize('size', [160, 3000])
@pytest.mark.parametrize('codewords', [True, False])
def test_session_strips_headers_and_suppresses_duplicate_audio(size, codewords, monkeypatch):
    clock = [1.0]
    monkeypatch.setattr('courier_emu.sip.time.monotonic', lambda: clock[0])
    raw = packet(flags=0x90, payload=b'\xbe\xde\x00\x01EXTN' + b'\x91' * size)
    session = object.__new__(SipSession)
    session.closed = False
    session._rtp_lock = threading.RLock()
    session.socket = Socket()
    session.rtp_socket = Socket([b'bad', raw, raw, packet(2, size, payload=b'\x92' * 160)])
    session._rtp_rx_stats = RtpReceiveStats()
    session._rtp_playout = RtpPlayout()
    session.remote_rtp = ('127.0.0.1', 5000)
    session.payload_type = 0
    session.codewords = codewords
    session._rx_codewords = deque()
    session._rx_audio = deque()
    session.rtp_packets_received = session.rtp_octets_received = 0
    session.state = 'connected'
    session._flush_rtp = lambda now: None
    session.poll()
    assert session.receive_pcmu() == b''
    clock[0] = 1.06 + (size + 160) / 8000 + 0.000001
    session.poll()
    expected = b'\x91' * size + b'\x92' * 160
    if codewords:
        assert session.receive_pcmu() == expected
    else:
        assert session.receive_audio() == [session._decode(v) for v in expected]
    assert session.rtp_packets_received == 3  # Actual valid media datagrams.
    assert session.rtp_octets_received == 2 * size + 160  # Duplicate is not replayed.
    assert session._rtp_rx_stats.invalid_packets == 1
    assert session._rtp_rx_stats.duplicates == 1
