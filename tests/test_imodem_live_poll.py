"""Guards for the explicitly opt-in live native polling experiment."""
import ctypes
import struct
import time

import pytest
from types import SimpleNamespace

from courier_emu.bri import BriNetwork
from courier_emu.dsp import ImodemHostIo, ImodemShared, NativeC5x
from courier_emu.poll_state import PollState, native_monotonic_ns


def test_live_native_target_extrapolates_wall_time_not_guest_instructions():
    shared = ImodemShared()
    state = PollState()
    state.ips = 5_000_000
    dsp = NativeC5x.from_program(0, struct.pack('<20000H', *([0x8b00] * 20000)))
    model = ImodemHostIo(shared, cycles_per_instruction=8.064, read_quantum=0)
    try:
        model.set_poll_state(state)
        model.configure(dsp.handle, True, wallclock=True)
        model.set_wall_target(0)
        state.live_ns = native_monotonic_ns() - 1_000_000
        state.live_dsp = 100
        model.advance_serve(512, 0)
        # The published zero target alone would execute nothing. Wall time
        # supplies the target, but the existing bounded CPU-turn budget stays.
        assert dsp.state()['cycles'] == 4128
        model.advance_serve(512, 0)
        assert dsp.state()['cycles'] == 4128
        state.live_ns = 0
        model.set_wall_target(0)
        model.advance_serve(1024, 0)
        assert dsp.state()['cycles'] == 4128
    finally:
        model.close()
        dsp.close()


def test_live_native_target_uses_configured_digital_dsp_clock():
    shared = ImodemShared()
    state = PollState()
    state.ips = 5_000_000
    # An infinite branch permits starting above the erroneous half-rate
    # target without requiring a long program or precise wall-clock sleeps.
    dsp = NativeC5x.from_program(0, struct.pack('<2H', 0x7980, 0))
    model = ImodemHostIo(shared, cycles_per_instruction=8.064, read_quantum=0)
    try:
        dsp.step_cycles(30_000_000)
        before = dsp.state()['cycles']
        model.set_poll_state(state)
        model.configure(dsp.handle, True, wallclock=True)
        model.set_wall_target(0)
        state.live_ns = native_monotonic_ns() - 1_000_000_000
        state.live_dsp = 0
        model.advance_serve(512, 0)
        # 40.32 MHz owes cycles; the old 20.16 MHz target incorrectly sees
        # this core as ahead. Retain the existing CPU-turn catch-up bound.
        assert 4128 <= dsp.state()['cycles'] - before <= 4129
    finally:
        model.close()
        dsp.close()


def test_paced_live_scheduler_can_recover_a_frame_without_extra_port_budget():
    def access(model, direction, port, *, now):
        result = ctypes.c_uint16()
        call = ctypes.CFUNCTYPE(
            ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint16,
            ctypes.c_int, ctypes.c_uint16, ctypes.c_uint64,
            ctypes.POINTER(ctypes.c_uint16))(model.function)
        return call(model.context, direction, port, 1, 0, now,
                    ctypes.byref(result)), result.value

    shared = ImodemShared()
    state = PollState()
    state.ips = 5_000_000
    state.live_cpu_ns = native_monotonic_ns()
    dsp = NativeC5x.from_program(0, struct.pack('<20000H', *([0x8b00] * 20000)))
    model = ImodemHostIo(shared, cycles_per_instruction=8.064, read_quantum=0)
    try:
        model.set_poll_state(state)
        model.configure(dsp.handle, True, wallclock=True)
        model.set_wall_target(15120)
        model.advance_serve(512, 0, supervisor_turn=True)
        assert dsp.state()['cycles'] == 5040
        model.advance_serve(512, 0, supervisor_turn=True)
        assert dsp.state()['cycles'] == 5040
        # Port reads are not scheduler turns, including at the same count.
        assert access(model, 1, 0x18, now=512)[0] == 1
        assert dsp.state()['cycles'] == 5040
        assert access(model, 1, 0x18, now=514)[0] == 1
        assert dsp.state()['cycles'] == 5056
        # A fallback zero-quantum port write must not grant a frame either.
        model.advance_serve(516, 0)
        assert dsp.state()['cycles'] == 5072
        model.advance_serve(1024, 0, supervisor_turn=True)
        # Port-driven cycles count against the frame allowance.
        assert dsp.state()['cycles'] == 10080
        model.advance_serve(1536, 0, supervisor_turn=True)
        assert dsp.state()['cycles'] == 15120
        model.advance_serve(2048, 0, supervisor_turn=True)
        assert dsp.state()['cycles'] == 15120
    finally:
        model.close()
        dsp.close()


@pytest.mark.parametrize('lag_ns,advance,expected_sleep', [
    (0, 5_000, .001),       # ahead: bounded sleep even in fallback service
    (2_000_000, 0, None),   # behind: rebase rather than banking a CPU sprint
    (0, 0, None),
])
def test_live_cpu_fallback_pacing(monkeypatch, lag_ns, advance, expected_sleep):
    from courier_emu import isdn

    now = 10_000_000_000
    state = PollState()
    state.live_cpu_ns = now - lag_ns
    state.live_cpu_count = 100
    machine = SimpleNamespace(_ps=state, instructions=100 + advance)
    sleeps = []
    monkeypatch.setattr(isdn, 'native_monotonic_ns', lambda: now)
    monkeypatch.setattr(isdn.time, 'sleep', sleeps.append)
    isdn.IsdnMachine._pace_live_cpu(machine)
    assert sleeps == ([] if expected_sleep is None else [expected_sleep])
    if lag_ns:
        assert state.live_cpu_ns == now
        assert state.live_cpu_count == machine.instructions


def test_live_native_cpu_pacing_applies_without_poll_elision():
    state = PollState()
    state.ips = 5_000_000
    shared = ImodemShared()  # elide_on is false; no DSP or bearer attached
    model = ImodemHostIo(shared, cycles_per_instruction=8.064, read_quantum=0)
    try:
        model.set_poll_state(state)
        poll = model.library.courier_imodemio_poll
        poll.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32,
                         ctypes.c_void_p]
        poll.restype = ctypes.c_int
        unused_cpu = ctypes.create_string_buffer(64)
        state.live_cpu_ns = native_monotonic_ns() - 100_000_000
        assert poll(model.context, 1234, 0, unused_cpu) == 0
        assert state.live_cpu_count == 1234
        assert native_monotonic_ns() - state.live_cpu_ns < 50_000_000
        # A far-ahead CPU waits at most one service window, not the full
        # one-second deficit. The sleep occurs despite disabled elision.
        state.live_cpu_ns = native_monotonic_ns()
        start = time.monotonic_ns()
        assert poll(model.context, 5_001_234, 0, unused_cpu) == 0
        assert time.monotonic_ns() - start >= 500_000
    finally:
        model.close()


def test_live_bri_quiet_window_requires_connected_active_call_and_respects_timer():
    peer = SimpleNamespace(realtime_clock=True,
                           session=SimpleNamespace(state='connected'))
    bri = BriNetwork(activate_at=None, activated_at=0, state='established',
                     call_state='active', media_channel=1, media_peer=peer)
    dsc = SimpleNamespace(activated=True, sent=[])
    assert bri.quiet_until(dsc) == 1 << 62
    bri._t303_expiry = 12345
    assert bri.quiet_until(dsc) == 12345
    peer.session.state = 'closed'
    assert bri.quiet_until(dsc) is None
    peer.session.state = 'connected'
    bri.call_state = 'null'
    assert bri.quiet_until(dsc) is None
    bri.call_state = 'active'
    dsc.sent.append(b'pending Q.931')
    assert bri.quiet_until(dsc) is None
