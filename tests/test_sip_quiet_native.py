"""Actual native quiet passes: no DSP work, and hard deadline/IO guards."""
import ctypes
import struct

import pytest

from courier_emu.dsp import LaneHostIo, NativeC5x
from courier_emu.worker_poll import WorkerPoll
from tests.test_board_service_trace import PollCpu


@pytest.fixture
def quiet_poll():
    with NativeC5x.from_program(0x6000, struct.pack('<H', 0xbe22)) as core:
        poll = WorkerPoll()
        s = poll.state
        s.core = core.handle
        s.armed = s.quiet_sip = 1
        s.elide_until = 4096
        s.batch = 4096
        s.timer_poll_period = s.timer_poll_owed = 64
        s.debt = 123.5
        s.cpi = 1.75
        s.mailbox_writes = 42
        regs = (ctypes.c_uint32 * 14)()
        cpu = PollCpu(regs, None, 0, None, None, 0, None, 0, 0)
        invoke = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_uint64,
                                 ctypes.c_uint32, ctypes.c_void_p)(poll.function)
        yield core, s, cpu, lambda now: invoke(poll.context, now, 0, ctypes.byref(cpu))


def test_native_quiet_accumulates_without_dsp_or_line_work(quiet_poll):
    core, s, cpu, invoke = quiet_poll
    before = core.state()
    for now in range(64, 4096, 64):
        assert invoke(now) == 1
        assert s.x86_ticks == s.bridge_instructions == s.last_service == now
        assert s.timer_poll_owed == 64
    assert invoke(4096) == 0
    assert s.x86_ticks == 4032
    assert s.polls == 63
    assert s.line_skipped == s.line_calls == s.tx_consumed == s.resampled == 0
    assert s.debt == 123.5 and s.cpi == 1.75 and s.mailbox_writes == 42
    assert core.state() == before


@pytest.mark.parametrize('codec_due', [False, True])
def test_native_rejects_due_batch_even_if_outer_deadline_is_wrong(quiet_poll, codec_due):
    core, s, cpu, invoke = quiet_poll
    s.elide_until = 100000
    if codec_due:
        s.codec_present = 1
        s.codec_instructions, s.line_frame_instructions = 100, 164
    else:
        s.x86_ticks = 4032
    before = core.state()
    assert invoke(64) == 0
    assert s.last_service == s.polls == 0
    assert core.state() == before


def test_native_stops_at_exchange_deadline_before_dsp_batch(quiet_poll):
    core, s, cpu, invoke = quiet_poll
    # The exchange accumulator can reach its boundary before the DSP's.
    s.elide_until = 256
    for now in (64, 128, 192):
        assert invoke(now) == 1
    assert invoke(256) == 0
    assert s.last_service == s.x86_ticks == 192
    assert core.state()['instructions'] == 0


def test_native_pending_overlay_event_yields_without_losing_event(quiet_poll):
    from tests.test_native_port_models import access
    core, s, cpu, invoke = quiet_poll
    model = LaneHostIo()
    try:
        model.configure(core.handle, True, command_port=0x18, ack_port=0x1a,
                        lane_first=0x40, banks=6, dsp_first=0x58, dsp_status=0x56)
        model.set_overlay_window(bytearray(8), first=1, start=4, strobes=(1, 2))
        model.set_overlay_strobes(True)
        assert access(model, 2, 0x1e, 1)[0] == 1
        assert model.overlay_pending() == 1
        s.quiet_laneio = model.context
        assert invoke(64) == 0
        assert s.last_service == s.polls == s.x86_ticks == 0
        assert model.overlay_pending() == 1
    finally:
        model.close()


def test_native_changed_panel_write_returns_to_python_before_commit(quiet_poll):
    core, s, cpu, invoke = quiet_poll
    s.panel_latch = 7
    events = (ctypes.c_uint8 * 4)(0x14, 0, 8, 1)
    cpu.io_events, cpu.io_event_count = ctypes.addressof(events), 1
    assert invoke(64) == 0
    assert s.last_service == s.polls == s.x86_ticks == 0
