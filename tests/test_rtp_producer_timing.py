from courier_emu.rtp import RtpTransmitStats


def test_producer_gaps_measure_input_cadence_separately_from_packet_gaps():
    stats = RtpTransmitStats()
    stats.produced(10, 800, 800)
    stats.sent(10, 10, 800)
    stats.sent(10.02, 10.02, 640)
    stats.produced(10.193, 800, 800)
    assert stats.produced_samples == 1600
    assert abs(stats.max_producer_gap_ms - 193) < 1e-6
    assert abs(stats.max_packet_gap_ms - 20) < 1e-6


def test_rebuffer_records_producer_age_without_changing_media_state():
    stats = RtpTransmitStats()
    stats.produced(10, 160, 160)
    stats.rebuffered(10.193, 0)
    assert stats.rebuffer_events == 1
    event = stats.rebuffer_history[0]
    assert event['queued_samples'] == 0
    assert abs(event['producer_gap_ms'] - 193) < 1e-6
    assert stats.produced_samples == 160


def test_rebuffer_history_is_bounded_and_status_is_serializable():
    import json
    stats = RtpTransmitStats()
    for i in range(50):
        stats.rebuffered(i, 0)
    assert stats.rebuffer_events == 50
    assert len(stats.rebuffer_history) == 32
    assert stats.rebuffer_history[0]['monotonic_seconds'] == 18
    status = stats.status()
    assert 'last_produced_at' not in status
    json.dumps(status)


def test_sample_clock_slip_is_not_hidden_by_resetting_packet_deadlines():
    stats = RtpTransmitStats()
    for n in range(101):
        # Only 1 ms of extra gap each packet, but 100 ms total sample slip.
        now = 10 + n * .021
        stats.sent(now, now, 160)
    assert stats.max_deadline_late_ms == 0
    assert abs(stats.max_packet_gap_ms - 21) < 1e-6
    assert abs(stats.sample_clock_late_ms - 100) < 1e-6
    assert abs(stats.max_sample_clock_late_ms - 100) < 1e-6
    assert stats.sent_samples == 101 * 160
    assert not any(k.startswith('_') for k in stats.status())
    # New media epoch can establish a new reference, not inherit old slip.
    stats.last_sent_at = None
    stats.sent(100, 100, 160)
    assert stats.sample_clock_late_ms == 0
    assert abs(stats.max_sample_clock_late_ms - 100) < 1e-6


def test_sample_clock_returns_to_original_phase_after_real_packet_catchup():
    stats = RtpTransmitStats()
    stats.sent(10, 10, 480)
    stats.sent(10.05, 10.02, 320)
    assert abs(stats.sample_clock_late_ms - 30) < 1e-6
    stats.sent(10.05, 10.04, 160)
    stats.sent(10.06, 10.06, 160)
    assert abs(stats.sample_clock_late_ms) < 1e-6
    assert abs(stats.max_sample_clock_late_ms - 30) < 1e-6


def test_empty_producer_calls_do_not_hide_a_production_outage():
    stats = RtpTransmitStats()
    stats.produced(10, 160, 160)
    stats.produced(10.1, 0, 0)
    stats.produced(10.2, 160, 160)
    assert abs(stats.max_producer_gap_ms - 200) < 1e-6
