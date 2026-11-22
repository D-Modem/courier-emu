"""Optional starvation recovery must not create another startup-reserve hold."""
from collections import deque
from types import SimpleNamespace
import pytest
from test_sip_media_clock import clocked_session


@pytest.mark.parametrize('codewords', [True, False])
def test_recovery_resumes_first_complete_packet_with_original_samples_and_timestamps(monkeypatch, codewords):
    s = clocked_session()
    s.codewords = codewords
    s._rtp_clock_thread = object()
    s._rtp_packet_recovery = True
    s._encode = lambda value: value  # Isolate scheduling from the G.711 codec.
    source = s._tx_codewords if codewords else s._tx_audio
    packets = []
    now = [10.0]
    monkeypatch.setattr('courier_emu.sip.time.monotonic', lambda: now[0])
    s.rtp_socket = SimpleNamespace(sendto=lambda packet, peer: packets.append(packet))
    def flush(at):
        now[0] = at
        s._flush_rtp_locked(at)
    # Recovery policy must not remove the original startup reserve.
    source.extend([0x91] * 160)
    flush(10.0)
    assert not packets
    source.extend([0x92] * 320)
    for at in [10.0, 10.02, 10.04, 10.061, 10.085]:
        flush(at)
    assert len(packets) == 3
    assert s._rtp_tx_recovering
    assert s._rtp_tx_stats.rebuffer_events == 1
    # Partial packets survive starvation. They must not be padded or sent.
    source.extend([0x12] * 80)
    flush(10.100)
    assert len(packets) == 3
    assert list(source) == [0x12] * 80
    source.extend([0x34] * 80)
    flush(10.105)
    assert len(packets) == 4  # Old policy would wait for 480 samples again.
    assert packets[-1][12:] == b'\x12' * 80 + b'\x34' * 80
    assert not source
    assert not s._rtp_tx_recovering
    assert s._next_rtp_at == pytest.approx(10.08)
    # Original deadlines survive recovery. Only genuinely overdue samples
    # catch up: the third added packet is not yet due at 10.110.
    source.extend([0x56] * 480)
    flush(10.110)
    assert len(packets) == 6
    assert list(source) == [0x56] * 160
    assert s._next_rtp_at == pytest.approx(10.12)
    flush(10.126)
    assert [int.from_bytes(p[4:8], 'big') for p in packets] == list(range(0, 1120, 160))
    assert [int.from_bytes(p[2:4], 'big') for p in packets] == list(range(7))
    assert b''.join(p[12:] for p in packets) == (b'\x91' * 160 + b'\x92' * 320
                                                + b'\x12' * 80 + b'\x34' * 80
                                                + b'\x56' * 480)
    assert s._rtp_tx_stats.max_packets_per_flush == 2
    assert s._next_rtp_at == pytest.approx(10.14)
    assert s._rtp_tx_stats.rebuffer_events == 1


def test_disconnect_restores_startup_reserve_after_recovery():
    s = clocked_session()
    s._rtp_clock_thread = object()
    s._rtp_packet_recovery = True
    s._rtp_tx_recovering = True
    s.state = 'idle'
    s._flush_rtp_locked(10)
    assert not s._rtp_tx_recovering
    s.state = 'connected'
    s._tx_codewords = deque([0x55] * 160)
    s._flush_rtp_locked(11)
    assert not s._rtp_tx_primed
    assert bytes(s._tx_codewords) == b'\x55' * 160
