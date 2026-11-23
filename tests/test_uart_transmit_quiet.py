from copy import deepcopy
from courier_emu.uart import EbSerial, S0TBUF, S0STS, TRANSMIT_VECTOR
from courier_emu.machine import CourierMachine


def test_quiet_transmit_preserves_exact_event_poll_and_double_buffer_timing():
    plain = EbSerial(control=0x61, baud_compare=0x8015, timed_transmit=True)
    optimized = deepcopy(plain)
    advanced = [0, 0]
    for now in range(0, 16000, 64):
        plain.advance(now, 5.93)
        advanced[0] += 1
        if optimized.transmit_quiet_until(now) is None:
            optimized.advance(now, 5.93)
            advanced[1] += 1
        # Real register accesses always advance the peripheral before access.
        if now % 256 == 0 and now < 8000:
            for uart in (plain, optimized):
                uart.advance(now, 5.93)
                uart.write(S0TBUF, 1, now & 255)
        if now % 192 == 0:
            for uart in (plain, optimized):
                uart.advance(now, 5.93)
            assert plain.read(S0STS, 2) == optimized.read(S0STS, 2)
            if plain.pending:
                assert plain.take_interrupt() == optimized.take_interrupt()
        for name in ('_tx_stop', '_tx_end', '_tx_buffer', 'pending', 'transmit_complete',
                     'transmit_overruns', 'transmitted', 'transmit_busy'):
            assert getattr(plain, name) == getattr(optimized, name), (now, name)
    assert advanced[1] < advanced[0]


def test_due_stop_and_pending_interrupt_are_never_quiet():
    u = EbSerial(control=0x61, baud_compare=0x8015, timed_transmit=True)
    u.advance(0, 5.93)
    u.write(S0TBUF, 1, 0x55)
    stop, end = u._tx_stop, u._tx_end
    assert u.transmit_quiet_until(0) == stop
    assert u.transmit_quiet_until(stop - 1) == stop
    assert u.transmit_quiet_until(stop) is None
    u.advance(stop, 5.93)
    assert list(u.pending) == [TRANSMIT_VECTOR]
    assert u.transmit_quiet_until(stop) is None
    u.take_interrupt()
    assert u.transmit_quiet_until(stop) == end
    assert u.transmit_quiet_until(end) is None
    u.advance(end, 5.93)
    assert u.transmit_quiet_until(end) is None


def test_machine_only_optimizes_online_rom_uart():
    m = CourierMachine.__new__(CourierMachine)
    m.console = None
    m._rom_serial = object()
    m._rom_dte_opened = True
    m.online_mode = True
    m.uart = EbSerial(_tx_stop=200, _tx_end=220)
    assert m._serial_transmit_quiet_until(100) == 200
    for attr, val in [('console', object()), ('_rom_serial', None),
                      ('_rom_dte_opened', False), ('online_mode', False), ('uart', None)]:
        old = getattr(m, attr)
        setattr(m, attr, val)
        assert m._serial_transmit_quiet_until(100) is None
        setattr(m, attr, old)
