import ctypes
import struct

from courier_emu.dsp import LaneHostIo, NativeC5x
from courier_emu.worker_poll import WorkerPoll


def access(model, direction, port, value=0, now=0):
    out = ctypes.c_uint16()
    function = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_int,
                               ctypes.c_uint16, ctypes.c_int, ctypes.c_uint16,
                               ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint16))(model.function)
    return function(model.context, direction, port, 1, value, now, ctypes.byref(out))


def test_recent_ring_is_opt_in_bounded_and_non_draining():
    model = LaneHostIo()
    try:
        model.record_irq(0, 6, 12, 0, 0x80000, 0x202)
        assert model.recent_events() == []
        model.set_recent()
        for i in range(3000):
            model.record_irq(i, 6, 12, 0, 0x80000 + i, 0x202)
        rows = model.recent_events()
        assert len(rows) == 2048
        assert rows[0]['cpu_instructions'] == 952
        assert rows[-1]['pc'] == 0x80000 + 2999
        assert model.recent_events() == rows
        model.set_recent(False)
        assert model.recent_events() == []
    finally:
        model.close()


def test_recent_lane_events_do_not_advance_dsp_or_drain_legacy_capture():
    dsp = NativeC5x.from_program(0, struct.pack('<16H', *([0x8b00] * 16)))
    model = LaneHostIo()
    try:
        model.configure(dsp.handle, True, command_port=0x18, ack_port=0x1a,
                        lane_first=0x40, banks=6, dsp_first=0x58, dsp_status=0x56)
        dsp.step(3)
        before = dsp.state()
        model.set_capture(True)
        model.set_recent()
        assert access(model, 1, 0x40, now=10)
        assert access(model, 2, 0x1a, value=2, now=20)
        model.record_irq(21, 6, 12, 0, 0x93a34, 0x202)
        assert dsp.state() == before
        assert dsp.io(0x56) & 0x200
        rows = model.recent_events()
        assert [r['kind'] for r in rows] == [3, 2, 6]
        assert all(r['dsp_instructions'] == before['instructions'] for r in rows)
        assert all(r['dsp_cycles'] == before['cycles'] for r in rows)
        raw = model.take_capture()
        assert len(raw) == 32
        assert struct.unpack('<QBBH4x', raw[16:]) == (20, 2, 0x1a, 2)
        assert model.recent_events() == rows
    finally:
        model.close()
        dsp.close()


class PollCpu(ctypes.Structure):
    _fields_ = [('regs', ctypes.POINTER(ctypes.c_uint32)),
                ('memory', ctypes.c_void_p), ('memory_size', ctypes.c_size_t),
                ('guard', ctypes.c_void_p), ('io_events', ctypes.c_void_p),
                ('io_event_count', ctypes.c_uint32), ('mmio_events', ctypes.c_void_p),
                ('mmio_count', ctypes.c_uint32), ('batch_total', ctypes.c_uint64)]


def test_native_eoi_observation_keeps_original_controller_semantics():
    poll = WorkerPoll()  # Also checks the native/Python layout after the added pointer.
    model = LaneHostIo()
    try:
        model.set_recent()
        state = poll.state
        state.armed = 1
        state.stack_depth = 1
        state.stack[0] = 12
        state.int0_in_service = 1
        state.diagnostic_trace = model.context
        state.elide_until = 0  # Return after applying EOIs, without advancing a core.
        regs = (ctypes.c_uint32 * 14)()
        regs[9], regs[12], regs[13] = 0x8000, 0x1234, 0x202
        events = (ctypes.c_uint8 * 8)(2, 255, 0, 0, 0, 128, 2, 0)
        cpu = PollCpu(regs, None, 0, None, None, 0, ctypes.addressof(events), 1, 123)
        invoke = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint64,
                                 ctypes.c_uint32, ctypes.c_void_p)(poll.function)
        assert invoke(poll.context, 123, 0x202, ctypes.byref(cpu)) == 0
        assert state.stack_depth == state.int0_in_service == 0
        assert events[7] == 1
        event, = model.recent_events()
        assert event['kind'] == 5 and event['cpu_instructions'] == 123
        assert event['port_or_vector'] == 12 and event['value'] == 0x8000
        assert event['pc'] == 0x81234
    finally:
        model.close()
