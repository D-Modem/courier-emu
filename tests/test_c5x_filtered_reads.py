"""Opt-in read tracing for diagnosing DSP sample-ring ownership."""
import struct

from courier_emu.dsp import NativeC5x


def test_filtered_reads_preserve_repeated_reads_and_identical_writes():
    # LDP #1; LACL @0; LACL @0; SACL @0; IDLE
    image = struct.pack('<5H', 0xbc01, 0x6900, 0x6900, 0x9000, 0xbe22)
    with NativeC5x.from_program(0x8000, image) as core:
        core.set_pc(0x8000)
        core.set_data(0x80, 7)
        core.set_data_trace_filter(0x80)
        core.trace_filtered_reads()
        core.trace_data_writes()
        core.step(5)
        events = core.data_events()
        assert [(e['pc'], e['address'], e['value']) for e in events] == [
            (0x8001, 0x80, 7), (0x8002, 0x80, 7), (0x8003, 0x80, 7),
        ]
        assert core.data(0x80) == 7


def test_filtered_trace_stays_write_only_by_default():
    image = struct.pack('<5H', 0xbc01, 0x6900, 0x6900, 0x9000, 0xbe22)
    with NativeC5x.from_program(0x8000, image) as core:
        core.set_pc(0x8000)
        core.set_data(0x80, 7)
        core.set_data_trace_filter(0x80)
        core.trace_data_writes()
        core.step(5)
        assert [e['pc'] for e in core.data_events()] == [0x8003]
