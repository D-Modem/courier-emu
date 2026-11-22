"""Deterministic offline playout deadlines; no sockets or sleeps."""
import pytest

from courier_emu.rtp import RtpPacket, RtpPlayout

PEER = ('127.0.0.1', 5000)


def push(buffer, sequence, timestamp, payload, now=0, ssrc=7, source=PEER):
    return buffer.push(RtpPacket(sequence, timestamp, ssrc, 0, payload),
                       source, PEER, now)


def at_sample(sample):
    return .06 + sample / 8000 + .00000001


def test_reorders_by_timestamp_and_preserves_arbitrary_binary():
    b = RtpPlayout()
    assert push(b, 1, 1000, bytes(range(160)))
    assert push(b, 3, 1320, b'C' * 160, .01)
    assert push(b, 2, 1160, b'B' * 160, .03)
    assert b.drain(.059) == b''
    assert b.drain(at_sample(480)) == bytes(range(160)) + b'B' * 160 + b'C' * 160
    assert b.missing_samples == 0


def test_initial_arrival_can_be_reordered_during_priming():
    b = RtpPlayout()
    push(b, 2, 160, b'B' * 160)
    assert push(b, 1, 0, b'A' * 160, now=.01)
    assert b.drain(at_sample(320)) == b'A' * 160 + b'B' * 160
    assert b.missing_samples == 0


def test_missing_deadline_inserts_idle_without_compressing_timeline():
    b = RtpPlayout()
    push(b, 1, 0, b'A' * 160)
    push(b, 3, 320, b'C' * 160)
    assert b.drain(at_sample(480)) == b'A' * 160 + b'\xff' * 160 + b'C' * 160
    assert b.missing_samples == 160
    assert not push(b, 2, 160, b'B' * 160, at_sample(480))
    assert b.late_packets == 1
    assert b.drain(at_sample(640)) == b'\xff' * 160
    assert b.missing_samples == 320


def test_late_arrival_cannot_revive_expired_samples_before_drain():
    b = RtpPlayout()
    push(b, 1, 0, b'A' * 160)
    assert not push(b, 2, 160, b'B' * 160, at_sample(320))
    assert b.drain(at_sample(320)) == b'A' * 160 + b'\xff' * 160


def test_sequence_and_timestamp_wrap_do_not_change_playout():
    b = RtpPlayout()
    push(b, 65535, 0xfffffff0, b'A' * 160)
    push(b, 0, 144, b'B' * 160)
    assert b.drain(at_sample(320)) == b'A' * 160 + b'B' * 160
    assert b.missing_samples == 0


def test_source_and_ssrc_are_pinned_until_dialog_reset():
    b = RtpPlayout()
    assert not push(b, 1, 0, b'X', source=('127.0.0.2', 5000))
    assert push(b, 1, 0, b'A' * 160)
    assert not push(b, 2, 160, b'X' * 160, ssrc=8)
    assert not push(b, 2, 160, b'X', source=('127.0.0.1', 5001))
    assert b.rejected_sources == 2
    assert b.rejected_ssrc == 1
    b.reset_stream()
    assert push(b, 1, 0, b'B' * 160, now=1, ssrc=8)
    assert b.drain(1 + at_sample(160)) == b'B' * 160


def test_no_sdp_endpoint_cannot_claim_stream():
    b = RtpPlayout()
    assert not b.push(RtpPacket(1, 0, 7, 0, b'A'), PEER, None, 0)
    assert b.drain(100) == b''


def test_duplicate_and_overlap_do_not_overwrite_samples():
    b = RtpPlayout()
    assert push(b, 1, 0, b'A' * 160)
    assert not push(b, 1, 0, b'X' * 160)
    assert not push(b, 2, 80, b'X' * 160)
    assert b.overlap_packets == 2
    assert b.drain(at_sample(160)) == b'A' * 160


def test_timestamp_jump_is_bounded_without_reanchoring():
    b = RtpPlayout()
    push(b, 1, 0, b'A' * 160)
    assert not push(b, 2, 1000000, b'X' * 160)
    assert push(b, 3, 160, b'B' * 160)
    assert b.status()['buffered_samples'] == 320
    assert b.out_of_window_packets == 1
    assert b.drain(at_sample(320)) == b'A' * 160 + b'B' * 160


def test_stalled_consumer_fails_closed_and_pcma_idle_is_explicit():
    b = RtpPlayout(silence=0xd5)
    push(b, 1, 0, b'A')
    assert b.drain(at_sample(2)) == b'A\xd5'
    with pytest.raises(RuntimeError, match='stalled'):
        b.drain(100)


@pytest.mark.parametrize('delay,capacity', [(-1, 100), (100, 100), (0, 0)])
def test_invalid_capacity(delay, capacity):
    with pytest.raises(ValueError):
        RtpPlayout(delay_samples=delay, capacity_samples=capacity)
