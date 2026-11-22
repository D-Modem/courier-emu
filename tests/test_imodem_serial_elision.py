"""UART transmission deadlines bound the opt-in live native poll window."""
import ctypes
import struct
from collections import Counter

import pytest
from types import SimpleNamespace

from courier_emu.dsp import ImodemHostIo, ImodemShared, NativeC5x
from courier_emu.native_bearer import NativeBearer
from courier_emu.isdn import IsdnMachine
from courier_emu.peripheral_clock import PeripheralClock
from courier_emu.poll_state import PollState
from courier_emu.sio import SerialChannel, THR, MSR, MCR, MCR_LOOPBACK


def test_uart_quiet_window_does_not_delay_start_or_receive():
    channel = SerialChannel(0xF4F8, pace=2048)
    assert channel.quiet_until() == 1 << 62
    channel.write(channel.base + THR, ord('A'))
    assert channel.quiet_until() is None  # THR must transfer on next poll
    channel.advance(512)
    assert channel.quiet_until() == 2560
    channel.write(channel.base + THR, ord('B'))
    assert channel.quiet_until() == 2560  # full THR cannot preempt shifter
    channel.feed(b'C')
    assert channel.quiet_until() is None


def test_skipping_quiet_polls_preserves_tx_bytes_status_and_deadlines():
    ordinary = SerialChannel(0xF4F8, pace=2048)
    elided = SerialChannel(0xF4F8, pace=2048)
    for channel in (ordinary, elided):
        channel.write(channel.base + THR, ord('A'))
        channel.advance(512)
        channel.write(channel.base + THR, ord('B'))
    for now in range(1024, 5121, 512):
        ordinary.advance(now)
        due = elided.quiet_until()
        if due is None or now >= due:
            elided.advance(now)
        assert elided.tx == ordinary.tx
        assert elided.pending() == ordinary.pending()
        assert elided.tx_shift == ordinary.tx_shift
        assert elided.tx_holding == ordinary.tx_holding
        assert elided._tx_complete == ordinary._tx_complete


def native_access(model, direction, port, *, size=1):
    value = ctypes.c_uint16()
    call = ctypes.CFUNCTYPE(
        ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_uint16,
        ctypes.c_int, ctypes.c_uint16, ctypes.c_uint64,
        ctypes.POINTER(ctypes.c_uint16))(model.function)
    served = call(model.context, direction, port, size, 0, 0, ctypes.byref(value))
    return served, value.value


@pytest.mark.parametrize('offset', range(8))
@pytest.mark.parametrize('direction', [1, 2])
def test_only_byte_lsr_reads_use_snapshot_and_other_access_invalidates(offset, direction):
    model = ImodemHostIo(ImodemShared(), cycles_per_instruction=8.064, read_quantum=0)
    base = 0xF4F8
    try:
        model.set_serial_status(0, base, 0x61)
        assert native_access(model, 1, base + 5) == (1, 0x61)
        served, _ = native_access(model, direction, base + offset)
        if direction == 1 and offset == 5:
            assert served == 1
        else:
            assert served == 0
            assert native_access(model, 1, base + 5)[0] == 0
        model.set_serial_status(0, base, 0x20)
        assert native_access(model, 1, base + 5) == (1, 0x20)
        assert native_access(model, 1, base + 5, size=2)[0] == 0
        assert native_access(model, 1, base + 5)[0] == 0
        assert model.take_serial_counts() == {base + 5: 3 if served else 2}
        assert model.take_serial_counts() == {}
    finally:
        model.close()


def test_serial_snapshot_invalidation_is_per_channel_and_can_be_disabled():
    model = ImodemHostIo(ImodemShared(), cycles_per_instruction=8.064, read_quantum=0)
    try:
        for index, base in enumerate((0xF4F8, 0xF8F8, 0x80)):
            model.set_serial_status(index, base, 0x20 + index)
        assert native_access(model, 2, 0xF4F8)[0] == 0
        assert native_access(model, 1, 0xF4FD)[0] == 0
        assert native_access(model, 1, 0xF8FD) == (1, 0x21)
        assert native_access(model, 1, 0x85) == (1, 0x22)
        model.set_serial_status(1, 0xF8F8, 0x60, enabled=False)
        assert native_access(model, 1, 0xF8FD)[0] == 0
    finally:
        model.close()


def test_native_uart_fallback_refreshes_status_after_rx_read_and_tx_write():
    from courier_emu.x86_interpreter import (
        UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_X86_INS_IN, UC_X86_INS_OUT,
        UC_X86_REG_AX, UC_X86_REG_BX, UC_X86_REG_CX, Uc)

    model = ImodemHostIo(ImodemShared(), cycles_per_instruction=8.064, read_quantum=0)
    channel = SerialChannel(0xF4F8)
    channel.rx.append(ord('A'))
    uc = Uc(UC_ARCH_X86, UC_MODE_16, profile='386ex')
    uc.native_enabled = True
    uc.mem_map(0, 0x10000)
    # LSR -> BL; RBR -> CL; LSR -> BH; THR='B'; LSR -> AL; HLT.
    uc.mem_write(0, bytes.fromhex(
        'bafdf4 ec 88c3 baf8f4 ec 88c1 bafdf4 ec 88c7 '
        'baf8f4 b042 ee bafdf4 ec f4'))
    calls = []
    def read(cpu, port, size, user):
        calls.append(('read', port))
        return channel.read(port)
    def write(cpu, port, size, value, user):
        calls.append(('write', port))
        channel.write(port, value)
    def refresh():
        model.set_serial_status(0, channel.base, channel.read(channel.base + 5))
    ports = bytearray(65536)
    after = bytearray(65536)
    for port in range(channel.base, channel.base + 8):
        ports[port] = 3
        after[port] = 1
    uc.native_host_io = (model.function, model.context, ports)
    uc.native_after_io = refresh
    uc.native_after_io_ports = after
    uc.hook_add(UC_HOOK_INSN, read, instruction=UC_X86_INS_IN)
    uc.hook_add(UC_HOOK_INSN, write, instruction=UC_X86_INS_OUT)
    refresh()
    try:
        uc.emu_start(0, 0, count=100)
        assert uc.reg_read(UC_X86_REG_BX) == 0x6061
        assert uc.reg_read(UC_X86_REG_CX) & 255 == ord('A')
        assert uc.reg_read(UC_X86_REG_AX) & 255 == 0
        assert calls == [('read', channel.base), ('write', channel.base)]
        assert channel.tx_holding == ord('B')
        assert model.take_serial_counts() == {channel.base + 5: 3}
    finally:
        model.close()


def test_stable_msr_snapshot_does_not_acknowledge_deltas_or_loopback():
    channel = SerialChannel(0xF4F8)
    original = channel.deltas
    assert original != 0
    assert channel.stable_modem_status() is None
    assert channel.deltas == original
    assert channel.read(channel.base + MSR) == channel.signals | original
    assert channel.deltas == 0
    assert channel.stable_modem_status() == channel.signals
    channel.write(channel.base + MCR, MCR_LOOPBACK)
    assert channel.stable_modem_status() is None


def test_msr_first_read_acknowledges_in_python_then_native_repeats_are_pure():
    from courier_emu.x86_interpreter import (
        UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_X86_INS_IN,
        UC_X86_REG_BX, Uc)
    model = ImodemHostIo(ImodemShared(), cycles_per_instruction=8.064, read_quantum=0)
    channel = SerialChannel(0xF4F8)
    original = channel.deltas
    uc = Uc(UC_ARCH_X86, UC_MODE_16, profile='386ex')
    uc.native_enabled = True
    uc.mem_map(0, 0x10000)
    uc.mem_write(0, bytes.fromhex('bafef4 ec 88c3 ec 88c7 f4'))
    calls = []
    def read(cpu, port, size, user):
        calls.append(port)
        return channel.read(port)
    def refresh():
        model.set_serial_status(0, channel.base, channel.read(channel.base + 5),
                                channel.stable_modem_status())
    ports = bytearray(65536)
    for port in range(channel.base, channel.base + 8):
        ports[port] = 3
    uc.native_host_io = (model.function, model.context, ports)
    uc.native_after_io = refresh
    uc.native_after_io_ports = ports
    uc.hook_add(UC_HOOK_INSN, read, instruction=UC_X86_INS_IN)
    refresh()
    assert channel.deltas == original
    try:
        uc.emu_start(0, 0, count=100)
        expected = (channel.signals << 8) | channel.signals | original
        assert uc.reg_read(UC_X86_REG_BX) == expected
        assert channel.deltas == 0
        assert calls == [channel.base + MSR]
        assert model.take_serial_counts() == {channel.base + MSR: 1}
    finally:
        model.close()


def test_uart_resume_advances_dsp_but_leaves_pic_tail_to_python():
    shared, state = ImodemShared(), PollState()
    state.ips = 5_000_000
    state.serial_until = 512
    state.asserted_count = 1
    state.asserted[0] = 13
    shared.elide_on = 1
    shared.elide_until = 10000
    shared.clock_frame = 16
    dsp = NativeC5x.from_program(0, struct.pack('<20000H', *([0x8b00] * 20000)))
    bearer = NativeBearer()
    bearer.configure(True, [], [None, None], 0)
    model = ImodemHostIo(shared, cycles_per_instruction=8.064, read_quantum=0)
    try:
        model.set_poll_state(state)
        model.set_bearer(bearer)
        model.configure(dsp.handle, True)
        poll = model.library.courier_imodemio_poll
        poll.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32,
                         ctypes.c_void_p]
        poll.restype = ctypes.c_int
        cpu = ctypes.create_string_buffer(64)
        assert poll(model.context, 256, 0, cpu) == 1
        before = dsp.state()['cycles']
        state.pic[1].irr = 0
        assert poll(model.context, 512, 0, cpu) == 5
        assert dsp.state()['cycles'] > before
        assert state.pic[1].irr == 0
        # An expired full-service bound always wins over the UART fast path.
        shared.elide_until = 768
        before = dsp.state()['cycles']
        assert poll(model.context, 768, 0, cpu) == 0
        assert dsp.state()['cycles'] == before
    finally:
        model.close()
        bearer.close()
        dsp.close()


def live_machine(channel):
    machine = IsdnMachine.__new__(IsdnMachine)
    machine._ledger = SimpleNamespace(elide_on=0)
    machine._ps = PollState()
    machine._why = Counter()
    machine._native_io = SimpleNamespace(live=True, uart_resume_available=True)
    machine.instructions = 1000
    machine.with_dsp = True
    machine._peripheral_clock = PeripheralClock(5_000_000)
    machine.mailbox = SimpleNamespace(
        _nb=object(), pcm_frame_service=None, error=None, core=object(),
        lookahead_channels=(1,), _publish_mode=lambda: None,
        realtime_target=lambda: 10000)
    machine.dsc = SimpleNamespace(sent=[], interrupting=lambda: False)
    machine.bri = SimpleNamespace(
        call_state='active', media_channel=1, _media_tx_cursor={1: 0},
        media_peer=SimpleNamespace(realtime_clock=True,
                                  session=SimpleNamespace(state='connected')),
        quiet_until=lambda dsc: 1 << 62)
    machine._line_walk = []
    machine.command_base = channel.base
    machine.channels = {channel.base: channel}
    machine._run_end = 1_000_000
    machine.offhook_at = None
    machine.serial_pump = None
    machine.rtos_service = False
    machine.mailbox_service = False
    machine._elision_enabled = 0
    return machine


def test_uart_changes_request_partial_service_without_clearing_other_device_dirtiness():
    machine = live_machine(SerialChannel(0xF4F8))
    machine._ledger.elide_on = 1
    machine._ledger.poll_dirty = 0
    machine._ps.live_ns = 1
    machine._serial_poll_changed()
    assert machine._ps.serial_until == machine.instructions
    assert machine._ledger.poll_dirty == 0
    machine._ledger.poll_dirty = 1
    machine._serial_poll_changed()
    assert machine._ledger.poll_dirty == 1
    machine._native_io.uart_resume_available = False
    machine._ledger.poll_dirty = 0
    machine._serial_poll_changed()
    assert machine._ledger.poll_dirty == 1


def test_uart_only_resume_skips_socket_and_dsp_work():
    machine = IsdnMachine.__new__(IsdnMachine)
    calls = []
    def unexpected(*args):
        raise AssertionError('UART-only resume repeated full device service')
    machine.bri = SimpleNamespace(service=unexpected)
    machine.mailbox = SimpleNamespace(service_pending=unexpected, resume_service=unexpected)
    machine._advance_dsp = unexpected
    machine._peripheral_instructions = lambda: 512
    machine.rtos_service = False
    machine.serial_pump = lambda m: calls.append('serial')
    machine.channels = {}
    machine._advance_line = lambda: None
    machine.offhook_at = None
    machine.dsc = SimpleNamespace(interrupting=lambda: False)
    machine.mailbox_service = False
    machine.pit = SimpleNamespace(counters=[])
    machine.poll_timers(resume=5)
    assert calls == ['serial']


def test_uart_wakes_do_not_slide_socket_deadline(monkeypatch):
    monkeypatch.setenv('COURIER_LIVE_POLL_ELISION', '1')
    machine = live_machine(SerialChannel(0xF4F8))
    machine._live_io_due_ns = 100_500_000
    for stamp in (100_000_000, 100_200_000, 100_499_999):
        monkeypatch.setattr('courier_emu.isdn.native_monotonic_ns', lambda: stamp)
        machine._update_elision()
        assert machine._ps.live_until_ns == 100_500_000


def test_live_elision_stops_at_uart_completion(monkeypatch):
    monkeypatch.setenv('COURIER_LIVE_POLL_ELISION', '1')
    channel = SerialChannel(0xF4F8, pace=2048)
    channel.write(channel.base + THR, ord('A'))
    channel.advance(1000)
    channel.write(channel.base + THR, ord('B'))
    machine = live_machine(channel)
    machine._update_elision()
    assert machine._ledger.elide_on == 1
    assert machine._ps.serial_until == 3048
    assert machine._ledger.elide_until > 3048


def test_live_elision_does_not_skip_staged_receive_and_schedules_pending_output(monkeypatch):
    monkeypatch.setenv('COURIER_LIVE_POLL_ELISION', '1')
    channel = SerialChannel(0xF4F8, pace=2048)
    machine = live_machine(channel)
    channel.feed(b'A')
    machine._update_elision()
    assert machine._ledger.elide_on == 0
    assert machine._why['serial'] == 1
    channel.staged.clear()
    channel._output.extend(b'B')
    machine._update_elision()
    assert machine._ledger.elide_on == 1
    assert machine._ps.serial_until == machine.instructions
