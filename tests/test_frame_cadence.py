"""Codec-derived periodic cadence, independently of IRQ polling frequency."""
import math
import struct
from types import SimpleNamespace

import pytest

from courier_emu.dsp import NativeC5x
from courier_emu.machine import CourierMachine
from courier_emu.worker_poll import WorkerPoll
from courier_emu.timebase import COURIER_20MHZ, COURIER_25MHZ


@pytest.fixture
def clocks():
    with NativeC5x.from_program(0, struct.pack('<H', 0xbe22)) as core:
        core.configure_rom_codec()
        core.configure_line_frame_interrupt(5, 0xffff)
        m = CourierMachine.__new__(CourierMachine)
        m._frame_hz = None
        m._frame_codec_samples = 3
        m._frame_codec_active = False
        m._use_dsp_xf_int0 = False
        m._frame_xf_core = None
        m._rom_tick = True
        m._frame_fallback = m.frame_instructions = 1415
        m._last_frame = 0
        m.dsp_bridge = SimpleNamespace(core=core, boot_rom_enabled=True,
                                       dsp_cycles_per_x86=11.86)
        m.dsp_bridge.set_timebase = lambda tb: setattr(
            m.dsp_bridge, 'dsp_cycles_per_x86', tb.dsp_cycles_per_x86)
        poll = WorkerPoll()  # Verifies the ABI, including fractional phase fields.
        s = poll.state
        s.core = core.handle
        s.cycles_per_x86 = 11.86
        s.frame_auto = 1
        s.frame_codec_samples = 3
        s.frame_fallback = s.frame_instructions = 1415
        yield m, core, poll


def program_codec(core):
    for word in (3, 0x010a, 3, 0x0214, 3, 0x0620):
        core.host_write(0x21, word)


def compare(m, poll, now):
    python_due = m._frame_irq_due(now)
    native_due = poll.refresh_frame_cadence(now)
    assert native_due == python_due
    assert poll.state.frame_instructions == m.frame_instructions
    assert poll.state.last_frame == m._last_frame
    assert bool(poll.state.frame_codec_active) == m._frame_codec_active
    return python_due


def consume_native(poll, now):
    # Mirror the native entry's phase update; no CPU/DSP time is advanced.
    s = poll.state
    s.last_frame += s.frame_instructions
    if now - s.last_frame >= s.frame_instructions:
        s.last_frame = now - s.frame_instructions


def test_unprogrammed_codec_retains_legacy_bootstrap_cadence(clocks):
    m, core, poll = clocks
    assert not compare(m, poll, 1000)
    assert compare(m, poll, 1415)
    assert m.frame_instructions == 1415
    assert not m._frame_codec_active


def test_cadence_follows_codec_retunes_without_touching_processor_clocks(clocks):
    m, core, poll = clocks
    program_codec(core)
    before = core.state()
    assert not compare(m, poll, 500)
    assert m.frame_instructions == 3 * 5600 / 11.86
    assert m._frame_codec_active
    phase = (500 - m._last_frame) / m.frame_instructions
    core.set_codec_mclk(3840000)  # 9600-Hz x2 rather than 7200-Hz V.34.
    compare(m, poll, 500)
    assert m.frame_instructions == 3 * 4200 / 11.86
    assert (500 - m._last_frame) / m.frame_instructions == pytest.approx(phase)
    assert core.state() == before
    assert m.dsp_bridge.dsp_cycles_per_x86 == 11.86


@pytest.mark.parametrize('samples', [1, 3, 4, 12])
def test_codec_grouping_is_configurable_not_an_x2_rate_table(clocks, samples):
    m, core, poll = clocks
    program_codec(core)
    m._frame_codec_samples = poll.state.frame_codec_samples = samples
    compare(m, poll, 123)
    assert m.frame_instructions == samples * core.codec_state()['frame_period'] / 11.86
    # A divider change, not just the two observed modem rates.
    core.host_write(0x21, 3)
    core.host_write(0x21, 0x023c)
    compare(m, poll, 456)
    assert m.frame_instructions == samples * core.codec_state()['frame_period'] / 11.86


def test_fractional_period_does_not_accumulate_integer_truncation_drift(clocks):
    m, core, poll = clocks
    program_codec(core)
    core.set_codec_mclk(3840000)
    compare(m, poll, 0)
    period = m.frame_instructions
    for index in range(1, 100001):
        now = math.ceil(index * period)
        m._consume_frame_irq(now)
        consume_native(poll, now)
    assert m._last_frame == poll.state.last_frame
    assert abs(m._last_frame - 100000 * period) < 0.001
    # Flooring each frame would lose over 39000 CPU instructions here.
    assert 100000 * (period - int(period)) > 39000


def test_overdue_requests_keep_existing_coalescing_policy(clocks):
    m, core, poll = clocks
    program_codec(core)
    compare(m, poll, 0)
    now = 1000000
    assert compare(m, poll, now)
    m._consume_frame_irq(now)
    consume_native(poll, now)
    assert m._last_frame == poll.state.last_frame == now - m.frame_instructions
    assert compare(m, poll, now)  # One pending edge, not a million-instruction queue.
    m._consume_frame_irq(now)
    consume_native(poll, now)
    assert not compare(m, poll, now)


def test_reset_and_missing_core_return_to_legacy_clock_without_phase_restart(clocks):
    m, core, poll = clocks
    program_codec(core)
    compare(m, poll, 500)
    phase = (500 - m._last_frame) / m.frame_instructions
    core.reset()
    compare(m, poll, 500)
    assert m.frame_instructions == 1415
    assert not m._frame_codec_active
    assert (500 - m._last_frame) / 1415 == pytest.approx(phase)
    m.dsp_bridge.core = None
    poll.state.core = None
    compare(m, poll, 600)


@pytest.mark.parametrize('board', [COURIER_20MHZ, COURIER_25MHZ])
def test_fixed_rate_has_fractional_precision_and_tracks_board_timebase(clocks, board):
    m, core, poll = clocks
    m._frame_hz = 3200
    m.instructions = 500
    phase = 500 / m.frame_instructions
    m._adopt_timebase(board)
    assert board.cpu_clock_hz / board.cycles_per_instruction / m.frame_instructions == pytest.approx(3200)
    assert m.frame_instructions != int(m.frame_instructions)
    assert (500 - m._last_frame) / m.frame_instructions == pytest.approx(phase)


def test_legacy_timebase_adoption_keeps_original_integer_period(clocks):
    m, core, poll = clocks
    m._frame_codec_samples = 0
    m.instructions = 500
    m._adopt_timebase(COURIER_25MHZ)
    assert m.frame_instructions == COURIER_25MHZ.instructions_per_second // 2401
    assert m._last_frame == 0


@pytest.mark.parametrize('mode', ['fixed', 'legacy', 'payload'])
def test_explicit_fixed_rate_legacy_and_non_rom_runs_do_not_follow_codec(clocks, mode):
    m, core, poll = clocks
    program_codec(core)
    if mode == 'fixed':
        m._frame_hz = 2401
    elif mode == 'legacy':
        m._frame_codec_samples = 0
    else:
        m.dsp_bridge.boot_rom_enabled = False
    poll.state.frame_auto = 0
    compare(m, poll, 500)
    assert m.frame_instructions == 1415
    assert not m._frame_codec_active
