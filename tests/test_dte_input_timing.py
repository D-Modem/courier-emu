from courier_emu.uart import DteInputTiming


def test_online_delivery_history_is_bounded_and_preserves_first_and_worst_gaps():
    timing = DteInputTiming()
    for index in range(100):
        at = index * 5000 + (10000 if index >= 50 else 0)
        timing.observe(instructions=at, line_frame=index, byte=index, queued=3,
                       wire_started=at - 4608)
    status = timing.status()
    assert status['deliveries'] == 100
    assert len(status['first']) == len(status['recent']) == 16
    assert status['first'][0]['index'] == 0
    assert status['recent'][-1]['index'] == 99
    assert len(status['largest_gaps']) == 8
    assert status['largest_gaps'][0]['index'] == 50
    assert status['largest_gaps'][0]['gap_instructions'] == 15000
    assert status['recent'][-1]['wire_elapsed_instructions'] == 4608
