"""Block-boundary reserve tests, without sockets, calls or wall-clock sleeps."""
import pytest

from courier_emu.ata import SipLine


class Session:
    state = 'connected'
    realtime = True

    def __init__(self):
        self.incoming = []
        self.sent = []

    def enable_media_clock(self, **kwargs):
        pass

    def receive_audio(self):
        result, self.incoming = self.incoming, []
        return result

    def send_audio(self, samples):
        self.sent.extend(samples)

    def status(self):
        return {}

    def poll(self):
        pass


class Identity:
    def convert(self, samples):
        return list(samples)


def line(**kwargs):
    session = Session()
    adapter = SipLine(session, line_rate=8000, **kwargs)
    # Isolate scheduling from FIR response/delay (covered by resampler tests).
    adapter._from_network = Identity()
    adapter._to_network = Identity()
    return adapter, session


def test_startup_preserves_entire_answer_waveform():
    adapter, session = line()
    session.incoming = list(range(1, 801))
    assert adapter._peer_samples(800, []) == [0] * 800
    assert adapter._pending == list(range(1, 801))
    session.incoming = list(range(801, 1601))
    assert adapter._peer_samples(800, []) == list(range(1, 801))
    assert adapter.startup_underrun_samples == 800
    assert adapter.active_underrun_samples == 0


def test_two_minute_block_jitter_preserves_every_sample():
    adapter, session = line()
    sent = []
    received = []
    # 100-ms service blocks with +/-20-ms receive scheduling variation.
    # This is consumer-boundary jitter, not missing or synthesized RTP data.
    for frame in range(1200):
        size = (800, 640, 960, 800)[frame % 4]
        start = len(sent) + 1
        block = list(range(start, start + size))
        sent.extend(block)
        session.incoming = block
        output = adapter._peer_samples(800, [123] * 800)
        assert len(output) == 800
        if frame:
            assert all(output)
            received.extend(output)
        else:
            assert output == [0] * 800
    assert received + adapter._pending == sent
    assert adapter.active_underrun_samples == 0
    assert adapter.receive_rebuffers == 0
    assert len(session.sent) == 1200 * 800
    assert adapter.pending_peak <= 1760


def connected_service_line(**kwargs):
    adapter, session = line(**kwargs)
    adapter._pace = lambda count: None
    adapter.exchange.state = 'connected'
    adapter.exchange.off_hook = True
    return adapter, session


def test_real_exchange_slices_do_not_prime_on_less_than_a_full_block():
    adapter, session = connected_service_line()
    # 400 samples cover one 80-sample exchange slice plus the reserve,
    # but cannot cover the caller's paced 800-sample block. The old helper
    # started immediately, then inserted a gap in this same service call.
    session.incoming = list(range(1, 401))
    assert adapter.service(True, [9] * 800, 800) == [0] * 800
    assert adapter._pending == list(range(1, 401))
    assert not adapter._receive_ever_started
    session.incoming = list(range(401, 1201))
    assert adapter.service(True, [9] * 800, 800) == list(range(1, 801))
    assert adapter._pending == list(range(801, 1201))
    assert adapter.active_underrun_samples == 0
    assert adapter._receive_block_samples == 0


def test_segmented_exchange_rebuilds_a_whole_block_after_outage():
    adapter, session = connected_service_line()
    session.incoming = list(range(1, 1121))
    assert adapter.service(True, [], 800) == list(range(1, 801))
    assert adapter.service(True, [], 800) == list(range(801, 1121)) + [0] * 480
    session.incoming = [7] * 800
    assert adapter.service(True, [], 800) == [0] * 800
    session.incoming = [8] * 320
    assert adapter.service(True, [], 800) == [7] * 800
    assert adapter._pending == [8] * 320
    assert adapter.receive_rebuffers == 1
    assert adapter.active_underrun_samples == 1280


def test_two_minute_jitter_through_real_segmented_exchange():
    adapter, session = connected_service_line()
    sent = []
    received = []
    for frame in range(1200):
        size = 400 if frame == 0 else (800, 640, 960, 800)[(frame - 1) % 4]
        start = len(sent) + 1
        session.incoming = list(range(start, start + size))
        sent.extend(session.incoming)
        output = adapter.service(True, [123] * 800, 800)
        assert len(output) == 800
        if frame:
            assert all(output)
            received.extend(output)
        else:
            assert output == [0] * 800
    assert received + adapter._pending == sent
    assert adapter.active_underrun_samples == 0
    assert adapter.receive_rebuffers == 0
    assert len(session.sent) == 1200 * 800


def test_service_clears_block_context_when_exchange_raises():
    adapter, session = connected_service_line()
    def fail(*args):
        raise RuntimeError('exchange failed')
    adapter.exchange.service = fail
    with pytest.raises(RuntimeError, match='exchange failed'):
        adapter.service(True, [], 800)
    assert adapter._receive_block_samples == 0


def test_same_jitter_without_reserve_inserts_active_silence():
    adapter, session = line(receive_buffer_ms=0)
    session.incoming = [7] * 800
    assert adapter._peer_samples(800, []) == [7] * 800
    session.incoming = [8] * 640
    assert adapter._peer_samples(800, []) == [8] * 640 + [0] * 160
    assert adapter.active_underrun_samples == 160


def test_real_outage_is_counted_and_reserve_rebuilt_without_dropping_tail():
    adapter, session = line()
    session.incoming = list(range(1, 1121))
    assert adapter._peer_samples(800, []) == list(range(1, 801))
    assert adapter._peer_samples(800, []) == list(range(801, 1121)) + [0] * 480
    assert adapter.receive_rebuffers == 1
    session.incoming = [7] * 800
    assert adapter._peer_samples(800, []) == [0] * 800
    session.incoming = [8] * 320
    assert adapter._peer_samples(800, []) == [7] * 800
    assert adapter._pending == [8] * 320
    assert adapter.active_underrun_samples == 1280
    assert adapter.startup_underrun_samples == 0


def test_new_call_reprimes_reserve():
    adapter, session = line()
    adapter._receive_started = adapter._receive_ever_started = True
    adapter._pending = [123] * 800
    adapter._sip_state = 'ringing'
    adapter._follow_sip()
    assert not adapter._receive_started
    assert not adapter._receive_ever_started
    assert adapter._pending == []


def test_zero_reserve_retains_legacy_partial_block_behavior():
    adapter, session = line(receive_buffer_ms=0)
    session.incoming = [7] * 80
    assert adapter._peer_samples(160, []) == [7] * 80 + [0] * 80


def test_offline_peer_does_not_acquire_wall_clock_reserve():
    session = Session()
    session.realtime = False
    adapter = SipLine(session)
    assert adapter.status()['receive_buffer_samples'] == 0


def test_slow_analog_consumer_fails_before_backlog_grows_unbounded():
    adapter, session = line()
    adapter._pending = [7] * adapter._receive_capacity
    session.incoming = [8]
    with pytest.raises(RuntimeError, match='emulator is not keeping up'):
        adapter._peer_samples(800, [])
    assert adapter._pending == [7] * adapter._receive_capacity
    assert adapter.status()['receive_error']
    with pytest.raises(RuntimeError, match='emulator is not keeping up'):
        adapter._peer_samples(800, [])


def test_negative_reserve_rejected():
    with pytest.raises(ValueError, match='receive buffer'):
        line(receive_buffer_ms=-1)
