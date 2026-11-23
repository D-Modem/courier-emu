import struct

from courier_emu.dsp import NativeC5x


def test_write_trace_rollover_keeps_order_and_lowering_limit_trims_tail():
    words = [word for value in range(1, 13) for word in (0xb900 | value, 0x9060)]
    with NativeC5x.from_program(0x8000, struct.pack('<24H', *words)) as core:
        core.set_pc(0x8000)
        core.set_data_trace_filter(0x60)
        core.set_data_event_limit(4)
        core.trace_data_writes()
        core.step(24)
        events = core.data_events()
        assert [event['value'] for event in events] == [9, 10, 11, 12]
        assert [event['pc'] for event in events] == [0x8011, 0x8013, 0x8015, 0x8017]
        assert all(event['address'] == 0x60 for event in events)
        core.set_data_event_limit(2)
        assert core.data_events() == events[-2:]
        core.trace_data_writes(clear=True)
        assert core.data_events() == []


def test_fixed_watch_read_trace_rollover_retains_repeated_reads():
    # LDP #6; repeated LACL @5c reads the fixed watched cell 035c.
    words = [0xbc06] + [0x695c] * 5
    with NativeC5x.from_program(0x8000, struct.pack('<6H', *words)) as core:
        core.set_pc(0x8000)
        core.set_data(0x035c, 0x1234)
        core.set_data_event_limit(2)
        core.trace_data_writes()
        core.step(6)
        events = core.data_events()
        assert [event['value'] for event in events] == [0x1234, 0x1234]
        assert [event['address'] for event in events] == [0x035c, 0x035c]
        assert [event['pc'] for event in events] == [0x8004, 0x8005]
