from types import SimpleNamespace

from courier_emu.machine import CourierMachine


def machine(count=0):
    m = CourierMachine.__new__(CourierMachine)
    m._use_dsp_xf_int0 = True
    m._frame_hz = None
    m._rom_tick = True
    m._frame_xf_core = None
    m._frame_xf_seen = m._frame_xf_sample = 0
    m._frame_xf_delivered = m._frame_xf_coalesced = 0
    m._last_frame, m.frame_instructions = 0, 1415
    core = SimpleNamespace(count=count)
    core.xf_falling_edges = lambda: core.count
    m.dsp_bridge = SimpleNamespace(core=core, boot_rom_enabled=True)
    return m, core


def test_no_fabricated_frame_edges_before_dsp_pulses():
    m, core = machine()
    assert not m._frame_irq_due(100000)
    assert m._frame_xf_delivered == 0
    core.count = 1
    assert m._frame_irq_due(100001)
    m._consume_frame_irq(100001)
    assert not m._frame_irq_due(200000)
    assert m._frame_xf_delivered == 1


def test_multiple_dsp_edges_latch_one_request_not_a_queue():
    m, core = machine(7)
    assert m._frame_irq_due(100)
    assert m._frame_irq_due(200)  # Checking does not consume the request.
    m._consume_frame_irq(200)
    assert m._frame_xf_seen == 7
    assert m._frame_xf_coalesced == 6
    assert m._frame_xf_delivered == 1
    assert not m._frame_irq_due(10000)
    core.count = 8
    assert m._frame_irq_due(10001)
    m._consume_frame_irq(10001)
    assert m._frame_xf_coalesced == 6


def test_core_counter_reset_does_not_leave_the_new_dsp_muted():
    m, core = machine(100)
    assert m._frame_irq_due(100)
    m._consume_frame_irq(100)
    core.count = 0
    assert not m._frame_irq_due(200)
    core.count = 1
    assert m._frame_irq_due(300)


def test_rebuilt_core_starts_its_own_edge_counter():
    m, core = machine(100)
    assert m._frame_irq_due(100)
    m._consume_frame_irq(100)
    m.dsp_bridge.core = SimpleNamespace(xf_falling_edges=lambda: 1)
    assert m._frame_irq_due(200)
    m._consume_frame_irq(200)
    assert m._frame_xf_seen == 1


def test_explicit_frame_rate_and_disabled_control_keep_original_phase_accounting():
    for explicit in (True, False):
        m, core = machine(999)
        if explicit:
            m._frame_hz = 2401
        else:
            m._use_dsp_xf_int0 = False
        assert not m._frame_irq_due(1000)
        assert m._frame_irq_due(1500)
        m._consume_frame_irq(1500)
        assert m._last_frame == 1415
        assert not m._frame_irq_due(2000)
        assert m._frame_xf_delivered == 0
